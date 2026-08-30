"""/me/* - the staff mobile app (spec 4.1).

Every route resolves the staff record from the caller's own profile, so there is
no path where a staff token reads another person's roster, tasks or attendance.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import (
    CertificateOut,
    CertificateUpsert,
    ClockRequest,
    PushSubscriptionRequest,
    TaskExceptionRequest,
    TaskStatusRequest,
)
from emma_core.services import attendance as att
from emma_core.services import certificates as cert_svc
from emma_core.services import me as svc
from emma_core.services import notifications as notify
from emma_core.services import tasks as task_svc

router = APIRouter(tags=["staff-app"])


def _staff_id(ctx: AuthCtx) -> str:
    try:
        return svc.resolve_staff_id(ctx.profile)
    except ValueError as exc:
        raise api_error(409, "no_staff_record", str(exc)) from exc


def _readable(ctx: AuthCtx, call):
    """Run a staff-app read, and answer a missing staff row with a reason.

    `_staff_row` raises ValueError when the account's `staff_id` resolves to no
    visible row - the record was deleted, the profile points at a staff_id from
    another facility, or RLS hides it from this token. Nothing caught it, so all
    three arrived as a bare 500.

    That is what made Cherry's production report undiagnosable: "/me/profile and
    /me/summary return 500 for staff_a and staff_hw_a" is the same symptom for
    three unrelated causes, and a 500 carries no information about which. 404
    with the staff_id in the message says what to go and look at.
    """
    try:
        return call()
    except ValueError as exc:
        raise api_error(
            404, "staff_record_unavailable",
            f"{exc}. The account is linked to staff_id "
            f"{svc.resolve_staff_id(ctx.profile)!r}, and no staff row with that "
            f"id is readable in this facility.",
        ) from exc


@router.get("/me/summary")
def my_summary(ctx: AuthCtx = Depends(get_ctx)):
    staff_id = _staff_id(ctx)
    return _readable(ctx, lambda: svc.summary(ctx.client, ctx.facility_id, staff_id))


@router.get("/me/roster")
def my_roster(days: int = Query(default=7, ge=1, le=42),
              start: Date | None = Query(default=None),
              end: Date | None = Query(
                  default=None,
                  description="Alternative to `days`. Wins where both are given; "
                              "the window is capped at 42 days."),
              ctx: AuthCtx = Depends(get_ctx)):
    staff_id = _staff_id(ctx)
    return _readable(ctx, lambda: svc.my_roster(
        ctx.client, ctx.facility_id, staff_id, days=days, start=start, end=end))


@router.get("/me/profile")
def my_profile(ctx: AuthCtx = Depends(get_ctx)):
    staff_id = _staff_id(ctx)
    return _readable(ctx, lambda: svc.profile(ctx.client, ctx.facility_id, staff_id))


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


# ── the staff member's own certificate vault (spec SA.7) ────────────────────
# The vault endpoints on /staff/{id}/certificates need a facility-wide grant, so
# the one person who cannot use them is the person whose certificate it is:
# FRONTLINE holds S on staff.certificates - self only. The ticket asks for staff
# to upload their own, so these are the same three operations resolved through
# the caller's own staff record instead of a path parameter. No role check: the
# staff_id is never taken from the request, so there is no path here that reads
# or writes anyone else's row.

@router.get("/me/certificates", response_model=list[CertificateOut])
def my_certificates(ctx: AuthCtx = Depends(get_ctx)):
    return cert_svc.list_for_staff(ctx.client, ctx.facility_id, _staff_id(ctx))


@router.post("/me/certificates", response_model=CertificateOut, status_code=201)
def upload_my_certificate(body: CertificateUpsert, ctx: AuthCtx = Depends(get_ctx)):
    """File or renew one of my own certificates (spec SA.7).

    Filing notifies whoever may act on certificates - HR first, which is the
    ticket's "HR receives a notification that a colleague's cert was updated".
    """
    try:
        return cert_svc.upsert(
            ctx.client, ctx.facility_id, _staff_id(ctx),
            cert_type=body.cert_type, expiry_date=body.expiry_date,
            file_url=body.file_url, certificate_id=body.certificate_id,
            cert_number=body.cert_number, issued_date=body.issued_date,
            uploaded_by=ctx.profile_id,
        )
    except ValueError as exc:
        raise api_error(404 if "not found" in str(exc) else 400,
                        "invalid_certificate", str(exc)) from exc


@router.delete("/me/certificates/{certificate_id}", status_code=204)
def delete_my_certificate(certificate_id: str, ctx: AuthCtx = Depends(get_ctx)):
    """Withdraw a certificate I filed.

    Scoped by staff_id rather than by id alone: a uuid from another person's
    vault must read as missing, not delete their record. RLS narrows a staff
    token to its own rows as well, and this does not rely on that - a check that
    only exists in one layer is a check that disappears when that layer moves.
    """
    mine = {c["id"] for c in
            cert_svc.list_for_staff(ctx.client, ctx.facility_id, _staff_id(ctx))}
    if certificate_id not in mine:
        raise api_error(404, "not_found", "certificate not found")
    cert_svc.delete(ctx.client, ctx.facility_id, certificate_id)
    return Response(status_code=204)


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
