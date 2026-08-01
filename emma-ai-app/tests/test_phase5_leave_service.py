"""Focused Phase 5 leave-policy integration tests (no database required)."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from emma_core.models import LeaveDecisionRequest, LeaveRequestCreate
from emma_core.services import leave


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 7, 1)


class LateFixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 7, 9)


class PostCutoffFixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 9)


class FakeQuery:
    def __init__(self, client, table: str):
        self.client = client
        self.table = table
        self.filters: list[tuple[str, str, object]] = []
        self.action = "select"
        self.payload = None

    def select(self, _columns: str = "*"):
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def eq(self, column: str, value):
        self.filters.append(("eq", column, value))
        return self

    def lte(self, column: str, value):
        self.filters.append(("lte", column, value))
        return self

    def gte(self, column: str, value):
        self.filters.append(("gte", column, value))
        return self

    def is_(self, column: str, _value):
        # PostgREST spells "column is null" as .is_(col, "null"); the roster-cell
        # lock reads filter on released_at that way.
        self.filters.append(("isnull", column, None))
        return self

    def or_(self, _expression: str):
        return self

    @staticmethod
    def _comparable(value):
        return str(value)[:10] if value is not None else ""

    def _matches(self, row: dict) -> bool:
        for operation, column, expected in self.filters:
            actual = row.get(column)
            if operation == "eq" and actual != expected:
                return False
            if operation == "lte" and self._comparable(actual) > self._comparable(expected):
                return False
            if operation == "gte" and self._comparable(actual) < self._comparable(expected):
                return False
            if operation == "isnull" and actual is not None:
                return False
        return True

    def execute(self):
        rows = self.client.rows.setdefault(self.table, [])
        if self.action == "insert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            inserted = []
            for payload in payloads:
                row = deepcopy(payload)
                row.setdefault("id", f"{self.table}-{len(rows) + 1}")
                row.setdefault("created_at", self.client.now)
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
        return SimpleNamespace(data=[
            deepcopy(row) for row in rows if self._matches(row)
        ])


class FakeClient:
    def __init__(self, rows: dict[str, list[dict]], *, now: str):
        self.rows = deepcopy(rows)
        self.now = now

    def table(self, name: str):
        return FakeQuery(self, name)


def _rows(*, facility_code: str = "A", active_hca_count: int = 1):
    staff = [{
        "id": "staff-1",
        "facility_id": "facility-1",
        "name": "Primary",
        "rank": "HCA",
        "status": "active",
    }]
    staff.extend({
        "id": f"staff-extra-{index}",
        "facility_id": "facility-1",
        "name": f"Extra {index}",
        "rank": "HCA",
        "status": "active",
    } for index in range(1, active_hca_count))
    return {
        "facilities": [{"id": "facility-1", "code": facility_code}],
        "staff": staff,
        "leave_requests": [],
        "calendar_days": [],
        "shift_assignments": [],
        "roster_periods": [{
            "id": "period-1",
            "facility_id": "facility-1",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        }],
        "leave_balances": [],
    }


def test_create_persists_priority_and_policy_evidence(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    client = FakeClient(_rows(), now="2026-07-01T09:00:00Z")

    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="AL",
        date_start=FixedDate(2026, 9, 3),
        date_end=FixedDate(2026, 9, 3),
        reason="family event",
    )

    assert row["status"] == "pending"
    assert row["priority"] == "urgent"
    assert row["priority_reason"] == "Previously approved annual leave"
    assert row["policy_result_json"] == {
        "passes": True,
        "issues": [],
        "priority_weight": 100,
    }


def test_home_b_five_day_holiday_pool_quota_blocks_approval(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    client = FakeClient(
        _rows(facility_code="B", active_hca_count=5),
        now="2026-07-01T09:00:00Z",
    )
    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="DO",
        date_start=FixedDate(2026, 9, 3),
        date_end=FixedDate(2026, 9, 5),
    )

    issues = row["policy_result_json"]["issues"]
    assert [issue["code"] for issue in issues] == ["monthly_request_quota"]
    assert issues[0]["quota"] == 2

    with pytest.raises(ValueError, match="monthly_request_quota"):
        leave.decide(
            client,
            "facility-1",
            row["id"],
            decision="approve",
            profile_id="manager-1",
        )
    stored = client.rows["leave_requests"][0]
    assert stored["status"] == "pending"
    assert stored["policy_result_json"]["passes"] is False


def test_home_b_six_day_holiday_pool_allows_three_requests(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    rows = _rows(facility_code="B")
    rows["calendar_days"] = [
        {
            "facility_id": None,
            "date": "2026-09-01",
            "day_type": "statutory_holiday",
        },
        {
            "facility_id": None,
            "date": "2026-09-20",
            "day_type": "public_holiday",
        },
    ]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")

    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="DO",
        date_start=FixedDate(2026, 9, 3),
        date_end=FixedDate(2026, 9, 5),
    )

    assert row["policy_result_json"]["passes"] is True
    assert row["policy_result_json"]["issues"] == []


def test_approval_rechecks_current_leave_balance(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    rows = _rows()
    rows["leave_balances"] = [{
        "id": "balance-1",
        "facility_id": "facility-1",
        "staff_id": "staff-1",
        "period_id": "period-1",
        "leave_type": "CL",
        "opening_balance": 1,
        "accrued": 0,
        "carried": 0,
        "used": 0,
    }]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")
    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="CL",
        date_start=FixedDate(2026, 9, 3),
        date_end=FixedDate(2026, 9, 3),
    )
    assert row["policy_result_json"]["passes"] is True

    client.rows["leave_balances"][0]["opening_balance"] = 0
    with pytest.raises(ValueError, match="insufficient_leave_balance"):
        leave.decide(
            client,
            "facility-1",
            row["id"],
            decision="approve",
            profile_id="manager-1",
        )
    assert client.rows["leave_requests"][0]["status"] == "pending"


def test_consecutive_cl_is_not_confused_with_combined_balance_cap(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    client = FakeClient(_rows(), now="2026-07-01T09:00:00Z")
    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="CL",
        date_start=FixedDate(2026, 9, 3),
        date_end=FixedDate(2026, 9, 6),
    )

    assert row["policy_result_json"]["issues"] == []
    approved = leave.decide(
        client,
        "facility-1",
        row["id"],
        decision="approve",
        profile_id="manager-1",
    )
    assert approved["status"] == "approved"


def test_high_demand_same_rank_conflict_blocks_approval(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    rows = _rows(active_hca_count=2)
    rows["calendar_days"] = [{
        "facility_id": None,
        "date": "2026-09-25",
        "day_type": "statutory_holiday",
        "holiday_name": "Mid-Autumn Festival",
    }]
    rows["leave_requests"] = [{
        "id": "existing-leave",
        "facility_id": "facility-1",
        "staff_id": "staff-extra-1",
        "category": "al",
        "leave_type": "AL",
        "date_start": "2026-09-25",
        "date_end": "2026-09-25",
        "status": "approved",
        "created_at": "2026-07-01T08:00:00Z",
    }]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")
    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="AL",
        date_start=FixedDate(2026, 9, 25),
        date_end=FixedDate(2026, 9, 25),
    )

    codes = {
        issue["code"] for issue in row["policy_result_json"]["issues"]
    }
    assert {
        "high_demand_ballot_deadline",
        "high_demand_rank_conflict",
    } <= codes
    with pytest.raises(ValueError, match="high_demand"):
        leave.decide(
            client,
            "facility-1",
            row["id"],
            decision="approve",
            profile_id="manager-1",
        )


def test_effective_soft_leave_policy_controls_cutoff(monkeypatch):
    monkeypatch.setattr(leave, "Date", LateFixedDate)
    rows = _rows()
    rows["rule_definitions"] = [{
        "id": "soft-leave-policy",
        "facility_id": "facility-1",
        "rule_code": "leave_rules",
        "severity": "soft",
        "active": True,
        "config_version": 2,
        "effective_from": "2026-01-01",
        "config_json": {
            "request_cutoff_day": 5,
            "max_do_cl_balance": 3,
        },
    }]
    client = FakeClient(rows, now="2026-07-09T09:00:00Z")

    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="AL",
        date_start=LateFixedDate(2026, 8, 3),
        date_end=LateFixedDate(2026, 8, 3),
    )

    assert row["policy_result_json"]["passes"] is True
    assert row["policy_result_json"]["issues"] == [{
        "code": "request_cutoff",
        "severity": "soft",
        "cutoff": "2026-07-05",
        "submitted_on": "2026-07-09",
    }]


def test_cross_period_leave_is_funded_by_each_period(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    rows = _rows()
    rows["roster_periods"].append({
        "id": "period-2",
        "facility_id": "facility-1",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
    })
    rows["leave_balances"] = [
        {
            "id": "september-balance",
            "facility_id": "facility-1",
            "staff_id": "staff-1",
            "period_id": "period-1",
            "leave_type": "AL",
            "opening_balance": 1,
            "used": 0,
        },
        {
            "id": "october-balance",
            "facility_id": "facility-1",
            "staff_id": "staff-1",
            "period_id": "period-2",
            "leave_type": "AL",
            "opening_balance": 1,
            "used": 0,
        },
    ]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")

    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="AL",
        date_start=FixedDate(2026, 9, 30),
        date_end=FixedDate(2026, 10, 1),
    )

    assert row["policy_result_json"]["passes"] is True
    assert row["policy_result_json"]["issues"] == []

    client.rows["leave_balances"][1]["opening_balance"] = 0
    with pytest.raises(ValueError, match="insufficient_leave_balance"):
        leave.decide(
            client,
            "facility-1",
            row["id"],
            decision="approve",
            profile_id="manager-1",
        )


def test_cross_period_leave_rejects_a_missing_period_balance(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    rows = _rows()
    rows["roster_periods"].append({
        "id": "period-2",
        "facility_id": "facility-1",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
    })
    rows["leave_balances"] = [{
        "id": "september-balance",
        "facility_id": "facility-1",
        "staff_id": "staff-1",
        "period_id": "period-1",
        "leave_type": "AL",
        "opening_balance": 1,
        "used": 0,
    }]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")

    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="AL",
        date_start=FixedDate(2026, 9, 30),
        date_end=FixedDate(2026, 10, 1),
    )

    [issue] = row["policy_result_json"]["issues"]
    assert issue["code"] == "insufficient_leave_balance"
    assert issue["period_id"] == "period-2"
    assert issue["reason"] == "missing_period_balance"


def test_leave_policy_is_frozen_at_roster_period_start(monkeypatch):
    monkeypatch.setattr(leave, "Date", PostCutoffFixedDate)
    rows = _rows()
    rows["rule_definitions"] = [
        {
            "id": "period-policy",
            "facility_id": "facility-1",
            "rule_code": "leave_rules",
            "severity": "hard",
            "active": True,
            "config_version": 1,
            "effective_from": "2026-01-01",
            "effective_to": "2026-09-14",
            "config_json": {"request_cutoff_day": 5},
        },
        {
            "id": "mid-period-policy",
            "facility_id": "facility-1",
            "rule_code": "leave_rules",
            "severity": "soft",
            "active": True,
            "config_version": 2,
            "effective_from": "2026-09-15",
            "config_json": {"request_cutoff_day": 5},
        },
    ]
    client = FakeClient(rows, now="2026-07-09T09:00:00Z")

    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="AL",
        date_start=PostCutoffFixedDate(2026, 9, 20),
        date_end=PostCutoffFixedDate(2026, 9, 20),
    )

    [issue] = row["policy_result_json"]["issues"]
    assert issue["code"] == "request_cutoff"
    assert issue["severity"] == "hard"
    assert row["policy_result_json"]["passes"] is False


def test_manager_can_record_audited_high_demand_ballot_override(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    rows = _rows()
    rows["calendar_days"] = [{
        "facility_id": None,
        "date": "2026-09-25",
        "day_type": "statutory_holiday",
        "holiday_name": "Mid-Autumn Festival",
    }]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")
    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="AL",
        date_start=FixedDate(2026, 9, 25),
        date_end=FixedDate(2026, 9, 25),
    )
    assert row["policy_result_json"]["passes"] is False

    approved = leave.decide(
        client,
        "facility-1",
        row["id"],
        decision="approve",
        profile_id="manager-1",
        ballot_approved=True,
    )

    assert approved["status"] == "approved"
    assert approved["policy_result_json"]["passes"] is True
    assert approved["policy_result_json"]["ballot_approved"] is True
    assert approved["policy_result_json"]["ballot_decided_by"] == "manager-1"


def test_leave_request_shape_cannot_flip_leave_and_duty_semantics():
    valid = LeaveRequestCreate(
        leave_type="duty_request",
        requested_shift_type="AN",
        date_start=date(2026, 7, 1),
        date_end=date(2026, 7, 1),
    )
    assert valid.requested_shift_type == "AN"

    with pytest.raises(ValidationError, match="requested_shift_type is required"):
        LeaveRequestCreate(
            leave_type="duty_request",
            date_start=date(2026, 7, 1),
            date_end=date(2026, 7, 1),
        )
    with pytest.raises(ValidationError, match="only valid"):
        LeaveRequestCreate(
            leave_type="AL",
            requested_shift_type="A",
            date_start=date(2026, 7, 1),
            date_end=date(2026, 7, 1),
        )
    with pytest.raises(ValidationError, match="only valid when approving"):
        LeaveDecisionRequest(decision="review", ballot_approved=True)


def test_positive_duty_does_not_block_same_rank_peak_leave(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    rows = _rows(active_hca_count=2)
    rows["calendar_days"] = [{
        "facility_id": None,
        "date": "2026-09-25",
        "day_type": "statutory_holiday",
        "holiday_name": "Mid-Autumn Festival",
    }]
    rows["leave_requests"] = [{
        "id": "working-preference",
        "facility_id": "facility-1",
        "staff_id": "staff-extra-1",
        "category": "duty",
        "leave_type": "duty_request",
        "requested_shift_type": "A",
        "date_start": "2026-09-25",
        "date_end": "2026-09-25",
        "status": "approved",
        "created_at": "2026-07-01T08:00:00Z",
    }]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")

    row = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="AL",
        date_start=FixedDate(2026, 9, 25),
        date_end=FixedDate(2026, 9, 25),
    )

    assert {
        issue["code"] for issue in row["policy_result_json"]["issues"]
    } == {"high_demand_ballot_deadline"}


def test_locked_night_blocks_duty_request_but_allows_true_swap(monkeypatch):
    monkeypatch.setattr(leave, "Date", FixedDate)
    rows = _rows()
    rows["shift_assignments"] = [{
        "facility_id": "facility-1",
        "staff_id": "staff-1",
        "status": "assigned",
        "shift": {
            "date": "2026-09-03",
            "shift_type": "AN",
            "is_working": True,
            "version": {"version_type": "manual", "status": "draft"},
        },
    }]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")

    duty = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="duty_request",
        requested_shift_type="P",
        date_start=FixedDate(2026, 9, 3),
        date_end=FixedDate(2026, 9, 3),
    )
    swap = leave.create_request(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="shift_swap",
        requested_shift_type="P",
        date_start=FixedDate(2026, 9, 3),
        date_end=FixedDate(2026, 9, 3),
    )

    assert {
        issue["code"] for issue in duty["policy_result_json"]["issues"]
    } == {"preassigned_night_locked"}
    assert swap["policy_result_json"]["issues"] == []


def test_approved_duty_request_is_not_reported_as_leave_unavailability():
    rows = _rows()
    rows["leave_requests"] = [
        {
            "id": "duty",
            "facility_id": "facility-1",
            "staff_id": "staff-1",
            "leave_type": "duty_request",
            "requested_shift_type": "AN",
            "date_start": "2026-09-03",
            "date_end": "2026-09-03",
            "status": "approved",
        },
        {
            "id": "annual-leave",
            "facility_id": "facility-1",
            "staff_id": "staff-1",
            "leave_type": "AL",
            "date_start": "2026-09-04",
            "date_end": "2026-09-04",
            "status": "approved",
        },
    ]
    client = FakeClient(rows, now="2026-07-01T09:00:00Z")

    unavailable = leave.approved_leave_dates(
        client,
        "facility-1",
        date(2026, 9, 1),
        date(2026, 9, 30),
    )

    assert unavailable == {("staff-1", "2026-09-04")}
