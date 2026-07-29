"""Phase 4 against a real database — the rules as the product actually runs them.

tests/test_phase4.py covers the pure evaluators with hand-built dictionaries.
That proves the algebra and nothing about the wiring: it cannot catch a missing
migration, a column the service selects but the schema lacks, or an RLS policy
that hides a rule table from the very user meant to read it. Every check here
goes through a real login, a real HTTP call and real seeded rows, and cleans up
whatever it created.

Needs the seeded Supabase project (`scripts/seed.py`, or `backfill_phase4.py` on
an environment seeded before Phase 4). Skips cleanly when it is not reachable.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)

PASSWORD = "EmmaDev123!"
# Far enough out that it cannot collide with a seeded event.
EVENT_DATE = "2026-07-21"


def _token(email: str) -> str:
    from emma_core.services.auth import sign_in
    try:
        _, session = sign_in(email, PASSWORD)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Supabase not reachable/seeded: {exc}")
    return session.access_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def token() -> str:
    return _token("super_a@emma.local")


@pytest.fixture(scope="module")
def token_b() -> str:
    return _token("super_b@emma.local")


@pytest.fixture(scope="module")
def home_a(token) -> dict:
    """Home A's manual roster, indexed by (rank, shift code) for cell lookup."""
    h = _auth(token)
    period = client.get("/roster-periods", headers=h).json()[0]
    versions = client.get("/roster-versions", params={"period_id": period["id"]},
                          headers=h).json()
    manual = next(v for v in versions if v["version_type"] == "manual")
    grid = client.get(f"/rosters/{period['id']}",
                      params={"version_id": manual["id"]}, headers=h).json()
    cells: dict[tuple[str, str], dict] = {}
    for row in grid["rows"]:
        for cell in row["cells"]:
            if cell.get("assignment_id"):
                cells.setdefault(
                    (row["staff"]["rank"], cell["shift_type"]),
                    {"assignment_id": cell["assignment_id"], "date": cell["date"],
                     "staff_id": row["staff"]["id"], "tasks": cell.get("tasks", [])})
    tasks = {t["task_code"]: t for t in client.get("/task-definitions", headers=h).json()}
    return {"period": period, "version": manual, "cells": cells,
            "tasks": tasks, "grid": grid}


def _reasons(response) -> set[str]:
    detail = response.json().get("detail", {})
    out = set()
    for issue in detail.get("issues") or []:
        if issue.get("reason"):
            out.add(issue["reason"])
        for nested in issue.get("issues") or []:
            if nested.get("reason"):
                out.add(nested["reason"])
    return out


def _rank_task(home_a: dict, rank: str, shift: str) -> tuple[dict, dict]:
    """A cell for `rank` on `shift`, plus a task code that rank owns."""
    cell = home_a["cells"].get((rank, shift))
    if not cell:
        pytest.skip(f"seed has no {rank} cell on a {shift} shift")
    task = next((t for t in home_a["tasks"].values()
                 if t["required_rank"] == rank and t["shift_type"] in (None, shift)), None)
    if not task:
        pytest.skip(f"seed has no task code for {rank} on {shift}")
    return cell, task


# ── 4.1 task codes and eligibility ──────────────────────────────────────────
def test_phase4_rule_tables_are_reachable_over_http(token):
    """The migration is applied and RLS lets the facility's own user read it."""
    h = _auth(token)
    for path in ("/staff-qualifications", "/floor-rules", "/facility-events",
                 "/task-assignments"):
        r = client.get(path, headers=h)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
        assert isinstance(r.json(), list)


def test_eligible_task_is_accepted_and_syncs_the_roster_cell(token, home_a):
    h = _auth(token)
    cell, task = _rank_task(home_a, "HW", "A")
    created = client.post("/task-assignments", headers=h, json={
        "shift_assignment_id": cell["assignment_id"], "task_id": task["id"]})
    assert created.status_code == 201, created.text
    body = created.json()
    try:
        assert body["roster_version_id"] == home_a["version"]["id"]
        listed = client.get("/task-assignments", headers=h,
                            params={"roster_version_id": home_a["version"]["id"]}).json()
        assert any(row["id"] == body["id"] for row in listed)

        grid = client.get(f"/rosters/{home_a['period']['id']}", headers=h,
                          params={"version_id": home_a["version"]["id"]}).json()
        row = next(r for r in grid["rows"] if r["staff"]["id"] == cell["staff_id"])
        now = next(c for c in row["cells"] if c["date"] == cell["date"])
        assert body["task_label"] in now["tasks"]
    finally:
        client.delete(f"/task-assignments/{body['id']}", headers=h)

    grid = client.get(f"/rosters/{home_a['period']['id']}", headers=h,
                      params={"version_id": home_a["version"]["id"]}).json()
    row = next(r for r in grid["rows"] if r["staff"]["id"] == cell["staff_id"])
    restored = next(c for c in row["cells"] if c["date"] == cell["date"])
    assert sorted(restored["tasks"]) == sorted(cell["tasks"]), "delete must undo the label"


def test_rejection_names_every_reason_and_is_recorded(token, home_a):
    """A refusal has to be actionable: each reason separately, and audited."""
    h = _auth(token)
    cw_cell = home_a["cells"].get(("CW", "A"))
    audited_task = next((t for t in home_a["tasks"].values()
                         if t["requires_audit"] and t["required_rank"] == "HW"), None)
    if not cw_cell or not audited_task:
        pytest.skip("seed lacks a CW morning cell or an audited HW task code")

    from emma_core.db import get_service_client

    sb = get_service_client()
    facility_id = client.get("/auth/me", headers=h).json()["facility_id"]
    logged = lambda: len(sb.table("violation_log").select("id")  # noqa: E731
                         .eq("facility_id", facility_id)
                         .eq("rule_code", "task_eligibility").execute().data)
    before = logged()

    r = client.post("/task-assignments", headers=h, json={
        "shift_assignment_id": cw_cell["assignment_id"], "task_id": audited_task["id"]})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "task_not_eligible"
    assert {"rank", "medication_audit"} <= _reasons(r), detail
    assert detail["task_code"] == audited_task["task_code"]

    # A refused attempt is evidence, so it has to survive the refusal.
    assert logged() == before + 1
    newest = (sb.table("violation_log")
              .select("details_json,rule_code,shift_id")
              .eq("facility_id", facility_id).eq("rule_code", "task_eligibility")
              .order("created_at", desc=True).limit(1).execute().data[0])
    assert {i["reason"] for i in newest["details_json"]["issues"]} >= {"rank", "medication_audit"}
    assert newest["details_json"]["shift_assignment_id"] == cw_cell["assignment_id"]


def test_task_code_must_match_the_rostered_shift_over_http(token, home_a):
    h = _auth(token)
    # Any cell whose rank owns a code scoped to a *different* shift will do —
    # which rank that is depends on the facility's own dictionary.
    pair = next((
        (cell, task)
        for (rank, shift), cell in home_a["cells"].items()
        for task in home_a["tasks"].values()
        if task["required_rank"] == rank and task["shift_type"]
        and task["shift_type"] != shift and shift in ("A", "P")), None)
    if not pair:
        pytest.skip("no cell in this seed carries a code from another shift")
    cell, task = pair
    r = client.post("/task-assignments", headers=h, json={
        "shift_assignment_id": cell["assignment_id"], "task_id": task["id"]})
    assert r.status_code == 422, r.text
    assert "shift_type" in _reasons(r)


def test_split_shift_carries_the_duty_of_both_its_windows(token, home_a):
    """A/N is two duty windows, so a morning code belongs on it (see shifttime)."""
    h = _auth(token)
    an_cell = home_a["cells"].get(("HW", "AN"))
    morning = next((t for t in home_a["tasks"].values()
                    if t["shift_type"] == "A" and t["required_rank"] == "HW"), None)
    if not an_cell or not morning:
        pytest.skip("seed lacks an HW A/N cell or a morning HW code")
    created = client.post("/task-assignments", headers=h, json={
        "shift_assignment_id": an_cell["assignment_id"], "task_id": morning["id"]})
    assert created.status_code == 201, (
        f"a morning code must be assignable on the A/N split shift: {created.text}")
    client.delete(f"/task-assignments/{created.json()['id']}", headers=h)


# ── 4.1 qualifications CRUD ─────────────────────────────────────────────────
def test_granting_the_audit_qualification_retires_that_reason(token, home_a):
    """The audit gate is data, not a hard-coded rank list.

    Isolate it: keep everything else about the attempt identical and grant only
    `medication_audited`. The medication_audit reason must disappear from the
    rejection while the unrelated rank reason stays — proving the qualification
    row, and nothing else, is what moved.
    """
    h = _auth(token)
    cw_cell = home_a["cells"].get(("CW", "A"))
    audited = next((t for t in home_a["tasks"].values()
                    if t["requires_audit"] and t["required_rank"] == "HW"), None)
    if not cw_cell or not audited:
        pytest.skip("seed lacks a CW morning cell or an audited HW code")
    body = {"shift_assignment_id": cw_cell["assignment_id"], "task_id": audited["id"]}

    before = client.post("/task-assignments", headers=h, json=body)
    assert before.status_code == 422
    assert {"rank", "medication_audit"} <= _reasons(before)

    granted = client.post("/staff-qualifications", headers=h, json={
        "staff_id": cw_cell["staff_id"], "qualification_type": "medication_audited",
        "effective_from": "2026-01-01"})
    assert granted.status_code == 201, granted.text
    try:
        after = client.post("/task-assignments", headers=h, json=body)
        assert after.status_code == 422
        reasons = _reasons(after)
        assert "medication_audit" not in reasons, "the grant must retire the audit block"
        assert "rank" in reasons, "the unrelated rank block must survive"
    finally:
        client.delete(f"/staff-qualifications/{granted.json()['id']}", headers=h)

    restored = client.post("/task-assignments", headers=h, json=body)
    assert "medication_audit" in _reasons(restored), "revoking must restore the block"


def test_qualification_crud_round_trip(token, home_a):
    h = _auth(token)
    staff_id = next(iter(home_a["cells"].values()))["staff_id"]
    created = client.post("/staff-qualifications", headers=h, json={
        "staff_id": staff_id, "qualification_type": "Manual Handling",
        "effective_from": "2026-01-01", "notes": "live test"})
    assert created.status_code == 201, created.text
    row = created.json()
    try:
        # Stored normalised, so eligibility set membership is exact.
        assert row["qualification_type"] == "manual_handling"
        listed = client.get("/staff-qualifications", headers=h,
                            params={"staff_id": staff_id}).json()
        assert any(q["id"] == row["id"] for q in listed)

        patched = client.patch(f"/staff-qualifications/{row['id']}", headers=h,
                               json={"is_active": False})
        assert patched.status_code == 200 and patched.json()["is_active"] is False

        bad = client.post("/staff-qualifications", headers=h, json={
            "staff_id": staff_id, "qualification_type": "x",
            "effective_from": "2026-06-01", "expiry_date": "2026-01-01"})
        assert bad.status_code == 422, "expiry before start must be rejected"
    finally:
        client.delete(f"/staff-qualifications/{row['id']}", headers=h)
    assert not [q for q in client.get("/staff-qualifications", headers=h).json()
                if q["id"] == row["id"]]


# ── 4.2 event staffing overlays ─────────────────────────────────────────────
@pytest.mark.parametrize("event_type,expect", [
    ("hair cut", lambda r: len(r) == 1 and r[0]["rank"] == "CW|HCA" and r[0]["is_additive"]),
    ("CGAT", lambda r: {x["rank"] for x in r} == {"RN", "HW"} and all(x["is_additive"] for x in r)),
    ("podiatry", lambda r: len(r) == 2 and not any(x["is_additive"] for x in r)),
    ("visiting", lambda r: r == []),
])
def test_event_templates_apply_on_create(token, event_type, expect):
    h = _auth(token)
    created = client.post("/facility-events", headers=h, json={
        "event_type": event_type, "event_date": EVENT_DATE,
        "title": f"live test {event_type}"})
    assert created.status_code == 201, created.text
    body = created.json()
    try:
        assert expect(body["staffing_requirements"]), body["staffing_requirements"]
    finally:
        client.delete(f"/facility-events/{body['id']}", headers=h)


def test_manager_entered_event_requirement_is_stored_verbatim(token):
    h = _auth(token)
    created = client.post("/facility-events", headers=h, json={
        "event_type": "visiting", "event_date": EVENT_DATE, "title": "live test visiting",
        "staffing_requirements": [{"rank": "HW", "count": 2, "is_additive": True,
                                   "notes": "escort"}]})
    assert created.status_code == 201, created.text
    body = created.json()
    try:
        reqs = body["staffing_requirements"]
        assert len(reqs) == 1
        assert (reqs[0]["rank"], reqs[0]["count"], reqs[0]["notes"]) == ("HW", 2, "escort")
    finally:
        client.delete(f"/facility-events/{body['id']}", headers=h)


def test_event_marker_reaches_the_roster_header_and_validation(token, home_a):
    h = _auth(token)
    created = client.post("/facility-events", headers=h, json={
        "event_type": "CGAT", "event_date": EVENT_DATE, "title": "live test CGAT",
        "start_at": f"{EVENT_DATE}T09:00:00+00:00", "end_at": f"{EVENT_DATE}T12:00:00+00:00"})
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    try:
        grid = client.get(f"/rosters/{home_a['period']['id']}", headers=h,
                          params={"version_id": home_a["version"]["id"]}).json()
        assert any(e["id"] == event_id for e in grid["events"]), \
            "the roster date header feeds off /rosters, so the event must appear there"

        result = client.post("/validate-roster", headers=h,
                             json={"roster_version_id": home_a["version"]["id"]}).json()
        ours = [v for v in result["violations"]
                if v["rule_code"] == "event_staffing" and v["event_id"] == event_id]
        assert ours, "additive event demand nobody covers must raise a violation"
        assert all(v["severity"] == "hard" for v in ours)
    finally:
        client.delete(f"/facility-events/{event_id}", headers=h)

    after = client.post("/validate-roster", headers=h,
                        json={"roster_version_id": home_a["version"]["id"]}).json()
    assert not [v for v in after["violations"] if v["event_id"] == event_id], \
        "deleting the event must retire its violations"


# ── 4.3 floor coverage ──────────────────────────────────────────────────────
def test_floor_rule_crud_and_condition_validation(token_b):
    h = _auth(token_b)
    unit = client.get("/units", headers=h).json()[0]
    created = client.post("/floor-rules", headers=h, json={
        "unit_id": unit["id"], "floor": "TEST", "time_window_start": "07:00",
        "time_window_end": "17:00", "rank": "HCA", "min_count": 2,
        "condition_json": {"weekdays": [0, 1, 2, 3, 4], "required_shift_types": ["7A"]}})
    assert created.status_code == 201, created.text
    rule = created.json()
    try:
        assert any(r["id"] == rule["id"] for r in client.get("/floor-rules", headers=h).json())
        patched = client.patch(f"/floor-rules/{rule['id']}", headers=h,
                               json={"min_count": 1})
        assert patched.status_code == 200 and patched.json()["min_count"] == 1

        # A silently-ignored typo would leave a floor looking protected when it
        # is not, so an unknown condition key has to be refused.
        bad = client.post("/floor-rules", headers=h, json={
            "unit_id": unit["id"], "time_window_start": "07:00",
            "time_window_end": "17:00", "rank": "HCA", "min_count": 1,
            "condition_json": {"weekdayz": [0]}})
        assert bad.status_code == 422 and "weekdayz" in bad.json()["detail"]["message"]

        bad_time = client.post("/floor-rules", headers=h, json={
            "unit_id": unit["id"], "time_window_start": "25:00",
            "time_window_end": "17:00", "rank": "HCA", "min_count": 1})
        assert bad_time.status_code == 422
    finally:
        client.delete(f"/floor-rules/{rule['id']}", headers=h)
    assert not [r for r in client.get("/floor-rules", headers=h).json()
                if r["id"] == rule["id"]]


def test_floor_shortfall_is_reported_with_minute_level_evidence(token_b):
    h = _auth(token_b)
    period = client.get("/roster-periods", headers=h).json()[0]
    manual = next(v for v in client.get("/roster-versions", headers=h,
                                        params={"period_id": period["id"]}).json()
                  if v["version_type"] == "manual")
    result = client.post("/validate-roster", headers=h,
                         json={"roster_version_id": manual["id"]}).json()
    floor = [v for v in result["violations"] if v["rule_code"] == "floor_coverage"]
    if not floor:
        pytest.skip("this facility's roster meets every configured floor rule")
    sample = floor[0]
    assert sample["unit_id"], "a floor breach must name the unit"
    assert sample["date"], "a floor breach must name the day"
    assert sample["details"]["required"] > sample["details"]["actual"] >= 0
    assert sample["details"]["rule_id"], "the breach must point back at its rule"


def test_weekend_relaxation_lowers_the_requirement(token_b):
    """The 6/F weekend rule is a different row, not a special case in code."""
    h = _auth(token_b)
    rules = client.get("/floor-rules", headers=h, params={"active_only": True}).json()
    weekday = [r for r in rules
               if set(r["condition_json"].get("weekdays") or []) == {0, 1, 2, 3, 4}]
    weekend = [r for r in rules
               if set(r["condition_json"].get("weekdays") or []) == {5, 6}]
    if not weekday or not weekend:
        pytest.skip("facility has no weekday/weekend split floor rule")
    pairs = [(w, e) for w in weekday for e in weekend
             if w["unit_id"] == e["unit_id"] and w["rank"] == e["rank"]
             and w["time_window_start"] == e["time_window_start"]]
    assert pairs, "expected a weekday/weekend pair on the same window"
    assert any(e["min_count"] < w["min_count"] for w, e in pairs)


def test_composition_rule_is_data_driven(token_b):
    """2/F's 16:00-21:30 local-P requirement only bites on a given 7A mix."""
    h = _auth(token_b)
    rules = client.get("/floor-rules", headers=h).json()
    composed = [r for r in rules if r["condition_json"].get("when_7a_composition")]
    if not composed:
        pytest.skip("facility has no composition-conditioned floor rule")
    rule = composed[0]
    assert rule["condition_json"]["required_shift_types"], \
        "the rule must say which shift satisfies it"
    assert rule["condition_json"].get("employment_types"), \
        "the local-staff requirement is the point of the rule"


# ── the publish gate ────────────────────────────────────────────────────────
def test_publish_is_guarded_by_the_operational_rules(token, home_a):
    """An unmet event requirement must stop a publish, and stop stopping it."""
    h = _auth(token)
    version_id = home_a["version"]["id"]
    baseline = client.post("/validate-roster", headers=h,
                           json={"roster_version_id": version_id}).json()
    if baseline["violations"]:
        pytest.skip("roster already has operational violations; gate covered elsewhere")

    blocker = client.post("/facility-events", headers=h, json={
        "event_type": "CGAT", "event_date": EVENT_DATE, "title": "live test gate"})
    assert blocker.status_code == 201, blocker.text
    try:
        blocked = client.post(f"/rosters/{version_id}/publish", headers=h)
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["detail"]["code"] == "not_publishable"
    finally:
        client.delete(f"/facility-events/{blocker.json()['id']}", headers=h)

    cleared = client.post("/validate-roster", headers=h,
                          json={"roster_version_id": version_id}).json()
    assert not cleared["violations"], "removing the cause must clear the block"


# ── tenancy ─────────────────────────────────────────────────────────────────
def test_phase4_writes_cannot_cross_the_facility_boundary(token, token_b):
    """Home B's rule ids must be invisible and unwritable from Home A."""
    b_units = client.get("/units", headers=_auth(token_b)).json()
    created = client.post("/floor-rules", headers=_auth(token_b), json={
        "unit_id": b_units[0]["id"], "time_window_start": "07:00",
        "time_window_end": "08:00", "rank": "HCA", "min_count": 1})
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    try:
        a_rules = client.get("/floor-rules", headers=_auth(token)).json()
        assert not [r for r in a_rules if r["id"] == rule_id], "RLS leak on read"

        stolen = client.patch(f"/floor-rules/{rule_id}", headers=_auth(token),
                              json={"min_count": 99})
        assert stolen.status_code >= 400, "Home A must not edit Home B's rule"

        client.delete(f"/floor-rules/{rule_id}", headers=_auth(token))
        still = client.get("/floor-rules", headers=_auth(token_b)).json()
        assert [r for r in still if r["id"] == rule_id], \
            "Home A's delete must not reach Home B's row"
    finally:
        client.delete(f"/floor-rules/{rule_id}", headers=_auth(token_b))


def test_cross_facility_task_assignment_is_refused(token, token_b):
    h_b = _auth(token_b)
    period = client.get("/roster-periods", headers=h_b).json()[0]
    manual = next(v for v in client.get("/roster-versions", headers=h_b,
                                        params={"period_id": period["id"]}).json()
                  if v["version_type"] == "manual")
    grid = client.get(f"/rosters/{period['id']}", headers=h_b,
                      params={"version_id": manual["id"]}).json()
    b_assignment = next(c["assignment_id"] for row in grid["rows"]
                        for c in row["cells"] if c.get("assignment_id"))
    a_task = client.get("/task-definitions", headers=_auth(token)).json()[0]

    r = client.post("/task-assignments", headers=_auth(token), json={
        "shift_assignment_id": b_assignment, "task_id": a_task["id"]})
    assert r.status_code >= 400, "Home A must not attach a task to Home B's shift"


# ── roles ───────────────────────────────────────────────────────────────────
def test_scheduling_writes_require_a_write_role():
    token = _token("staff_a@emma.local")
    for path, body in (("/facility-events", {"event_type": "visiting",
                                             "event_date": EVENT_DATE}),
                       ("/floor-rules", {"floor": "1F", "time_window_start": "07:00",
                                         "time_window_end": "08:00", "rank": "HCA",
                                         "min_count": 1}),
                       ("/staff-qualifications", {"staff_id": "00000000-0000-0000-0000-000000000000",
                                                  "qualification_type": "mentor"})):
        r = client.post(path, headers=_auth(token), json=body)
        assert r.status_code == 403, f"{path} -> {r.status_code} {r.text[:160]}"


def test_no_test_residue_is_left_behind(token):
    """Whatever the run created above must be gone by the time it ends."""
    h = _auth(token)
    events = client.get("/facility-events", headers=h,
                        params={"date_from": EVENT_DATE, "date_to": EVENT_DATE}).json()
    assert not [e for e in events if (e.get("title") or "").startswith("live test")]
    assert not [q for q in client.get("/staff-qualifications", headers=h).json()
                if q["qualification_type"] == "manual_handling"]
    tomorrow = (date.fromisoformat(EVENT_DATE) + timedelta(days=1)).isoformat()
    assert client.get("/facility-events", headers=h,
                      params={"date_from": EVENT_DATE, "date_to": tomorrow}).status_code == 200
