"""NAAC config data and the rules it unblocks - MVP tasks 2.2, 2.3 and 4.1.

These three tasks were blocked from 30 Jul to 31 Jul on source files that were
reported delivered but never arrived. Cherry attached them to ClickUp 2.2 and 4.1
on 31 Jul; `docs/naac/README.md` records what was extracted and what was left out.

What is worth testing here is not that a CSV parses. It is that the two
independent descriptions of the same duty code agree:

  * the **grammar** the home applies (`A` = 8 hours, digits = start time, `s` =
    +30 minutes), implemented in `naac.derive_window`; and
  * the **sheet** the home maintains, 279 rows of code and clock time.

If those two drift, someone has mistyped a shift, and the first symptom would be
a payroll number that is quietly wrong for one person for one cycle. So the
cross-check is a test rather than a comment, and the known disagreements are
listed by name - a new one fails the build.
"""
from __future__ import annotations

import pytest

from datetime import date, timedelta

from emma_core.importers import naac
from emma_core.services import facility_config
from emma_core.services.validation import (
    DEFAULT_SEQUENCE_POLICY,
    RosterSnapshot,
    _matches_any,
    evaluate_sequence_rules,
)

# The rule set migration 18 seeds for NAAC, kept here as a literal so the tests
# exercise the same shape the database will hold.
NAAC_SEQUENCE_CONFIG = {
    "max_consecutive_working_days": 8,
    "forbidden_before": [
        {"shift": ["AN", "A7N*", "G7SN*"], "forbidden": ["P*"],
         "reason": "A P shift the day before an AN double shift leaves too little rest."},
    ],
    "forbidden_after": [
        {"shift": ["A230*", "*E"], "forbidden": ["A7", "A7X", "A7S", "A7#"],
         "reason": "A7 the morning after A230 or an E-position shift is too short a turnaround."},
    ],
    "no_consecutive": [
        {"codes": ["A130", "A230E"],
         "reason": "Kitchen duty and the A230 E-position cannot fall on consecutive days."},
    ],
}


def _naac_snapshot(shifts, assignments, *, staff_id="staff-1") -> RosterSnapshot:
    return RosterSnapshot(
        facility_id="facility-naac",
        roster_version_id="version-1",
        period_id="period-1",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 9, 11),
        facility={"id": "facility-naac", "code": "NAAC"},
        staff=({"id": staff_id, "rank": "PCW", "employment_type": "local_ft"},),
        shifts=tuple(shifts),
        assignments=tuple(assignments),
        rule_definitions=({
            "id": "rule-seq", "facility_id": "facility-naac",
            "rule_code": "shift_sequence", "severity": "hard", "active": True,
            "config_version": 1, "config_json": NAAC_SEQUENCE_CONFIG,
        },),
    )


def _day(offset: int) -> str:
    return str(date(2026, 8, 3) + timedelta(days=offset))


def _roster(*codes_by_offset, staff_id="staff-1"):
    """(offset, code) pairs -> the shifts and assignments a snapshot needs."""
    shifts, assignments = [], []
    for index, (offset, code) in enumerate(codes_by_offset):
        shift_id = f"shift-{index}"
        shifts.append({
            "id": shift_id, "date": _day(offset), "shift_type": code,
            "start_time": "07:00", "end_time": "15:00", "cross_midnight": False,
            "is_working": True,
        })
        assignments.append({
            "id": f"assign-{index}", "shift_id": shift_id, "staff_id": staff_id,
            "role": "PCW", "status": "assigned", "is_agency": False,
        })
    return shifts, assignments


# ── the code grammar (2.3) ───────────────────────────────────────────────────
@pytest.mark.parametrize(("code", "start", "end", "minutes"), [
    ("A7",      "07:00", "15:00", 480),    # letter A = 8h, digits = start
    ("A9",      "09:00", "17:00", 480),
    ("A1030",   "10:30", "18:30", 480),    # 4 digits are h:mm
    ("A610",    "06:10", "14:10", 480),
    ("A7s",     "07:00", "15:30", 510),    # s = +30 min
    ("A7x",     "07:00", "15:10", 490),    # x = +10 min
    ("A7v",     "07:00", "15:05", 485),    # v = +5 min
    ("B7",      "07:00", "16:00", 540),    # B = 9h
    ("G7",      "07:00", "14:00", 420),    # G = 7h
    ("G7s",     "07:00", "14:30", 450),
    ("P1",      "13:00", "22:00", 540),    # P ends at 22:00, whenever it starts
    ("P2",      "14:00", "22:00", 480),
    ("N10",     "22:00", "07:00", 540),    # N counts from noon
    ("N1015",   "22:15", "07:15", 540),
])
def test_the_grammar_reads_a_duty_code(code, start, end, minutes):
    window = naac.derive_window(code)
    assert window is not None, f"{code} was not recognised"
    assert (window.start, window.end) == (start, end)
    assert window.paid_minutes == minutes


def test_the_duty_supervisor_marker_does_not_change_the_hours():
    """`#` is a responsibility, not a longer shift."""
    plain, duty = naac.derive_window("A7"), naac.derive_window("A7#")
    assert duty.duty_supervisor is True
    assert plain.duty_supervisor is False
    assert (duty.start, duty.end, duty.paid_minutes) == (
        plain.start, plain.end, plain.paid_minutes)


def test_a_combined_code_is_two_windows_not_one_long_one():
    """A7N10 is 07:00-15:00 and 22:00-07:00 - 17 paid hours across a 24-hour
    envelope, not the 24 hours the envelope would suggest."""
    window = naac.derive_window("A7N10")
    assert window.segments == (
        {"start": "07:00", "end": "15:00"},
        {"start": "22:00", "end": "07:00"},
    )
    assert window.paid_minutes == 17 * 60


def test_a_sleepover_code_is_three_windows():
    """P1C = the P1 duty, then 22:00-22:30 and 06:30-07:00 on the premises."""
    window = naac.derive_window("P1C")
    assert len(window.segments) == 3
    assert window.segments[0] == {"start": "13:00", "end": "22:00"}
    assert window.paid_minutes == 9 * 60 + 3 * 60


@pytest.mark.parametrize("code", ["AL", "SL", "PH", "NO", "O", "CL-8", "1-6p", "/"])
def test_non_duty_codes_are_not_forced_through_the_grammar(code):
    """Leave codes and ad-hoc hour ranges are not shifts; returning None is how
    the loader knows to fall back to the sheet."""
    assert naac.derive_window(code) is None


# ── the home's own dictionary (2.3) ──────────────────────────────────────────
def test_the_dictionary_loads():
    codes = naac.load_shift_codes()
    assert len(codes) > 250, f"expected the full NAAC dictionary, got {len(codes)}"
    a7 = codes["A7"]
    assert a7.hours == 8
    assert a7.windows == (("07:00", "15:00"),)
    assert a7.is_working


def test_the_x_family_carries_the_49_hour_day():
    """8h10m is the frontline day since 2021-01-04, and the `x` codes are how the
    home writes it. 8.1667 rather than 8.1666 matters: over a 6-week cycle the
    difference is a visible number of minutes on a payslip."""
    codes = naac.load_shift_codes()
    for code in ("A7x", "A8x", "A9x", "A610x"):
        assert codes[code].hours == pytest.approx(8.1667, abs=1e-4), code


def test_leave_codes_are_present_in_both_hour_regimes():
    """AL is 8h for an office day and 8h10m for a frontline one, which is why the
    home writes two codes rather than one code and a lookup."""
    codes = naac.load_shift_codes()
    assert "AL" in codes and "ALx" in codes
    assert codes["ALx"].hours > codes["AL"].hours


# The five places the grammar and the sheet disagree, each understood:
#
#   A1230s  the sheet's Remarks say "1230a-9p", which is 00:30 to 21:00 - 20.5
#           hours against its own 時數 column of 8.5. The `a` is a slip.
#   F2      Remarks "1-8p" is 7 hours; the 時數 column says 6, and F is a 6-hour
#           code. Again the Remarks are the loose field.
#   K10     genuinely 22:00-08:00, but K7/K8/K9/K1230 are all ten-hour *day*
#   K10s    shifts starting at the hour they name. Nothing in the code says
#           which, so only the sheet can - and does.
#   N1030   a documented special: 8.5 hours, 22:30-07:00, the long or substitute
#           N. The grammar would give it the standard 9.
GRAMMAR_SHEET_DISAGREEMENTS = {"A1230s", "F2", "K10", "K10s", "N1030"}


def test_the_grammar_and_the_sheet_agree():
    """The cross-check the module exists to make possible."""
    disagreed = {}
    agreed = 0
    for code, spec in naac.load_shift_codes().items():
        derived = naac.derive_window(code)
        if derived is None or not spec.windows:
            continue
        sheet = (spec.windows[0][0], spec.windows[-1][1])
        if (derived.start, derived.end) == sheet:
            agreed += 1
        else:
            disagreed[code] = {"sheet": sheet, "grammar": (derived.start, derived.end)}

    assert agreed > 150, f"only {agreed} codes cross-checked; the parser has regressed"
    unexpected = set(disagreed) - GRAMMAR_SHEET_DISAGREEMENTS
    assert not unexpected, (
        "new grammar/sheet disagreements - either the sheet changed or the parser "
        f"broke: { {k: disagreed[k] for k in unexpected} }")
    resolved = GRAMMAR_SHEET_DISAGREEMENTS - set(disagreed)
    assert not resolved, (
        f"{sorted(resolved)} now agree; drop them from GRAMMAR_SHEET_DISAGREEMENTS "
        "so the list stays a true record of what is still odd")


def test_the_sheet_wins_where_they_disagree():
    """The loaded dictionary carries the sheet's hours, not the grammar's - it is
    what the home pays against."""
    codes = naac.load_shift_codes()
    assert codes["N1030"].hours == 8.5
    assert codes["N1030"].windows == (("22:30", "07:00"),)
    assert codes["K10"].windows == (("22:00", "08:00"),)


# ── escort locations (4.1) ───────────────────────────────────────────────────
def test_escort_locations_load_with_shared_codes_merged():
    """Two places share TMH and two share CPH in the home's own sheet. Both are
    kept as aliases rather than forcing the home to invent codes."""
    locations = naac.load_escort_locations()
    assert len(locations) == 18, f"expected 18 distinct codes, got {len(locations)}"
    assert len(locations["TMH"]["places"]) == 2
    assert len(locations["CPH"]["places"]) == 2
    assert locations["POH"]["name_en"] == "Pok Oi Hospital"


def test_codes_without_a_latin_abbreviation_survive():
    """Three places have no Latin short form in the source. Dropping them would
    silently lose three destinations."""
    codes = naac.escort_codes()
    assert {"深盲輔", "元盲輔", "盈愛"} <= codes


# ── task codes (4.1) ─────────────────────────────────────────────────────────
def test_task_codes_load():
    tasks = naac.load_task_codes()
    assert len(tasks) > 50
    assert tasks["#"].name_en == "Duty supervisor"
    assert tasks["e"].name_zh == "洗衣+搽葯"


def test_only_escort_tasks_require_a_location():
    """`needs_location` is what validation reads, so that a home can add its own
    escort task without an engine change."""
    needs = naac.location_required_task_codes()
    assert needs == {"f", "陪", "家"}, needs
    assert not naac.load_task_codes()["#"].needs_location


# ── facility config (2.2) ────────────────────────────────────────────────────
def test_the_dual_working_week_is_per_role():
    """44h and 49h run in the same building on the same roster, so the regime has
    to hang off the rank and not off the facility."""
    hours = facility_config.NAAC_WORKING_HOURS
    frontline = facility_config.working_hours_for_rank(hours, "PCW")
    office = facility_config.working_hours_for_rank(hours, "SW")
    therapist = facility_config.working_hours_for_rank(hours, "PT")

    assert frontline["weekly_hours"] == 49
    assert frontline["daily_hours"] == pytest.approx(8.1667, abs=1e-4)
    assert office["weekly_hours"] == 44 and office["daily_hours"] == 8.0
    assert therapist["weekly_hours"] == 44 and therapist["daily_hours"] == 9.0
    # Different rest-day entitlements per 6-week cycle, from the same document.
    assert office["rest_days_per_cycle"] == 9
    assert frontline["rest_days_per_cycle"] == 6


def test_an_unmapped_rank_returns_none_rather_than_guessing():
    """A wrong guess silently misprices every leave day for that person, and the
    cheaper guess (44h) is the likelier one - so the caller has to decide."""
    assert facility_config.working_hours_for_rank(
        facility_config.NAAC_WORKING_HOURS, "DRIVER") is None
    assert facility_config.working_hours_for_rank(
        facility_config.NAAC_WORKING_HOURS, None) is None


def test_the_duty_supervisor_marker_grants_no_authority():
    """The '#' is a rostering marker. If it ever implies approval rights it has
    to appear in the RBAC matrix instead, and it does not."""
    quota = facility_config.NAAC_DUTY_SUPERVISOR_QUOTA
    assert quota["grants_approval_rights"] is False
    assert quota["per_cycle_default"] == 12


def test_no_real_staff_names_are_committed_as_config():
    """Per-person quotas are employee data. The shape ships; the mapping does not.

    Cherry confirmed the handling on 1 Aug and added a requirement: the overrides
    must live in the database so an OWNER can change them without a deploy. So
    this asserts not just that the mapping is absent, but that the config points
    at where it actually lives - a config key holding an empty dict would drift
    back into being filled in.
    """
    quota = facility_config.NAAC_DUTY_SUPERVISOR_QUOTA
    assert "per_staff_overrides" not in quota
    assert quota["overrides_source"] == "staff_scheduling_constraints"


def test_no_config_value_anywhere_looks_like_a_person():
    """A blunt guard on the whole config block. The five names Cherry's document
    carried must not reappear in any key or value, however they get there."""
    import json

    blob = json.dumps(facility_config.NAAC_CONFIGS, ensure_ascii=False)
    for name in ("Pan Jianmin", "Jiang Ruting", "Qiu Huiyi", "Su Hua",
                 "Li Zhixiong", "潘建民", "姜汝廷", "邱惠儀", "蘇華", "李志雄"):
        assert name not in blob, f"{name} must not be committed as config"


def test_the_overnight_coverage_minimum_is_recorded():
    """Two staff between 18:00 and 07:00 is the reason the B130 / A2s / A220x
    codes exist at all."""
    windows = facility_config.NAAC_COVERAGE_MINIMUMS["windows"]
    overnight = next(w for w in windows if w["from"] == "18:00")
    assert overnight["min_staff"] == 2
    daytime = next(w for w in windows if w["from"] == "10:00")
    assert daytime["min_nurses"] == 1 and daytime["or_min_health_workers"] == 2


# ── sequencing rules (2.3) ───────────────────────────────────────────────────
def test_sequence_rules_are_off_by_default():
    """Homes A and B stated no adjacency rules, so they must get none - a default
    that fires would invent violations on their rosters."""
    assert DEFAULT_SEQUENCE_POLICY["max_consecutive_working_days"] == 0
    assert DEFAULT_SEQUENCE_POLICY["forbidden_before"] == []
    assert DEFAULT_SEQUENCE_POLICY["forbidden_after"] == []
    assert DEFAULT_SEQUENCE_POLICY["no_consecutive"] == []


@pytest.mark.parametrize(("codes", "patterns", "expected"), [
    ({"A230", "A7"},    ["A230*"],  {"A230"}),
    ({"A230E", "A7"},   ["A230*"],  {"A230E"}),   # prefix catches the task marker
    ({"A230E", "A7E"},  ["*E"],     {"A230E", "A7E"}),  # suffix catches the position
    ({"P1", "P2", "A7"}, ["P*"],    {"P1", "P2"}),
    ({"A7", "A9"},      ["A7"],     {"A7"}),      # bare pattern is exact
    ({"A70"},           ["A7"],     set()),
])
def test_pattern_matching_selects_the_right_codes(codes, patterns, expected):
    """NAAC writes the task marker into the duty code, so `A230e` has to be
    reachable as an A230 shift and as an E position, depending on the rule."""
    assert _matches_any(codes, patterns) == expected


def _codes(violations) -> list[str]:
    return sorted(v["rule_code"] for v in violations)


def test_a_p_shift_the_day_before_an_an_shift_is_caught():
    shifts, assignments = _roster((0, "P2"), (1, "AN"))
    violations = evaluate_sequence_rules(_naac_snapshot(shifts, assignments))
    assert _codes(violations) == ["shift_sequence"]
    assert violations[0]["details"]["relation"] == "before"
    assert violations[0]["details"]["previous_day"] == ["P2"]
    # Reported on the AN day, which is the one that has to move.
    assert violations[0]["date"] == _day(1)


def test_an_a_shift_the_day_before_an_an_shift_is_allowed():
    """The home's stated preference is A7, A1030 or A9 before an AN."""
    shifts, assignments = _roster((0, "A7"), (1, "AN"))
    assert evaluate_sequence_rules(_naac_snapshot(shifts, assignments)) == []


def test_a7_the_morning_after_a230_is_caught():
    shifts, assignments = _roster((0, "A230"), (1, "A7"))
    violations = evaluate_sequence_rules(_naac_snapshot(shifts, assignments))
    assert _codes(violations) == ["shift_sequence"]
    assert violations[0]["details"]["relation"] == "after"


def test_a7_after_an_e_position_is_caught_by_the_suffix_pattern():
    """The E position rides on any morning duty, so the rule matches the marker
    rather than the duty - `A9E` has to trip it just as `A230E` does."""
    shifts, assignments = _roster((0, "A9E"), (1, "A7"))
    violations = evaluate_sequence_rules(_naac_snapshot(shifts, assignments))
    assert _codes(violations) == ["shift_sequence"]


def test_kitchen_duty_on_consecutive_days_is_caught():
    shifts, assignments = _roster((0, "A130"), (1, "A230E"))
    violations = evaluate_sequence_rules(_naac_snapshot(shifts, assignments))
    assert _codes(violations) == ["shift_sequence"]
    assert violations[0]["details"]["relation"] == "no_consecutive"


def test_kitchen_duty_with_a_day_between_is_allowed():
    shifts, assignments = _roster((0, "A130"), (2, "A230E"))
    assert evaluate_sequence_rules(_naac_snapshot(shifts, assignments)) == []


def test_eight_consecutive_days_is_allowed_and_nine_is_not():
    eight = _roster(*[(d, "A7") for d in range(8)])
    assert evaluate_sequence_rules(_naac_snapshot(*eight)) == []

    nine = _roster(*[(d, "A7") for d in range(9)])
    violations = evaluate_sequence_rules(_naac_snapshot(*nine))
    assert _codes(violations) == ["max_consecutive_days"]
    assert violations[0]["details"]["run_length_at_breach"] == 9


def test_a_long_run_is_reported_once_not_once_per_day():
    """A 12-day run is one scheduling mistake. Four near-identical rows would
    bury everything else in the same validation report."""
    twelve = _roster(*[(d, "A7") for d in range(12)])
    violations = evaluate_sequence_rules(_naac_snapshot(*twelve))
    assert len(violations) == 1
    assert violations[0]["details"]["run_length_at_breach"] == 9


def test_a_rest_day_restarts_the_run():
    """Days 0-5 then 7-12: two runs of six, neither over the limit."""
    split = _roster(*[(d, "A7") for d in list(range(6)) + list(range(7, 13))])
    assert evaluate_sequence_rules(_naac_snapshot(*split)) == []


def test_homes_without_a_sequence_rule_get_no_violations():
    """Home B rosters 12-hour blocks back to back by design. With no rule row the
    evaluator must return immediately rather than apply someone else's practice."""
    shifts, assignments = _roster(*[(d, "7A") for d in range(20)])
    snapshot = RosterSnapshot(
        facility_id="facility-b", roster_version_id="v", period_id="p",
        period_start=date(2026, 8, 1), period_end=date(2026, 9, 11),
        facility={"id": "facility-b", "code": "B"},
        staff=({"id": "staff-1", "rank": "PCW", "employment_type": "local_ft"},),
        shifts=tuple(shifts), assignments=tuple(assignments),
    )
    assert evaluate_sequence_rules(snapshot) == []
