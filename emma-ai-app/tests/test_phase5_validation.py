"""Pure fixture tests for the deterministic Phase 5 validation engine."""
from __future__ import annotations

from datetime import date

from emma_core.services.validation import (
    RosterSnapshot,
    _snapshot_digest,
    evaluate_agency_rules,
    evaluate_core_constraints,
    evaluate_leave_rules,
    evaluate_night_rules,
)


def _snapshot(**overrides) -> RosterSnapshot:
    values = {
        "facility_id": "facility-1",
        "roster_version_id": "version-1",
        "period_id": "period-1",
        "period_start": date(2026, 7, 1),
        "period_end": date(2026, 7, 31),
        "facility": {"id": "facility-1", "code": "B"},
    }
    values.update(overrides)
    return RosterSnapshot(**values)


def _shift(
    shift_id: str,
    day: str,
    shift_type: str,
    start: str,
    end: str,
    **extra,
) -> dict:
    return {
        "id": shift_id,
        "date": day,
        "shift_type": shift_type,
        "start_time": start,
        "end_time": end,
        "cross_midnight": end <= start,
        "is_working": True,
        **extra,
    }


def _assignment(
    assignment_id: str,
    shift_id: str,
    staff_id: str,
    role: str,
    **extra,
) -> dict:
    return {
        "id": assignment_id,
        "shift_id": shift_id,
        "staff_id": staff_id,
        "role": role,
        "status": "assigned",
        "is_agency": False,
        **extra,
    }


def test_core_constraints_are_deterministic_and_auditable():
    staff = ({
        "id": "staff-1",
        "rank": "HCA",
        "employment_type": "local_ft",
        "is_audited_for_medication": False,
    },)
    shifts = (
        _shift(
            "shift-1",
            "2026-07-01",
            "A",
            "07:00",
            "15:00",
            required_rank="RN",
            required_count=2,
            requires_medication=True,
        ),
        _shift("shift-2", "2026-07-01", "P", "08:00", "16:00"),
        _shift("shift-3", "2026-07-02", "A", "01:00", "09:00"),
    )
    assignments = (
        _assignment("a-1", "shift-1", "staff-1", "RN"),
        _assignment("a-2", "shift-2", "staff-1", "HCA"),
        _assignment("a-3", "shift-3", "staff-1", "HCA"),
    )
    snapshot = _snapshot(
        period_end=date(2026, 7, 7),
        shifts=shifts,
        assignments=assignments,
        staff=staff,
        contracts=({
            "staff_id": "staff-1",
            "min_rest_minutes": 660,
            "max_weekly_hours": 8,
            "allowed_shift_types": ["A", "P"],
        },),
        leave_requests=({
            "id": "leave-1",
            "staff_id": "staff-1",
            "leave_type": "AL",
            "date_start": "2026-07-01",
            "date_end": "2026-07-01",
            "status": "approved",
        },),
    )

    violations = evaluate_core_constraints(snapshot)
    codes = {row["rule_code"] for row in violations}

    assert {
        "required_coverage",
        "assignment_eligibility",
        "approved_leave_unavailable",
        "one_staff_no_overlap",
        "min_rest",
        "max_hours",
    } <= codes
    assert all("details" in row and row["severity"] == "hard" for row in violations)


def test_cross_midnight_assignment_conflicts_with_next_day_approved_leave():
    snapshot = _snapshot(
        period_end=date(2026, 7, 2),
        shifts=(
            _shift("night", "2026-07-01", "N", "21:00", "07:00"),
        ),
        assignments=(
            _assignment("night-cell", "night", "staff-1", "HW"),
        ),
        staff=({
            "id": "staff-1",
            "rank": "HW",
            "employment_type": "local_ft",
        },),
        leave_requests=({
            "id": "leave-1",
            "staff_id": "staff-1",
            "leave_type": "AL",
            "date_start": "2026-07-02",
            "date_end": "2026-07-02",
            "status": "approved",
        },),
    )

    violations = evaluate_core_constraints(snapshot)

    conflict = next(
        row for row in violations
        if row["rule_code"] == "approved_leave_unavailable"
    )
    assert conflict["date"] == "2026-07-02"
    assert conflict["details"]["overlap_dates"] == ["2026-07-02"]


def test_snapshot_digest_is_independent_of_database_row_order():
    first = _snapshot(
        shifts=(
            _shift("b", "2026-07-02", "P", "13:00", "21:00"),
            _shift("a", "2026-07-01", "A", "07:00", "15:00"),
        ),
    )
    second = _snapshot(shifts=tuple(reversed(first.shifts)))

    assert _snapshot_digest(first) == _snapshot_digest(second)


def test_night_chain_limits_and_next_period_cooldown():
    shifts = tuple(
        _shift(
            f"night-{index}",
            day,
            shift_type,
            "21:00",
            "07:00",
        )
        for index, (day, shift_type) in enumerate((
            ("2026-07-01", "N"),
            ("2026-07-10", "AN"),
            ("2026-07-20", "N"),
        ), start=1)
    )
    assignments = tuple(
        _assignment(f"a-{index}", shift["id"], "nurse-1", "EN")
        for index, shift in enumerate(shifts, start=1)
    )
    snapshot = _snapshot(
        shifts=shifts,
        assignments=assignments,
        staff=({
            "id": "nurse-1",
            "rank": "EN",
            "employment_type": "local_ft",
        },),
        rule_definitions=({
            "id": "night-rule",
            "facility_id": "facility-1",
            "rule_code": "night_chain",
            "active": True,
            "config_version": 1,
            "config_json": {
                "night_shift_types": ["N", "AN"],
                "an_monthly_limit": 1,
                "nurse_night_monthly_limit": 2,
            },
        },),
        future_debts=({
            "staff_id": "nurse-1",
            "debt_type": "NIGHT_COOLDOWN",
            "status": "open",
            "due_period_id": "period-1",
        },),
    )

    violations = evaluate_night_rules(snapshot)
    codes = [row["rule_code"] for row in violations]

    assert "night_chain" in codes
    assert "night_monthly_limit" in codes
    assert "night_cooldown" in codes
    assert all(row.get("rule_definition_id") == "night-rule" for row in violations)


def test_rule_definition_severity_controls_policy_violation_severity():
    snapshot = _snapshot(
        period_end=date(2026, 7, 3),
        shifts=(
            _shift("night", "2026-07-01", "N", "21:00", "07:00"),
        ),
        assignments=(
            _assignment("night-cell", "night", "staff-1", "HW"),
        ),
        staff=({
            "id": "staff-1",
            "rank": "HW",
            "employment_type": "local_ft",
        },),
        rule_definitions=({
            "id": "soft-night-rule",
            "facility_id": "facility-1",
            "rule_code": "night_chain",
            "severity": "soft",
            "active": True,
            "effective_from": "2026-01-01",
            "config_version": 1,
            "config_json": {},
        },),
    )

    violations = evaluate_night_rules(snapshot)

    assert violations
    assert {row["severity"] for row in violations} == {"soft"}


def test_external_workforce_bans_and_caps_use_staff_employment_type():
    shifts = (
        _shift("night", "2026-07-01", "N", "21:00", "07:00"),
        _shift("day", "2026-07-01", "A", "07:00", "15:00"),
    )
    snapshot = _snapshot(
        shifts=shifts,
        assignments=(
            _assignment("agency-a", "night", "agency-1", "HW"),
            _assignment("internal-a", "day", "internal-1", "HW"),
        ),
        staff=(
            {"id": "agency-1", "rank": "HW", "employment_type": "agency"},
            {"id": "internal-1", "rank": "HW", "employment_type": "local_ft"},
        ),
        calendar_days=({
            "date": "2026-07-01",
            "facility_id": "facility-1",
            "is_agency_allowed": False,
        },),
        rule_definitions=({
            "id": "agency-rule",
            "facility_id": "facility-1",
            "rule_code": "agency_limits",
            "active": True,
            "config_version": 1,
            "config_json": {
                "agency_employment_types": ["agency", "outsource", "casual"],
                "banned_shift_types": ["N"],
                "period_ratio_cap": 0.5,
                "daily_rank_caps": {},
            },
        },),
    )

    violations = evaluate_agency_rules(snapshot)

    assert {row["rule_code"] for row in violations} == {
        "agency_ban",
        "agency_cap",
    }
    assert all(row["rule_definition_id"] == "agency-rule" for row in violations)


def test_pending_request_cannot_make_an_approved_roster_unpublishable():
    snapshot = _snapshot(
        period_end=date(2026, 7, 7),
        facility={"id": "facility-1", "code": "A"},
        staff=({
            "id": "staff-1",
            "rank": "HCA",
            "employment_type": "local_ft",
            "status": "active",
        },),
        leave_requests=(
            {
                "id": "approved-do",
                "staff_id": "staff-1",
                "leave_type": "DO",
                "date_start": "2026-07-01",
                "date_end": "2026-07-04",
                "status": "approved",
            },
            {
                "id": "pending-do",
                "staff_id": "staff-1",
                "leave_type": "DO",
                "date_start": "2026-07-05",
                "date_end": "2026-07-05",
                "status": "pending",
            },
        ),
    )

    assert evaluate_leave_rules(snapshot) == []


def test_fulfilled_night_duty_request_is_not_treated_as_leave():
    snapshot = _snapshot(
        period_end=date(2026, 7, 3),
        shifts=(
            _shift("night", "2026-07-01", "AN", "21:00", "07:00"),
        ),
        assignments=(
            _assignment("night-cell", "night", "staff-1", "HCA"),
        ),
        staff=({
            "id": "staff-1",
            "rank": "HCA",
            "employment_type": "local_ft",
            "status": "active",
        },),
        leave_requests=({
            "id": "requested-night",
            "staff_id": "staff-1",
            "leave_type": "duty_request",
            "requested_shift_type": "AN",
            "date_start": "2026-07-01",
            "date_end": "2026-07-01",
            "status": "approved",
        },),
    )

    assert evaluate_leave_rules(snapshot) == []


def test_soft_leave_policy_is_audited_without_blocking():
    snapshot = _snapshot(
        period_end=date(2026, 7, 7),
        staff=({
            "id": "staff-1",
            "rank": "HCA",
            "employment_type": "local_ft",
            "status": "active",
        },),
        leave_requests=({
            "id": "five-days",
            "staff_id": "staff-1",
            "leave_type": "DO",
            "date_start": "2026-07-01",
            "date_end": "2026-07-05",
            "status": "approved",
        },),
        rule_definitions=({
            "id": "soft-leave-rule",
            "facility_id": "facility-1",
            "rule_code": "leave_rules",
            "severity": "soft",
            "active": True,
            "effective_from": "2026-01-01",
            "config_version": 1,
            "config_json": {},
        },),
    )

    violations = evaluate_leave_rules(snapshot)

    assert len(violations) == 1
    assert violations[0]["rule_code"] == "leave_quota"
    assert violations[0]["severity"] == "soft"


def test_combined_do_cl_balance_rule_is_rechecked():
    snapshot = _snapshot(
        staff=({
            "id": "staff-1",
            "rank": "HCA",
            "employment_type": "local_ft",
            "status": "active",
        },),
        leave_requests=({
            "id": "leave-1",
            "staff_id": "staff-1",
            "leave_type": "CL",
            "date_start": "2026-07-02",
            "date_end": "2026-07-05",
            "created_at": "2026-06-01T09:00:00Z",
            "status": "approved",
        },),
        leave_balances=({
            "id": "balance-1",
            "staff_id": "staff-1",
            "leave_type": "CL",
            "opening_balance": 2,
            "accrued": 2,
            "carried": 1,
            "used": 0,
        },),
        rule_definitions=({
            "id": "leave-rule",
            "facility_id": "facility-1",
            "rule_code": "leave_rules",
            "active": True,
            "config_version": 1,
            "config_json": {"max_do_cl_balance": 3},
        },),
    )

    violations = evaluate_leave_rules(snapshot)

    assert {row["rule_code"] for row in violations} == {"leave_balance"}
    assert all(row["rule_definition_id"] == "leave-rule" for row in violations)


def test_approved_requests_cannot_overbook_configured_leave_entitlement():
    snapshot = _snapshot(
        period_end=date(2026, 7, 7),
        staff=({
            "id": "staff-1",
            "rank": "HCA",
            "employment_type": "local_ft",
            "status": "active",
        },),
        leave_requests=(
            {
                "id": "leave-1",
                "staff_id": "staff-1",
                "leave_type": "AL",
                "date_start": "2026-07-02",
                "date_end": "2026-07-02",
                "status": "approved",
            },
            {
                "id": "leave-2",
                "staff_id": "staff-1",
                "leave_type": "AL",
                "date_start": "2026-07-03",
                "date_end": "2026-07-03",
                "status": "approved",
            },
        ),
        leave_balances=({
            "id": "balance-1",
            "staff_id": "staff-1",
            "leave_type": "AL",
            "opening_balance": 1,
            "accrued": 0,
            "carried": 0,
            "used": 0,
        },),
    )

    violations = evaluate_leave_rules(snapshot)

    overbooked = next(
        row for row in violations
        if row["rule_code"] == "leave_balance"
        and row["details"].get("leave_type") == "AL"
    )
    assert overbooked["details"]["approved_days"] == 2
    assert overbooked["details"]["entitlement_days"] == 1
