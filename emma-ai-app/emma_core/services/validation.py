"""Phase 5 deterministic roster validation.

The optimizer, manual roster editor and publish workflow all use this module as
their compliance source of truth.  Evaluators are pure where practical; the
PostgREST orchestration only loads one immutable roster snapshot, records a
validation run, and persists structured evidence.

AI may explain these results in Phase 6, but it must never change them.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass, fields
from datetime import date as Date, datetime as DateTime, time as Time, timedelta, timezone
from typing import Iterable, Mapping

from ..constants import can_cover_rank
from ..shifttime import envelope, paid_minutes, to_minutes
from . import compliance, scheduling


PHASE5_RULE_CODES = frozenset({
    "required_coverage",
    "swd_ratio",
    "one_staff_no_overlap",
    "min_rest",
    "max_hours",
    "assignment_eligibility",
    "approved_leave_unavailable",
    "night_chain",
    "night_monthly_limit",
    "night_cooldown",
    "agency_ban",
    "agency_cap",
    "part_time_restriction",
    "leave_quota",
    "leave_balance",
})

EXTERNAL_AGENCY_TYPES = frozenset({"agency", "outsource", "casual"})
INTERNAL_FULL_TIME_TYPES = frozenset({"local_ft", "imported_labor"})
PREFERENCE_LEAVE_TYPES = frozenset({"DO", "duty_request"})
PEAK_HOLIDAY_TERMS = (
    "mid-autumn",
    "mid autumn",
    "winter solstice",
    "lunar new year",
    "農曆新年",
    "中秋",
    "冬至",
)

DEFAULT_NIGHT_POLICY = {
    "night_shift_types": ["AN", "N"],
    "chain_employment_types": ["local_ft"],
    "sleep_codes": ["SLEEP", "SD"],
    "day_off_codes": ["DO", "OFF"],
    "an_monthly_limit": 2,
    "nurse_night_monthly_limit": 2,
    "cooldown_ranks": ["RN", "EN"],
}

DEFAULT_AGENCY_POLICY = {
    "agency_employment_types": sorted(EXTERNAL_AGENCY_TYPES),
    "banned_shift_types": ["N", "AN", "7P"],
    "period_ratio_cap": 0.5,
    "daily_rank_caps": {"RN|EN|HW": 2, "CW|HCA": 12},
    "monthly_shift_caps": {},
    "peak_holiday_terms": list(PEAK_HOLIDAY_TERMS),
}

DEFAULT_LEAVE_POLICY = {
    "request_cutoff_day": 10,
    "max_do_cl_balance": 3,
}

LEAVE_PRIORITY = {
    "AL": ("urgent", "Previously approved annual leave"),
    "PH": ("urgent", "Public/statutory holiday entitlement"),
    "medical_fu": ("high", "Medical follow-up"),
    "CL": ("high", "Compensatory leave"),
    "DO": ("normal", "Preferred day off"),
    "duty_request": ("normal", "Preferred duty"),
}
LEAVE_PRIORITY_WEIGHT = {
    "AL": 100,
    "PH": 90,
    "medical_fu": 80,
    "CL": 70,
    "DO": 50,
    "duty_request": 40,
}


@dataclass(frozen=True, slots=True)
class RosterSnapshot:
    facility_id: str
    roster_version_id: str
    period_id: str | None
    period_start: Date
    period_end: Date
    facility: dict
    version_content_updated_at: str | None = None
    shifts: tuple[dict, ...] = ()
    assignments: tuple[dict, ...] = ()
    staff: tuple[dict, ...] = ()
    facility_units: tuple[dict, ...] = ()
    task_definitions: tuple[dict, ...] = ()
    task_assignments: tuple[dict, ...] = ()
    staff_qualifications: tuple[dict, ...] = ()
    facility_events: tuple[dict, ...] = ()
    event_staffing_requirements: tuple[dict, ...] = ()
    floor_min_staffing_rules: tuple[dict, ...] = ()
    contracts: tuple[dict, ...] = ()
    leave_requests: tuple[dict, ...] = ()
    leave_balances: tuple[dict, ...] = ()
    calendar_days: tuple[dict, ...] = ()
    resident_counts: tuple[dict, ...] = ()
    ratio_rules: tuple[dict, ...] = ()
    rule_definitions: tuple[dict, ...] = ()
    future_debts: tuple[dict, ...] = ()
    prior_night_assignments: tuple[dict, ...] = ()
    roi_settings: dict | None = None

    @property
    def period_days(self) -> int:
        return (self.period_end - self.period_start).days + 1


def _as_date(value) -> Date:
    if isinstance(value, DateTime):
        return value.date()
    if isinstance(value, Date):
        return value
    return Date.fromisoformat(str(value)[:10])


def _iso_now() -> str:
    return DateTime.now(timezone.utc).isoformat()


def _rank_expression_matches(actual: str | None, expression: str) -> bool:
    required = {
        value.strip() for value in expression.upper().split("|") if value.strip()
    }
    if not required:
        return True
    # A pipe expression is an explicit allow-list (for example CW|HCA).
    # A single rank keeps the normal seniority substitution ladder.
    if len(required) > 1:
        return str(actual or "").upper() in required
    return can_cover_rank(
        str(actual or "").upper(),
        next(iter(required)),
    )


def _rank_group_matches(actual: str | None, expression: str) -> bool:
    """Exact rank-group membership for quota/cap buckets."""
    return str(actual or "").upper() in {
        value.strip() for value in expression.upper().split("|") if value.strip()
    }


def _effective_rule_rows(snapshot: RosterSnapshot, rule_code: str) -> list[dict]:
    """Select the policy effective when this roster period begins.

    Ratio rules are evaluated day-by-day because statutory windows can change
    mid-period. Operational night/agency/leave policy is intentionally frozen at
    the period boundary so validation and optimization use the same version.
    """
    candidates = [
        row for row in snapshot.rule_definitions
        if row.get("rule_code") == rule_code
        and row.get("active", True)
        and (row.get("facility_id") in (None, snapshot.facility_id))
        and (
            not row.get("effective_from")
            or _as_date(row["effective_from"]) <= snapshot.period_start
        )
        and (
            not row.get("effective_to")
            or _as_date(row["effective_to"]) >= snapshot.period_start
        )
    ]
    candidates.sort(key=lambda row: (
        row.get("facility_id") == snapshot.facility_id,
        int(row.get("config_version") or 1),
        str(row.get("effective_from") or ""),
    ), reverse=True)
    return candidates


def _rule_config(
    snapshot: RosterSnapshot,
    rule_code: str,
    defaults: dict,
) -> tuple[dict, str | None, str]:
    rows = _effective_rule_rows(snapshot, rule_code)
    if not rows:
        return dict(defaults), None, "hard"
    config = dict(defaults)
    config.update(rows[0].get("config_json") or {})
    return (
        config,
        rows[0].get("id"),
        str(rows[0].get("severity") or "hard"),
    )


def _violation(
    rule_code: str,
    message: str,
    *,
    shift_id: str | None = None,
    staff_id: str | None = None,
    on_date: Date | str | None = None,
    unit_id: str | None = None,
    rule_definition_id: str | None = None,
    severity: str = "hard",
    details: dict | None = None,
) -> dict:
    return {
        "rule_code": rule_code,
        "shift_id": shift_id,
        "staff_id": staff_id,
        "date": str(on_date)[:10] if on_date else None,
        "unit_id": unit_id,
        "rule_definition_id": rule_definition_id,
        "severity": severity,
        "message": message,
        "details": details or {},
        "resolved": False,
    }


def _active_assignments(snapshot: RosterSnapshot, *, working_only: bool = False):
    shift_by_id = {row["id"]: row for row in snapshot.shifts}
    staff_by_id = {row["id"]: row for row in snapshot.staff}
    for assignment in snapshot.assignments:
        if assignment.get("status") == "cancelled":
            continue
        shift = shift_by_id.get(assignment.get("shift_id"))
        if not shift or (working_only and not shift.get("is_working", True)):
            continue
        yield assignment, shift, staff_by_id.get(assignment.get("staff_id"))


def _contract_by_staff(snapshot: RosterSnapshot) -> dict[str, dict]:
    candidates: dict[str, list[dict]] = defaultdict(list)
    for row in snapshot.contracts:
        if (
            row.get("effective_from")
            and _as_date(row["effective_from"]) > snapshot.period_end
        ):
            continue
        if (
            row.get("effective_to")
            and _as_date(row["effective_to"]) < snapshot.period_start
        ):
            continue
        candidates[row["staff_id"]].append(row)
    return {
        staff_id: sorted(
            rows,
            key=lambda row: (
                str(row.get("effective_from") or ""),
                str(row.get("created_at") or ""),
            ),
        )[-1]
        for staff_id, rows in candidates.items()
    }


def _absolute_shift_interval(shift: dict) -> tuple[DateTime, DateTime] | None:
    interval = envelope(shift)
    if not interval:
        return None
    start_min, end_min, crosses = interval
    day = _as_date(shift["date"])
    start = DateTime.combine(day, Time.min) + timedelta(minutes=start_min)
    end = DateTime.combine(day, Time.min) + timedelta(minutes=end_min)
    if crosses or end <= start:
        end += timedelta(days=1)
    return start, end


def evaluate_core_constraints(snapshot: RosterSnapshot) -> list[dict]:
    """Coverage, overlap, rest, hours, assignment eligibility and approved leave."""
    violations: list[dict] = []
    staff_by_id = {row["id"]: row for row in snapshot.staff}
    contract_by_staff = _contract_by_staff(snapshot)

    assignments_by_shift: dict[str, list[dict]] = defaultdict(list)
    shifts_by_staff: dict[str, list[dict]] = defaultdict(list)
    for assignment, shift, staff in _active_assignments(snapshot):
        assignments_by_shift[shift["id"]].append(assignment)
        if staff and shift.get("is_working", True):
            shifts_by_staff[staff["id"]].append(shift)

    # Required count is meaningful for generated demand slots and unassigned
    # manual slots.  Phase 4 overlays/floor rules are evaluated separately.
    for shift in snapshot.shifts:
        if not shift.get("is_working", True):
            continue
        required = int(shift.get("required_count") or 1)
        actual = len({
            row.get("staff_id") or f"agency:{row.get('id')}"
            for row in assignments_by_shift.get(shift["id"], [])
        })
        if actual < required:
            violations.append(_violation(
                "required_coverage",
                f"{shift.get('shift_type')} requires {required} staff; {actual} assigned.",
                shift_id=shift["id"],
                on_date=shift["date"],
                unit_id=shift.get("unit_id"),
                details={"required": required, "actual": actual},
            ))

    approved = [
        row for row in snapshot.leave_requests
        if row.get("status") == "approved"
        # A requested duty is a positive scheduling preference, not leave from
        # work. Treat only actual time-off rows as hard unavailability.
        and row.get("leave_type") not in {"duty_request", "shift_swap"}
    ]
    approved_by_staff: dict[str, list[dict]] = defaultdict(list)
    for row in approved:
        approved_by_staff[row["staff_id"]].append(row)

    for assignment, shift, staff in _active_assignments(snapshot, working_only=True):
        if not staff:
            continue
        staff_id = staff["id"]
        contract = contract_by_staff.get(staff_id, {})
        required_rank = shift.get("required_rank") or assignment.get("role")
        if (
            required_rank
            and not _rank_expression_matches(staff.get("rank"), required_rank)
        ):
            violations.append(_violation(
                "assignment_eligibility",
                f"{staff.get('rank')} cannot cover a {required_rank} assignment.",
                shift_id=shift["id"],
                staff_id=staff_id,
                on_date=shift["date"],
                unit_id=shift.get("unit_id"),
                details={
                    "required_rank": required_rank,
                    "actual_rank": staff.get("rank"),
                },
            ))
        allowed = set(contract.get("allowed_shift_types") or ())
        if allowed and shift.get("shift_type") not in allowed:
            violations.append(_violation(
                "assignment_eligibility",
                f"{shift.get('shift_type')} is not allowed by this staff contract.",
                shift_id=shift["id"],
                staff_id=staff_id,
                on_date=shift["date"],
                unit_id=shift.get("unit_id"),
                details={
                    "shift_type": shift.get("shift_type"),
                    "allowed_shift_types": sorted(allowed),
                },
            ))
        if (
            shift.get("requires_medication")
            and not staff.get("is_audited_for_medication")
        ):
            violations.append(_violation(
                "assignment_eligibility",
                "Medication duty requires an audited staff member.",
                shift_id=shift["id"],
                staff_id=staff_id,
                on_date=shift["date"],
                unit_id=shift.get("unit_id"),
                details={"required": "medication_audited"},
            ))

        day = _as_date(shift["date"])
        occupied_days = {day}
        interval = _absolute_shift_interval(shift)
        if interval:
            occupied_day = interval[0].date()
            final_day = (interval[1] - timedelta(microseconds=1)).date()
            while occupied_day <= final_day:
                occupied_days.add(occupied_day)
                occupied_day += timedelta(days=1)
        for request in approved_by_staff.get(staff_id, ()):
            leave_start = _as_date(request["date_start"])
            leave_end = _as_date(request["date_end"])
            overlap_days = sorted(
                value for value in occupied_days
                if leave_start <= value <= leave_end
            )
            if overlap_days:
                violations.append(_violation(
                    "approved_leave_unavailable",
                    f"Staff is assigned during approved {request.get('leave_type')} leave.",
                    shift_id=shift["id"],
                    staff_id=staff_id,
                    on_date=overlap_days[0],
                    unit_id=shift.get("unit_id"),
                    details={
                        "leave_request_id": request.get("id"),
                        "overlap_dates": [
                            value.isoformat() for value in overlap_days
                        ],
                    },
                ))
                break

    for staff_id, shifts in shifts_by_staff.items():
        contract = contract_by_staff.get(staff_id, {})
        employment = staff_by_id.get(staff_id, {}).get("employment_type")
        default_rest = 720 if employment == "imported_labor" else 660
        minimum_rest = int(contract.get("min_rest_minutes") or default_rest)
        if employment == "imported_labor":
            minimum_rest = max(720, minimum_rest)
        intervals = [
            (interval[0], interval[1], shift)
            for shift in shifts
            if (interval := _absolute_shift_interval(shift))
        ]
        intervals.sort(key=lambda row: (row[0], row[1], row[2]["id"]))
        for index, (start, end, shift) in enumerate(intervals):
            for next_start, next_end, next_shift in intervals[index + 1:]:
                gap = round((next_start - end).total_seconds() / 60)
                if next_start < end:
                    violations.append(_violation(
                        "one_staff_no_overlap",
                        "One staff member has overlapping shift assignments.",
                        shift_id=next_shift["id"],
                        staff_id=staff_id,
                        on_date=next_shift["date"],
                        unit_id=next_shift.get("unit_id"),
                        details={
                            "previous_shift_id": shift["id"],
                            "previous_end": end.isoformat(),
                            "next_start": next_start.isoformat(),
                        },
                    ))
                    continue
                if gap < minimum_rest:
                    violations.append(_violation(
                        "min_rest",
                        f"Rest gap is {gap} minutes; contract requires {minimum_rest}.",
                        shift_id=next_shift["id"],
                        staff_id=staff_id,
                        on_date=next_shift["date"],
                        unit_id=next_shift.get("unit_id"),
                        details={
                            "previous_shift_id": shift["id"],
                            "gap_minutes": gap,
                            "required_minutes": minimum_rest,
                        },
                    ))
                    continue
                break

        max_weekly = contract.get("max_weekly_hours")
        if max_weekly:
            actual_minutes = sum(paid_minutes(shift) for shift in shifts)
            maximum_minutes = round(
                float(max_weekly) * snapshot.period_days / 7 * 60
            )
            if actual_minutes > maximum_minutes:
                violations.append(_violation(
                    "max_hours",
                    (
                        f"Scheduled {round(actual_minutes / 60, 2)}h exceeds "
                        f"the period cap of {round(maximum_minutes / 60, 2)}h."
                    ),
                    staff_id=staff_id,
                    details={
                        "actual_minutes": actual_minutes,
                        "maximum_minutes": maximum_minutes,
                        "period_days": snapshot.period_days,
                    },
                ))
    return violations


def _resident_rows_by_date(snapshot: RosterSnapshot) -> dict[str, list[dict]]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in snapshot.resident_counts:
        by_date[str(row["date"])[:10]].append(row)
    return by_date


def evaluate_swd_ratios(snapshot: RosterSnapshot) -> tuple[list[dict], list[dict]]:
    """Return (violations, audit-grade minute rows) for every roster day."""
    shift_by_id = {row["id"]: row for row in snapshot.shifts if row.get("is_working", True)}
    assignments_by_date: dict[str, list[dict]] = defaultdict(list)
    shifts_by_date: dict[str, dict[str, dict]] = defaultdict(dict)
    for assignment in snapshot.assignments:
        if assignment.get("status") == "cancelled":
            continue
        shift = shift_by_id.get(assignment.get("shift_id"))
        if not shift:
            continue
        key = str(shift["date"])[:10]
        assignments_by_date[key].append(assignment)
        shifts_by_date[key][shift["id"]] = shift

    residents_by_date = _resident_rows_by_date(snapshot)
    rows: list[dict] = []
    violations: list[dict] = []
    day = snapshot.period_start
    while day <= snapshot.period_end:
        key = day.isoformat()
        day_rows = compliance._minute_eval(
            list(snapshot.ratio_rules),
            residents_by_date.get(key, []),
            shifts_by_date.get(key, {}),
            assignments_by_date.get(key, []),
            key,
        )
        rows.extend(day_rows)
        for row in day_rows:
            if row["passes"]:
                continue
            violations.append(_violation(
                "swd_ratio",
                (
                    f"{row['label']} is below the statutory minimum for "
                    f"{row['breach_minutes']} minute(s)."
                ),
                on_date=key,
                unit_id=row.get("unit_id"),
                details={
                    "ratio_rule_id": row.get("rule_id"),
                    "required": row["required"],
                    "min_actual": row["min_actual"],
                    "breach_minutes": row["breach_minutes"],
                    "window_start": row["window_start"],
                    "window_end": row["window_end"],
                    "residents": row["residents"],
                    "segments": row["segments"],
                },
            ))
        day += timedelta(days=1)
    return violations, rows


def evaluate_night_rules(snapshot: RosterSnapshot) -> list[dict]:
    policy, rule_id, severity = _rule_config(
        snapshot,
        "night_chain",
        DEFAULT_NIGHT_POLICY,
    )
    night_types = {str(value).upper() for value in policy["night_shift_types"]}
    chain_employment = set(policy["chain_employment_types"])
    sleep_codes = {str(value).upper() for value in policy["sleep_codes"]}
    day_off_codes = {str(value).upper() for value in policy["day_off_codes"]}
    cooldown_ranks = {str(value).upper() for value in policy["cooldown_ranks"]}
    an_limit = int(policy.get("an_monthly_limit") or 0)
    nurse_limit = int(policy.get("nurse_night_monthly_limit") or 0)

    staff_by_id = {row["id"]: row for row in snapshot.staff}
    shifts_by_staff_day: dict[str, dict[Date, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for _assignment, shift, staff in _active_assignments(snapshot):
        if staff:
            shifts_by_staff_day[staff["id"]][_as_date(shift["date"])].append(shift)

    violations: list[dict] = []
    for staff_id, by_day in shifts_by_staff_day.items():
        staff = staff_by_id[staff_id]
        employment = staff.get("employment_type")
        monthly_an: dict[tuple[int, int], list[dict]] = defaultdict(list)
        monthly_nurse_nights: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for day, shifts in by_day.items():
            for shift in shifts:
                code = str(shift.get("shift_type") or "").upper()
                if code == "AN":
                    monthly_an[(day.year, day.month)].append(shift)
                if code in night_types and staff.get("rank") in cooldown_ranks:
                    monthly_nurse_nights[(day.year, day.month)].append(shift)
                if code not in night_types or employment not in chain_employment:
                    continue
                next_day = day + timedelta(days=1)
                third_day = day + timedelta(days=2)
                next_types = {
                    str(row.get("shift_type") or "").upper()
                    for row in by_day.get(next_day, ())
                }
                third_types = {
                    str(row.get("shift_type") or "").upper()
                    for row in by_day.get(third_day, ())
                }
                missing = []
                if (
                    next_day <= snapshot.period_end
                    and not (next_types & sleep_codes)
                ):
                    missing.append({
                        "offset_days": 1,
                        "required": sorted(sleep_codes),
                        "actual": sorted(next_types),
                    })
                if (
                    third_day <= snapshot.period_end
                    and not (third_types & day_off_codes)
                ):
                    missing.append({
                        "offset_days": 2,
                        "required": sorted(day_off_codes),
                        "actual": sorted(third_types),
                    })
                if missing:
                    violations.append(_violation(
                        "night_chain",
                        f"{code} must be followed by a sleeping day and day off.",
                        shift_id=shift["id"],
                        staff_id=staff_id,
                        on_date=day,
                        unit_id=shift.get("unit_id"),
                        rule_definition_id=rule_id,
                        severity=severity,
                        details={"missing": missing},
                    ))

        for month, shifts in monthly_an.items():
            if an_limit and len(shifts) > an_limit:
                violations.append(_violation(
                    "night_monthly_limit",
                    f"AN assignments exceed the monthly limit of {an_limit}.",
                    shift_id=shifts[an_limit]["id"],
                    staff_id=staff_id,
                    on_date=shifts[an_limit]["date"],
                    rule_definition_id=rule_id,
                    severity=severity,
                    details={
                        "year": month[0],
                        "month": month[1],
                        "actual": len(shifts),
                        "limit": an_limit,
                    },
                ))
        if staff.get("rank") in cooldown_ranks:
            for month, shifts in monthly_nurse_nights.items():
                if nurse_limit and len(shifts) > nurse_limit:
                    violations.append(_violation(
                        "night_monthly_limit",
                        f"Nurse night assignments exceed the monthly limit of {nurse_limit}.",
                        shift_id=shifts[nurse_limit]["id"],
                        staff_id=staff_id,
                        on_date=shifts[nurse_limit]["date"],
                        rule_definition_id=rule_id,
                        severity=severity,
                        details={
                            "year": month[0],
                            "month": month[1],
                            "actual": len(shifts),
                            "limit": nurse_limit,
                        },
                    ))

    prior_night_staff = {
        row["staff_id"] for row in snapshot.prior_night_assignments
        if row.get("staff_id")
        and str(row.get("rank") or "").upper() in cooldown_ranks
    }
    cooldown_debt_staff = {
        row["staff_id"] for row in snapshot.future_debts
        if row.get("debt_type") == "NIGHT_COOLDOWN"
        and row.get("status") == "open"
        and (
            not row.get("due_period_id")
            or row.get("due_period_id") == snapshot.period_id
        )
    }
    blocked_staff = prior_night_staff | cooldown_debt_staff
    for assignment, shift, staff in _active_assignments(snapshot, working_only=True):
        if (
            staff
            and staff["id"] in blocked_staff
            and staff.get("rank") in cooldown_ranks
            and str(shift.get("shift_type") or "").upper() in night_types
        ):
            violations.append(_violation(
                "night_cooldown",
                "Nurse is in the mandatory next-period night cooldown.",
                shift_id=shift["id"],
                staff_id=staff["id"],
                on_date=shift["date"],
                unit_id=shift.get("unit_id"),
                rule_definition_id=rule_id,
                severity=severity,
                details={"source": "prior_roster_or_debt"},
            ))
    return violations


def _calendar_by_date(snapshot: RosterSnapshot) -> dict[str, dict]:
    """Facility calendar row overrides a global row for the same date."""
    out: dict[str, dict] = {}
    for row in sorted(
        snapshot.calendar_days,
        key=lambda item: item.get("facility_id") == snapshot.facility_id,
    ):
        out[str(row["date"])[:10]] = row
    return out


def _is_peak_holiday(row: dict | None, terms: Iterable[str]) -> bool:
    if not row:
        return False
    text = " ".join(
        str(row.get(key) or "") for key in ("holiday_name", "day_type", "notes")
    ).casefold()
    return any(str(term).casefold() in text for term in terms)


def evaluate_agency_rules(snapshot: RosterSnapshot) -> list[dict]:
    policy, rule_id, severity = _rule_config(
        snapshot,
        "agency_limits",
        DEFAULT_AGENCY_POLICY,
    )
    agency_types = {str(value) for value in policy["agency_employment_types"]}
    banned_shift_types = {
        str(value).upper() for value in policy["banned_shift_types"]
    }
    peak_terms = policy.get("peak_holiday_terms") or PEAK_HOLIDAY_TERMS
    calendar = _calendar_by_date(snapshot)
    external: list[tuple[dict, dict, dict | None]] = []
    internal_ft = 0
    for assignment, shift, staff in _active_assignments(snapshot, working_only=True):
        employment = staff.get("employment_type") if staff else None
        if assignment.get("is_agency") or employment in agency_types:
            external.append((assignment, shift, staff))
        elif employment in INTERNAL_FULL_TIME_TYPES:
            internal_ft += 1

    violations: list[dict] = []
    for assignment, shift, staff in external:
        day_key = str(shift["date"])[:10]
        cal = calendar.get(day_key)
        banned_reasons = []
        if not (cal or {}).get("is_agency_allowed", True):
            banned_reasons.append("calendar_day")
        if str(shift.get("shift_type") or "").upper() in banned_shift_types:
            banned_reasons.append("shift_type")
        if _is_peak_holiday(cal, peak_terms):
            banned_reasons.append("peak_holiday")
        if banned_reasons:
            violations.append(_violation(
                "agency_ban",
                "Agency staff is assigned to a prohibited shift or date.",
                shift_id=shift["id"],
                staff_id=(staff or {}).get("id"),
                on_date=shift["date"],
                unit_id=shift.get("unit_id"),
                rule_definition_id=rule_id,
                severity=severity,
                details={
                    "assignment_id": assignment.get("id"),
                    "reasons": banned_reasons,
                },
            ))

    ratio = float(policy.get("period_ratio_cap") or 0)
    if ratio:
        period_cap = math.floor(internal_ft * ratio)
        if len(external) > period_cap:
            violations.append(_violation(
                "agency_cap",
                (
                    f"Agency volume is {len(external)}; the period cap is "
                    f"{period_cap} ({ratio:g} of internal full-time assignments)."
                ),
                rule_definition_id=rule_id,
                severity=severity,
                details={
                    "actual": len(external),
                    "cap": period_cap,
                    "internal_full_time_assignments": internal_ft,
                    "ratio": ratio,
                },
            ))

    daily_caps = policy.get("daily_rank_caps") or {}
    per_day: dict[str, list[tuple[dict, dict, dict | None]]] = defaultdict(list)
    for row in external:
        per_day[str(row[1]["date"])[:10]].append(row)
    for day, rows in per_day.items():
        for expression, cap_value in daily_caps.items():
            cap = int(cap_value)
            matches = [
                row for row in rows
                if _rank_group_matches(
                    (row[2] or {}).get("rank") or row[0].get("role"),
                    expression,
                )
            ]
            if len(matches) > cap:
                violations.append(_violation(
                    "agency_cap",
                    f"{day} agency {expression} count {len(matches)} exceeds {cap}.",
                    on_date=day,
                    rule_definition_id=rule_id,
                    severity=severity,
                    details={
                        "rank_expression": expression,
                        "actual": len(matches),
                        "cap": cap,
                    },
                ))

    for shift_type, cap_value in (policy.get("monthly_shift_caps") or {}).items():
        cap = int(cap_value)
        by_month: dict[tuple[int, int], list] = defaultdict(list)
        for row in external:
            if (
                str(row[1].get("shift_type") or "").upper()
                != str(shift_type).upper()
            ):
                continue
            day = _as_date(row[1]["date"])
            by_month[(day.year, day.month)].append(row)
        for (year, month), matches in sorted(by_month.items()):
            if len(matches) <= cap:
                continue
            violations.append(_violation(
                "agency_cap",
                (
                    f"Agency {shift_type} volume {len(matches)} exceeds "
                    f"the monthly cap of {cap}."
                ),
                rule_definition_id=rule_id,
                severity=severity,
                details={
                    "shift_type": str(shift_type).upper(),
                    "year": year,
                    "month": month,
                    "actual": len(matches),
                    "cap": cap,
                },
            ))

    vacancy_policy = policy.get("vacancy_cap") or {}
    if vacancy_policy.get("enabled") and snapshot.roi_settings:
        vacancies = sum(
            max(0, int(value))
            for value in (snapshot.roi_settings.get("vacancies_json") or {}).values()
        )
        holidays = {
            str(row["date"])[:10] for row in snapshot.calendar_days
            if str(row.get("day_type") or "") in {
                "public_holiday", "statutory_holiday", "special_pay"
            }
        }
        standard_do = int(vacancy_policy.get("standard_do_days") or 6)
        factor = float(vacancy_policy.get("factor") or 0.7)
        vacancy_cap = math.floor(
            max(0, vacancies * (snapshot.period_days - standard_do - len(holidays)))
            * factor
        )
        if len(external) > vacancy_cap:
            violations.append(_violation(
                "agency_cap",
                (
                    f"Agency volume {len(external)} exceeds the vacancy-based "
                    f"cap of {vacancy_cap}."
                ),
                rule_definition_id=rule_id,
                severity=severity,
                details={
                    "actual": len(external),
                    "cap": vacancy_cap,
                    "vacancies": vacancies,
                    "period_days": snapshot.period_days,
                    "holiday_days": len(holidays),
                    "standard_do_days": standard_do,
                    "factor": factor,
                },
            ))
    return violations


def evaluate_part_time_rules(snapshot: RosterSnapshot) -> list[dict]:
    """Validate facility-specific PT windows, days and compensatory leave."""
    policy, rule_id, severity = _rule_config(
        snapshot,
        "agency_limits",
        DEFAULT_AGENCY_POLICY,
    )
    part_time = policy.get("part_time_policy") or {}
    employment_types = {
        str(value) for value in part_time.get("employment_types", ())
    }
    if not employment_types:
        return []

    allowed_weekdays = {
        int(value) for value in part_time.get("allowed_weekdays", ())
    }
    required_start = (
        to_minutes(part_time.get("required_start"))
        if part_time.get("required_start") else None
    )
    required_end = (
        to_minutes(part_time.get("required_end"))
        if part_time.get("required_end") else None
    )
    staff_by_id = {
        row["id"]: row
        for row in snapshot.staff
        if row.get("employment_type") in employment_types
    }
    if not staff_by_id:
        return []

    working_by_staff_day: dict[str, dict[Date, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    codes_by_staff_day: dict[str, dict[Date, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    violations: list[dict] = []

    for _assignment, shift, staff in _active_assignments(snapshot):
        if not staff or staff["id"] not in staff_by_id:
            continue
        staff_id = staff["id"]
        day = _as_date(shift["date"])
        code = str(shift.get("shift_type") or "").upper()
        codes_by_staff_day[staff_id][day].add(code)
        if not shift.get("is_working", True):
            continue
        working_by_staff_day[staff_id][day].append(shift)

        if allowed_weekdays and day.weekday() not in allowed_weekdays:
            violations.append(_violation(
                "part_time_restriction",
                "Part-time staff is assigned on a prohibited weekday.",
                shift_id=shift["id"],
                staff_id=staff_id,
                on_date=day,
                unit_id=shift.get("unit_id"),
                rule_definition_id=rule_id,
                severity=severity,
                details={
                    "actual_weekday": day.weekday(),
                    "allowed_weekdays": sorted(allowed_weekdays),
                },
            ))

        span = envelope(shift)
        if (
            required_start is not None
            and required_end is not None
            and (
                not span
                or span[0] != required_start
                or span[1] != required_end
                or span[2]
            )
        ):
            violations.append(_violation(
                "part_time_restriction",
                "Part-time shift does not match the required fixed hours.",
                shift_id=shift["id"],
                staff_id=staff_id,
                on_date=day,
                unit_id=shift.get("unit_id"),
                rule_definition_id=rule_id,
                severity=severity,
                details={
                    "required_start": part_time.get("required_start"),
                    "required_end": part_time.get("required_end"),
                    "actual_start": shift.get("start_time"),
                    "actual_end": shift.get("end_time"),
                },
            ))

    credited_leave_by_staff: dict[str, set[Date]] = defaultdict(set)
    approved_cl_by_staff: dict[str, set[Date]] = defaultdict(set)
    for request in snapshot.leave_requests:
        staff_id = request.get("staff_id")
        if (
            request.get("status") != "approved"
            or staff_id not in staff_by_id
            or request.get("leave_type") in {"duty_request", "shift_swap"}
        ):
            continue
        day = max(snapshot.period_start, _as_date(request["date_start"]))
        end = min(snapshot.period_end, _as_date(request["date_end"]))
        while day <= end:
            credited_leave_by_staff[staff_id].add(day)
            if str(request.get("leave_type") or "").upper() == "CL":
                approved_cl_by_staff[staff_id].add(day)
            day += timedelta(days=1)
    for staff_id, by_day in codes_by_staff_day.items():
        for day, codes in by_day.items():
            if codes & {"AL", "PH", "CL", "SL", "DSL"}:
                credited_leave_by_staff[staff_id].add(day)
            if (
                "CL" in codes
                and day in working_by_staff_day.get(staff_id, {})
            ):
                violations.append(_violation(
                    "part_time_restriction",
                    "Compensatory leave cannot overlap a working assignment.",
                    staff_id=staff_id,
                    on_date=day,
                    rule_definition_id=rule_id,
                    severity=severity,
                    details={"leave_type": "CL"},
                ))

    def check_work_day_window(
        staff_id: str,
        window_start: Date,
        window_days: int,
        bounds: dict | None,
        label: str,
    ) -> None:
        if not bounds:
            return
        minimum = max(0, int(bounds.get("min") or 0))
        maximum = max(minimum, int(bounds.get("max") or minimum))
        days = [
            window_start + timedelta(days=offset)
            for offset in range(window_days)
        ]
        actual = sum(
            day in working_by_staff_day.get(staff_id, {})
            for day in days
        )
        credited_leave = sum(
            day in credited_leave_by_staff.get(staff_id, set())
            for day in days
            if day not in working_by_staff_day.get(staff_id, {})
            and (
                not allowed_weekdays
                or day.weekday() in allowed_weekdays
            )
        )
        effective = actual + credited_leave
        if effective >= minimum and actual <= maximum:
            return
        violations.append(_violation(
            "part_time_restriction",
            f"Part-time {label} work-day requirement is not satisfied.",
            staff_id=staff_id,
            on_date=window_start,
            rule_definition_id=rule_id,
            severity=severity,
            details={
                "window": label,
                "window_start": window_start.isoformat(),
                "window_end": days[-1].isoformat(),
                "actual_work_days": actual,
                "credited_leave_days": credited_leave,
                "effective_days": effective,
                "minimum_work_days": minimum,
                "maximum_work_days": maximum,
            },
        ))

    for staff_id in staff_by_id:
        weekly = part_time.get("weekly_work_days")
        week_start = snapshot.period_start - timedelta(
            days=snapshot.period_start.weekday()
        )
        while week_start <= snapshot.period_end:
            window_start = max(snapshot.period_start, week_start)
            window_end = min(
                snapshot.period_end,
                week_start + timedelta(days=6),
            )
            window_days = (window_end - window_start).days + 1
            full_week = window_days == 7
            boundary_bounds = None
            if (
                not full_week
                and weekly
                and allowed_weekdays
                and int(weekly.get("min") or 0)
                == int(weekly.get("max") or 0)
                == len(allowed_weekdays)
            ):
                expected = sum(
                    (
                        window_start + timedelta(days=offset)
                    ).weekday() in allowed_weekdays
                    for offset in range(window_days)
                )
                boundary_bounds = {"min": expected, "max": expected}
            if full_week or boundary_bounds is not None:
                check_work_day_window(
                    staff_id,
                    window_start,
                    window_days,
                    weekly if full_week else boundary_bounds,
                    "weekly",
                )
            week_start += timedelta(days=7)

        fortnightly = part_time.get("fortnightly_work_days")
        block_start = snapshot.period_start
        while block_start + timedelta(days=13) <= snapshot.period_end:
            check_work_day_window(
                staff_id,
                block_start,
                14,
                fortnightly,
                "fortnightly",
            )
            block_start += timedelta(days=14)

        if not part_time.get("saturday_requires_weekday_cl"):
            continue
        for saturday in sorted(working_by_staff_day.get(staff_id, {})):
            if saturday.weekday() != 5:
                continue
            following_weekdays = [
                saturday + timedelta(days=offset)
                for offset in range(1, 7)
                if (
                    saturday + timedelta(days=offset) <= snapshot.period_end
                    and (saturday + timedelta(days=offset)).weekday() < 5
                )
            ]
            if any(
                (
                    "CL" in codes_by_staff_day.get(staff_id, {}).get(day, set())
                    or day in approved_cl_by_staff.get(staff_id, set())
                )
                and day not in working_by_staff_day.get(staff_id, {})
                for day in following_weekdays
            ):
                continue
            if not following_weekdays and any(
                row.get("staff_id") == staff_id
                and row.get("debt_type") == "CL"
                and row.get("status", "open") == "open"
                and (
                    (row.get("details_json") or {}).get("source_roster_version_id")
                    == snapshot.roster_version_id
                )
                and (
                    (row.get("details_json") or {}).get("source_saturday")
                    == saturday.isoformat()
                )
                for row in snapshot.future_debts
            ):
                continue
            violations.append(_violation(
                "part_time_restriction",
                "Saturday PT duty must be followed by weekday compensatory leave.",
                staff_id=staff_id,
                on_date=saturday,
                rule_definition_id=rule_id,
                severity=severity,
                details={
                    "required_leave_type": "CL",
                    "eligible_dates": [
                        day.isoformat() for day in following_weekdays
                    ],
                },
            ))
    return violations


def leave_priority(leave_type: str, reason: str | None = None) -> tuple[str, str]:
    code = str(leave_type)
    reason_text = (reason or "").casefold()
    if "medical" in reason_text or "覆診" in reason_text:
        return LEAVE_PRIORITY["medical_fu"]
    return LEAVE_PRIORITY.get(code, ("low", "Other request"))


def leave_priority_weight(leave_type: str, reason: str | None = None) -> int:
    reason_text = (reason or "").casefold()
    if "medical" in reason_text or "覆診" in reason_text:
        return LEAVE_PRIORITY_WEIGHT["medical_fu"]
    return LEAVE_PRIORITY_WEIGHT.get(str(leave_type), 20)


def _request_days_in_month(request: dict, year: int, month: int) -> int:
    start, end = _as_date(request["date_start"]), _as_date(request["date_end"])
    day = start
    count = 0
    while day <= end:
        if (day.year, day.month) == (year, month):
            count += 1
        day += timedelta(days=1)
    return count


def leave_request_policy_issues(
    *,
    request: dict,
    staff: dict,
    facility: dict,
    existing_requests: Iterable[dict],
    active_staff: Iterable[dict] = (),
    calendar_days: Iterable[dict] = (),
    assigned_night_shifts: Mapping[Date | str, str] | None = None,
    submitted_on: Date | None = None,
    enforce_cutoff: bool = True,
    policy: dict | None = None,
    policy_severity: str = "hard",
) -> list[dict]:
    """Pure request-policy check used before approval and in Phase 5 fixtures."""
    existing_requests = tuple(existing_requests)
    active_staff = tuple(active_staff)
    calendar_days = tuple(calendar_days)
    effective_policy = dict(DEFAULT_LEAVE_POLICY)
    effective_policy.update(policy or {})
    start, end = _as_date(request["date_start"]), _as_date(request["date_end"])
    if end < start:
        return [{"code": "invalid_date_range", "severity": "hard"}]
    issues: list[dict] = []
    leave_type = str(request.get("leave_type") or "")
    facility_code = str(facility.get("code") or "").upper()

    if enforce_cutoff and leave_type not in {"SL", "DSL", "urgent", "late"}:
        first = start.replace(day=1)
        previous_month_last = first - timedelta(days=1)
        cutoff = previous_month_last.replace(
            day=max(
                1,
                min(
                    int(effective_policy.get("request_cutoff_day") or 10),
                    previous_month_last.day,
                ),
            )
        )
        submitted = submitted_on or Date.today()
        if submitted > cutoff:
            issues.append({
                "code": "request_cutoff",
                "severity": policy_severity,
                "cutoff": cutoff.isoformat(),
                "submitted_on": submitted.isoformat(),
            })

    locked_nights = {
        _as_date(day): str(shift_type or "").upper()
        for day, shift_type in dict(assigned_night_shifts or {}).items()
    }
    overlapped_nights = {
        day: shift_type
        for day, shift_type in locked_nights.items()
        if start <= day <= end
    }
    # A duty request naming the very night already rostered is fulfilled by that
    # assignment, not in conflict with it - the anchor never moves.
    requested_shift = str(request.get("requested_shift_type") or "").upper()
    night_already_fulfilled = (
        leave_type == "duty_request"
        and bool(requested_shift)
        and all(
            shift_type == requested_shift
            for shift_type in overlapped_nights.values()
        )
    )
    # A true swap is the documented escape hatch for a pre-assigned night.
    # A normal duty request must not be able to move that hard night anchor.
    if (
        leave_type != "shift_swap"
        and overlapped_nights
        and not night_already_fulfilled
    ):
        issues.append({
            "code": "preassigned_night_locked",
            "severity": policy_severity,
        })

    calendar_by_date = {
        _as_date(row["date"]): row
        for row in calendar_days
        if row.get("date")
    }
    peak_dates = {
        day
        for day, row in calendar_by_date.items()
        if start <= day <= end
        and _is_peak_holiday(row, PEAK_HOLIDAY_TERMS)
    }
    if peak_dates and leave_type in {"AL", "PH"}:
        ballot_approved = bool(
            (request.get("policy_result_json") or {}).get("ballot_approved")
        )
        submitted = submitted_on or Date.today()
        late_dates = sorted(
            day for day in peak_dates
            if submitted > Date(day.year - 1, 9, 30)
        )
        if late_dates and not ballot_approved:
            ballot_deadline = Date(late_dates[0].year - 1, 9, 30)
            issues.append({
                "code": "high_demand_ballot_deadline",
                "severity": policy_severity,
                "deadline": ballot_deadline.isoformat(),
                "dates": [day.isoformat() for day in late_dates],
            })
        staff_rank_by_id = {
            row.get("id"): str(row.get("rank") or "")
            for row in active_staff
        }
        request_rank = str(staff.get("rank") or "")
        conflicts = []
        for row in existing_requests:
            if (
                row.get("id") == request.get("id")
                or row.get("status") in {"rejected", "cancelled"}
                or row.get("leave_type") in {"duty_request", "shift_swap"}
                or staff_rank_by_id.get(row.get("staff_id")) != request_rank
            ):
                continue
            other_start = _as_date(row["date_start"])
            other_end = _as_date(row["date_end"])
            overlap = sorted(
                day.isoformat()
                for day in peak_dates
                if other_start <= day <= other_end
            )
            if overlap:
                conflicts.append({
                    "leave_request_id": row.get("id"),
                    "staff_id": row.get("staff_id"),
                    "dates": overlap,
                })
        if conflicts:
            issues.append({
                "code": "high_demand_rank_conflict",
                "severity": policy_severity,
                "rank": request_rank,
                "conflicts": conflicts,
            })

    if leave_type in PREFERENCE_LEAVE_TYPES:
        existing = [
            row for row in existing_requests
            if row.get("staff_id") == staff.get("id")
            and row.get("id") != request.get("id")
            and row.get("leave_type") in PREFERENCE_LEAVE_TYPES
            and row.get("status") not in {"rejected", "cancelled"}
        ]
        rank = str(staff.get("rank") or "")
        month = start.replace(day=1)
        last_month = end.replace(day=1)
        while month <= last_month:
            month_key = (month.year, month.month)
            if facility_code == "B" and rank in {"HCA", "CW"}:
                statutory_days = len({
                    _as_date(row["date"])
                    for row in calendar_days
                    if _as_date(row["date"]).year == month.year
                    and _as_date(row["date"]).month == month.month
                    and row.get("day_type") in {
                        "public_holiday",
                        "statutory_holiday",
                    }
                })
                # Four regular DOs plus one statutory holiday = two requests;
                # a six-day-or-larger holiday pool permits three.
                quota = 3 if statutory_days >= 2 else 2
            elif facility_code == "B" and rank in {"EN", "HW"}:
                quota = 5
            else:
                quota = 4
            requested = sum(
                _request_days_in_month(row, *month_key) for row in existing
            ) + _request_days_in_month(request, *month_key)
            if requested > quota:
                issues.append({
                    "code": "monthly_request_quota",
                    "severity": policy_severity,
                    "requested_days": requested,
                    "quota": quota,
                    "year": month.year,
                    "month": month.month,
                })
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return issues


def leave_balance_issues(
    *,
    request: dict,
    balances: Iterable[dict],
    periods: Iterable[dict] = (),
) -> list[dict]:
    """Return a hard issue when a configured balance cannot fund a request.

    Historic installations have no balance rows, so absence intentionally
    remains non-blocking. Once a balance is configured, it becomes authoritative.
    """
    leave_type = str(request.get("leave_type") or "")
    balances = tuple(balances)
    periods = tuple(periods)
    matching = [
        row for row in balances
        if row.get("staff_id") == request.get("staff_id")
        and str(row.get("leave_type") or "") == leave_type
    ]
    if not matching:
        return []
    start = _as_date(request["date_start"])
    end = _as_date(request["date_end"])

    # A cross-period request must be funded by each period it touches. This
    # prevents a large balance in one month from silently subsidising another.
    bounded = [
        row for row in matching
        if row.get("period_start") and row.get("period_end")
    ]
    if bounded:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in bounded:
            grouped[str(row.get("period_id") or row.get("id"))].append(row)
        issues = []
        overlapping_periods = [
            row for row in periods
            if _as_date(row["period_start"]) <= end
            and _as_date(row["period_end"]) >= start
        ]
        if not overlapping_periods:
            overlapping_periods = [{
                "id": period_id,
                "period_start": rows[0]["period_start"],
                "period_end": rows[0]["period_end"],
            } for period_id, rows in grouped.items()]

        for period in overlapping_periods:
            period_id = str(period.get("id") or "")
            rows = grouped.get(period_id, [])
            overlap_start = max(start, _as_date(period["period_start"]))
            overlap_end = min(end, _as_date(period["period_end"]))
            if overlap_start > overlap_end:
                continue
            requested_days = (overlap_end - overlap_start).days + 1
            if not rows:
                issues.append({
                    "code": "insufficient_leave_balance",
                    "severity": "hard",
                    "leave_type": leave_type,
                    "period_id": period_id or None,
                    "period_start": period["period_start"],
                    "period_end": period["period_end"],
                    "requested_days": requested_days,
                    "available_days": 0,
                    "reason": "missing_period_balance",
                })
                continue
            overlap_start = max(start, _as_date(rows[0]["period_start"]))
            overlap_end = min(end, _as_date(rows[0]["period_end"]))
            if overlap_start > overlap_end:
                continue
            requested_days = (overlap_end - overlap_start).days + 1
            available = sum(
                float(row.get("opening_balance") or 0)
                + float(row.get("accrued") or 0)
                + float(row.get("carried") or 0)
                - float(row.get("used") or 0)
                for row in rows
            )
            if requested_days > available:
                issues.append({
                    "code": "insufficient_leave_balance",
                    "severity": "hard",
                    "leave_type": leave_type,
                    "period_id": period_id,
                    "period_start": rows[0]["period_start"],
                    "period_end": rows[0]["period_end"],
                    "requested_days": requested_days,
                    "available_days": available,
                })
        return issues

    requested_days = (end - start).days + 1
    available = sum(
        float(row.get("opening_balance") or 0)
        + float(row.get("accrued") or 0)
        + float(row.get("carried") or 0)
        - float(row.get("used") or 0)
        for row in matching
    )
    if requested_days <= available:
        return []
    return [{
        "code": "insufficient_leave_balance",
        "severity": "hard",
        "leave_type": leave_type,
        "requested_days": requested_days,
        "available_days": available,
    }]


def evaluate_leave_rules(snapshot: RosterSnapshot) -> list[dict]:
    policy, rule_id, severity = _rule_config(
        snapshot,
        "leave_rules",
        DEFAULT_LEAVE_POLICY,
    )
    violations: list[dict] = []
    active_staff = [
        row for row in snapshot.staff
        if row.get("status", "active") == "active"
    ]
    staff_by_id = {row["id"]: row for row in active_staff}
    night_shifts_by_staff: dict[str, dict[Date, str]] = defaultdict(dict)
    for _assignment, shift, staff in _active_assignments(
        snapshot, working_only=True
    ):
        shift_type = str(shift.get("shift_type") or "").upper()
        if staff and shift_type in {"AN", "N", "7P"}:
            night_shifts_by_staff[staff["id"]][_as_date(shift["date"])] = shift_type

    approved_requests = tuple(
        request for request in snapshot.leave_requests
        if request.get("status") == "approved"
    )
    for request in approved_requests:
        staff = staff_by_id.get(request.get("staff_id"))
        if not staff:
            continue
        created_at = request.get("created_at")
        issues = leave_request_policy_issues(
            request=request,
            staff=staff,
            facility=snapshot.facility,
            existing_requests=approved_requests,
            active_staff=active_staff,
            calendar_days=snapshot.calendar_days,
            assigned_night_shifts=night_shifts_by_staff.get(staff["id"], {}),
            submitted_on=_as_date(created_at) if created_at else None,
            enforce_cutoff=bool(created_at),
            policy=policy,
            policy_severity=severity,
        )
        for issue in issues:
            rule_code = (
                "leave_balance"
                if issue.get("code") == "insufficient_leave_balance"
                else "leave_quota"
            )
            violations.append(_violation(
                rule_code,
                f"Leave request violates policy: {issue.get('code')}.",
                staff_id=staff["id"],
                on_date=request.get("date_start"),
                rule_definition_id=rule_id,
                severity=str(issue.get("severity") or severity),
                details={
                    "leave_request_id": request.get("id"),
                    **issue,
                },
            ))
    approved_days: dict[tuple[str, str], int] = defaultdict(int)
    for request in snapshot.leave_requests:
        if request.get("status") != "approved" or not request.get("staff_id"):
            continue
        leave_type = str(request.get("leave_type") or "")
        if not leave_type:
            continue
        start = max(snapshot.period_start, _as_date(request["date_start"]))
        end = min(snapshot.period_end, _as_date(request["date_end"]))
        if start <= end:
            approved_days[(request["staff_id"], leave_type)] += (
                end - start
            ).days + 1
    balance_entitlement: dict[tuple[str, str], float] = defaultdict(float)
    balance_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in snapshot.leave_balances:
        key = (row.get("staff_id"), str(row.get("leave_type") or ""))
        if not key[0] or not key[1]:
            continue
        balance_entitlement[key] += (
            float(row.get("opening_balance") or 0)
            + float(row.get("accrued") or 0)
            + float(row.get("carried") or 0)
        )
        if row.get("id"):
            balance_ids[key].append(row["id"])
    for key, requested_days in approved_days.items():
        # No configured balance remains backward-compatible. Once configured,
        # aggregate approved requests cannot exceed the period entitlement even
        # if historic `used` data was imported incorrectly.
        if key not in balance_entitlement:
            continue
        entitlement = balance_entitlement[key]
        if requested_days <= entitlement:
            continue
        violations.append(_violation(
            "leave_balance",
            "Approved leave exceeds the configured period entitlement.",
            staff_id=key[0],
            rule_definition_id=rule_id,
            severity=severity,
            details={
                "leave_type": key[1],
                "approved_days": requested_days,
                "entitlement_days": entitlement,
                "leave_balance_ids": balance_ids[key],
            },
        ))

    max_balance = float(policy.get("max_do_cl_balance") or 3)
    do_cl_by_staff: dict[str, list[dict]] = defaultdict(list)
    for row in snapshot.leave_balances:
        if row.get("leave_type") in {"DO", "CL"} and row.get("staff_id"):
            do_cl_by_staff[row["staff_id"]].append(row)
    for staff_id, balance_rows in do_cl_by_staff.items():
        balance = sum(
            float(row.get("opening_balance") or 0)
            + float(row.get("accrued") or 0)
            + float(row.get("carried") or 0)
            - float(row.get("used") or 0)
            for row in balance_rows
        )
        if balance > max_balance:
            violations.append(_violation(
                "leave_balance",
                (
                    f"Combined DO/CL balance {balance:g} exceeds "
                    f"the limit of {max_balance:g} days."
                ),
                staff_id=staff_id,
                rule_definition_id=rule_id,
                severity=severity,
                details={
                    "leave_balance_ids": [
                        row.get("id") for row in balance_rows if row.get("id")
                    ],
                    "leave_types": sorted({
                        str(row.get("leave_type")) for row in balance_rows
                    }),
                    "balance": balance,
                    "limit": max_balance,
                },
            ))
    return violations


def _snapshot_digest(snapshot: RosterSnapshot) -> str:
    payload = {}
    for item in fields(snapshot):
        if item.name in {"facility_id", "roster_version_id"}:
            continue
        value = getattr(snapshot, item.name)
        if isinstance(value, tuple):
            value = sorted(
                value,
                key=lambda row: (
                    str(row.get("id") or "") if isinstance(row, dict) else "",
                    json.dumps(row, sort_keys=True, default=str),
                ),
            )
        payload[item.name] = value
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_prior_nights(
    client,
    facility_id: str,
    period_start: Date,
) -> list[dict]:
    prior_periods = (
        client.table("roster_periods")
        .select("*")
        .eq("facility_id", facility_id)
        .lt("period_end", period_start.isoformat())
        .order("period_end", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not prior_periods:
        return []
    versions = (
        client.table("roster_versions")
        .select("id")
        .eq("facility_id", facility_id)
        .eq("period_id", prior_periods[0]["id"])
        .eq("status", "published")
        .execute()
        .data
    )
    if not versions:
        return []
    shifts = (
        client.table("shifts")
        .select("id,date,shift_type")
        .eq("facility_id", facility_id)
        .in_("roster_version_id", [row["id"] for row in versions])
        .in_("shift_type", ["AN", "N", "7P"])
        .execute()
        .data
    )
    if not shifts:
        return []
    assignments = (
        client.table("shift_assignments")
        .select("shift_id,staff_id,status")
        .eq("facility_id", facility_id)
        .in_("shift_id", [row["id"] for row in shifts])
        .execute()
        .data
    )
    staff_ids = {row.get("staff_id") for row in assignments if row.get("staff_id")}
    staff = {}
    if staff_ids:
        staff = {
            row["id"]: row
            for row in (
                client.table("staff")
                .select("id,rank")
                .eq("facility_id", facility_id)
                .in_("id", list(staff_ids))
                .execute()
                .data
            )
        }
    shift_by_id = {row["id"]: row for row in shifts}
    return [
        {
            "staff_id": row["staff_id"],
            "rank": (staff.get(row["staff_id"]) or {}).get("rank"),
            **shift_by_id[row["shift_id"]],
        }
        for row in assignments
        if row.get("staff_id")
        and row.get("status") != "cancelled"
        and row.get("shift_id") in shift_by_id
    ]


def load_snapshot(client, facility_id: str, roster_version_id: str) -> RosterSnapshot:
    versions = (
        client.table("roster_versions")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("id", roster_version_id)
        .execute()
        .data
    )
    if not versions:
        raise ValueError("roster version not found")
    version = versions[0]
    periods = (
        client.table("roster_periods")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("id", version["period_id"])
        .execute()
        .data
    )
    if not periods:
        raise ValueError("roster period not found")
    period = periods[0]
    period_start = _as_date(period["period_start"])
    period_end = _as_date(period["period_end"])

    facilities = (
        client.table("facilities")
        .select("*")
        .eq("id", facility_id)
        .execute()
        .data
    )
    facility = facilities[0] if facilities else {"id": facility_id}
    shifts = (
        client.table("shifts")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("roster_version_id", roster_version_id)
        .execute()
        .data
    )
    assignments = []
    if shifts:
        assignments = (
            client.table("shift_assignments")
            .select("*")
            .eq("facility_id", facility_id)
            .in_("shift_id", [row["id"] for row in shifts])
            .execute()
            .data
        )
    staff = (
        client.table("staff")
        .select("*")
        .eq("facility_id", facility_id)
        .execute()
        .data
    )
    facility_units = (
        client.table("facility_units")
        .select("*")
        .eq("facility_id", facility_id)
        .execute()
        .data
    )
    task_definitions = (
        client.table("task_definitions")
        .select("*")
        .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
        .eq("active", True)
        .execute()
        .data
    )
    task_assignments = (
        client.table("task_assignments")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("roster_version_id", roster_version_id)
        .execute()
        .data
    )
    staff_qualifications = []
    if staff:
        staff_qualifications = (
            client.table("staff_qualifications")
            .select("*")
            .eq("facility_id", facility_id)
            .in_("staff_id", [row["id"] for row in staff])
            .eq("is_active", True)
            .execute()
            .data
        )
    facility_events = (
        client.table("facility_events")
        .select("*")
        .eq("facility_id", facility_id)
        .gte("date", period_start.isoformat())
        .lte("date", period_end.isoformat())
        .execute()
        .data
    )
    event_staffing_requirements = []
    if facility_events:
        event_staffing_requirements = (
            client.table("event_staffing_requirements")
            .select("*")
            .eq("facility_id", facility_id)
            .in_("event_id", [row["id"] for row in facility_events])
            .execute()
            .data
        )
    floor_min_staffing_rules = (
        client.table("floor_min_staffing_rules")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("active", True)
        .execute()
        .data
    )
    contracts = (
        client.table("staff_contracts")
        .select("*")
        .eq("facility_id", facility_id)
        .execute()
        .data
    )
    leave_requests = (
        client.table("leave_requests")
        .select("*")
        .eq("facility_id", facility_id)
        .lte("date_start", period_end.isoformat())
        .gte("date_end", period_start.isoformat())
        .execute()
        .data
    )
    leave_balances = []
    if version.get("period_id"):
        leave_balances = (
            client.table("leave_balances")
            .select("*")
            .eq("facility_id", facility_id)
            .eq("period_id", version["period_id"])
            .execute()
            .data
        )
    calendar_days = (
        client.table("calendar_days")
        .select("*")
        .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
        .gte("date", period_start.isoformat())
        .lte("date", period_end.isoformat())
        .execute()
        .data
    )
    resident_counts = (
        client.table("daily_resident_counts")
        .select("*")
        .eq("facility_id", facility_id)
        .gte("date", period_start.isoformat())
        .lte("date", period_end.isoformat())
        .execute()
        .data
    )
    ratio_rules = (
        client.table("staffing_ratio_rules")
        .select("*")
        .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
        .eq("active", True)
        .execute()
        .data
    )
    rule_definitions = (
        client.table("rule_definitions")
        .select("*")
        .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
        .eq("active", True)
        .execute()
        .data
    )
    future_debts = (
        client.table("future_debt_ledger")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("status", "open")
        .execute()
        .data
    )
    roi_rows = (
        client.table("roi_settings")
        .select("*")
        .eq("facility_id", facility_id)
        .execute()
        .data
    )
    return RosterSnapshot(
        facility_id=facility_id,
        roster_version_id=roster_version_id,
        period_id=version.get("period_id"),
        period_start=period_start,
        period_end=period_end,
        facility=facility,
        version_content_updated_at=version.get("content_updated_at"),
        shifts=tuple(shifts),
        assignments=tuple(assignments),
        staff=tuple(staff),
        facility_units=tuple(facility_units),
        task_definitions=tuple(task_definitions),
        task_assignments=tuple(task_assignments),
        staff_qualifications=tuple(staff_qualifications),
        facility_events=tuple(facility_events),
        event_staffing_requirements=tuple(event_staffing_requirements),
        floor_min_staffing_rules=tuple(floor_min_staffing_rules),
        contracts=tuple(contracts),
        leave_requests=tuple(leave_requests),
        leave_balances=tuple(leave_balances),
        calendar_days=tuple(calendar_days),
        resident_counts=tuple(resident_counts),
        ratio_rules=tuple(ratio_rules),
        rule_definitions=tuple(rule_definitions),
        future_debts=tuple(future_debts),
        prior_night_assignments=tuple(
            _load_prior_nights(client, facility_id, period_start)
        ),
        roi_settings=roi_rows[0] if roi_rows else None,
    )


def _persist_run(
    client,
    snapshot: RosterSnapshot,
    violations: list[dict],
    ratio_rows: list[dict],
    *,
    validated_by: str | None,
) -> tuple[str, str]:
    digest = _snapshot_digest(snapshot)
    run = (
        client.table("roster_validation_runs")
        .insert({
            "facility_id": snapshot.facility_id,
            "roster_version_id": snapshot.roster_version_id,
            "roster_digest": digest,
            "source_content_updated_at": snapshot.version_content_updated_at,
            "status": "running",
            "validated_by": validated_by,
        })
        .execute()
        .data[0]
    )
    run_id = run["id"]
    try:
        # Keep every run as evidence while ensuring dashboards count only the
        # current snapshot's unresolved findings.
        (
            client.table("violation_log")
            .update({"resolved": True})
            .eq("facility_id", snapshot.facility_id)
            .eq("roster_version_id", snapshot.roster_version_id)
            .eq("resolved", False)
            .execute()
        )
        rows = [{
            "facility_id": snapshot.facility_id,
            "roster_version_id": snapshot.roster_version_id,
            "validation_run_id": run_id,
            "rule_code": row["rule_code"],
            "shift_id": row.get("shift_id"),
            "staff_id": row.get("staff_id"),
            "date": row.get("date"),
            "unit_id": row.get("unit_id"),
            "task_assignment_id": row.get("task_assignment_id"),
            "event_id": row.get("event_id"),
            "rule_definition_id": row.get("rule_definition_id"),
            "severity": row.get("severity", "hard"),
            "message": row.get("message"),
            "details_json": row.get("details") or {},
            "resolved": False,
        } for row in violations]
        if rows:
            client.table("violation_log").insert(rows).execute()
        hard_count = sum(
            row.get("severity", "hard") == "hard" for row in violations
        )
        soft_count = len(violations) - hard_count
        client.table("roster_validation_runs").update({
            "status": "passed" if hard_count == 0 else "failed",
            "hard_violation_count": hard_count,
            "soft_violation_count": soft_count,
            "summary_json": {
                "violation_count": len(violations),
                "ratio_checks": len(ratio_rows),
                "ratio_breaches": sum(
                    not row["passes"] for row in ratio_rows
                ),
                "rule_codes": sorted({
                    row["rule_code"] for row in violations
                }),
            },
            "completed_at": _iso_now(),
        }).eq("id", run_id).execute()
    except Exception:  # noqa: BLE001 - preserve original persistence failure
        try:
            (
                client.table("roster_validation_runs")
                .update({"status": "error", "completed_at": _iso_now()})
                .eq("id", run_id)
                .execute()
            )
        except Exception:  # noqa: BLE001 - best-effort audit finalization
            pass
        raise
    return run_id, digest


def validate_roster(
    client,
    facility_id: str,
    roster_version_id: str,
    *,
    validated_by: str | None = None,
    persist: bool = True,
) -> dict:
    """Run the complete fresh Phase 4+5 ruleset for one roster version."""
    snapshot = load_snapshot(client, facility_id, roster_version_id)
    violations = evaluate_core_constraints(snapshot)
    if not any(row.get("is_working", True) for row in snapshot.shifts):
        violations.append(_violation(
            "required_coverage",
            "Roster has no working shifts.",
            details={"reason": "empty_roster"},
        ))
    ratio_violations, ratio_rows = evaluate_swd_ratios(snapshot)
    violations.extend(ratio_violations)
    violations.extend(evaluate_night_rules(snapshot))
    violations.extend(evaluate_agency_rules(snapshot))
    violations.extend(evaluate_part_time_rules(snapshot))
    violations.extend(evaluate_leave_rules(snapshot))
    violations.extend(
        scheduling.evaluate_roster_rules(
            shifts=snapshot.shifts,
            assignments=snapshot.assignments,
            staff=snapshot.staff,
            units=snapshot.facility_units,
            task_definitions=snapshot.task_definitions,
            task_assignments=snapshot.task_assignments,
            qualification_rows=snapshot.staff_qualifications,
            events=snapshot.facility_events,
            event_requirements=snapshot.event_staffing_requirements,
            floor_rules=snapshot.floor_min_staffing_rules,
        )
    )
    violations.sort(key=lambda row: (
        str(row.get("date") or ""),
        row["rule_code"],
        str(row.get("staff_id") or ""),
        str(row.get("shift_id") or ""),
    ))
    run_id = digest = None
    if persist:
        run_id, digest = _persist_run(
            client,
            snapshot,
            violations,
            ratio_rows,
            validated_by=validated_by,
        )
    hard_count = sum(row.get("severity", "hard") == "hard" for row in violations)
    ratio_checks = [{
        "label": row["label"],
        "rank": row.get("rank"),
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "residents": row["residents"],
        "required": row["required"],
        "actual": row["min_actual"],
        "passes": row["passes"],
    } for row in ratio_rows]
    return {
        "roster_version_id": roster_version_id,
        "method": "deterministic-phase5",
        "passes": hard_count == 0,
        "hard_violation_count": hard_count,
        "violations": violations,
        "ratio_checks": ratio_checks,
        "validation_run_id": run_id,
        "input_digest": digest,
    }


def list_rule_definitions(client, facility_id: str, *, rule_code: str | None = None) -> list[dict]:
    query = (
        client.table("rule_definitions")
        .select("*")
        .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
    )
    if rule_code:
        query = query.eq("rule_code", rule_code)
    return query.order("rule_code").order("config_version", desc=True).execute().data


def create_rule_definition(client, facility_id: str, payload: dict) -> dict:
    row = {
        **payload,
        "facility_id": facility_id,
        "updated_at": _iso_now(),
    }
    return client.table("rule_definitions").insert(row).execute().data[0]
