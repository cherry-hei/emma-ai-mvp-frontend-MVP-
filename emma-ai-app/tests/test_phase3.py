"""Phase 3 tests — the operations layer (Approval, Alert, ROI, Reports, Staff App)
and the Pareto optimizer.

Split the same way as test_api.py:
  • Offline: pure functions (Gini, minute-level ratio evaluation, Pareto
    dominance/selection, rank substitution) and the OpenAPI surface. Always run.
  • DB-backed: real login → RLS-scoped endpoint calls against the seeded local
    Supabase. Skips cleanly when it isn't reachable.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── offline: OpenAPI surface ─────────────────────────────────────────────────
def test_openapi_documents_phase3_surface():
    paths = client.get("/openapi.json").json()["paths"]
    expected = [
        "/leave-requests", "/leave-requests/stats", "/leave-requests/{request_id}",
        "/sl-incidents", "/sl-incidents/stats", "/sl-incidents/{incident_id}/resolve",
        "/replacement-candidates", "/alerts", "/future-debt",
        "/dashboard/summary", "/roi/summary", "/roi/settings",
        "/kpi/overview", "/kpi/conflict-rate", "/kpi/an-gini", "/kpi/shift-fairness",
        "/kpi/ai-acceptance", "/kpi/external-workforce", "/kpi/staffing-ratio-compliance",
        "/compliance/minute-ratio", "/compliance/thresholds",
        "/reports", "/reports/generate", "/reports/schedules",
        "/reports/event-triggers", "/reports/regulatory-docs",
        "/me/summary", "/me/roster", "/me/tasks", "/me/profile",
        "/me/attendance", "/me/attendance/clock",
        "/staff/{staff_id}/ai-analysis", "/optimize-pareto",
    ]
    missing = [p for p in expected if p not in paths]
    assert not missing, f"missing from OpenAPI: {missing}"


# ── offline: rank substitution ───────────────────────────────────────────────
def test_rank_substitution_only_allows_equal_or_more_senior_care_ranks():
    from emma_core.constants import can_cover_rank

    assert can_cover_rank("RN", "CW")        # senior covers junior
    assert can_cover_rank("CW", "CW")        # exact match
    assert not can_cover_rank("CW", "RN")    # junior may not cover senior
    assert not can_cover_rank("PTA", "CW")   # therapy rank is not a care rank
    assert can_cover_rank("PTA", "PTA")
    assert can_cover_rank("CW", None)        # no requirement => anyone


# ── offline: Gini ────────────────────────────────────────────────────────────
def test_gini_is_zero_when_even_and_one_when_concentrated():
    from emma_core.services.kpi import gini

    assert gini([2, 2, 2, 2]) == 0.0
    assert gini([0, 0, 0, 0]) == 0.0          # nothing to share out
    assert gini([1]) == 0.0                    # undefined for n<2 → 0
    assert gini([0, 0, 0, 8]) == pytest.approx(0.75, abs=0.01)
    assert 0 < gini([1, 2, 3, 10]) < 1


# ── offline: minute-level ratio ──────────────────────────────────────────────
def _rule(rank, start, end, ratio=None, min_any=None):
    return {"staff_rank": rank, "time_window_start": start, "time_window_end": end,
            "ratio_residents_per_staff": ratio, "min_staff_any_rank": min_any}


def test_minute_ratio_counts_only_minutes_actually_covered():
    from emma_core.services.compliance import _minute_eval

    # Window 07:00–20:00 (780 min) needs 1 RN for 50 residents at 1:60.
    # The only RN works 07:00–15:00, so 15:00–20:00 (300 min) is uncovered.
    rules = [_rule("RN", "07:00", "20:00", ratio=60)]
    shifts = {"s1": {"id": "s1", "start_time": "07:00", "end_time": "15:00",
                     "shift_type": "A", "is_working": True}}
    assigns = [{"shift_id": "s1", "role": "RN", "staff_id": "u1"}]

    out = _minute_eval(rules, 50, shifts, assigns, "2026-07-01")
    assert len(out) == 1
    row = out[0]
    assert row["required"] == 1
    assert row["window_minutes"] == 780
    assert row["breach_minutes"] == 300
    assert row["passes"] is False
    assert row["min_actual"] == 0


def test_minute_ratio_passes_when_window_fully_covered():
    from emma_core.services.compliance import _minute_eval

    rules = [_rule("RN", "07:00", "15:00", ratio=60)]
    shifts = {"s1": {"id": "s1", "start_time": "07:00", "end_time": "15:00",
                     "shift_type": "A", "is_working": True}}
    assigns = [{"shift_id": "s1", "role": "RN", "staff_id": "u1"}]

    row = _minute_eval(rules, 50, shifts, assigns, "2026-07-01")[0]
    assert row["breach_minutes"] == 0 and row["passes"] is True


def test_minute_ratio_handles_cross_midnight_window():
    from emma_core.services.compliance import _minute_eval

    # 18:00–07:00 needs >=2 of any rank. One night shift 21:30–07:00 covers
    # 21:30–24:00 and 00:00–07:00 with only 1 person => every minute is short.
    rules = [_rule(None, "18:00", "07:00", min_any=2)]
    shifts = {"s1": {"id": "s1", "start_time": "21:30", "end_time": "07:00",
                     "shift_type": "N", "is_working": True}}
    assigns = [{"shift_id": "s1", "role": "PCW", "staff_id": "u1"}]

    row = _minute_eval(rules, 50, shifts, assigns, "2026-07-01")[0]
    assert row["window_minutes"] == 780          # 18:00→24:00 (360) + 00:00→07:00 (420)
    assert row["breach_minutes"] == 780
    assert row["passes"] is False


# ── offline: Pareto ──────────────────────────────────────────────────────────
class _FakePoint:
    """Minimal stand-in with the .objectives/.vector contract non_dominated needs."""

    def __init__(self, **objectives):
        from emma_core.solver.pareto import AXES
        self.objectives = {a: objectives.get(a, 0) for a in AXES}
        self.result = None
        self._axes = AXES

    @property
    def vector(self):
        return tuple(self.objectives[a] for a in self._axes)


def test_pareto_drops_dominated_points():
    from emma_core.solver.pareto import non_dominated

    best = _FakePoint(agency=1, ot=1, future_debt=1, unmet=1, fairness=1)
    worse = _FakePoint(agency=5, ot=5, future_debt=5, unmet=5, fairness=5)
    tradeoff = _FakePoint(agency=0, ot=9, future_debt=1, unmet=1, fairness=1)

    keep = non_dominated([best, worse, tradeoff])
    assert best in keep and tradeoff in keep
    assert worse not in keep


def test_pareto_collapses_duplicate_coordinates():
    from emma_core.solver.pareto import non_dominated

    a = _FakePoint(agency=2, ot=2, future_debt=2, unmet=2, fairness=2)
    b = _FakePoint(agency=2, ot=2, future_debt=2, unmet=2, fairness=2)
    assert len(non_dominated([a, b])) == 1


def test_pareto_picks_cost_satisfaction_and_knee():
    from emma_core.constants import PlanMode
    from emma_core.solver.pareto import select_representatives

    cheap = _FakePoint(agency=0, ot=0, future_debt=5, unmet=10, fairness=10)
    happy = _FakePoint(agency=10, ot=10, future_debt=5, unmet=0, fairness=0)
    middle = _FakePoint(agency=4, ot=4, future_debt=4, unmet=4, fairness=4)

    chosen = select_representatives([cheap, happy, middle])
    assert chosen[PlanMode.A] is cheap        # cost extreme
    assert chosen[PlanMode.B] is happy        # satisfaction extreme
    assert chosen[PlanMode.C] is middle       # knee


def test_weight_grid_is_deterministic_and_spans_both_corners():
    from emma_core.solver.pareto import weight_grid

    grid, again = weight_grid(), weight_grid()
    assert grid == again
    assert len(grid) == 15
    assert grid[0].agency > grid[-1].agency          # cost emphasis falls away
    assert grid[0].unmet_request < grid[-1].unmet_request   # request emphasis rises


# ── offline: ROI arithmetic (service math, no DB) ────────────────────────────
def test_emma_tier_lookup_walks_the_bands():
    from emma_core.constants import tier_for

    assert tier_for(49)["tier"] == 1
    assert tier_for(500)["tier"] == 1
    assert tier_for(501)["tier"] == 2
    assert tier_for(5000)["tier"] == 4       # above the top band clamps to Tier 4


# ── DB-backed ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def token():
    from emma_core.services.auth import sign_in
    try:
        _, session = sign_in("super_a@emma.local", "EmmaDev123!")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"local Supabase not reachable/seeded: {exc}")
    return session.access_token


@pytest.fixture(scope="module")
def staff_token():
    from emma_core.services.auth import sign_in
    try:
        _, session = sign_in("staff_a@emma.local", "EmmaDev123!")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"local Supabase not reachable/seeded: {exc}")
    return session.access_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_summary_is_populated(token):
    r = client.get("/dashboard/summary", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["facility"]["code"] == "A"
    assert body["total_staff"] > 0
    assert body["kpis"]["incidents_month"] > 0
    assert len(body["highlights"]) == 3
    assert body["shift_distribution"], "today should have a rostered shift mix"


def test_leave_requests_split_by_group_and_category(token):
    pending = client.get("/leave-requests", params={"group": "pending"},
                         headers=_auth(token)).json()
    approved = client.get("/leave-requests", params={"group": "approved"},
                          headers=_auth(token)).json()
    assert pending and approved
    assert all(r["status"] in ("pending", "reviewed") for r in pending)
    assert all(r["status"] in ("approved", "rejected") for r in approved)

    sick = client.get("/leave-requests", params={"category": "sick"},
                      headers=_auth(token)).json()
    assert sick and all(r["category"] == "sick" for r in sick)

    stats = client.get("/leave-requests/stats", headers=_auth(token)).json()
    assert 0 <= stats["approval_rate"] <= 100


def test_leave_decision_round_trip(token):
    # Decide a request this test created rather than one from the seed — there is
    # no API to put a row back to 'pending', so mutating seeded data would leave
    # the demo drifted after every run.
    staff = client.get("/staff", headers=_auth(token)).json()[0]
    created = client.post("/leave-requests", headers=_auth(token), json={
        "staff_id": staff["id"], "leave_type": "AL",
        "date_start": "2026-09-01", "date_end": "2026-09-02", "reason": "pytest",
    })
    assert created.status_code == 201
    request_id = created.json()["id"]

    listed = client.get("/leave-requests", params={"group": "pending"},
                        headers=_auth(token)).json()
    assert any(r["id"] == request_id for r in listed)

    reviewed = client.patch(f"/leave-requests/{request_id}", json={"decision": "review"},
                            headers=_auth(token))
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "reviewed"

    approved = client.patch(f"/leave-requests/{request_id}",
                            json={"decision": "approve", "note": "pytest"},
                            headers=_auth(token))
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_at"]

    # it has left the pending queue and joined the decided one
    still_pending = client.get("/leave-requests", params={"group": "pending"},
                               headers=_auth(token)).json()
    assert not any(r["id"] == request_id for r in still_pending)


def test_replacement_candidates_are_compliance_filtered(token):
    incidents = client.get("/sl-incidents", params={"status": "open"},
                           headers=_auth(token)).json()
    if not incidents:
        pytest.skip("no open incident in the seed")
    incident_id = incidents[0]["id"]

    clean = client.get("/replacement-candidates",
                       params={"incident_id": incident_id, "refresh": True},
                       headers=_auth(token)).json()
    everyone = client.get("/replacement-candidates",
                          params={"incident_id": incident_id,
                                  "compliance_checked": False, "limit": 50},
                          headers=_auth(token)).json()

    assert all(c["compliance_ok"] for c in clean)
    assert len(everyone) >= len(clean)
    # a blocked candidate must say why — a silent exclusion is not auditable
    for c in everyone:
        if not c["compliance_ok"]:
            assert c["blocked_reasons"]


def test_incident_stats_and_alerts(token):
    stats = client.get("/sl-incidents/stats", headers=_auth(token)).json()
    assert stats["total"] >= stats["resolved"]
    assert stats["avg_response_minutes"] > 0
    assert sum(d["count"] for d in stats["distribution"]) == stats["total"]

    alerts = client.get("/alerts", headers=_auth(token)).json()
    assert isinstance(alerts, list)
    assert all({"id", "kind", "urgent", "title"} <= set(a) for a in alerts)


def test_roi_summary_uses_measured_inputs(token):
    body = client.get("/roi/summary", headers=_auth(token)).json()
    assert body["staff"]["total"] > 0
    assert body["a2"]["incidents"] > 0                    # counted, not configured
    assert body["agency"]["monthly_cost"] > 0             # from agency_assignments
    assert body["a1"]["saving"] == round(
        body["a1"]["hours_saved"] * body["a1"]["hourly_rate"])
    assert body["totals"]["monthly_saving"] == (
        body["totals"]["admin_saving"] + body["agency"]["saving"])
    assert body["emma"]["annual_fee"] == (
        body["staff"]["total"] * body["emma"]["rate_per_user"] * 12)


def test_roi_settings_are_persisted(token):
    original = client.get("/roi/settings", headers=_auth(token)).json()
    try:
        r = client.put("/roi/settings", json={"agency_reduction_pct": 8},
                       headers=_auth(token))
        assert r.status_code == 200
        summary = client.get("/roi/summary", headers=_auth(token)).json()
        assert summary["agency"]["reduction_pct"] == 8
        assert summary["agency"]["saving"] == round(
            summary["agency"]["monthly_cost"] * 8 / 100)
    finally:
        client.put("/roi/settings",
                   json={"agency_reduction_pct": float(original["agency_reduction_pct"])},
                   headers=_auth(token))


def test_kpi_overview_covers_every_metric(token):
    body = client.get("/kpi/overview", headers=_auth(token)).json()
    assert set(body) == {
        "conflict_rate", "an_gini", "shift_fairness", "ai_acceptance",
        "external_workforce", "staffing_ratio_compliance",
    }
    ratio = body["staffing_ratio_compliance"]
    assert ratio["checks"] > 0
    assert 0 <= ratio["pass_rate_pct"] <= 100
    assert body["shift_fairness"]["by_shift_type"]


def test_minute_ratio_endpoint_reports_breach_minutes(token):
    periods = client.get("/roster-periods", headers=_auth(token)).json()
    day = periods[0]["period_start"]
    rows = client.get("/compliance/minute-ratio", params={"date": day},
                      headers=_auth(token)).json()
    assert rows
    for row in rows:
        assert row["breach_minutes"] <= row["window_minutes"]
        assert row["passes"] == (row["breach_minutes"] == 0)


def test_threshold_monitors_are_measured(token):
    monitors = client.get("/compliance/thresholds", headers=_auth(token)).json()
    codes = {m["code"] for m in monitors}
    assert {"CERT_EXPIRY", "PT_RATIO", "AN_LIMIT", "RN_ABSENT",
            "CL_ACCRUAL", "OCCUPANCY"} <= codes
    for m in monitors:
        assert m["severity"] in ("ok", "warn", "over")
        assert m["note_en"] and m["note_zh"]


def test_report_generation_persists_rows(token):
    r = client.post("/reports/generate", json={"report_type": "roster_hours"},
                    headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] > 0
    assert body["payload"]["columns"] and body["payload"]["rows"]

    listed = client.get("/reports", headers=_auth(token)).json()
    assert any(x["id"] == body["id"] for x in listed)

    csv = client.get("/reports/download/roster_hours.csv", headers=_auth(token))
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "Total hours" in csv.text


def test_report_registry_reads(token):
    schedules = client.get("/reports/schedules", headers=_auth(token)).json()
    assert schedules and all(s["report_type"] for s in schedules)

    triggers = client.get("/reports/event-triggers", headers=_auth(token)).json()
    assert triggers and all("recent_count" in t for t in triggers)

    docs = client.get("/reports/regulatory-docs", headers=_auth(token)).json()
    assert docs and all(d["doc_code"] for d in docs)


def test_staff_ai_analysis_is_evidence_backed(token):
    staff = client.get("/staff", headers=_auth(token)).json()
    rn = next(s for s in staff if s["rank"] == "RN")
    body = client.get(f'/staff/{rn["id"]}/ai-analysis', headers=_auth(token)).json()

    assert body["staff"]["rank"] == "RN"
    assert body["activity"]["working_shifts"] > 0
    assert body["explicit_skills"], "seeded RN has certificates"
    assert body["implicit_skills"], "seeded RN has rostered task labels"
    for bar in body["skill_bars"]:
        assert 0 <= bar["explicit"] <= 100 and 0 <= bar["implicit"] <= 100


# ── staff app: self-scope ────────────────────────────────────────────────────
def test_staff_app_summary_is_own_record(staff_token):
    body = client.get("/me/summary", headers=_auth(staff_token)).json()
    assert body["staff"]["rank"] == "RN"
    assert body["hours"]["contracted_hours"] > 0
    assert isinstance(body["tasks"], list)


def test_staff_app_roster_window(staff_token, token):
    body = client.get("/me/roster", params={"days": 7}, headers=_auth(staff_token)).json()
    assert len(body["days"]) == 7

    period = client.get("/roster-periods", headers=_auth(token)).json()[0]
    # the window is clamped into the period rather than running off its end
    assert body["start"] >= period["period_start"]
    assert body["end"] <= period["period_end"]
    if period["period_start"] <= date.today().isoformat() <= period["period_end"]:
        assert body["start"] <= date.today().isoformat() <= body["end"]
    assert any(d["is_working"] for d in body["days"])


def test_staff_cannot_decide_leave_requests(staff_token):
    requests = client.get("/leave-requests", headers=_auth(staff_token)).json()
    if not requests:
        pytest.skip("staff account has no leave requests")
    r = client.patch(f'/leave-requests/{requests[0]["id"]}',
                     json={"decision": "approve"}, headers=_auth(staff_token))
    assert r.status_code == 403


def test_staff_only_sees_own_leave_requests(staff_token, token):
    mine = client.get("/leave-requests", headers=_auth(staff_token)).json()
    all_rows = client.get("/leave-requests", headers=_auth(token)).json()
    assert len(mine) < len(all_rows), "RLS must scope a staff login to its own rows"
    staff_ids = {r["staff_id"] for r in mine}
    assert len(staff_ids) <= 1


def test_task_completion_round_trip(staff_token):
    # The staff member may be off duty today, so drive the round trip from a day
    # they are actually rostered with tasks rather than skipping.
    roster = client.get("/me/roster", params={"days": 28},
                        headers=_auth(staff_token)).json()
    day = next((d["date"] for d in roster["days"] if d["is_working"] and d["tasks"]), None)
    assert day, "the seeded staff member should have rostered tasks in the period"

    tasks = client.get("/me/tasks", params={"date": day}, headers=_auth(staff_token)).json()
    assert tasks, f"expected materialised task rows for {day}"
    task = tasks[0]
    original = task["status"]

    r = client.patch(f'/me/tasks/{task["id"]}', json={"status": "done"},
                     headers=_auth(staff_token))
    assert r.status_code == 200 and r.json()["task_status"] == "done"

    client.patch(f'/me/tasks/{task["id"]}', json={"status": original},
                 headers=_auth(staff_token))


def test_attendance_reports_paired_hours(staff_token):
    body = client.get("/me/attendance", headers=_auth(staff_token)).json()
    assert body["month"]["worked_hours"] > 0
    assert body["month"]["days_worked"] > 0
    # the seed leaves the staff member clocked in with no matching clock-out today,
    # so today's paired total must stay at zero rather than guessing an end time
    assert body["today"]["clocked_in"] is True
    assert body["today"]["worked_minutes_today"] == 0
