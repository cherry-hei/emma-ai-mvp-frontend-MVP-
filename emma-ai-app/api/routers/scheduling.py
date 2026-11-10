"""Phase 4 task assignments and facility-event overlays."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, get_ctx, require_staff_in_roster_scope
from emma_core.models import (
    EscortLocationAssign,
    EscortLocationOut,
    EscortLocationRequest,
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
from emma_core.services import escort as escort_svc
from emma_core.services import scheduling as svc
from emma_core.permissions import Feature

router = APIRouter(tags=["task scheduling"])



def _require_write_role(ctx: AuthCtx, feature: Feature = Feature.ROSTER_AI_DRAFT) -> None:
    if not ctx.can_write(feature):
        raise api_error(
            403,
            "forbidden",
            "This workflow appointment may not change scheduling data.",
        )


def _assignment_scope(ctx: AuthCtx, assignment_id: str, *, write: bool) -> None:
    """Resolve through the bound home before any task read/write."""
    rows = (ctx.client.table("shift_assignments").select("staff_id,shift_id")
            .eq("facility_id", ctx.facility_id).eq("id", assignment_id).execute().data)
    if not rows:
        raise api_error(404, "not_found", "shift assignment not found")
    require_staff_in_roster_scope(ctx, rows[0]["staff_id"])
    if write:
        shifts = (ctx.client.table("shifts").select("roster_version_id")
                  .eq("facility_id", ctx.facility_id)
                  .eq("id", rows[0]["shift_id"]).execute().data)
        if not shifts:
            raise api_error(404, "not_found", "shift not found")
        from api.routers.roster import _require_editable_version
        _require_editable_version(ctx, shifts[0]["roster_version_id"])


def _task_editor(ctx: AuthCtx, assignment_id: str) -> None:
    if not ctx.allows("roster_edit"):
        raise api_error(403, "forbidden", "This appointment may not edit roster tasks.")
    _assignment_scope(ctx, assignment_id, write=True)


@router.get("/task-assignments", response_model=list[TaskAssignmentOut])
def task_assignments(
    roster_version_id: str | None = Query(default=None),
    shift_assignment_id: str | None = Query(default=None),
    ctx: AuthCtx = Depends(get_ctx),
):
    if ctx.profile.care_workflow.roster_scope != "facility":
        if not ctx.allows("roster_edit") or not shift_assignment_id:
            raise api_error(403, "forbidden", "A scoped shift assignment is required.")
        _assignment_scope(ctx, shift_assignment_id, write=False)
    elif not ctx.can_read(Feature.TASK_CODES):
        raise api_error(403, "forbidden", "This appointment may not read task assignments.")
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
    _task_editor(ctx, body.shift_assignment_id)
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
    rows = (ctx.client.table("task_assignments").select("shift_assignment_id")
            .eq("facility_id", ctx.facility_id).eq("id", task_assignment_id).execute().data)
    if not rows:
        raise api_error(404, "not_found", "task assignment not found")
    _task_editor(ctx, rows[0]["shift_assignment_id"])
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
    _require_write_role(ctx, Feature.FACILITY_SETTINGS)
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


@router.get("/facility-events/types")
def facility_event_types(ctx: AuthCtx = Depends(get_ctx)):
    """The event types the create-event modal may offer (spec 4.2).

    Declared before `/facility-events/{event_id}` so `types` is never read as an
    event id. Authenticated but not role-gated: it is a dictionary, and anyone
    who can open the roster can see the picker.
    """
    return {"event_types": svc.event_type_catalogue(ctx.client, ctx.facility_id)}


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
    _require_write_role(ctx, Feature.STAFF_PROFILE_WRITE)
    return svc.create_staff_qualification(
        ctx.client, ctx.facility_id, body.model_dump(mode="json"))


@router.patch("/staff-qualifications/{qualification_id}",
              response_model=StaffQualificationOut)
def update_staff_qualification(
    qualification_id: str,
    body: StaffQualificationPatch,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx, Feature.STAFF_PROFILE_WRITE)
    return svc.update_staff_qualification(
        ctx.client, ctx.facility_id, qualification_id,
        body.model_dump(mode="json", exclude_unset=True))


@router.delete("/staff-qualifications/{qualification_id}", status_code=204)
def delete_staff_qualification(
    qualification_id: str,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx, Feature.STAFF_PROFILE_WRITE)
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
    _require_write_role(ctx, Feature.ROSTER_RULE_ENGINE)
    return svc.create_floor_rule(
        ctx.client, ctx.facility_id, body.model_dump(mode="json"))


@router.patch("/floor-rules/{rule_id}", response_model=FloorRuleOut)
def update_floor_rule(
    rule_id: str,
    body: FloorRulePatch,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx, Feature.ROSTER_RULE_ENGINE)
    return svc.update_floor_rule(
        ctx.client, ctx.facility_id, rule_id,
        body.model_dump(mode="json", exclude_unset=True))


@router.delete("/floor-rules/{rule_id}", status_code=204)
def delete_floor_rule(
    rule_id: str,
    ctx: AuthCtx = Depends(get_ctx),
):
    _require_write_role(ctx, Feature.ROSTER_RULE_ENGINE)
    svc.delete_floor_rule(ctx.client, ctx.facility_id, rule_id)
    return Response(status_code=204)
