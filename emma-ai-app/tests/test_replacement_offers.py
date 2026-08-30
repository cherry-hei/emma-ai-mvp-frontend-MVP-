"""The emergency cover loop: manager asks, staff answer, manager commits."""
from __future__ import annotations

import pytest

from emma_core.services import replacement_offers as offers


# ── a stand-in for the PostgREST client ─────────────────────────────────────
class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.op, self.payload, self.filters = "select", None, []

    def select(self, *_a, **_k):
        return self

    def insert(self, payload, **_k):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload, **_k):
        self.op, self.payload = "update", payload
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def _matches(self, row):
        return all(str(row.get(c)) == str(v) for c, v in self.filters)

    def execute(self):
        rows = self.db.tables.setdefault(self.name, [])
        if self.op == "insert":
            payload = dict(self.payload)
            payload.setdefault("id", f"{self.name}-{len(rows) + 1}")
            rows.append(payload)
            return _Result([payload])
        if self.op == "update":
            hit = [r for r in rows if self._matches(r)]
            for r in hit:
                r.update(self.payload)
            return _Result(hit)
        return _Result([r for r in rows if self._matches(r)])


class _Result:
    def __init__(self, data):
        self.data = data


class FakeDB:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return _Query(self, name)


@pytest.fixture
def db():
    d = FakeDB()
    d.tables["sl_incidents"] = [{
        "id": "inc1", "facility_id": "fac1", "staff_id": "absent1",
        "shift_id": "sh1", "replacement_status": "open",
    }]
    d.tables["replacement_offers"] = []
    d.tables["notifications"] = []
    return d


@pytest.fixture(autouse=True)
def engine(monkeypatch):
    """Two eligible candidates and one the rules refuse."""
    monkeypatch.setattr(offers.incidents, "build_candidates", lambda *a, **k: [
        {"candidate_staff_id": "ok1", "compliance_ok": True, "score": 91, "rank": "CW"},
        {"candidate_staff_id": "ok2", "compliance_ok": True, "score": 78, "rank": "CW"},
        {"candidate_staff_id": "blocked", "compliance_ok": False, "score": 99,
         "rank": "CW", "blocked_reasons": ["rest period"]},
    ])
    sent = []
    monkeypatch.setattr(offers.notify, "push",
                        lambda *a, **k: sent.append(k) or {"id": "n"})
    monkeypatch.setattr(offers.audit, "record", lambda *a, **k: None)
    return sent


def _offer_two(db):
    return offers.offer(db, "fac1", "inc1", staff_ids=["ok1", "ok2"], profile_id="mgr")


# ── offering ────────────────────────────────────────────────────────────────
def test_a_manager_can_ask_several_people_at_once(db, engine):
    rows = _offer_two(db)

    assert [r["offered_staff_id"] for r in rows] == ["ok1", "ok2"]
    assert all(r["status"] == "pending" for r in rows)
    assert len(engine) == 2, "each person asked gets their own notification"


def test_the_score_the_manager_saw_is_kept(db):
    rows = _offer_two(db)

    assert rows[0]["score"] == 91
    assert rows[1]["score"] == 78


def test_someone_the_rules_refuse_cannot_be_asked(db):
    """Offering a shift the approval step must refuse wastes the person's day."""
    with pytest.raises(ValueError) as exc:
        offers.offer(db, "fac1", "inc1", staff_ids=["blocked"])

    assert "blocked" in str(exc.value)


def test_asking_the_same_person_twice_does_not_send_twice(db, engine):
    _offer_two(db)
    again = offers.offer(db, "fac1", "inc1", staff_ids=["ok1"])

    assert again == []
    assert len(engine) == 2


def test_a_resolved_incident_takes_no_more_offers(db):
    db.tables["sl_incidents"][0]["replacement_status"] = "resolved"

    with pytest.raises(ValueError):
        offers.offer(db, "fac1", "inc1", staff_ids=["ok1"])


# ── answering ───────────────────────────────────────────────────────────────
def test_accepting_records_the_answer(db):
    rows = _offer_two(db)
    out = offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=True)

    assert out["status"] == "accepted"
    assert out["responded_at"]


def test_declining_records_the_answer(db):
    rows = _offer_two(db)
    out = offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1",
                         accept=False, note="already on nights")

    assert out["status"] == "declined"
    assert out["response_note"] == "already on nights"


def test_only_the_person_asked_may_answer(db):
    rows = _offer_two(db)

    with pytest.raises(ValueError):
        offers.respond(db, "fac1", rows[0]["id"], staff_id="ok2", accept=True)


def test_an_answered_offer_cannot_be_answered_again(db):
    rows = _offer_two(db)
    offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=False)

    with pytest.raises(ValueError):
        offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=True)


def test_the_manager_hears_back(db, engine):
    rows = _offer_two(db)
    engine.clear()
    offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=True)

    assert len(engine) == 1
    assert engine[0]["profile_id"] == "mgr"


# ── approving ───────────────────────────────────────────────────────────────
@pytest.fixture
def resolved(monkeypatch):
    calls = []

    def resolve_incident(_c, _f, incident_id, **kwargs):
        calls.append((incident_id, kwargs))
        return {"incident": {"replacement_status": "resolved"},
                "future_debts": [], "resolution_minutes": 9}

    monkeypatch.setattr(offers.incidents, "resolve_incident", resolve_incident)
    return calls


def test_approving_hands_the_roster_write_to_the_existing_code(db, resolved):
    """A second copy of the re-rostering logic would drift from the first."""
    rows = _offer_two(db)
    offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=True)
    out = offers.approve(db, "fac1", rows[0]["id"], profile_id="mgr")

    assert len(resolved) == 1
    incident_id, kwargs = resolved[0]
    assert incident_id == "inc1"
    assert kwargs["replacement_staff_id"] == "ok1"
    assert out["offer"]["status"] == "approved"
    assert out["resolution_minutes"] == 9


def test_accepting_is_not_being_rostered(db, resolved):
    """The first yes does not win; the manager still chooses."""
    rows = _offer_two(db)
    offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=True)

    assert resolved == []


def test_an_unanswered_offer_cannot_be_approved(db, resolved):
    rows = _offer_two(db)

    with pytest.raises(ValueError):
        offers.approve(db, "fac1", rows[0]["id"], profile_id="mgr")
    assert resolved == []


def test_a_declined_offer_cannot_be_approved(db, resolved):
    rows = _offer_two(db)
    offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=False)

    with pytest.raises(ValueError):
        offers.approve(db, "fac1", rows[0]["id"], profile_id="mgr")


def test_everyone_else_is_told_the_shift_is_gone(db, resolved, engine):
    """Otherwise they wait on an answer that is never coming."""
    rows = _offer_two(db)
    offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=True)
    engine.clear()
    offers.approve(db, "fac1", rows[0]["id"], profile_id="mgr")

    assert db.tables["replacement_offers"][1]["status"] == "superseded"
    assert [n["staff_id"] for n in engine] == ["ok2"]


def test_the_approval_is_audited(db, resolved, monkeypatch):
    logged = []
    monkeypatch.setattr(offers.audit, "record",
                        lambda _c, **kw: logged.append(kw))
    rows = _offer_two(db)
    offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=True)
    offers.approve(db, "fac1", rows[0]["id"], profile_id="mgr")

    assert len(logged) == 1
    assert logged[0]["entity_table"] == "replacement_offers"
    assert logged[0]["after"]["replacement_staff_id"] == "ok1"


# ── withdrawing ─────────────────────────────────────────────────────────────
def test_a_manager_can_pull_an_offer_back(db, engine):
    rows = _offer_two(db)
    engine.clear()
    out = offers.withdraw(db, "fac1", rows[1]["id"], profile_id="mgr")

    assert out["status"] == "withdrawn"
    assert engine[0]["staff_id"] == "ok2"


def test_a_committed_offer_cannot_be_pulled_back(db, resolved):
    rows = _offer_two(db)
    offers.respond(db, "fac1", rows[0]["id"], staff_id="ok1", accept=True)
    offers.approve(db, "fac1", rows[0]["id"], profile_id="mgr")

    with pytest.raises(ValueError):
        offers.withdraw(db, "fac1", rows[0]["id"], profile_id="mgr")


def test_a_withdrawn_offer_can_be_made_again(db):
    """Circumstances change; the person is still eligible."""
    rows = _offer_two(db)
    offers.withdraw(db, "fac1", rows[0]["id"])
    again = offers.offer(db, "fac1", "inc1", staff_ids=["ok1"])

    assert len(again) == 1
    assert again[0]["status"] == "pending"


# ── reading ─────────────────────────────────────────────────────────────────
def test_a_staff_member_sees_only_their_own(db):
    _offer_two(db)

    mine = offers.list_offers(db, "fac1", staff_id="ok2")

    assert [r["offered_staff_id"] for r in mine] == ["ok2"]
