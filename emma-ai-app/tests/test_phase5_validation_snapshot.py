"""Audit-boundary tests for immutable Phase 4+5 roster validation."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from emma_core.services import scheduling, validation
from emma_core.services.validation import RosterSnapshot, _snapshot_digest


class FakeQuery:
    def __init__(self, client, table: str):
        self.client = client
        self.table = table
        self.action = "select"
        self.filters: list[tuple[str, str, object]] = []

    def select(self, _columns: str = "*"):
        return self

    def insert(self, _payload):
        self.action = "insert"
        return self

    def update(self, _payload):
        self.action = "update"
        return self

    def delete(self):
        self.action = "delete"
        return self

    def eq(self, column: str, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values):
        self.filters.append(("in", column, set(values)))
        return self

    def gte(self, column: str, value):
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column: str, value):
        self.filters.append(("lte", column, value))
        return self

    def or_(self, _expression: str):
        return self

    def order(self, _column: str, **_kwargs):
        return self

    def _matches(self, row: dict) -> bool:
        for operation, column, expected in self.filters:
            actual = row.get(column)
            if operation == "eq" and actual != expected:
                return False
            if operation == "in" and actual not in expected:
                return False
            if operation == "gte" and str(actual)[:10] < str(expected)[:10]:
                return False
            if operation == "lte" and str(actual)[:10] > str(expected)[:10]:
                return False
        return True

    def execute(self):
        if self.action != "select":
            self.client.mutations.append((self.action, self.table))
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[
            deepcopy(row)
            for row in self.client.rows.get(self.table, ())
            if self._matches(row)
        ])


class FakeClient:
    def __init__(self, rows: dict[str, list[dict]]):
        self.rows = deepcopy(rows)
        self.mutations: list[tuple[str, str]] = []

    def table(self, name: str):
        return FakeQuery(self, name)


def _snapshot(**updates) -> RosterSnapshot:
    values = {
        "facility_id": "facility-1",
        "roster_version_id": "roster-1",
        "period_id": "period-1",
        "period_start": date(2026, 7, 1),
        "period_end": date(2026, 7, 31),
        "facility": {"id": "facility-1", "code": "A"},
    }
    values.update(updates)
    return RosterSnapshot(**values)


def test_read_only_phase4_validation_never_materializes_legacy_tasks():
    client = FakeClient({
        "roster_versions": [{
            "id": "roster-1",
            "facility_id": "facility-1",
        }],
        "shifts": [{
            "id": "shift-1",
            "facility_id": "facility-1",
            "roster_version_id": "roster-1",
            "date": "2026-07-01",
            "shift_type": "A",
            "start_time": "07:00",
            "end_time": "15:00",
            "is_working": True,
        }],
        "shift_assignments": [{
            "id": "assignment-1",
            "facility_id": "facility-1",
            "shift_id": "shift-1",
            "staff_id": "staff-1",
            "role": "HCA",
            "status": "assigned",
            "tasks": ["Medication"],
        }],
        "staff": [{
            "id": "staff-1",
            "facility_id": "facility-1",
            "rank": "HCA",
            "employment_type": "agency",
        }],
        "facility_units": [],
        "task_definitions": [{
            "id": "task-1",
            "facility_id": "facility-1",
            "task_name": "Medication",
            "task_code": "A1",
            "required_rank": "HCA",
            "active": True,
        }],
        "task_assignments": [],
        "staff_qualifications": [],
        "facility_events": [],
        "event_staffing_requirements": [],
        "floor_min_staffing_rules": [],
        "violation_log": [],
    })

    violations = scheduling.validate_roster_rules(
        client,
        "facility-1",
        "roster-1",
        persist=False,
    )

    assert client.mutations == []
    assert len(violations) == 1
    assert violations[0]["rule_code"] == "task_eligibility"
    assert violations[0]["task_assignment_id"] is None
    assert violations[0]["details"]["task_reference"].startswith("legacy:")
    assert violations[0]["details"]["source_type"] == "legacy_cell"
    assert violations[0]["details"]["issues"][0]["reason"] == "unaudited_external"


def test_persisted_phase4_validation_keeps_materialization_and_audit_writes():
    client = FakeClient({
        "roster_versions": [{
            "id": "roster-1",
            "facility_id": "facility-1",
        }],
        "shifts": [{
            "id": "shift-1",
            "facility_id": "facility-1",
            "roster_version_id": "roster-1",
            "date": "2026-07-01",
            "shift_type": "A",
            "start_time": "07:00",
            "end_time": "15:00",
            "is_working": True,
        }],
        "shift_assignments": [{
            "id": "assignment-1",
            "facility_id": "facility-1",
            "shift_id": "shift-1",
            "staff_id": "staff-1",
            "role": "HCA",
            "status": "assigned",
            "tasks": ["Medication"],
        }],
        "staff": [{
            "id": "staff-1",
            "facility_id": "facility-1",
            "rank": "HCA",
            "employment_type": "agency",
        }],
        "task_definitions": [{
            "id": "task-1",
            "facility_id": "facility-1",
            "task_name": "Medication",
            "task_code": "A1",
            "required_rank": "HCA",
            "active": True,
        }],
    })

    scheduling.validate_roster_rules(
        client,
        "facility-1",
        "roster-1",
        persist=True,
    )

    assert ("insert", "task_assignments") in client.mutations
    assert ("delete", "violation_log") in client.mutations
    assert ("insert", "violation_log") in client.mutations


@pytest.mark.parametrize("field_name", (
    "shifts",
    "assignments",
    "staff",
    "facility_units",
    "task_definitions",
    "task_assignments",
    "staff_qualifications",
    "facility_events",
    "event_staffing_requirements",
    "floor_min_staffing_rules",
))
def test_digest_covers_every_phase4_validation_input(field_name: str):
    baseline = _snapshot()
    changed = replace(
        baseline,
        **{field_name: ({"id": f"{field_name}-1", "value": 1},)},
    )

    assert _snapshot_digest(changed) != _snapshot_digest(baseline)


def test_complete_validation_consumes_phase4_rows_from_loaded_snapshot(monkeypatch):
    snapshot = _snapshot(
        shifts=({"id": "shift-1", "date": "2026-07-01", "is_working": False},),
        facility_units=({"id": "unit-1"},),
        task_definitions=({"id": "task-1"},),
        task_assignments=({"id": "task-assignment-1"},),
        staff_qualifications=({"id": "qualification-1"},),
        facility_events=({"id": "event-1"},),
        event_staffing_requirements=({"id": "event-rule-1"},),
        floor_min_staffing_rules=({"id": "floor-rule-1"},),
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        validation,
        "load_snapshot",
        lambda _client, _facility_id, _roster_version_id: snapshot,
    )

    def capture(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(scheduling, "evaluate_roster_rules", capture)
    monkeypatch.setattr(
        scheduling,
        "validate_roster_rules",
        lambda *_args, **_kwargs: pytest.fail(
            "complete validation must not re-read Phase 4 inputs"
        ),
    )

    validation.validate_roster(
        object(),
        "facility-1",
        "roster-1",
        persist=False,
    )

    assert captured == {
        "shifts": snapshot.shifts,
        "assignments": snapshot.assignments,
        "staff": snapshot.staff,
        "units": snapshot.facility_units,
        "task_definitions": snapshot.task_definitions,
        "task_assignments": snapshot.task_assignments,
        "qualification_rows": snapshot.staff_qualifications,
        "events": snapshot.facility_events,
        "event_requirements": snapshot.event_staffing_requirements,
        "floor_rules": snapshot.floor_min_staffing_rules,
    }
