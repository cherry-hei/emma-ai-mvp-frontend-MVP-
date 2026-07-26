"""Emma AI Phase 2 rostering engine (OR-Tools CP-SAT).

Generates three roster options — A (Cost-Optimized), B (Staff-Satisfaction),
C (Balanced) — from pure dataclass inputs. Importing this package does NOT require
ortools; the wheel is imported lazily the first time a model is built, so the rest
of ``emma_core`` stays importable without it. The DB mapping + writeback lives in
``emma_core.services.optimize``.
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
)
from .objective import PLAN_LABELS, PLAN_WEIGHTS
from .results import SolvedAssignment, SolverKpi, SolverResult, Violation
from .solve import build_and_solve, solve_plan

__all__ = [
    "StaffInput", "DemandSlot", "RatioRuleInput", "ResidentCountInput",
    "BaselineCell", "LockedAssignment", "SolverLimits", "PlanWeights", "SolverInputs",
    "SolvedAssignment", "Violation", "SolverKpi", "SolverResult",
    "PLAN_WEIGHTS", "PLAN_LABELS", "build_and_solve", "solve_plan",
]
