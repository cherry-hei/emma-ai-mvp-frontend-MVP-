"""Phase 4 task assignments and facility-event overlays."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import (
    FacilityEventCreate,
    FacilityEventOut,
    FacilityEventPatch,
    FloorRuleCreate,
    FloorRuleOut,
    FloorRulePatch,
    StaffQualificationCreate,
    StaffQualificationOut,
    StaffQualificationPatch,
    TaskAssignmentCreate,
    TaskAssignmentOut,
    TaskAssignmentPatch,
)
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


# ── 4.1 staff qualifications ────────────────────────────────────────────────
@router.get("/staff-qualifications", response_model=list[StaffQualificationOut])
def staff_qualifications(
    staff_id: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    ctx: AuthCtx = Depends(get_ctx),
):
    return svc.list_staff_qualifications(
        ctx.client, ctx.facility_id, staff_id=staff_id, active_only=active_only)


@router.post("/staff-qualifications", response_model=StaffQualificationOut,
             status_code=201)
def create_staff_qualification(
    body: StaffQualificationCreate,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    return svc.create_staff_qualification(
        ctx.client, ctx.facility_id, body.model_dump(mode="json"))


@router.patch("/staff-qualifications/{qualification_id}",
              response_model=StaffQualificationOut)
def update_staff_qualification(
    qualification_id: str,
    body: StaffQualificationPatch,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    return svc.update_staff_qualification(
        ctx.client, ctx.facility_id, qualification_id,
        body.model_dump(mode="json", exclude_unset=True))


@router.delete("/staff-qualifications/{qualification_id}", status_code=204)
def delete_staff_qualification(
    qualification_id: str,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    svc.delete_staff_qualification(ctx.client, ctx.facility_id, qualification_id)
    return Response(status_code=204)


# ── 4.3 floor / unit minimum staffing ───────────────────────────────────────
@router.get("/floor-rules", response_model=list[FloorRuleOut])
def floor_rules(
    unit_id: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    ctx: AuthCtx = Depends(get_ctx),
):
    return svc.list_floor_rules(
        ctx.client, ctx.facility_id, unit_id=unit_id, active_only=active_only)


@router.post("/floor-rules", response_model=FloorRuleOut, status_code=201)
def create_floor_rule(
    body: FloorRuleCreate,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    return svc.create_floor_rule(
        ctx.client, ctx.facility_id, body.model_dump(mode="json"))


@router.patch("/floor-rules/{rule_id}", response_model=FloorRuleOut)
def update_floor_rule(
    rule_id: str,
    body: FloorRulePatch,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    return svc.update_floor_rule(
        ctx.client, ctx.facility_id, rule_id,
        body.model_dump(mode="json", exclude_unset=True))


@router.delete("/floor-rules/{rule_id}", status_code=204)
def delete_floor_rule(
    rule_id: str,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx)
    svc.delete_floor_rule(ctx.client, ctx.facility_id, rule_id)
    return Response(status_code=204)
