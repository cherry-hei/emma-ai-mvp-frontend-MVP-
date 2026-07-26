"""Roster read + manual edit + publish. RLS-scoped by the caller's token via get_ctx."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.constants import PUBLISH_THRESHOLD
from emma_core.models import (
    CellWriteRequest, PeriodCreateRequest, PeriodOut, RosterGrid, ShiftDef,
    TaskDefOut, VersionOut,
)
from emma_core.services import optimize as opt
from emma_core.services import roster as svc

router = APIRouter(tags=["roster"])


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
def _upsert_cell(body: CellWriteRequest, ctx: AuthCtx):
    defs = {d.shift_type: d for d in svc.get_shift_defs(ctx.client, ctx.facility_id)}
    sd = defs.get(body.shift_type)
    if not sd:
        raise api_error(422, "unknown_shift_type",
                        f"'{body.shift_type}' is not a shift type for this facility.")
    assignment_id = svc.set_cell(
        ctx.client, facility_id=ctx.facility_id,
        roster_version_id=body.roster_version_id, staff_id=body.staff_id,
        date=body.date, shift_type=body.shift_type, shift_def=sd,
        tasks=body.tasks, changed_by=ctx.profile_id,
    )
    return {"assignment_id": assignment_id}


@router.post("/shifts", status_code=201)
def create_shift(body: CellWriteRequest, ctx: AuthCtx = Depends(get_ctx)):
    return _upsert_cell(body, ctx)


@router.patch("/shifts")
def edit_shift(body: CellWriteRequest, ctx: AuthCtx = Depends(get_ctx)):
    return _upsert_cell(body, ctx)


@router.delete("/shifts", status_code=204)
def delete_shift(roster_version_id: str = Query(...), staff_id: str = Query(...),
                 date: Date = Query(...), ctx: AuthCtx = Depends(get_ctx)):
    svc.clear_cell(ctx.client, facility_id=ctx.facility_id,
                   roster_version_id=roster_version_id, staff_id=staff_id,
                   date=date, changed_by=ctx.profile_id)
    return Response(status_code=204)


# ── publish workflow ────────────────────────────────────────────────────────
@router.post("/rosters/{version_id}/save-draft")
def save_draft(version_id: str, ctx: AuthCtx = Depends(get_ctx)):
    svc.save_draft(ctx.client, facility_id=ctx.facility_id,
                   roster_version_id=version_id, created_by=ctx.profile_id)
    return {"ok": True}


@router.post("/rosters/{version_id}/publish")
def publish(version_id: str, ctx: AuthCtx = Depends(get_ctx)):
    # A solver option publishes only if it clears the threshold with zero hard
    # violations; a manual version (no score row) publishes freely.
    score = opt.get_option_scores(ctx.client, version_id)
    if score is not None:
        if score["constraint_score"] < PUBLISH_THRESHOLD or score["hard_violation_count"] > 0:
            raise api_error(
                409, "not_publishable",
                f"Option scores {score['constraint_score']} with "
                f"{score['hard_violation_count']} hard violation(s); "
                f"minimum publishable score is {PUBLISH_THRESHOLD} with zero hard violations.",
            )
    svc.publish_version(ctx.client, facility_id=ctx.facility_id,
                        roster_version_id=version_id, created_by=ctx.profile_id)
    return {"roster_version_id": version_id, "status": "published"}
