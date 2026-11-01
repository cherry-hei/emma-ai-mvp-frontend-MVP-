"""Dependency-free rolling actual-work evidence. Soft advice, never a quota.

Scope includes a caller-versioned code bucket; N and AN are never merged here.
Completeness/eligibility are caller attestations, not inferred from roster rows.
No health reasons, rates, fitness or performance fields are accepted.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from fractions import Fraction
from typing import Iterable


@dataclass(frozen=True)
class Scope:
    organisation: str
    job_family: str
    code_bucket: str

    def __post_init__(self):
        if not all(isinstance(x, str) and x.strip() for x in
                   (self.organisation, self.job_family, self.code_bucket)):
            raise ValueError("Explicit nonempty scope required")


class EventKind(str, Enum):
    PLANNED = "planned"
    CANCELLED_PLANNED = "cancelled_planned"
    ACTUAL_WORK = "actual_work"
    ACTUAL_COVER = "actual_cover"


@dataclass(frozen=True)
class WorkEvent:
    event_id: str
    assignment_id: str  # same ID for original plan and replacement actual cover
    scope: Scope
    employee_id: str
    day: date  # roster/service date, counted once across midnight
    kind: EventKind
    actual_worked: bool | None = None


@dataclass(frozen=True)
class Eligibility:
    employee_id: str
    scope: Scope
    eligible: bool | None
    employment_start: date
    employment_end: date | None
    history_start: date
    history_end: date
    history_complete: bool
    # Explicit documented exposure denominator, never defaulted to 1.
    opportunities: Fraction | None = None
    expected_share: Fraction | None = None
    exposure_source: str | None = None


@dataclass(frozen=True)
class EmployeeEvidence:
    employee_id: str
    documented_actual: int
    actual_count: int | None
    actual_event_ids: tuple[str, ...]
    planned_event_ids: tuple[str, ...]
    cancelled_event_ids: tuple[str, ...]
    unknown_reasons: tuple[str, ...]
    per_opportunity: Fraction | None
    # Positive debt suggests fewer past assignments; negative is overallocation.
    carryforward_debt: Fraction | None


@dataclass(frozen=True)
class FairnessEvidence:
    scope: Scope
    start: date
    end: date
    employees: tuple[EmployeeEvidence, ...]
    spread: int | None
    soft_target: int = 3
    meets_soft_target: bool | None = None


def rolling_window(as_of: date) -> tuple[date, date]:
    """Exactly 365 inclusive calendar dates, including leap-year windows."""
    return as_of - timedelta(days=364), as_of


def fairness_evidence(scope: Scope, as_of: date, eligibility: Iterable[Eligibility],
                      events: Iterable[WorkEvent]) -> FairnessEvidence:
    """Reject scope mixing/future events/conflicting IDs; identical retries dedupe.

    Events before the window are retained as valid history but not credited.
    Only actual work/cover with actual_worked=True earns one assignment credit.
    One assignment may have at most one positive actual credit, even across staff.
    Explicit False earns none; None makes the employee's total unknown.
    """
    start, end = rolling_window(as_of)
    cohort = {}
    for person in eligibility:
        if person.scope != scope or not person.employee_id.strip():
            raise ValueError("Eligibility scope/identity mismatch")
        if person.employee_id in cohort:
            raise ValueError("Duplicate employee eligibility")
        if (person.eligible is not None and type(person.eligible) is not bool
                or type(person.history_complete) is not bool
                or person.history_start > person.history_end
                or person.history_end > as_of
                or person.employment_end is not None
                and person.employment_end < person.employment_start):
            raise ValueError("Invalid eligibility/history dates or flags")
        if any(value is not None and (type(value) not in (int, Fraction))
               for value in (person.opportunities, person.expected_share)):
            raise ValueError("Exposure values must be exact integers or Fractions")
        if person.opportunities is not None and person.opportunities <= 0:
            raise ValueError("Opportunity denominator must be positive")
        if person.expected_share is not None and person.expected_share < 0:
            raise ValueError("Expected share must be nonnegative")
        cohort[person.employee_id] = person
    unique = {}
    credits = {}
    for event in events:
        if (event.scope != scope or event.employee_id not in cohort
                or not event.event_id.strip() or not event.assignment_id.strip()
                or not isinstance(event.kind, EventKind) or event.day > as_of
                or event.actual_worked is not None and type(event.actual_worked) is not bool):
            raise ValueError("Invalid event scope/identity/date/kind/actual flag")
        if event.event_id in unique:
            if unique[event.event_id] != event:
                raise ValueError("Conflicting event ID")
            continue
        person = cohort[event.employee_id]
        if (event.day < person.employment_start or person.employment_end is not None
                and event.day > person.employment_end):
            raise ValueError("Event outside employment")
        actual = event.kind in (EventKind.ACTUAL_WORK, EventKind.ACTUAL_COVER)
        if not actual and event.actual_worked is not None:
            raise ValueError("Planned evidence cannot assert actual work")
        if actual and event.actual_worked is True:
            if event.assignment_id in credits:
                raise ValueError("Duplicate actual assignment credit")
            credits[event.assignment_id] = event.event_id
        unique[event.event_id] = event
    rows = []
    for person in cohort.values():
        lo = max(start, person.employment_start)
        hi = min(end, person.employment_end or end)
        if person.eligible is False or lo > hi:
            continue
        reasons = []
        if person.eligible is None:
            reasons.append("unknown eligibility")
        if (not person.history_complete or person.history_start > lo
                or person.history_end < hi):
            reasons.append("incomplete actual-work history")
        relevant = [e for e in unique.values()
                    if e.employee_id == person.employee_id and lo <= e.day <= hi]
        actual = [e for e in relevant if e.kind in
                  (EventKind.ACTUAL_WORK, EventKind.ACTUAL_COVER)]
        if any(e.actual_worked is None for e in actual):
            reasons.append("unknown actual worked")
        credited = tuple(e.event_id for e in actual if e.actual_worked is True)
        count = None if reasons else len(credited)
        exposure_known = (person.opportunities is not None
                          and bool(person.exposure_source and person.exposure_source.strip()))
        rate = (Fraction(count) / person.opportunities
                if count is not None and exposure_known else None)
        debt = (Fraction(person.expected_share) - count
                if count is not None and exposure_known
                and person.expected_share is not None else None)
        rows.append(EmployeeEvidence(
            person.employee_id, len(credited), count, credited,
            tuple(e.event_id for e in relevant if e.kind == EventKind.PLANNED),
            tuple(e.event_id for e in relevant if e.kind == EventKind.CANCELLED_PLANNED),
            tuple(reasons), rate, debt))
    counts = [r.actual_count for r in rows]
    spread = (max(counts) - min(counts)
              if counts and all(c is not None for c in counts) else None)
    return FairnessEvidence(scope, start, end, tuple(rows), spread, 3,
                            spread <= 3 if spread is not None else None)
