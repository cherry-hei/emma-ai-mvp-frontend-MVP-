"""Every roster write leaves an audit row, not just a KPI row."""
from __future__ import annotations

import pytest

from emma_core.models import ShiftDef
from emma_core.services import roster


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.op, self.payload, self.filters, self.ins = "select", None, [], []

    def select(self, *_a, **_k):
        return self

    def insert(self, payload, **_k):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload, **_k):
        self.op, self.payload = "update", payload
        return self

    def delete(self, **_k):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def in_(self, col, vals):
        self.ins.append((col, {str(v) for v in vals}))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def _hit(self):
        return [r for r in self.db.tables.setdefault(self.name, [])
                if all(str(r.get(c)) == str(v) for c, v in self.filters)
                and all(str(r.get(c)) in vals for c, vals in self.ins)]

    def execute(self):
        rows = self.db.tables.setdefault(self.name, [])
        if self.op == "insert":
            made = self.payload if isinstance(self.payload, list) else [self.payload]
            for row in made:
                row.setdefault("id", f"{self.name}-{len(rows) + 1}")
                rows.append(row)
            return _Result(made)
        if self.op == "update":
            hit = self._hit()
            for r in hit:
                r.update(self.payload)
            return _Result(hit)
        if self.op == "delete":
            hit = self._hit()
            self.db.tables[self.name] = [r for r in rows if r not in hit]
            return _Result(hit)
        return _Result(self._hit())


class _Result:
    def __init__(self, data):
        self.data = data


class FakeDB:
    """No `rpc`, so publish takes the offline path on purpose."""

    def __init__(self, tables=None):
        self.tables = tables or {}

    def table(self, name):
        return _Query(self, name)

    def audit_rows(self, action=None):
        rows = self.tables.get("audit_logs", [])
        return [r for r in rows if action is None or r["action"] == action]


DEF = ShiftDef(id="sd-A", shift_type="A", start_time="07:00", end_time="15:00",
               cross_midnight=False, is_working=True, segments=[], paid_minutes=480)


@pytest.fixture
def db():
    return FakeDB({"staff": [{"id": "staff-1", "facility_id": "home-a",
                              "rank": "RN", "primary_unit_id": "unit-1"}]})


def test_creating_a_period_is_audited(db):
    period, version = roster.create_period(
        db, facility_id="home-a", period_start="2026-09-01",
        period_end="2026-09-30", created_by="prof-1")

    row = db.audit_rows("create")[0]
    assert row["entity_table"] == "roster_periods"
    assert row["entity_id"] == period["id"]
    assert row["actor_profile_id"] == "prof-1"
    assert row["after_json"]["roster_version_id"] == version["id"]


def test_setting_a_cell_is_audited_as_well_as_logged(db):
    roster.set_cell(db, facility_id="home-a", roster_version_id="v1",
                    staff_id="staff-1", date="2026-09-02", shift_type="A",
                    shift_def=DEF, changed_by="prof-1")

    # The KPI log and the audit trail are separate evidence; both must exist.
    assert len(db.tables["manual_override_log"]) == 1
    row = db.audit_rows("create")[0]
    assert row["entity_table"] == "shift_assignments"
    assert row["after_json"]["shift_type"] == "A"
    assert row["actor_profile_id"] == "prof-1"


def test_replacing_a_cell_audits_the_previous_value(db):
    roster.set_cell(db, facility_id="home-a", roster_version_id="v1",
                    staff_id="staff-1", date="2026-09-02", shift_type="A",
                    shift_def=DEF, changed_by="prof-1")
    roster.set_cell(db, facility_id="home-a", roster_version_id="v1",
                    staff_id="staff-1", date="2026-09-02", shift_type="N",
                    shift_def=DEF, changed_by="prof-2")

    row = db.audit_rows("update")[0]
    assert row["before_json"] is not None
    assert row["after_json"]["shift_type"] == "N"


def test_clearing_a_cell_is_audited(db):
    roster.set_cell(db, facility_id="home-a", roster_version_id="v1",
                    staff_id="staff-1", date="2026-09-02", shift_type="A",
                    shift_def=DEF, changed_by="prof-1")
    roster.clear_cell(db, facility_id="home-a", roster_version_id="v1",
                      staff_id="staff-1", date="2026-09-02", changed_by="prof-2")

    row = db.audit_rows("delete")[0]
    assert row["entity_table"] == "shift_assignments"
    assert row["before_json"]["staff_id"] == "staff-1"
    assert row["actor_profile_id"] == "prof-2"


def test_publishing_is_audited(db):
    db.tables["roster_versions"] = [{"id": "v1", "facility_id": "home-a",
                                     "period_id": "p1", "status": "draft"}]
    roster.publish_version(db, facility_id="home-a", roster_version_id="v1",
                           created_by="prof-1")

    row = db.audit_rows("publish")[0]
    assert row["entity_table"] == "roster_versions"
    assert row["entity_id"] == "v1"
    assert row["after_json"]["status"] == "published"


def test_a_failed_audit_write_never_breaks_the_edit(db, monkeypatch):
    from emma_core.services import audit

    monkeypatch.setattr(audit, "_jsonable", lambda _v: (_ for _ in ()).throw(RuntimeError))
    # A lost log line is a defect; a rolled-back roster edit is an outage.
    assignment_id = roster.set_cell(
        db, facility_id="home-a", roster_version_id="v1", staff_id="staff-1",
        date="2026-09-02", shift_type="A", shift_def=DEF, changed_by="prof-1")

    assert assignment_id
    assert db.audit_rows() == []
