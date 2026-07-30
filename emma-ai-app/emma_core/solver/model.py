"""CP-SAT model construction: decision variables, seven hard constraints, five
soft-penalty expressions.

Consumes :class:`SolverInputs`; ortools is imported lazily so importing this
package doesn't require the wheel. Hard #2 (leave) and #7 (eligibility) are
enforced by omitting variables for impossible pairs; #3 (coverage) and #4
(ratio) use bounded, heavily-penalized slack (gap / ratio_short) so the engine
returns an explainable roster instead of a bare INFEASIBLE.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import timedelta

from ..constants import can_cover_rank
from .inputs import DemandSlot, SolverInputs, StaffInput
from .objective import BIG_M
from .timeutils import absolute_interval, intervals_conflict

NOMINAL_SHIFT_MIN = 480   # one 8h shift; the common scale for day-based penalties


def eligible(staff: StaffInput, slot: DemandSlot, inputs: SolverInputs) -> bool:
    """Hard #2 (leave) + #7 (rank/skill/audit): False for pairs that must never
    be assigned, so no variable is created for them."""
    if inputs.include_staff_ids and staff.id not in inputs.include_staff_ids:
        return False
    if staff.id in inputs.exclude_staff_ids:
        return False
    required_ranks = {
        value.strip() for value in (slot.required_rank or "").split("|") if value.strip()
    }
    if required_ranks:
        # A pipe expression is an explicit allow-list (for example an event
        # asking for CW|HCA). Single-rank slots use the seniority substitution
        # ladder through can_cover_rank.
        if len(required_ranks) > 1 and staff.rank not in required_ranks:
            return False
        if len(required_ranks) == 1 and not can_cover_rank(
            staff.rank, next(iter(required_ranks))
        ):
            return False
    if (
        staff.employment_type in inputs.agency_limits.external_employment_types
        and not slot.agency_allowed
    ):
        return False
    if (
        staff.night_cooldown
        and slot.shift_type.upper() in inputs.night_shift_types
    ):
        return False
    pattern = staff.work_pattern
    if pattern.allowed_weekdays and slot.date.weekday() not in pattern.allowed_weekdays:
        return False
    if pattern.required_shift_window:
        required_start, required_end = pattern.required_shift_window
        if (
            slot.cross_midnight
            or slot.start_min != required_start
            or slot.end_min != required_end
        ):
            return False
    if (not slot.is_event_overlay and staff.allowed_shift_types
            and slot.shift_type not in staff.allowed_shift_types):
        return False
    if slot.requires_medication and not staff.is_audited_for_medication:
        return False
    unavailable_dates = {slot.date}
    segments = slot.segments or ((slot.start_min, slot.end_min, slot.cross_midnight),)
    if any(cross or end <= start for start, end, cross in segments):
        unavailable_dates.add(slot.date + timedelta(days=1))
    if any((staff.id, day) in inputs.leave_unavailable for day in unavailable_dates):
        return False
    return True


def _day_spans(start: int, end: int, cross: bool) -> tuple[tuple[int, int], ...]:
    if cross or end <= start:
        spans = [(start, 1440)]
        if end > 0:
            spans.append((0, end))
        return tuple(spans)
    return ((start, end),)


def _slot_spans(slot: DemandSlot) -> tuple[tuple[int, int], ...]:
    segments = slot.segments or ((slot.start_min, slot.end_min, slot.cross_midnight),)
    return tuple(
        span
        for start, end, cross in segments
        for span in _day_spans(start, end, cross)
    )


def _ratio_segments(slots, rule):
    """Yield constant-coverage slices for every minute of a ratio window."""
    windows = _day_spans(
        rule.window_start_min,
        rule.window_end_min,
        rule.window_end_min <= rule.window_start_min,
    )
    spans_by_slot = {slot.id: _slot_spans(slot) for slot in slots}
    for win_start, win_end in windows:
        clipped: dict[str, list[tuple[int, int]]] = {}
        points = {win_start, win_end}
        for slot in slots:
            for start, end in spans_by_slot[slot.id]:
                lo, hi = max(start, win_start), min(end, win_end)
                if lo >= hi:
                    continue
                clipped.setdefault(slot.id, []).append((lo, hi))
                points.update((lo, hi))
        ordered = sorted(points)
        for lo, hi in zip(ordered, ordered[1:]):
            covering = [
                slot for slot in slots
                if any(start <= lo and end >= hi for start, end in clipped.get(slot.id, ()))
            ]
            yield lo, hi, covering


def _rank_weight(rule, rank: str | None) -> int | None:
    counted = rule.counted_ranks or (
        frozenset({rule.staff_rank}) if rule.staff_rank else frozenset()
    )
    if counted and rank not in counted:
        return None
    weights = dict(rule.rank_weights)
    weight = weights.get(rank, rule.weight_scale)
    return weight if weight > 0 else None


def _agency_rank_weight(rule, slot: DemandSlot) -> int | None:
    ranks = [
        value.strip()
        for value in (slot.required_rank or "").split("|")
        if value.strip()
    ]
    if not ranks:
        return _rank_weight(rule, None)
    weights = [
        weight for rank in ranks
        if (weight := _rank_weight(rule, rank)) is not None
    ]
    return max(weights) if weights else None


def _rank_group_matches(rank: str | None, expression: str) -> bool:
    """Agency cap buckets are exact rank groups, not substitution ladders."""
    return bool(rank) and rank.upper() in {
        required.strip()
        for required in expression.upper().split("|")
        if required.strip()
    }


def _synthetic_agency_rank(slot: DemandSlot) -> str | None:
    return next((
        value.strip() for value in (slot.required_rank or "").split("|")
        if value.strip()
    ), None)


def _add_agency_limit_constraints(model, inputs, x, agency) -> None:
    """Mirror central-validator agency_cap rules before a roster is emitted."""
    policy = inputs.agency_limits
    external: list[tuple[object, str, str | None, object]] = []
    internal = []

    for slot in inputs.demand:
        external.append((
            slot.date,
            slot.shift_type.upper(),
            _synthetic_agency_rank(slot),
            agency[slot.id],
        ))
        for staff in inputs.staff:
            var = x.get((staff.id, slot.id))
            if var is None:
                continue
            if staff.employment_type in policy.external_employment_types:
                external.append((slot.date, slot.shift_type.upper(), staff.rank, var))
            elif staff.employment_type in policy.internal_full_time_types:
                internal.append(var)

    external_total = sum(record[3] for record in external)
    if policy.period_ratio_cap_scaled > 0:
        model.Add(
            policy.ratio_scale * external_total
            <= policy.period_ratio_cap_scaled * sum(internal)
        )
    if policy.vacancy_period_cap is not None:
        model.Add(external_total <= max(0, policy.vacancy_period_cap))

    for day in {
        slot.date for slot in inputs.demand
    }:
        rows = [record for record in external if record[0] == day]
        for expression, cap in policy.daily_rank_caps:
            model.Add(sum(
                var for _day, _shift_type, rank, var in rows
                if _rank_group_matches(rank, expression)
            ) <= max(0, cap))

    for shift_type, cap in policy.monthly_shift_caps:
        normalized = shift_type.upper()
        for year, month in {
            (day.year, day.month) for day, _code, _rank, _var in external
        }:
            model.Add(sum(
                var for day, code, _rank, var in external
                if code == normalized and (day.year, day.month) == (year, month)
            ) <= max(0, cap))


@dataclass
class SolverModel:
    """CpModel plus its variables, so objective/scoring read them without
    re-deriving. Holds ortools objects - not frozen."""
    model: object                       # cp_model.CpModel
    inputs: SolverInputs
    x: dict                             # (staff_id, slot_id) -> BoolVar
    agency: dict                        # slot_id -> IntVar
    gap: dict                           # slot_id -> IntVar (coverage slack)
    ratio_short: dict                   # (date, rule_idx) -> IntVar (ratio slack)
    ot: dict                            # staff_id -> IntVar (overtime minutes)
    works: dict                         # (staff_id, date) -> BoolVar
    penalties: dict                     # name -> LinearExpr | int
    soft_ub: dict                       # name -> int (upper bound for normalization)
    raw_unmet: object                   # unscaled baseline-deviation count (KPI)
    eligible_by_slot: dict              # slot_id -> list[StaffInput]
    slot_by_id: dict                    # slot_id -> DemandSlot
    lock_errors: list = field(default_factory=list)


def build_model(inputs: SolverInputs) -> SolverModel:
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    slot_by_id = {sl.id: sl for sl in inputs.demand}
    dates = [
        inputs.period_start + timedelta(days=offset)
        for offset in range(inputs.period_days)
    ]
    total_demand_minutes = sum(sl.duration_min for sl in inputs.demand) or 1

    eligible_by_slot: dict[str, list[StaffInput]] = {
        sl.id: [s for s in inputs.staff if eligible(s, sl, inputs)] for sl in inputs.demand
    }

    # ── decision variables (eligible pairs only) ────────────────────────────
    x: dict[tuple[str, str], object] = {}
    for sl in inputs.demand:
        for s in eligible_by_slot[sl.id]:
            x[(s.id, sl.id)] = model.NewBoolVar(f"x_{s.id}_{sl.id}")

    # locks: a pin can force an otherwise-ineligible pair; also detect contradictions
    lock_errors: list[str] = []
    seen_pins: dict[str, str] = {}      # slot_id -> pinned staff
    for lock in inputs.locks:
        sl = slot_by_id.get(lock.slot_id)
        if sl is None:
            lock_errors.append(f"Locked slot {lock.slot_id} is not in this period's demand.")
            continue
        key = (lock.staff_id, lock.slot_id)
        if lock.pin and key not in x:
            lock_errors.append(
                f"Locked assignment is ineligible: staff {lock.staff_id}, slot {lock.slot_id}."
            )
            continue
        if key in x:
            model.Add(x[key] == (1 if lock.pin else 0))
    _detect_lock_conflicts(inputs, slot_by_id, lock_errors)

    # ── #3 required coverage (elastic: staff + agency + gap slack) ───────────
    agency: dict[str, object] = {}
    gap: dict[str, object] = {}
    for sl in inputs.demand:
        agency[sl.id] = model.NewIntVar(0, sl.required_count if sl.agency_allowed else 0,
                                        f"agency_{sl.id}")
        gap[sl.id] = model.NewIntVar(0, sl.required_count, f"gap_{sl.id}")
        covered = [x[(s.id, sl.id)] for s in eligible_by_slot[sl.id]]
        model.Add(sum(covered) + agency[sl.id] + gap[sl.id] == sl.required_count)
    _add_agency_limit_constraints(model, inputs, x, agency)

    # ── #1 overlap + #5 min rest (combined pairwise, per staff) ──────────────
    for s in inputs.staff:
        s_slots = [sl for sl in inputs.demand if (s.id, sl.id) in x]
        interval = {
            sl.id: absolute_interval(sl.day_index, sl.start_min, sl.end_min, sl.cross_midnight)
            for sl in s_slots
        }
        for a, b in itertools.combinations(s_slots, 2):
            if intervals_conflict(interval[a.id], interval[b.id], s.min_rest_minutes):
                model.Add(x[(s.id, a.id)] + x[(s.id, b.id)] <= 1)

    # ── #4 SWD ratio (elastic; window-overlap membership) ────────────────────
    ratio_short: dict[tuple, object] = {}
    for d in dates:
        for k, rule in enumerate(inputs.ratio_rules):
            if rule.effective_dates and d not in rule.effective_dates:
                continue
            residents = sum(rc.resident_count for rc in inputs.resident_counts
                            if rc.date == d
                            and (rule.unit_id is None or rc.unit_id == rule.unit_id)
                            and (not rule.care_level or rc.care_level == rule.care_level))
            if rule.ratio_residents_per_staff:
                required_scaled = (
                    math.ceil(
                        residents * rule.weight_scale
                        / rule.ratio_residents_per_staff
                    )
                    if residents else 0
                )
            else:
                required_scaled = (rule.min_staff_any_rank or 0) * rule.weight_scale
            if required_scaled <= 0:
                continue
            day_slots = [
                sl for sl in inputs.demand
                if sl.date == d and (rule.unit_id is None or sl.unit_id == rule.unit_id)
            ]
            for lo, hi, covering_slots in _ratio_segments(day_slots, rule):
                members: list = []
                for staff in inputs.staff:
                    weight = _rank_weight(rule, staff.rank)
                    if weight is None:
                        continue
                    staff_vars = [
                        x[(staff.id, sl.id)]
                        for sl in covering_slots
                        if (staff.id, sl.id) in x
                    ]
                    if not staff_vars:
                        continue
                    present = model.NewBoolVar(
                        f"ratio_present_{staff.id}_{d}_{k}_{lo}_{hi}"
                    )
                    model.AddMaxEquality(present, staff_vars)
                    members.append(weight * present)

                for sl in covering_slots:
                    weight = _agency_rank_weight(rule, sl)
                    if weight is not None:
                        members.append(weight * agency[sl.id])

                short = model.NewIntVar(
                    0, required_scaled, f"ratio_short_{d}_{k}_{lo}_{hi}"
                )
                ratio_short[(d, k, lo, hi)] = short
                model.Add(sum(members) + short >= required_scaled)

    # ── #6 max hours (hard) + OT accumulation (soft source) ──────────────────
    ot: dict[str, object] = {}
    for s in inputs.staff:
        worked = [sl.duration_min * x[(s.id, sl.id)] for sl in inputs.demand if (s.id, sl.id) in x]
        total = sum(worked)
        if s.max_period_minutes and s.max_period_minutes > 0:
            model.Add(total <= s.max_period_minutes)
        ot[s.id] = model.NewIntVar(0, total_demand_minutes, f"ot_{s.id}")
        model.Add(ot[s.id] >= total - s.contracted_period_minutes)

    # ── day-worked indicator (future-debt + unmet-request) ───────────────────
    works: dict[tuple, object] = {}
    for s in inputs.staff:
        for d in dates:
            day_x = [x[(s.id, sl.id)] for sl in inputs.demand if sl.date == d and (s.id, sl.id) in x]
            w = model.NewBoolVar(f"works_{s.id}_{d}")
            if day_x:
                model.AddMaxEquality(w, day_x)
            else:
                model.Add(w == 0)
            works[(s.id, d)] = w

    # Facility-specific PT patterns are hard constraints. Weekly windows are
    # calendar-aligned; fortnight windows follow the roster-cycle boundary.
    for s in inputs.staff:
        if (
            (inputs.include_staff_ids and s.id not in inputs.include_staff_ids)
            or s.id in inputs.exclude_staff_ids
        ):
            continue
        pattern = s.work_pattern
        if pattern.weekly_work_days:
            minimum, maximum = pattern.weekly_work_days
            week_start = inputs.period_start - timedelta(
                days=inputs.period_start.weekday()
            )
            while week_start <= inputs.period_end:
                week_days = [
                    week_start + timedelta(days=offset)
                    for offset in range(7)
                    if inputs.period_start
                    <= week_start + timedelta(days=offset)
                    <= inputs.period_end
                ]
                full_week = len(week_days) == 7
                window_minimum, window_maximum = minimum, maximum
                if not full_week:
                    if (
                        not pattern.allowed_weekdays
                        or minimum != maximum
                        or minimum != len(pattern.allowed_weekdays)
                    ):
                        week_start += timedelta(days=7)
                        continue
                    window_minimum = window_maximum = sum(
                        day.weekday() in pattern.allowed_weekdays
                        for day in week_days
                    )
                worked = sum(works[(s.id, day)] for day in week_days)
                leave_credit = sum(
                    (s.id, day) in inputs.leave_unavailable
                    for day in week_days
                    if (
                        not pattern.allowed_weekdays
                        or day.weekday() in pattern.allowed_weekdays
                    )
                )
                model.Add(worked + leave_credit >= max(0, window_minimum))
                model.Add(worked <= max(0, window_maximum))
                week_start += timedelta(days=7)

        if pattern.fortnightly_work_days:
            minimum, maximum = pattern.fortnightly_work_days
            block_start = inputs.period_start
            while block_start + timedelta(days=13) <= inputs.period_end:
                block_days = [
                    block_start + timedelta(days=offset) for offset in range(14)
                ]
                worked = sum(works[(s.id, day)] for day in block_days)
                leave_credit = sum(
                    (s.id, day) in inputs.leave_unavailable
                    for day in block_days
                    if (
                        not pattern.allowed_weekdays
                        or day.weekday() in pattern.allowed_weekdays
                    )
                )
                model.Add(worked + leave_credit >= max(0, minimum))
                model.Add(worked <= max(0, maximum))
                block_start += timedelta(days=14)

        if pattern.saturday_requires_weekday_cl:
            for saturday in (day for day in dates if day.weekday() == 5):
                following_weekdays = [
                    saturday + timedelta(days=offset)
                    for offset in range(1, 7)
                    if (
                        saturday + timedelta(days=offset) <= inputs.period_end
                        and (saturday + timedelta(days=offset)).weekday() < 5
                    )
                ]
                if not following_weekdays:
                    # Writeback records an open CL debt for the next roster
                    # period; do not make a boundary Saturday infeasible.
                    continue
                # The writeback layer materialises CL on one of these guaranteed
                # non-working weekdays.
                model.Add(
                    sum(works[(s.id, day)] for day in following_weekdays)
                    <= len(following_weekdays) - works[(s.id, saturday)]
                )

    # Local full-time N/AN recovery is a hard chain: the next two dates cannot
    # contain working assignments. Writeback materialises those dates as
    # SLEEP/DO cells when the facility has matching shift definitions.
    for s in inputs.staff:
        if s.employment_type != "local_ft":
            continue
        night_slots = [
            sl for sl in inputs.demand
            if sl.shift_type.upper() in inputs.night_shift_types
            and (s.id, sl.id) in x
        ]
        for sl in night_slots:
            night = x[(s.id, sl.id)]
            for offset in (1, 2):
                recovery = works.get((s.id, sl.date + timedelta(days=offset)))
                if recovery is not None:
                    model.Add(night + recovery <= 1)

    # Monthly limits include prior published assignments when a prior roster and
    # the optimization period share a calendar month.
    months = sorted({(d.year, d.month) for d in dates})
    for s in inputs.staff:
        prior_an = {(year, month): count for year, month, count in s.prior_an_counts}
        prior_nights = {
            (year, month): count for year, month, count in s.prior_night_counts
        }
        for year, month in months:
            month_slots = [
                sl for sl in inputs.demand
                if (sl.date.year, sl.date.month) == (year, month)
                and (s.id, sl.id) in x
            ]
            if s.an_monthly_limit:
                remaining = max(
                    0, s.an_monthly_limit - prior_an.get((year, month), 0)
                )
                model.Add(sum(
                    x[(s.id, sl.id)] for sl in month_slots
                    if sl.shift_type.upper() == "AN"
                ) <= remaining)
            if s.rank in {"RN", "EN"} and s.nurse_night_monthly_limit:
                remaining = max(
                    0,
                    s.nurse_night_monthly_limit
                    - prior_nights.get((year, month), 0),
                )
                model.Add(sum(
                    x[(s.id, sl.id)] for sl in month_slots
                    if sl.shift_type.upper() in inputs.night_shift_types
                ) <= remaining)

    penalties, soft_ub, raw_unmet = _build_penalties(model, inputs, dates, total_demand_minutes,
                                                     x, agency, ot, works)

    return SolverModel(
        model=model, inputs=inputs, x=x, agency=agency, gap=gap, ratio_short=ratio_short,
        ot=ot, works=works, penalties=penalties, soft_ub=soft_ub, raw_unmet=raw_unmet,
        eligible_by_slot=eligible_by_slot, slot_by_id=slot_by_id, lock_errors=lock_errors,
    )


def _build_penalties(model, inputs, dates, total_demand_minutes, x, agency, ot, works):
    """Five soft-penalty terms on a shared minute-equivalent scale, so A/B/C
    weights compare like-for-like (a day of debt/deviation ≈ one shift =
    NOMINAL_SHIFT_MIN). Returns (penalties, soft_ub, raw_unmet)."""
    # agency: fills × shift minutes × day cost multiplier (agency_cost_scaled/10)
    def agency_coeff(sl):
        return sl.duration_min * sl.agency_cost_scaled // 10
    p_agency = sum(agency[sl.id] * agency_coeff(sl) for sl in inputs.demand)
    ub_agency = sum(sl.required_count * agency_coeff(sl) for sl in inputs.demand)

    # OT / workload cost: Home B imported-labour 12h assignments carry a 1.3
    # workload multiplier. Hard hour caps and the KPI remain actual minutes.
    long_shift_surcharge = sum(
        sl.duration_min * max(0, s.long_shift_cost_scaled - 100) // 100
        * x[(s.id, sl.id)]
        for s in inputs.staff
        for sl in inputs.demand
        if sl.duration_min >= 720 and (s.id, sl.id) in x
    )
    p_ot = sum(ot.values()) + long_shift_surcharge
    ub_ot = total_demand_minutes + sum(
        sl.duration_min * max(0, s.long_shift_cost_scaled - 100) // 100
        for s in inputs.staff
        for sl in inputs.demand
        if sl.duration_min >= 720 and (s.id, sl.id) in x
    )

    # future debt: working days over each staff's fair maximum (× nominal shift)
    debts = []
    for s in inputs.staff:
        max_days = s.max_work_days or inputs.period_days
        worked_days = sum(works[(s.id, d)] for d in dates)
        debt = model.NewIntVar(0, len(dates), f"debt_{s.id}")
        model.Add(debt >= worked_days - max_days)
        debts.append(debt)
    p_future_debt = NOMINAL_SHIFT_MIN * sum(debts)
    ub_future_debt = NOMINAL_SHIFT_MIN * max(1, len(inputs.staff) * len(dates))

    # Unmet request: deviation from the human baseline plus pending staff
    # preferences. Priority weights affect the objective, while the KPI remains
    # an intuitive count of requests/deviations not honoured.
    staff_ids = {s.id for s in inputs.staff}
    unmet_terms = []
    weighted_unmet_terms = []
    for b in inputs.baseline:
        if b.staff_id not in staff_ids or (b.staff_id, b.date) not in works:
            continue
        w = works[(b.staff_id, b.date)]
        deviation = (1 - w) if b.is_working else w
        unmet_terms.append(deviation)
        weighted_unmet_terms.append(deviation)

    for index, pref in enumerate(inputs.preferences):
        if pref.staff_id not in staff_ids or (pref.staff_id, pref.date) not in works:
            continue
        if pref.prefer_working and pref.shift_type:
            matching = [
                x[(pref.staff_id, sl.id)]
                for sl in inputs.demand
                if sl.date == pref.date
                and sl.shift_type.upper() == pref.shift_type.upper()
                and (pref.staff_id, sl.id) in x
            ]
            if matching:
                honoured = model.NewBoolVar(f"preference_{index}_honoured")
                model.AddMaxEquality(honoured, matching)
                deviation = 1 - honoured
            else:
                deviation = 1
        else:
            working = works[(pref.staff_id, pref.date)]
            deviation = (1 - working) if pref.prefer_working else working
        unmet_terms.append(deviation)
        weighted_unmet_terms.append(max(1, pref.weight) * deviation)

    raw_unmet = sum(unmet_terms)
    p_unmet = NOMINAL_SHIFT_MIN * sum(weighted_unmet_terms)
    max_unmet_weight = len([
        b for b in inputs.baseline
        if b.staff_id in staff_ids and (b.staff_id, b.date) in works
    ]) + sum(
        max(1, pref.weight) for pref in inputs.preferences
        if pref.staff_id in staff_ids and (pref.staff_id, pref.date) in works
    )
    ub_unmet = NOMINAL_SHIFT_MIN * max(1, max_unmet_weight)

    # fairness: spread of worked minutes across staff (already minute-scaled)
    loads = []
    load_upper_bounds = []
    for s in inputs.staff:
        eligible_slots = [
            sl for sl in inputs.demand if (s.id, sl.id) in x
        ]
        coefficients = [
            (
                sl.duration_min
                * (s.long_shift_cost_scaled if sl.duration_min >= 720 else 100)
                // 100
            )
            for sl in eligible_slots
        ]
        load_ub = sum(coefficients)
        lv = model.NewIntVar(0, max(1, load_ub), f"load_{s.id}")
        terms = [
            coefficient * x[(s.id, sl.id)]
            for coefficient, sl in zip(coefficients, eligible_slots)
        ]
        model.Add(lv == sum(terms))
        loads.append(lv)
        load_upper_bounds.append(load_ub)
    if len(loads) >= 2:
        fairness_ub = max(1, max(load_upper_bounds, default=0))
        lmax = model.NewIntVar(0, fairness_ub, "load_max")
        lmin = model.NewIntVar(0, fairness_ub, "load_min")
        model.AddMaxEquality(lmax, loads)
        model.AddMinEquality(lmin, loads)
        p_fairness = lmax - lmin
    else:
        p_fairness = 0
    ub_fairness = max(1, max(load_upper_bounds, default=total_demand_minutes))

    penalties = {"agency": p_agency, "ot": p_ot, "future_debt": p_future_debt,
                 "unmet": p_unmet, "fairness": p_fairness}
    soft_ub = {"agency": max(1, ub_agency), "ot": max(1, ub_ot),
               "future_debt": ub_future_debt, "unmet": ub_unmet,
               "fairness": max(1, ub_fairness)}
    return penalties, soft_ub, raw_unmet


def _detect_lock_conflicts(inputs, slot_by_id, lock_errors) -> None:
    """Flag locks that can never hold together, for a precise reason instead of
    a bare INFEASIBLE."""
    pins = [lk for lk in inputs.locks if lk.pin and lk.slot_id in slot_by_id]
    by_staff: dict[str, list] = {}
    for lk in pins:
        by_staff.setdefault(lk.staff_id, []).append(slot_by_id[lk.slot_id])
    for staff_id, slots in by_staff.items():
        staff = next((s for s in inputs.staff if s.id == staff_id), None)
        rest = staff.min_rest_minutes if staff else 720
        for a, b in itertools.combinations(slots, 2):
            ia = absolute_interval(a.day_index, a.start_min, a.end_min, a.cross_midnight)
            ib = absolute_interval(b.day_index, b.start_min, b.end_min, b.cross_midnight)
            if intervals_conflict(ia, ib, rest):
                lock_errors.append(
                    f"Locked assignments conflict for one staff: {a.date} {a.shift_type} "
                    f"and {b.date} {b.shift_type} overlap or violate rest.")


def apply_objective(sm: SolverModel, weights) -> None:
    """Minimize BIG_M·(hard slack) + Σ weight·penalty. The hard term dominates so
    the solver eliminates coverage/ratio gaps before optimizing soft trade-offs."""
    p = sm.penalties
    hard = sum(sm.gap.values()) + sum(sm.ratio_short.values())
    sm.model.Minimize(
        BIG_M * hard
        + weights.agency * p["agency"]
        + weights.ot * p["ot"]
        + weights.future_debt * p["future_debt"]
        + weights.unmet_request * p["unmet"]
        + weights.fairness * p["fairness"]
    )
