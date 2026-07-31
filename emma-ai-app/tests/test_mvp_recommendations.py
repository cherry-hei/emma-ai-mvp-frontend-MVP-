"""Recommend-vs-approve (spec 1.1).

The rule under test, from the RBAC definition of 30 Jul 2026: a nursing officer,
therapist or admin clerk may attach a suggest-approve/suggest-reject with a
reason; the final decision belongs to OWNER alone.

The interesting cases are the boundaries - the same role passing one guard and
failing the other on the same feature, and two reviewers disagreeing without the
disagreement being averaged away.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.deps import AuthCtx, get_ctx
from emma_core.models import Profile, RecommendationRequest, RevokeRequest
from emma_core.services import recommendations as rec_svc


def _ctx(role: str) -> AuthCtx:
    return AuthCtx(
        token="t",
        client=object(),
        profile=Profile(id="profile-1", facility_id="f1", role=role, staff_id="staff-1"),
    )


@pytest.fixture
def as_role():
    from api.main import app

    http = TestClient(app, raise_server_exceptions=False)

    def _as(role: str) -> TestClient:
        app.dependency_overrides[get_ctx] = lambda: _ctx(role)
        return http

    yield _as
    app.dependency_overrides.pop(get_ctx, None)


# ── the boundary: same feature, two different guards ────────────────────────
CANNOT_RECOMMEND = ["ALLIED_HEALTH", "FRONTLINE", "SCHEDULER", "HR_AUDITOR", "staff"]


@pytest.mark.parametrize("role", CANNOT_RECOMMEND)
def test_roles_without_r_cannot_recommend(as_role, role):
    r = as_role(role).post("/leave-requests/req-1/recommendation",
                           json={"recommendation": "approve", "reason": "ok"})
    assert r.status_code == 403, f"{role} must not recommend on leave"


@pytest.mark.parametrize("role", ["NURSE_MGR", "ADMIN_CLERK", "admin", "hr", "scheduler"])
def test_no_role_but_owner_can_decide_or_revoke(as_role, role):
    """The heart of it: these roles reach the recommendation endpoint but must be
    refused the decision and the revocation."""
    http = as_role(role)
    assert http.patch("/leave-requests/req-1",
                      json={"decision": "approve"}).status_code == 403
    assert http.post("/leave-requests/req-1/revoke",
                     json={"reason": "cover fell through"}).status_code == 403


def test_nurse_mgr_passes_recommend_and_fails_decide_on_the_same_request(as_role):
    http = as_role("NURSE_MGR")
    # Not 403 - it gets past the guard and into the handler, which is the point.
    assert http.post("/leave-requests/req-1/recommendation",
                     json={"recommendation": "approve", "reason": "cover arranged"}
                     ).status_code != 403
    assert http.patch("/leave-requests/req-1",
                      json={"decision": "approve"}).status_code == 403


# ── payload validation ──────────────────────────────────────────────────────
def test_a_recommendation_requires_a_non_blank_reason():
    with pytest.raises(ValueError):
        RecommendationRequest(recommendation="approve", reason="   ")
    with pytest.raises(ValueError):
        RecommendationRequest(recommendation="approve", reason="")
    assert RecommendationRequest(recommendation="reject", reason="short-staffed").reason


def test_recommendation_must_be_approve_or_reject():
    with pytest.raises(ValueError):
        RecommendationRequest(recommendation="maybe", reason="unsure")


def test_revoking_requires_a_reason():
    with pytest.raises(ValueError):
        RevokeRequest(reason=" ")
    assert RevokeRequest(reason="staff withdrew").reason


def test_service_rejects_an_unknown_recommendation():
    with pytest.raises(ValueError, match="must be one of"):
        rec_svc.add(object(), "f1", "req-1", profile_id="p1", role="NURSE_MGR",
                    recommendation="perhaps", reason="x")


def test_service_rejects_a_blank_reason():
    with pytest.raises(ValueError, match="needs a reason"):
        rec_svc.add(object(), "f1", "req-1", profile_id="p1", role="NURSE_MGR",
                    recommendation="approve", reason="  ")


# ── summarise: disagreement must survive ────────────────────────────────────
def _rec(who: str, what: str, withdrawn: str | None = None) -> dict:
    return {"recommended_by": who, "recommendation": what,
            "withdrawn_at": withdrawn, "created_at": f"2026-07-31T0{len(who)}:00:00Z"}


def test_summarise_counts_live_recommendations():
    s = rec_svc.summarise([_rec("a", "approve"), _rec("bb", "approve")])
    assert (s["total"], s["approve"], s["reject"], s["split"]) == (2, 2, 0, False)


def test_summarise_flags_a_split_rather_than_netting_it_off():
    """Two reviewers disagreeing is signal, not noise - the approver has to be
    told to read the reasons instead of trusting a tally."""
    s = rec_svc.summarise([_rec("a", "approve"), _rec("bb", "reject")])
    assert s["split"] is True
    assert (s["approve"], s["reject"]) == (1, 1)


def test_summarise_ignores_withdrawn_recommendations():
    s = rec_svc.summarise([
        _rec("a", "approve"),
        _rec("bb", "reject", withdrawn="2026-07-31T09:00:00Z"),
    ])
    assert (s["total"], s["reject"], s["split"]) == (1, 0, False)


def test_summarise_of_nothing_is_empty_not_an_error():
    assert rec_svc.summarise([]) == {"total": 0, "approve": 0, "reject": 0,
                                     "split": False}


# ── attach ──────────────────────────────────────────────────────────────────
class _FakeClient:
    """Minimal supabase-shaped stub: .table().select().eq().in_().is_().execute()."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def is_(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()


def test_attach_puts_recommendations_on_each_request():
    rows = [
        {**_rec("a", "approve"), "leave_request_id": "r1"},
        {**_rec("bb", "reject"), "leave_request_id": "r1"},
        {**_rec("ccc", "approve"), "leave_request_id": "r2"},
    ]
    out = rec_svc.attach(_FakeClient(rows), "f1", [{"id": "r1"}, {"id": "r2"}])
    by_id = {r["id"]: r for r in out}
    assert len(by_id["r1"]["recommendations"]) == 2
    assert by_id["r1"]["recommendation_summary"]["split"] is True
    assert by_id["r2"]["recommendation_summary"] == {
        "total": 1, "approve": 1, "reject": 0, "split": False}


def test_attach_on_an_empty_queue_makes_no_query():
    """An empty approval queue must not fan out a query - `in_()` with no ids is
    both pointless and, on some drivers, a syntax error."""
    def _explode(*_a, **_k):
        raise AssertionError("attach must not query for an empty request list")

    client = _FakeClient([])
    client.table = _explode
    assert rec_svc.attach(client, "f1", []) == []


def test_attach_leaves_a_request_with_no_reviews_with_an_empty_list():
    out = rec_svc.attach(_FakeClient([]), "f1", [{"id": "r1"}])
    assert out[0]["recommendations"] == []
    assert out[0]["recommendation_summary"]["total"] == 0


# ── revoke guards ───────────────────────────────────────────────────────────
def test_revoke_refuses_a_request_that_was_never_approved():
    from emma_core.services import leave as leave_svc

    with pytest.raises(ValueError, match="only an approved request"):
        leave_svc.revoke(_FakeClient([{"id": "r1", "status": "pending"}]), "f1", "r1",
                         profile_id="p1", reason="mistake")


def test_revoke_refuses_a_missing_request():
    from emma_core.services import leave as leave_svc

    with pytest.raises(ValueError, match="not found"):
        leave_svc.revoke(_FakeClient([]), "f1", "nope", profile_id="p1", reason="x")
