"""Focused Phase 5 emergency-cover consistency tests without Supabase."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest

from emma_core.services import incidents


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.action = "select"
        self.payload = None
        self.filters = []
        self.sort_column = None
        self.sort_desc = False
        self.row_limit = None

    def select(self, _columns="*"):
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def delete(self):
        self.action = "delete"
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

    def in_(self, column, values):
        self.filters.append(("in", column, set(values)))
        return self

    def order(self, column, *, desc=False, **_kwargs):
        self.sort_column = column
        self.sort_desc = desc
        return self

    def limit(self, value):
        self.row_limit = value
        return self

    def _matches(self, row):
        for operation, column, expected in self.filters:
            actual = row.get(column)
            if operation == "eq" and actual != expected:
                return False
            if operation == "gte" and str(actual) < str(expected):
                return False
            if operation == "lte" and str(actual) > str(expected):
                return False
            if operation == "in" and actual not in expected:
                return False
        return True

    def execute(self):
        rows = self.client.rows.setdefault(self.table, [])
        if self.action == "insert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            inserted = []
            for payload in payloads:
                row = deepcopy(payload)
                row.setdefault("id", f"{self.table}-{self.client.next_id}")
                self.client.next_id += 1
                rows.append(row)
                inserted.append(deepcopy(row))
            return SimpleNamespace(data=inserted)
        if self.action == "update":
            updated = []
            for row in rows:
                if self._matches(row):
                    row.update(deepcopy(self.payload))
                    updated.append(deepcopy(row))
            return SimpleNamespace(data=updated)
        if self.action == "delete":
            kept = [row for row in rows if not self._matches(row)]
            deleted = [deepcopy(row) for row in rows if self._matches(row)]
            self.client.rows[self.table] = kept
            return SimpleNamespace(data=deleted)

        selected = [deepcopy(row) for row in rows if self._matches(row)]
        if self.sort_column:
            selected.sort(
                key=lambda row: str(row.get(self.sort_column) or ""),
                reverse=self.sort_desc,
            )
        if self.row_limit is not None:
            selected = selected[:self.row_limit]
        return SimpleNamespace(data=selected)


class FakeClient:
    def __init__(self):
        self.next_id = 100
        self.rows = {
            "sl_incidents": [{
                "id": "incident-1",
                "facility_id": "facility-1",
                "staff_id": "absent-1",
                "shift_id": "shift-1",
                "incident_type": "SL",
                "replacement_status": "open",
                "reported_at": "2026-07-10T00:00:00Z",
            }],
            "staff": [
                {
                    "id": "absent-1",
                    "facility_id": "facility-1",
                    "name": "Absent",
                    "rank": "EN",
                    "status": "active",
                    "employment_type": "local_ft",
                    "is_audited_for_medication": True,
                    "contracted_hours": 44,
                },
                {
                    "id": "nurse-1",
                    "facility_id": "facility-1",
                    "name": "Cover Nurse",
                    "rank": "EN",
                    "status": "active",
                    "employment_type": "local_ft",
                    "is_audited_for_medication": True,
                    "contracted_hours": 44,
                },
            ],
            "staff_contracts": [{
                "id": "contract-1",
                "facility_id": "facility-1",
                "staff_id": "nurse-1",
                "weekly_hours": 44,
                "max_weekly_hours": 44,
                "min_rest_minutes": 720,
            }],
            "shifts": [{
                "id": "shift-1",
                "facility_id": "facility-1",
                "roster_version_id": "version-1",
                "date": "2026-07-10",
                "shift_type": "7P",
                "start_time": "19:00",
                "end_time": "07:00",
                "cross_midnight": True,
                "required_rank": "EN",
                "required_count": 1,
                "is_working": True,
                "unit_id": "unit-1",
            }],
            "shift_assignments": [{
                "id": "assignment-old",
                "facility_id": "facility-1",
                "shift_id": "shift-1",
                "staff_id": "absent-1",
                "status": "assigned",
            }],
            "shift_definitions": [
                {
                    "id": "definition-sleep",
                    "facility_id": "facility-1",
                    "shift_type": "SLEEP",
                    "is_working": False,
                    "paid_minutes": 0,
                },
                {
                    "id": "definition-do",
                    "facility_id": "facility-1",
                    "shift_type": "DO",
                    "is_working": False,
                    "paid_minutes": 0,
                },
            ],
            "roster_versions": [
                {
                    "id": "version-1",
                    "facility_id": "facility-1",
                    "period_id": "period-current",
                    "version_type": "manual",
                    "status": "published",
                    "created_at": "2026-07-01T00:00:00Z",
                },
                {
                    "id": "version-next",
                    "facility_id": "facility-1",
                    "period_id": "period-next",
                    "version_type": "manual",
                    "status": "published",
                    "created_at": "2026-08-01T00:00:00Z",
                },
            ],
            "roster_periods": [
                {
                    "id": "period-current",
                    "facility_id": "facility-1",
                    "period_start": "2026-07-01",
                    "period_end": "2026-07-31",
                },
                {
                    "id": "period-next",
                    "facility_id": "facility-1",
                    "period_start": "2026-08-01",
                    "period_end": "2026-08-31",
                },
            ],
            "rule_definitions": [{
                "id": "night-policy",
                "facility_id": "facility-1",
                "rule_code": "night_chain",
                "active": True,
                "effective_from": "2026-01-01",
                "config_version": 2,
                "config_json": {
                    "night_shift_types": ["7P"],
                    "chain_employment_types": ["local_ft"],
                    "sleep_codes": ["SLEEP"],
                    "day_off_codes": ["DO"],
                    "cooldown_ranks": ["EN"],
                },
            }],
            "leave_requests": [],
            "future_debt_ledger": [],
            "replacement_candidates": [],
            "manual_override_log": [],
            "users_profile": [{
                "id": "manager-1",
                "facility_id": "facility-1",
            }],
        }

    def table(self, name):
        return FakeQuery(self, name)


@pytest.fixture
def client(monkeypatch):
    store = FakeClient()
    monkeypatch.setattr(incidents.notify, "push", lambda *_args, **_kwargs: None)
    return store


def test_configured_7p_candidate_honours_cooldown_and_recovery(client):
    client.rows["future_debt_ledger"].append({
        "id": "cooldown-1",
        "facility_id": "facility-1",
        "staff_id": "nurse-1",
        "debt_type": "NIGHT_COOLDOWN",
        "due_period_id": "period-current",
        "status": "open",
    })

    [candidate] = incidents.build_candidates(
        client,
        "facility-1",
        client.rows["sl_incidents"][0],
    )

    assert candidate["candidate_staff_id"] == "nurse-1"
    assert not candidate["compliance_ok"]
    assert "mandatory next-period nurse night cooldown" in candidate["blocked_reasons"]


def test_candidate_is_blocked_when_sleep_recovery_day_is_occupied(client):
    client.rows["shifts"].append({
        "id": "shift-next-day",
        "facility_id": "facility-1",
        "roster_version_id": "version-1",
        "date": "2026-07-11",
        "shift_type": "A",
        "start_time": "07:00",
        "end_time": "15:00",
        "cross_midnight": False,
        "required_rank": "EN",
        "required_count": 1,
        "is_working": True,
        "unit_id": "unit-1",
    })
    client.rows["shift_assignments"].append({
        "id": "assignment-next-day",
        "facility_id": "facility-1",
        "shift_id": "shift-next-day",
        "staff_id": "nurse-1",
        "status": "assigned",
    })

    [candidate] = incidents.build_candidates(
        client,
        "facility-1",
        client.rows["sl_incidents"][0],
    )

    assert not candidate["compliance_ok"]
    assert any(
        "mandatory SLEEP recovery" in reason
        for reason in candidate["blocked_reasons"]
    )


def test_resolve_rejects_unknown_candidate_without_writes(client, monkeypatch):
    monkeypatch.setattr(
        incidents,
        "build_candidates",
        lambda *_args, **_kwargs: [{
            "candidate_staff_id": "nurse-1",
            "compliance_ok": True,
            "blocked_reasons": [],
        }],
    )
    before = deepcopy(client.rows)

    with pytest.raises(ValueError, match="current candidate IDs"):
        incidents.resolve_incident(
            client,
            "facility-1",
            "incident-1",
            replacement_staff_id="not-a-candidate",
            profile_id="manager-1",
        )

    assert client.rows == before


def test_7p_cover_materializes_recovery_and_bounded_debts(client):
    result = incidents.resolve_incident(
        client,
        "facility-1",
        "incident-1",
        replacement_staff_id="nurse-1",
        profile_id="manager-1",
    )

    assert [row["shift_type"] for row in result["night_recovery"]] == [
        "SLEEP",
        "DO",
    ]
    assert [row["date"] for row in result["night_recovery"]] == [
        "2026-07-11",
        "2026-07-12",
    ]
    debts = result["future_debts"]
    assert [row["debt_type"] for row in debts] == [
        "TOIL",
        "OT",
        "NIGHT_COOLDOWN",
    ]
    assert all(row["due_period_id"] == "period-next" for row in debts)
    assert all(row["source_shift_id"] == "shift-1" for row in debts)
    assert all(row["details_json"]["shift_type"] == "7P" for row in debts)

    old = next(
        row for row in client.rows["shift_assignments"]
        if row["id"] == "assignment-old"
    )
    assert old["status"] == "cancelled"
    assert result["incident"]["replacement_staff_id"] == "nurse-1"


def test_missing_next_period_blocks_before_any_roster_write(client):
    client.rows["roster_periods"] = [
        row for row in client.rows["roster_periods"]
        if row["id"] == "period-current"
    ]
    before_assignments = deepcopy(client.rows["shift_assignments"])

    with pytest.raises(ValueError, match="next roster period"):
        incidents.resolve_incident(
            client,
            "facility-1",
            "incident-1",
            replacement_staff_id="nurse-1",
            profile_id="manager-1",
        )

    assert client.rows["shift_assignments"] == before_assignments
    assert client.rows["future_debt_ledger"] == []
    assert client.rows["sl_incidents"][0]["replacement_status"] == "open"


def test_open_incident_rejects_cross_facility_staff_before_insert(client):
    client.rows["staff"].append({
        "id": "outsider-1",
        "facility_id": "facility-2",
        "name": "Outsider",
        "rank": "EN",
        "status": "active",
        "employment_type": "local_ft",
    })
    before = deepcopy(client.rows["sl_incidents"])

    with pytest.raises(ValueError, match="does not belong"):
        incidents.open_incident(
            client,
            "facility-1",
            staff_id="outsider-1",
            on_date=date(2026, 7, 10),
        )

    assert client.rows["sl_incidents"] == before
