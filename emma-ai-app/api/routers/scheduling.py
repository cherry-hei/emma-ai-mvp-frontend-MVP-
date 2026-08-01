"""Phase 4 task assignments and facility-event overlays."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import (
    EscortLocationAssign,
    EscortLocationOut,
    EscortLocationRequest,
    FacilityEventCreate,
    FacilityEventOut,
    FacilityEventPatch,
    TaskAssignmentCreate,
    TaskAssignmentOut,
    TaskAssignmentPatch,
)
from emma_core.services import escort as escort_svc
from emma_core.services import scheduling as svc

router = APIRouter(tags=["task scheduling"])

WRITE_ROLES = {"superintendent", "admin", "scheduler"}


def _require_write_role(ctx: AuthCtx) -> None:
    if str(ctx.profile.role) not in WRITE_ROLES:
        raise api_error(
            403,
            "forbidden",
            "Only a superintendent, admin or scheduler may change scheduling data.",
        )


@router.get("/task-assignments", response_model=list[TaskAssignmentOut])
def task_assignments(
    roster_version_id: str | None = Query(default=None),
    shift_assignment_id: str | None = Query(default=None),
    ctx: AuthCtx = Depends(get_ctx),
):
    return svc.list_task_assignments(
        ctx.client,
        ctx.facility_id,
        roster_version_id=roster_version_id,
        shift_assignment_id=shift_assignment_id,
    )


@router.post("/task-assignments", response_model=TaskAssignmentOut, status_code=201)
def create_task_assignment(
    body: TaskAssignmentCreate,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    return svc.create_task_assignment(
        ctx.client,
        ctx.facility_id,
        body.model_dump(mode="json"),
    )


@router.patch("/task-assignments/{task_assignment_id}", response_model=TaskAssignmentOut)
def update_task_assignment(
    task_assignment_id: str,
    body: TaskAssignmentPatch,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    return svc.update_task_assignment(
        ctx.client,
        ctx.facility_id,
        task_assignment_id,
        body.model_dump(mode="json", exclude_unset=True),
    )


@router.delete("/task-assignments/{task_assignment_id}", status_code=204)
def delete_task_assignment(
    task_assignment_id: str,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    svc.delete_task_assignment(ctx.client, ctx.facility_id, task_assignment_id)
    return Response(status_code=204)


# ── medical-escort destinations (4.1) ────────────────────────────────────────
@router.get("/escort-locations", response_model=list[EscortLocationOut])
def escort_locations(
    include_inactive: bool = Query(default=False),
    ctx: AuthCtx = Depends(get_ctx),
):
    """The destination dictionary. Readable by anyone signed in - the roster grid
    and the staff app both render the code."""
    return escort_svc.list_locations(
        ctx.client, ctx.facility_id, include_inactive=include_inactive,
    )


@router.post("/escort-locations", response_model=EscortLocationOut, status_code=201)
def upsert_escort_location(
    body: EscortLocationRequest,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    return escort_svc.upsert_location(
        ctx.client, ctx.facility_id, code=body.code, name_en=body.name_en,
        name_zh=body.name_zh, aliases=body.aliases,
    )


@router.put("/task-assignments/{task_assignment_id}/escort-location")
def set_escort_location(
    task_assignment_id: str,
    body: EscortLocationAssign,
    ctx: AuthCtx = Depends(get_ctx),
):
    """Attach or clear this assignment's destination.

    A code that is not in the dictionary is accepted and echoed back with
    `escort_location_unknown: true`. The roster cell is the record of what the
    home did; a missing reference row is a gap in our data, not in theirs.
    """
    _require_write_role(ctx)
    try:
        return escort_svc.set_escort_location(
            ctx.client, ctx.facility_id, task_assignment_id,
            location=body.escort_location,
        )
    except ValueError as exc:
        raise api_error(404 if "not found" in str(exc) else 400,
                        "invalid_escort_location", str(exc)) from exc


@router.get("/escorts")
def escorts_on_date(
    on: Date = Query(description="the date to list escorts for"),
    ctx: AuthCtx = Depends(get_ctx),
):
    """Who is off the floor escorting a resident on this date."""
    return escort_svc.escorts_on_date(ctx.client, ctx.facility_id, on)


@router.get("/facility-events", response_model=list[FacilityEventOut])
def facility_events(
    date_from: Date | None = Query(default=None),
    date_to: Date | None = Query(default=None),
    ctx: AuthCtx = Depends(get_ctx),
):
    return svc.list_facility_events(
        ctx.client,
        ctx.facility_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/facility-events", response_model=FacilityEventOut, status_code=201)
def create_facility_event(
    body: FacilityEventCreate,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    return svc.create_facility_event(
        ctx.client,
        ctx.facility_id,
        body.model_dump(mode="json"),
    )


@router.patch("/facility-events/{event_id}", response_model=FacilityEventOut)
def update_facility_event(
    event_id: str,
    body: FacilityEventPatch,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    return svc.update_facility_event(
        ctx.client,
        ctx.facility_id,
        event_id,
        body.model_dump(mode="json", exclude_unset=True),
    )


@router.delete("/facility-events/{event_id}", status_code=204)
def delete_facility_event(
    event_id: str,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    svc.delete_facility_event(ctx.client, ctx.facility_id, event_id)
    return Response(status_code=204)
