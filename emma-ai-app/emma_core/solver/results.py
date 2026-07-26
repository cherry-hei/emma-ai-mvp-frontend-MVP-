"""Pure output dataclasses returned by the solver — no DB or ortools types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SolvedAssignment:
    slot_id: str
    staff_id: str | None            # None => agency fill
    role: str | None
    is_agency: bool = False


@dataclass(frozen=True, slots=True)
class Violation:
    rule_code: str                  # constants.ViolationCode value
    slot_id: str | None
    message: str
    severity: str = "hard"


@dataclass(frozen=True, slots=True)
class SolverKpi:
    headcount_assigned: int = 0
    agency_count: int = 0
    ot_minutes: int = 0
    coverage_gap: int = 0
    ratio_breaches: int = 0
    deviation_from_baseline: int = 0
    fairness_spread_minutes: int = 0


@dataclass(frozen=True, slots=True)
class SolverResult:
    plan_mode: str                  # constants.PlanMode value
    label: str
    status: str                     # constants.SolveStatus value
    constraint_score: int
    hard_violation_count: int
    soft_penalty_total: int
    assignments: tuple[SolvedAssignment, ...] = ()
    violations: tuple[Violation, ...] = ()
    infeasible_reasons: tuple[str, ...] = ()
    kpi: SolverKpi = field(default_factory=SolverKpi)
    weights: dict | None = None
