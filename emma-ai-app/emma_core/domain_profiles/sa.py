"""Pure SA confirmed-rule evidence, version 2026-11-01; NOT live solver policy.

Intervals are half-open Hong Kong local wall-clock intervals. Elapsed minutes
are never paid minutes. Callers must still enforce leave, rest, hours and all
other effective policies. No I/O, approval writes or compliance certification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal


def _text(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('nonempty identity/evidence required')


def _day(value: date) -> None:
    if type(value) is not date:
        raise ValueError('calendar date required')


@dataclass(frozen=True)
class MonthlyAnchors:
    opens_on: date
    closes_on: date
    publication_year: int
    publication_month: int
    publication_week: int = 3
    display_timezone: str = 'Asia/Hong_Kong'
    exclusive_cutoff: datetime | None = None  # required runtime config, never inferred


def monthly_anchors(year: int, month: int) -> MonthlyAnchors:
    target = date(year, month, 1)
    previous = target - timedelta(days=1)
    earlier = previous.replace(day=1) - timedelta(days=1)
    return MonthlyAnchors(earlier.replace(day=25), previous.replace(day=10),
                          previous.year, previous.month)


@dataclass(frozen=True, order=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if (type(self.start) is not datetime or type(self.end) is not datetime
                or self.start.tzinfo is not None or self.end.tzinfo is not None
                or self.end <= self.start
                or self.start.second or self.end.second
                or self.start.microsecond or self.end.microsecond):
            raise ValueError('increasing minute-precision local interval required')

    @property
    def elapsed_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def overlaps(a: Interval, b: Interval) -> bool:
    return a.start < b.end and b.start < a.end


def interval_available(window: Interval, occupied: tuple[Interval, ...]) -> bool:
    """Free of occupancy only; does not imply leave/rest/qualification approval."""
    return not any(overlaps(window, item) for item in occupied)


@dataclass(frozen=True)
class Scope:
    organisation: str
    facility: str
    dictionary_version: str

    def __post_init__(self) -> None:
        for item in (self.organisation, self.facility, self.dictionary_version):
            _text(item)


@dataclass(frozen=True)
class Duty:
    scope: Scope
    staff_id: str
    family: Literal['HW', 'RCW', 'CW']
    anchor: date
    code: Literal['N', 'AN', 'A/N']

    def __post_init__(self) -> None:
        if not isinstance(self.scope, Scope):
            raise ValueError('explicit SA scope required')
        _text(self.staff_id)
        _day(self.anchor)
        if self.family not in {'HW', 'RCW', 'CW'} or self.code not in {'N', 'AN', 'A/N'}:
            raise ValueError('unsupported SA family/code')
        # Also rejects an unrepresentable next-day boundary.
        self.anchor + timedelta(days=1)

    @property
    def segments(self) -> tuple[Interval, ...]:
        def at(day: date, hour: int, minute: int) -> datetime:
            return datetime.combine(day, time(hour, minute))
        night = Interval(at(self.anchor, 21, 15 if self.code == 'N' else 30),
                         at(self.anchor + timedelta(days=1), 7, 15))
        return ((night,) if self.code == 'N' else
                (Interval(at(self.anchor, 7, 0), at(self.anchor, 14, 30)), night))


def validate_duties(duties: tuple[Duty, ...], scope: Scope) -> None:
    seen: set[tuple[str, date]] = set()
    families: dict[str, str] = {}
    occupied: dict[str, list[Interval]] = {}
    for duty in duties:
        if duty.scope != scope:
            raise ValueError('mixed scope')
        key = (duty.staff_id, duty.anchor)
        if key in seen:
            raise ValueError('duplicate staff/day assignment')
        seen.add(key)
        if families.setdefault(duty.staff_id, duty.family) != duty.family:
            raise ValueError('inconsistent staff family')
        prior = occupied.setdefault(duty.staff_id, [])
        if any(overlaps(a, b) for a in prior for b in duty.segments):
            raise ValueError('staff interval overlap')
        prior.extend(duty.segments)


@dataclass(frozen=True)
class CoverageSlice:
    interval: Interval
    staff_ids: tuple[str, ...]


@dataclass(frozen=True)
class NightEvidence:
    anchor: date
    rcw_ids: tuple[str, ...]
    hard_count_passes: bool
    slices: tuple[CoverageSlice, ...]  # zero-count slices are explicit gaps


def nightly_evidence(duties: tuple[Duty, ...], scope: Scope,
                     anchor: date) -> NightEvidence:
    _day(anchor)
    validate_duties(duties, scope)
    nights = [(d.staff_id, d.segments[-1]) for d in duties
              if d.anchor == anchor and d.family == 'RCW']
    # Clock comparison envelope, NOT an invented hard minute-coverage minimum.
    start = datetime.combine(anchor, time(21, 15))
    end = datetime.combine(anchor + timedelta(days=1), time(7, 15))
    points = sorted({start, end, *(p for _, i in nights for p in (i.start, i.end))})
    slices = tuple(CoverageSlice(Interval(a, b), tuple(sorted(
        sid for sid, i in nights if i.start <= a and i.end >= b)))
        for a, b in zip(points, points[1:]))
    ids = tuple(sorted({sid for sid, _ in nights}))
    return NightEvidence(anchor, ids, len(ids) >= 3, slices)


@dataclass(frozen=True)
class FairnessEvidence:
    staff_id: str
    an_count: int | None
    n_count: int | None
    penalty: int | None
    finding: str  # always soft; incomplete history is unknown


def monthly_fairness(duties: tuple[Duty, ...], scope: Scope, year: int, month: int,
                     applicable_ids: frozenset[str], *,
                     complete_month: bool) -> tuple[FairnessEvidence, ...]:
    date(year, month, 1)
    validate_duties(duties, scope)
    result = []
    for sid in sorted(applicable_ids):
        _text(sid)
        if not complete_month:
            result.append(FairnessEvidence(sid, None, None, None, 'unknown'))
            continue
        rows = [d for d in duties if d.staff_id == sid
                and (d.anchor.year, d.anchor.month) == (year, month)]
        an = sum(d.code != 'N' for d in rows)
        n = sum(d.code == 'N' for d in rows)
        penalty = max(0, 2 - an, an - 3)
        result.append(FairnessEvidence(sid, an, n, penalty,
                                      'soft_outside_2_3' if penalty else 'within_target'))
    return tuple(result)


@dataclass(frozen=True)
class Requirement:
    id: str
    role: str
    location: str
    interval: Interval
    required: int

    def __post_init__(self) -> None:
        for item in (self.id, self.role, self.location):
            _text(item)
        if type(self.required) is not int or self.required < 1:
            raise ValueError('positive hard requirement required')


@dataclass(frozen=True)
class Resource:
    staff_id: str
    role: str
    location: str
    interval: Interval
    cost_id: str  # one accounting identity per resource, no duplicate cost

    def __post_init__(self) -> None:
        for item in (self.staff_id, self.role, self.location, self.cost_id):
            _text(item)


@dataclass(frozen=True)
class Allocation:
    staff_id: str
    source: Literal['extra', 'baseline']
    qualified: bool | None
    simultaneous_compatible: bool | None = None
    compatibility_evidence: str | None = None


@dataclass(frozen=True)
class DrawAuthorisation:
    decision_id: str
    candidate_id: str
    task_id: str
    staff_ids: frozenset[str]
    authority_receipt: str
    reason: str
    budget_impact_cents: int


@dataclass(frozen=True)
class TaskEvidence:
    passes: bool
    findings: tuple[str, ...]
    remaining: tuple[tuple[str, int], ...]
    required_audit_fields: tuple[str, ...]
    authorisation: DrawAuthorisation | None
    task: Requirement
    baseline_minima: tuple[Requirement, ...]
    baseline_availability: tuple[Resource, ...]
    extra_availability: tuple[Resource, ...]
    allocations: tuple[Allocation, ...]

    @property
    def safe_to_propose(self) -> bool:
        """Planning evidence only: owner acceptance may still be outstanding.

        The CEO permits safe baseline-draw proposals before the normal whole-plan
        review. Missing/stale draw acceptance cannot waive a physical hard gap;
        it prevents final acceptance, not otherwise-feasible proposal generation.
        No return value authenticates receipts or commits any operational write.
        """
        return all(finding == 'missing or stale scoped draw authorisation'
                   for finding in self.findings)


def evaluate_task(task: Requirement, baseline_minima: tuple[Requirement, ...],
                  baseline: tuple[Resource, ...], extra: tuple[Resource, ...],
                  allocations: tuple[Allocation, ...], *, decision_id: str,
                  candidate_id: str, hard_minima_complete: bool,
                  authorisation: DrawAuthorisation | None = None) -> TaskEvidence:
    """Evaluate ONE task against a complete simultaneous baseline snapshot.

    Caller must include other task bookings as unavailable, supply all statutory
    and operational minima, and authenticate receipt provenance in a future
    transaction adapter. A returned pass neither creates audit nor approves.
    Unknown compatibility removes a drawn worker from base during this task.
    """
    _text(decision_id)
    _text(candidate_id)
    findings: list[str] = []
    resources = baseline + extra
    if (len({r.staff_id for r in resources}) != len(resources)
            or len({r.cost_id for r in resources}) != len(resources)):
        raise ValueError('duplicate resource or cost')
    if len({r.id for r in baseline_minima}) != len(baseline_minima):
        raise ValueError('duplicate hard minimum')
    if len({a.staff_id for a in allocations}) != len(allocations):
        raise ValueError('duplicate allocation')
    if not hard_minima_complete:
        findings.append('incomplete hard minima')
    by_source = {'baseline': {r.staff_id: r for r in baseline},
                 'extra': {r.staff_id: r for r in extra}}
    drawn = frozenset(a.staff_id for a in allocations if a.source == 'baseline')
    if drawn:
        if not baseline_minima:
            findings.append('baseline draw requires explicit hard minima')
        auth = authorisation
        if (auth is None or (auth.decision_id, auth.candidate_id, auth.task_id)
                != (decision_id, candidate_id, task.id) or auth.staff_ids != drawn
                or not auth.authority_receipt.strip() or not auth.reason.strip()
                or type(auth.budget_impact_cents) is not int):
            findings.append('missing or stale scoped draw authorisation')
    removed: set[str] = set()
    valid_count = 0
    for a in allocations:
        r = by_source.get(a.source, {}).get(a.staff_id)
        if (r is None or a.qualified is not True or r.role != task.role
                or r.interval.start > task.interval.start or r.interval.end < task.interval.end
                or (a.source == 'extra' and r.location != task.location)):
            findings.append(f'invalid task resource: {a.staff_id}')
            continue
        valid_count += 1
        if a.source == 'baseline':
            compatible = (a.simultaneous_compatible is True
                          and bool(a.compatibility_evidence and a.compatibility_evidence.strip()))
            if not compatible:
                removed.add(a.staff_id)
    if valid_count < task.required:
        findings.append('task shortfall')
    remaining = []
    # Sweep every hard minimum, including its portions outside the task.
    for req in baseline_minima:
        points = {req.interval.start, req.interval.end}
        for interval in (task.interval, *(r.interval for r in baseline)):
            for p in (interval.start, interval.end):
                if req.interval.start < p < req.interval.end:
                    points.add(p)
        ordered = sorted(points)
        counts = []
        for lo, hi in zip(ordered, ordered[1:]):
            counts.append(sum(r.role == req.role and r.location == req.location
                              and r.interval.start <= lo and r.interval.end >= hi
                              and not (r.staff_id in removed
                                       and overlaps(Interval(lo, hi), task.interval))
                              for r in baseline))
        count = min(counts)
        remaining.append((req.id, count))
        if count < req.required:
            findings.append(f'hard baseline shortfall: {req.id}')
    return TaskEvidence(not findings, tuple(findings), tuple(remaining),
                        ('decision_id', 'candidate_id', 'task_id', 'authority_receipt',
                         'reason', 'staff_ids', 'role', 'location', 'interval',
                         'affected_unit_counts', 'budget_impact_cents',
                         'qualification_evidence', 'compatibility_evidence',
                         'hard_minima_version', 'audit_receipt', 'outbox_receipt'),
                        authorisation, task, baseline_minima, baseline, extra, allocations)
