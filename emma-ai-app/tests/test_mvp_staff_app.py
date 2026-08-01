"""Staff App PWA backend (spec SA.1, SA.3, SA.4, SA.5, SA.6).

These run against a fake supabase client rather than the database. The rules
worth protecting here are ordering and authority - who may make each transition,
and what state the system is left in when a step half-fails - and both are
decided in Python before any SQL is emitted.

The one test that does read SQL is the reason-code parity check, because a code
the UI can send and the database rejects is a 500 on a nurse's phone at 3am.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from emma_core.models import TaskExceptionRequest
from emma_core.services import roster_locks, swaps
from emma_core.services import tasks as task_svc

MIGRATION = (pathlib.Path(__file__).resolve().parents[1]
             / "supabase" / "migrations" / "20260731000017_mvp_staff_app.sql")


# ── a fake supabase client ──────────────────────────────────────────────────
class _Query:
    """Records one table operation and applies the filters it was given."""

    def __init__(self, db: "_Fake", name: str):
        self.db, self.name = db, name
        self.op = "select"
        self.payload = None
        self.filters: list[tuple] = []

    # -- verbs ----------------------------------------------------------------
    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def insert(self, payload, **_k):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload, **_k):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload, **_k):
        self.op, self.payload = "upsert", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    # -- filters --------------------------------------------------------------
    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self.filters.append(("neq", col, val))
        return self

    def gt(self, col, val):
        self.filters.append(("gt", col, val))
        return self

    def gte(self, col, val):
        self.filters.append(("gte", col, val))
        return self

    def lte(self, col, val):
        self.filters.append(("lte", col, val))
        return self

    def is_(self, col, _val):
        self.filters.append(("isnull", col, None))
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, list(vals)))
        return self

    def or_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    # -- run ------------------------------------------------------------------
    def _matches(self, row: dict) -> bool:
        for kind, col, val in self.filters:
            actual = row.get(col)
            if kind == "eq" and str(actual) != str(val):
                return False
            if kind == "neq" and str(actual) == str(val):
                return False
            if kind == "isnull" and actual is not None:
                return False
            if kind == "in" and actual not in val:
                return False
            if kind == "gt" and not (actual is not None and str(actual) > str(val)):
                return False
            if kind == "gte" and not (actual is not None and str(actual) >= str(val)):
                return False
            if kind == "lte" and not (actual is not None and str(actual) <= str(val)):
                return False
        return True

    def execute(self):
        rows = self.db.rows.setdefault(self.name, [])
        self.db.calls.append((self.op, self.name))
        if self.op == "select":
            return _Result([r for r in rows if self._matches(r)])
        if self.op in ("insert", "upsert"):
            payload = self.payload if isinstance(self.payload, list) else [self.payload]
            made = []
            for item in payload:
                self.db.seq += 1
                made.append({"id": f"{self.name}-{self.db.seq}", **item})
            rows.extend(made)
            return _Result(made)
        if self.op == "update":
            hit = [r for r in rows if self._matches(r)]
            for r in hit:
                r.update(self.payload)
            return _Result(hit)
        if self.op == "delete":
            keep = [r for r in rows if not self._matches(r)]
            gone = [r for r in rows if self._matches(r)]
            self.db.rows[self.name] = keep
            return _Result(gone)
        raise AssertionError(f"unhandled op {self.op}")


class _Result:
    def __init__(self, data):
        self.data = data


class _Fake:
    def __init__(self, **tables):
        self.rows: dict[str, list[dict]] = {k: list(v) for k, v in tables.items()}
        self.calls: list[tuple[str, str]] = []
        self.seq = 0

    def table(self, name):
        return _Query(self, name)


# ── SA.3 · task exceptions ──────────────────────────────────────────────────
def test_exception_reasons_match_the_migration():
    """The closed list exists in three places - the service, the Pydantic
    pattern and the SQL check. Any two of them agreeing is not enough."""
    sql = MIGRATION.read_text(encoding="utf-8")
    block = re.search(r"reason_code\s+text not null check \(reason_code in \((.*?)\)\)",
                      sql, re.S)
    assert block, "could not find the reason_code check constraint"
    in_sql = set(re.findall(r"'([a-z_]+)'", block.group(1)))

    assert in_sql == set(task_svc.EXCEPTION_REASONS)
    for code in in_sql:
        TaskExceptionRequest(reason_code=code, note="n")     # pattern accepts it


def test_report_exception_logs_the_reason_then_flags_the_task():
    db = _Fake(task_assignments=[{"id": "ta-1", "facility_id": "f1",
                                "task_status": "pending"}])
    out = task_svc.report_exception(db, "f1", "ta-1",
                                    reason_code="resident_refused", staff_id="s1")

    assert out["exception"]["reason_code"] == "resident_refused"
    assert out["task_assignment"]["task_status"] == "exception"
    # Order matters: a task flagged 'exception' with no logged reason reads as
    # explained to anyone scanning the dashboard.
    writes = [c for c in db.calls if c[0] in ("insert", "update")]
    assert writes == [("insert", "task_exceptions"), ("update", "task_assignments")]


def test_report_exception_refuses_a_reason_the_database_would_reject():
    db = _Fake(task_assignments=[{"id": "ta-1", "facility_id": "f1",
                                "task_status": "pending"}])
    with pytest.raises(ValueError, match="reason_code must be one of"):
        task_svc.report_exception(db, "f1", "ta-1", reason_code="because")
    assert db.rows["task_assignments"][0]["task_status"] == "pending"


def test_other_without_a_note_is_refused():
    db = _Fake(task_assignments=[{"id": "ta-1", "facility_id": "f1",
                                "task_status": "pending"}])
    with pytest.raises(ValueError, match="note is required"):
        task_svc.report_exception(db, "f1", "ta-1", reason_code="other", note="   ")


def test_report_exception_refuses_a_task_in_another_facility():
    """The lookup is facility-scoped, so a valid id from another home reads as
    missing rather than as somebody else's task to annotate."""
    other_home = _Fake(task_assignments=[{"id": "ta-1", "facility_id": "f2",
                                          "task_status": "pending"}])
    with pytest.raises(ValueError, match="task assignment not found"):
        task_svc.report_exception(other_home, "f1", "ta-1",
                                  reason_code="clinical_hold")
    assert other_home.rows.get("task_exceptions", []) == []
    assert other_home.rows["task_assignments"][0]["task_status"] == "pending"


def test_set_status_will_not_fabricate_an_exception():
    """`exception` is the outcome of reporting one. Reachable through the status
    endpoint it would create an exception with no reason attached."""
    with pytest.raises(ValueError, match="report_exception"):
        task_svc.set_status(_Fake(), "f1", "ta-1", status="exception")


# ── SA.5 · roster cell locks ────────────────────────────────────────────────
def _request(leave_type: str, start="2026-08-03", end="2026-08-03", **extra) -> dict:
    return {"id": "req-1", "staff_id": "s1", "leave_type": leave_type,
            "date_start": start, "date_end": end, **extra}


def test_an_approved_day_off_forbids_the_cell():
    db = _Fake(roster_cell_locks=[])
    written = roster_locks.apply_for_request(db, "f1", _request("DO"), profile_id="p1")

    assert len(written) == 1
    assert written[0]["lock_type"] == "forbid"
    assert written[0]["shift_type"] is None
    assert written[0]["source_table"] == "leave_requests"


def test_a_day_off_range_locks_every_day_in_it():
    db = _Fake(roster_cell_locks=[])
    written = roster_locks.apply_for_request(
        db, "f1", _request("DO", start="2026-08-03", end="2026-08-05"))
    assert [w["date"] for w in written] == ["2026-08-03", "2026-08-04", "2026-08-05"]


def test_an_approved_duty_request_pins_the_shift_asked_for():
    db = _Fake(roster_cell_locks=[])
    written = roster_locks.apply_for_request(
        db, "f1", _request("duty_request", requested_shift_type="A"))
    assert (written[0]["lock_type"], written[0]["shift_type"]) == ("pin", "A")


def test_annual_leave_creates_no_lock():
    """AL already makes the person unavailable through the
    `approved_leave_unavailable` rule. A lock would report it a second time."""
    db = _Fake(roster_cell_locks=[])
    assert roster_locks.apply_for_request(db, "f1", _request("AL")) == []
    assert db.rows["roster_cell_locks"] == []


def test_re_approving_the_same_request_is_idempotent():
    db = _Fake(roster_cell_locks=[])
    request = _request("DO")
    roster_locks.apply_for_request(db, "f1", request)
    again = roster_locks.apply_for_request(db, "f1", request)

    assert again == []
    assert len(db.rows["roster_cell_locks"]) == 1


def test_a_second_decision_cannot_silently_take_a_locked_cell():
    """Two approvals claiming the same day is a contradiction for the approver to
    resolve, not something to store twice."""
    db = _Fake(roster_cell_locks=[])
    roster_locks.apply_for_request(db, "f1", _request("DO"))
    other = {**_request("duty_request", requested_shift_type="A"), "id": "req-2"}

    with pytest.raises(ValueError, match="already locked"):
        roster_locks.apply_for_request(db, "f1", other)


def test_a_duty_request_with_no_shift_type_cannot_be_locked():
    with pytest.raises(ValueError, match="requested_shift_type"):
        roster_locks.apply_for_request(_Fake(roster_cell_locks=[]), "f1",
                                       _request("duty_request"))


def test_revoking_releases_the_lock_without_deleting_it():
    db = _Fake(roster_cell_locks=[])
    roster_locks.apply_for_request(db, "f1", _request("DO"))
    released = roster_locks.release_for(db, "f1", source_table="leave_requests",
                                        source_id="req-1", profile_id="p2",
                                        reason="cover fell through")

    assert len(released) == 1
    assert released[0]["release_reason"] == "cover fell through"
    # Still on the record - "why was she off on the 3rd?" stays answerable.
    assert len(db.rows["roster_cell_locks"]) == 1


def test_a_released_lock_frees_the_cell_for_a_later_decision():
    db = _Fake(roster_cell_locks=[])
    roster_locks.apply_for_request(db, "f1", _request("DO"))
    roster_locks.release_for(db, "f1", source_table="leave_requests",
                             source_id="req-1")

    later = {**_request("duty_request", requested_shift_type="A"), "id": "req-2"}
    assert roster_locks.apply_for_request(db, "f1", later)


# ── SA.6 · three-party swap ─────────────────────────────────────────────────
def _swap_db(status="pending_peer", **overrides) -> _Fake:
    swap = {"id": "sw-1", "facility_id": "f1", "status": status,
            "requester_staff_id": "s1", "requester_shift_id": "sh-1",
            "counterparty_staff_id": "s2", "counterparty_shift_id": "sh-2",
            **overrides}
    return _Fake(
        swap_requests=[swap],
        shifts=[{"id": "sh-1", "facility_id": "f1", "date": "2026-08-03",
                 "shift_type": "A"},
                {"id": "sh-2", "facility_id": "f1", "date": "2026-08-04",
                 "shift_type": "P"}],
        shift_assignments=[
            {"id": "sa-1", "facility_id": "f1", "shift_id": "sh-1",
             "staff_id": "s1", "status": "assigned"},
            {"id": "sa-2", "facility_id": "f1", "shift_id": "sh-2",
             "staff_id": "s2", "status": "assigned"},
        ],
        roster_cell_locks=[], notifications=[], users_profile=[],
    )


def test_only_the_counterparty_may_answer_a_swap():
    db = _swap_db()
    with pytest.raises(ValueError, match="only the counterparty"):
        swaps.peer_respond(db, "f1", "sw-1", staff_id="s3", accept=True)


def test_the_requester_cannot_accept_their_own_swap():
    """The obvious way to fake a swap: propose it, then approve your own half."""
    db = _swap_db()
    with pytest.raises(ValueError, match="only the counterparty"):
        swaps.peer_respond(db, "f1", "sw-1", staff_id="s1", accept=True)


def test_accepting_moves_it_to_the_manager_not_to_approved():
    db = _swap_db()
    row = swaps.peer_respond(db, "f1", "sw-1", staff_id="s2", accept=True)
    assert row["status"] == "pending_manager"


def test_declining_closes_it():
    db = _swap_db()
    row = swaps.peer_respond(db, "f1", "sw-1", staff_id="s2", accept=False)
    assert row["status"] == "declined"


def test_a_manager_cannot_approve_before_the_peer_has_agreed():
    """The whole point of the ordering: approving here would commit s2 to a shift
    s2 never accepted."""
    db = _swap_db(status="pending_peer")
    with pytest.raises(ValueError, match="only a peer-accepted swap"):
        swaps.manager_decide(db, "f1", "sw-1", decision="approve", profile_id="p1")


def test_approval_exchanges_both_cells_and_locks_them():
    db = _swap_db(status="pending_manager")
    swaps.manager_decide(db, "f1", "sw-1", decision="approve", profile_id="p1")

    by_id = {r["id"]: r for r in db.rows["shift_assignments"]}
    assert by_id["sa-1"]["staff_id"] == "s2"      # s2 now works s1's shift
    assert by_id["sa-2"]["staff_id"] == "s1"

    locks = {(l["staff_id"], l["date"]): l for l in db.rows["roster_cell_locks"]}
    assert locks[("s2", "2026-08-03")]["shift_type"] == "A"
    assert locks[("s1", "2026-08-04")]["shift_type"] == "P"
    assert all(l["source_table"] == "swap_requests" for l in locks.values())


def test_rejection_leaves_the_roster_alone():
    db = _swap_db(status="pending_manager")
    swaps.manager_decide(db, "f1", "sw-1", decision="reject", profile_id="p1")

    by_id = {r["id"]: r for r in db.rows["shift_assignments"]}
    assert (by_id["sa-1"]["staff_id"], by_id["sa-2"]["staff_id"]) == ("s1", "s2")
    assert db.rows["roster_cell_locks"] == []


def test_a_decided_swap_cannot_be_decided_again():
    db = _swap_db(status="approved")
    with pytest.raises(ValueError, match="only a peer-accepted swap"):
        swaps.manager_decide(db, "f1", "sw-1", decision="reject", profile_id="p1")


def test_only_the_requester_may_cancel():
    db = _swap_db()
    with pytest.raises(ValueError, match="only the staff member who proposed"):
        swaps.cancel(db, "f1", "sw-1", staff_id="s2")


def test_a_closed_swap_cannot_be_cancelled():
    db = _swap_db(status="approved")
    with pytest.raises(ValueError, match="no longer be cancelled"):
        swaps.cancel(db, "f1", "sw-1", staff_id="s1")


def test_swapping_with_yourself_is_refused():
    with pytest.raises(ValueError, match="with yourself"):
        swaps.create(_swap_db(), "f1", requester_staff_id="s1",
                     requester_shift_id="sh-1", counterparty_staff_id="s1",
                     counterparty_shift_id="sh-2")


def test_you_cannot_offer_a_shift_you_do_not_hold():
    db = _swap_db()
    with pytest.raises(ValueError, match="not assigned to that shift"):
        swaps.create(db, "f1", requester_staff_id="s3",
                     requester_shift_id="sh-1", counterparty_staff_id="s2",
                     counterparty_shift_id="sh-2")


def test_a_cancelled_assignment_is_not_a_tradeable_shift():
    """Someone already taken off a shift has nothing to trade, and letting them
    offer it would put a second person on a cell the roster believes is vacant."""
    db = _swap_db()
    db.rows["shift_assignments"][0]["status"] = "cancelled"
    with pytest.raises(ValueError, match="not assigned to that shift"):
        swaps.create(db, "f1", requester_staff_id="s1",
                     requester_shift_id="sh-1", counterparty_staff_id="s2",
                     counterparty_shift_id="sh-2")


def test_a_swap_the_roster_moved_under_is_not_committed():
    """A swap can wait on a manager while the roster is republished. Committing a
    stale one would assign somebody to a shift they no longer hold."""
    db = _swap_db(status="pending_manager")
    db.rows["shift_assignments"][1]["status"] = "cancelled"

    with pytest.raises(ValueError, match="not assigned to that shift"):
        swaps.manager_decide(db, "f1", "sw-1", decision="approve", profile_id="p1")
    assert db.rows["shift_assignments"][0]["staff_id"] == "s1"   # untouched


# ── who may make each transition (spec 1.1 x SA.5, SA.6, 2.1) ───────────────
# The service tests above prove the state machine. These prove the guards in
# front of it, because "only the counterparty may accept" is worthless if any
# role can reach the manager's endpoint.
from fastapi.testclient import TestClient                          # noqa: E402

from api.deps import AuthCtx, get_ctx                              # noqa: E402
from emma_core.models import Profile                               # noqa: E402


def _ctx(role: str) -> AuthCtx:
    return AuthCtx(token="t", client=object(),
                   profile=Profile(id="profile-1", facility_id="f1", role=role,
                                   staff_id="staff-1"))


@pytest.fixture
def as_role():
    from api.main import app

    http = TestClient(app, raise_server_exceptions=False)

    def _as(role: str) -> TestClient:
        app.dependency_overrides[get_ctx] = lambda: _ctx(role)
        return http

    yield _as
    app.dependency_overrides.pop(get_ctx, None)


@pytest.mark.parametrize("role", ["NURSE_MGR", "ALLIED_HEALTH", "ADMIN_CLERK",
                                  "SCHEDULER", "FRONTLINE", "HR_AUDITOR", "staff"])
def test_only_owner_may_approve_a_swap(as_role, role):
    """Recommending on a duty request and committing two people's rosters are
    different acts. Everyone below OWNER is refused here."""
    r = as_role(role).post("/swap-requests/sw-1/manager-approve",
                           json={"decision": "approve"})
    assert r.status_code == 403, f"{role} reached the manager approval"
    assert r.json()["detail"]["code"] == "forbidden"


def test_owner_is_not_locked_out_of_swap_approval(as_role):
    """403 is the failure under test; any other status means the guard passed
    and the request reached the (unstubbed) database."""
    r = as_role("superintendent").post("/swap-requests/sw-1/manager-approve",
                                       json={"decision": "approve"})
    assert r.status_code != 403


@pytest.mark.parametrize("role", ["NURSE_MGR", "ALLIED_HEALTH", "SCHEDULER",
                                  "FRONTLINE", "HR_AUDITOR", "staff"])
def test_only_owner_and_the_clerk_may_write_a_staff_profile(as_role, role):
    """rank and employment_type decide which compliance rules apply to a person,
    so editing them is not a directory convenience."""
    r = as_role(role).post("/staff", json={"name": "New", "rank": "RN",
                                           "employment_type": "local_ft"})
    assert r.status_code == 403, f"{role} could create a staff record"


@pytest.mark.parametrize("role", ["superintendent", "ADMIN_CLERK"])
def test_the_roles_that_own_staff_profiles_are_not_locked_out(as_role, role):
    r = as_role(role).post("/staff", json={"name": "New", "rank": "RN",
                                           "employment_type": "local_ft"})
    assert r.status_code != 403


def test_the_facility_swap_queue_is_gated_but_your_own_list_is_not(as_role):
    """Defaulting to `mine` matters: a frontline caller who omits the parameter
    must get their own rows, not a 403."""
    assert as_role("FRONTLINE").get("/swap-requests?mine=false").status_code == 403
    assert as_role("FRONTLINE").get("/swap-requests").status_code != 403


def test_a_staff_profile_write_needs_at_least_one_field(as_role):
    r = as_role("superintendent").patch("/staff/s1", json={})
    assert r.status_code == 422


def test_an_unknown_exception_reason_is_rejected_at_the_edge(as_role):
    """The Pydantic pattern refuses it before any service or database sees it."""
    r = as_role("staff").post("/me/tasks/ta-1/exception",
                              json={"reason_code": "because"})
    assert r.status_code == 422


# ── SA.5 end to end: approving is what locks the cell ───────────────────────
# The tests above prove the lock service. This one proves the wiring, which is
# the actual acceptance criterion: "on approval, the system automatically locks
# the corresponding roster cell".
from tests.test_phase5_leave_service import (      # noqa: E402
    FakeClient, FixedDate, _rows,
)
from emma_core.services import leave as leave_svc  # noqa: E402


def _approve_a(leave_type: str, monkeypatch, **extra) -> FakeClient:
    monkeypatch.setattr(leave_svc, "Date", FixedDate)
    client = FakeClient(_rows(), now="2026-07-01T09:00:00Z")
    row = leave_svc.create_request(
        client, "facility-1", staff_id="staff-1", leave_type=leave_type,
        date_start=FixedDate(2026, 9, 3), date_end=FixedDate(2026, 9, 3), **extra)
    leave_svc.decide(client, "facility-1", row["id"], decision="approve",
                     profile_id="manager-1")
    return client


def test_approving_a_day_off_locks_the_cell(monkeypatch):
    client = _approve_a("DO", monkeypatch)
    locks = client.rows.get("roster_cell_locks", [])
    assert len(locks) == 1
    assert locks[0]["lock_type"] == "forbid"
    assert locks[0]["date"] == "2026-09-03"
    assert locks[0]["locked_by"] == "manager-1"


def test_approving_a_duty_request_pins_the_shift(monkeypatch):
    client = _approve_a("duty_request", monkeypatch, requested_shift_type="A")
    locks = client.rows.get("roster_cell_locks", [])
    assert (locks[0]["lock_type"], locks[0]["shift_type"]) == ("pin", "A")


def test_approving_annual_leave_locks_nothing(monkeypatch):
    client = _approve_a("AL", monkeypatch)
    assert client.rows.get("roster_cell_locks", []) == []


def test_revoking_an_approved_day_off_releases_the_lock(monkeypatch):
    monkeypatch.setattr(leave_svc, "Date", FixedDate)
    client = FakeClient(_rows(), now="2026-07-01T09:00:00Z")
    row = leave_svc.create_request(
        client, "facility-1", staff_id="staff-1", leave_type="DO",
        date_start=FixedDate(2026, 9, 3), date_end=FixedDate(2026, 9, 3))
    leave_svc.decide(client, "facility-1", row["id"], decision="approve",
                     profile_id="manager-1")
    leave_svc.revoke(client, "facility-1", row["id"], profile_id="manager-1",
                     reason="cover fell through")

    lock = client.rows["roster_cell_locks"][0]
    assert lock["released_at"] and lock["release_reason"] == "cover fell through"


def test_submitting_a_request_notifies_the_people_who_can_act_on_it(monkeypatch):
    """SA.1's acceptance criterion. The recipients come from the permission
    matrix, so a legacy 'superintendent' spelling is still notified."""
    monkeypatch.setattr(leave_svc, "Date", FixedDate)
    rows = _rows()
    rows["users_profile"] = [
        {"id": "p-owner", "facility_id": "facility-1", "role": "superintendent"},
        {"id": "p-nurse", "facility_id": "facility-1", "role": "NURSE_MGR"},
        {"id": "p-front", "facility_id": "facility-1", "role": "FRONTLINE"},
    ]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")
    leave_svc.create_request(
        client, "facility-1", staff_id="staff-1", leave_type="DO",
        date_start=FixedDate(2026, 9, 3), date_end=FixedDate(2026, 9, 3))

    told = {n["profile_id"] for n in client.rows.get("notifications", [])
            if n["event_type"] == "request_submitted"}
    assert "p-owner" in told and "p-nurse" in told
    assert "p-front" not in told, "a frontline colleague is not an approver"


# ── SA.4 · the manager stream ───────────────────────────────────────────────
def test_the_stream_replays_only_this_manager_s_events(monkeypatch):
    """"Manager receives update within 5 seconds" is met by a short poll. What
    matters for correctness is the scoping: the stream is one profile's queue,
    not a facility firehose."""
    from api.main import app

    db = _Fake(notifications=[
        {"id": "n1", "facility_id": "f1", "profile_id": "profile-1",
         "created_at": "2026-07-31T10:00:01Z", "event_type": "request_submitted",
         "title": "New DO request"},
        {"id": "n2", "facility_id": "f1", "profile_id": "someone-else",
         "created_at": "2026-07-31T10:00:02Z", "event_type": "request_submitted",
         "title": "Not yours"},
        {"id": "n3", "facility_id": "f1", "profile_id": "profile-1",
         "created_at": "2026-07-30T09:00:00Z", "event_type": "old",
         "title": "Before the cursor"},
    ])
    ctx = _ctx("superintendent")
    ctx.client = db
    app.dependency_overrides[get_ctx] = lambda: ctx
    try:
        http = TestClient(app, raise_server_exceptions=False)
        # max_seconds=0 makes the stream finite: one poll, then close.
        r = http.get("/notifications/stream",
                     params={"after": "2026-07-31T00:00:00Z", "max_seconds": 0})
        body = r.text
    finally:
        app.dependency_overrides.pop(get_ctx, None)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "New DO request" in body
    assert "Not yours" not in body, "the stream leaked another profile's events"
    assert "Before the cursor" not in body
    # The closing cursor lets EventSource resume exactly where it stopped.
    assert "event: reconnect" in body
    assert "2026-07-31T10:00:01Z" in body
