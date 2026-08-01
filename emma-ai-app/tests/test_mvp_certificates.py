"""Certificate vault and expiry warnings - MVP SA.7.

The interesting behaviour is not storage, it is the warning ladder. A single
"expires within 30 days" alert fails two ways and hits both: sent once it is
forgotten in a busy week, sent daily it is muted by day three and the mute
carries over to the certificate that actually matters.

So each certificate crosses fixed stages and each stage fires exactly once,
which makes the job safe to run from a scheduler. These tests pin the stage
boundaries, the once-only guarantee, and the two places the guarantee could
silently break: a renewal, and a failed send.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as Date, timedelta

import pytest

from emma_core.services import certificates as svc

TODAY = Date(2026, 8, 1)


# ── a stand-in for the PostgREST client ──────────────────────────────────────
class _Query:
    def __init__(self, store, table):
        self.store, self.table_name = store, table
        self.eq_filters, self.in_filters = {}, {}
        self.not_null, self._lte, self._gte = None, None, None
        self.payload, self.mode = None, "select"

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.eq_filters[col] = val
        return self

    def in_(self, col, vals):
        self.in_filters[col] = list(vals)
        return self

    def lte(self, col, val):
        self._lte = (col, val)
        return self

    def gte(self, col, val):
        self._gte = (col, val)
        return self

    @property
    def not_(self):
        return self

    def is_(self, col, _val):
        self.not_null = col
        return self

    def order(self, *_a, **_k):
        return self

    def insert(self, row):
        self.mode, self.payload = "insert", row
        return self

    def update(self, patch):
        self.mode, self.payload = "update", patch
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def _matches(self, row):
        if any(row.get(k) != v for k, v in self.eq_filters.items()):
            return False
        if any(row.get(k) not in v for k, v in self.in_filters.items()):
            return False
        if self.not_null and row.get(self.not_null) is None:
            return False
        if self._lte and str(row.get(self._lte[0]) or "9999") > str(self._lte[1]):
            return False
        if self._gte and str(row.get(self._gte[0]) or "0000") < str(self._gte[1]):
            return False
        return True

    def execute(self):
        rows = self.store[self.table_name]
        if self.mode == "insert":
            new = {**self.payload, "id": f"{self.table_name}-{len(rows)}"}
            rows.append(new)
            return type("R", (), {"data": [new]})
        hits = [r for r in rows if self._matches(r)]
        if self.mode == "update":
            for row in hits:
                row.update(self.payload)
        elif self.mode == "delete":
            for row in hits:
                rows.remove(row)
            return type("R", (), {"data": []})
        hits.sort(key=lambda r: str(r.get("expiry_date") or "9999-99-99"))
        return type("R", (), {"data": hits})


class FakeDB:
    def __init__(self):
        self.store = defaultdict(list)
        self.store["staff"].append(
            {"id": "staff-1", "facility_id": "fac-1", "name": "Chan Siu Ming"})
        self.store["users_profile"].append(
            {"id": "prof-mgr", "facility_id": "fac-1", "role": "superintendent"})

    def table(self, name):
        return _Query(self.store, name)

    @property
    def notifications(self):
        return self.store["notifications"]

    @property
    def certificates(self):
        return self.store["staff_certificates"]


@pytest.fixture
def db():
    return FakeDB()


def _add(db, cert_type, days_from_today, **extra):
    """Put a certificate in the vault as setup.

    `notify=False` because filing one now tells HR (SA.7: "on upload/update, HR
    receives a notification"), and these tests assert on the notification list
    to check the *expiry* ladder. Leaving the filing notice in would make every
    one of them assert around a message it is not about. The filing notice has
    its own tests at the bottom of this file.
    """
    extra.setdefault("notify", False)
    return svc.upsert(db, "fac-1", "staff-1", cert_type=cert_type,
                      expiry_date=TODAY + timedelta(days=days_from_today), **extra)


# ── stage boundaries ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(("days_left", "stage"), [
    (365, None),          # nothing due this far out
    (91,  None),
    (90,  "d90"),         # inclusive at the boundary
    (61,  "d90"),         # still in the 90 band until it crosses 60
    (60,  "d60"),
    (31,  "d60"),
    (30,  "d30"),
    (15,  "d30"),
    (14,  "d14"),
    (8,   "d14"),
    (7,   "d7"),
    (1,   "d7"),
    (0,   "expires_today"),
    (-1,  "expired:1"),
    (-7,  "expired:1"),
    (-8,  "expired:2"),   # weekly once lapsed, not daily
    (-15, "expired:3"),
])
def test_the_warning_ladder_has_the_right_rungs(days_left, stage):
    assert svc.stage_for(days_left) == stage


def test_a_certificate_with_no_expiry_never_warns():
    """Some certificates do not expire. Treating a null as 'overdue' would bury
    the real ones under permanent noise."""
    assert svc.stage_for(None) is None


# ── the vault ────────────────────────────────────────────────────────────────
def test_a_renewal_replaces_the_row_rather_than_adding_one(db):
    _add(db, "BLS", 20)
    _add(db, "BLS", 400)
    assert len(db.certificates) == 1, "a renewal must not leave two live BLS rows"
    assert db.certificates[0]["expiry_date"] == str(TODAY + timedelta(days=400))


def test_cert_type_is_normalised(db):
    """'bls' and 'BLS' are the same certificate; storing both would defeat the
    one-row-per-type rule the readers depend on."""
    _add(db, "bls", 20)
    _add(db, "BLS", 30)
    assert len(db.certificates) == 1
    assert db.certificates[0]["cert_type"] == "BLS"


def test_days_left_is_derived_not_stored(db):
    """A stored days_left is wrong the morning after it is written."""
    row = _add(db, "BLS", 45)
    assert row["days_left"] == 45
    assert "days_left" not in db.certificates[0]


@pytest.mark.parametrize("bad", ["", "   ", "X" * 65])
def test_a_bad_cert_type_is_refused(db, bad):
    with pytest.raises(ValueError):
        svc.upsert(db, "fac-1", "staff-1", cert_type=bad)


# ── the sweep ────────────────────────────────────────────────────────────────
def test_only_certificates_inside_the_horizon_are_swept(db):
    _add(db, "BLS", 10)
    _add(db, "ACLS", 200)
    _add(db, "WOUND_CARE", -5)
    due = {c["cert_type"] for c in svc.expiring(db, "fac-1", today=TODAY)}
    assert due == {"BLS", "WOUND_CARE"}


def test_expired_can_be_excluded(db):
    _add(db, "BLS", 10)
    _add(db, "WOUND_CARE", -5)
    due = {c["cert_type"] for c in
           svc.expiring(db, "fac-1", include_expired=False, today=TODAY)}
    assert due == {"BLS"}


# ── the notification job ─────────────────────────────────────────────────────
def test_each_stage_notifies_exactly_once(db):
    _add(db, "BLS", 30)
    first = svc.notify_expiring(db, "fac-1", today=TODAY)
    assert [c["stage"] for c in first] == ["d30"]

    again = svc.notify_expiring(db, "fac-1", today=TODAY)
    assert again == [], "re-running the job must not re-send the same stage"


def test_the_next_stage_does_fire(db):
    _add(db, "BLS", 30)
    svc.notify_expiring(db, "fac-1", today=TODAY)
    later = svc.notify_expiring(db, "fac-1", today=TODAY + timedelta(days=20))
    assert [c["stage"] for c in later] == ["d14"]


def test_a_renewal_resets_the_ladder(db):
    """Otherwise a certificate renewed at the 7-day mark would carry `d7` into
    its new expiry and stay silent until it was a week from lapsing again."""
    _add(db, "BLS", 7)
    svc.notify_expiring(db, "fac-1", today=TODAY)
    assert db.certificates[0]["notified_stage"] == "d7"

    _add(db, "BLS", 80)
    assert db.certificates[0]["notified_stage"] is None
    resumed = svc.notify_expiring(db, "fac-1", today=TODAY)
    assert [c["stage"] for c in resumed] == ["d90"]


def test_the_staff_member_is_always_told(db):
    _add(db, "BLS", 30)
    svc.notify_expiring(db, "fac-1", today=TODAY)
    to_staff = [n for n in db.notifications if n.get("staff_id") == "staff-1"]
    assert len(to_staff) == 1
    assert to_staff[0]["event_type"] == "certificate_expiry"
    assert "BLS" in to_staff[0]["title"]


def test_a_roster_critical_certificate_escalates_early(db):
    """A lapsed BLS is a rostering problem before it is an HR one - the person
    cannot be put on a drug round tomorrow - so a manager hears at 90 days."""
    _add(db, "BLS", 90)
    sent = svc.notify_expiring(db, "fac-1", today=TODAY)
    assert sent[0]["escalated"] is True
    assert any(n.get("profile_id") == "prof-mgr" for n in db.notifications)


def test_an_ordinary_certificate_escalates_only_when_close(db):
    _add(db, "CONFERENCE_ATTENDANCE", 90)
    sent = svc.notify_expiring(db, "fac-1", today=TODAY)
    assert sent[0]["escalated"] is False
    assert not any(n.get("profile_id") == "prof-mgr" for n in db.notifications)


def test_a_dry_run_sends_nothing(db):
    _add(db, "BLS", 30)
    preview = svc.notify_expiring(db, "fac-1", today=TODAY, dry_run=True)
    assert [c["stage"] for c in preview] == ["d30"]
    assert db.notifications == []
    assert db.certificates[0]["notified_stage"] is None, (
        "a dry run must not consume the stage, or the real send would be skipped")


def test_an_expired_certificate_keeps_being_reported(db):
    """Silence after lapse is the worst outcome: the roster keeps assigning
    someone who is no longer qualified and nothing says so."""
    _add(db, "BLS", -10)
    sent = svc.notify_expiring(db, "fac-1", today=TODAY)
    assert sent[0]["stage"] == "expired:2"
    assert "expired" in db.notifications[0]["title"].lower()


def test_the_message_names_the_staff_member_for_the_manager(db):
    _add(db, "BLS", 30)
    svc.notify_expiring(db, "fac-1", today=TODAY)
    body = db.notifications[0]["body"]
    assert "Chan Siu Ming" in body


# ── SA.7 second pass: the staff member's own vault ──────────────────────────
# "Staff upload their own certificates ... On upload/update, HR receives a
# notification that a colleague's cert was updated ... lead time configurable
# per facility." Three things the first pass did not do.

def _hr_db() -> FakeDB:
    db = FakeDB()
    db.store["users_profile"].append(
        {"id": "prof-hr", "facility_id": "fac-1", "role": "hr"})
    db.store["users_profile"].append(
        {"id": "prof-staff", "facility_id": "fac-1", "role": "FRONTLINE"})
    return db


def _filed(db) -> list[dict]:
    return [n for n in db.notifications if n["event_type"] == "certificate_filed"]


def test_filing_a_certificate_tells_hr(db=None):
    db = _hr_db()
    svc.upsert(db, "fac-1", "staff-1", cert_type="BLS",
               expiry_date=TODAY + timedelta(days=300), cert_number="BLS-99",
               uploaded_by="prof-staff")
    told = {n["profile_id"] for n in _filed(db)}
    # 'hr' is the legacy spelling of HR_AUDITOR, which holds the one write grant
    # on certificates. A literal role list would have missed it entirely.
    assert "prof-hr" in told
    assert "prof-staff" not in told, "the uploader does not need telling"
    assert "Chan Siu Ming" in _filed(db)[0]["title"]


def test_a_renewal_says_renewed_not_uploaded():
    db = _hr_db()
    svc.upsert(db, "fac-1", "staff-1", cert_type="BLS",
               expiry_date=TODAY + timedelta(days=10), notify=False)
    svc.upsert(db, "fac-1", "staff-1", cert_type="BLS",
               expiry_date=TODAY + timedelta(days=400))
    assert "renewed" in _filed(db)[0]["title"]


def test_the_certificate_number_and_issue_date_are_stored():
    db = _hr_db()
    row = svc.upsert(db, "fac-1", "staff-1", cert_type="practising",
                     cert_number="RN-123456", issued_date=Date(2026, 1, 5),
                     expiry_date=TODAY + timedelta(days=200), notify=False)
    assert row["cert_number"] == "RN-123456"
    assert row["issued_date"] == "2026-01-05"
    assert row["cert_type"] == "PRACTISING"


def test_an_issue_date_after_the_expiry_is_refused():
    db = _hr_db()
    with pytest.raises(ValueError, match="issued_date cannot be after"):
        svc.upsert(db, "fac-1", "staff-1", cert_type="BLS",
                   issued_date=Date(2027, 1, 1), expiry_date=Date(2026, 12, 1))


def test_a_failed_notification_does_not_lose_the_certificate():
    """The staff member photographed their card and pressed save."""
    class _NoNotifications(FakeDB):
        def table(self, name):
            if name == "notifications":
                raise RuntimeError("unreachable")
            return super().table(name)

    db = _NoNotifications()
    row = svc.upsert(db, "fac-1", "staff-1", cert_type="BLS",
                     expiry_date=TODAY + timedelta(days=30))
    assert row["cert_type"] == "BLS"
    assert len(db.certificates) == 1


# ── configurable lead times ─────────────────────────────────────────────────
def _with_policy(config: dict) -> FakeDB:
    db = FakeDB()
    db.store["facility_json_configs"].append({
        "id": "cfg-1", "facility_id": "fac-1", "config_key": "certificate_reminders",
        "config_json": config, "active": True, "version": 1,
    })
    return db


def test_a_facility_can_set_its_own_lead_times():
    db = _with_policy({"lead_days": [180, 30], "expired_repeat_days": 14})
    policy = svc.reminder_policy(db, "fac-1")
    assert policy.lead_days == (30, 180)
    assert svc.stage_for(120, policy) == "d180"
    assert svc.stage_for(29, policy) == "d30"
    # 90 is not a rung for this home, so it falls into the next one up.
    assert svc.stage_for(90, policy) == "d180"
    assert svc.stage_for(-10, policy) == "expired:1", "14-day repeat, not 7"


def test_the_sweep_looks_as_far_ahead_as_the_configured_ladder():
    """A home asking to be warned six months out gets nothing from a sweep that
    only looks 90 days ahead, and the misconfiguration is invisible."""
    db = _with_policy({"lead_days": [180]})
    svc.upsert(db, "fac-1", "staff-1", cert_type="BLS",
               expiry_date=TODAY + timedelta(days=150), notify=False)
    sent = svc.notify_expiring(db, "fac-1", today=TODAY, dry_run=True)
    assert [c["stage"] for c in sent] == ["d180"]


@pytest.mark.parametrize("config", [
    {}, {"lead_days": []}, {"lead_days": "soon"}, {"lead_days": [0, -5]},
    {"expired_repeat_days": 0}, {"lead_days": None},
])
def test_a_broken_config_falls_back_to_the_default_ladder(config):
    """Over-warned is recoverable. Silently unwarned is how a certificate lapses
    with nobody told, so no config mistake may be able to cause it."""
    assert svc.reminder_policy(_with_policy(config), "fac-1").lead_days \
        == svc.DEFAULT_POLICY.lead_days


def test_an_unreachable_config_table_falls_back_too():
    class _NoConfigs(FakeDB):
        def table(self, name):
            if name == "facility_json_configs":
                raise RuntimeError("unreachable")
            return super().table(name)

    assert svc.reminder_policy(_NoConfigs(), "fac-1") == svc.DEFAULT_POLICY


# ── the /me/* half, which is the only one FRONTLINE can reach ───────────────
def _staff_client(db):
    from fastapi.testclient import TestClient

    from api.deps import AuthCtx, get_ctx
    from api.main import app
    from emma_core.models import Profile

    ctx = AuthCtx(token="t", client=db,
                  profile=Profile(id="prof-staff", facility_id="fac-1",
                                  role="FRONTLINE", staff_id="staff-1"))
    app.dependency_overrides[get_ctx] = lambda: ctx
    return TestClient(app, raise_server_exceptions=False), app, get_ctx


def test_a_care_worker_can_file_and_read_their_own_certificate():
    """FRONTLINE holds S on staff.certificates, so /staff/{id}/certificates is a
    403 for them - the one person who cannot use the vault was the person whose
    certificate it is."""
    db = _hr_db()
    http, app, get_ctx = _staff_client(db)
    try:
        created = http.post("/me/certificates", json={
            "cert_type": "BLS", "cert_number": "BLS-42",
            "expiry_date": "2027-01-31"})
        listed = http.get("/me/certificates")
    finally:
        app.dependency_overrides.pop(get_ctx, None)

    assert created.status_code == 201, created.text
    assert created.json()["cert_number"] == "BLS-42"
    assert [c["cert_type"] for c in listed.json()] == ["BLS"]
    assert _filed(db), "HR was not told a colleague filed a certificate"


def test_a_care_worker_cannot_delete_a_colleagues_certificate():
    db = _hr_db()
    db.store["staff"].append(
        {"id": "staff-2", "facility_id": "fac-1", "name": "Someone Else"})
    theirs = svc.upsert(db, "fac-1", "staff-2", cert_type="BLS",
                        expiry_date=TODAY + timedelta(days=90), notify=False)

    http, app, get_ctx = _staff_client(db)
    try:
        response = http.delete(f"/me/certificates/{theirs['id']}")
    finally:
        app.dependency_overrides.pop(get_ctx, None)

    assert response.status_code == 404, "a colleague's uuid must read as missing"
    assert len(db.certificates) == 1, "the colleague's certificate was deleted"


# ── the RLS hole the second pass closed ─────────────────────────────────────
def test_the_vault_policy_is_scoped_to_the_person_not_the_facility():
    """Before migration 21 the policy was `facility_id = current_facility_id()`
    alone, so any token in the home could enumerate every colleague's
    certificates straight off the table."""
    import pathlib
    import re

    sql = (pathlib.Path(__file__).resolve().parents[1] / "supabase" / "migrations"
           / "20260801000021_sa7_self_service_vault.sql").read_text(encoding="utf-8")
    policy = re.search(
        r"create policy staff_certificates_tenant.*?;", sql, re.S)
    assert policy, "the policy is not redefined in this migration"
    assert policy.group(0).count("can_see_staff_row(staff_id)") == 2, \
        "both USING and WITH CHECK must be person-scoped"
    assert "add column if not exists cert_number" in sql
