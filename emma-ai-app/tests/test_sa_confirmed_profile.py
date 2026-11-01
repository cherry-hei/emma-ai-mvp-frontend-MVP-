"""Synthetic, offline SA primitive evidence only; no live solver acceptance."""
from datetime import date, datetime

import pytest

from emma_core.domain_profiles.sa import (
    Allocation, DrawAuthorisation, Duty, Interval, Requirement, Resource, Scope,
    evaluate_task, interval_available, monthly_anchors, monthly_fairness,
    nightly_evidence, overlaps, validate_duties,
)

SCOPE = Scope('synthetic-SA', 'fixture-home', '2026-11-01')
DAY = date(2026, 12, 31)


def duty(sid='s1', code='N', day=DAY, family='RCW'):
    return Duty(SCOPE, sid, family, day, code)


def interval(start='2026-12-31T08:00', end='2026-12-31T10:00'):
    return Interval(datetime.fromisoformat(start), datetime.fromisoformat(end))


@pytest.mark.parametrize('year,month,opening,closing,publication', [
    (2027, 1, date(2026, 11, 25), date(2026, 12, 10), (2026, 12)),
    (2028, 2, date(2027, 12, 25), date(2028, 1, 10), (2028, 1)),
    (2028, 3, date(2028, 1, 25), date(2028, 2, 10), (2028, 2)),
    (2027, 12, date(2027, 10, 25), date(2027, 11, 10), (2027, 11)),
])
def test_month_anchors(year, month, opening, closing, publication):
    result = monthly_anchors(year, month)
    assert (result.opens_on, result.closes_on) == (opening, closing)
    assert (result.publication_year, result.publication_month) == publication
    assert result.publication_week == 3
    assert result.display_timezone == 'Asia/Hong_Kong'
    assert result.exclusive_cutoff is None


@pytest.mark.parametrize('year,month', [(2027, 0), (2027, 13), (1, 1)])
def test_invalid_month_boundaries(year, month):
    with pytest.raises((ValueError, OverflowError)):
        monthly_anchors(year, month)


def test_separate_clocks_elapsed_not_paid_and_gap():
    n, an = duty(), duty('s2', 'AN')
    assert [i.elapsed_minutes for i in n.segments] == [600]
    assert [i.elapsed_minutes for i in an.segments] == [450, 585]
    assert n.segments[-1].start.hour == 21 and n.segments[-1].start.minute == 15
    assert an.segments[-1].end.date() == date(2027, 1, 1)
    gap = interval('2026-12-31T14:30', '2026-12-31T21:30')
    assert interval_available(gap, an.segments)
    assert not hasattr(an, 'paid_minutes')
    assert duty('s2', 'A/N').segments == an.segments


@pytest.mark.parametrize('day,next_day', [
    (date(2026, 12, 31), date(2027, 1, 1)),
    (date(2028, 2, 28), date(2028, 2, 29)),
    (date(2028, 2, 29), date(2028, 3, 1)),
])
def test_next_day_a_overlaps_prior_n_fifteen_minutes(day, next_day):
    n, an = duty(day=day), duty(code='AN', day=next_day)
    assert overlaps(n.segments[-1], an.segments[0])
    assert int((n.segments[-1].end - an.segments[0].start).total_seconds() / 60) == 15
    with pytest.raises(ValueError, match='overlap'):
        validate_duties((n, an), SCOPE)


@pytest.mark.parametrize('first,second', [('N', 'AN'), ('AN', 'A/N'), ('N', 'N')])
def test_staff_day_uniqueness(first, second):
    with pytest.raises(ValueError, match='duplicate'):
        validate_duties((duty(code=first), duty(code=second)), SCOPE)


@pytest.mark.parametrize('kwargs', [
    {'code': 'an'}, {'code': 'A-N'}, {'family': 'RN'}, {'sid': ''},
    {'day': '2026-12-31'}, {'day': datetime(2026, 12, 31)},
    {'day': date.max},
])
def test_invalid_duty(kwargs):
    with pytest.raises((ValueError, OverflowError)):
        duty(**kwargs)


def test_scope_and_family_consistency():
    with pytest.raises(ValueError, match='scope'):
        validate_duties((duty(),), Scope('other-org', 'fixture-home', 'v1'))
    with pytest.raises(ValueError, match='family'):
        validate_duties((duty(), duty(day=date(2027, 1, 2), family='CW')), SCOPE)


def test_touching_intervals_are_available_invalid_intervals_rejected():
    assert interval_available(interval('2026-12-31T10:00', '2026-12-31T11:00'), (interval(),))
    with pytest.raises(ValueError):
        interval('2026-12-31T10:00', '2026-12-31T08:00')
    with pytest.raises(ValueError):
        interval('2026-12-31T08:00:01', '2026-12-31T10:00')


def test_nightly_distinct_mixed_codes_and_no_maximum():
    rows = (duty('1'), duty('2', 'AN'), duty('3', 'A/N'), duty('4'))
    result = nightly_evidence(rows, SCOPE, DAY)
    assert result.hard_count_passes and result.rcw_ids == ('1', '2', '3', '4')
    assert [len(s.staff_ids) for s in result.slices] == [2, 4]
    assert result.slices[0].interval.elapsed_minutes == 15


@pytest.mark.parametrize('family', ['CW', 'HW'])
def test_two_rcw_plus_other_family_fails(family):
    result = nightly_evidence((duty('1'), duty('2'), duty('3', family=family)), SCOPE, DAY)
    assert not result.hard_count_passes
    assert result.rcw_ids == ('1', '2')


def test_an_count_pass_exposes_early_gap_without_invented_hard_window():
    result = nightly_evidence(tuple(duty(str(i), 'AN') for i in range(3)), SCOPE, DAY)
    assert result.hard_count_passes
    assert result.slices[0].staff_ids == ()
    assert result.slices[0].interval.elapsed_minutes == 15
    empty = nightly_evidence((), SCOPE, DAY)
    assert not empty.hard_count_passes and empty.slices[0].staff_ids == ()


@pytest.mark.parametrize('count,penalty', [(0, 2), (1, 1), (2, 0), (3, 0), (4, 1)])
def test_fairness_soft_separate_n_and_month_anchor(count, penalty):
    rows = tuple(duty(code='AN', day=date(2026, 12, 1 + 2*i)) for i in range(count))
    rows += (duty(day=DAY), duty('ineligible', 'AN'))
    result, = monthly_fairness(rows, SCOPE, 2026, 12, frozenset({'s1'}), complete_month=True)
    assert (result.an_count, result.n_count, result.penalty) == (count, 1, penalty)
    january, = monthly_fairness(rows, SCOPE, 2027, 1, frozenset({'s1'}), complete_month=True)
    assert january.an_count == january.n_count == 0


def test_fairness_unknown_not_zero_and_alias_once():
    result, = monthly_fairness((duty(code='A/N'),), SCOPE, 2026, 12,
                              frozenset({'s1'}), complete_month=True)
    assert result.an_count == 1
    unknown, = monthly_fairness((), SCOPE, 2026, 12, frozenset({'s1'}), complete_month=False)
    assert (unknown.an_count, unknown.n_count, unknown.penalty) == (None, None, None)


def task_case(*, draw=False, count=2, auth=True, compatible=None, evidence=None,
              complete=True, qualified=True, extra_location='task-room'):
    span = interval()
    task = Requirement('task', 'HW', 'task-room', span, 1)
    floor = Requirement('floor', 'HW', 'East', span, 2)
    base = tuple(Resource(f'b{i}', 'HW', 'East', span, f'cost-b{i}') for i in range(count))
    extra = (Resource('e1', 'HW', extra_location, span, 'cost-e1'),)
    allocations = (Allocation('b0' if draw else 'e1', 'baseline' if draw else 'extra',
                              qualified, compatible, evidence),)
    receipt = (DrawAuthorisation('decision-v1', 'candidate-v1', 'task', frozenset({'b0'}),
                                 'synthetic-manager-receipt', 'reviewed draw', 0)
               if auth else None)
    return task, (floor,), base, extra, allocations, dict(
        decision_id='decision-v1', candidate_id='candidate-v1', hard_minima_complete=complete,
        authorisation=receipt)


def run_case(**kwargs):
    task, minima, base, extra, allocations, options = task_case(**kwargs)
    return evaluate_task(task, minima, base, extra, allocations, **options)


def test_additive_default_preserves_floor_and_has_no_audit_writes():
    result = run_case(auth=False)
    assert result.passes and result.remaining == (('floor', 2),)
    assert result.authorisation is None
    assert 'audit_receipt' in result.required_audit_fields


def test_draw_requires_scoped_authorisation_even_with_surplus():
    assert not run_case(draw=True, count=3, auth=False).passes
    assert run_case(draw=True, count=3).passes
    task, minima, base, extra, allocations, options = task_case(draw=True, count=3)
    options['candidate_id'] = 'candidate-v2'
    result = evaluate_task(task, minima, base, extra, allocations, **options)
    assert not result.passes and 'stale' in result.findings[0]


def test_authorised_draw_cannot_waive_floor_unknown_compatibility_removed():
    result = run_case(draw=True)
    assert not result.passes and result.remaining == (('floor', 1),)
    assert 'hard baseline shortfall: floor' in result.findings
    assert not run_case(draw=True, compatible=True).passes
    assert run_case(draw=True, compatible=True, evidence='confirmed-location-policy-v1').passes


@pytest.mark.parametrize('kwargs', [
    {'complete': False}, {'qualified': None}, {'qualified': False},
    {'extra_location': 'West'},
])
def test_missing_or_incompatible_task_inputs_block(kwargs):
    assert not run_case(**kwargs).passes


def test_duplicate_resources_costs_and_allocations_rejected():
    task, minima, base, extra, allocations, options = task_case()
    for changed_base, changed_extra, changed_allocations in [
        (base + (base[0],), extra, allocations),
        (base, (Resource('e2', 'HW', 'task-room', interval(), 'cost-b0'),), allocations),
        (base, extra, allocations + allocations),
    ]:
        with pytest.raises(ValueError, match='duplicate'):
            evaluate_task(task, minima, changed_base, changed_extra, changed_allocations, **options)


def test_simultaneous_floor_sweep_and_task_duration():
    task, minima, base, extra, allocations, options = task_case(draw=True, count=3)
    # A worker departs halfway through the task: aggregate surplus is insufficient.
    base = base[:2] + (Resource('b2', 'HW', 'East',
                               interval(end='2026-12-31T09:00'), 'cost-b2'),)
    assert not evaluate_task(task, minima, base, extra, allocations, **options).passes
    task, minima, base, extra, allocations, options = task_case()
    extra = (Resource('e1', 'HW', 'task-room', interval(end='2026-12-31T09:00'), 'cost-e1'),)
    assert not evaluate_task(task, minima, base, extra, allocations, **options).passes


def test_other_location_hard_minimum_cannot_be_ignored():
    task, minima, base, extra, allocations, options = task_case(draw=True, count=3)
    minima += (Requirement('West-floor', 'HW', 'West', interval(), 1),)
    result = evaluate_task(task, minima, base, extra, allocations, **options)
    assert not result.passes and ('West-floor', 0) in result.remaining


def test_draw_without_explicit_baseline_minima_blocked():
    task, _, base, extra, allocations, options = task_case(draw=True, count=3)
    assert not evaluate_task(task, (), base, extra, allocations, **options).passes


def test_evidence_retains_required_available_extra_and_allocation_identity():
    task, minima, base, extra, allocations, options = task_case()
    result = evaluate_task(task, minima, base, extra, allocations, **options)
    assert (result.task, result.baseline_minima, result.baseline_availability,
            result.extra_availability, result.allocations) == (task, minima, base, extra, allocations)


def test_safe_draw_proposal_can_precede_normal_owner_acceptance():
    result = run_case(draw=True, count=3, auth=False)
    assert result.safe_to_propose
    assert not result.passes
    assert result.remaining == (('floor', 2),)
    assert result.authorisation is None


def test_proposal_may_not_waive_hard_shortfall_or_unknown_qualification():
    assert not run_case(draw=True, count=2, auth=False).safe_to_propose
    assert not run_case(draw=True, count=3, auth=False, qualified=None).safe_to_propose
    assert not run_case(draw=True, count=3, auth=False, complete=False).safe_to_propose
    assert run_case(draw=False, auth=False).safe_to_propose
