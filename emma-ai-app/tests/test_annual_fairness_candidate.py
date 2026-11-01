"""Synthetic opaque identifiers only; no source roster or health reasons."""
from dataclasses import replace
from datetime import date, timedelta
from fractions import Fraction
import pytest
from emma_core.domain_profiles.fairness import (
    Scope, Eligibility, WorkEvent, EventKind as K, rolling_window, fairness_evidence,
)

S = Scope("synthetic-org", "RCW", "N:v1")
END = date(2026, 11, 1)
START, _ = rolling_window(END)


def person(id="e1", **kw):
    return replace(Eligibility(id, S, True, date(2020, 1, 1), None,
                               START, END, True), **kw)


def event(id="a", employee="e1", **kw):
    return replace(WorkEvent(id, id, S, employee, END, K.ACTUAL_WORK, True), **kw)


@pytest.mark.parametrize("end", [date(2024, 2, 29), date(2025, 2, 28),
                                   date(2027, 1, 1), date(2026, 3, 1)])
def test_exact_365_inclusive_leap_year_and_month_boundaries(end):
    start, _ = rolling_window(end)
    p = person(history_start=start, history_end=end)
    events = [event("before", day=start-timedelta(days=1)),
              event("start", day=start), event("end", day=end)]
    r = fairness_evidence(S, end, [p], events)
    assert (r.end-r.start).days + 1 == 365
    assert r.employees[0].actual_count == 2


def test_original_plan_cancelled_replacement_only_gets_actual_credit():
    ps = [person("e1", opportunities=Fraction(10), expected_share=Fraction(1),
                 exposure_source="synthetic exposure v1"),
          person("e2", opportunities=Fraction(10), expected_share=Fraction(0),
                 exposure_source="synthetic exposure v1")]
    events = [event("plan", kind=K.PLANNED, actual_worked=None, assignment_id="shift"),
              event("cancel", kind=K.CANCELLED_PLANNED, actual_worked=None,
                    assignment_id="shift"),
              event("notworked", actual_worked=False, assignment_id="shift"),
              event("cover", "e2", kind=K.ACTUAL_COVER, assignment_id="shift")]
    r = fairness_evidence(S, END, ps, events + [events[-1]])
    a, b = r.employees
    assert (a.actual_count, b.actual_count) == (0, 1)
    assert a.planned_event_ids == ("plan",) and a.cancelled_event_ids == ("cancel",)
    assert (a.carryforward_debt, b.carryforward_debt) == (1, -1)
    assert b.per_opportunity == Fraction(1, 10)
    assert r.spread == 1 and r.meets_soft_target


@pytest.mark.parametrize("change", [{"history_complete": False}, {"eligible": None},
                                    {"history_start": START+timedelta(days=1)}])
def test_unknown_is_not_zero(change):
    r = fairness_evidence(S, END, [person(**change)], [event()])
    assert r.employees[0].documented_actual == 1
    assert r.employees[0].actual_count is None
    assert r.spread is None and r.meets_soft_target is None
    assert r.employees[0].carryforward_debt is None


def test_unknown_actual_and_no_default_normalisation():
    r = fairness_evidence(S, END, [person(expected_share=Fraction(2))],
                          [event(actual_worked=None)])
    assert r.employees[0].actual_count is None
    assert "unknown actual worked" in r.employees[0].unknown_reasons
    known = fairness_evidence(S, END, [person(expected_share=Fraction(2))], [])
    assert known.employees[0].actual_count == 0
    assert known.employees[0].per_opportunity is None
    assert known.employees[0].carryforward_debt is None


@pytest.mark.parametrize("bad", [event(day=END+timedelta(days=1)),
    event(scope=Scope("other", "RCW", "N:v1")),
    event(scope=Scope("synthetic-org", "CW", "N:v1")),
    event(scope=Scope("synthetic-org", "RCW", "AN:v1")),
    event(event_id=""), event(employee_id="missing"), event(actual_worked="yes")])
def test_invalid_scope_identity_and_date_rejected(bad):
    with pytest.raises(ValueError):
        fairness_evidence(S, END, [person()], [bad])


@pytest.mark.parametrize("other", [event(day=END-timedelta(days=1)),
    event("duplicate", assignment_id="a"),
    event("duplicate", "e2", assignment_id="a", kind=K.ACTUAL_COVER)])
def test_conflicting_id_or_duplicate_actual_credit(other):
    with pytest.raises(ValueError):
        fairness_evidence(S, END, [person(), person("e2")], [event(), other])


def test_soft_spread_and_employment_window():
    p = person(employment_start=END, history_start=END)
    r = fairness_evidence(S, END, [p, person("e2")],
                          [event(str(i)) for i in range(4)])
    assert r.spread == 4 and r.meets_soft_target is False
    with pytest.raises(ValueError):
        fairness_evidence(S, END, [p], [event(day=END-timedelta(days=1))])


def test_empty_or_ineligible_cohort_is_unknown():
    for ps in ([], [person(eligible=False)]):
        assert fairness_evidence(S, END, ps, []).spread is None


@pytest.mark.parametrize("kw", [{"opportunities": Fraction(0)},
    {"expected_share": Fraction(-1)}, {"history_end": END+timedelta(days=1)},
    {"employment_end": date(2010, 1, 1)}])
def test_invalid_exposure_and_dates(kw):
    with pytest.raises(ValueError):
        fairness_evidence(S, END, [person(**kw)], [])


@pytest.mark.parametrize("kw", [{"opportunities": 0.5}, {"expected_share": True}])
def test_exposure_requires_exact_numbers(kw):
    with pytest.raises(ValueError):
        fairness_evidence(S, END, [person(**kw)], [])


def test_unknown_exposure_source_does_not_create_debt():
    r = fairness_evidence(S, END, [person(opportunities=Fraction(10),
                                         expected_share=Fraction(2))], [event()])
    assert r.employees[0].actual_count == 1
    assert r.employees[0].per_opportunity is None
    assert r.employees[0].carryforward_debt is None


def test_ended_employment_needs_only_documented_employment_interval():
    ended = END-timedelta(days=30)
    p = person(employment_end=ended, history_end=ended)
    r = fairness_evidence(S, END, [p], [event(day=ended)])
    assert r.employees[0].actual_count == 1
