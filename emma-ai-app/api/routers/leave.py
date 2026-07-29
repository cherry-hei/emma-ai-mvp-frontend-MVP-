"""/leave-requests — the Approval Centre (spec 4.2)."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.db import get_service_client
from emma_core.models import LeaveDecisionRequest, LeaveRequestCreate
from emma_core.services import leave as svc
from emma_core.services.me import resolve_staff_id

router = APIRouter(tags=["leave"])
DECISION_ROLES = {"superintendent", "admin", "scheduler", "hr"}


@router.get("/leave-requests")
def list_requests(group: str | None = Query(default=None, pattern="^(pending|approved)$"),
                  category: str | None = Query(default=None, pattern="^(al|duty|sick)$"),
                  search: str | None = Query(default=None),
                  unit_id: str | None = Query(default=None),
                  date_from: Date | None = Query(default=None),
                  date_to: Date | None = Query(default=None),
                  staff_id: str | None = Query(default=None),
                  ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_requests(ctx.client, ctx.facility_id, group=group, category=category,
                             search=search, unit_id=unit_id, date_from=date_from,
                             date_to=date_to, staff_id=staff_id)


@router.get("/leave-requests/stats")
def request_stats(on: Date | None = Query(default=None, alias="date"),
                  ctx: AuthCtx = Depends(get_ctx)):
    return svc.stats(ctx.client, ctx.facility_id, on)


@router.post("/leave-requests", status_code=201)
def create_request(body: LeaveRequestCreate, ctx: AuthCtx = Depends(get_ctx)):
    role = str(ctx.profile.role)
    if role == "staff":
        own_staff_id = resolve_staff_id(ctx.profile)
        if body.staff_id and body.staff_id != own_staff_id:
            raise api_error(
                403,
                "forbidden",
                "staff accounts may only create their own requests",
            )
        staff_id = own_staff_id
    else:
        staff_id = body.staff_id or resolve_staff_id(ctx.profile)
    if not (
        ctx.client.table("staff").select("id")
        .eq("facility_id", ctx.facility_id)
        .eq("id", staff_id)
        .execute().data
    ):
        raise api_error(404, "not_found", "staff member not found")
    return svc.create_request(
        get_service_client(), ctx.facility_id,
        staff_id=staff_id, leave_type=body.leave_type,
        date_start=body.date_start, date_end=body.date_end, reason=body.reason,
        remark=body.remark, requested_shift_type=body.requested_shift_type,
        document_url=body.document_url,
    )


@router.patch("/leave-requests/{request_id}")
def decide_request(request_id: str, body: LeaveDecisionRequest,
                   ctx: AuthCtx = Depends(get_ctx)):
    if str(ctx.profile.role) not in DECISION_ROLES:
        raise api_error(403, "forbidden", "only a manager can decide leave requests")
    # Resolve the request through the caller's RLS boundary first. Approval
    # then uses the service role because status transitions and balance usage
    # are authoritative workflow writes, not client-editable table fields.
    if not (
        ctx.client.table("leave_requests").select("id")
        .eq("facility_id", ctx.facility_id)
        .eq("id", request_id)
        .execute().data
    ):
        raise api_error(404, "not_found", "leave request not found")
    return svc.decide(get_service_client(), ctx.facility_id, request_id,
                      decision=body.decision, profile_id=ctx.profile_id,
                      note=body.note, ballot_approved=body.ballot_approved)
