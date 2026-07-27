"""Turn a solved CP-SAT model into scores, KPIs, and human-readable reasons."""
from __future__ import annotations

from ..constants import PUBLISH_THRESHOLD, ViolationCode
from .model import SolverModel
from .results import SolvedAssignment, SolverKpi, Violation

_HARD_STEP = 5   # score points shed per unit of unresolved hard slack


def _val(solver, expr):
    """solver.Value for a var/expr; passthrough for a plain int (empty penalties
    degenerate to 0)."""
    return expr if isinstance(expr, int) else solver.Value(expr)


def extract_assignments(sm: SolverModel, solver) -> list[SolvedAssignment]:
    out: list[SolvedAssignment] = []
    for (sid, slot_id), var in sm.x.items():
        if solver.Value(var) == 1:
            sl = sm.slot_by_id[slot_id]
            out.append(SolvedAssignment(slot_id=slot_id, staff_id=sid, role=sl.required_rank))
    for slot_id, var in sm.agency.items():
        sl = sm.slot_by_id[slot_id]
        for _ in range(solver.Value(var)):
            out.append(SolvedAssignment(slot_id=slot_id, staff_id=None,
                                        role=sl.required_rank, is_agency=True))
    return out


def collect_violations(sm: SolverModel, solver) -> list[Violation]:
    vs: list[Violation] = []
    for slot_id, var in sm.gap.items():
        n = solver.Value(var)
        if n > 0:
            sl = sm.slot_by_id[slot_id]
            vs.append(Violation(
                rule_code=ViolationCode.COVERAGE, slot_id=slot_id,
                message=(f"Coverage short by {n}: {sl.date} {sl.shift_type} "
                         f"{sl.required_rank or 'any rank'} (needed {sl.required_count})"),
            ))
    for (d, k), var in sm.ratio_short.items():
        n = solver.Value(var)
        if n > 0:
            rule = sm.inputs.ratio_rules[k]
            vs.append(Violation(
                rule_code=ViolationCode.RATIO, slot_id=None,
                message=f"SWD ratio short by {n} on {d} for {rule.staff_rank or 'any rank'}.",
            ))
    return vs


def raw_objectives(sm: SolverModel, solver) -> dict[str, int]:
    """Unweighted penalty per objective axis — the coordinates a Pareto comparison
    needs. Weighted totals can't be compared across plans with different weights."""
    p = sm.penalties
    return {
        "agency": _val(solver, p["agency"]),
        "ot": _val(solver, p["ot"]),
        "future_debt": _val(solver, p["future_debt"]),
        "unmet": _val(solver, p["unmet"]),
        "fairness": _val(solver, p["fairness"]),
        "hard": (sum(solver.Value(v) for v in sm.gap.values())
                 + sum(solver.Value(v) for v in sm.ratio_short.values())),
    }


def score(sm: SolverModel, solver, weights) -> tuple[int, int, int]:
    """Returns (constraint_score, hard_violation_count, soft_penalty_total).

    Score is 100 - normalized(soft); any hard slack forces it below
    PUBLISH_THRESHOLD (minus _HARD_STEP per unit) so an unsafe roster can never
    look publishable."""
    hard = (sum(solver.Value(v) for v in sm.gap.values())
            + sum(solver.Value(v) for v in sm.ratio_short.values()))
    p, ub = sm.penalties, sm.soft_ub
    soft = (weights.agency * _val(solver, p["agency"])
            + weights.ot * _val(solver, p["ot"])
            + weights.future_debt * _val(solver, p["future_debt"])
            + weights.unmet_request * _val(solver, p["unmet"])
            + weights.fairness * _val(solver, p["fairness"]))
    worst = max(1, (weights.agency * ub["agency"] + weights.ot * ub["ot"]
                    + weights.future_debt * ub["future_debt"]
                    + weights.unmet_request * ub["unmet"] + weights.fairness * ub["fairness"]))
    base = max(0, min(100, round(100 * (1 - soft / worst))))
    if hard > 0:
        return max(0, min(base, PUBLISH_THRESHOLD - 1) - _HARD_STEP * hard), hard, soft
    return base, hard, soft


def build_kpi(sm: SolverModel, solver, inputs) -> SolverKpi:
    assigns = extract_assignments(sm, solver)
    return SolverKpi(
        headcount_assigned=sum(1 for a in assigns if not a.is_agency),
        agency_count=sum(1 for a in assigns if a.is_agency),
        ot_minutes=sum(solver.Value(v) for v in sm.ot.values()),
        coverage_gap=sum(solver.Value(v) for v in sm.gap.values()),
        ratio_breaches=sum(1 for v in sm.ratio_short.values() if solver.Value(v) > 0),
        deviation_from_baseline=_val(solver, sm.raw_unmet),
        fairness_spread_minutes=_val(solver, sm.penalties["fairness"]),
    )
