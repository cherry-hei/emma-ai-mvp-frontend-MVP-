"""First-pass reviews on pending requests (spec 1.1).

A recommendation is a nursing officer, therapist or admin clerk saying "I suggest
you approve this, and here is why". It is deliberately not a decision: the
superintendent sees every recommendation attached to the request and decides
alone. Enforcement of who may do which lives in `emma_core.permissions`; this
module only records and reads.

Three rules the storage enforces rather than trusts:

*One live recommendation per reviewer.*
    Changing your mind means withdrawing the first, which leaves both on the
    record. A reviewer cannot quietly become the person who always agreed.

*The role is copied, not joined.*
    `recommended_role` stores the role held at the time. A nursing officer
    promoted to superintendent next month must not retroactively turn last
    month's recommendation into an approval.

*Append-only, apart from withdrawal.*
    `trg_recommendation_append_only` rejects any other update. Editing a reason
    after the approver has read it would make the trail useless as evidence.
"""
from __future__ import annotations

from ..permissions import Feature, may_recommend_for, recommend_scope
from . import audit
from ._common import now_iso

RECOMMENDATIONS = ("approve", "reject")


class OutOfDomainError(PermissionError):
    """The reviewer may recommend, but not on this person's request."""


def _rank_of_staff(client, facility_id: str, staff_id: str | None) -> str | None:
    """The rank on a staff row, or None if it cannot be established.

    Every failure collapses to None - missing id, missing row, unreachable table.
    That is deliberate: this feeds a permission decision, and None denies. A
    lookup that fails must not become a 500 on an endpoint whose answer, when the
    lookup fails, is knowably "no".
    """
    if not staff_id:
        return None
    try:
        rows = (client.table("staff").select("rank")
                .eq("facility_id", facility_id).eq("id", staff_id)
                .execute().data or [])
    except Exception:  # noqa: BLE001 - see docstring: unknown rank denies
        return None
    return rows[0].get("rank") if rows else None


def _rank_of_profile(client, facility_id: str, profile_id: str) -> str | None:
    """The reviewer's own rank, via the staff row their profile points at.

    A profile without a staff row has no rank, so a domain-scoped reviewer in
    that state recommends on nobody. That is the correct failure: an account we
    cannot place in a discipline cannot be shown to be in the right one.
    """
    try:
        rows = (client.table("users_profile").select("staff_id")
                .eq("facility_id", facility_id).eq("id", profile_id)
                .execute().data or [])
    except Exception:  # noqa: BLE001
        return None
    return _rank_of_staff(client, facility_id, rows[0].get("staff_id")) if rows else None


def add(client, facility_id: str, request_id: str, *, profile_id: str,
        role: str, recommendation: str, reason: str,
        feature: Feature = Feature.APPROVE_LEAVE) -> dict:
    """Record a first-pass review. Replaces the reviewer's own previous one."""
    if recommendation not in RECOMMENDATIONS:
        raise ValueError(
            f"recommendation must be one of {RECOMMENDATIONS}, got {recommendation!r}"
        )
    if not (reason or "").strip():
        raise ValueError("a recommendation needs a reason")

    # The request must exist inside the caller's facility. Checked through the
    # caller's own client so RLS decides visibility, not this function.
    rows = (client.table("leave_requests").select("id,status,staff_id")
            .eq("facility_id", facility_id).eq("id", request_id).execute().data)
    if not rows:
        raise ValueError("leave request not found")

    # "R within own domain only - e.g. PT approving PT leave" (Cherry, 1 Aug).
    # The route guard has already established that this role may recommend at
    # all; this is the second question, about whose request.
    #
    # Checked here rather than in the router because it is a property of the
    # data, not of the request: the router knows the caller's role, only a query
    # knows whose leave this is.
    if recommend_scope(role, feature) == "own_domain":
        subject_rank = _rank_of_staff(client, facility_id, rows[0].get("staff_id"))
        own_rank = _rank_of_profile(client, facility_id, profile_id)
        if not may_recommend_for(role, feature, recommender_rank=own_rank,
                                 subject_rank=subject_rank):
            raise OutOfDomainError(
                f"{role} may only recommend within their own discipline; this "
                f"request belongs to {subject_rank or 'an unknown rank'} and the "
                f"reviewer is {own_rank or 'not linked to a staff record'}.")

    withdraw_own(client, facility_id, request_id, profile_id=profile_id)

    row = (client.table("request_recommendations").insert({
        "facility_id": facility_id,
        "leave_request_id": request_id,
        "recommended_by": profile_id,
        "recommended_role": role,
        "recommendation": recommendation,
        "reason": reason.strip(),
    }).execute().data or [{}])[0]

    audit.record(
        client,
        facility_id=facility_id,
        action="request.recommend",
        entity_table="leave_requests",
        entity_id=request_id,
        after={"recommendation": recommendation, "role": role},
        reason=reason.strip(),
        actor_profile_id=profile_id,
    )
    return row


def withdraw_own(client, facility_id: str, request_id: str, *,
                 profile_id: str) -> int:
    """Withdraw this reviewer's live recommendation, if any. Returns how many."""
    rows = (client.table("request_recommendations").select("id")
            .eq("facility_id", facility_id)
            .eq("leave_request_id", request_id)
            .eq("recommended_by", profile_id)
            .is_("withdrawn_at", "null").execute().data or [])
    for row in rows:
        (client.table("request_recommendations")
         .update({"withdrawn_at": now_iso()}).eq("id", row["id"]).execute())
    return len(rows)


def for_request(client, facility_id: str, request_id: str, *,
                include_withdrawn: bool = False) -> list[dict]:
    q = (client.table("request_recommendations").select("*")
         .eq("facility_id", facility_id).eq("leave_request_id", request_id))
    if not include_withdrawn:
        q = q.is_("withdrawn_at", "null")
    rows = q.execute().data or []
    return sorted(rows, key=lambda r: str(r.get("created_at") or ""))


def summarise(rows: list[dict]) -> dict:
    """What the approver's header needs: the counts, and whether reviewers split.

    `split` is the interesting flag. Two reviewers disagreeing is not an error and
    must not be averaged away - it is the signal that the superintendent should
    read the reasons rather than trust the tally."""
    live = [r for r in rows if not r.get("withdrawn_at")]
    approve = sum(1 for r in live if r.get("recommendation") == "approve")
    reject = sum(1 for r in live if r.get("recommendation") == "reject")
    return {
        "total": len(live),
        "approve": approve,
        "reject": reject,
        "split": approve > 0 and reject > 0,
    }


def attach(client, facility_id: str, requests: list[dict]) -> list[dict]:
    """Attach recommendations to a list of requests in one round trip.

    The approval queue renders "pending items together with all recommendations
    attached", so fetching per row would mean one query per request."""
    ids = [r["id"] for r in requests if r.get("id")]
    if not ids:
        return requests
    try:
        rows = (client.table("request_recommendations").select("*")
                .eq("facility_id", facility_id)
                .in_("leave_request_id", ids)
                .is_("withdrawn_at", "null").execute().data or [])
    except Exception:  # noqa: BLE001
        # Annotation is not the queue. If `request_recommendations` is unreachable
        # - most likely because migration 20260731000016 has not been applied to
        # this environment, and the deploy pipeline has no migration step - the
        # Approval Centre must still list its requests. Same reasoning as
        # `audit.record`: a missing annotation is a defect, a 500 on the approval
        # queue is an outage. The absent `recommendations` key is the signal.
        return requests

    by_request: dict[str, list[dict]] = {}
    for row in rows:
        by_request.setdefault(row["leave_request_id"], []).append(row)

    out = []
    for req in requests:
        mine = sorted(by_request.get(req.get("id"), []),
                      key=lambda r: str(r.get("created_at") or ""))
        out.append({**req,
                    "recommendations": mine,
                    "recommendation_summary": summarise(mine)})
    return out
