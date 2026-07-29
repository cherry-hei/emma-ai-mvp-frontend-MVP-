"""Emma AI Phase 2 rostering engine (OR-Tools CP-SAT).

Generates three roster options — A (Cost-Optimized), B (Staff-Satisfaction),
C (Balanced) — from pure dataclass inputs. ortools is imported lazily on first
model build, so importing this package doesn't require the wheel.
"""
from .inputs import (
    BaselineCell,
    DemandSlot,
    LockedAssignment,
    PlanWeights,
    RatioRuleInput,
    ResidentCountInput,
    SolverInputs,
    SolverLimits,
    StaffInput,
    WorkPatternInput,
)
from .objective import PLAN_LABELS, PLAN_WEIGHTS
from .pareto import solve_pareto, weight_grid
from .results import SolvedAssignment, SolverKpi, SolverResult, Violation
from .solve import build_and_solve, solve_plan

__all__ = [
    "StaffInput", "WorkPatternInput", "DemandSlot", "RatioRuleInput", "ResidentCountInput",
    "BaselineCell", "LockedAssignment", "SolverLimits", "PlanWeights", "SolverInputs",
    "SolvedAssignment", "Violation", "SolverKpi", "SolverResult",
    "PLAN_WEIGHTS", "PLAN_LABELS", "build_and_solve", "solve_plan",
    "solve_pareto", "weight_grid",
]
