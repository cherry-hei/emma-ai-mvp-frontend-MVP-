"""DB boundary for the CP-SAT solver: loads a period into solver inputs, runs the
requested plan modes, and writes each option back as a roster version. Pass a
service-role client so the bulk writeback bypasses RLS.

Demand comes from working shifts of the latest ``manual`` version. Phase 5
policy data is loaded alongside it: approved leave, pending preferences,
versioned ratio rules, agency restrictions and night-recovery history.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date as Date, datetime, timedelta, timezone

from ..constants import JobStatus, PlanMode, RosterStatus, SolveStatus
from ..models import KpiSummary, OptimizeRequest, OptimizeResponse, RosterOption
from ..solver import (
    BaselineCell,
    DemandSlot,
    LockedAssignment,
    RatioRuleInput,
    ResidentCountInput,
    SolverInputs,
    SolverLimits,
    StaffInput,
    WorkPatternInput,
    build_and_solve,
    solve_pareto,
)
from ..solver.inputs import AgencyLimitsInput, PreferenceInput
from ..shifttime import duty_segments, envelope, paid_minutes
from ..solver.timeutils import to_minutes
from . import compliance, validation

_AUDIT_RANKS = {"RN", "EN", "HW"}      # slots of these ranks involve medication duty
_LEAVE_TYPES = {"AL"}                  # source cells meaning hard unavailability
_DEFAULT_NIGHT_POLICY = validation.DEFAULT_NIGHT_POLICY
_DEFAULT_AGENCY_POLICY = validation.DEFAULT_AGENCY_POLICY
_AGENCY_SHIFT_COST = {
    # Phase 3 seed baselines: HK$1,231 nursing / HK$957 care per eight-hour shift.
    "RN": 1231.0,
    "EN": 1231.0,
    "HW": 1231.0,
    "HCA": 957.0,
    "CW": 957.0,
    "PCW": 957.0,
    "AW": 957.0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_date(v) -> Date:
    return v if isinstance(v, Date) else Date.fromisoformat(str(v)[:10])


def _min_to_time(m: int | None) -> str | None:
    return None if m is None else f"{m // 60:02d}:{m % 60:02d}:00"


def _segments_json(segments) -> list[dict] | None:
    """Solver segments back to the jsonb shape stored on shifts."""
    if len(segments) <= 1:
        return None                                # ordinary contiguous shift
    return [{"start": _min_to_time(s)[:5], "end": _min_to_time(e)[:5]}
            for s, e, _ in segments]


def _clock_minutes(value, fallback: str) -> int:
    if not value:
        return int(to_minutes(fallback))
    text = str(value)
    if "T" in text:
        text = text.split("T", 1)[1]
    return int(to_minutes(text[:5]))


# ── load: DB rows -> pure SolverInputs ───────────────────────────────────────
def _json_value(value, expected_type, default):
    if isinstance(value, expected_type):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return default
        return parsed if isinstance(parsed, expected_type) else default
    return default


def _preference_weight(request: dict) -> int:
    policy_result = _json_value(request.get("policy_result_json"), dict, {})
    try:
        configured = int(policy_result.get("priority_weight") or 0)
    except (TypeError, ValueError):
        configured = 0
    if configured > 0:
        return configured
    return validation.leave_priority_weight(
        request.get("leave_type") or "",
        request.get("reason"),
    )


def _days(start: Date, end: Date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _effective_config(rows, facility_id: str, rule_code: str,
                      on_date: Date, defaults: dict) -> dict:
    candidates = [
        row for row in rows
        if row.get("rule_code") == rule_code
        and row.get("active", True)
        and row.get("facility_id") in (None, facility_id)
        and (
            not row.get("effective_from")
            or _as_date(row["effective_from"]) <= on_date
        )
        and (
            not row.get("effective_to")
            or _as_date(row["effective_to"]) >= on_date
        )
    ]
    if not candidates:
        return dict(defaults)
    candidates.sort(key=lambda row: (
        row.get("facility_id") == facility_id,
        int(row.get("config_version") or 1),
        str(row.get("effective_from") or ""),
    ), reverse=True)
    config = dict(defaults)
    config.update(_json_value(candidates[0].get("config_json"), dict, {}))
    return config


def _work_day_range(value) -> tuple[int, int] | None:
    if not isinstance(value, dict):
        return None
    try:
        minimum = int(value["min"])
        maximum = int(value["max"])
    except (KeyError, TypeError, ValueError):
        return None
    if minimum < 0 or maximum < minimum:
        return None
    return minimum, maximum


def _work_pattern(policy: dict, employment_type: str) -> WorkPatternInput:
    """Project a facility PT policy into immutable solver primitives."""
    enabled_types = {
        str(value) for value in policy.get("employment_types", ())
    }
    if employment_type not in enabled_types:
        return WorkPatternInput()

    required_start = policy.get("required_start")
    required_end = policy.get("required_end")
    required_window = None
    if required_start and required_end:
        required_window = (
            int(to_minutes(str(required_start))),
            int(to_minutes(str(required_end))),
        )

    allowed_weekdays = frozenset(
        value
        for value in policy.get("allowed_weekdays", ())
        if isinstance(value, int) and 0 <= value <= 6
    )
    return WorkPatternInput(
        allowed_weekdays=allowed_weekdays,
        required_shift_window=required_window,
        weekly_work_days=_work_day_range(policy.get("weekly_work_days")),
        fortnightly_work_days=_work_day_range(
            policy.get("fortnightly_work_days")
        ),
        saturday_requires_weekday_cl=bool(
            policy.get("saturday_requires_weekday_cl")
        ),
    )


def _calendar_by_date(rows, facility_id: str) -> dict[Date, dict]:
    """Facility calendar rows override a global template for the same date."""
    out: dict[Date, dict] = {}
    for row in sorted(rows, key=lambda item: item.get("facility_id") == facility_id):
        out[_as_date(row["date"])] = row
    return out


def _agency_allowed(calendar_row: dict | None, shift_type: str, policy: dict) -> bool:
    if calendar_row and not calendar_row.get("is_agency_allowed", True):
        return False
    if shift_type.upper() in {
        str(value).upper() for value in policy.get("banned_shift_types", ())
    }:
        return False
    holiday_text = " ".join(str((calendar_row or {}).get(field) or "")
                            for field in ("holiday_name", "notes")).lower()
    return not any(
        str(term).lower() in holiday_text
        for term in policy.get("peak_holiday_terms", ())
        if str(term).strip()
    )


def _ratio_rule_inputs(rows, facility_id: str,
                       period_start: Date, period_end: Date) -> list[RatioRuleInput]:
    """Select the same effective rule version as the compliance validator."""
    selected: dict[str, tuple[dict, set[Date]]] = {}
    for day in _days(period_start, period_end):
        for index, row in enumerate(compliance._effective_rules(rows, facility_id, day)):
            key = str(row.get("id") or (
                row.get("rule_code"), row.get("unit_id"), row.get("care_level"),
                row.get("staff_rank"), row.get("time_window_start"),
                row.get("time_window_end"), row.get("config_version"), index,
            ))
            selected.setdefault(key, (row, set()))[1].add(day)

    inputs: list[RatioRuleInput] = []
    for row, effective_dates in selected.values():
        counted_raw = _json_value(row.get("counted_ranks_json"), list, [])
        weights_raw = _json_value(row.get("rank_weights_json"), dict, {})
        weights: list[tuple[str, int]] = []
        for rank, value in weights_raw.items():
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(parsed) and parsed >= 0:
                weights.append((str(rank), round(parsed * 100)))
        counted = {str(rank) for rank in counted_raw if rank not in (None, "")}
        if not counted and weights:
            counted = {rank for rank, _weight in weights}
        inputs.append(RatioRuleInput(
            window_start_min=to_minutes(row["time_window_start"]),
            window_end_min=to_minutes(row["time_window_end"]),
            staff_rank=row.get("staff_rank"),
            unit_id=row.get("unit_id"),
            care_level=row.get("care_level"),
            ratio_residents_per_staff=row.get("ratio_residents_per_staff"),
            min_staff_any_rank=row.get("min_staff_any_rank"),
            counted_ranks=frozenset(counted),
            rank_weights=tuple(sorted(weights)),
            effective_dates=frozenset(effective_dates),
            rule_id=row.get("id"),
            config_version=int(row.get("config_version") or 1),
        ))
    return inputs


def _prior_night_history(client, facility_id: str, period_start: Date,
                         night_types: set[str]):
    prior_periods = [
        row for row in (
            client.table("roster_periods").select("*")
            .eq("facility_id", facility_id).execute().data
        )
        if _as_date(row["period_end"]) < period_start
    ]
    if not prior_periods:
        return Counter(), Counter(), set()
    prior = max(prior_periods, key=lambda row: _as_date(row["period_end"]))
    versions = (
        client.table("roster_versions").select("*")
        .eq("facility_id", facility_id).eq("period_id", prior["id"])
        .eq("status", "published").execute().data
    )
    if not versions:
        return Counter(), Counter(), set()
    shifts = (
        client.table("shifts").select("*")
        .eq("facility_id", facility_id)
        .in_("roster_version_id", [row["id"] for row in versions])
        .execute().data
    )
    shifts = [
        row for row in shifts
        if str(row.get("shift_type") or "").upper() in night_types
    ]
    if not shifts:
        return Counter(), Counter(), set()
    assignments = (
        client.table("shift_assignments").select("*")
        .eq("facility_id", facility_id)
        .in_("shift_id", [row["id"] for row in shifts])
        .execute().data
    )
    shift_by_id = {row["id"]: row for row in shifts}
    an_counts, night_counts, staff_ids = Counter(), Counter(), set()
    for assignment in assignments:
        if assignment.get("status") == "cancelled" or not assignment.get("staff_id"):
            continue
        shift = shift_by_id.get(assignment.get("shift_id"))
        if not shift:
            continue
        day = _as_date(shift["date"])
        key = (assignment["staff_id"], day.year, day.month)
        night_counts[key] += 1
        if str(shift.get("shift_type") or "").upper() == "AN":
            an_counts[key] += 1
        staff_ids.add(assignment["staff_id"])
    return an_counts, night_counts, staff_ids


def _source_version(client, facility_id, period_id, source_version_id):
    if source_version_id:
        # facility_id filter matters: with the RLS-bypassing service-role client, a
        # source_version_id from another facility would otherwise leak its roster.
        # SQL: select * from roster_versions
        #      where id = :source_version_id and facility_id = :facility_id
        #        and period_id = :period_id
        rows = (client.table("roster_versions").select("*")
                .eq("id", source_version_id)
                .eq("facility_id", facility_id)
                .eq("period_id", period_id)
                .execute().data)
        return rows[0] if rows else None
    # SQL: select * from roster_versions
    #      where facility_id = :facility_id
    #        and period_id = :period_id
    #        and version_type = 'manual'
    #      order by created_at desc
    #      limit 1
    rows = (client.table("roster_versions").select("*")
            .eq("facility_id", facility_id).eq("period_id", period_id)
            .eq("version_type", "manual").order("created_at", desc=True).limit(1).execute().data)
    return rows[0] if rows else None


def load_inputs(client, facility_id: str, period_id: str, *, source_version_id=None,
                include_staff_ids=None, exclude_staff_ids=None,
                locked_assignments=None) -> SolverInputs:
    # SQL: select * from roster_periods
    #      where id = :period_id and facility_id = :facility_id
    periods = (client.table("roster_periods").select("*")
               .eq("id", period_id).eq("facility_id", facility_id).execute().data)
    if not periods:
        raise ValueError(f"roster_period {period_id} not found")
    period = periods[0]
    period_start = _as_date(period["period_start"])
    period_end = _as_date(period["period_end"])
    facility_rows = (
        client.table("facilities").select("*").eq("id", facility_id).execute().data
    )
    facility_code = str((facility_rows[0] if facility_rows else {}).get("code") or "")

    src = _source_version(client, facility_id, period_id, source_version_id)
    if not src:
        raise ValueError("no source 'manual' roster version to derive demand from")

    # Flat facility-scoped reads together become SolverInputs. They are
    # deliberately unjoined: the solver wants whole tables in memory, not a
    # denormalised row set.
    #
    # SQL: select * from shifts where roster_version_id = :source_version_id
    shifts = client.table("shifts").select("*").eq("roster_version_id", src["id"]).execute().data
    shift_ids = [s["id"] for s in shifts]
    assigns = []
    if shift_ids:
        # SQL: select * from shift_assignments where shift_id = any(:shift_ids)
        assigns = (client.table("shift_assignments").select("*")
                   .in_("shift_id", shift_ids).execute().data)

    # SQL: select * from staff where facility_id = :facility_id and status = 'active'
    staff_rows = (client.table("staff").select("*")
                  .eq("facility_id", facility_id).eq("status", "active").execute().data)
    # SQL: select * from staff_contracts where facility_id = :facility_id
    contracts = client.table("staff_contracts").select("*").eq("facility_id", facility_id).execute().data
    contract_by_staff = {c["staff_id"]: c for c in contracts}
    # SQL: select * from staffing_ratio_rules
    #      where (facility_id = :facility_id or facility_id is null)   -- null = statutory
    #        and active = true
    rules = (client.table("staffing_ratio_rules").select("*")
             .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
             .eq("active", True).execute().data)
    rule_definitions = (
        client.table("rule_definitions").select("*")
        .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
        .eq("active", True).execute().data
    )
    leave_requests = (
        client.table("leave_requests").select("*")
        .eq("facility_id", facility_id)
        .lte("date_start", str(period_end))
        .gte("date_end", str(period_start))
        .execute().data
    )
    future_debts = (
        client.table("future_debt_ledger").select("*")
        .eq("facility_id", facility_id)
        .eq("status", "open")
        .execute().data
    )
    roi_rows = (
        client.table("roi_settings").select("*")
        .eq("facility_id", facility_id).limit(1).execute().data
    )
    # SQL: select * from daily_resident_counts
    #      where facility_id = :facility_id
    #        and date >= :period_start and date <= :period_end
    counts = (client.table("daily_resident_counts").select("*")
              .eq("facility_id", facility_id)
              .gte("date", str(period_start)).lte("date", str(period_end)).execute().data)
    # Phase 4 additive event requirements become independent demand slots. A
    # concurrent requirement (podiatry/weighing) stays a validation-only overlay.
    events = (client.table("facility_events").select("*")
              .eq("facility_id", facility_id)
              .gte("date", str(period_start)).lte("date", str(period_end))
              .execute().data)
    event_requirements = []
    if events:
        event_requirements = (
            client.table("event_staffing_requirements").select("*")
            .eq("facility_id", facility_id)
            .in_("event_id", [event["id"] for event in events])
            .execute().data
        )
    # SQL: select * from calendar_days
    #      where (facility_id = :facility_id or facility_id is null)
    # (unbounded by date - the whole calendar is pulled, then indexed by date below)
    calendar = (client.table("calendar_days").select("*")
                .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
                .gte("date", str(period_start)).lte("date", str(period_end))
                .execute().data)
    cal_by_date = _calendar_by_date(calendar, facility_id)

    night_policy = _effective_config(
        rule_definitions, facility_id, "night_chain", period_start,
        _DEFAULT_NIGHT_POLICY,
    )
    agency_policy = _effective_config(
        rule_definitions, facility_id, "agency_limits", period_start,
        _DEFAULT_AGENCY_POLICY,
    )
    part_time_policy = _json_value(
        agency_policy.get("part_time_policy"), dict, {}
    )
    vacancy_period_cap = None
    vacancy_policy = agency_policy.get("vacancy_cap") or {}
    if vacancy_policy.get("enabled") and roi_rows:
        vacancies_json = _json_value(
            roi_rows[0].get("vacancies_json"), dict, {}
        )
        vacancies = sum(
            max(0, int(value)) for value in vacancies_json.values()
        )
        holiday_dates = {
            _as_date(row["date"]) for row in calendar
            if str(row.get("day_type") or "") in {
                "public_holiday", "statutory_holiday", "special_pay",
            }
        }
        standard_do = int(vacancy_policy.get("standard_do_days") or 6)
        factor = float(vacancy_policy.get("factor") or 0.7)
        vacancy_period_cap = math.floor(
            max(
                0,
                vacancies * (
                    (period_end - period_start).days + 1
                    - standard_do
                    - len(holiday_dates)
                ),
            )
            * factor
        )
    agency_limits = AgencyLimitsInput(
        external_employment_types=frozenset(
            str(value) for value in agency_policy.get(
                "agency_employment_types", ()
            )
        ),
        period_ratio_cap_scaled=round(
            float(agency_policy.get("period_ratio_cap") or 0) * 1000
        ),
        daily_rank_caps=tuple(sorted(
            (str(expression), int(cap))
            for expression, cap in (
                agency_policy.get("daily_rank_caps") or {}
            ).items()
        )),
        monthly_shift_caps=tuple(sorted(
            (str(shift_type).upper(), int(cap))
            for shift_type, cap in (
                agency_policy.get("monthly_shift_caps") or {}
            ).items()
        )),
        vacancy_period_cap=vacancy_period_cap,
    )
    night_types = {
        str(value).upper() for value in night_policy.get("night_shift_types", ())
    }
    cooldown_ranks = {
        str(value).upper() for value in night_policy.get("cooldown_ranks", ())
    }
    prior_an, prior_nights, prior_night_staff = _prior_night_history(
        client, facility_id, period_start, night_types
    )
    debt_cooldown_staff = {
        row["staff_id"] for row in future_debts
        if row.get("staff_id")
        and row.get("debt_type") == "NIGHT_COOLDOWN"
        and (
            not row.get("due_period_id")
            or row.get("due_period_id") == period_id
        )
    }

    period_days = (period_end - period_start).days + 1
    weeks = period_days / 7
    max_work_days = max(1, period_days - period_days // 7)   # ~1 rest day / week

    # ── staff (with Home-B defaults where no contract row exists) ──
    staff: list[StaffInput] = []
    for st in staff_rows:
        c = contract_by_staff.get(st["id"]) or {}
        weekly = c.get("weekly_hours") or st.get("contracted_hours") or 0
        max_weekly = c.get("max_weekly_hours")
        employment_type = str(st["employment_type"])
        default_rest = 720 if employment_type == "imported_labor" else 660
        minimum_rest = int(c.get("min_rest_minutes") or default_rest)
        if employment_type == "imported_labor":
            minimum_rest = max(720, minimum_rest)
        staff.append(StaffInput(
            id=st["id"], rank=st["rank"], employment_type=employment_type,
            primary_unit_id=st.get("primary_unit_id"),
            is_audited_for_medication=bool(st.get("is_audited_for_medication")),
            min_rest_minutes=minimum_rest,
            allowed_shift_types=frozenset(c.get("allowed_shift_types") or []),
            contracted_period_minutes=round(float(weekly) * weeks * 60),
            max_period_minutes=round(float(max_weekly) * weeks * 60) if max_weekly else 0,
            max_work_days=max_work_days,
            night_cooldown=(
                str(st["rank"]).upper() in cooldown_ranks
                and st["id"] in (prior_night_staff | debt_cooldown_staff)
            ),
            an_monthly_limit=int(night_policy.get("an_monthly_limit") or 0),
            nurse_night_monthly_limit=int(
                night_policy.get("nurse_night_monthly_limit") or 0
            ),
            prior_an_counts=tuple(sorted(
                (year, month, count)
                for (staff_id, year, month), count in prior_an.items()
                if staff_id == st["id"]
            )),
            prior_night_counts=tuple(sorted(
                (year, month, count)
                for (staff_id, year, month), count in prior_nights.items()
                if staff_id == st["id"]
            )),
            long_shift_cost_scaled=(
                130 if facility_code.upper() == "B"
                and employment_type == "imported_labor" else 100
            ),
            work_pattern=_work_pattern(part_time_policy, employment_type),
        ))

    # ── demand + baseline + leave (all from the source version) ──
    assign_by_shift: dict[str, list] = {}
    for a in assigns:
        assign_by_shift.setdefault(a["shift_id"], []).append(a)

    demand: list[DemandSlot] = []
    baseline: list[BaselineCell] = []
    leave: set[tuple[str, Date]] = set()
    preferences: list[PreferenceInput] = []
    for request in leave_requests:
        start = max(period_start, _as_date(request["date_start"]))
        end = min(period_end, _as_date(request["date_end"]))
        if end < start:
            continue
        requested_shift = request.get("requested_shift_type")
        leave_type = str(request.get("leave_type") or "").lower()
        status = str(request.get("status") or "").lower()
        is_duty_preference = leave_type in {"duty_request", "shift_swap"}
        weight = _preference_weight(request)
        # Approved actual leave is authoritative hard unavailability even when
        # legacy data accidentally carries a requested_shift_type. Only the two
        # explicit duty-preference types can request a positive shift.
        if status == "approved" and not is_duty_preference:
            leave.update(
                (request["staff_id"], day) for day in _days(start, end)
            )
        elif status in {"approved", "pending", "reviewed"}:
            preferences.extend(
                PreferenceInput(
                    staff_id=request["staff_id"],
                    date=day,
                    prefer_working=bool(
                        is_duty_preference and requested_shift
                    ),
                    shift_type=(
                        requested_shift
                        if is_duty_preference and requested_shift
                        else None
                    ),
                    weight=weight,
                )
                for day in _days(start, end)
            )
    for s in shifts:
        d = _as_date(s["date"])
        working = bool(s.get("is_working"))
        for a in assign_by_shift.get(s["id"], []):
            if a.get("staff_id"):
                baseline.append(BaselineCell(staff_id=a["staff_id"], date=d,
                                             shift_type=s["shift_type"], is_working=working))
                if s["shift_type"] in _LEAVE_TYPES:
                    leave.add((a["staff_id"], d))
        if not working:
            continue
        segments = duty_segments(s)
        span = envelope(s)
        if not span:
            continue
        start, end, cross = span
        rank = s.get("required_rank")
        cal = cal_by_date.get(d)
        demand.append(DemandSlot(
            id=s["id"], date=d, day_index=(d - period_start).days, shift_type=s["shift_type"],
            start_min=start, end_min=end, cross_midnight=cross,
            duration_min=paid_minutes(s), segments=segments,
            unit_id=s.get("unit_id"), required_rank=rank,
            required_count=int(s.get("required_count") or 1),
            requires_medication=rank in _AUDIT_RANKS,
            agency_allowed=_agency_allowed(cal, s["shift_type"], agency_policy),
            agency_cost_scaled=round(float(cal["agency_cost_multiplier"]) * 10) if cal else 10,
        ))

    event_by_id = {event["id"]: event for event in events}
    for requirement in event_requirements:
        if not requirement.get("is_additive", True):
            continue
        event = event_by_id.get(requirement.get("event_id"))
        if not event:
            continue
        d = _as_date(event["date"])
        start = _clock_minutes(event.get("start_at"), "00:00")
        end = _clock_minutes(event.get("end_at"), "24:00")
        cross = end <= start
        duration = ((1440 - start) + end) if cross else end - start
        cal = cal_by_date.get(d)
        event_type = str(event.get("event_type") or "event")
        demand.append(DemandSlot(
            id=f"event:{event['id']}:{requirement['id']}",
            date=d,
            day_index=(d - period_start).days,
            shift_type=f"EVENT:{event_type}",
            start_min=start,
            end_min=end,
            cross_midnight=cross,
            duration_min=duration,
            segments=((start, end, cross),),
            unit_id=event.get("unit_id"),
            required_rank=requirement.get("rank"),
            required_count=int(requirement.get("count") or 1),
            requires_medication=event_type.lower().startswith("medication"),
            agency_allowed=_agency_allowed(
                cal, f"EVENT:{event_type}", agency_policy
            ),
            agency_cost_scaled=(
                round(float(cal["agency_cost_multiplier"]) * 10) if cal else 10
            ),
            is_event_overlay=True,
        ))

    ratio_rules = _ratio_rule_inputs(
        rules, facility_id, period_start, period_end
    )

    resident_counts = [ResidentCountInput(
        date=_as_date(rc["date"]), resident_count=int(rc["resident_count"]),
        unit_id=rc.get("unit_id"),
        care_level=rc.get("care_level"),
    ) for rc in counts]

    locks = tuple(LockedAssignment(staff_id=lk["staff_id"], slot_id=lk["slot_id"],
                                   pin=bool(lk.get("pin", True)))
                  for lk in (locked_assignments or []))

    return SolverInputs(
        facility_id=facility_id, period_id=period_id,
        period_start=period_start, period_end=period_end,
        staff=tuple(staff), demand=tuple(demand), ratio_rules=tuple(ratio_rules),
        resident_counts=tuple(resident_counts), baseline=tuple(baseline),
        preferences=tuple(preferences),
        leave_unavailable=frozenset(leave), locks=locks,
        include_staff_ids=frozenset(include_staff_ids or []),
        exclude_staff_ids=frozenset(exclude_staff_ids or []),
        night_shift_types=frozenset(night_types),
        agency_limits=agency_limits,
    )


# ── run + writeback ──────────────────────────────────────────────────────────
def run_optimization(client, request: OptimizeRequest, *, persist: bool = True,
                     job_id: str | None = None, pareto: bool = False) -> OptimizeResponse:
    """Run the solver for the requested plan mode(s), optionally persisting each option
    as a roster version. Pass ``job_id`` for an already-enqueued PENDING job (async
    path); otherwise a RUNNING job is created inline. With ``pareto`` the three
    options come off a non-dominated frontier instead of the fixed A/B/C presets."""
    persist = persist and request.writeback.persist
    created_here = job_id is None
    if created_here:
        job_id = _create_job(client, request)
    try:
        if not created_here:
            # inside the try so a failure here is captured by _fail_job, not orphaned.
            _start_job(client, job_id)
        inputs = load_inputs(
            client, request.facility_id, request.period_id,
            source_version_id=request.source_version_id,
            include_staff_ids=request.include_staff_ids,
            exclude_staff_ids=request.exclude_staff_ids,
            locked_assignments=request.locked_assignments,
        )
        limits = SolverLimits(max_seconds=request.solver_limits.max_seconds,
                              workers=request.solver_limits.workers,
                              seed=request.solver_limits.seed)
        if persist and request.writeback.archive_previous_auto:
            _archive_previous(client, request.facility_id, request.period_id)

        meta: dict | None = None
        if pareto:
            solved, meta = solve_pareto(inputs, limits)
        else:
            modes = ([request.plan_mode] if request.plan_mode
                     else [PlanMode.A, PlanMode.B, PlanMode.C])
            solved = build_and_solve(inputs, modes, limits)

        options: list[RosterOption] = []
        for res in solved:
            version_id = None
            if persist and res.status != SolveStatus.INFEASIBLE:
                version_id = _writeback_version(client, request, inputs, res)
            options.append(_to_option(res, version_id))

        _complete_job(client, job_id, options, meta=meta)
        return OptimizeResponse(job_id=job_id, status=JobStatus.COMPLETED,
                                roster_options=options)
    except Exception as exc:  # noqa: BLE001
        _fail_job(client, job_id, exc)
        raise


def _to_option(res, version_id) -> RosterOption:
    return RosterOption(
        plan_mode=res.plan_mode, version_label=res.label, status=res.status,
        roster_version_id=version_id,
        constraint_score=res.constraint_score,
        hard_violation_count=res.hard_violation_count,
        soft_penalty_total=res.soft_penalty_total,
        kpi=KpiSummary(
            headcount_assigned=res.kpi.headcount_assigned,
            agency_count=res.kpi.agency_count,
            ot_hours=round(res.kpi.ot_minutes / 60, 1),
            coverage_gap=res.kpi.coverage_gap,
            ratio_breaches=res.kpi.ratio_breaches,
            deviation_from_baseline=res.kpi.deviation_from_baseline,
            fairness_spread_minutes=res.kpi.fairness_spread_minutes,
        ),
        infeasible_reasons=list(res.infeasible_reasons),
    )


def _archive_previous(client, facility_id, period_id) -> None:
    # SQL: update roster_versions set status = 'archived'
    #      where facility_id = :facility_id and period_id = :period_id
    #        and version_type = any('{A,B,C}')
    #        and status = 'draft'
    #      returning *
    (client.table("roster_versions").update({"status": RosterStatus.ARCHIVED})
     .eq("facility_id", facility_id).eq("period_id", period_id)
     .in_("version_type", [PlanMode.A, PlanMode.B, PlanMode.C])
     .eq("status", RosterStatus.DRAFT).execute())


def _insert_nonworking_cell(client, *, facility_id: str, version_id: str,
                            day: Date, code: str, definition: dict,
                            unit_id: str | None, staff: StaffInput) -> None:
    shift = (
        client.table("shifts").insert({
            "facility_id": facility_id,
            "roster_version_id": version_id,
            "date": str(day),
            "shift_type": code,
            "start_time": definition.get("start_time"),
            "end_time": definition.get("end_time"),
            "cross_midnight": bool(definition.get("cross_midnight")),
            "unit_id": unit_id,
            "required_rank": None,
            "required_count": 1,
            "is_working": False,
            "segments": None,
            "paid_minutes": int(definition.get("paid_minutes") or 0),
        }).execute().data[0]
    )
    client.table("shift_assignments").insert({
        "facility_id": facility_id,
        "shift_id": shift["id"],
        "staff_id": staff.id,
        "role": staff.rank,
        "status": "assigned",
        "is_agency": False,
    }).execute()


def _writeback_night_recovery(client, facility_id: str, version_id: str,
                              inputs: SolverInputs, assignments) -> None:
    definitions = (
        client.table("shift_definitions").select("*")
        .eq("facility_id", facility_id)
        .in_("shift_type", ["SLEEP", "DO"])
        .execute().data
    )
    definition_by_code = {row["shift_type"]: row for row in definitions}
    if "SLEEP" not in definition_by_code or "DO" not in definition_by_code:
        return

    staff_by_id = {staff.id: staff for staff in inputs.staff}
    slot_by_id = {slot.id: slot for slot in inputs.demand}
    occupied = {
        (assignment.staff_id, slot_by_id[assignment.slot_id].date)
        for assignment in assignments
        if assignment.staff_id and assignment.slot_id in slot_by_id
    }
    recovery: list[tuple[Date, str, object, StaffInput]] = []
    for assignment in assignments:
        if not assignment.staff_id:
            continue
        staff = staff_by_id.get(assignment.staff_id)
        slot = slot_by_id.get(assignment.slot_id)
        if (
            not staff or not slot or staff.employment_type != "local_ft"
            or slot.shift_type.upper() not in inputs.night_shift_types
        ):
            continue
        recovery.extend([
            (slot.date + timedelta(days=1), "SLEEP", slot, staff),
            (slot.date + timedelta(days=2), "DO", slot, staff),
        ])

    for day, code, source_slot, staff in sorted(
        recovery, key=lambda item: (item[0], item[3].id, item[1])
    ):
        key = (staff.id, day)
        if day < inputs.period_start or day > inputs.period_end or key in occupied:
            continue
        definition = definition_by_code[code]
        _insert_nonworking_cell(
            client,
            facility_id=facility_id,
            version_id=version_id,
            day=day,
            code=code,
            definition=definition,
            unit_id=source_slot.unit_id,
            staff=staff,
        )
        occupied.add(key)


def _writeback_part_time_cl(client, facility_id: str, version_id: str,
                            inputs: SolverInputs, assignments) -> None:
    """Materialise or defer the Home-A CL earned by Saturday PT duty."""
    staff_by_id = {staff.id: staff for staff in inputs.staff}
    slot_by_id = {slot.id: slot for slot in inputs.demand}
    occupied = {
        (assignment.staff_id, slot_by_id[assignment.slot_id].date)
        for assignment in assignments
        if assignment.staff_id and assignment.slot_id in slot_by_id
    }
    saturday_work: dict[tuple[Date, str], tuple[object, StaffInput]] = {}
    for assignment in assignments:
        staff = staff_by_id.get(assignment.staff_id)
        slot = slot_by_id.get(assignment.slot_id)
        if (
            staff
            and slot
            and slot.date.weekday() == 5
            and staff.work_pattern.saturday_requires_weekday_cl
        ):
            saturday_work.setdefault((slot.date, staff.id), (slot, staff))

    if not saturday_work:
        return

    definitions = (
        client.table("shift_definitions").select("*")
        .eq("facility_id", facility_id)
        .eq("shift_type", "CL")
        .limit(1)
        .execute().data
    )
    # A non-working CL cell has no time envelope, so it can be materialised
    # safely even when an older tenant has not seeded the display definition.
    definition = definitions[0] if definitions else {
        "start_time": None,
        "end_time": None,
        "cross_midnight": False,
        "paid_minutes": 0,
    }

    for (saturday, _staff_id), (source_slot, staff) in sorted(
        saturday_work.items()
    ):
        following_weekdays = [
            saturday + timedelta(days=offset)
            for offset in range(1, 7)
            if (
                saturday + timedelta(days=offset) <= inputs.period_end
                and (saturday + timedelta(days=offset)).weekday() < 5
            )
        ]
        recovery_day = next((
            day for day in following_weekdays
            if (staff.id, day) not in occupied
        ), None)
        if recovery_day is None:
            if following_weekdays:
                raise ValueError(
                    "Saturday PT duty has no non-working weekday available for CL"
                )
            client.table("future_debt_ledger").insert({
                "facility_id": facility_id,
                "staff_id": staff.id,
                "debt_type": "CL",
                "quantity": 1,
                "unit": "days",
                "due_period_id": None,
                "status": "open",
                "note": "Saturday PT compensatory leave due next roster period",
                "details_json": {
                    "source_roster_version_id": version_id,
                    "source_slot_id": source_slot.id,
                    "source_saturday": saturday.isoformat(),
                    "eligible_from": (
                        saturday + timedelta(days=2)
                    ).isoformat(),
                },
            }).execute()
            continue
        _insert_nonworking_cell(
            client,
            facility_id=facility_id,
            version_id=version_id,
            day=recovery_day,
            code="CL",
            definition=definition,
            unit_id=source_slot.unit_id,
            staff=staff,
        )
        client.table("future_debt_ledger").insert({
            "facility_id": facility_id,
            "staff_id": staff.id,
            "debt_type": "CL",
            "quantity": 1,
            "unit": "days",
            "due_period_id": inputs.period_id,
            "status": "settled",
            "note": "Saturday PT compensatory leave assigned",
            "settled_at": _now(),
            "details_json": {
                "source_roster_version_id": version_id,
                "source_slot_id": source_slot.id,
                "source_saturday": saturday.isoformat(),
                "recovery_date": recovery_day.isoformat(),
            },
        }).execute()
        occupied.add((staff.id, recovery_day))


def _writeback_version(client, request, inputs, res) -> str:
    # SQL: insert into roster_versions
    #        (facility_id, period_id, version_type, label, status, created_by)
    #      values (:facility_id, :period_id, :plan_mode, :label, 'draft', :created_by)
    #      returning id
    version_id = (client.table("roster_versions").insert({
        "facility_id": request.facility_id, "period_id": request.period_id,
        "version_type": str(res.plan_mode), "label": f"{res.label} · auto",
        "status": RosterStatus.DRAFT, "created_by": request.created_by,
    }).execute().data[0]["id"])

    # one fresh shift per demand slot; keep source-slot -> new-shift id map
    #
    # SQL (once per demand slot - an N-statement loop, not a single multi-row insert,
    #      because each returned shift id has to be mapped back to its solver slot):
    #      insert into shifts
    #        (facility_id, roster_version_id, date, shift_type, start_time, end_time,
    #         cross_midnight, unit_id, required_rank, required_count, is_working,
    #         segments, paid_minutes)
    #      values (:facility_id, :version_id, :date, :shift_type, :start_time,
    #              :end_time, :cross_midnight, :unit_id, :required_rank,
    #              :required_count, true, :segments::jsonb, :paid_minutes)
    #      returning id
    slot_to_shift: dict[str, str] = {}
    for sl in inputs.demand:
        new_id = (client.table("shifts").insert({
            "facility_id": request.facility_id, "roster_version_id": version_id,
            "date": str(sl.date), "shift_type": sl.shift_type,
            "start_time": _min_to_time(sl.start_min), "end_time": _min_to_time(sl.end_min),
            "cross_midnight": sl.cross_midnight, "unit_id": sl.unit_id,
            "required_rank": (
                sl.required_rank if "|" not in (sl.required_rank or "") else None
            ),
            "required_count": sl.required_count,
            "is_working": True,
            # carry the split-shift shape through, else a solver option would
            # silently re-inflate an A/N shift back to its elapsed span
            "segments": _segments_json(sl.segments), "paid_minutes": sl.duration_min,
        }).execute().data[0]["id"])
        slot_to_shift[sl.id] = new_id

    solved_assignments = [
        assignment for assignment in res.assignments
        if assignment.slot_id in slot_to_shift
    ]
    rows = [{
        "facility_id": request.facility_id,
        "shift_id": slot_to_shift[assignment.slot_id],
        "staff_id": assignment.staff_id,
        "role": assignment.role,
        "status": "assigned",
        "is_agency": assignment.is_agency,
    } for assignment in solved_assignments]
    inserted_assignments = []
    if rows:
        # SQL: insert into shift_assignments
        #        (facility_id, shift_id, staff_id, role, status, is_agency)
        #      values (...), (...), ...      -- one tuple per solver assignment
        #      returning *
        inserted_assignments = (
            client.table("shift_assignments").insert(rows).execute().data
        )

    # Synthetic solver fills have both a roster cell and a linked purchase/cost
    # record. Downstream KPI code can deduplicate the two using the foreign keys.
    agency_rows = []
    slot_by_id = {slot.id: slot for slot in inputs.demand}
    for solved, inserted in zip(solved_assignments, inserted_assignments):
        if not solved.is_agency:
            continue
        slot = slot_by_id[solved.slot_id]
        hours = slot.duration_min / 60
        base_cost = _AGENCY_SHIFT_COST.get(solved.role, 957.0)
        cost = round(
            base_cost * slot.duration_min / 480 * slot.agency_cost_scaled / 10,
            2,
        )
        agency_rows.append({
            "facility_id": request.facility_id,
            "shift_id": inserted["shift_id"],
            "shift_assignment_id": inserted["id"],
            "date": str(slot.date),
            "role": solved.role,
            "vendor": "Emma auto-fill",
            "hours": hours,
            "cost": cost,
            "reason": "Solver coverage fill",
        })
    if agency_rows:
        client.table("agency_assignments").insert(agency_rows).execute()

    _writeback_night_recovery(
        client, request.facility_id, version_id, inputs, solved_assignments
    )
    _writeback_part_time_cl(
        client, request.facility_id, version_id, inputs, solved_assignments
    )

    # SQL: insert into roster_option_scores
    #        (facility_id, roster_version_id, plan_mode, constraint_score,
    #         hard_violation_count, soft_penalty_total, objective_weights_json,
    #         infeasible_reasons_json)
    #      values (:facility_id, :version_id, :plan_mode, :constraint_score,
    #              :hard_violation_count, :soft_penalty_total,
    #              :weights::jsonb, :infeasible_reasons::jsonb)
    #      returning *
    client.table("roster_option_scores").insert({
        "facility_id": request.facility_id, "roster_version_id": version_id,
        "plan_mode": str(res.plan_mode), "constraint_score": res.constraint_score,
        "hard_violation_count": res.hard_violation_count,
        "soft_penalty_total": res.soft_penalty_total,
        "objective_weights_json": res.weights,
        "infeasible_reasons_json": list(res.infeasible_reasons),
    }).execute()

    vrows = [{
        "facility_id": request.facility_id, "roster_version_id": version_id,
        "rule_code": str(v.rule_code),
        "shift_id": slot_to_shift.get(v.slot_id) if v.slot_id else None,
        "severity": v.severity, "message": v.message, "resolved": False,
    } for v in res.violations]
    if vrows:
        # SQL: insert into violation_log
        #        (facility_id, roster_version_id, rule_code, shift_id, severity,
        #         message, resolved)
        #      values (...), (...), ...      -- one tuple per solver violation
        #      returning *
        client.table("violation_log").insert(vrows).execute()

    return version_id


# ── optimization_jobs lifecycle ──────────────────────────────────────────────
def enqueue_optimization(client, request: OptimizeRequest) -> str:
    """Insert a PENDING job and return its id immediately; the HTTP layer runs
    ``run_optimization(..., job_id=job_id)`` in the background so the request doesn't
    block on the CP-SAT solves."""
    # SQL: insert into optimization_jobs
    #        (facility_id, period_id, rule_profile_id, status, plan_mode,
    #         solver_limits_json, input_payload_json)
    #      values (:facility_id, :period_id, :rule_profile_id, 'pending', :plan_mode,
    #              :solver_limits::jsonb, :input_payload::jsonb)
    #      returning id
    return (client.table("optimization_jobs").insert({
        "facility_id": request.facility_id, "period_id": request.period_id,
        "rule_profile_id": request.rule_profile_id, "status": JobStatus.PENDING,
        "plan_mode": str(request.plan_mode) if request.plan_mode else None,
        "solver_limits_json": request.solver_limits.model_dump(),
        "input_payload_json": request.model_dump(mode="json"),
    }).execute().data[0]["id"])


def _create_job(client, request: OptimizeRequest) -> str:
    # SQL: insert into optimization_jobs
    #        (facility_id, period_id, rule_profile_id, status, plan_mode,
    #         solver_limits_json, input_payload_json, started_at)
    #      values (:facility_id, :period_id, :rule_profile_id, 'running', :plan_mode,
    #              :solver_limits::jsonb, :input_payload::jsonb, now())
    #      returning id
    return (client.table("optimization_jobs").insert({
        "facility_id": request.facility_id, "period_id": request.period_id,
        "rule_profile_id": request.rule_profile_id, "status": JobStatus.RUNNING,
        "plan_mode": str(request.plan_mode) if request.plan_mode else None,
        "solver_limits_json": request.solver_limits.model_dump(),
        "input_payload_json": request.model_dump(mode="json"),
        "started_at": _now(),
    }).execute().data[0]["id"])


def _start_job(client, job_id: str) -> None:
    # SQL: update optimization_jobs set status = 'running', started_at = now()
    #      where id = :job_id
    #      returning *
    (client.table("optimization_jobs").update({
        "status": JobStatus.RUNNING, "started_at": _now(),
    }).eq("id", job_id).execute())


def _complete_job(client, job_id: str, options, *, meta: dict | None = None) -> None:
    result = {"roster_options": [o.model_dump(mode="json") for o in options]}
    if meta:
        result["pareto"] = meta
    # SQL: update optimization_jobs
    #      set status = 'completed', result_json = :result::jsonb, completed_at = now()
    #      where id = :job_id
    #      returning *
    (client.table("optimization_jobs").update({
        "status": JobStatus.COMPLETED, "result_json": result, "completed_at": _now(),
    }).eq("id", job_id).execute())


def _fail_job(client, job_id: str, exc: Exception) -> None:
    try:
        # SQL: update optimization_jobs
        #      set status = 'failed', error_json = :error::jsonb, completed_at = now()
        #      where id = :job_id
        #      returning *
        (client.table("optimization_jobs").update({
            "status": JobStatus.FAILED,
            "error_json": {"type": type(exc).__name__, "message": str(exc)},
            "completed_at": _now(),
        }).eq("id", job_id).execute())
    except Exception:  # noqa: BLE001 - never mask the original error
        pass


def get_job(client, job_id: str) -> dict | None:
    # SQL: select * from optimization_jobs where id = :job_id
    rows = client.table("optimization_jobs").select("*").eq("id", job_id).execute().data
    return rows[0] if rows else None


# ── option-score reads (compare / publish-guard UI) ──────────────────────────
def get_option_scores(client, roster_version_id: str) -> dict | None:
    """Score row + hard-violation detail for one roster version."""
    # SQL: select * from roster_option_scores
    #      where roster_version_id = :roster_version_id
    #      limit 1
    rows = (client.table("roster_option_scores").select("*")
            .eq("roster_version_id", roster_version_id).limit(1).execute().data)
    if not rows:
        return None
    score = rows[0]
    # SQL: select * from violation_log
    #      where roster_version_id = :roster_version_id
    #      order by created_at
    score["violations"] = (client.table("violation_log").select("*")
                           .eq("roster_version_id", roster_version_id)
                           .order("created_at").execute().data)
    return score


def list_period_option_scores(client, period_id: str) -> list[dict]:
    """All A/B/C option scores for a period, for the side-by-side compare table."""
    # SQL: select id, version_type, label, status from roster_versions
    #      where period_id = :period_id
    #        and version_type = any('{A,B,C}')
    versions = (client.table("roster_versions").select("id,version_type,label,status")
                .eq("period_id", period_id)
                .in_("version_type", [PlanMode.A, PlanMode.B, PlanMode.C])
                .execute().data)
    by_version = {v["id"]: v for v in versions}
    if not by_version:
        return []
    # SQL: select * from roster_option_scores
    #      where roster_version_id = any(:version_ids)
    # (the label/status columns are grafted on in Python rather than joined)
    scores = (client.table("roster_option_scores").select("*")
              .in_("roster_version_id", list(by_version)).execute().data)
    for s in scores:
        v = by_version.get(s["roster_version_id"], {})
        s["version_label"] = v.get("label")
        s["version_status"] = v.get("status")
    return scores
