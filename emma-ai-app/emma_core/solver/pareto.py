"""Pareto-style multi-objective roster selection (spec 9.1, Phase 3).

Phase 2 produced A/B/C by fixing three soft-weight presets. That answers "what
does the solver do under these three opinions?", not "what trade-offs are
actually available?". Here the same hard model is re-solved across a spread of
weight vectors, dominated candidates are discarded, and three *representative*
points are picked off the remaining frontier:

    A  the cost extreme          (least agency + overtime)
    B  the staff-satisfaction extreme (fewest unmet requests, most even load)
    C  the knee - the point closest to the ideal corner once each axis is
       normalised, i.e. the best all-round compromise the frontier offers

The three come back as ordinary SolverResult values with plan_mode A/B/C, so the
existing job, writeback and comparison UI need no special case.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..constants import PlanMode, SolveStatus
from . import scoring
from .inputs import PlanWeights, SolverInputs, SolverLimits
from .model import apply_objective, build_model
from .results import SolverResult

AXES = ("agency", "ot", "future_debt", "unmet", "fairness")
COST_AXES = ("agency", "ot")
SATISFACTION_AXES = ("unmet", "fairness")

PARETO_LABELS = {
    PlanMode.A: "Cost-Optimized · Pareto",
    PlanMode.B: "Staff-Satisfaction · Pareto",
    PlanMode.C: "Balanced · Pareto knee",
}


@dataclass(frozen=True, slots=True)
class ParetoPoint:
    weights: PlanWeights
    objectives: dict[str, int]
    result: SolverResult

    @property
    def vector(self) -> tuple[int, ...]:
        return tuple(self.objectives[a] for a in AXES)


def weight_grid(steps: int = 5) -> list[PlanWeights]:
    """A deterministic spread from the cost corner to the satisfaction corner,
    crossed with three fairness emphases. Deterministic so a re-run of the same
    period reproduces the same frontier."""
    grid: list[PlanWeights] = []
    for i in range(steps):
        t = i / (steps - 1) if steps > 1 else 0.0
        for fairness_mult in (0.6, 1.0, 1.5):
            grid.append(PlanWeights(
                agency=max(1, round(100 - 70 * t)),
                ot=max(1, round(90 - 50 * t)),
                future_debt=max(1, round(80 - 40 * t)),
                unmet_request=max(1, round(25 + 75 * t)),
                fairness=max(1, round((40 + 45 * t) * fairness_mult)),
            ))
    return grid


def _solve_with(inputs: SolverInputs, weights: PlanWeights,
                limits: SolverLimits) -> ParetoPoint | None:
    from ortools.sat.python import cp_model

    sm = build_model(inputs)
    if sm.lock_errors:
        return None
    apply_objective(sm, weights)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = limits.max_seconds
    solver.parameters.num_search_workers = limits.workers
    solver.parameters.random_seed = limits.seed
    status = solver.Solve(sm.model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    s, hard, soft = scoring.score(sm, solver, weights)
    violations = scoring.collect_violations(sm, solver)
    result = SolverResult(
        plan_mode=PlanMode.C, label="candidate",
        status=SolveStatus.OPTIMAL if status == cp_model.OPTIMAL else SolveStatus.FEASIBLE,
        constraint_score=s, hard_violation_count=hard, soft_penalty_total=soft,
        assignments=tuple(scoring.extract_assignments(sm, solver)),
        violations=tuple(violations),
        infeasible_reasons=tuple(v.message for v in violations),
        kpi=scoring.build_kpi(sm, solver, inputs),
        weights=asdict(weights),
    )
    return ParetoPoint(weights=weights, objectives=scoring.raw_objectives(sm, solver),
                       result=result)


def non_dominated(points: list[ParetoPoint]) -> list[ParetoPoint]:
    """Keep points no other point beats on every axis (all axes are minimised)."""
    keep: list[ParetoPoint] = []
    for p in points:
        dominated = any(
            other is not p
            and all(o <= q for o, q in zip(other.vector, p.vector))
            and any(o < q for o, q in zip(other.vector, p.vector))
            for other in points
        )
        if not dominated:
            keep.append(p)
    # collapse duplicates that landed on the same coordinates
    seen: dict[tuple[int, ...], ParetoPoint] = {}
    for p in keep:
        seen.setdefault(p.vector, p)
    return list(seen.values())


def _normalised(points: list[ParetoPoint]) -> list[dict[str, float]]:
    lows = {a: min(p.objectives[a] for p in points) for a in AXES}
    highs = {a: max(p.objectives[a] for p in points) for a in AXES}
    out = []
    for p in points:
        out.append({a: ((p.objectives[a] - lows[a]) / (highs[a] - lows[a])
                        if highs[a] > lows[a] else 0.0) for a in AXES})
    return out


def select_representatives(points: list[ParetoPoint]) -> dict[str, ParetoPoint]:
    """Cost extreme, satisfaction extreme, and the knee - distinct where possible."""
    if not points:
        return {}
    norms = _normalised(points)
    scored = list(zip(points, norms))

    cost = min(scored, key=lambda pn: sum(pn[1][a] for a in COST_AXES))[0]
    satisfaction = min(scored, key=lambda pn: sum(pn[1][a] for a in SATISFACTION_AXES))[0]
    knee = min(scored, key=lambda pn: sum(v * v for v in pn[1].values()))[0]

    chosen = {PlanMode.A: cost, PlanMode.B: satisfaction, PlanMode.C: knee}
    # If two roles collapsed onto the same point, spend the slot on another
    # frontier point rather than publishing the same roster twice.
    used: set[int] = set()
    for mode in (PlanMode.A, PlanMode.B, PlanMode.C):
        point = chosen[mode]
        if id(point) in used and len(points) > len(used):
            spare = next((p for p in points if id(p) not in used), point)
            chosen[mode] = spare
            point = spare
        used.add(id(point))
    return chosen


def solve_pareto(inputs: SolverInputs, limits: SolverLimits | None = None, *,
                 steps: int = 5) -> tuple[list[SolverResult], dict]:
    """Returns (three A/B/C results, frontier metadata for the compare UI)."""
    limits = limits or SolverLimits()
    grid = weight_grid(steps)
    per_solve = max(1.0, limits.max_seconds / max(1, len(grid)))
    budget = SolverLimits(max_seconds=per_solve, workers=limits.workers, seed=limits.seed)

    points = [p for p in (_solve_with(inputs, w, budget) for w in grid) if p]
    if not points:
        reasons = ["Pareto sweep found no feasible roster within the time budget "
                   "(check locked assignments, leave and staff max-hours)."]
        return ([SolverResult(plan_mode=m, label=PARETO_LABELS[m],
                              status=SolveStatus.INFEASIBLE, constraint_score=0,
                              hard_violation_count=0, soft_penalty_total=0,
                              infeasible_reasons=tuple(reasons))
                 for m in (PlanMode.A, PlanMode.B, PlanMode.C)],
                {"evaluated": len(grid), "frontier": []})

    frontier = non_dominated(points)
    chosen = select_representatives(frontier)

    results = []
    for mode in (PlanMode.A, PlanMode.B, PlanMode.C):
        point = chosen.get(mode)
        if not point:
            continue
        r = point.result
        results.append(SolverResult(
            plan_mode=mode, label=PARETO_LABELS[mode], status=r.status,
            constraint_score=r.constraint_score,
            hard_violation_count=r.hard_violation_count,
            soft_penalty_total=r.soft_penalty_total,
            assignments=r.assignments, violations=r.violations,
            infeasible_reasons=r.infeasible_reasons, kpi=r.kpi,
            weights={**(r.weights or {}), "selection": mode.value,
                     "objectives": point.objectives},
        ))

    meta = {
        "method": "pareto",
        "evaluated": len(grid),
        "feasible": len(points),
        "frontier_size": len(frontier),
        "axes": list(AXES),
        "frontier": [{"weights": asdict(p.weights), "objectives": p.objectives,
                      "constraint_score": p.result.constraint_score}
                     for p in frontier],
    }
    return results, meta
