"""Roster read + manual edit + publish. RLS-scoped by the caller's token via get_ctx."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, get_ctx, require_decide
from emma_core.db import get_service_client
from emma_core.models import (
    CellWriteRequest, PeriodCreateRequest, PeriodOut, PublishRosterOut,
    PublishRosterRequest, RosterGrid, ShiftDef, TaskDefOut, VersionOut,
)
from emma_core.permissions import Feature
from emma_core.services import audit
from emma_core.services import optimize as opt
from emma_core.services import publication as publication_svc
from emma_core.services import roster as svc
from emma_core.services import scheduling as scheduling_svc
from emma_core.services import validation as validation_svc
from emma_core.services import roster_history as history_svc
from emma_core.permissions import can_read
from api.deps import require_read, require_write

router = APIRouter(tags=["roster"])
WRITE_ROLES = {"superintendent", "admin", "scheduler"}


def _require_write_role(ctx: AuthCtx) -> None:
    if str(ctx.profile.role) not in WRITE_ROLES:
        raise api_error(
            403,
            "forbidden",
            "Only a superintendent, admin or scheduler may change a roster.",
        )


# `manual_override_log` only ever holds cells; this covers the rest.
def _audit(ctx: AuthCtx, action: str, entity_table: str, *,
           entity_id: str | None = None, before: dict | None = None,
           after: dict | None = None) -> None:
    audit.record(
        ctx.client, facility_id=ctx.facility_id, action=action,
        entity_table=entity_table, entity_id=entity_id,
        before=before, after=after,
        actor_profile_id=ctx.profile_id, actor_email=ctx.profile.email,
    )


# ── periods ─────────────────────────────────────────────────────────────────
@router.get("/roster-periods", response_model=list[PeriodOut])
def list_periods(ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_periods(ctx.client, ctx.facility_id)


@router.post("/roster-periods", status_code=201)
def create_period(body: PeriodCreateRequest, ctx: AuthCtx = Depends(require_write(Feature.ROSTER_AI_DRAFT))):
    period, version = svc.create_period(
        ctx.client, facility_id=ctx.facility_id,
        period_start=body.period_start, period_end=body.period_end,
        cycle_type=body.cycle_type, created_by=ctx.profile_id,
        create_manual_version=body.create_manual_version,
    )
    _audit(ctx, "create", "roster_periods", entity_id=period["id"],
           after={"period_start": body.period_start, "period_end": body.period_end,
                  "cycle_type": body.cycle_type,
                  "manual_version_id": version["id"] if version else None})
    return {"period": PeriodOut.model_validate(period),
            "manual_version_id": version["id"] if version else None}


# ── versions ────────────────────────────────────────────────────────────────
@router.get("/roster-versions", response_model=list[VersionOut])
def list_versions(period_id: str | None = Query(default=None),
                  ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_versions(ctx.client, ctx.facility_id, period_id)


# ── grid read ───────────────────────────────────────────────────────────────
@router.get('/roster-history')
def roster_history(period_id: str = Query(...), version_id: str | None = Query(default=None),
                   ctx: AuthCtx = Depends(require_read(Feature.ROSTER_VIEW))):
    try:
        return history_svc.read_history(ctx.client, ctx.facility_id, period_id, version_id,
            include_audit=can_read(ctx.profile.role, Feature.AUDIT_LOG))
    except ValueError as exc:
        raise api_error(404, 'not_found', str(exc)) from exc


@router.get('/roster-history/download.csv')
def download_roster_audit(period_id: str = Query(...), version_id: str | None = Query(default=None),
                          ctx: AuthCtx = Depends(require_read(Feature.AUDIT_LOG))):
    try:
        history = history_svc.read_history(ctx.client, ctx.facility_id, period_id, version_id,
                                          include_audit=True, limit=10000)
        content = history_svc.audit_csv(history)
    except ValueError as exc:
        raise api_error(409 if 'limit' in str(exc) else 404, 'audit_unavailable', str(exc)) from exc
    return Response(content, media_type='text/csv; charset=utf-8', headers={
        'Content-Disposition': 'attachment; filename="roster-audit.csv"',
        'Cache-Control': 'private, no-store',
    })


@router.get("/rosters/{period_id}", response_model=RosterGrid)
def get_roster(period_id: str,
               version_id: str | None = Query(default=None),
               version_type: str | None = Query(default="manual"),
               ctx: AuthCtx = Depends(get_ctx)):
    # A specific version_id overrides the version_type default.
    return svc.get_roster_grid(
        ctx.client, ctx.facility_id, period_id,
        version_type=(None if version_id else version_type), version_id=version_id,
    )


# ── facility dictionaries ───────────────────────────────────────────────────
@router.get("/shift-definitions", response_model=list[ShiftDef])
def shift_definitions(ctx: AuthCtx = Depends(get_ctx)):
    return svc.get_shift_defs(ctx.client, ctx.facility_id)


@router.get("/task-definitions", response_model=list[TaskDefOut])
def task_definitions(ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_task_definitions(ctx.client, ctx.facility_id)


# ── manual cell edit ────────────────────────────────────────────────────────
def _cell_ref(body: CellWriteRequest) -> dict:
    return {"roster_version_id": body.roster_version_id, "staff_id": body.staff_id,
            "date": body.date, "shift_type": body.shift_type, "tasks": body.tasks}


def _authorize_draft(ctx: AuthCtx, version_id: str, *, on_date: Date | None = None):
    require_write(Feature.ROSTER_AI_DRAFT)(ctx)
    rows = (ctx.client.table('roster_versions').select('*')
            .eq('facility_id', ctx.facility_id).eq('id', version_id).execute().data or [])
    if not rows:
        raise api_error(404, 'not_found', 'roster version not found')
    version = rows[0]
    if version.get('status') != 'draft':
        raise api_error(409, 'roster_locked', 'Only a draft roster may be edited.')
    if on_date is not None:
        periods = (ctx.client.table('roster_periods').select('*')
                   .eq('facility_id', ctx.facility_id).eq('id', version.get('period_id')).execute().data or [])
        if not periods or not (str(periods[0]['period_start'])[:10] <= on_date.isoformat() <= str(periods[0]['period_end'])[:10]):
            raise api_error(422, 'date_outside_period', 'The date is outside this roster period.')
    return version


def _upsert_cell(body: CellWriteRequest, ctx: AuthCtx, *, action: str):
    _authorize_draft(ctx, body.roster_version_id, on_date=body.date)
    defs = {d.shift_type: d for d in svc.get_shift_defs(ctx.client, ctx.facility_id)}
    sd = defs.get(body.shift_type)
    if not sd:
        raise api_error(422, "unknown_shift_type",
                        f"'{body.shift_type}' is not a shift type for this facility.")
    scheduling_svc.validate_task_labels(
        ctx.client,
        ctx.facility_id,
        roster_version_id=body.roster_version_id,
        staff_id=body.staff_id,
        shift_type=body.shift_type,
        on_date=body.date,
        labels=body.tasks,
    )
    assignment_id = svc.set_cell(
        ctx.client, facility_id=ctx.facility_id,
        roster_version_id=body.roster_version_id, staff_id=body.staff_id,
        date=body.date, shift_type=body.shift_type, shift_def=sd,
        tasks=body.tasks, changed_by=ctx.profile_id,
    )
    scheduling_svc.sync_task_rows_for_assignment(
        ctx.client, ctx.facility_id, assignment_id)
    _audit(ctx, action, "shift_assignments",
           entity_id=assignment_id, after=_cell_ref(body))
    return {"assignment_id": assignment_id}


@router.post("/shifts", status_code=201)
def create_shift(body: CellWriteRequest, ctx: AuthCtx = Depends(get_ctx)):
    return _upsert_cell(body, ctx, action="create")


@router.patch("/shifts")
def edit_shift(body: CellWriteRequest, ctx: AuthCtx = Depends(get_ctx)):
    return _upsert_cell(body, ctx, action="update")


@router.delete("/shifts", status_code=204)
def delete_shift(roster_version_id: str = Query(...), staff_id: str = Query(...),
                 date: Date = Query(...), ctx: AuthCtx = Depends(get_ctx)):
    _authorize_draft(ctx, roster_version_id, on_date=date)
    svc.clear_cell(ctx.client, facility_id=ctx.facility_id,
                   roster_version_id=roster_version_id, staff_id=staff_id,
                   date=date, changed_by=ctx.profile_id)
    # The row is gone by now, so the cell is what identifies it.
    _audit(ctx, "delete", "shift_assignments",
           before={"roster_version_id": roster_version_id, "staff_id": staff_id,
                   "date": date})
    return Response(status_code=204)


# ── publish workflow ────────────────────────────────────────────────────────
@router.post("/rosters/{version_id}/save-draft")
def save_draft(version_id: str, ctx: AuthCtx = Depends(get_ctx)):
    _authorize_draft(ctx, version_id)
    svc.save_draft(ctx.client, facility_id=ctx.facility_id,
                   roster_version_id=version_id, created_by=ctx.profile_id)
    return {"ok": True}


@router.post("/rosters/{version_id}/publish", response_model=PublishRosterOut)
def publish(
    version_id: str,
    body: PublishRosterRequest,
    ctx: AuthCtx = Depends(require_decide(Feature.ROSTER_PUBLISH)),
):
    """Final, server-authoritative roster publication.

    The request contains only an OWNER's individual acknowledgement IDs and the
    digest of the snapshot they reviewed. The server always recomputes the
    deterministic check; hard, unknown, stale and incomplete soft states are
    refused before the atomic publication RPC is called.
    """
    if not (
        ctx.client.table("roster_versions").select("id")
        .eq("facility_id", ctx.facility_id)
        .eq("id", version_id)
        .execute().data
    ):
        raise api_error(404, "not_found", "roster version not found")
    service_client = get_service_client()
    try:
        validation = validation_svc.validate_roster(
            service_client,
            ctx.facility_id,
            version_id,
            validated_by=ctx.profile_id,
            persist=True,
        )
    except ValueError as exc:
        raise api_error(404, "not_found", str(exc)) from exc
    try:
        _, omitted = publication_svc.require_publishable_validation(
            validation,
            body.soft_omission_ids,
            expected_input_digest=body.validation_input_digest,
        )
    except publication_svc.PublishGateError as exc:
        raise api_error(
            409, exc.code, str(exc),
        ) from exc
    # A solver score may be low solely because it includes agency/OT/fairness
    # soft penalties. The current deterministic validation above decides every
    # hard rule; retain a non-zero solver hard count as a separate hard quality
    # refusal, but never convert a soft quality trade-off into an unacknowledged
    # hard violation.
    score = opt.get_option_scores(ctx.client, version_id)
    if score is not None:
        score_hard_count = score.get("hard_violation_count")
        if not isinstance(score_hard_count, int) or isinstance(score_hard_count, bool):
            raise api_error(
                409, "option_score_state_unknown",
                "Generated option score evidence is incomplete; regenerate or review the roster.",
            )
        if score_hard_count != 0:
            raise api_error(
                409, "not_publishable",
                "Generated option has unresolved hard solver violations.",
            )
    try:
        persisted_omission_row_ids = (
            publication_svc.resolve_persisted_soft_omission_row_ids(
                service_client,
                facility_id=ctx.facility_id,
                roster_version_id=version_id,
                validation_run_id=validation["validation_run_id"],
                approved_soft_omission_ids=[row["omission_id"] for row in omitted],
            )
        )
    except publication_svc.PublishGateError as exc:
        raise api_error(409, exc.code, str(exc)) from exc
    svc.publish_version(
        service_client,
        facility_id=ctx.facility_id,
        roster_version_id=version_id,
        created_by=ctx.profile_id,
        validation_run_id=validation["validation_run_id"],
        input_digest=validation["input_digest"],
        omitted_soft_violation_row_ids=persisted_omission_row_ids,
    )
    # Event/audit evidence is inserted by the RPC in this same transaction as
    # the operative status change. Do not add a best-effort post-RPC duplicate:
    # it would reintroduce an evidence gap if that write failed.
    # Only now that the version is operative (spec SA.4b, "push triggers: roster
    # changes"). Notifying before the publish could tell a ward to work a roster
    # that a failed publish left unpublished. Uses the service client because the
    # rows are written for other people than the caller, which RLS forbids the
    # caller's own token.
    #
    # Swallowed, because by this line the publish has committed: raising would
    # answer 500 to a scheduler whose roster *is* published, and they would
    # publish again to fix an error that was never about the roster.
    try:
        svc.notify_published(service_client, ctx.facility_id, version_id)
    except Exception:  # noqa: BLE001 - see above
        pass
    return {
        "roster_version_id": version_id,
        "status": "published",
        "validation_run_id": validation.get("validation_run_id"),
        "input_digest": validation.get("input_digest"),
        "omitted_soft_violation_ids": [row["omission_id"] for row in omitted],
    }
