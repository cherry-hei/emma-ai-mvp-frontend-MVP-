"""Three-party shift swap (spec SA.6).

    Staff A proposes  ->  Staff B accepts or declines  ->  manager decides

Three consents, and the order is not decoration: a manager must never be asked
to approve a swap the counterparty has not agreed to, because approving one
would commit B to a shift B never accepted. `swap_requests.status` is the state
machine that enforces the order, and every transition here checks the state it
is coming from rather than trusting the caller to have followed the flow.

On approval the two roster cells change hands and are locked, so the next solve
cannot quietly undo a swap two people arranged and a manager signed off.
"""
from __future__ import annotations

from . import notifications as notify
from . import roster_locks
from ..permissions import Feature
from ._common import iso, now_iso

# Only these can still move. Everything else is a closed record.
OPEN_STATES = ("pending_peer", "pending_manager")


def _swap(client, facility_id: str, swap_id: str) -> dict:
    # SQL: select * from swap_requests
    #      where facility_id = :facility_id and id = :swap_id
    rows = (client.table("swap_requests").select("*")
            .eq("facility_id", facility_id).eq("id", swap_id).execute().data)
    if not rows:
        raise ValueError("swap request not found")
    return rows[0]


def _shift(client, facility_id: str, shift_id: str) -> dict:
    # SQL: select * from shifts where facility_id = :facility_id and id = :shift_id
    rows = (client.table("shifts").select("*")
            .eq("facility_id", facility_id).eq("id", shift_id).execute().data)
    if not rows:
        raise ValueError("shift not found in this facility")
    return rows[0]


def _live_assignment(client, facility_id: str, shift_id: str, staff_id: str) -> dict:
    """The staff member's own, still-live row on that shift.

    A cancelled row does not count: someone already taken off a shift has nothing
    to trade, and letting them offer it would put a second person on a cell the
    roster believes is vacant.
    """
    # SQL: select * from shift_assignments
    #      where facility_id = :facility_id and shift_id = :shift_id
    #        and staff_id = :staff_id
    rows = (client.table("shift_assignments").select("*")
            .eq("facility_id", facility_id).eq("shift_id", shift_id)
            .eq("staff_id", staff_id).execute().data)
    live = [r for r in rows if r.get("status") != "cancelled"]
    if not live:
        raise ValueError("that staff member is not assigned to that shift")
    return live[0]


def create(client, facility_id: str, *, requester_staff_id: str,
           requester_shift_id: str, counterparty_staff_id: str,
           counterparty_shift_id: str, reason: str | None = None) -> dict:
    """Staff A proposes a swap. Both sides are checked before B is ever asked."""
    if requester_staff_id == counterparty_staff_id:
        raise ValueError("cannot swap a shift with yourself")
    if requester_shift_id == counterparty_shift_id:
        raise ValueError("both sides of a swap cannot be the same shift")

    # Both must actually hold what they are offering, checked now rather than at
    # approval: asking B to accept a swap A cannot honour wastes B's decision.
    _live_assignment(client, facility_id, requester_shift_id, requester_staff_id)
    _live_assignment(client, facility_id, counterparty_shift_id, counterparty_staff_id)
    requester_shift = _shift(client, facility_id, requester_shift_id)
    counterparty_shift = _shift(client, facility_id, counterparty_shift_id)

    # SQL: insert into swap_requests
    #        (facility_id, requester_staff_id, requester_shift_id,
    #         counterparty_staff_id, counterparty_shift_id, reason, status)
    #      values (..., 'pending_peer') returning *
    row = client.table("swap_requests").insert({
        "facility_id": facility_id,
        "requester_staff_id": requester_staff_id,
        "requester_shift_id": requester_shift_id,
        "counterparty_staff_id": counterparty_staff_id,
        "counterparty_shift_id": counterparty_shift_id,
        "reason": reason,
        "status": "pending_peer",
    }).execute().data[0]

    notify.push(
        client, facility_id, staff_id=counterparty_staff_id,
        event_type="swap_requested",
        title="A colleague asked to swap a shift",
        body=(f'They take your {iso(counterparty_shift["date"])} '
              f'{counterparty_shift["shift_type"]}; you take their '
              f'{iso(requester_shift["date"])} {requester_shift["shift_type"]}'),
        related_type="swap_request", related_id=row["id"],
    )
    return row


def peer_respond(client, facility_id: str, swap_id: str, *, staff_id: str,
                 accept: bool, note: str | None = None) -> dict:
    """Staff B accepts or declines. Only B may answer."""
    swap = _swap(client, facility_id, swap_id)
    if swap["status"] != "pending_peer":
        raise ValueError(
            f"this swap is {swap['status']!r} and is no longer waiting on a peer")
    if swap["counterparty_staff_id"] != staff_id:
        raise ValueError("only the counterparty may respond to this swap")

    patch = {
        "status": "pending_manager" if accept else "declined",
        "peer_responded_at": now_iso(),
        "peer_response_note": note,
    }
    # SQL: update swap_requests set status = :status, peer_responded_at = now(),
    #        peer_response_note = :note
    #      where facility_id = :facility_id and id = :swap_id returning *
    row = (client.table("swap_requests").update(patch)
           .eq("facility_id", facility_id).eq("id", swap_id).execute().data[0])

    if accept:
        notify.push_to_approvers(
            client, facility_id, Feature.APPROVE_DUTY_DO,
            event_type="swap_pending_approval",
            title="A shift swap needs your approval",
            body="Both staff have agreed; the roster changes only once you approve.",
            related_type="swap_request", related_id=swap_id,
        )
    notify.push(
        client, facility_id, staff_id=swap["requester_staff_id"],
        event_type="swap_peer_responded",
        title=f"Your swap was {'accepted' if accept else 'declined'}",
        body=note or None,
        related_type="swap_request", related_id=swap_id,
    )
    return row


def manager_decide(client, facility_id: str, swap_id: str, *, decision: str,
                   profile_id: str | None = None, note: str | None = None) -> dict:
    """Final approval. On approve the roster cells change hands and are locked."""
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be approve or reject")
    swap = _swap(client, facility_id, swap_id)
    if swap["status"] != "pending_manager":
        raise ValueError(
            f"this swap is {swap['status']!r}; only a peer-accepted swap can be decided")

    if decision == "approve":
        _exchange_cells(client, facility_id, swap, profile_id=profile_id)

    patch = {
        "status": "approved" if decision == "approve" else "rejected",
        "manager_decided_by": profile_id,
        "manager_decided_at": now_iso(),
        "manager_note": note,
    }
    # SQL: update swap_requests set status = :status, manager_decided_by = :profile_id,
    #        manager_decided_at = now(), manager_note = :note
    #      where facility_id = :facility_id and id = :swap_id returning *
    row = (client.table("swap_requests").update(patch)
           .eq("facility_id", facility_id).eq("id", swap_id).execute().data[0])

    verdict = "approved" if decision == "approve" else "rejected"
    for staff_id in (swap["requester_staff_id"], swap["counterparty_staff_id"]):
        notify.push(
            client, facility_id, staff_id=staff_id, event_type="swap_decided",
            title=f"Shift swap {verdict}",
            body=note or None,
            related_type="swap_request", related_id=swap_id,
        )
    return row


def _exchange_cells(client, facility_id: str, swap: dict,
                    *, profile_id: str | None) -> None:
    """Move each person onto the other's shift, then lock both cells.

    Re-checked here and not only at proposal time: a swap can sit waiting on a
    manager while the roster is re-published underneath it, and committing a
    stale swap would assign someone to a shift they no longer hold.

    The two updates cannot share a transaction over PostgREST. The order is
    chosen so a failure between them leaves the counterparty on both shifts -
    an overlap the validator reports - rather than a shift with nobody on it.
    """
    requester_assignment = _live_assignment(
        client, facility_id, swap["requester_shift_id"], swap["requester_staff_id"])
    counterparty_assignment = _live_assignment(
        client, facility_id, swap["counterparty_shift_id"], swap["counterparty_staff_id"])

    # SQL: update shift_assignments set staff_id = :counterparty_staff_id
    #      where facility_id = :facility_id and id = :requester_assignment_id
    (client.table("shift_assignments")
     .update({"staff_id": swap["counterparty_staff_id"]})
     .eq("facility_id", facility_id).eq("id", requester_assignment["id"]).execute())
    # SQL: update shift_assignments set staff_id = :requester_staff_id
    #      where facility_id = :facility_id and id = :counterparty_assignment_id
    (client.table("shift_assignments")
     .update({"staff_id": swap["requester_staff_id"]})
     .eq("facility_id", facility_id).eq("id", counterparty_assignment["id"]).execute())

    for shift_id, staff_id in (
        (swap["requester_shift_id"], swap["counterparty_staff_id"]),
        (swap["counterparty_shift_id"], swap["requester_staff_id"]),
    ):
        shift = _shift(client, facility_id, shift_id)
        roster_locks.pin_cell(
            client, facility_id, staff_id=staff_id, on=shift["date"],
            shift_type=shift["shift_type"], source_table="swap_requests",
            source_id=swap["id"], profile_id=profile_id,
        )


def cancel(client, facility_id: str, swap_id: str, *, staff_id: str) -> dict:
    """Staff A withdraws their own proposal while it is still open."""
    swap = _swap(client, facility_id, swap_id)
    if swap["status"] not in OPEN_STATES:
        raise ValueError(f"this swap is {swap['status']!r} and can no longer be cancelled")
    if swap["requester_staff_id"] != staff_id:
        raise ValueError("only the staff member who proposed the swap may cancel it")

    # SQL: update swap_requests set status = 'cancelled'
    #      where facility_id = :facility_id and id = :swap_id returning *
    row = (client.table("swap_requests").update({"status": "cancelled"})
           .eq("facility_id", facility_id).eq("id", swap_id).execute().data[0])
    notify.push(
        client, facility_id, staff_id=swap["counterparty_staff_id"],
        event_type="swap_cancelled", title="A swap request was withdrawn",
        related_type="swap_request", related_id=swap_id,
    )
    return row


def list_swaps(client, facility_id: str, *, staff_id: str | None = None,
               status: str | None = None, limit: int = 50) -> list[dict]:
    """Manager queue when `staff_id` is omitted; the staff app's own list when not."""
    # SQL: select * from swap_requests
    #      where facility_id = :facility_id
    #        [and (requester_staff_id = :staff_id or counterparty_staff_id = :staff_id)]
    #        [and status = :status]
    #      order by created_at desc limit :limit
    query = client.table("swap_requests").select("*").eq("facility_id", facility_id)
    if staff_id:
        query = query.or_(
            f"requester_staff_id.eq.{staff_id},counterparty_staff_id.eq.{staff_id}")
    if status:
        query = query.eq("status", status)
    return query.order("created_at", desc=True).limit(limit).execute().data
