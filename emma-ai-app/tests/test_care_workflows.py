"""Offline authority and HTTP boundary tests; no live accounts or database."""
from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.deps import AuthCtx, get_ctx
from api.main import app
from api.routers import auth as auth_api, roster, scheduling, leave
from api.workflow_gate import naac_route_enabled
from emma_core.care_workflows import resolve_care_workflow
from emma_core.models import Profile, RosterGrid, RosterRow, StaffLite, ShiftDef
from emma_core.permissions import Feature, Grant, SystemRole, grant_for
from emma_core.services import auth as auth_svc
from emma_core.services._common import operative_version
from emma_core.services import roster as roster_svc


def uid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


ORG, FAC, PROFILE, AUTH, STAFF, UNIT, OTHER_UNIT = [uid(i) for i in range(1, 8)]
VERSION, PERIOD, OTHER_STAFF, OTHER_VERSION = [uid(i) for i in range(8, 12)]


class MemoryQuery:
    def __init__(self, db, table):
        self.db, self.table_name = db, table
        self.filters, self.limit_n, self.order_by = [], None, None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value)
        return self

    def in_(self, key, values):
        self.filters.append(lambda row: row.get(key) in values)
        return self

    def order(self, key, desc=False):
        self.order_by = key, desc
        return self

    def limit(self, count):
        self.limit_n = count
        return self

    def execute(self):
        rows = [deepcopy(row) for row in self.db.tables.get(self.table_name, [])
                if all(check(row) for check in self.filters)]
        if self.order_by:
            key, desc = self.order_by
            rows.sort(key=lambda row: str(row.get(key) or ""), reverse=desc)
        if self.limit_n is not None:
            rows = rows[:self.limit_n]
        return SimpleNamespace(data=rows)


class MemoryDB:
    def __init__(self, **tables):
        self.tables = tables

    def table(self, name):
        return MemoryQuery(self, name)


class NoDB:
    def table(self, name):
        pytest.fail(f"Denied request touched database table {name}")


def identity(role="director", home="B", db=None):
    system = {"director": "OWNER", "deputy": "OWNER", "nurse": "NURSE_MGR", "staff": "FRONTLINE"}.get(role, role)
    profile = Profile(
        id=PROFILE, auth_user_id=AUTH, org_id=ORG, facility_id=FAC,
        staff_id=STAFF if role in ("nurse", "staff", "FRONTLINE") else None,
        role=system,
        facility={"id": FAC, "org_id": ORG, "code": "NAAC" if home == "B" else "A",
                  "name": "Synthetic home", "scheduling_cycle_days": 42 if home == "B" else 28},
        organisation={"id": ORG, "code": "synthetic"},
    )
    member = {"profile_id": PROFILE, "auth_user_id": AUTH,
              "expected_system_role": system, "workflow_role": role,
              "staff_id": profile.staff_id,
              "unit_ids": [UNIT] if role in ("nurse", "staff") else []}
    config = {"schema_version": 1, "bindings": [{
        "care_home": home, "workflow": "NAAC" if home == "B" else "SA",
        "org_id": ORG, "facility_id": FAC, "memberships": [member],
    }]}
    profile.care_workflow = resolve_care_workflow(profile, json.dumps(config))
    return AuthCtx(token="offline-fixture", client=db or NoDB(), profile=profile), config


@pytest.fixture
def http():
    before = dict(app.dependency_overrides)
    clients = []

    def make(ctx):
        app.dependency_overrides[get_ctx] = lambda: ctx
        client = TestClient(app)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()
    app.dependency_overrides.clear()
    app.dependency_overrides.update(before)


def test_sa_preserves_canonical_matrix_and_does_not_inherit_naac_nurse_policy():
    ctx, _ = identity("NURSE_MGR", "A")
    assert ctx.profile.care_workflow.status == "ready"
    assert ctx.profile.care_workflow.workflow == "SA"
    assert ctx.profile.care_workflow.role_label.zh == "護理主任"
    for feature in Feature:
        assert ctx.grant(feature) == grant_for(SystemRole.NURSE_MGR, feature)
    assert ctx.allows("roster_generate")
    naac, _ = identity("nurse")
    assert naac.allows("roster_edit")
    assert not naac.allows("roster_generate")
    assert not naac.allows("roster_delete")


def test_naac_deputy_appointment_is_distinct_from_director_despite_same_base_role():
    director, _ = identity("director")
    deputy, _ = identity("deputy")
    assert director.profile.role == deputy.profile.role == "OWNER"
    assert director.allows("roster_publish") and director.can_decide(Feature.APPROVE_LEAVE)
    assert deputy.allows("roster_edit") and deputy.allows("roster_generate")
    assert deputy.can_recommend(Feature.APPROVE_LEAVE)
    assert not deputy.allows("roster_publish") and not deputy.can_decide(Feature.APPROVE_LEAVE)
    assert deputy.can_read(Feature.AUDIT_LOG)


@pytest.mark.parametrize("change", [
    {"facility_id": uid(99)}, {"org_id": uid(99)}, {"auth_user_id": uid(99)},
    {"id": uid(99)}, {"role": "ADMIN_CLERK"}, {"staff_id": uid(99)},
])
def test_identity_or_role_drift_never_grants(change):
    ctx, config = identity("nurse")
    profile = ctx.profile.model_copy(update=change)
    access = resolve_care_workflow(profile, json.dumps(config))
    assert access.status != "ready"
    assert all(grant == Grant.NONE for grant in access.permissions.values())
    assert not any(access.actions.model_dump().values())


@pytest.mark.parametrize("field,value", [("code", "B"), ("scheduling_cycle_days", 31), ("org_id", uid(90))])
def test_generic_b_or_inconsistent_facility_cannot_be_relabelled_naac(field, value):
    ctx, config = identity()
    ctx.profile.facility = ctx.profile.facility.model_copy(update={field: value})
    assert resolve_care_workflow(ctx.profile, json.dumps(config)).status == "invalid"


@pytest.mark.parametrize("raw", ["", "not-json", '{"schema_version":2,"bindings":[]}'])
def test_missing_or_invalid_config_fails_closed(raw):
    ctx, _ = identity()
    access = resolve_care_workflow(ctx.profile, raw)
    assert access.status != "ready" and not access.actions.roster_publish


def test_duplicate_or_swapped_binding_is_rejected():
    ctx, config = identity()
    config["bindings"].append(deepcopy(config["bindings"][0]))
    assert resolve_care_workflow(ctx.profile, json.dumps(config)).status == "invalid"


def test_same_auth_user_cannot_be_bound_to_both_homes():
    ctx, config = identity()
    second = deepcopy(config["bindings"][0])
    second.update(care_home="A", workflow="SA", org_id=uid(90), facility_id=uid(91))
    second["memberships"][0].update(profile_id=uid(92), workflow_role="OWNER")
    config["bindings"].append(second)
    assert resolve_care_workflow(ctx.profile, json.dumps(config)).status == "invalid"
    config["bindings"] = config["bindings"][:1]
    config["bindings"][0]["workflow"] = "SA"
    assert resolve_care_workflow(ctx.profile, json.dumps(config)).status == "invalid"


def operational_db(profile=None):
    return MemoryDB(
        users_profile=[profile.model_dump()] if profile else [],
        facility_json_configs=[{"facility_id": FAC, "config_key": "scheduling_cycle", "active": True,
                                "config_json": {"cycle_type": "42day", "days": 42, "weeks": 6}}],
        rule_definitions=[
            {"facility_id": FAC, "active": True, "rule_code": "shift_sequence", "severity": "hard",
             "config_json": {"max_consecutive_working_days": 8, "forbidden_before": [{}],
                             "forbidden_after": [{}], "no_consecutive": [{}]}},
            {"facility_id": FAC, "active": True, "rule_code": "night_chain", "severity": "hard",
             "config_json": {"sleep_codes": ["NO"], "day_off_codes": ["O", "DO"]}},
        ],
        shift_definitions=[{"org_id": ORG, "shift_type": code} for code in ("A7", "N10", "NO", "O")],
    )


def test_naac_operational_profile_requires_critical_active_configuration():
    ctx, _ = identity()
    db = operational_db()
    assert auth_svc._naac_profile_configured(db, ctx.profile)
    db.tables["facility_json_configs"][0]["config_json"]["days"] = 31
    assert not auth_svc._naac_profile_configured(db, ctx.profile)
    db = operational_db()
    db.tables["rule_definitions"][1]["severity"] = "soft"
    assert not auth_svc._naac_profile_configured(db, ctx.profile)
    db = operational_db()
    db.tables["shift_definitions"].pop()
    assert not auth_svc._naac_profile_configured(db, ctx.profile)


def test_auth_recomputes_authority_and_never_accepts_database_injected_metadata(monkeypatch):
    ctx, config = identity("deputy")
    db = operational_db(ctx.profile)
    db.tables["users_profile"][0]["care_workflow"] = {"actions": {"roster_publish": True}}
    monkeypatch.setattr(auth_svc.settings, "care_workflow_bindings_json", json.dumps(config))
    profile = auth_svc.get_profile(db, AUTH)
    assert profile.care_workflow.status == "ready"
    assert not profile.care_workflow.actions.roster_publish
    db.tables["rule_definitions"] = []
    profile = auth_svc.get_profile(db, AUTH)
    assert profile.care_workflow.status == "invalid"
    assert not any(profile.care_workflow.actions.model_dump().values())


def test_auth_rejects_ambiguous_profile_rows(monkeypatch):
    ctx, config = identity()
    db = operational_db(ctx.profile)
    db.tables["users_profile"].append(deepcopy(db.tables["users_profile"][0]))
    monkeypatch.setattr(auth_svc.settings, "care_workflow_bindings_json", json.dumps(config))
    assert auth_svc.get_profile(db, AUTH) is None


def test_login_and_refresh_session_shape_carries_current_server_authority():
    ctx, _ = identity("deputy")
    session = SimpleNamespace(access_token="fixture", refresh_token="fixture", expires_at=1,
                              user=SimpleNamespace(id=AUTH, email="fixture@example.invalid"))
    result = auth_api._session_out(session, ctx.profile)
    assert result.org_id == ORG
    assert result.care_workflow.role == "deputy"
    assert result.user.care_workflow == result.care_workflow
    assert not result.care_workflow.actions.roster_publish


def test_unbound_session_can_explain_status_but_cannot_access_business_data(http):
    ctx, _ = identity()
    ctx.profile.care_workflow = resolve_care_workflow(ctx.profile, "")
    client = http(ctx)
    assert client.get("/auth/me").json()["care_workflow"]["status"] == "unbound"
    for path in ("/roster-periods", "/staff", "/me/profile", "/reports"):
        response = client.get(path)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "workflow_not_configured"


@pytest.mark.parametrize("role", ["deputy", "nurse", "staff"])
def test_naac_non_directors_cannot_commit_final_decisions(role, http):
    ctx, _ = identity(role)
    client = http(ctx)
    assert client.post(f"/rosters/{VERSION}/publish").status_code == 403
    assert client.patch(f"/leave-requests/{uid(20)}", json={"decision": "approve"}).status_code == 403
    assert client.post(f"/leave-requests/{uid(20)}/revoke", json={"reason": "fixture"}).status_code == 403
    assert client.post(f"/swap-requests/{uid(20)}/manager-approve", json={"decision": "approve"}).status_code == 403


def test_sa_admin_and_scheduler_cannot_publish_despite_previous_legacy_allowlist(http):
    for role in ("ADMIN_CLERK", "SCHEDULER"):
        ctx, _ = identity(role, "A")
        assert http(ctx).post(f"/rosters/{VERSION}/publish").status_code == 403


def test_only_director_passes_publish_guard_and_hard_violations_still_block(http, monkeypatch):
    ctx, _ = identity("director", db=edit_db())
    commits = []
    result = {"passes": True, "hard_violation_count": 0}
    monkeypatch.setattr(roster, "get_service_client", lambda: ctx.client)
    monkeypatch.setattr(roster.validation_svc, "validate_roster", lambda *a, **k: result)
    monkeypatch.setattr(roster.opt, "get_option_scores", lambda *a, **k: None)
    monkeypatch.setattr(roster.svc, "publish_version", lambda *a, **k: commits.append(k))
    monkeypatch.setattr(roster.svc, "notify_published", lambda *a, **k: None)
    monkeypatch.setattr(roster, "_audit", lambda *a, **k: None)
    assert http(ctx).post(f"/rosters/{VERSION}/publish").status_code == 200
    assert commits[0]["facility_id"] == FAC and commits[0]["created_by"] == PROFILE
    result.update(passes=False, hard_violation_count=1)
    assert http(ctx).post(f"/rosters/{VERSION}/publish").status_code == 409
    assert len(commits) == 1


def test_nurse_cannot_generate_batch_validate_or_delete(http):
    ctx, _ = identity("nurse")
    client = http(ctx)
    for path in ("/optimize-roster", "/optimize-pareto", "/validate-roster", "/roster-periods"):
        assert client.post(path, json={}).status_code == 403
    assert client.delete("/shifts", params={"roster_version_id": VERSION, "staff_id": STAFF,
                                           "date": "2026-11-11"}).status_code == 403


def edit_db(unit=UNIT, status="draft"):
    return MemoryDB(
        roster_versions=[{"id": VERSION, "facility_id": FAC, "period_id": PERIOD,
                          "status": status, "version_type": "manual"}],
        staff=[{"id": OTHER_STAFF, "facility_id": FAC, "primary_unit_id": unit}],
        facility_units=[{"id": UNIT, "facility_id": FAC}],
    )


def cell_payload():
    return {"roster_version_id": VERSION, "staff_id": OTHER_STAFF,
            "date": "2026-11-11", "shift_type": "A7", "tasks": []}


def test_nurse_can_edit_only_assigned_unit_manual_draft(http, monkeypatch):
    calls = []
    monkeypatch.setattr(roster.svc, "get_shift_defs", lambda *_: [ShiftDef(id=uid(30), shift_type="A7")])
    monkeypatch.setattr(roster.scheduling_svc, "validate_task_labels", lambda *a, **k: None)
    monkeypatch.setattr(roster.scheduling_svc, "sync_task_rows_for_assignment", lambda *a, **k: None)
    monkeypatch.setattr(roster, "_audit", lambda *a, **k: None)
    monkeypatch.setattr(roster.svc, "set_cell", lambda *a, **kw: calls.append(kw) or uid(31))
    ctx, _ = identity("nurse", db=edit_db())
    response = http(ctx).post("/shifts", json={**cell_payload(), "facility_id": uid(99)})
    assert response.status_code == 201
    assert calls[0]["facility_id"] == FAC and calls[0]["staff_id"] == OTHER_STAFF
    ctx.client = edit_db(unit=OTHER_UNIT)
    assert http(ctx).post("/shifts", json=cell_payload()).status_code == 403
    ctx.client = edit_db(status="published")
    assert http(ctx).post("/shifts", json=cell_payload()).status_code == 409
    ctx.client = edit_db(status="unexpected")
    assert http(ctx).post("/shifts", json=cell_payload()).status_code == 409
    ctx.client = edit_db()
    ctx.client.tables["staff"] = []
    assert http(ctx).post("/shifts", json=cell_payload()).status_code == 404
    assert len(calls) == 1


@pytest.mark.parametrize("role", ["nurse", "staff", "deputy"])
def test_non_final_approver_cannot_create_leave_for_another_staff_member(role, http):
    ctx, _ = identity(role)
    # A deputy without a staff record is not an employee proxy. A linked deputy
    # is still allowed only its own request, never someone else's.
    ctx.profile.staff_id = STAFF
    response = http(ctx).post("/leave-requests", json={
        "staff_id": OTHER_STAFF, "leave_type": "AL", "date_start": "2026-11-11",
        "date_end": "2026-11-11", "reason": "fixture",
    })
    assert response.status_code == 403


def test_published_unit_roster_filters_staff_and_events_and_rejects_foreign_or_draft(http, monkeypatch):
    db = edit_db(status="published")
    db.tables["roster_versions"][0]["created_at"] = "2026-11-11"
    db.tables["staff"].append({"id": uid(50), "facility_id": FAC, "primary_unit_id": OTHER_UNIT})
    ctx, _ = identity("staff", db=db)
    monkeypatch.setattr(roster, "get_service_client", lambda: db)
    def grid(*_a, **_k):
        return RosterGrid(version_id=VERSION, period_id=PERIOD, status="published", rows=[
            RosterRow(staff=StaffLite(id=sid, name="Fixture", rank="RN", employment_type="local_ft"), cells=[])
            for sid in (STAFF, OTHER_STAFF, uid(50))
        ])
    monkeypatch.setattr(roster.svc, "get_roster_grid", grid)
    response = http(ctx).get("/me/unit-roster")
    assert response.status_code == 200
    assert {r["staff"]["id"] for r in response.json()["rows"]} == {STAFF, OTHER_STAFF}
    assert response.json()["events"] == []
    assert http(ctx).get("/me/unit-roster", params={"version_id": uid(99)}).status_code == 404
    assert http(ctx).get("/me/unit-roster", params={"period_id": uid(99), "version_id": VERSION}).status_code == 404
    db.tables["roster_versions"][0]["status"] = "draft"
    assert http(ctx).get("/me/unit-roster").status_code == 404


def test_task_hydration_requires_exact_assignment_in_nurse_unit(http, monkeypatch):
    db = edit_db()
    db.tables["shift_assignments"] = [{"id": uid(60), "facility_id": FAC,
                                      "staff_id": OTHER_STAFF, "shift_id": uid(61)}]
    ctx, _ = identity("nurse", db=db)
    monkeypatch.setattr(scheduling.svc, "list_task_assignments", lambda *a, **k: [])
    assert http(ctx).get("/task-assignments").status_code == 403
    assert http(ctx).get("/task-assignments", params={"shift_assignment_id": uid(60)}).status_code == 200
    db.tables["staff"][0]["primary_unit_id"] = OTHER_UNIT
    assert http(ctx).get("/task-assignments", params={"shift_assignment_id": uid(60)}).status_code == 403


def test_staff_version_selection_never_falls_back_to_draft():
    db = edit_db()
    assert operative_version(db, FAC, PERIOD)["id"] == VERSION  # manager compatibility
    assert operative_version(db, FAC, PERIOD, published_only=True) is None
    db.tables["roster_versions"][0]["status"] = "published"
    assert operative_version(db, FAC, PERIOD, published_only=True)["id"] == VERSION


def test_explicit_roster_version_cannot_override_facility_or_period_scope():
    db = edit_db()
    assert roster_svc._latest_version(db, uid(99), PERIOD, version_id=VERSION) is None
    assert roster_svc._latest_version(db, FAC, uid(99), version_id=VERSION) is None
    assert roster_svc._latest_version(db, FAC, PERIOD, version_id=VERSION)["id"] == VERSION


def test_naac_unknown_manager_features_fail_closed_but_dashboard_and_staff_tasks_are_explicit():
    director, _ = identity("director")
    nurse, _ = identity("nurse")
    staff, _ = identity("staff")
    assert naac_route_enabled(director, "/dashboard/summary", "GET")
    assert not naac_route_enabled(nurse, "/dashboard/summary", "GET")
    assert not naac_route_enabled(director, "/roi/summary", "GET")
    assert not naac_route_enabled(nurse, "/floor-rules", "GET")
    assert naac_route_enabled(staff, "/me/tasks/{task_assignment_id}/exception", "POST")
    assert not naac_route_enabled(staff, "/task-assignments", "GET")


@pytest.mark.parametrize("role", ["NURSE_MGR", "ALLIED_HEALTH"])
def test_sa_task_code_edit_grant_does_not_grant_floor_rule_or_staff_qualification_writes(role, http):
    ctx, _ = identity(role, "A")
    # Handlers refuse before any DB call; those fields are not task-code edits.
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as denied:
        scheduling._require_write_role(ctx, Feature.ROSTER_RULE_ENGINE)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as denied:
        scheduling._require_write_role(ctx, Feature.STAFF_PROFILE_WRITE)
    assert denied.value.status_code == 403
