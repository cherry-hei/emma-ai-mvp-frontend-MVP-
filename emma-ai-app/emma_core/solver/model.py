"""CP-SAT model construction: decision variables, the seven hard constraints,
and the five soft-penalty expressions.

Pure with respect to the DB — consumes :class:`SolverInputs` dataclasses. ortools
is imported lazily inside the functions so merely importing ``emma_core`` (or this
package) does not require the wheel to be installed.

Hard constraints (Solver Contract):
  #1 no overlap, #2 approved-leave unavailable, #3 required coverage,
  #4 SWD ratio, #5 min rest, #6 max hours, #7 task/rank eligibility.
#2 and #7 are realized by *not creating* an x-variable for impossible pairs;
#3 and #4 use bounded, heavily-penalized slack (gap / ratio_short) so the engine
returns an explainable roster instead of a bare INFEASIBLE.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from .inputs import DemandSlot, SolverInputs, StaffInput
from .objective import BIG_M
from .timeutils import absolute_interval, intervals_conflict, window_overlap

NOMINAL_SHIFT_MIN = 480   # one 8h shift; the common scale for day-based penalties


def eligible(staff: StaffInput, slot: DemandSlot, inputs: SolverInputs) -> bool:
    """Hard constraints #2 (leave) and #7 (rank / skill / audit): return False for
    (staff, slot) pairs that must never be assigned, so no variable is created."""
    if inputs.include_staff_ids and staff.id not in inputs.include_staff_ids:
        return False
    if staff.id in inputs.exclude_staff_ids:
        return False
    if slot.required_rank and staff.rank != slot.required_rank:
        return False
    if staff.allowed_shift_types and slot.shift_type not in staff.allowed_shift_types:
        return False
    if slot.requires_medication and not staff.is_audited_for_medication:
        return False
    if (staff.id, slot.date) in inputs.leave_unavailable:
        return False
    return True


@dataclass
class SolverModel:
    """Bundle of the CpModel and its variables so objective/scoring can read them
    without re-deriving anything. Holds ortools objects — not frozen."""
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
    dates = sorted({sl.date for sl in inputs.demand})
    total_demand_minutes = sum(sl.duration_min for sl in inputs.demand) or 1

    eligible_by_slot: dict[str, list[StaffInput]] = {
        sl.id: [s for s in inputs.staff if eligible(s, sl, inputs)] for sl in inputs.demand
    }

    # ── decision variables (eligible pairs only) ────────────────────────────
    x: dict[tuple[str, str], object] = {}
    for sl in inputs.demand:
        for s in eligible_by_slot[sl.id]:
            x[(s.id, sl.id)] = model.NewBoolVar(f"x_{s.id}_{sl.id}")

    # locks: a pin may force a pair eligibility skipped; also detect contradictions
    lock_errors: list[str] = []
    seen_pins: dict[str, str] = {}      # slot_id -> staff pinned (for quick dup detection)
    for lock in inputs.locks:
        sl = slot_by_id.get(lock.slot_id)
        if sl is None:
            lock_errors.append(f"Locked slot {lock.slot_id} is not in this period's demand.")
            continue
        key = (lock.staff_id, lock.slot_id)
        if lock.pin and key not in x:
            x[key] = model.NewBoolVar(f"x_{lock.staff_id}_{lock.slot_id}")  # manager override
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
        model.Add(sum(covered) + agency[sl.id] + gap[sl.id] >= sl.required_count)

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
            residents = sum(rc.resident_count for rc in inputs.resident_counts
                            if rc.date == d and (rule.unit_id is None or rc.unit_id == rule.unit_id))
            if rule.ratio_residents_per_staff:
                required = math.ceil(residents / rule.ratio_residents_per_staff) if residents else 0
            else:
                required = rule.min_staff_any_rank or 0
            if required <= 0:
                continue
            members: list = []
            for sl in inputs.demand:
                if sl.date != d:
                    continue
                if rule.staff_rank is not None and sl.required_rank != rule.staff_rank:
                    continue
                if rule.unit_id is not None and sl.unit_id != rule.unit_id:
                    continue
                if not window_overlap(sl.start_min, sl.end_min, sl.cross_midnight,
                                      rule.window_start_min, rule.window_end_min):
                    continue
                members.extend(x[(s.id, sl.id)] for s in eligible_by_slot[sl.id])
                members.append(agency[sl.id])
            short = model.NewIntVar(0, required, f"ratio_short_{d}_{k}")
            ratio_short[(d, k)] = short
            model.Add(sum(members) + short >= required)

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

    penalties, soft_ub, raw_unmet = _build_penalties(model, inputs, dates, total_demand_minutes,
                                                     x, agency, ot, works)

    return SolverModel(
        model=model, inputs=inputs, x=x, agency=agency, gap=gap, ratio_short=ratio_short,
        ot=ot, works=works, penalties=penalties, soft_ub=soft_ub, raw_unmet=raw_unmet,
        eligible_by_slot=eligible_by_slot, slot_by_id=slot_by_id, lock_errors=lock_errors,
    )


def _build_penalties(model, inputs, dates, total_demand_minutes, x, agency, ot, works):
    """The five soft-penalty terms on a shared *minute-equivalent* scale so the
    A/B/C weights compare like-for-like (a day of debt/deviation ≈ one shift =
    NOMINAL_SHIFT_MIN). Returns (penalties, soft_ub, raw_unmet) where soft_ub are
    upper bounds for score normalization and raw_unmet is the unscaled deviation
    count for the KPI."""
    # agency: fills × shift minutes × day cost multiplier (agency_cost_scaled/10)
    def agency_coeff(sl):
        return sl.duration_min * sl.agency_cost_scaled // 10
    p_agency = sum(agency[sl.id] * agency_coeff(sl) for sl in inputs.demand)
    ub_agency = sum(sl.required_count * agency_coeff(sl) for sl in inputs.demand)

    # OT: minutes beyond contract, summed over staff
    p_ot = sum(ot.values())
    ub_ot = total_demand_minutes

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

    # unmet request: deviation from the human baseline at day granularity
    staff_ids = {s.id for s in inputs.staff}
    unmet_terms = []
    for b in inputs.baseline:
        if b.staff_id not in staff_ids or (b.staff_id, b.date) not in works:
            continue
        w = works[(b.staff_id, b.date)]
        unmet_terms.append((1 - w) if b.is_working else w)
    raw_unmet = sum(unmet_terms)                 # count of deviating days
    p_unmet = NOMINAL_SHIFT_MIN * raw_unmet
    ub_unmet = NOMINAL_SHIFT_MIN * max(1, len(unmet_terms))

    # fairness: spread of worked minutes across staff (already minute-scaled)
    loads = []
    for s in inputs.staff:
        lv = model.NewIntVar(0, total_demand_minutes, f"load_{s.id}")
        terms = [sl.duration_min * x[(s.id, sl.id)] for sl in inputs.demand if (s.id, sl.id) in x]
        model.Add(lv == sum(terms))
        loads.append(lv)
    if len(loads) >= 2:
        lmax = model.NewIntVar(0, total_demand_minutes, "load_max")
        lmin = model.NewIntVar(0, total_demand_minutes, "load_min")
        model.AddMaxEquality(lmax, loads)
        model.AddMinEquality(lmin, loads)
        p_fairness = lmax - lmin
    else:
        p_fairness = 0
    ub_fairness = total_demand_minutes

    penalties = {"agency": p_agency, "ot": p_ot, "future_debt": p_future_debt,
                 "unmet": p_unmet, "fairness": p_fairness}
    soft_ub = {"agency": max(1, ub_agency), "ot": max(1, ub_ot),
               "future_debt": ub_future_debt, "unmet": ub_unmet,
               "fairness": max(1, ub_fairness)}
    return penalties, soft_ub, raw_unmet


def _detect_lock_conflicts(inputs, slot_by_id, lock_errors) -> None:
    """Pre-solve check for locks that can never be satisfied together, so we can
    report a precise reason rather than a bare INFEASIBLE."""
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
