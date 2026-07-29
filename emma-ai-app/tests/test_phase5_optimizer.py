"""Focused offline coverage for Phase 5 optimizer policy alignment."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from emma_core.constants import PlanMode
from emma_core.models import OptimizeRequest
from emma_core.services import optimize
from emma_core.solver import (
    DemandSlot,
    LockedAssignment,
    RatioRuleInput,
    ResidentCountInput,
    SolverInputs,
    SolverLimits,
    StaffInput,
    solve_plan,
)
from emma_core.solver.model import eligible
from emma_core.solver.inputs import AgencyLimitsInput, PreferenceInput

from tests.test_optimize_service import build_store


LIM = SolverLimits(workers=1, seed=42, max_seconds=5)


def _staff(staff_id: str, rank: str = "CW", **changes) -> StaffInput:
    values = {
        "id": staff_id,
        "rank": rank,
        "employment_type": "local_ft",
        "contracted_period_minutes": 10_000,
        "min_rest_minutes": 0,
    }
    values.update(changes)
    return StaffInput(**values)


def _slot(slot_id: str, day_index: int, shift_type: str = "A", *,
          start: int = 420, end: int = 900, cross: bool = False,
          rank: str = "CW", unit_id: str | None = None,
          agency_allowed: bool = False) -> DemandSlot:
    duration = (1440 - start + end) if cross or end <= start else end - start
    return DemandSlot(
        id=slot_id,
        date=date(2026, 7, 1 + day_index),
        day_index=day_index,
        shift_type=shift_type,
        start_min=start,
        end_min=end,
        cross_midnight=cross,
        duration_min=duration,
        segments=((start, end, cross),),
        unit_id=unit_id,
        required_rank=rank,
        agency_allowed=agency_allowed,
    )


def _inputs(staff, demand, *, days=3, **changes) -> SolverInputs:
    values = {
        "facility_id": "f1",
        "period_id": "p1",
        "period_start": date(2026, 7, 1),
        "period_end": date(2026, 7, days),
        "staff": tuple(staff),
        "demand": tuple(demand),
        "night_shift_types": frozenset({"N", "AN"}),
    }
    values.update(changes)
    return SolverInputs(**values)


def test_loader_maps_approved_leave_and_priority_preferences():
    store = build_store()
    store.data["leave_requests"] = [
        {
            "id": "approved",
            "facility_id": "f1",
            "staff_id": "cw1",
            "date_start": "2026-07-01",
            "date_end": "2026-07-02",
            "status": "approved",
            "priority": "normal",
        },
        {
            "id": "pending",
            "facility_id": "f1",
            "staff_id": "cw2",
            "date_start": "2026-07-02",
            "date_end": "2026-07-02",
            "leave_type": "duty_request",
            "requested_shift_type": "P",
            "status": "pending",
            "priority": "urgent",
            "policy_result_json": {"priority_weight": 85},
        },
        {
            "id": "approved-duty",
            "facility_id": "f1",
            "staff_id": "cw2",
            "date_start": "2026-07-01",
            "date_end": "2026-07-01",
            "leave_type": "duty_request",
            "requested_shift_type": "A",
            "status": "approved",
            "policy_result_json": {"priority_weight": 40},
        },
    ]

    loaded = optimize.load_inputs(store, "f1", "p1")

    assert ("cw1", date(2026, 7, 1)) in loaded.leave_unavailable
    assert ("cw1", date(2026, 7, 2)) in loaded.leave_unavailable
    assert ("cw2", date(2026, 7, 1)) not in loaded.leave_unavailable
    assert set(loaded.preferences) == {
        optimize.PreferenceInput(
            staff_id="cw2",
            date=date(2026, 7, 2),
            prefer_working=True,
            shift_type="P",
            weight=85,
        ),
        optimize.PreferenceInput(
            staff_id="cw2",
            date=date(2026, 7, 1),
            prefer_working=True,
            shift_type="A",
            weight=40,
        ),
    }


def test_rank_substitution_and_external_ban_are_hard_eligibility():
    slot = _slot("cw", 0, agency_allowed=False)
    inputs = _inputs([], [slot], days=1)

    assert eligible(_staff("rn", "RN"), slot, inputs)
    assert not eligible(
        _staff("agency", employment_type="agency"), slot, inputs
    )


def test_preference_weight_uses_policy_result_then_domain_fallback():
    assert optimize._preference_weight({
        "leave_type": "DO",
        "policy_result_json": {"priority_weight": 95},
    }) == 95
    assert optimize._preference_weight({
        "leave_type": "CL",
    }) == 70
    assert optimize._preference_weight({
        "leave_type": "DO",
        "reason": "Medical follow-up",
    }) == 80
    assert optimize._preference_weight({
        "leave_type": "duty_request",
    }) == 40


def test_pending_preference_priority_changes_the_selected_staff():
    slot = _slot("a", 0, agency_allowed=False)
    result = solve_plan(
        _inputs(
            [_staff("low"), _staff("urgent")],
            [slot],
            days=1,
            preferences=(
                PreferenceInput("low", date(2026, 7, 1), True, "A", 1),
                PreferenceInput("urgent", date(2026, 7, 1), True, "A", 8),
            ),
        ),
        PlanMode.B,
        LIM,
    )

    assert any(a.staff_id == "urgent" for a in result.assignments)
    assert all(a.staff_id != "low" for a in result.assignments)


def test_ratio_is_minute_aware_unit_scoped_and_uses_actual_rank_weight():
    rn = _staff("rn", "RN")
    early = _slot(
        "early", 0, start=420, end=480, rank="CW", unit_id="u1"
    )
    rule = RatioRuleInput(
        window_start_min=420,
        window_end_min=540,
        unit_id="u1",
        min_staff_any_rank=1,
        counted_ranks=frozenset({"RN"}),
        rank_weights=(("RN", 50),),
    )
    result = solve_plan(
        _inputs(
            [rn],
            [early],
            days=1,
            ratio_rules=(rule,),
            resident_counts=(ResidentCountInput(date(2026, 7, 1), 1, "u1"),),
        ),
        PlanMode.C,
        LIM,
    )

    assert any(a.staff_id == "rn" for a in result.assignments)
    # RN contributes 0.5 equivalent head and is absent after 08:00.
    assert result.kpi.ratio_breaches == 1
    assert result.hard_violation_count >= 1


def test_fractional_hw_ratio_compares_resident_equivalents_before_ceiling():
    hw = _staff("hw", "HW")
    slot = _slot("hw-day", 0, rank="HW", unit_id="u1")
    rule = RatioRuleInput(
        window_start_min=420,
        window_end_min=900,
        unit_id="u1",
        ratio_residents_per_staff=60,
        counted_ranks=frozenset({"RN", "EN", "HW"}),
        rank_weights=(("RN", 100), ("EN", 100), ("HW", 67)),
    )
    result = solve_plan(
        _inputs(
            [hw],
            [slot],
            days=1,
            ratio_rules=(rule,),
            resident_counts=(ResidentCountInput(date(2026, 7, 1), 40, "u1"),),
        ),
        PlanMode.C,
        LIM,
    )

    assert result.kpi.ratio_breaches == 0
    assert result.hard_violation_count == 0


def test_night_chain_and_monthly_nurse_limit_are_hard():
    cooldown = _staff(
        "cooldown",
        "RN",
        is_audited_for_medication=True,
        night_cooldown=True,
    )
    cooldown_night = _slot(
        "cooldown-night", 0, "7P", start=1140, end=420,
        cross=True, rank="RN"
    )
    cooldown_result = solve_plan(
        _inputs(
            [cooldown],
            [cooldown_night],
            days=1,
            night_shift_types=frozenset({"N", "AN", "7P"}),
        ),
        PlanMode.C,
        LIM,
    )
    assert all(a.staff_id != "cooldown" for a in cooldown_result.assignments)

    nurse = _staff(
        "rn",
        "RN",
        is_audited_for_medication=True,
        nurse_night_monthly_limit=2,
    )
    night = _slot(
        "n0", 0, "7P", start=1140, end=420, cross=True, rank="RN"
    )
    next_day = _slot("a1", 1, rank="RN")
    result = solve_plan(
        _inputs(
            [nurse],
            [night, next_day],
            days=3,
            locks=(LockedAssignment("rn", "n0"),),
            night_shift_types=frozenset({"N", "AN", "7P"}),
        ),
        PlanMode.C,
        LIM,
    )

    assigned = {a.slot_id for a in result.assignments if a.staff_id == "rn"}
    assert "n0" in assigned
    assert "a1" not in assigned

    imported = _staff(
        "rn",
        "RN",
        employment_type="imported_labor",
        is_audited_for_medication=True,
        nurse_night_monthly_limit=2,
    )
    nights = [
        _slot(f"n{index}", index * 2, "N", start=1290, end=420,
              cross=True, rank="RN")
        for index in range(3)
    ]
    limited = solve_plan(
        _inputs([imported], nights, days=5), PlanMode.C, LIM
    )
    assert sum(a.staff_id == "rn" for a in limited.assignments) <= 2


def test_home_b_imported_long_shift_gets_1_3_cost_weight():
    store = build_store()
    store.data["facilities"][0]["code"] = "B"
    store.data["staff"][1]["employment_type"] = "imported_labor"
    store.data["rule_definitions"] = [{
        "id": "agency-policy",
        "facility_id": "f1",
        "rule_code": "agency_limits",
        "active": True,
        "config_version": 1,
        "config_json": {
            "period_ratio_cap": 0.4,
            "daily_rank_caps": {"RN|EN|HW": 1},
            "monthly_shift_caps": {"A": 3},
            "vacancy_cap": {
                "enabled": True,
                "standard_do_days": 1,
                "factor": 0.5,
            },
        },
    }]
    store.data["roi_settings"] = [{
        "facility_id": "f1",
        "vacancies_json": {"CW": 2},
    }]
    loaded = optimize.load_inputs(store, "f1", "p1")
    loaded_cw = next(staff for staff in loaded.staff if staff.id == "cw1")
    assert loaded_cw.long_shift_cost_scaled == 130
    assert loaded.agency_limits.period_ratio_cap_scaled == 400
    assert loaded.agency_limits.daily_rank_caps == (("RN|EN|HW", 1),)
    assert loaded.agency_limits.monthly_shift_caps == (("A", 3),)
    assert loaded.agency_limits.vacancy_period_cap == 1

    normal = _staff(
        "normal", employment_type="imported_labor",
        contracted_period_minutes=0,
    )
    weighted = _staff(
        "weighted", employment_type="imported_labor",
        contracted_period_minutes=0,
        long_shift_cost_scaled=130,
    )
    twelve_hours = _slot("long", 0, start=420, end=1140)

    base_result = solve_plan(
        _inputs([normal], [twelve_hours], days=1), PlanMode.A, LIM
    )
    weighted_result = solve_plan(
        _inputs([weighted], [twelve_hours], days=1), PlanMode.A, LIM
    )

    assert weighted_result.soft_penalty_total > base_result.soft_penalty_total


def test_agency_caps_cover_ratio_daily_monthly_and_vacancy_rules():
    internal = [
        _staff("local1", max_period_minutes=480),
        _staff("local2", max_period_minutes=480),
    ]
    external = [
        _staff("ext1", "HCA", employment_type="agency"),
        _staff("ext2", "HCA", employment_type="agency"),
    ]
    three_days = [
        _slot(f"a{index}", index, agency_allowed=True)
        for index in range(3)
    ]
    ratio_result = solve_plan(
        _inputs(
            internal + external,
            three_days,
            days=3,
            agency_limits=AgencyLimitsInput(period_ratio_cap_scaled=500),
        ),
        PlanMode.C,
        LIM,
    )
    external_ids = {"ext1", "ext2"}
    ratio_external = sum(
        assignment.is_agency or assignment.staff_id in external_ids
        for assignment in ratio_result.assignments
    )
    assert ratio_external <= 1

    two_required = _slot("two", 0, rank="CW", agency_allowed=True)
    two_required = replace(two_required, required_count=2)
    daily_result = solve_plan(
        _inputs(
            external,
            [two_required],
            days=1,
            agency_limits=AgencyLimitsInput(
                daily_rank_caps=(("CW|HCA", 1),),
            ),
        ),
        PlanMode.C,
        LIM,
    )
    assert sum(
        assignment.is_agency or assignment.staff_id in external_ids
        for assignment in daily_result.assignments
    ) <= 1

    monthly_result = solve_plan(
        _inputs(
            external,
            three_days[:2],
            days=2,
            agency_limits=AgencyLimitsInput(
                monthly_shift_caps=(("A", 1),),
            ),
        ),
        PlanMode.C,
        LIM,
    )
    assert sum(
        assignment.is_agency or assignment.staff_id in external_ids
        for assignment in monthly_result.assignments
    ) <= 1

    vacancy_result = solve_plan(
        _inputs(
            external,
            [three_days[0]],
            days=1,
            agency_limits=AgencyLimitsInput(vacancy_period_cap=0),
        ),
        PlanMode.C,
        LIM,
    )
    assert not any(
        assignment.is_agency or assignment.staff_id in external_ids
        for assignment in vacancy_result.assignments
    )


def test_agency_rank_caps_are_exact_and_monthly_caps_reset_by_calendar_month():
    external_rn = _staff("external-rn", "RN", employment_type="agency")
    cw_slot = _slot("cw", 0, rank="CW", agency_allowed=True)
    exact_group = solve_plan(
        _inputs(
            [external_rn],
            [cw_slot],
            days=1,
            agency_limits=AgencyLimitsInput(
                daily_rank_caps=(("CW|HCA", 0),),
            ),
        ),
        PlanMode.C,
        LIM,
    )
    assert any(a.staff_id == "external-rn" for a in exact_group.assignments)

    july_slot = replace(
        _slot("july", 0, agency_allowed=True),
        date=date(2026, 7, 31),
        day_index=0,
    )
    august_slot = replace(
        _slot("august", 1, agency_allowed=True),
        date=date(2026, 8, 1),
        day_index=1,
    )
    cross_month = SolverInputs(
        facility_id="f1",
        period_id="p1",
        period_start=date(2026, 7, 31),
        period_end=date(2026, 8, 1),
        staff=(
            _staff("external1", employment_type="agency"),
            _staff("external2", employment_type="agency"),
        ),
        demand=(july_slot, august_slot),
        agency_limits=AgencyLimitsInput(
            monthly_shift_caps=(("A", 1),),
        ),
    )
    monthly = solve_plan(cross_month, PlanMode.C, LIM)
    assert sum(
        assignment.staff_id in {"external1", "external2"}
        for assignment in monthly.assignments
    ) == 2


def test_writeback_links_agency_ledger_and_materialises_recovery_cells():
    agency_store = build_store()
    agency_store.data["rule_definitions"] = [{
        "id": "agency-policy",
        "facility_id": "f1",
        "rule_code": "agency_limits",
        "active": True,
        "config_version": 1,
        "config_json": {
            "banned_shift_types": [],
            "period_ratio_cap": 0,
            "daily_rank_caps": {},
            "monthly_shift_caps": {},
        },
    }]
    agency_store.data["staff"] = []
    agency_store.data["staff_contracts"] = []
    agency_store.data["shifts"] = [
        {
            "id": "only",
            "facility_id": "f1",
            "roster_version_id": "mv1",
            "date": "2026-07-01",
            "shift_type": "A",
            "start_time": "07:00:00",
            "end_time": "15:00:00",
            "cross_midnight": False,
            "unit_id": None,
            "required_rank": "CW",
            "required_count": 1,
            "is_working": True,
        }
    ]
    agency_store.data["shift_assignments"] = []
    response = optimize.run_optimization(
        agency_store,
        OptimizeRequest(facility_id="f1", period_id="p1", plan_mode=PlanMode.C),
    )
    assert response.roster_options[0].kpi.agency_count == 1
    ledger = agency_store.data["agency_assignments"][0]
    roster_assignment = next(
        row for row in agency_store.data["shift_assignments"]
        if row["id"] == ledger["shift_assignment_id"]
    )
    assert ledger["shift_id"] == roster_assignment["shift_id"]
    assert ledger["cost"] > 0

    recovery_store = build_store()
    recovery_store.data["facilities"][0]["code"] = "B"
    recovery_store.data["roster_periods"][0]["period_end"] = "2026-07-03"
    recovery_store.data["rule_definitions"] = [{
        "id": "night-policy",
        "facility_id": "f1",
        "rule_code": "night_chain",
        "active": True,
        "config_version": 1,
        "config_json": {
            "night_shift_types": ["N", "AN", "7P"],
        },
    }]
    recovery_store.data["staff"] = [
        row for row in recovery_store.data["staff"] if row["id"] == "cw1"
    ]
    recovery_store.data["staff_contracts"] = [
        row for row in recovery_store.data["staff_contracts"]
        if row["staff_id"] == "cw1"
    ]
    recovery_store.data["shifts"] = [{
        "id": "night",
        "facility_id": "f1",
        "roster_version_id": "mv1",
        "date": "2026-07-01",
        "shift_type": "7P",
        "start_time": "19:00:00",
        "end_time": "07:00:00",
        "cross_midnight": True,
        "unit_id": None,
        "required_rank": "CW",
        "required_count": 1,
        "is_working": True,
    }]
    recovery_store.data["shift_assignments"] = [{
        "id": "night-cell",
        "facility_id": "f1",
        "shift_id": "night",
        "staff_id": "cw1",
        "role": "CW",
        "status": "assigned",
        "is_agency": False,
    }]
    recovery_store.data["shift_definitions"] = [
        {
            "id": "sleep-def",
            "facility_id": "f1",
            "shift_type": "SLEEP",
            "start_time": None,
            "end_time": None,
            "cross_midnight": False,
            "paid_minutes": 0,
            "is_working": False,
        },
        {
            "id": "do-def",
            "facility_id": "f1",
            "shift_type": "DO",
            "start_time": None,
            "end_time": None,
            "cross_midnight": False,
            "paid_minutes": 0,
            "is_working": False,
        },
    ]
    recovery_response = optimize.run_optimization(
        recovery_store,
        OptimizeRequest(facility_id="f1", period_id="p1", plan_mode=PlanMode.C),
    )
    version_id = recovery_response.roster_options[0].roster_version_id
    recovery_codes = {
        row["shift_type"] for row in recovery_store.data["shifts"]
        if row.get("roster_version_id") == version_id and not row["is_working"]
    }
    assert recovery_codes == {"SLEEP", "DO"}
