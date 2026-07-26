"""Run the CP-SAT solver for one plan, or all three A/B/C plans."""
from __future__ import annotations

from dataclasses import asdict

from ..constants import PlanMode, SolveStatus
from . import scoring
from .inputs import SolverInputs, SolverLimits
from .model import apply_objective, build_model
from .objective import PLAN_LABELS, PLAN_WEIGHTS
from .results import SolverResult


def _infeasible(plan_mode, label, weights, reasons) -> SolverResult:
    return SolverResult(
        plan_mode=plan_mode, label=label, status=SolveStatus.INFEASIBLE,
        constraint_score=0, hard_violation_count=0, soft_penalty_total=0,
        infeasible_reasons=tuple(reasons), weights=asdict(weights),
    )


def solve_plan(inputs: SolverInputs, plan_mode: PlanMode,
               limits: SolverLimits | None = None) -> SolverResult:
    from ortools.sat.python import cp_model

    limits = limits or SolverLimits()
    weights = PLAN_WEIGHTS[plan_mode]
    label = PLAN_LABELS[plan_mode]

    sm = build_model(inputs)
    if sm.lock_errors:                       # contradictory locks => report, don't solve
        return _infeasible(plan_mode, label, weights, sm.lock_errors)

    apply_objective(sm, weights)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = limits.max_seconds
    solver.parameters.num_search_workers = limits.workers
    solver.parameters.random_seed = limits.seed
    status = solver.Solve(sm.model)

    if status == cp_model.OPTIMAL:
        solve_status = SolveStatus.OPTIMAL
    elif status == cp_model.FEASIBLE:
        solve_status = SolveStatus.FEASIBLE
    else:
        return _infeasible(plan_mode, label, weights, [
            "Solver found no feasible assignment within the time limit "
            "(check locked assignments and staff max-hours)."])

    s, hard, soft = scoring.score(sm, solver, weights)
    violations = scoring.collect_violations(sm, solver)
    return SolverResult(
        plan_mode=plan_mode, label=label, status=solve_status,
        constraint_score=s, hard_violation_count=hard, soft_penalty_total=soft,
        assignments=tuple(scoring.extract_assignments(sm, solver)),
        violations=tuple(violations),
        infeasible_reasons=tuple(v.message for v in violations),
        kpi=scoring.build_kpi(sm, solver, inputs),
        weights=asdict(weights),
    )


def build_and_solve(inputs: SolverInputs, modes=None,
                    limits: SolverLimits | None = None) -> list[SolverResult]:
    """Solve the requested plan modes (default all three A/B/C)."""
    modes = list(modes) if modes else [PlanMode.A, PlanMode.B, PlanMode.C]
    return [solve_plan(inputs, m, limits) for m in modes]
