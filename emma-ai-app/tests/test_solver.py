"""Pure, offline tests for the CP-SAT rostering engine - no DB, no Supabase.

Determinism: every solve uses SolverLimits(workers=1, seed=42) so results are
reproducible (multi-worker search is non-deterministic even with a fixed seed).
"""
from __future__ import annotations

from datetime import date

from emma_core.constants import PUBLISH_THRESHOLD, PlanMode, SolveStatus
from emma_core.solver import (
    BaselineCell,
    DemandSlot,
    LockedAssignment,
    SolverInputs,
    SolverLimits,
    StaffInput,
    build_and_solve,
    solve_plan,
)
from emma_core.solver.timeutils import absolute_interval, intervals_conflict

LIM = SolverLimits(workers=1, seed=42, max_seconds=5)
AUDIT = {"RN", "EN", "HW"}

# shift clocks (minutes)
A = (420, 900, False)     # 07:00–15:00
P = (810, 1290, False)    # 13:30–21:30
N = (1290, 420, True)     # 21:30–07:00 (+1)


def slot(sid, di, st, clock, rank, cnt=1, agency=True):
    s, e, cross = clock
    dur = (1440 - s) + e if (cross or e <= s) else e - s
    return DemandSlot(id=sid, date=date(2026, 7, 1 + di), day_index=di, shift_type=st,
                      start_min=s, end_min=e, cross_midnight=cross, duration_min=dur,
                      unit_id=None, required_rank=rank, required_count=cnt,
                      requires_medication=(rank in AUDIT), agency_allowed=agency)


def person(pid, rank, *, rest=660, contract=3000, maxp=0, audited=False):
    return StaffInput(id=pid, rank=rank, employment_type="local_ft",
                      is_audited_for_medication=audited, min_rest_minutes=rest,
                      contracted_period_minutes=contract, max_period_minutes=maxp)


def inputs(staff, demand, *, days=2, **kw):
    return SolverInputs(facility_id="f", period_id="p", period_start=date(2026, 7, 1),
                        period_end=date(2026, 7, days), staff=tuple(staff),
                        demand=tuple(demand), **kw)


def _no_conflict(res, demand, rest=660):
    by_slot = {d.id: d for d in demand}
    per_staff: dict[str, list] = {}
    for a in res.assignments:
        if a.staff_id:
            per_staff.setdefault(a.staff_id, []).append(by_slot[a.slot_id])
    for sls in per_staff.values():
        for i in range(len(sls)):
            for j in range(i + 1, len(sls)):
                ia = absolute_interval(sls[i].day_index, sls[i].start_min, sls[i].end_min, sls[i].cross_midnight)
                ib = absolute_interval(sls[j].day_index, sls[j].start_min, sls[j].end_min, sls[j].cross_midnight)
                if intervals_conflict(ia, ib, rest):
                    return False
    return True


def test_hard_constraints_hold():
    staff = [person("rn1", "RN", audited=True), person("cw1", "CW"), person("cw2", "CW")]
    demand = []
    for di in (0, 1):
        demand += [slot(f"rnA{di}", di, "A", A, "RN"),
                   slot(f"cwP{di}", di, "P", P, "CW"),
                   slot(f"cwN{di}", di, "N", N, "CW")]
    for res in build_and_solve(inputs(staff, demand), limits=LIM):
        assert res.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE)
        assert res.hard_violation_count == 0 and res.kpi.coverage_gap == 0
        # #7 eligibility: RN slots filled by the RN, never by a CW
        for a in res.assignments:
            if a.slot_id.startswith("rnA") and not a.is_agency:
                assert a.staff_id == "rn1"
        # #1 / #5 overlap + rest
        assert _no_conflict(res, demand), f"conflict in plan {res.plan_mode}"


def test_max_hours_respected():
    # one CW, capped at a single shift; two shifts exist -> the second goes to agency
    staff = [person("cw1", "CW", maxp=480, contract=480)]
    demand = [slot("d0", 0, "A", A, "CW"), slot("d1", 1, "A", A, "CW")]
    res = solve_plan(inputs(staff, demand), PlanMode.A, LIM)
    worked = sum(480 for a in res.assignments if a.staff_id == "cw1")
    assert worked <= 480                       # #6 hard cap
    assert res.hard_violation_count == 0       # agency covers the rest
    assert res.kpi.agency_count == 1


def test_leave_blocks_assignment():
    staff = [person("cw1", "CW"), person("cw2", "CW")]
    demand = [slot("d0", 0, "P", P, "CW")]
    inp = inputs(staff, demand, days=1, leave_unavailable=frozenset({("cw1", date(2026, 7, 1))}))
    res = solve_plan(inp, PlanMode.C, LIM)
    assert res.hard_violation_count == 0
    assert all(a.staff_id != "cw1" for a in res.assignments)   # #2 leave respected


def test_abc_differ_in_expected_direction():
    # One CW slot; the only local CW requested that day off. Honoring the request
    # forces an agency fill. Cost mode assigns the staffer anyway (avoids agency);
    # satisfaction mode honors the day off (uses agency); balanced sits between.
    # A single staffer means no fairness spread to muddy the agency-vs-request call.
    staff = [person("cw1", "CW")]
    demand = [slot("sP", 0, "P", P, "CW")]
    base = [BaselineCell("cw1", date(2026, 7, 1), "OFF", False)]
    a, b, c = build_and_solve(inputs(staff, demand, days=1, baseline=tuple(base)), limits=LIM)
    res = {r.plan_mode: r for r in (a, b, c)}
    A_, B_, C_ = res[PlanMode.A], res[PlanMode.B], res[PlanMode.C]
    # satisfaction honors the request most; cost honors it least
    assert B_.kpi.deviation_from_baseline <= C_.kpi.deviation_from_baseline <= A_.kpi.deviation_from_baseline
    # cost avoids agency most; satisfaction leans on it most
    assert A_.kpi.agency_count <= C_.kpi.agency_count <= B_.kpi.agency_count
    # and cost vs satisfaction are genuinely different plans
    assert A_.kpi.agency_count < B_.kpi.agency_count


def test_infeasible_scenario_returns_reasons():
    # need 2 RN on a night, only 1 RN, agency banned that night -> unavoidable gap
    staff = [person("rn1", "RN", audited=True)]
    demand = [slot("n0", 0, "N", N, "RN", cnt=2, agency=False)]
    res = solve_plan(inputs(staff, demand, days=1), PlanMode.C, LIM)
    assert res.hard_violation_count >= 1
    assert res.constraint_score < PUBLISH_THRESHOLD
    assert res.infeasible_reasons
    assert any("Coverage" in r or "coverage" in r for r in res.infeasible_reasons)


def test_locked_conflict_is_infeasible():
    staff = [person("cw1", "CW")]
    demand = [slot("sA", 0, "A", A, "CW"), slot("sP", 0, "P", P, "CW")]   # overlap
    locks = (LockedAssignment("cw1", "sA", True), LockedAssignment("cw1", "sP", True))
    res = solve_plan(inputs(staff, demand, days=1, locks=locks), PlanMode.C, LIM)
    assert res.status == SolveStatus.INFEASIBLE
    assert any("Locked" in r or "lock" in r for r in res.infeasible_reasons)


def test_empty_demand_scores_100():
    staff = [person("cw1", "CW")]
    for res in build_and_solve(inputs(staff, [], days=1), limits=LIM):
        assert res.constraint_score == 100
        assert res.hard_violation_count == 0
        assert res.assignments == ()
