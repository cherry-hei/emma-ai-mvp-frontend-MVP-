"""Synthetic actual CP-SAT tests; no API/data access."""
import pytest
cp = pytest.importorskip("ortools.sat.python.cp_model")
from emma_core.domain_profiles.lexicographic import (
    LayerName as N, ObjectiveLayer as L, PRIORITIES, SolveConfig,
    minimise_lexicographic,
)


def layers(first=0, second=0):
    return [L(n, v) for n, v in zip(PRIORITIES, [first, second, 0, 0, 0])]


def test_real_stages_beat_weighted_sum_and_preserve_original():
    m = cp.CpModel()
    al = m.new_bool_var("AL_unfilled")
    ph = m.new_int_var(0, 100, "PH_unfilled")
    m.add(ph == 100 * (1 - al))
    m.minimize(2 * al + ph)
    before = str(m.proto)
    result = minimise_lexicographic(m, layers(al, ph) + [L(N.EXTERNAL_STAFF, al)])
    assert result.proven_optimal
    assert [s.value for s in result.stages] == [0, 100, 0, 0, 0, 0]
    assert all(s.status == "OPTIMAL" and s.bound == s.value for s in result.stages)
    assert result.candidate_values[al.index] == 0
    assert str(m.proto) == before
    weighted = cp.CpSolver()
    assert weighted.solve(m) == cp.OPTIMAL
    assert weighted.value(al) == 1  # same fixture: weighted sum sacrifices AL


def test_approved_hard_lock_cannot_be_traded():
    m = cp.CpModel()
    unavailable = m.new_bool_var("approved_leave")
    m.add(unavailable == 1)
    r = minimise_lexicographic(m, layers(unavailable))
    assert r.proven_optimal and r.stages[0].value == 1


@pytest.mark.parametrize("kind, expected", [("infeasible", "INFEASIBLE"),
                                             ("invalid", "MODEL_INVALID"),
                                             ("timeout", "UNKNOWN")])
def test_actual_failure_statuses_do_not_advance_or_mutate(kind, expected):
    m = cp.CpModel()
    x = m.new_bool_var("x")
    if kind == "infeasible":
        m.add(x == 0)
        m.add(x == 1)
    if kind == "invalid":
        m.new_int_var(2, 1, "invalid_domain")
    before = str(m.proto)
    r = minimise_lexicographic(m, layers(x),
                              SolveConfig(seconds_per_stage=0 if kind == "timeout" else 5))
    assert not r.proven_optimal and len(r.stages) == 1
    assert r.stages[0].status == expected and r.stages[0].value is None
    assert r.candidate_values is None and str(m.proto) == before


def test_feasible_candidate_stops_without_freezing():
    m = cp.CpModel()
    xs = [m.new_bool_var(str(i)) for i in range(80)]
    for j in range(20):
        m.add(sum(((i * 17 + j * 31) % 97 + 1) * x for i, x in enumerate(xs)) >= 1200)
    # Disable presolve on the input model is not possible; this nontrivial cover
    # yields a genuine first-solution FEASIBLE status with one search worker.
    before = str(m.proto)
    r = minimise_lexicographic(m, layers(sum(xs)),
                              SolveConfig(stop_after_first_solution=True))
    assert r.stages[0].status == "FEASIBLE"
    assert len(r.stages) == 1 and not r.proven_optimal
    assert r.candidate_values is not None and str(m.proto) == before


@pytest.mark.parametrize("bad", [[], [L(N.PH, 0)] * 5,
                                      layers() + [L(N.AL, 0)]])
def test_reject_undeclared_priority_order(bad):
    with pytest.raises(ValueError):
        minimise_lexicographic(cp.CpModel(), bad)


def test_float_objective_rejected_transactionally():
    m = cp.CpModel()
    x = m.new_bool_var("x")
    before = str(m.proto)
    with pytest.raises(ValueError):
        minimise_lexicographic(m, layers(0.5 * x))
    assert str(m.proto) == before


@pytest.mark.parametrize("priority", range(4))
def test_each_request_priority_precedes_the_next(priority):
    m = cp.CpModel()
    x = m.new_bool_var("higher_unfilled")
    penalties = [0] * 5
    penalties[priority] = x
    penalties[priority + 1] = 100 * (1-x)
    r = minimise_lexicographic(m, [L(n, p) for n, p in zip(PRIORITIES, penalties)])
    assert r.proven_optimal
    assert r.stages[priority].value == 0
    assert r.stages[priority + 1].value == 100


def test_later_stage_exception_leaves_no_frozen_constraint_on_caller():
    m = cp.CpModel()
    x = m.new_bool_var("x")
    before = str(m.proto)
    with pytest.raises(ValueError):
        minimise_lexicographic(m, layers(x, 0.5*x))
    assert str(m.proto) == before


@pytest.mark.parametrize("config", [SolveConfig(seconds_per_stage=-1),
    SolveConfig(seconds_per_stage=float("nan")), SolveConfig(workers=2),
    SolveConfig(random_seed=-1)])
def test_invalid_config(config):
    with pytest.raises(ValueError):
        minimise_lexicographic(cp.CpModel(), layers(), config)
