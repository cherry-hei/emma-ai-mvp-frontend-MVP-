"""A/B/C plan weight presets.

The hard-constraint model is identical across the three plans; only these
soft-penalty weights change, which is what makes A/B/C meaningfully different.
Values come straight from the project's agreed Solver Contract:
(agency, ot, future_debt, unmet_request, fairness).
"""
from __future__ import annotations

from ..constants import PlanMode
from .inputs import PlanWeights

PLAN_WEIGHTS: dict[PlanMode, PlanWeights] = {
    PlanMode.A: PlanWeights(agency=100, ot=90, future_debt=80, unmet_request=25, fairness=40),
    PlanMode.B: PlanWeights(agency=30, ot=40, future_debt=40, unmet_request=100, fairness=85),
    PlanMode.C: PlanWeights(agency=60, ot=65, future_debt=60, unmet_request=65, fairness=70),
}

PLAN_LABELS: dict[PlanMode, str] = {
    PlanMode.A: "Cost-Optimized",
    PlanMode.B: "Staff-Satisfaction",
    PlanMode.C: "Balanced",
}

# Large enough to dominate the entire achievable soft penalty (which is on a
# minute-equivalent scale — see model._build_penalties), so covering a shift or
# meeting a ratio always beats any soft trade-off.
BIG_M = 1_000_000_000
