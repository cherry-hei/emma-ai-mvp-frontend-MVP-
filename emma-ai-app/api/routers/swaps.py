"""/swap-requests - three-party shift swap (spec SA.6).

Who may call what is the whole design here. The two staff-facing transitions are
authorised by *identity*, not by role: only the counterparty may answer, only the
requester may cancel, and both are resolved from the caller's own profile rather
than the request body. The manager transition is authorised by the permission
matrix, because deciding is a role.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx, require_decide, require_read
from emma_core.models import SwapCreateRequest, SwapDecisionRequest, SwapPeerResponse
from emma_core.permissions import Feature
from emma_core.services import me as me_svc
from emma_core.services import swaps as svc

router = APIRouter(tags=["staff-app"])


def _staff_id(ctx: AuthCtx) -> str:
    try:
        return me_svc.resolve_staff_id(ctx.profile)
    except ValueError as exc:
        raise api_error(409, "no_staff_record", str(exc)) from exc


@router.get("/swap-requests")
def list_swaps(status: str | None = Query(default=None),
               mine: bool = Query(default=True,
                                  description="false = the facility queue (needs approve.duty_do)"),
               ctx: AuthCtx = Depends(get_ctx)):
    """`mine=true` (the default) is the staff app's own list and needs no role.

    The facility-wide queue is a different question - "every swap in the home" -
    so it is gated on the same feature that decides them. Defaulting to `mine`
    means a frontline caller who omits the parameter gets their own rows rather
    than a 403.
    """
    if not mine:
        from emma_core.permissions import can_read

        if not can_read(ctx.profile.role, Feature.APPROVE_DUTY_DO):
            raise api_error(403, "forbidden",
                            "Your role may not view the facility swap queue.")
        return svc.list_swaps(ctx.client, ctx.facility_id, status=status)
    return svc.list_swaps(ctx.client, ctx.facility_id,
                          staff_id=_staff_id(ctx), status=status)


@router.post("/swap-requests", status_code=201)
def create_swap(body: SwapCreateRequest, ctx: AuthCtx = Depends(get_ctx)):
    """Staff A proposes. The requester is always the caller."""
    return svc.create(
        ctx.client, ctx.facility_id,
        requester_staff_id=_staff_id(ctx),
        requester_shift_id=body.requester_shift_id,
        counterparty_staff_id=body.counterparty_staff_id,
        counterparty_shift_id=body.counterparty_shift_id,
        reason=body.reason,
    )


@router.patch("/swap-requests/{swap_id}/accept")
def peer_respond(swap_id: str, body: SwapPeerResponse,
                 ctx: AuthCtx = Depends(get_ctx)):
    """Staff B accepts or declines. The service refuses anyone who is not B."""
    return svc.peer_respond(ctx.client, ctx.facility_id, swap_id,
                            staff_id=_staff_id(ctx), accept=body.accept,
                            note=body.note)


@router.post("/swap-requests/{swap_id}/manager-approve")
def manager_decide(swap_id: str, body: SwapDecisionRequest,
                   ctx: AuthCtx = Depends(require_decide(Feature.APPROVE_DUTY_DO))):
    """Final approval. `require_decide` keeps this to OWNER - a nursing officer
    who may recommend on duty requests still cannot commit two people's rosters."""
    return svc.manager_decide(ctx.client, ctx.facility_id, swap_id,
                              decision=body.decision, profile_id=ctx.profile_id,
                              note=body.note)


@router.patch("/swap-requests/{swap_id}/cancel")
def cancel_swap(swap_id: str, ctx: AuthCtx = Depends(get_ctx)):
    """Staff A withdraws their own proposal."""
    return svc.cancel(ctx.client, ctx.facility_id, swap_id, staff_id=_staff_id(ctx))


@router.get("/roster-cell-locks")
def list_locks(start: str = Query(...), end: str = Query(...),
               ctx: AuthCtx = Depends(require_read(Feature.ROSTER_VIEW))):
    """Cells the optimiser must honour in a date range (spec SA.5).

    Read-only on purpose: a lock is a consequence of an approval, so it is
    created by approving and released by revoking. A lock the UI could delete
    directly would let someone cancel a promise without cancelling the decision
    that made it.
    """
    from emma_core.services import roster_locks

    return roster_locks.live_for_period(ctx.client, ctx.facility_id, start, end)
