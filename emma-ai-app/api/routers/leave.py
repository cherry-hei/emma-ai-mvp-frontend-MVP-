"""/leave-requests - the Approval Centre (spec 4.2 / 1.1).

The Approval Centre is where "recommend is not approve" has teeth. Matrix row
"Approvals: leave": F for OWNER, R for NURSE_MGR and ADMIN_CLERK, hidden from
ALLIED_HEALTH, S for FRONTLINE. So:

* the list is facility-wide for managers and silently narrowed to their own rows
  for a FRONTLINE caller - a 403 would break the Staff App, and returning the
  whole home's leave history to every care worker is the bug that was there;
* the final decision is OWNER-only. `DECISION_ROLES` previously admitted admin,
  scheduler and hr, which is exactly the "final approve must 403 for them" case
  Cherry called out.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import (
    AuthCtx, api_error, get_ctx, require_decide, require_read, require_recommend,
)
from emma_core.db import get_service_client
from emma_core.models import (
    LeaveDecisionRequest, LeaveRequestCreate, RecommendationRequest, RevokeRequest,
    WithdrawRequest,
)
from emma_core.permissions import Feature, can_decide, can_read, is_self_only
from emma_core.services import leave as svc
from emma_core.services import recommendations as rec_svc
from emma_core.services.me import resolve_staff_id

router = APIRouter(tags=["leave"])


@router.get("/leave-requests")
def list_requests(group: str | None = Query(default=None, pattern="^(pending|approved)$"),
                  category: str | None = Query(default=None, pattern="^(al|duty|sick)$"),
                  search: str | None = Query(default=None),
                  unit_id: str | None = Query(default=None),
                  date_from: Date | None = Query(default=None),
                  date_to: Date | None = Query(default=None),
                  staff_id: str | None = Query(default=None),
                  ctx: AuthCtx = Depends(get_ctx)):
    if is_self_only(ctx.profile.role, Feature.APPROVE_LEAVE):
        # Ignore whatever staff_id was asked for - self-only means self.
        staff_id = resolve_staff_id(ctx.profile)
    elif not can_read(ctx.profile.role, Feature.APPROVE_LEAVE):
        raise api_error(403, "forbidden", "Your role may not view leave requests.")
    rows = svc.list_requests(ctx.client, ctx.facility_id, group=group,
                             category=category, search=search, unit_id=unit_id,
                             date_from=date_from, date_to=date_to, staff_id=staff_id)
    # "Approver UI must show pending items together with all recommendations
    # attached" - so they travel with the queue rather than needing a call per row.
    return rec_svc.attach(ctx.client, ctx.facility_id, rows)


@router.get("/leave-requests/stats")
def request_stats(on: Date | None = Query(default=None, alias="date"),
                  ctx: AuthCtx = Depends(require_read(Feature.APPROVE_LEAVE))):
    """Facility-wide counts, so managers only - there is no self-only version of
    an aggregate over other people's leave."""
    return svc.stats(ctx.client, ctx.facility_id, on)


@router.post("/leave-requests", status_code=201)
def create_request(body: LeaveRequestCreate, ctx: AuthCtx = Depends(get_ctx)):
    if is_self_only(ctx.profile.role, Feature.APPROVE_LEAVE):
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
                   ctx: AuthCtx = Depends(require_decide(Feature.APPROVE_LEAVE))):
    """Final approve/reject/review - OWNER only (院長/副院長 at SA, 主任/副主任 at
    NAAC). A nursing officer or clerk reaching this gets 403; their first-pass
    review belongs on the recommendation endpoint, and taking a request back
    belongs on `/withdraw`."""
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


# ── first-pass review (spec 1.1) ─────────────────────────────────────────────
# The pair of endpoints below is the whole point of the R grade. `require_recommend`
# admits OWNER and the R roles; `require_decide` above admits OWNER alone. A nursing
# officer can therefore say "I suggest you approve this, because …" and cannot
# approve it - which is what Cherry asked for in one sentence and what
# DECISION_ROLES = {superintendent, admin, scheduler, hr} used to get wrong.

@router.post("/leave-requests/{request_id}/recommendation", status_code=201)
def recommend_request(request_id: str, body: RecommendationRequest,
                      ctx: AuthCtx = Depends(require_recommend(Feature.APPROVE_LEAVE))):
    """Attach a suggest-approve / suggest-reject with a reason.

    Replaces the caller's own previous recommendation on this request rather than
    adding a second - and the previous one is withdrawn, not deleted."""
    try:
        return rec_svc.add(
            ctx.client, ctx.facility_id, request_id,
            profile_id=ctx.profile_id,
            role=str(ctx.role or ctx.profile.role),
            recommendation=body.recommendation,
            reason=body.reason,
            feature=Feature.APPROVE_LEAVE,
        )
    except rec_svc.OutOfDomainError as exc:
        # 403 rather than 422: the role holds R, the request is well-formed, and
        # the reviewer simply has no standing over this person. A therapist
        # retrying with better wording will not help.
        raise api_error(403, "out_of_domain", str(exc)) from exc
    except ValueError as exc:
        code = "not_found" if "not found" in str(exc) else "invalid_request"
        raise api_error(404 if code == "not_found" else 422, code, str(exc)) from exc


@router.get("/leave-requests/{request_id}/recommendations")
def list_recommendations(request_id: str, include_withdrawn: bool = Query(default=False),
                         ctx: AuthCtx = Depends(require_read(Feature.APPROVE_LEAVE))):
    rows = rec_svc.for_request(ctx.client, ctx.facility_id, request_id,
                               include_withdrawn=include_withdrawn)
    return {"recommendations": rows, "summary": rec_svc.summarise(rows)}


@router.delete("/leave-requests/{request_id}/recommendation", status_code=200)
def withdraw_recommendation(request_id: str,
                            ctx: AuthCtx = Depends(require_recommend(Feature.APPROVE_LEAVE))):
    """Withdraw your own recommendation. You cannot withdraw someone else's."""
    n = rec_svc.withdraw_own(ctx.client, ctx.facility_id, request_id,
                             profile_id=ctx.profile_id)
    return {"withdrawn": n}


@router.post("/leave-requests/{request_id}/withdraw")
def withdraw_request(request_id: str, body: WithdrawRequest | None = None,
                     ctx: AuthCtx = Depends(get_ctx)):
    """The requester takes back a request nobody has decided yet.

    Authorised by *identity* for a frontline caller and by role for an approver,
    the same split as `/swap-requests/{id}/cancel`: a care worker may withdraw
    their own request and no one else's, an OWNER may cancel any of them. The
    outcome is `cancelled`, not `rejected` - a withdrawn request must not be
    counted as a refusal in the stats or read as one in the history.
    """
    # Resolved through the caller's own client first, so RLS decides what they
    # can see before the service role is used to write the transition.
    if not (
        ctx.client.table("leave_requests").select("id")
        .eq("facility_id", ctx.facility_id)
        .eq("id", request_id)
        .execute().data
    ):
        raise api_error(404, "not_found", "leave request not found")
    reason = body.reason if body else None
    own_staff_id = None
    if not can_decide(ctx.profile.role, Feature.APPROVE_LEAVE):
        # Anyone who is not the final approver may only act on their own request,
        # whatever their role - resolved from the caller's profile, never the body.
        own_staff_id = resolve_staff_id(ctx.profile)
    try:
        return svc.withdraw(get_service_client(), ctx.facility_id, request_id,
                            profile_id=ctx.profile_id, staff_id=own_staff_id,
                            reason=reason)
    except PermissionError as exc:
        raise api_error(403, "forbidden", str(exc)) from exc
    except ValueError as exc:
        code = "not_found" if "not found" in str(exc) else "not_withdrawable"
        raise api_error(404 if code == "not_found" else 422, code, str(exc)) from exc


@router.post("/leave-requests/{request_id}/revoke")
def revoke_request(request_id: str, body: RevokeRequest,
                   ctx: AuthCtx = Depends(require_decide(Feature.APPROVE_LEAVE))):
    """Withdraw an approval already given - "APPROVE may be REVOKED". OWNER only.

    The original decision stays on the row; revocation is recorded alongside it so
    "this was approved and then withdrawn, by whom and why" stays answerable."""
    rows = (ctx.client.table("leave_requests").select("id,status")
            .eq("facility_id", ctx.facility_id).eq("id", request_id).execute().data)
    if not rows:
        raise api_error(404, "not_found", "leave request not found")
    if rows[0].get("status") != "approved":
        raise api_error(422, "not_approved",
                        "Only an approved request can be revoked "
                        f"(this one is {rows[0].get('status')!r}).")
    return svc.revoke(get_service_client(), ctx.facility_id, request_id,
                      profile_id=ctx.profile_id, reason=body.reason)
