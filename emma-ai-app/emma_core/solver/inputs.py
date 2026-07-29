"""DB-free frozen dataclasses of primitives — the CP-SAT solver's inputs.

Row mapping lives in ``emma_core.services.optimize``, never here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date


@dataclass(frozen=True, slots=True)
class WorkPatternInput:
    """Facility-specific hard work pattern projected into solver primitives."""

    allowed_weekdays: frozenset[int] = frozenset()  # Monday=0; empty => any day
    required_shift_window: tuple[int, int] | None = None
    weekly_work_days: tuple[int, int] | None = None  # inclusive (minimum, maximum)
    fortnightly_work_days: tuple[int, int] | None = None
    saturday_requires_weekday_cl: bool = False


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
    night_cooldown: bool = False                  # no N/AN in this period
    an_monthly_limit: int = 2                     # 0 => uncapped
    nurse_night_monthly_limit: int = 2            # RN/EN total N/AN; 0 => uncapped
    prior_an_counts: tuple[tuple[int, int, int], ...] = ()      # (year, month, count)
    prior_night_counts: tuple[tuple[int, int, int], ...] = ()   # (year, month, count)
    long_shift_cost_scaled: int = 100             # 100 = 1.0; Home B imported 12h = 130
    work_pattern: WorkPatternInput = WorkPatternInput()


@dataclass(frozen=True, slots=True)
class DemandSlot:
    """One staffing requirement, derived from the source roster's working shifts."""
    id: str                                      # source shift id (natural key)
    date: Date
    day_index: int                               # (date - period_start).days
    shift_type: str
    # start/end/cross describe the OUTER envelope — the whole span the staff
    # member is unavailable, which is what overlap and rest checks need.
    start_min: int                               # minutes from midnight
    end_min: int
    cross_midnight: bool
    duration_min: int                            # PAID minutes (sum of segments)
    # Duty windows as (start, end, crosses). A split A/N shift has two; an
    # ordinary shift has one equal to the envelope. Ratio coverage uses these,
    # so a nurse is not counted as present during an unpaid rest gap.
    segments: tuple[tuple[int, int, bool], ...] = ()
    unit_id: str | None = None
    required_rank: str | None = None             # None => any rank
    required_count: int = 1
    requires_medication: bool = False
    agency_allowed: bool = True
    agency_cost_scaled: int = 10                 # round(cost_multiplier * 10); 10 == 1.0x
    is_event_overlay: bool = False


@dataclass(frozen=True, slots=True)
class RatioRuleInput:
    window_start_min: int
    window_end_min: int                          # may wrap midnight (end <= start)
    staff_rank: str | None = None                # None => any-rank rule
    unit_id: str | None = None
    care_level: str | None = None
    ratio_residents_per_staff: int | None = None
    min_staff_any_rank: int | None = None
    counted_ranks: frozenset[str] = frozenset()
    # Equivalent-head weights are integer-scaled for CP-SAT. A missing rank
    # receives ``weight_scale`` (one whole head).
    rank_weights: tuple[tuple[str, int], ...] = ()
    weight_scale: int = 100
    effective_dates: frozenset[Date] = frozenset()
    rule_id: str | None = None
    config_version: int = 1


@dataclass(frozen=True, slots=True)
class ResidentCountInput:
    date: Date
    resident_count: int
    unit_id: str | None = None
    care_level: str | None = None


@dataclass(frozen=True, slots=True)
class AgencyLimitsInput:
    """Primitive, solver-safe projection of the facility agency policy."""

    external_employment_types: frozenset[str] = frozenset({
        "agency", "outsource", "casual",
    })
    internal_full_time_types: frozenset[str] = frozenset({
        "local_ft", "imported_labor",
    })
    ratio_scale: int = 1000
    period_ratio_cap_scaled: int = 0       # 0 => disabled
    daily_rank_caps: tuple[tuple[str, int], ...] = ()
    monthly_shift_caps: tuple[tuple[str, int], ...] = ()
    vacancy_period_cap: int | None = None


@dataclass(frozen=True, slots=True)
class BaselineCell:
    """A cell of the human (source) roster — drives the unmet-request proxy."""
    staff_id: str
    date: Date
    shift_type: str
    is_working: bool


@dataclass(frozen=True, slots=True)
class PreferenceInput:
    """One pending staff request represented as a weighted soft preference."""

    staff_id: str
    date: Date
    prefer_working: bool
    shift_type: str | None = None
    weight: int = 1


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
    preferences: tuple[PreferenceInput, ...] = ()
    leave_unavailable: frozenset[tuple[str, Date]] = frozenset()   # (staff_id, date)
    locks: tuple[LockedAssignment, ...] = ()
    include_staff_ids: frozenset[str] = frozenset()   # empty => all staff
    exclude_staff_ids: frozenset[str] = frozenset()
    night_shift_types: frozenset[str] = frozenset()
    agency_limits: AgencyLimitsInput = AgencyLimitsInput()

    @property
    def period_days(self) -> int:
        return (self.period_end - self.period_start).days + 1
