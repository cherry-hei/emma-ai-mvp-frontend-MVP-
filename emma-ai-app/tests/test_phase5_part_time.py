"""Focused Phase 5 part-time work-pattern tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from emma_core.constants import PlanMode, SolveStatus
from emma_core.services.validation import (
    RosterSnapshot,
    evaluate_part_time_rules,
)
from emma_core.solver import (
    DemandSlot,
    SolverInputs,
    SolverLimits,
    StaffInput,
    WorkPatternInput,
    solve_plan,
)
from emma_core.solver.model import eligible


def _shift(shift_id: str, day: date, start: str, end: str, *,
           shift_type: str = "PT", working: bool = True) -> dict:
    return {
        "id": shift_id,
        "date": day.isoformat(),
        "shift_type": shift_type,
        "start_time": start,
        "end_time": end,
        "cross_midnight": False,
        "is_working": working,
    }


def _assignment(assignment_id: str, shift_id: str) -> dict:
    return {
        "id": assignment_id,
        "shift_id": shift_id,
        "staff_id": "pt-1",
        "role": "HCA",
        "status": "assigned",
        "is_agency": False,
    }


def _snapshot(start: date, end: date, shifts: list[dict]) -> RosterSnapshot:
    return RosterSnapshot(
        facility_id="facility-1",
        roster_version_id="version-1",
        period_id="period-1",
        period_start=start,
        period_end=end,
        facility={"id": "facility-1", "code": "B"},
        staff=({
            "id": "pt-1",
            "rank": "HCA",
            "employment_type": "local_pt",
            "status": "active",
        },),
        shifts=tuple(shifts),
        assignments=tuple(
            _assignment(f"assignment-{index}", shift["id"])
            for index, shift in enumerate(shifts)
        ),
        rule_definitions=({
            "id": "agency-policy",
            "facility_id": "facility-1",
            "rule_code": "agency_limits",
            "severity": "hard",
            "active": True,
            "effective_from": "2026-01-01",
            "config_version": 1,
            "config_json": {
                "part_time_policy": {
                    "employment_types": ["local_pt"],
                    "required_start": "09:00",
                    "required_end": "18:00",
                    "allowed_weekdays": [0, 1, 3, 5],
                    "weekly_work_days": {"min": 4, "max": 4},
                },
            },
        },),
    )


def test_home_b_pt_fixed_window_weekdays_and_four_day_week():
    monday = date(2026, 7, 6)
    valid_days = (monday, monday + timedelta(days=1),
                  monday + timedelta(days=3), monday + timedelta(days=5))
    valid = [
        _shift(f"valid-{index}", day, "09:00", "18:00")
        for index, day in enumerate(valid_days)
    ]

    assert evaluate_part_time_rules(
        _snapshot(monday, monday + timedelta(days=6), valid)
    ) == []

    invalid = [
        _shift("monday", monday, "09:30", "18:00"),
        _shift("tuesday", monday + timedelta(days=1), "09:00", "18:00"),
        _shift("wednesday", monday + timedelta(days=2), "09:00", "18:00"),
        _shift("thursday", monday + timedelta(days=3), "09:00", "18:00"),
    ]
    violations = evaluate_part_time_rules(
        _snapshot(monday, monday + timedelta(days=6), invalid)
    )

    assert len(violations) == 2
    assert {row["message"] for row in violations} == {
        "Part-time staff is assigned on a prohibited weekday.",
        "Part-time shift does not match the required fixed hours.",
    }


def test_approved_leave_credits_pt_minimum_without_permitting_extra_work():
    monday = date(2026, 7, 6)
    shifts = [
        _shift("monday", monday, "09:00", "18:00"),
        _shift("tuesday", monday + timedelta(days=1), "09:00", "18:00"),
        _shift("thursday", monday + timedelta(days=3), "09:00", "18:00"),
    ]
    snapshot = replace(
        _snapshot(monday, monday + timedelta(days=6), shifts),
        leave_requests=({
            "id": "approved-al",
            "staff_id": "pt-1",
            "leave_type": "AL",
            "date_start": (monday + timedelta(days=5)).isoformat(),
            "date_end": (monday + timedelta(days=5)).isoformat(),
            "status": "approved",
        },),
    )

    assert evaluate_part_time_rules(snapshot) == []


def test_leave_on_prohibited_weekday_does_not_credit_home_b_minimum():
    monday = date(2026, 7, 6)
    shifts = [
        _shift("monday", monday, "09:00", "18:00"),
        _shift("tuesday", monday + timedelta(days=1), "09:00", "18:00"),
        _shift("thursday", monday + timedelta(days=3), "09:00", "18:00"),
    ]
    snapshot = replace(
        _snapshot(monday, monday + timedelta(days=6), shifts),
        leave_requests=({
            "id": "sunday-al",
            "staff_id": "pt-1",
            "leave_type": "AL",
            "date_start": (monday + timedelta(days=6)).isoformat(),
            "date_end": (monday + timedelta(days=6)).isoformat(),
            "status": "approved",
        },),
    )

    violations = evaluate_part_time_rules(snapshot)

    assert [row["message"] for row in violations] == [
        "Part-time weekly work-day requirement is not satisfied."
    ]
    assert violations[0]["details"]["credited_leave_days"] == 0


def test_home_b_partial_calendar_week_requires_each_in_period_duty_day():
    wednesday = date(2026, 7, 1)
    thursday = wednesday + timedelta(days=1)
    saturday = wednesday + timedelta(days=3)
    snapshot = _snapshot(
        wednesday,
        wednesday + timedelta(days=4),
        [_shift("thursday", thursday, "09:00", "18:00")],
    )

    [violation] = evaluate_part_time_rules(snapshot)
    assert violation["details"]["minimum_work_days"] == 2

    credited = replace(
        snapshot,
        leave_requests=({
            "id": "saturday-al",
            "staff_id": "pt-1",
            "leave_type": "AL",
            "date_start": saturday.isoformat(),
            "date_end": saturday.isoformat(),
            "status": "approved",
        },),
    )
    assert evaluate_part_time_rules(credited) == []


def test_cl_roster_marker_cannot_share_a_day_with_work():
    monday = date(2026, 7, 6)
    valid_days = (
        monday,
        monday + timedelta(days=1),
        monday + timedelta(days=3),
        monday + timedelta(days=5),
    )
    shifts = [
        _shift(f"work-{index}", day, "09:00", "18:00")
        for index, day in enumerate(valid_days)
    ]
    shifts.append(_shift(
        "overlapping-cl",
        monday,
        "",
        "",
        shift_type="CL",
        working=False,
    ))

    violations = evaluate_part_time_rules(
        _snapshot(monday, monday + timedelta(days=6), shifts)
    )

    assert [row["message"] for row in violations] == [
        "Compensatory leave cannot overlap a working assignment."
    ]


def test_home_a_pt_fortnight_and_saturday_cl():
    start = date(2026, 7, 6)  # Monday
    end = date(2026, 7, 20)
    working_days = [
        start + timedelta(days=offset)
        for offset in range(14)
        if offset not in {6, 7, 13}  # 6-day week, then 5-day week
    ]
    shifts = [
        _shift(f"work-{index}", day, "09:00", "17:48")
        for index, day in enumerate(working_days)
    ]
    shifts.extend([
        _shift("cl-after-first-saturday", date(2026, 7, 13), "", "",
               shift_type="CL", working=False),
        _shift("cl-after-second-saturday", date(2026, 7, 20), "", "",
               shift_type="CL", working=False),
    ])
    snapshot = _snapshot(start, end, shifts)
    snapshot.rule_definitions[0]["config_json"]["part_time_policy"] = {
        "employment_types": ["local_pt"],
        "required_start": "09:00",
        "required_end": "17:48",
        "allowed_weekdays": [],
        "weekly_work_days": {"min": 5, "max": 6},
        "fortnightly_work_days": {"min": 11, "max": 11},
        "saturday_requires_weekday_cl": True,
    }

    assert evaluate_part_time_rules(snapshot) == []

    without_second_cl = replace(
        snapshot,
        shifts=tuple(row for row in snapshot.shifts
                     if row["id"] != "cl-after-second-saturday"),
        assignments=tuple(row for row in snapshot.assignments
                          if row["shift_id"] != "cl-after-second-saturday"),
    )
    violations = evaluate_part_time_rules(without_second_cl)

    assert len(violations) == 1
    assert violations[0]["details"]["required_leave_type"] == "CL"


def test_boundary_saturday_requires_a_deferred_cl_debt():
    saturday = date(2026, 7, 18)
    snapshot = _snapshot(
        saturday,
        saturday,
        [_shift("saturday", saturday, "09:00", "17:48")],
    )
    snapshot.rule_definitions[0]["config_json"]["part_time_policy"] = {
        "employment_types": ["local_pt"],
        "required_start": "09:00",
        "required_end": "17:48",
        "allowed_weekdays": [],
        "saturday_requires_weekday_cl": True,
    }

    [violation] = evaluate_part_time_rules(snapshot)
    assert violation["details"]["eligible_dates"] == []

    deferred = replace(
        snapshot,
        future_debts=({
            "staff_id": "pt-1",
            "debt_type": "CL",
            "status": "open",
            "details_json": {
                "source_roster_version_id": "version-1",
                "source_saturday": saturday.isoformat(),
            },
        },),
    )
    assert evaluate_part_time_rules(deferred) == []


def _slot(slot_id: str, day: date) -> DemandSlot:
    return DemandSlot(
        id=slot_id,
        date=day,
        day_index=(day - date(2026, 7, 6)).days,
        shift_type="PT",
        start_min=9 * 60,
        end_min=18 * 60,
        cross_midnight=False,
        duration_min=9 * 60,
        segments=((9 * 60, 18 * 60, False),),
        required_rank="HCA",
        agency_allowed=False,
    )


def test_solver_enforces_pt_eligibility_and_exact_week():
    monday = date(2026, 7, 6)
    pattern = WorkPatternInput(
        allowed_weekdays=frozenset({0, 1, 3, 5}),
        required_shift_window=(9 * 60, 18 * 60),
        weekly_work_days=(4, 4),
    )
    staff = StaffInput(
        id="pt-1",
        rank="HCA",
        employment_type="local_pt",
        min_rest_minutes=0,
        contracted_period_minutes=10_000,
        work_pattern=pattern,
    )
    valid_days = [
        monday,
        monday + timedelta(days=1),
        monday + timedelta(days=3),
        monday + timedelta(days=5),
    ]
    inputs = SolverInputs(
        facility_id="facility-1",
        period_id="period-1",
        period_start=monday,
        period_end=monday + timedelta(days=6),
        staff=(staff,),
        demand=tuple(
            _slot(f"slot-{index}", day)
            for index, day in enumerate(valid_days)
        ),
    )

    assert eligible(staff, inputs.demand[0], inputs)
    disallowed = _slot("wednesday", monday + timedelta(days=2))
    assert not eligible(staff, disallowed, inputs)

    result = solve_plan(
        inputs,
        PlanMode.C,
        SolverLimits(max_seconds=5, workers=1, seed=42),
    )
    assert result.status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}
    assert {
        assignment.staff_id for assignment in result.assignments
    } == {"pt-1"}

    short_inputs = SolverInputs(
        **{
            "facility_id": inputs.facility_id,
            "period_id": inputs.period_id,
            "period_start": inputs.period_start,
            "period_end": inputs.period_end,
            "staff": inputs.staff,
            "demand": inputs.demand[:3],
        }
    )
    assert solve_plan(
        short_inputs,
        PlanMode.C,
        SolverLimits(max_seconds=5, workers=1, seed=42),
    ).status == SolveStatus.INFEASIBLE

    disallowed_leave_inputs = SolverInputs(
        facility_id=inputs.facility_id,
        period_id=inputs.period_id,
        period_start=inputs.period_start,
        period_end=inputs.period_end,
        staff=inputs.staff,
        demand=inputs.demand[:3],
        leave_unavailable=frozenset({
            ("pt-1", monday + timedelta(days=6)),
        }),
    )
    assert solve_plan(
        disallowed_leave_inputs,
        PlanMode.C,
        SolverLimits(max_seconds=5, workers=1, seed=42),
    ).status == SolveStatus.INFEASIBLE
