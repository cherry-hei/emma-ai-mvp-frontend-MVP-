"""Synthetic regressions for durable duty-pin and day-off lock enforcement.

These tests intentionally use only an in-memory PostgREST-shaped fake.  They
prove application guard ordering and deterministic validation behaviour; they
do not prove deployed database RLS policy behaviour.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.deps import AuthCtx, get_ctx
from api.main import app
from api.routers import roster as roster_router
from emma_core.models import Profile, ShiftDef
from emma_core.services import incidents, roster, swaps, validation


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Small in-memory subset of the PostgREST chain used by these guards."""

    def __init__(self, db: "_MemoryDB", table: str):
        self.db = db
        self.table_name = table
        self.operation = "select"
        self.payload = None
        self.filters: list[tuple[str, str, object]] = []
        self._limit: int | None = None

    def select(self, *_args, **_kwargs):
        self.operation = "select"
        return self

    def insert(self, payload, **_kwargs):
        self.operation, self.payload = "insert", payload
        return self

    def update(self, payload, **_kwargs):
        self.operation, self.payload = "update", payload
        return self

    def delete(self, **_kwargs):
        self.operation = "delete"
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self.filters.append(("lte", column, value))
        return self

    def is_(self, column, value):
        self.filters.append(("is", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, list(values)))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self._limit = value
        return self

    def _matches(self, row: dict) -> bool:
        for kind, column, expected in self.filters:
            actual = row.get(column)
            if kind == "eq" and str(actual) != str(expected):
                return False
            if kind == "gte" and (actual is None or str(actual) < str(expected)):
                return False
            if kind == "lte" and (actual is None or str(actual) > str(expected)):
                return False
            if kind == "is" and expected == "null" and actual is not None:
                return False
            if kind == "in" and str(actual) not in {str(value) for value in expected}:
                return False
        return True

    def execute(self):
        rows = self.db.tables.setdefault(self.table_name, [])
        hits = [row for row in rows if self._matches(row)]
        if self.operation == "select":
            return _Result(hits[:self._limit] if self._limit is not None else hits)
        if self.operation == "insert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            made = []
            for payload in payloads:
                self.db.sequence += 1
                row = {"id": f"{self.table_name}-{self.db.sequence}", **payload}
                rows.append(row)
                made.append(row)
            return _Result(made)
        if self.operation == "update":
            for row in hits:
                row.update(self.payload)
            return _Result(hits)
        if self.operation == "delete":
            self.db.tables[self.table_name] = [row for row in rows if row not in hits]
            return _Result(hits)
        raise AssertionError(f"unknown operation {self.operation}")


class _MemoryDB:
    def __init__(self, tables: dict[str, list[dict]] | None = None):
        self.tables = {name: [dict(row) for row in rows]
                       for name, rows in (tables or {}).items()}
        self.sequence = 0

    def table(self, name):
        return _Query(self, name)


PIN = {
    "id": "pin-1",
    "facility_id": "facility-1",
    "staff_id": "staff-1",
    "date": "2026-11-01",
    "lock_type": "pin",
    "shift_type": "A",
    "source_table": "leave_requests",
    "source_id": "request-1",
    "released_at": None,
}
FORBID = {
    "id": "forbid-1",
    "facility_id": "facility-1",
    "staff_id": "staff-1",
    "date": "2026-11-01",
    "lock_type": "forbid",
    "shift_type": None,
    "source_table": "leave_requests",
    "source_id": "day-off-1",
    "released_at": None,
}
A_DEF = ShiftDef(
    id="definition-a", shift_type="A", start_time="07:00", end_time="15:00",
    cross_midnight=False, is_working=True, segments=[], paid_minutes=480,
)
P_DEF = ShiftDef(
    id="definition-p", shift_type="P", start_time="13:00", end_time="21:00",
    cross_midnight=False, is_working=True, segments=[], paid_minutes=480,
)
DO_DEF = ShiftDef(
    id="definition-do", shift_type="DO", start_time=None, end_time=None,
    cross_midnight=False, is_working=False, segments=[], paid_minutes=0,
)


def _db(*locks: dict) -> _MemoryDB:
    return _MemoryDB({
        "staff": [{
            "id": "staff-1", "facility_id": "facility-1", "rank": "HCA",
            "primary_unit_id": "unit-1",
        }],
        "roster_cell_locks": list(locks),
    })


def _set(db: _MemoryDB, shift_type: str, definition: ShiftDef):
    return roster.set_cell(
        db, facility_id="facility-1", roster_version_id="version-1",
        staff_id="staff-1", date="2026-11-01", shift_type=shift_type,
        shift_def=definition,
    )


def test_live_pin_allows_its_requested_working_shift(monkeypatch):
    monkeypatch.setattr(roster.audit, "record", lambda *_args, **_kwargs: None)
    db = _db(PIN)

    assignment_id = _set(db, "A", A_DEF)

    assert assignment_id
    assert db.tables["shifts"][0]["shift_type"] == "A"
    assert db.tables["shift_assignments"][0]["staff_id"] == "staff-1"


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda db: _set(db, "P", P_DEF), "pin_shift_type_mismatch"),
        (lambda db: roster.clear_cell(
            db, facility_id="facility-1", roster_version_id="version-1",
            staff_id="staff-1", date="2026-11-01",
        ), "pin_requires_working_shift"),
        (lambda db: _set(db, "DO", DO_DEF), "pin_requires_working_shift"),
    ],
)
def test_live_pin_rejects_wrong_code_removal_or_nonworking_replacement(operation, message):
    db = _db(PIN)

    with pytest.raises(ValueError, match=message):
        operation(db)

    assert db.tables.get("shifts", []) == []
    assert db.tables.get("shift_assignments", []) == []


def test_released_pin_does_not_block_a_different_cell_write(monkeypatch):
    monkeypatch.setattr(roster.audit, "record", lambda *_args, **_kwargs: None)
    db = _db({**PIN, "released_at": "2026-10-30T09:00:00Z"})

    _set(db, "P", P_DEF)

    assert db.tables["shifts"][0]["shift_type"] == "P"


def test_live_forbid_blocks_working_assignment_but_not_nonworking_remediation(monkeypatch):
    monkeypatch.setattr(roster.audit, "record", lambda *_args, **_kwargs: None)
    db = _db(FORBID)

    with pytest.raises(ValueError, match="forbid_rejects_working_shift"):
        _set(db, "A", A_DEF)

    assignment_id = _set(db, "DO", DO_DEF)
    assert assignment_id
    assert db.tables["shifts"][0]["shift_type"] == "DO"


def _snapshot(*, locks=(), shifts=(), assignments=()):
    return validation.RosterSnapshot(
        facility_id="facility-1",
        roster_version_id="version-1",
        period_id="period-1",
        period_start=date(2026, 11, 1),
        period_end=date(2026, 11, 2),
        facility={"id": "facility-1", "code": "B"},
        cell_locks=tuple(locks),
        shifts=tuple(shifts),
        assignments=tuple(assignments),
        staff=({"id": "staff-1", "rank": "HCA", "employment_type": "local_ft"},),
    )


def test_mismatched_live_pin_is_hard_and_prevents_deterministic_publish_validation(monkeypatch):
    snapshot = _snapshot(
        locks=(PIN,),
        shifts=({
            "id": "shift-p", "date": "2026-11-01", "shift_type": "P",
            "is_working": True, "start_time": "13:00", "end_time": "21:00",
        },),
        assignments=({
            "id": "assignment-p", "shift_id": "shift-p", "staff_id": "staff-1",
            "status": "assigned", "role": "HCA",
        },),
    )
    monkeypatch.setattr(validation, "load_snapshot", lambda *_args: snapshot)
    monkeypatch.setattr(validation, "evaluate_core_constraints", lambda _snapshot: [])
    monkeypatch.setattr(validation, "evaluate_swd_ratios", lambda _snapshot: ([], []))
    monkeypatch.setattr(validation, "evaluate_night_rules", lambda _snapshot: [])
    monkeypatch.setattr(validation, "evaluate_naac_hash_day_off_rule", lambda _snapshot: [])
    monkeypatch.setattr(validation, "evaluate_sequence_rules", lambda _snapshot: [])
    monkeypatch.setattr(validation, "evaluate_agency_rules", lambda _snapshot: [])
    monkeypatch.setattr(validation, "evaluate_part_time_rules", lambda _snapshot: [])
    monkeypatch.setattr(validation, "evaluate_leave_rules", lambda _snapshot: [])
    monkeypatch.setattr(validation.scheduling, "evaluate_roster_rules", lambda **_kwargs: [])

    result = validation.validate_roster(
        object(), "facility-1", "version-1", persist=False,
    )

    assert result["passes"] is False
    assert result["hard_violation_count"] == 1
    finding = result["violations"][0]
    assert finding["rule_code"] == "persisted_cell_lock"
    assert finding["details"]["reason"] == "pin_missing_or_mismatched"
    assert finding["details"]["actual_shift_types"] == ["P"]


@pytest.mark.parametrize(
    ("shift_staff_id", "shift_date"),
    [("staff-2", "2026-11-01"), ("staff-1", "2026-11-02")],
)
def test_live_pin_with_wrong_actual_staff_or_date_is_a_hard_finding(
        shift_staff_id, shift_date):
    snapshot = _snapshot(
        locks=(PIN,),
        shifts=({
            "id": "shift-a", "date": shift_date, "shift_type": "A",
            "is_working": True,
        },),
        assignments=({
            "id": "assignment-a", "shift_id": "shift-a", "staff_id": shift_staff_id,
            "status": "assigned",
        },),
    )

    [finding] = validation.evaluate_persisted_cell_locks(snapshot)

    assert finding["rule_code"] == "persisted_cell_lock"
    assert finding["severity"] == "hard"
    assert finding["details"]["reason"] == "pin_missing_or_mismatched"
    assert finding["staff_id"] == "staff-1"
    assert finding["date"] == "2026-11-01"


def test_incident_cover_cannot_remove_a_live_pinned_staff_member(monkeypatch):
    """The incident resolution route reaches this service before roster mutation."""
    db = _MemoryDB({
        "sl_incidents": [{
            "id": "incident-1", "facility_id": "facility-1", "staff_id": "staff-1",
            "shift_id": "shift-a", "incident_type": "SL", "replacement_status": "open",
            "reported_at": "2026-11-01T00:00:00+00:00",
        }],
        "shifts": [{
            "id": "shift-a", "facility_id": "facility-1", "date": "2026-11-01",
            "shift_type": "A", "is_working": True, "required_rank": "HCA",
        }],
        "shift_assignments": [{
            "id": "assignment-old", "facility_id": "facility-1", "shift_id": "shift-a",
            "staff_id": "staff-1", "status": "assigned",
        }],
        "roster_cell_locks": [PIN],
    })
    monkeypatch.setattr(incidents, "_require_profile", lambda *_args: None)
    monkeypatch.setattr(incidents, "build_candidates", lambda *_args: [{
        "candidate_staff_id": "staff-2", "compliance_ok": True, "blocked_reasons": [],
    }])
    monkeypatch.setattr(incidents, "_require_active_staff",
                        lambda *_args: {"id": "staff-2", "rank": "HCA"})
    monkeypatch.setattr(incidents, "_resolve_recovery_plan",
                        lambda *_args: (None, None, None, ()))

    with pytest.raises(ValueError, match="pin_requires_working_shift"):
        incidents.resolve_incident(
            db, "facility-1", "incident-1", replacement_staff_id="staff-2",
            profile_id="profile-1",
        )

    assert db.tables["shift_assignments"] == [{
        "id": "assignment-old", "facility_id": "facility-1", "shift_id": "shift-a",
        "staff_id": "staff-1", "status": "assigned",
    }]


def test_incident_recovery_cannot_insert_nonworking_cell_over_a_live_pin(monkeypatch):
    db = _MemoryDB({
        "roster_cell_locks": [{**PIN, "date": "2026-11-02"}],
    })
    target = incidents._RecoveryTarget(
        day=date(2026, 11, 2), code="SLEEP", version_id="version-1",
        definition={"shift_type": "SLEEP", "is_working": False},
    )
    monkeypatch.setattr(incidents, "_target_assignments", lambda *_args: {})

    with pytest.raises(ValueError, match="pin_requires_working_shift"):
        incidents._materialize_night_recovery(
            db, "facility-1", {"unit_id": "unit-1"},
            {"id": "staff-1", "rank": "HCA"}, [target],
        )

    assert db.tables.get("shifts", []) == []
    assert db.tables.get("shift_assignments", []) == []


def test_approved_swap_cannot_move_a_live_pinned_staff_member():
    db = _MemoryDB({
        "shifts": [
            {"id": "shift-a", "facility_id": "facility-1", "date": "2026-11-01",
             "shift_type": "A", "is_working": True},
            {"id": "shift-p", "facility_id": "facility-1", "date": "2026-11-02",
             "shift_type": "P", "is_working": True},
        ],
        "shift_assignments": [
            {"id": "assignment-a", "facility_id": "facility-1", "shift_id": "shift-a",
             "staff_id": "staff-1", "status": "assigned"},
            {"id": "assignment-p", "facility_id": "facility-1", "shift_id": "shift-p",
             "staff_id": "staff-2", "status": "assigned"},
        ],
        "roster_cell_locks": [PIN],
    })
    swap = {
        "id": "swap-1", "requester_shift_id": "shift-a", "requester_staff_id": "staff-1",
        "counterparty_shift_id": "shift-p", "counterparty_staff_id": "staff-2",
    }

    with pytest.raises(ValueError, match="pin_requires_working_shift"):
        swaps._exchange_cells(db, "facility-1", swap, profile_id="profile-1")

    assert [row["staff_id"] for row in db.tables["shift_assignments"]] == [
        "staff-1", "staff-2",
    ]


def test_rest_shift_route_reaches_live_pin_guard_before_any_mutation(monkeypatch):
    """The permitted HTTP route cannot bypass the service-level cell guard."""
    db = _db(PIN)
    context = AuthCtx(
        token="synthetic", client=db,
        profile=Profile(
            id="profile-1", facility_id="facility-1", role="scheduler",
            staff_id="staff-1",
        ),
    )
    monkeypatch.setattr(roster_router.svc, "get_shift_defs", lambda *_args: [P_DEF])
    monkeypatch.setattr(roster_router.scheduling_svc, "validate_task_labels",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(roster_router.scheduling_svc, "sync_task_rows_for_assignment",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(roster.audit, "record", lambda *_args, **_kwargs: None)
    app.dependency_overrides[get_ctx] = lambda: context
    try:
        response = TestClient(app, raise_server_exceptions=False).patch(
            "/shifts",
            json={
                "roster_version_id": "version-1", "staff_id": "staff-1",
                "date": "2026-11-01", "shift_type": "P", "tasks": [],
            },
        )
    finally:
        app.dependency_overrides.pop(get_ctx, None)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_input"
    assert "pin_shift_type_mismatch" in response.json()["detail"]["message"]
    assert db.tables.get("shifts", []) == []
    assert db.tables.get("shift_assignments", []) == []
