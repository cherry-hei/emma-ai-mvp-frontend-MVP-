"""Roster read + manual edit + publish. RLS-scoped by the caller's token via get_ctx."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.constants import PUBLISH_THRESHOLD
from emma_core.db import get_service_client
from emma_core.models import (
    CellWriteRequest, PeriodCreateRequest, PeriodOut, RosterGrid, ShiftDef,
    TaskDefOut, VersionOut,
)
from emma_core.services import audit
from emma_core.services import optimize as opt
from emma_core.services import roster as svc
from emma_core.services import scheduling as scheduling_svc
from emma_core.services import validation as validation_svc

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
def create_period(body: PeriodCreateRequest, ctx: AuthCtx = Depends(get_ctx)):
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


def _upsert_cell(body: CellWriteRequest, ctx: AuthCtx, *, action: str):
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
    svc.save_draft(ctx.client, facility_id=ctx.facility_id,
                   roster_version_id=version_id, created_by=ctx.profile_id)
    return {"ok": True}


@router.post("/rosters/{version_id}/publish")
def publish(version_id: str, ctx: AuthCtx = Depends(get_ctx)):
    _require_write_role(ctx)
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
    if not validation["passes"]:
        raise api_error(
            409, "not_publishable",
            (
                f"Roster has {validation['hard_violation_count']} hard "
                "compliance violation(s). Validate the roster for details."
            ),
        )
    # A generated option retains its Phase 2 quality threshold, while the fresh
    # deterministic run above is authoritative for every hard constraint.
    score = opt.get_option_scores(ctx.client, version_id)
    if score is not None:
        if score["constraint_score"] < PUBLISH_THRESHOLD:
            raise api_error(
                409, "not_publishable",
                f"Option scores {score['constraint_score']}; minimum publishable "
                f"score is {PUBLISH_THRESHOLD}.",
            )
    svc.publish_version(service_client, facility_id=ctx.facility_id,
                        roster_version_id=version_id, created_by=ctx.profile_id)
    # After the write, so we never log a publish that rolled back.
    _audit(ctx, "publish", "roster_versions", entity_id=version_id,
           after={"status": "published",
                  "hard_violation_count": validation["hard_violation_count"],
                  "constraint_score": score["constraint_score"] if score else None})
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
    return {"roster_version_id": version_id, "status": "published"}
