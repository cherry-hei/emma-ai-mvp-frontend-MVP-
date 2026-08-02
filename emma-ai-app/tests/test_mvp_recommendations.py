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
# ALLIED_HEALTH left this list on 1 Aug 2026: Cherry confirmed the role does hold
# R on leave, scoped to its own discipline. The scoping is exercised further
# down, against a client that can answer "whose leave is this".
CANNOT_RECOMMEND = ["FRONTLINE", "SCHEDULER", "HR_AUDITOR", "staff"]


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


# ── domain-scoped recommendation (Cherry, 1 Aug 2026) ───────────────────────
# "R for leave/duty approvals within their own domain only (e.g. PT approving PT
# leave)." The route guard cannot enforce this - it knows the caller's role but
# not whose leave the request is for - so these run against the service with a
# client that can answer that question.
class _RecQuery:
    def __init__(self, store, table):
        self.store, self.table, self.f, self.mode, self.payload = store, table, {}, "select", None

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self.f[col] = val
        return self

    def is_(self, col, _v):
        self.f[col] = None
        return self

    def insert(self, row):
        self.mode, self.payload = "insert", row
        return self

    def update(self, patch):
        self.mode, self.payload = "update", patch
        return self

    def execute(self):
        rows = self.store[self.table]
        if self.mode == "insert":
            new = {**self.payload, "id": f"{self.table}-{len(rows)}"}
            rows.append(new)
            return type("R", (), {"data": [new]})
        hits = [r for r in rows if all(r.get(k) == v for k, v in self.f.items())]
        if self.mode == "update":
            for r in hits:
                r.update(self.payload)
        return type("R", (), {"data": hits})


class _RecDB:
    """Two therapists, one nurse, and a leave request belonging to each."""

    def __init__(self):
        from collections import defaultdict
        self.store = defaultdict(list)
        self.store["staff"] += [
            {"id": "s-pt", "facility_id": "f1", "rank": "PT"},
            {"id": "s-pta", "facility_id": "f1", "rank": "PTA"},
            {"id": "s-ot", "facility_id": "f1", "rank": "OT"},
            {"id": "s-rn", "facility_id": "f1", "rank": "RN"},
        ]
        self.store["users_profile"] += [
            {"id": "p-pt", "facility_id": "f1", "staff_id": "s-pt", "role": "ALLIED_HEALTH"},
            {"id": "p-nurse", "facility_id": "f1", "staff_id": "s-rn", "role": "NURSE_MGR"},
            {"id": "p-orphan", "facility_id": "f1", "staff_id": None, "role": "ALLIED_HEALTH"},
        ]
        for who in ("s-pt", "s-pta", "s-ot", "s-rn"):
            self.store["leave_requests"].append(
                {"id": f"req-{who}", "facility_id": "f1", "status": "pending",
                 "staff_id": who})

    def table(self, name):
        return _RecQuery(self.store, name)


@pytest.fixture
def recdb():
    return _RecDB()


def _recommend(db, *, profile, role, request_id):
    return rec_svc.add(db, "f1", request_id, profile_id=profile, role=role,
                       recommendation="approve", reason="cover is arranged")


@pytest.mark.parametrize(("request_id", "label"), [
    ("req-s-pt", "another physiotherapist"),
    ("req-s-pta", "their own physiotherapy assistant"),
])
def test_a_therapist_may_recommend_inside_their_discipline(recdb, request_id, label):
    row = _recommend(recdb, profile="p-pt", role="ALLIED_HEALTH",
                     request_id=request_id)
    assert row["recommendation"] == "approve", label


@pytest.mark.parametrize("request_id", ["req-s-ot", "req-s-rn"])
def test_a_therapist_may_not_recommend_outside_it(recdb, request_id):
    """An OT is a different profession and a nurse is not allied health at all.
    Neither is "own domain", however sympathetic the reviewer."""
    with pytest.raises(rec_svc.OutOfDomainError):
        _recommend(recdb, profile="p-pt", role="ALLIED_HEALTH",
                   request_id=request_id)


def test_a_reviewer_with_no_staff_record_recommends_on_nobody(recdb):
    """Fails closed. An account we cannot place in a discipline cannot be shown
    to be in the right one, and the safe reading of "unknown" is "no"."""
    with pytest.raises(rec_svc.OutOfDomainError):
        _recommend(recdb, profile="p-orphan", role="ALLIED_HEALTH",
                   request_id="req-s-pt")


def test_a_nursing_officer_is_not_scoped(recdb):
    """Scoping belongs to ALLIED_HEALTH alone. Leaking it to the other R roles
    would quietly empty the approval queue for the people who run it."""
    for request_id in ("req-s-pt", "req-s-ot", "req-s-rn"):
        assert _recommend(recdb, profile="p-nurse", role="NURSE_MGR",
                          request_id=request_id)


def test_the_endpoint_returns_403_not_500(recdb, as_role):
    """Out-of-domain is a permission answer, not a malformed request. A therapist
    retrying with better wording will not help, so it must not read as 422."""
    from api.main import app
    from api.deps import get_ctx

    app.dependency_overrides[get_ctx] = lambda: AuthCtx(
        token="t", client=recdb,
        profile=Profile(id="p-pt", facility_id="f1", role="ALLIED_HEALTH",
                        staff_id="s-pt"))
    try:
        http = TestClient(app, raise_server_exceptions=False)
        blocked = http.post("/leave-requests/req-s-ot/recommendation",
                            json={"recommendation": "approve", "reason": "ok"})
        assert blocked.status_code == 403
        assert blocked.json()["detail"]["code"] == "out_of_domain"

        allowed = http.post("/leave-requests/req-s-pta/recommendation",
                            json={"recommendation": "approve", "reason": "ok"})
        assert allowed.status_code == 201
    finally:
        app.dependency_overrides.pop(get_ctx, None)


# ── the approver has to see who said it (Cherry, 1 Aug 2026) ────────────────
class _Directory:
    """A stub that answers per table, so profiles and staff can differ."""

    def __init__(self, **tables):
        self.tables = tables
        self.name = None

    def table(self, name):
        self.name = name
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
        return type("R", (), {"data": list(self.tables.get(self.name, []))})()


def _directory(recommendations):
    return _Directory(
        request_recommendations=recommendations,
        users_profile=[
            {"id": "p-nurse", "email": "no@naac.hk", "staff_id": "s-nurse"},
            {"id": "p-clerk", "email": "clerk@naac.hk", "staff_id": None},
        ],
        staff=[{"id": "s-nurse", "name": "李美玲", "name_en": "Li Mei Ling"}],
    )


def test_each_recommendation_names_its_reviewer():
    """Two nursing officers who disagree must not render as two identical
    'NURSE_MGR' rows - the OWNER is being asked to weigh people, not job titles."""
    rows = [{**_rec("p-nurse", "approve"), "leave_request_id": "r1",
             "recommended_role": "NURSE_MGR", "reason": "cover is fine"},
            {**_rec("p-clerk", "reject"), "leave_request_id": "r1",
             "recommended_role": "ADMIN_CLERK", "reason": "quota is spent"}]
    out = rec_svc.attach(_directory(rows), "f1", [{"id": "r1"}])
    names = {r["recommended_by"]: r["recommended_by_name"]
             for r in out[0]["recommendations"]}
    assert names["p-nurse"] == "李美玲"
    # No staff record: the email's local part beats showing a bare uuid.
    assert names["p-clerk"] == "clerk"
    assert out[0]["recommendation_summary"]["split"] is True


def test_an_unnameable_reviewer_still_appears():
    """A missing name renders as the role. Dropping the row, or 500ing the
    queue, would hide a review the approver is required to weigh."""
    rows = [{**_rec("p-ghost", "reject"), "leave_request_id": "r1",
             "recommended_role": "NURSE_MGR", "reason": "no"}]
    out = rec_svc.attach(_directory(rows), "f1", [{"id": "r1"}])
    assert out[0]["recommendations"][0]["recommended_by_name"] is None
    assert out[0]["recommendations"][0]["recommendation"] == "reject"


def test_names_survive_an_unreachable_directory():
    class _NoDirectory(_Directory):
        def execute(self):
            if self.name in ("users_profile", "staff"):
                raise RuntimeError("unreachable")
            return super().execute()

    db = _NoDirectory(request_recommendations=[
        {**_rec("p-nurse", "approve"), "leave_request_id": "r1"}])
    out = rec_svc.attach(db, "f1", [{"id": "r1"}])
    assert len(out[0]["recommendations"]) == 1
    assert out[0]["recommendations"][0]["recommended_by_name"] is None


# ── the shape the approval screen reads ─────────────────────────────────────
def test_each_recommendation_carries_the_approval_screen_aliases():
    """`recommender_name` / `recommender_role` / `decision` are what the screen
    binds to; the columns are named after the table. Both travel, so neither the
    schema nor the screen has to be renamed to match the other."""
    rows = [{**_rec("p-nurse", "approve"), "leave_request_id": "r1",
             "recommended_role": "NURSE_MGR", "reason": "cover is fine"}]
    rec = rec_svc.attach(_directory(rows), "f1", [{"id": "r1"}])[0]["recommendations"][0]
    assert rec["recommender_name"] == "李美玲"
    assert rec["recommender_role"] == "NURSE_MGR"
    assert rec["decision"] == "approve"
    # The canonical names stay - the aliases are additive, not a rename.
    assert (rec["recommended_role"], rec["recommendation"]) == ("NURSE_MGR", "approve")
    assert rec["reason"] and rec["created_at"]


# ── withdraw: authorised by identity, not by role ───────────────────────────
@pytest.mark.parametrize("role", ["FRONTLINE", "NURSE_MGR", "ADMIN_CLERK", "OWNER"])
def test_withdraw_is_not_a_role_gate(as_role, role):
    """Unlike the decision, `/withdraw` refuses nobody at the door: a care worker
    withdraws their own request, an OWNER cancels any. Whose request it is gets
    decided in the handler, where the data can answer it - so the only thing that
    must not happen here is a 403 on the way in."""
    r = as_role(role).post("/leave-requests/req-1/withdraw", json={})
    assert r.status_code != 403, f"{role} must reach the withdraw handler"


def test_withdraw_takes_an_optional_reason():
    from emma_core.models import WithdrawRequest

    assert WithdrawRequest().reason is None
    assert WithdrawRequest(reason="changed my mind").reason == "changed my mind"
