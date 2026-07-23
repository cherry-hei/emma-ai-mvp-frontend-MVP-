"""Pure, DB-free inputs for the CP-SAT rostering engine.

Everything the solver needs is expressed as frozen dataclasses of primitives
(minutes as ints, dates as ``datetime.date``) so the model can be built and
unit-tested without Supabase, an ortools import, or any I/O. The mapping from
PostgREST rows to these dataclasses lives in ``emma_core.services.optimize`` —
never here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date


@dataclass(frozen=True, slots=True)
class StaffInput:
    id: str
    rank: str                                    # constants.Rank value
    employment_type: str                         # constants.EmploymentType value
    primary_unit_id: str | None = None
    is_audited_for_medication: bool = False
    min_rest_minutes: int = 720                  # imported labour default = 12h
    allowed_shift_types: frozenset[str] = frozenset()   # empty => all types allowed
    contracted_period_minutes: int = 0           # target minutes over period (OT reference)
    max_period_minutes: int = 0                  # hard cap; 0 => uncapped
    max_work_days: int = 0                        # fair max working days (future-debt ref); 0 => period length


@dataclass(frozen=True, slots=True)
class DemandSlot:
    """One staffing requirement: a shift on a date needing `required_count` of a
    role in a unit. Derived from the source manual roster's working shifts."""
    id: str                                      # source shift id (natural key)
    date: Date
    day_index: int                               # (date - period_start).days
    shift_type: str
    start_min: int                               # minutes from midnight
    end_min: int
    cross_midnight: bool
    duration_min: int
    unit_id: str | None = None
    required_rank: str | None = None             # None => any rank
    required_count: int = 1
    requires_medication: bool = False
    agency_allowed: bool = True
    agency_cost_scaled: int = 10                 # round(cost_multiplier * 10); 10 == 1.0x


@dataclass(frozen=True, slots=True)
class RatioRuleInput:
    window_start_min: int
    window_end_min: int                          # may wrap midnight (end <= start)
    staff_rank: str | None = None                # None => any-rank rule
    unit_id: str | None = None
    ratio_residents_per_staff: int | None = None
    min_staff_any_rank: int | None = None


@dataclass(frozen=True, slots=True)
class ResidentCountInput:
    date: Date
    resident_count: int
    unit_id: str | None = None


@dataclass(frozen=True, slots=True)
class BaselineCell:
    """A cell of the human (source) roster — drives the unmet-request proxy."""
    staff_id: str
    date: Date
    shift_type: str
    is_working: bool


@dataclass(frozen=True, slots=True)
class LockedAssignment:
    staff_id: str
    slot_id: str
    pin: bool = True                             # True => force assigned; False => forbid


@dataclass(frozen=True, slots=True)
class SolverLimits:
    max_seconds: float = 10.0
    workers: int = 8                             # tests use 1 for determinism
    seed: int = 42


@dataclass(frozen=True, slots=True)
class PlanWeights:
    agency: int
    ot: int
    future_debt: int
    unmet_request: int
    fairness: int


@dataclass(frozen=True, slots=True)
class SolverInputs:
    facility_id: str
    period_id: str
    period_start: Date
    period_end: Date
    staff: tuple[StaffInput, ...] = ()
    demand: tuple[DemandSlot, ...] = ()
    ratio_rules: tuple[RatioRuleInput, ...] = ()
    resident_counts: tuple[ResidentCountInput, ...] = ()
    baseline: tuple[BaselineCell, ...] = ()
    leave_unavailable: frozenset[tuple[str, Date]] = frozenset()   # (staff_id, date)
    locks: tuple[LockedAssignment, ...] = ()
    include_staff_ids: frozenset[str] = frozenset()   # empty => all staff
    exclude_staff_ids: frozenset[str] = frozenset()

    @property
    def period_days(self) -> int:
        return (self.period_end - self.period_start).days + 1
