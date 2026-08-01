"""/me/* - the staff mobile app (spec 4.1).

Every route resolves the staff record from the caller's own profile, so there is
no path where a staff token reads another person's roster, tasks or attendance.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import (
    ClockRequest,
    PushSubscriptionRequest,
    TaskExceptionRequest,
    TaskStatusRequest,
)
from emma_core.services import attendance as att
from emma_core.services import me as svc
from emma_core.services import notifications as notify
from emma_core.services import tasks as task_svc

router = APIRouter(tags=["staff-app"])


def _staff_id(ctx: AuthCtx) -> str:
    try:
        return svc.resolve_staff_id(ctx.profile)
    except ValueError as exc:
        raise api_error(409, "no_staff_record", str(exc)) from exc


@router.get("/me/summary")
def my_summary(ctx: AuthCtx = Depends(get_ctx)):
    return svc.summary(ctx.client, ctx.facility_id, _staff_id(ctx))


@router.get("/me/roster")
def my_roster(days: int = Query(default=7, ge=1, le=42),
              start: Date | None = Query(default=None),
              ctx: AuthCtx = Depends(get_ctx)):
    return svc.my_roster(ctx.client, ctx.facility_id, _staff_id(ctx),
                         days=days, start=start)


@router.get("/me/profile")
def my_profile(ctx: AuthCtx = Depends(get_ctx)):
    return svc.profile(ctx.client, ctx.facility_id, _staff_id(ctx))


@router.get("/me/tasks")
def my_tasks(on: Date | None = Query(default=None, alias="date"),
             ctx: AuthCtx = Depends(get_ctx)):
    return task_svc.for_staff_date(ctx.client, ctx.facility_id, _staff_id(ctx),
                                   on or Date.today())


@router.patch("/me/tasks/{task_assignment_id}")
def set_task_status(task_assignment_id: str, body: TaskStatusRequest,
                    ctx: AuthCtx = Depends(get_ctx)):
    return task_svc.set_status(ctx.client, ctx.facility_id, task_assignment_id,
                               status=body.status, staff_id=_staff_id(ctx))


@router.post("/me/tasks/{task_assignment_id}/exception", status_code=201)
def report_task_exception(task_assignment_id: str, body: TaskExceptionRequest,
                          ctx: AuthCtx = Depends(get_ctx)):
    """"I could not do this, and here is why" (spec SA.3).

    Separate from the PATCH above because it is a different act: a status change
    says what the task is now, an exception says what happened. Only the second
    one is evidence.
    """
    return task_svc.report_exception(
        ctx.client, ctx.facility_id, task_assignment_id,
        reason_code=body.reason_code, note=body.note, staff_id=_staff_id(ctx),
    )


@router.post("/me/push-subscriptions", status_code=201)
def register_push_device(body: PushSubscriptionRequest,
                         ctx: AuthCtx = Depends(get_ctx)):
    """Register this device for push (spec SA.4). Re-registering the same token
    refreshes the row rather than adding a second one, so a reinstalled app does
    not double every notification."""
    return notify.register_device(
        ctx.client, ctx.facility_id, token=body.token, platform=body.platform,
        user_agent=body.user_agent, staff_id=_staff_id(ctx),
        profile_id=ctx.profile_id,
    )


@router.get("/me/attendance")
def my_attendance(ctx: AuthCtx = Depends(get_ctx)):
    staff_id = _staff_id(ctx)
    return {
        "today": att.today_status(ctx.client, ctx.facility_id, staff_id),
        "month": att.month_summary(ctx.client, ctx.facility_id, staff_id),
        "recent": att.recent(ctx.client, ctx.facility_id, staff_id),
    }


@router.post("/me/attendance/clock")
def clock(body: ClockRequest, ctx: AuthCtx = Depends(get_ctx)):
    return att.clock(ctx.client, ctx.facility_id, _staff_id(ctx),
                     event_type=body.event_type, shift_id=body.shift_id, note=body.note)


@router.get("/me/leave-requests")
def my_leave(ctx: AuthCtx = Depends(get_ctx)):
    return svc.my_leave(ctx.client, ctx.facility_id, _staff_id(ctx))


@router.get("/me/colleagues")
def colleagues(on: Date | None = Query(default=None, alias="date"),
               ctx: AuthCtx = Depends(get_ctx)):
    return svc.colleagues_on(ctx.client, ctx.facility_id, on or Date.today())


@router.get("/me/notifications")
def my_notifications(unread_only: bool = Query(default=False),
                     ctx: AuthCtx = Depends(get_ctx)):
    return notify.list_for(ctx.client, ctx.facility_id, staff_id=_staff_id(ctx),
                           unread_only=unread_only)


@router.patch("/me/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, ctx: AuthCtx = Depends(get_ctx)):
    row = notify.mark_read(ctx.client, ctx.facility_id, notification_id)
    if not row:
        raise api_error(404, "not_found", "notification not found")
    return row
