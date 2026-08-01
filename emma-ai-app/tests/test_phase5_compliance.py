"""Pure Phase 5 SWD-ratio tests (no Supabase required)."""
from __future__ import annotations

import pytest

from emma_core.services.compliance import (
    _effective_rules,
    _minute_eval,
    _rank_config,
    _requirement,
)


def _shift(shift_id: str, unit_id: str | None = None) -> dict:
    return {
        "id": shift_id,
        "date": "2026-07-01",
        "unit_id": unit_id,
        "start_time": "07:00",
        "end_time": "08:00",
        "cross_midnight": False,
        "is_working": True,
    }


def _assignment(
    assignment_id: str,
    shift_id: str,
    role: str,
    staff_id: str | None,
) -> dict:
    return {
        "id": assignment_id,
        "shift_id": shift_id,
        "role": role,
        "staff_id": staff_id,
        "status": "assigned",
        "is_agency": staff_id is None,
    }


def test_effective_rules_use_version_and_facility_precedence():
    rules = [
        {
            "id": "global",
            "facility_id": None,
            "rule_code": "SWD_RN_DAY",
            "config_version": 1,
            "ratio_residents_per_staff": 60,
            "time_window_start": "07:00",
            "time_window_end": "20:00",
            "active": True,
        },
        {
            "id": "f1-v1",
            "facility_id": "f1",
            "rule_code": "SWD_RN_DAY",
            "config_version": 1,
            "ratio_residents_per_staff": 50,
            "time_window_start": "07:00",
            "time_window_end": "20:00",
            "effective_from": "2026-01-01",
            "effective_to": "2026-06-30",
            "active": True,
        },
        {
            "id": "f1-v2",
            "facility_id": "f1",
            "rule_code": "SWD_RN_DAY",
            "config_version": 2,
            "ratio_residents_per_staff": 40,
            "time_window_start": "07:00",
            "time_window_end": "20:00",
            "effective_from": "2026-07-01",
            "effective_to": "2026-12-31",
            "active": True,
        },
        {
            "id": "other-home",
            "facility_id": "f2",
            "rule_code": "SWD_RN_DAY",
            "config_version": 99,
            "ratio_residents_per_staff": 1,
            "time_window_start": "07:00",
            "time_window_end": "20:00",
            "active": True,
        },
    ]

    assert _effective_rules(rules, "f1", "2026-05-01")[0]["id"] == "f1-v1"
    assert _effective_rules(rules, "f1", "2026-08-01")[0]["id"] == "f1-v2"
    # Once the local override expires, the effective global template applies.
    assert _effective_rules(rules, "f1", "2027-01-01")[0]["id"] == "global"


def test_minute_ratio_is_unit_scoped_weighted_and_person_deduplicated():
    rule = {
        "id": "u1-care",
        "facility_id": "f1",
        "rule_code": "SWD_U1_CARE_DAY",
        "config_version": 1,
        "unit_id": "u1",
        "staff_rank": "RN",
        "counted_ranks_json": ["RN", "EN"],
        "rank_weights_json": {"RN": 1, "EN": 0.5},
        "time_window_start": "07:00",
        "time_window_end": "08:00",
        "ratio_residents_per_staff": 2,
        "active": True,
    }
    residents = [
        {"unit_id": "u1", "care_level": "general", "resident_count": 4},
        {"unit_id": "u2", "care_level": "general", "resident_count": 100},
    ]
    shifts = {
        "rn": _shift("rn", "u1"),
        "rn-duplicate": _shift("rn-duplicate", "u1"),
        "en": _shift("en", "u1"),
        "other-unit": _shift("other-unit", "u2"),
    }
    assignments = [
        _assignment("a-rn", "rn", "RN", "person-1"),
        # Same person in another assignment must not become a second head.
        _assignment("a-rn-duplicate", "rn-duplicate", "RN", "person-1"),
        _assignment("a-en", "en", "EN", "person-2"),
        # Correct rank, wrong unit.
        _assignment("a-u2", "other-unit", "RN", "person-3"),
    ]

    failed = _minute_eval(
        [rule], residents, shifts, assignments, "2026-07-01", facility_id="f1")[0]
    assert failed["residents"] == 4
    assert failed["required"] == 2
    assert failed["min_actual"] == 1.5
    assert failed["breach_minutes"] == 60

    # Synthetic workers use assignment id as identity. A duplicated row with
    # the same id counts once; a distinct agency assignment counts separately.
    assignments.extend([
        _assignment("agency-1", "en", "EN", None),
        _assignment("agency-1", "en", "EN", None),
        _assignment("agency-2", "en", "EN", None),
    ])
    passed = _minute_eval(
        [rule], residents, shifts, assignments, "2026-07-01", facility_id="f1")[0]
    assert passed["min_actual"] == 2.5
    assert passed["breach_minutes"] == 0
    assert passed["passes"] is True


def test_exact_rank_and_integer_resident_fallback_stay_compatible():
    rule = {
        "staff_rank": "RN",
        "time_window_start": "07:00",
        "time_window_end": "08:00",
        "ratio_residents_per_staff": 50,
    }
    shifts = {"rn": _shift("rn"), "en": _shift("en")}
    assignments = [
        _assignment("a-rn", "rn", "RN", "person-rn"),
        _assignment("a-en", "en", "EN", "person-en"),
    ]

    row = _minute_eval(
        [rule], 50, shifts, assignments, "2026-07-01")[0]
    assert row["required"] == 1
    assert row["min_actual"] == 1
    assert row["passes"] is True


def test_home_b_hw_substitution_uses_forty_resident_capacity():
    rule = {
        "staff_rank": "RN",
        "counted_ranks_json": ["RN", "EN", "HW"],
        "rank_weights_json": {"RN": 1, "EN": 1, "HW": 2 / 3},
        "time_window_start": "07:00",
        "time_window_end": "20:00",
        "ratio_residents_per_staff": 60,
    }
    shifts = {"hw": _shift("hw")}
    shifts["hw"]["end_time"] = "20:00"
    assignments = [_assignment("a-hw", "hw", "HW", "person-hw")]

    at_capacity = _minute_eval(
        [rule],
        40,
        shifts,
        assignments,
        "2026-07-01",
    )[0]
    over_capacity = _minute_eval(
        [rule],
        41,
        shifts,
        assignments,
        "2026-07-01",
    )[0]

    assert at_capacity["required"] == 0.667
    assert at_capacity["passes"] is True
    assert over_capacity["passes"] is False


@pytest.mark.parametrize("ratio", (0, -1, 1.5, "invalid", True))
def test_invalid_ratio_configuration_fails_closed(ratio):
    rule = {
        "time_window_start": "07:00",
        "time_window_end": "20:00",
        "ratio_residents_per_staff": ratio,
    }

    with pytest.raises(ValueError, match="positive integer"):
        _requirement(rule, 40)


@pytest.mark.parametrize("minimum", (-1, 1.5, "invalid", True))
def test_invalid_minimum_configuration_fails_closed(minimum):
    rule = {
        "time_window_start": "07:00",
        "time_window_end": "20:00",
        "min_staff_any_rank": minimum,
    }

    with pytest.raises(ValueError, match="non-negative integer"):
        _requirement(rule, 40)


@pytest.mark.parametrize("weight", (-0.1, float("inf"), "invalid", True))
def test_invalid_rank_weight_configuration_fails_closed(weight):
    with pytest.raises(ValueError, match="staffing ratio weight"):
        _rank_config({"rank_weights_json": {"HW": weight}})
