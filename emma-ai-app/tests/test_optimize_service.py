"""Offline tests for the optimize service using an in-memory fake Supabase client.

Exercises the DB<->dataclass mapping and writeback without a real database. The
fake implements only the chained calls load_inputs / writeback / job-lifecycle use.
"""
from __future__ import annotations

import uuid

from emma_core.constants import JobStatus, PlanMode
from emma_core.models import OptimizeRequest, WritebackOptions
from emma_core.services import optimize


# ── minimal chainable fake Supabase client ───────────────────────────────────
class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self._store, self._t = store, table
        self._mode, self._payload = "select", None
        self._filters, self._order, self._desc, self._limit = [], None, False, None

    # builders
    def select(self, *a, **k):
        return self

    def insert(self, payload):
        self._mode, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._mode, self._payload = "update", payload
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val)); return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals))); return self

    def gte(self, col, val):
        self._filters.append(("gte", col, val)); return self

    def lte(self, col, val):
        self._filters.append(("lte", col, val)); return self

    def or_(self, expr):
        terms = []
        for t in expr.split(","):
            col, op, val = t.split(".", 2)
            terms.append((col, op, val))
        self._filters.append(("or", terms)); return self

    def order(self, col, desc=False):
        self._order, self._desc = col, desc; return self

    def limit(self, n):
        self._limit = n; return self

    # terminal
    def _match(self, row):
        for f in self._filters:
            if f[0] == "eq" and row.get(f[1]) != f[2]:
                return False
            if f[0] == "in" and row.get(f[1]) not in f[2]:
                return False
            if f[0] == "gte" and not (str(row.get(f[1])) >= str(f[2])):
                return False
            if f[0] == "lte" and not (str(row.get(f[1])) <= str(f[2])):
                return False
            if f[0] == "or":
                ok = False
                for col, op, val in f[1]:
                    if op == "eq" and str(row.get(col)) == val:
                        ok = True
                    if op == "is" and val == "null" and row.get(col) is None:
                        ok = True
                if not ok:
                    return False
        return True

    def execute(self):
        rows = self._store.setdefault(self._t, [])
        if self._mode == "insert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = []
            for r in payload:
                r = dict(r)
                r.setdefault("id", uuid.uuid4().hex)
                r["_seq"] = self._store["_seq"]; self._store["_seq"] += 1
                rows.append(r); inserted.append(r)
            return _Result(inserted)
        if self._mode == "update":
            hit = [r for r in rows if self._match(r)]
            for r in hit:
                r.update(self._payload)
            return _Result(hit)
        # select
        out = [r for r in rows if self._match(r)]
        if self._order:
            out.sort(key=lambda r: r.get(self._order) or r.get("_seq", 0), reverse=self._desc)
        if self._limit is not None:
            out = out[: self._limit]
        return _Result(out)


class FakeSupabase:
    def __init__(self):
        self.data = {"_seq": 0}

    def table(self, name):
        return _Query(self.data, name)


# ── fixture ──────────────────────────────────────────────────────────────────
T = {"A": ("07:00:00", "15:00:00", False), "P": ("13:30:00", "21:30:00", False),
     "N": ("21:30:00", "07:00:00", True)}


def build_store(*, understaffed=False):
    fake = FakeSupabase()
    d = fake.data
    d["facilities"] = [{"id": "f1", "code": "A", "name": "Home A"}]
    d["roster_periods"] = [{"id": "p1", "facility_id": "f1", "period_start": "2026-07-01",
                            "period_end": "2026-07-02", "cycle_type": "28day"}]
    d["roster_versions"] = [{"id": "mv1", "facility_id": "f1", "period_id": "p1",
                             "version_type": "manual", "status": "draft",
                             "created_at": "2026-07-20T00:00:00"}]
    staff = [{"id": "rn1", "facility_id": "f1", "rank": "RN", "employment_type": "local_ft",
              "is_audited_for_medication": True, "contracted_hours": 44, "status": "active"},
             {"id": "cw1", "facility_id": "f1", "rank": "CW", "employment_type": "local_ft",
              "is_audited_for_medication": False, "contracted_hours": 44, "status": "active"}]
    if not understaffed:
        staff.append({"id": "cw2", "facility_id": "f1", "rank": "CW",
                      "employment_type": "local_ft", "is_audited_for_medication": False,
                      "contracted_hours": 44, "status": "active"})
    d["staff"] = staff
    d["staff_contracts"] = [{"id": f"c_{s['id']}", "facility_id": "f1", "staff_id": s["id"],
                             "weekly_hours": 44, "max_weekly_hours": 54, "min_rest_minutes": 660,
                             "allowed_shift_types": []} for s in staff]
    d["staffing_ratio_rules"] = []
    d["daily_resident_counts"] = []
    d["calendar_days"] = []
    if understaffed:   # ban agency so shortages become real coverage gaps
        d["calendar_days"] = [{"id": f"cal{i}", "facility_id": "f1",
                               "date": f"2026-07-0{i+1}", "is_agency_allowed": False,
                               "agency_cost_multiplier": 1.0} for i in range(2)]

    shifts, assigns = [], []
    plan = [("rnA", "RN", "A", "rn1"), ("cwP", "CW", "P", "cw1"), ("cwN", "CW", "N", "cw2")]
    for di in range(2):
        for base, rank, code, owner in plan:
            start, end, cross = T[code]
            sid = f"{base}{di}"
            shifts.append({"id": sid, "facility_id": "f1", "roster_version_id": "mv1",
                           "date": f"2026-07-0{di+1}", "shift_type": code,
                           "start_time": start, "end_time": end, "cross_midnight": cross,
                           "unit_id": None, "required_rank": rank, "required_count": 1,
                           "is_working": True})
            assigns.append({"id": f"a_{sid}", "facility_id": "f1", "shift_id": sid,
                            "staff_id": owner, "role": rank, "status": "assigned",
                            "is_agency": False})
    d["shifts"] = shifts
    d["shift_assignments"] = assigns
    return fake


def _versions(store, *types):
    return [v for v in store.data["roster_versions"] if v["version_type"] in types]


def _shifts_of(store, version_id):
    return [s for s in store.data["shifts"] if s["roster_version_id"] == version_id]


def test_run_optimization_persists_three_versions():
    store = build_store()
    resp = optimize.run_optimization(store, OptimizeRequest(facility_id="f1", period_id="p1"))

    assert resp.status == JobStatus.COMPLETED
    assert len(resp.roster_options) == 3

    autos = _versions(store, "A", "B", "C")
    assert {v["version_type"] for v in autos} == {"A", "B", "C"}
    for v in autos:
        assert len(_shifts_of(store, v["id"])) == 6            # every demand slot materialized
        shift_ids = {s["id"] for s in _shifts_of(store, v["id"])}
        n_assign = sum(1 for a in store.data["shift_assignments"] if a["shift_id"] in shift_ids)
        assert n_assign == 6                                   # every slot filled (staff/agency)

    assert len(store.data.get("roster_option_scores", [])) == 3
    jobs = store.data["optimization_jobs"]
    assert len(jobs) == 1 and jobs[0]["status"] == JobStatus.COMPLETED
    assert jobs[0]["result_json"]["roster_options"]


def test_persist_false_writes_nothing_but_returns_options():
    store = build_store()
    req = OptimizeRequest(facility_id="f1", period_id="p1",
                          writeback=WritebackOptions(persist=False))
    resp = optimize.run_optimization(store, req)

    assert len(resp.roster_options) == 3                       # still scored
    assert _versions(store, "A", "B", "C") == []               # nothing persisted
    assert store.data.get("roster_option_scores", []) == []
    assert store.data["optimization_jobs"][0]["status"] == JobStatus.COMPLETED


def test_understaffed_writes_violations():
    store = build_store(understaffed=True)
    resp = optimize.run_optimization(
        store, OptimizeRequest(facility_id="f1", period_id="p1", plan_mode=PlanMode.C))

    opt = resp.roster_options[0]
    assert opt.hard_violation_count >= 1
    assert opt.roster_version_id is not None                   # persisted despite gaps
    coverage = [v for v in store.data.get("violation_log", []) if v["rule_code"] == "coverage"]
    assert coverage
