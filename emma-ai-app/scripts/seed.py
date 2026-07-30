"""Seed local Supabase with Home A + Home B demo data.

Run AFTER `supabase db reset` (schema+RLS applied) and after .env holds the
service-role key:

    python scripts/seed.py

Uses the service-role client (bypasses RLS) to create reference data, a full
period roster, resident counts, and the Phase 3 operations layer (leave
requests, SL/DSL incidents, agency spend, attendance, debt ledger, report
schedules, regulatory registry, and Phase 4 operational rules). Idempotent: wipes the two demo facilities +
dev users first.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date as Date, datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from emma_core.db import get_service_client  # noqa: E402
from emma_core.shifttime import paid_minutes  # noqa: E402

DEV_PASSWORD = "EmmaDev123!"

sb = get_service_client()


# ── helpers ──────────────────────────────────────────────────────────────────
def ins(table: str, row: dict) -> str:
    # SQL: insert into <table> (<keys of row>) values (<values>) returning id
    res = sb.table(table).insert(row).execute()
    return res.data[0]["id"]


def ins_many(table: str, rows: list[dict]) -> list[str]:
    if not rows:
        return []
    # SQL: insert into <table> (<keys>) values (...), (...), ... returning id
    res = sb.table(table).insert(rows).execute()
    return [r["id"] for r in res.data]


def ts(day: Date, hour: int, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute,
                    tzinfo=timezone.utc).isoformat()


def dates_for(start: str, days: int) -> list[str]:
    d0 = Date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(days)]


def wipe() -> None:
    for code in ("A", "B"):
        # SQL: delete from facilities where code = :code
        # (every tenant table is ON DELETE CASCADE from facilities, so this one
        #  statement per home clears the whole fixture)
        sb.table("facilities").delete().eq("code", code).execute()
    # global (facility-less) reference rows this script owns
    # SQL: delete from regulatory_documents where facility_id is null
    sb.table("regulatory_documents").delete().is_("facility_id", "null").execute()
    try:
        users = sb.auth.admin.list_users()
        for u in users:
            if u.email and u.email.endswith("@emma.local"):
                sb.auth.admin.delete_user(u.id)
    except Exception as e:  # noqa: BLE001
        print("  (auth wipe skipped:", e, ")")


def seed_shift_defs(facility_id: str, defs: list[tuple], splits: dict) -> None:
    rows = []
    for code, label, start, end, cross, working in defs:
        segments = splits.get(code)
        rows.append({
            "facility_id": facility_id, "shift_type": code, "label": label,
            "start_time": start, "end_time": end, "cross_midnight": cross,
            "is_working": working, "segments": segments,
            "paid_minutes": paid_minutes({"segments": segments}) if segments else None,
        })
    ins_many("shift_definitions", rows)


def seed_ratio_rules(facility_id: str, facility_code: str) -> None:
    """Seed the exact Home A/B SWD windows from the source specification."""
    if facility_code == "A":
        rules = [
            ("swd_aw", "AW", "08:30", "19:30", 40, ["AW"], {}),
            ("swd_care_day", "CW", "07:00", "17:00", 20, ["CW"], {}),
            ("swd_care_night", "CW", "17:00", "07:00", 240, ["CW"], {}),
            (
                "swd_health_worker",
                "HW",
                "07:00",
                "18:00",
                30,
                ["HW", "RN", "EN"],
                {"HW": 1, "RN": 2, "EN": 2},
            ),
            (
                "swd_nurse",
                "RN",
                "07:00",
                "18:00",
                60,
                ["RN", "EN"],
                {"RN": 1, "EN": 1},
            ),
        ]
    else:
        rules = [
            ("swd_aw", "AW", "07:00", "18:00", 40, ["AW"], {}),
            ("swd_care_day", "HCA", "07:00", "17:00", 20, ["HCA"], {}),
            ("swd_health_worker", "HW", "07:00", "20:00", 30, ["HW"], {}),
            (
                "swd_nurse",
                "RN",
                "07:00",
                "20:00",
                60,
                ["RN", "EN", "HW"],
                # One RN/EN covers 60 residents; the HW substitute covers 40,
                # so an HW contributes two-thirds of a nurse-equivalent head.
                {"RN": 1, "EN": 1, "HW": 2 / 3},
            ),
        ]
    ins_many("staffing_ratio_rules", [{
        "facility_id": facility_id,
        "rule_code": code,
        "staff_rank": rank,
        "time_window_start": start,
        "time_window_end": end,
        "ratio_residents_per_staff": ratio,
        "counted_ranks_json": counted_ranks,
        "rank_weights_json": rank_weights,
        "effective_from": "2026-01-01",
        "config_version": 1,
        "active": True,
    } for code, rank, start, end, ratio, counted_ranks, rank_weights in rules])


def seed_phase5_rules(facility_id: str, facility_code: str) -> None:
    night_types = ["AN", "N"] if facility_code == "A" else ["AN", "N", "7P"]
    agency_config = {
        "agency_employment_types": ["agency", "outsource", "casual"],
        "banned_shift_types": [] if facility_code == "A" else ["AN", "N", "7P"],
        "period_ratio_cap": 0.5,
        "daily_rank_caps": {"RN|EN|HW": 2, "CW|HCA": 12},
        "monthly_shift_caps": {"AN": 2} if facility_code == "A" else {},
        "peak_holiday_terms": [
            "mid-autumn", "winter solstice", "lunar new year",
            "農曆新年", "中秋", "冬至",
        ],
        "part_time_policy": {
            "employment_types": ["local_pt"],
            "required_start": "09:00",
            "required_end": "17:48" if facility_code == "A" else "18:00",
            "allowed_weekdays": (
                [] if facility_code == "A" else [0, 1, 3, 5]
            ),
            "weekly_work_days": (
                {"min": 5, "max": 6}
                if facility_code == "A"
                else {"min": 4, "max": 4}
            ),
            "fortnightly_work_days": (
                {"min": 11, "max": 11}
                if facility_code == "A"
                else None
            ),
            "saturday_requires_weekday_cl": facility_code == "A",
        },
    }
    if facility_code == "B":
        agency_config["vacancy_cap"] = {
            "enabled": True,
            "standard_do_days": 6,
            "factor": 0.7,
        }
    ins_many("rule_definitions", [
        {
            "facility_id": facility_id,
            "rule_code": "night_chain",
            "name": f"Home {facility_code} night recovery chain",
            "severity": "hard",
            "config_json": {
                "night_shift_types": night_types,
                "chain_employment_types": ["local_ft"],
                "sleep_codes": ["SLEEP", "SD"],
                "day_off_codes": ["DO", "OFF"],
                "an_monthly_limit": 2,
                "nurse_night_monthly_limit": 2,
                "cooldown_ranks": ["RN", "EN"],
            },
            "config_version": 1,
            "effective_from": "2026-01-01",
        },
        {
            "facility_id": facility_id,
            "rule_code": "agency_limits",
            "name": f"Home {facility_code} external workforce limits",
            "severity": "hard",
            "config_json": agency_config,
            "config_version": 1,
            "effective_from": "2026-01-01",
        },
        {
            "facility_id": facility_id,
            "rule_code": "leave_rules",
            "name": f"Home {facility_code} leave policy",
            "severity": "hard",
            "config_json": {
                "request_cutoff_day": 10,
                "max_do_cl_balance": 3,
            },
            "config_version": 1,
            "effective_from": "2026-01-01",
        },
    ])


# Leave must be requested by ~the 10th of the preceding month, so the earliest
# approvable request starts about two months out. Carry the configured periods
# past that horizon or the whole of 5.5 is unreachable.
FORWARD_CYCLE_DAYS = 120


def seed_forward_cycles(
    facility_id: str,
    cycle_type: str,
    last_end: Date,
    days: int,
    staff_ids: list[str],
    *,
    horizon: Date,
) -> list[str]:
    """Open the upcoming cycles (period + entitlements) with no roster attached.

    The leave rules gate on two things at once: a request must clear the
    submission cutoff, and every requested day must resolve to exactly one
    configured balance. With only the current cycle seeded, anything late enough
    to clear the cutoff falls outside every period, so no leave request can ever
    be approved. Periods must not overlap - the balance trigger rejects a day
    that resolves to two.
    """
    cycles = []
    while last_end < horizon:
        start = last_end + timedelta(days=1)
        if cycle_type == "natural_month":
            # Roll to the calendar month end so month-based cycles stay aligned.
            next_month = (start.replace(day=1) + timedelta(days=31)).replace(day=1)
            last_end = next_month - timedelta(days=1)
        else:
            last_end = start + timedelta(days=days - 1)
        period_id = ins("roster_periods", {
            "facility_id": facility_id,
            "period_start": start.isoformat(),
            "period_end": last_end.isoformat(),
            "cycle_type": cycle_type,
            "status": "planning",
        })
        seed_leave_balances(facility_id, period_id, staff_ids)
        cycles.append({"id": period_id, "start": start, "end": last_end})
    return cycles


def roster_cycle_covering(
    facility_id: str,
    cycles: list[dict],
    on_date: Date,
    label: str,
    *,
    staff_ids, ranks, units, pattern, times, splits, task_map,
) -> dict | None:
    """Put a real roster on whichever upcoming cycle contains `on_date`.

    The fixed 1-28 Jul cycle stops covering "today" two days later, and every
    today-scoped screen (dashboard shift mix, staff-app window, attendance) then
    reads an empty day. Rostering the cycle that actually contains today keeps
    those live without moving the July fixtures other tests assert on.
    """
    current = next(
        (c for c in cycles if c["start"] <= on_date <= c["end"]), None)
    if not current:
        return None
    version_id = ins("roster_versions", {
        "facility_id": facility_id, "period_id": current["id"],
        "version_type": "manual", "label": label, "status": "draft",
    })
    dates = dates_for(current["start"].isoformat(),
                      (current["end"] - current["start"]).days + 1)
    roster = seed_roster(facility_id, version_id, staff_ids, ranks, units, pattern,
                         times, splits, task_map, dates)
    return {**current, "version_id": version_id, "dates": dates, "roster": roster}


def seed_leave_balances(
    facility_id: str,
    period_id: str,
    staff_ids: list[str],
) -> None:
    ins_many("leave_balances", [
        {
            "facility_id": facility_id,
            "staff_id": staff_id,
            "period_id": period_id,
            "leave_type": leave_type,
            "opening_balance": opening,
        }
        for staff_id in staff_ids
        # DO + CL are one combined carry-over pool with a hard maximum of 3.
        for leave_type, opening in (("AL", 12), ("PH", 2), ("CL", 1), ("DO", 2))
    ])


# time maps per shift code -> (start, end, cross_midnight, is_working).
# For a split shift these are the FIRST duty window only; SPLIT_* below carries
# the full truth and takes priority everywhere (see emma_core/shifttime.py).
SHIFT_TIMES_A = {
    "A": ("07:00", "15:00", False, True), "B": ("08:00", "16:00", False, True),
    "E": ("09:00", "17:00", False, True), "P": ("13:30", "21:30", False, True),
    "N": ("21:30", "07:00", True, True),  "AN": ("07:00", "13:30", False, True),
    "PT": ("09:00", "17:48", False, True),
    "OFF": (None, None, False, False), "AL": (None, None, False, False),
    "SLEEP": (None, None, False, False), "DO": (None, None, False, False),
    "CL": (None, None, False, False),
}
SHIFT_TIMES_B = {
    "7A": ("07:00", "19:00", False, True), "9A": ("09:00", "21:00", False, True),
    "7P": ("19:00", "07:00", True, True),  "A": ("07:00", "16:00", False, True),
    "P": ("12:30", "21:30", False, True),  "AN": ("07:00", "14:30", False, True),
    "PT": ("09:00", "18:00", False, True),
    "OFF": (None, None, False, False), "DO": (None, None, False, False),
    "AL": (None, None, False, False), "SLEEP": (None, None, False, False),
    "CL": (None, None, False, False),
}

# Split shifts, straight from the scheduling spec:
#   Home A  A/N更: 07:00–13:30 且當晚 21:30–07:00 (次日)   ->  6.5h +  9.5h = 16h
#   Home B  A/N更: 07:00–14:30 且 21:15–07:15 (次日)       ->  7.5h + 10.0h = 17.5h
# The chain that follows is A/N -> SLEEP -> DO, which the seeded patterns honour.
SPLIT_A = {"AN": [{"start": "07:00", "end": "13:30"}, {"start": "21:30", "end": "07:00"}]}
SPLIT_B = {"AN": [{"start": "07:00", "end": "14:30"}, {"start": "21:15", "end": "07:15"}]}

PERIOD_A_START, PERIOD_A_DAYS = "2026-07-01", 28
PERIOD_B_START, PERIOD_B_DAYS = "2026-07-01", 31

# Weekly patterns sized to the 44h local-FT contract, with the spec's A/N -> SLEEP
# -> DO chain honoured. Previously the AW worked all seven days and the PCW six
# nights, which put them 27-30% over contract before any overtime - that is a
# rostering breach, not an OT signal, and it drowned the real alerts.
#   A/N = 16h, N = 9.5h, everything else 8h.
PATTERN_A = [
    ["P", "A", "P", "AN", "SLEEP", "OFF", "AL"],      # RN   8+8+8+16   = 40h
    ["OFF", "P", "P", "A", "P", "A", "DO"],           # EN   5 x 8      = 40h
    ["A", "AN", "SLEEP", "OFF", "A", "A", "OFF"],     # HW   8+16+8+8   = 40h
    ["P", "P", "OFF", "P", "P", "A", "DO"],           # CW   5 x 8      = 40h
    ["A", "A", "A", "A", "A", "OFF", "OFF"],          # PTA  5 x 8      = 40h
    ["N", "N", "SLEEP", "OFF", "N", "N", "DO"],       # PCW  4 x 9.5    = 38h
    ["P", "P", "P", "P", "P", "OFF", "OFF"],          # AW   5 x 8      = 40h
]
# Home B: imported HCA 72h/week, local staff 49.5h/week (spec: 11 working days
# + 3 rest days per fortnight). 7A/7P are 12h, A/P are 9h.
PATTERN_B = [
    ["7A", "7A", "7P", "OFF", "7A", "7A", "7A"],      # HCA  6 x 12 = 72h
    ["A", "A", "P", "P", "OFF", "A", "DO"],           # HW   5 x 9  = 45h
    ["P", "P", "A", "A", "P", "OFF", "DO"],           # EN   5 x 9  = 45h
]
# staff index -> shift code -> task labels. Home A defines RN-only task codes
# (A1/A2 Med Checking + Medication Mgmt on A, A4/A5 Wound Care + ICP Review on P),
# so the nurses must carry them: they are the clinical tasks the ratio and
# task-eligibility rules are written about, and leaving rows 0-1 empty left the
# RN/EN with no rostered task evidence at all.
TASKS_A = {
    0: {"A": ["Med Checking", "Medication Mgmt"],
        "P": ["Wound Care", "ICP Review"],
        "AN": ["Med Checking"]},
    1: {"A": ["Med Checking"], "P": ["Wound Care", "FU Chat"]},
    2: {"A": ["Vital Signs"], "AN": ["Vital Signs"],
        "P": ["AOM (Oral)"]},
    3: {"A": ["Oral Feeding"], "P": ["Evening Diaper Change"]},
    4: {"A": ["Rehab Session"]},
    6: {"P": ["Infection Control"]},
}


def seed_roster(facility_id, version_id, staff_ids, ranks, units, pattern,
                times, splits, task_map, dates) -> dict[str, list[str]]:
    """One shift + assignment per staff per day. The 7-day pattern repeats across
    the whole period so a 28-day cycle really has 28 days of roster - the KPI,
    fairness and report screens all read a full period.

    Returns {staff_id: [assignment_id, ...]} in date order.
    """
    shift_rows, meta = [], []
    for i, staff_id in enumerate(staff_ids):
        for d, day in enumerate(dates):
            code = pattern[i][d % 7]
            start, end, cross, working = times[code]
            segments = splits.get(code)
            shift_rows.append({
                "facility_id": facility_id, "roster_version_id": version_id,
                "date": day, "shift_type": code, "start_time": start,
                "end_time": end, "cross_midnight": cross, "unit_id": units[i],
                "required_rank": ranks[i], "required_count": 1, "is_working": working,
                "segments": segments,
                "paid_minutes": paid_minutes({"segments": segments}) if segments else None,
            })
            meta.append((i, staff_id, d, code))

    shift_ids = ins_many("shifts", shift_rows)
    assign_rows = []
    for shift_id, (i, staff_id, d, code) in zip(shift_ids, meta):
        # A staff member's standing duties recur on every working day, which is
        # what gives the AI-analysis tab real task-frequency evidence.
        configured_tasks = task_map.get(i, [])
        if isinstance(configured_tasks, dict):
            configured_tasks = configured_tasks.get(code, [])
        tasks = configured_tasks if times[code][3] else []
        assign_rows.append({
            "facility_id": facility_id, "shift_id": shift_id, "staff_id": staff_id,
            "role": ranks[i], "status": "assigned", "is_agency": False, "tasks": tasks,
        })
    assignment_ids = ins_many("shift_assignments", assign_rows)

    by_staff: dict[str, list[str]] = {}
    for aid, (_, staff_id, _, _) in zip(assignment_ids, meta):
        by_staff.setdefault(staff_id, []).append(aid)
    return {"shift_ids": shift_ids, "meta": meta, "by_staff": by_staff}


def seed_resident_counts(facility_id, unit_counts, entered_by, dates) -> None:
    ins_many("daily_resident_counts", [{
        "facility_id": facility_id, "date": day, "unit_id": unit_id,
        "care_level": "general", "resident_count": count, "entered_by": entered_by,
    } for day in dates for unit_id, count in unit_counts])


def make_user(email, role, facility_id, staff_id=None) -> str:
    res = sb.auth.admin.create_user({
        "email": email, "password": DEV_PASSWORD, "email_confirm": True,
    })
    auth_id = res.user.id
    ins("users_profile", {
        "auth_user_id": auth_id, "facility_id": facility_id, "email": email,
        "role": role, "staff_id": staff_id,
    })
    return auth_id


# ── Phase 3 operations layer ─────────────────────────────────────────────────
def seed_task_definitions(facility_id: str) -> None:
    """Phase 4 dictionary: rank-specific codes remain reusable across facilities."""
    rows = [{
        "facility_id": facility_id, "task_code": code, "task_name": name,
        "shift_type": shift, "required_rank": rank, "requires_audit": audit,
        "description": description,
        "required_qualification_json": (
            {"all_of": ["medication_audited"]} if audit else {}
        ),
        "is_restricted": restricted,
    } for code, name, shift, rank, audit, restricted, description in [
        ("A1", "Med Checking", "A", "HW", True, True, "Audited morning medication check"),
        ("A2", "Medication Mgmt", "A", "HW", True, True, "Audited morning medication round"),
        ("A3", "Vital Signs", "A", "HW", False, False, "Basic morning care; agency-safe"),
        ("P1", "ICP Review", "P", "HW", True, True, "Audited afternoon care-plan review"),
        ("P2", "FU Chat", "P", "HW", True, True, "Afternoon clinical follow-up"),
        ("P3", "AOM (Oral)", "P", "HW", False, False, "Basic afternoon care; agency-safe"),
    ]]
    cw_names = {
        "A1": "Oral Feeding", "A2": "Diaper Change", "A3": "Bathing",
        "A4": "Transfer", "A5": "Morning Hygiene", "A6": "Hydration Round",
        "A7": "Bed Making", "A8": "Activity Support",
        "P1": "Evening Feeding", "P2": "Evening Diaper Change", "P3": "Evening Bathing",
        "P4": "Evening Transfer", "P5": "Bedtime Care", "P6": "Night Preparation",
    }
    rows.extend({
        "facility_id": facility_id, "task_code": code, "task_name": name,
        "shift_type": code[0], "required_rank": "CW", "requires_audit": False,
        "description": "Daily care-worker task code",
        "required_qualification_json": {}, "is_restricted": False,
    } for code, name in cw_names.items())
    # RN/EN intentionally have no daily task codes; event staffing carries their
    # priorities. Therapy/admin labels retain the existing staff-app demo.
    rows.extend([
        {"facility_id": facility_id, "task_code": "R1", "task_name": "Rehab Session",
         "shift_type": None, "required_rank": "PTA", "requires_audit": False,
         "description": "Therapy support", "required_qualification_json": {},
         "is_restricted": False},
        {"facility_id": facility_id, "task_code": "I1", "task_name": "Infection Control",
         "shift_type": None, "required_rank": "AW", "requires_audit": False,
         "description": "Infection-control support", "required_qualification_json": {},
         "is_restricted": False},
    ])
    ins_many("task_definitions", rows)


def seed_staff_qualifications(facility_id: str, staff_ids: list[str],
                              ranks: list[str]) -> None:
    rows = []
    for staff_id, rank in zip(staff_ids, ranks):
        if rank in {"RN", "EN", "HW"}:
            rows.append({
                "facility_id": facility_id, "staff_id": staff_id,
                "qualification_type": "medication_audited", "is_active": True,
                "effective_from": "2026-01-01",
            })
        if rank == "RN":
            rows.append({
                "facility_id": facility_id, "staff_id": staff_id,
                "qualification_type": "mentor", "is_active": True,
                "effective_from": "2026-01-01",
            })
    ins_many("staff_qualifications", rows)


def seed_floor_rules(facility_id: str, floors: dict[str, str]) -> None:
    """Home B's minute-level operational floor coverage from the source spec."""
    rows = []
    for floor in ("1F", "2F"):
        rows.extend([
            {"facility_id": facility_id, "unit_id": floors[floor], "floor": floor,
             "time_window_start": "07:00", "time_window_end": "17:00",
             "rank": "HCA", "min_count": 3,
             "condition_json": {"required_shift_types": ["7A"]}, "active": True},
            {"facility_id": facility_id, "unit_id": floors[floor], "floor": floor,
             "time_window_start": "19:00", "time_window_end": "07:00",
             "rank": "HCA", "min_count": 1,
             "condition_json": {"required_shift_types": ["7P"]}, "active": True},
        ])
    rows.extend([
        {"facility_id": facility_id, "unit_id": floors["6F"], "floor": "6F",
         "time_window_start": "07:00", "time_window_end": "17:00",
         "rank": "HCA", "min_count": 3,
         "condition_json": {"weekdays": [0, 1, 2, 3, 4], "required_shift_types": ["7A"]},
         "active": True},
        {"facility_id": facility_id, "unit_id": floors["6F"], "floor": "6F",
         "time_window_start": "07:00", "time_window_end": "17:00",
         "rank": "HCA", "min_count": 2,
         "condition_json": {"weekdays": [5, 6], "required_shift_types": ["7A"]},
         "active": True},
        {"facility_id": facility_id, "unit_id": floors["6F"], "floor": "6F",
         "time_window_start": "19:00", "time_window_end": "07:00",
         "rank": "HCA", "min_count": 1,
         "condition_json": {"required_shift_types": ["7P"]}, "active": True},
        {"facility_id": facility_id, "unit_id": floors["2F"], "floor": "2F",
         "time_window_start": "16:00", "time_window_end": "21:30",
         "rank": "HCA", "min_count": 1,
         "condition_json": {
             "when_7a_composition": {"imported_labor": 2, "local_ft": 1},
             "required_shift_types": ["P"], "employment_types": ["local_ft"],
         }, "active": True},
    ])
    ins_many("floor_min_staffing_rules", rows)


def seed_roi_settings(facility_id: str, profile_id: str, *, total_budget: int,
                      salary_budget: int, vacancies: dict) -> None:
    # roi_settings is keyed by facility_id - it has no surrogate `id`, so this
    # can't go through ins().
    # SQL: insert into roi_settings
    #        (facility_id, manager_hourly_rate, roster_hours_before, roster_hours_after,
    #         hours_saved_per_incident, agency_reduction_pct, total_budget,
    #         salary_budget, ...)
    #      values (:facility_id, 409, 26, 7, 0.75, 5, :total_budget, :salary_budget, ...)
    #      returning *
    sb.table("roi_settings").insert({
        "facility_id": facility_id, "manager_hourly_rate": 409,
        "roster_hours_before": 26, "roster_hours_after": 7,
        "hours_saved_per_incident": 0.75, "agency_reduction_pct": 5,
        "total_budget": total_budget, "salary_budget": salary_budget,
        "contract_years": "5yr", "vacancies_json": vacancies,
        "updated_by": profile_id,
    }).execute()


def seed_leave_requests(facility_id: str, staff_ids: list[str], profile_id: str,
                        ref: Date) -> list[str]:
    """A realistic approval queue: some decided, some awaiting the superintendent."""
    rows = [
        # (staff idx, category, type, start offset, end offset, reason, remark, status, reviewed)
        (3, "al", "AL", -60, -54, "Marriage", "Wedding leave", "approved", True),
        (0, "al", "AL", 12, 16, "Annual leave", None, "reviewed", True),
        (2, "al", "special", 20, 20, "Compassionate leave", None, "pending", False),
        (5, "duty", "duty_request", 5, 5, "Requesting A shift", "Childcare", "pending", False),
        (1, "duty", "DO", 9, 9, "Day off request", None, "approved", True),
        (4, "duty", "duty_request", -3, -3, "Requesting P shift", None, "rejected", True),
        (4, "sick", "SL", -1, -1, "Fever", None, "approved", True),
        (6, "sick", "SL", -8, -8, "Gastric flu", None, "approved", True),
        (1, "sick", "DSL", -14, -11, "Influenza, 4 days", "Medical cert attached",
         "approved", True),
        (5, "sick", "late", 0, 0, "MTR disruption", None, "pending", False),
    ]
    payload = []
    for idx, category, ltype, d0, d1, reason, remark, status, reviewed in rows:
        created = ref + timedelta(days=min(d0, 0) - 1)
        payload.append({
            "facility_id": facility_id, "staff_id": staff_ids[idx],
            "category": category, "leave_type": ltype,
            "date_start": (ref + timedelta(days=d0)).isoformat(),
            "date_end": (ref + timedelta(days=d1)).isoformat(),
            "requested_shift_type": "A" if ltype == "duty_request" and idx == 5 else (
                "P" if ltype == "duty_request" else None),
            "reason": reason, "remark": remark,
            "document_url": "sick-leave-cert.pdf" if category == "sick" and ltype != "late" else None,
            "status": status,
            "reviewed_at": ts(created, 9) if reviewed else None,
            "decided_by": profile_id if status in ("approved", "rejected") else None,
            "decided_at": ts(created, 10) if status in ("approved", "rejected") else None,
            "created_at": ts(created, 8),
        })
    return ins_many("leave_requests", payload)


def seed_incidents(facility_id: str, staff_ids: list[str], profile_id: str,
                   ref: Date, shift_lookup) -> None:
    """A month of SL/DSL activity: mostly closed with a real response time, two
    still open so the Alert centre has live work and candidates to rank."""
    closed = [
        # (staff idx, type, days ago, response minutes, replacement idx, auto)
        (4, "SL", 1, 12, 3, True),
        (6, "SL", 3, 8, 0, True),
        (1, "DSL", 13, 27, 2, False),
        (5, "SL", 5, 19, 3, True),
        (2, "SL", 7, 14, 6, True),
        (3, "urgent", 9, 22, 1, True),
        (0, "SL", 11, 9, 2, True),
        (4, "SL", 15, 31, 6, False),
        (6, "late", 17, 5, 6, True),
        (1, "SL", 19, 16, 4, True),
        (5, "DSL", 22, 34, 0, False),
        (2, "SL", 24, 11, 3, True),
    ]
    rows = []
    for idx, itype, ago, minutes, rep_idx, auto in closed:
        day = ref - timedelta(days=ago)
        reported = ts(day, 7, 15)
        rows.append({
            "facility_id": facility_id, "staff_id": staff_ids[idx],
            "shift_id": shift_lookup(staff_ids[idx], day),
            "incident_type": itype, "reason": "Reported unfit for duty",
            "reported_at": reported, "replacement_status": "resolved",
            "replacement_staff_id": staff_ids[rep_idx],
            "resolved_at": ts(day, 7, 15 + minutes % 45),
            "resolved_by": profile_id, "resolution_minutes": minutes,
            "auto_resolved": auto, "created_at": reported,
        })

    # PostgREST unions the column set across a bulk insert and writes NULL where a
    # key is missing, so every row must carry the same keys - column defaults do
    # not fill the gaps here.
    open_cases = [(5, "SL", 0), (2, "urgent", 0)]
    for idx, itype, ago in open_cases:
        day = ref - timedelta(days=ago)
        rows.append({
            "facility_id": facility_id, "staff_id": staff_ids[idx],
            "shift_id": shift_lookup(staff_ids[idx], day),
            "incident_type": itype, "reason": "Called in unfit for duty",
            "reported_at": ts(day, 6, 40), "replacement_status": "open",
            "replacement_staff_id": None, "resolved_at": None, "resolved_by": None,
            "resolution_minutes": None, "auto_resolved": False,
            "created_at": ts(day, 6, 40),
        })
    ins_many("sl_incidents", rows)


def seed_agency(facility_id: str, ref: Date) -> None:
    """Real per-shift agency rates (HK$118,520 / 124 PT RCW shifts = HK$956;
    HK$29,550 / 24 PT HW-EN shifts = HK$1,231), at this home's scale."""
    rows = []
    for i in range(18):
        day = ref - timedelta(days=(i * 3) % 26)
        rows.append({
            "facility_id": facility_id, "date": day.isoformat(), "role": "PCW",
            "vendor": "HK Care Staffing Ltd", "hours": 8, "cost": 957,
            "reason": "SL cover - no internal candidate within rest rules",
        })
    for i in range(3):
        day = ref - timedelta(days=4 + i * 7)
        rows.append({
            "facility_id": facility_id, "date": day.isoformat(), "role": "HW",
            "vendor": "Prime Nursing Agency", "hours": 8, "cost": 1231,
            "reason": "Vacancy cover pending recruitment",
        })
    ins_many("agency_assignments", rows)


def seed_attendance(facility_id: str, staff_id: str, ref: Date) -> None:
    rows = []
    for ago in range(1, 11):
        day = ref - timedelta(days=ago)
        rows.append({"facility_id": facility_id, "staff_id": staff_id,
                     "event_type": "clock_in", "event_at": ts(day, 13, 22),
                     "source": "staff_app"})
        rows.append({"facility_id": facility_id, "staff_id": staff_id,
                     "event_type": "clock_out", "event_at": ts(day, 21, 34),
                     "source": "staff_app"})
    # on shift right now, so the app shows a live "clocked in" state
    rows.append({"facility_id": facility_id, "staff_id": staff_id,
                 "event_type": "clock_in", "event_at": ts(ref, 13, 18),
                 "source": "staff_app"})
    ins_many("attendance_events", rows)


def seed_debt(facility_id: str, staff_ids: list[str], period_id: str) -> None:
    ins_many("future_debt_ledger", [{
        "facility_id": facility_id, "staff_id": staff_ids[idx], "debt_type": kind,
        "quantity": qty, "unit": "hours" if kind != "AN" else "count",
        "due_period_id": period_id, "status": "open", "note": note,
    } for idx, kind, qty, note in [
        (3, "TOIL", 8, "emergency cover - compensate next cycle"),
        (0, "CL", 12.5, "public holiday worked"),
        (2, "TOIL", 8, "emergency cover - compensate next cycle"),
        (6, "CL", 4, "shift extension"),
        (1, "AN", 1, "AN make-up owed"),
    ]])


def seed_notifications(facility_id: str, staff_id: str, profile_id: str) -> None:
    ins_many("notifications", [{
        "facility_id": facility_id, "staff_id": staff_id, "profile_id": None,
        "channel": "in_app", "event_type": event, "title": title, "body": body,
        "status": status, "sent_at": None if status == "queued" else datetime.now(
            timezone.utc).isoformat(),
    } for event, title, body, status in [
        ("roster_published", "July roster published",
         "Your shifts for 1–28 July are confirmed.", "read"),
        ("leave_decided", "Annual leave reviewed",
         "Your 12–16 July request is with the superintendent.", "sent"),
        ("cover_request", "Cover needed - P shift",
         "A P shift needs cover today. Tap to accept.", "sent"),
    ]])


def seed_report_registry(facility_id: str) -> None:
    ins_many("report_schedules", [{
        "facility_id": facility_id, "report_type": rtype, "icon": icon,
        "name_en": name_en, "name_zh": name_zh,
        "cron_label_en": cron_en, "cron_label_zh": cron_zh,
        "recipients_en": rec_en, "recipients_zh": rec_zh,
        "content_en": content_en, "content_zh": content_zh,
        "law_reference": law, "last_run_at": last, "next_run_at": nxt,
        "sort_order": i,
    } for i, (rtype, icon, name_en, name_zh, cron_en, cron_zh, rec_en, rec_zh,
              content_en, content_zh, law, last, nxt) in enumerate([
        ("monthly_staffing_compliance", "📊",
         "Monthly Staffing Compliance Report", "月度人手合規報告",
         "1st of every month, 08:00", "每月1日 08:00",
         ["Home Manager", "Assistant Home Manager"], ["院長", "助理院長"],
         ["Actual FT/PT headcount per shift vs Cap.459A minimum",
          "PT ratio statistics for specific-hour A/P shifts",
          "Staff over the monthly AN limit",
          "CL accrual hours and estimated liability",
          "SL/DSL days and agency replacement cost",
          "External workforce dependency and fairness Gini"],
         ["各更次 FT/PT 實際人數 vs Cap.459A 最低要求",
          "特定鐘點 A/P 更 PT 比例統計",
          "AN 超限員工名單",
          "CL 積壓時數及財務負債估算",
          "SL/DSL 日數及外購替更成本",
          "外購人手依賴度及公平度 Gini"],
         "Cap.459A s.11(1)(3)", "2026-07-01", "2026-08-01"),
        ("compliance_summary", "📋",
         "Quarterly Service Quality Report (SQS)", "季度服務質素報告（SQS）",
         "First day of every quarter, 08:00", "每季首日 08:00",
         ["Home Manager", "Assistant Home Manager", "SWD"], ["院長", "助理院長", "社署"],
         ["Staffing ratio pass rate and breach minutes",
          "Unresolved hard-constraint violations",
          "Threshold monitor status across all six checks"],
         ["人手比率達標率及違規分鐘", "未解決硬約束違規", "六項閾值監控狀態"],
         "SQS 3.2", "2026-07-01", "2026-10-01"),
        ("staff_register", "🏛️",
         "Annual Licence Declaration", "年度牌照申報",
         "1 January every year, 08:00", "每年1月1日 08:00",
         ["Home Manager", "Licensing Office"], ["院長", "牌照處"],
         ["RCH staff list (Annex 3.2 format)",
          "Rank, employment type and unit for every staff member",
          "Certificate register with expiry dates",
          "Medication-audit status per staff"],
         ["安老院員工名單（附件3.2格式）", "每名員工職級、僱用類別及所屬單位",
          "證書登記及到期日", "各員工藥物審核資格"],
         "Cap.459A s.9.6", "2026-01-01", "2027-01-01"),
    ])])

    ins_many("event_trigger_rules", [{
        "facility_id": facility_id, "trigger_code": code, "icon": icon,
        "label_en": label_en, "label_zh": label_zh, "action_en": action_en,
        "action_zh": action_zh, "sla_en": sla_en, "sla_zh": sla_zh,
        "law_reference": law, "sort_order": i,
    } for i, (code, icon, label_en, label_zh, action_en, action_zh,
              sla_en, sla_zh, law) in enumerate([
        ("STAFF_JOIN_LEAVE", "👤", "Staff Joining / Leaving", "員工入職/離職",
         "Auto-update SWD staff list + notify Licensing Office",
         "自動更新社署員工名單 + 通知牌照處",
         "Within 1 working day", "1個工作天內", "Cap.459A s.9.6"),
        ("INCIDENT_REPORTED", "🚨", "Notifiable Incident", "特別事故登記",
         "Generate pre-filled Annex 8.3 draft + remind 24h reporting deadline",
         "生成附件8.3預填草稿 + 提醒24小時通報時限",
         "Immediate", "即時", "Cap.459A s.8.3"),
        ("INFECTION_OUTBREAK", "🦠", "Infection Control Event", "感染控制事件",
         "Activate infection control protocol + generate Annex 13.2 + alert staff",
         "啟動感染控制流程 + 生成附件13.2呈報表 + 通知相關員工",
         "Immediate", "即時", "Cap.459A s.13 / Cap.599"),
        ("RESIDENT_ADMISSION", "🛏️", "Resident Admission", "住客入住",
         "Create individual care plan reminder + auto-prompt review after 6 months",
         "建立個人照顧計劃提醒 + 6個月後自動提示更新",
         "Day of admission", "入住當日", "Cap.459A s.12"),
    ])])


def seed_facility_events(facility_id: str, ref: Date) -> None:
    ins_many("facility_events", [{
        "facility_id": facility_id, "event_type": etype,
        "date": (ref - timedelta(days=ago)).isoformat(), "title": title,
    } for etype, ago, title in [
        ("STAFF_JOIN_LEAVE", 21, "PCW joined - imported labour contract"),
        ("STAFF_JOIN_LEAVE", 6, "PTA resigned - 1 month notice"),
        ("RESIDENT_ADMISSION", 18, "New resident - East Wing"),
        ("RESIDENT_ADMISSION", 12, "New resident - West Wing"),
        ("RESIDENT_ADMISSION", 4, "New resident - East Wing"),
    ]])
    operational = [
        ("hair_cutting", 0, "Hair cutting", "09:00", "12:00",
         [("CW|HCA", 1, True)]),
        ("CGAT", 1, "Geriatric outreach", "09:00", "12:00",
         [("RN", 1, True), ("HW", 1, True)]),
        ("medication_record_checking", 2, "Medication record checking",
         "09:00", "17:00", [("EN", 1, True), ("HW", 1, True)]),
        ("podiatry", 3, "Podiatry", "09:00", "12:00",
         [("HW", 1, False), ("CW|HCA", 1, False)]),
        ("monthly_weighing", 4, "Monthly weighing", "09:00", "12:00",
         [("CW|HCA", 1, False)]),
    ]
    for event_type, days_ago, title, start, end, requirements in operational:
        day = ref - timedelta(days=days_ago)
        start_hour, start_minute = map(int, start.split(":"))
        end_hour, end_minute = map(int, end.split(":"))
        event_id = ins("facility_events", {
            "facility_id": facility_id, "event_type": event_type,
            "date": day.isoformat(), "start_at": ts(day, start_hour, start_minute),
            "end_at": ts(day, end_hour, end_minute), "title": title,
            "required_staffing_json": [
                {"rank": rank, "count": count, "is_additive": additive}
                for rank, count, additive in requirements
            ],
        })
        ins_many("event_staffing_requirements", [{
            "facility_id": facility_id, "event_id": event_id, "rank": rank,
            "count": count, "is_additive": additive,
        } for rank, count, additive in requirements])


def seed_regulatory_docs() -> None:
    ins_many("regulatory_documents", [{
        "facility_id": None, "doc_code": code, "name_en": name_en, "name_zh": name_zh,
        "key_clause_en": clause_en, "key_clause_zh": clause_zh,
        "version_label": version, "last_synced_at": synced, "sync_status": "synced",
        "sort_order": i,
    } for i, (code, name_en, name_zh, clause_en, clause_zh, version, synced) in enumerate([
        ("CAP459A", "Residential Care Homes (Elderly Persons) Regulation Cap.459A",
         "《安老院規例》Cap.459A", "s.11(3) PT headcount cap", "s.11(3) PT人數上限",
         "2024-06-16", "2024-06-16"),
        ("COP_2024", "Code of Practice for RCH(E) - June 2024 Revision",
         "《安老院實務守則》2024年6月修訂版", "Chapter 9: Agency Services",
         "第9章 外購服務", "2024-06", "2026-04-01"),
        ("SQS_16", "SWD 16 Service Quality Standards", "社署16項服務質素標準",
         "SQS 8: Legal Compliance", "SQS 8 法律合規", "2026", "2026-04-01"),
        ("LSG_TIPS", "LSG SmartTips April 2026 Edition", "LSG SmartTips 2026年4月版",
         "Recognised / Non-recognised Items", "認可/不認可項目", "2026-04", "2026-04-01"),
    ])])


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print("Wiping demo facilities + dev users ...")
    wipe()

    dates_a = dates_for(PERIOD_A_START, PERIOD_A_DAYS)
    dates_b = dates_for(PERIOD_B_START, PERIOD_B_DAYS)
    period_a_start, period_a_end = Date.fromisoformat(dates_a[0]), Date.fromisoformat(dates_a[-1])
    today = Date.today()
    # Anchor the Phase 3 activity inside the period so "today" always has data.
    ref = today if period_a_start <= today <= period_a_end else period_a_end

    # ---- calendar (global HK public holiday) ----
    # SQL: delete from calendar_days where date = '2026-07-01' and facility_id is null
    sb.table("calendar_days").delete().eq("date", "2026-07-01").is_("facility_id", "null").execute()
    ins("calendar_days", {
        "facility_id": None, "date": "2026-07-01", "day_type": "public_holiday",
        "holiday_name": "HKSAR Establishment Day", "is_agency_allowed": True,
        "staff_cost_multiplier": 2.0,
    })
    seed_regulatory_docs()

    # ================= HOME A (28-day cycle) =================
    print("Seeding Home A ...")
    fa = ins("facilities", {
        "code": "A", "name": "Care Home A (救世軍式)", "type": "RCHE",
        "scheduling_cycle_days": 28, "capacity": 85,
    })
    east = ins("facility_units", {"facility_id": fa, "unit_type": "wing", "name": "East Wing", "code": "EW"})
    west = ins("facility_units", {"facility_id": fa, "unit_type": "wing", "name": "West Wing", "code": "WW"})

    a_staff = [
        ("余逸詩", "Yu Yat Sze", "RN", "local_ft", east, "F"),
        ("梁嘉琪", "Leung Ka Kei", "EN", "local_ft", west, "F"),
        ("王雅琛", "Wong Yat Sum", "HW", "local_ft", east, "F"),
        ("何啟晴", "Ho Kai Ching", "CW", "local_ft", west, "F"),
        ("黃司琦", "Wong Sze Kai", "PTA", "local_ft", east, "M"),
        ("黃靜賢", "Wong Jing Yin", "PCW", "imported_labor", west, "F"),
        ("李紹洪", "Li Shao Hung", "AW", "local_ft", east, "M"),
    ]
    a_ids, a_ranks, a_units = [], [], []
    for name, en, rank, emp, unit, gender in a_staff:
        sid = ins("staff", {
            "facility_id": fa, "name": name, "name_en": en, "rank": rank,
            "employment_type": emp, "primary_unit_id": unit, "gender": gender,
            "contracted_hours": 44, "is_audited_for_medication": rank in ("RN", "EN", "HW"),
            "is_mentor": rank == "RN", "status": "active",
        })
        ins("staff_contracts", {
            "facility_id": fa, "staff_id": sid, "weekly_hours": 44,
            "max_weekly_hours": 54, "min_rest_minutes": 720 if emp == "imported_labor" else 660,
            "allowed_shift_types": ["A", "B", "E", "P", "N", "AN"],
            "effective_from": "2026-01-01",
        })
        a_ids.append(sid); a_ranks.append(rank); a_units.append(unit)

    # per-staff certificates with expiry (feeds Staff Portfolio credentials +
    # Compliance "Certifications" expiry tracking). Dates around 2026-07 give a mix
    # of expiring-soon and far-off for a realistic compliance view.
    a_certs = [
        [("ACLS", "2026-08-10"), ("Triage", "2027-01-15"), ("BLS", "2026-08-01")],  # RN
        [("First Aid", "2026-08-20"), ("Manual Handling", "2027-03-01")],           # EN
        [("Elder Care", "2026-09-30"), ("Vitals", "2026-08-15")],                   # HW
        [("Personal Care", "2027-06-30")],                                          # CW
        [("Rehab Tech", "2026-11-05")],                                             # PTA
        [("Bathing", "2026-08-28"), ("Transfer", "2027-02-01")],                    # PCW
        [("Infection Control", "2027-01-20")],                                      # AW
    ]
    ins_many("staff_certificates", [
        {"facility_id": fa, "staff_id": a_ids[i], "cert_type": c, "expiry_date": exp}
        for i, certs in enumerate(a_certs) for (c, exp) in certs
    ])
    seed_staff_qualifications(fa, a_ids, a_ranks)

    seed_shift_defs(fa, [
        ("A", "Morning", "07:00", "15:00", False, True),
        ("B", "Morning B", "08:00", "16:00", False, True),
        ("E", "Morning E", "09:00", "17:00", False, True),
        ("P", "Afternoon", "13:30", "21:30", False, True),
        ("N", "Night", "21:30", "07:00", True, True),
        ("AN", "A/N split", "07:00", "13:30", True, True),
        ("PT", "Part-time", "09:00", "17:48", False, True),
        ("OFF", "Day Off", None, None, False, False),
        ("AL", "Annual Leave", None, None, False, False),
        ("SLEEP", "Sleeping Day", None, None, False, False),
        ("DO", "Rest Day", None, None, False, False),
        ("CL", "Compensatory Leave", None, None, False, False),
    ], SPLIT_A)
    seed_ratio_rules(fa, "A")
    seed_phase5_rules(fa, "A")
    seed_task_definitions(fa)

    period_a = ins("roster_periods", {
        "facility_id": fa, "period_start": dates_a[0], "period_end": dates_a[-1],
        "cycle_type": "28day", "status": "planning",
    })
    ver_a = ins("roster_versions", {
        "facility_id": fa, "period_id": period_a, "version_type": "manual",
        "label": "July 2026 draft", "status": "draft",
    })
    seed_leave_balances(fa, period_a, a_ids)
    cycles_a = seed_forward_cycles(
        fa, "28day", period_a_end, PERIOD_A_DAYS, a_ids,
        horizon=max(today, period_a_end) + timedelta(days=FORWARD_CYCLE_DAYS))
    roster_a = seed_roster(fa, ver_a, a_ids, a_ranks, a_units, PATTERN_A,
                           SHIFT_TIMES_A, SPLIT_A, TASKS_A, dates_a)
    current_a = roster_cycle_covering(
        fa, cycles_a, today, "Current cycle draft",
        staff_ids=a_ids, ranks=a_ranks, units=a_units, pattern=PATTERN_A,
        times=SHIFT_TIMES_A, splits=SPLIT_A, task_map=TASKS_A)
    rosters_a = [(roster_a, dates_a)]
    if current_a:
        # Today now sits on a real roster, so hang the Phase 3 activity off today
        # instead of the stale cycle's last day.
        ref = today
        rosters_a.append((current_a.pop("roster"), current_a["dates"]))

    def shift_lookup_a(staff_id: str, day: Date) -> str | None:
        """The staff member's working shift id on `day`, else None."""
        want = day.isoformat()
        for roster, dates in rosters_a:
            for shift_id, (i, sid, d, code) in zip(roster["shift_ids"], roster["meta"]):
                if sid == staff_id and dates[d] == want and SHIFT_TIMES_A[code][3]:
                    return shift_id
        return None

    # ================= HOME B (natural month) =================
    print("Seeding Home B ...")
    fb = ins("facilities", {
        "code": "B", "name": "Care Home B (多層院舍)", "type": "RCHE",
        "scheduling_cycle_days": 31, "capacity": 60,
    })
    f1 = ins("facility_units", {"facility_id": fb, "unit_type": "floor", "name": "1/F", "code": "1F"})
    f2 = ins("facility_units", {"facility_id": fb, "unit_type": "floor", "name": "2/F", "code": "2F"})
    f6 = ins("facility_units", {"facility_id": fb, "unit_type": "floor", "name": "6/F", "code": "6F"})
    b_staff = [
        ("陳大文", "Chan Tai Man", "HCA", "imported_labor", f2, "M"),
        ("李美娟", "Li Mei Kuen", "HW", "local_ft", f6, "F"),
        ("王志強", "Wong Chi Keung", "EN", "local_ft", f6, "M"),
    ]
    b_ids, b_ranks, b_units = [], [], []
    for name, en, rank, emp, unit, gender in b_staff:
        sid = ins("staff", {
            "facility_id": fb, "name": name, "name_en": en, "rank": rank,
            "employment_type": emp, "primary_unit_id": unit, "gender": gender,
            "contracted_hours": 49.5 if emp == "local_ft" else 72, "status": "active",
        })
        b_ids.append(sid); b_ranks.append(rank); b_units.append(unit)
    seed_staff_qualifications(fb, b_ids, b_ranks)

    seed_shift_defs(fb, [
        ("7A", "7A 12h", "07:00", "19:00", False, True),
        ("9A", "9A 12h", "09:00", "21:00", False, True),
        ("7P", "7P night", "19:00", "07:00", True, True),
        ("A", "Morning", "07:00", "16:00", False, True),
        ("P", "Afternoon", "12:30", "21:30", False, True),
        ("AN", "A/N split", "07:00", "14:30", True, True),
        ("PT", "Part-time", "09:00", "18:00", False, True),
        ("OFF", "Day Off", None, None, False, False),
        ("DO", "Rest Day", None, None, False, False),
        ("AL", "Annual Leave", None, None, False, False),
        ("SLEEP", "Sleeping Day", None, None, False, False),
        ("CL", "Compensatory Leave", None, None, False, False),
    ], SPLIT_B)
    seed_ratio_rules(fb, "B")
    seed_phase5_rules(fb, "B")
    seed_task_definitions(fb)
    seed_floor_rules(fb, {"1F": f1, "2F": f2, "6F": f6})

    period_b = ins("roster_periods", {
        "facility_id": fb, "period_start": dates_b[0], "period_end": dates_b[-1],
        "cycle_type": "natural_month", "status": "planning",
    })
    ver_b = ins("roster_versions", {
        "facility_id": fb, "period_id": period_b, "version_type": "manual",
        "label": "July 2026 draft", "status": "draft",
    })
    seed_leave_balances(fb, period_b, b_ids)
    period_b_end = Date.fromisoformat(dates_b[-1])
    cycles_b = seed_forward_cycles(
        fb, "natural_month", period_b_end, PERIOD_B_DAYS, b_ids,
        horizon=max(today, period_b_end) + timedelta(days=FORWARD_CYCLE_DAYS))
    seed_roster(fb, ver_b, b_ids, b_ranks, b_units, PATTERN_B, SHIFT_TIMES_B, SPLIT_B, {}, dates_b)
    current_b = roster_cycle_covering(
        fb, cycles_b, today, "Current cycle draft",
        staff_ids=b_ids, ranks=b_ranks, units=b_units, pattern=PATTERN_B,
        times=SHIFT_TIMES_B, splits=SPLIT_B, task_map={})

    # ---- auth users + profiles ----
    print("Creating dev auth users ...")
    super_a = make_user("super_a@emma.local", "superintendent", fa)
    make_user("admin_a@emma.local", "admin", fa)
    make_user("staff_a@emma.local", "staff", fa, staff_id=a_ids[0])
    make_user("super_b@emma.local", "superintendent", fb)

    # SQL: select id from users_profile where auth_user_id = :super_a
    prof_a = sb.table("users_profile").select("id").eq("auth_user_id", super_a).execute().data[0]["id"]
    # Resident counts are the ratio denominator, so they have to be plausible for
    # the seeded headcount: 7 staff cannot lawfully serve 80 residents under the
    # Code of Practice ratios, and an impossible fixture makes every compliance
    # screen fail for a reason that has nothing to do with the roster. 18 residents
    # across two wings leaves a realistic mix - most windows pass, and the genuine
    # gaps (nobody on an RN's rest day, 21:30–07:00 covered by one person) show up.
    # The newly rostered current cycle needs the same denominator, or every ratio
    # check for today divides by nothing.
    seed_resident_counts(fa, [(east, 10), (west, 8)], prof_a,
                         dates_a + (current_a["dates"] if current_a else []))
    seed_resident_counts(fb, [(f2, 8), (f6, 7)], prof_a,
                         dates_b + (current_b["dates"] if current_b else []))

    # ---- Phase 3 operations layer (Home A carries the demo activity) ----
    print("Seeding Phase 3 operations data ...")
    seed_roi_settings(fa, prof_a, total_budget=1_600_000, salary_budget=1_190_800,
                      vacancies={"RN": 1, "HCA": 2})
    seed_roi_settings(fb, prof_a, total_budget=900_000, salary_budget=640_000,
                      vacancies={})
    seed_leave_requests(fa, a_ids, prof_a, ref)
    seed_incidents(fa, a_ids, prof_a, ref, shift_lookup_a)
    seed_agency(fa, ref)
    seed_attendance(fa, a_ids[0], ref)
    seed_debt(fa, a_ids, period_a)
    seed_notifications(fa, a_ids[0], prof_a)
    seed_report_registry(fa)
    seed_facility_events(fa, ref)

    print("\nSeed complete.")
    print("  Roster: %s .. %s (%d days), Home B %d days"
          % (dates_a[0], dates_a[-1], len(dates_a), len(dates_b)))
    print("  Dev logins (password: %s):" % DEV_PASSWORD)
    print("    super_a@emma.local  (Superintendent, Home A)")
    print("    admin_a@emma.local  (Admin, Home A)")
    print("    staff_a@emma.local  (Staff app, Home A - 余逸詩 / Yu Yat Sze)")
    print("    super_b@emma.local  (Superintendent, Home B)")


if __name__ == "__main__":
    main()
