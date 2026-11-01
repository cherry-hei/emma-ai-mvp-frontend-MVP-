"""Opt-in staged CP-SAT minimisation; no runtime wiring or approval semantics.

The caller owns hard validity, request penalty expressions and input versions.
All mutations (including objective replacement and optimum freezes) are made on
an isolated clone. The original model remains unchanged even on exceptions.
"""
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Sequence


class LayerName(str, Enum):
    AL = "AL"
    PH = "PH"
    MEDICAL_FU = "medicalFU"
    CL = "CL"
    ORDINARY_DUTY = "ordinaryduty"
    EXTERNAL_STAFF = "external_staff"
    FAIRNESS = "fairness"


PRIORITIES = tuple(LayerName)[:5]


@dataclass(frozen=True)
class ObjectiveLayer:
    name: LayerName
    penalty: Any  # integer CP-SAT expression: unfilled pending requests, not approvals


@dataclass(frozen=True)
class SolveConfig:
    seconds_per_stage: float = 10.0
    random_seed: int = 0
    workers: int = 1
    stop_after_first_solution: bool = False


@dataclass(frozen=True)
class StageEvidence:
    stage: int
    name: LayerName
    status: str
    value: int | None
    bound: float | None
    wall_seconds: float


@dataclass(frozen=True)
class LexicographicResult:
    stages: tuple[StageEvidence, ...]
    config: SolveConfig
    proven_optimal: bool
    # Variable-index values from the last stage with a solution; candidate only.
    candidate_values: tuple[int, ...] | None


def minimise_lexicographic(model: Any, layers: Sequence[ObjectiveLayer],
                           config: SolveConfig = SolveConfig()) -> LexicographicResult:
    """Freeze only proven integer optima, stopping at every non-OPTIMAL status.

    Supply all five request layers (zero expression when absent), followed only
    by explicitly ordered external-staff/fairness objectives. No budget/rates or
    resource-versus-request policy is invented. ImportError means OR-Tools is
    unavailable; importing this module itself does not require OR-Tools.
    """
    names = tuple(layer.name for layer in layers)
    if (any(not isinstance(name, LayerName) for name in names)
            or names[:5] != PRIORITIES or len(set(names)) != len(names)
            or any(name not in (LayerName.EXTERNAL_STAFF, LayerName.FAIRNESS)
                   for name in names[5:])):
        raise ValueError("Supply AL/PH/medicalFU/CL/ordinaryduty then declared lower layers")
    if (not math.isfinite(config.seconds_per_stage) or config.seconds_per_stage < 0
            or config.workers != 1 or type(config.random_seed) is not int
            or not 0 <= config.random_seed <= 2147483647):
        raise ValueError("Finite nonnegative time, one worker and nonnegative int32 seed required")
    from ortools.sat.python import cp_model

    working = model.clone()
    evidence = []
    candidate = None
    for stage, layer in enumerate(layers, 1):
        working.minimize(layer.penalty)
        # Floating objectives would not support an exact integer freeze.
        if working.proto.has_floating_point_objective():
            raise ValueError("Only integer objectives are supported")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = config.seconds_per_stage
        solver.parameters.random_seed = config.random_seed
        solver.parameters.num_search_workers = config.workers
        solver.parameters.stop_after_first_solution = config.stop_after_first_solution
        status = solver.solve(working)
        has_solution = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        value = int(solver.value(layer.penalty)) if has_solution else None
        bound = (solver.best_objective_bound
                 if status in (cp_model.OPTIMAL, cp_model.FEASIBLE, cp_model.UNKNOWN)
                 else None)
        evidence.append(StageEvidence(stage, layer.name, solver.status_name(status),
                                      value, bound, solver.wall_time))
        if has_solution:
            candidate = tuple(solver.response_proto.solution)
        if status != cp_model.OPTIMAL:
            break
        working.add(layer.penalty == value)
    return LexicographicResult(tuple(evidence), config,
                               len(evidence) == len(layers)
                               and all(e.status == "OPTIMAL" for e in evidence), candidate)
