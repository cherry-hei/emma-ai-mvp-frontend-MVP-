"""Offline account-acceptance boundaries for the November trial.

These are deliberately HTTP-level tests over the application router, not direct
handler calls and not a Supabase fixture.  They give a repeatable pre-flight
answer to three bounded questions without creating identities or touching a
real database:

* Is the public API invitation-only (no self-sign-up/account-provision route)?
* Does a successfully authenticated identity still need a tenant profile?
* Can a caller smuggle a privileged application role through staff-record CRUD?

They do *not* prove hosted Supabase Auth, database RLS, email delivery, or a
live invitation flow.  Those require the dedicated trial UAT in accounts.md.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.deps import AuthCtx, get_ctx
from api.main import app
from api.routers import auth as auth_router
from api.routers import configs as configs_router
from api.routers import scheduling as scheduling_router
from api.routers import staff as staff_router
from emma_core.models import Profile


@pytest.fixture
def http():
    """A real ASGI client for the registered API; external dependencies are mocked."""
    return TestClient(app, raise_server_exceptions=False)


def _ctx(role: str) -> AuthCtx:
    profile = Profile.model_construct(
        id="profile-1",
        auth_user_id="auth-user-1",
        facility_id="facility-1",
        org_id="org-1",
        email="manager@example.invalid",
        role=role,
    )
    return AuthCtx(
        token="offline-account-acceptance-token",
        client=object(),
        # ``model_construct`` deliberately bypasses schema validation so the
        # fail-closed tests can model a pre-migration/corrupt DB role. Normal
        # profiles still arrive through validated production models.
        profile=profile,
    )


@pytest.fixture
def as_role():
    """Run an actual HTTP route under a bounded, in-memory caller context."""
    client = TestClient(app, raise_server_exceptions=False)

    def _as(role: str) -> TestClient:
        app.dependency_overrides[get_ctx] = lambda: _ctx(role)
        return client

    yield _as
    app.dependency_overrides.pop(get_ctx, None)


def test_public_contract_has_no_self_signup_or_account_provisioning_operation(http):
    """Current public API is login/refresh/me only, not a self-service sign-up API.

    This assertion intentionally permits staff business records and device
    registration, but blocks routes whose very purpose would be creating an
    identity, invitation, profile assignment, or bootstrap account.
    """
    paths = http.get("/openapi.json").json()["paths"]
    forbidden_tokens = ("signup", "sign-up", "register", "invite", "invitation",
                        "account", "provision", "bootstrap", "users", "profiles")
    public_account_paths = [
        path for path in paths
        if any(token in path.lower() for token in forbidden_tokens)
    ]
    assert public_account_paths == [], (
        "public self-service/account-provisioning surface added: "
        f"{public_account_paths}"
    )
    assert {"/auth/login", "/auth/refresh", "/auth/me"} <= set(paths)


def test_login_refuses_authenticated_identity_without_tenant_profile(http, monkeypatch):
    """A provider identity cannot enter the app until provisioning links its profile.

    ``sign_in`` is replaced only at the auth-provider boundary.  The test calls
    the registered ``POST /auth/login`` route and verifies the application-side
    tenant-profile gate without contacting a provider or using credentials.
    """
    session = SimpleNamespace(
        access_token="offline-access-token",
        refresh_token="offline-refresh-token",
        expires_at=1_800_000_000,
        user=SimpleNamespace(id="auth-user-unlinked", email="unlinked@example.invalid"),
    )
    monkeypatch.setattr(auth_router, "sign_in", lambda _email, _password: (object(), session))
    monkeypatch.setattr(auth_router, "get_profile", lambda _client, _user_id: None)

    response = http.post(
        "/auth/login",
        json={"email": "unlinked@example.invalid", "password": "not-used-offline"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "no_profile"


@pytest.mark.parametrize("role", ["FRONTLINE", "NURSE_MGR", "SCHEDULER", "HR_AUDITOR"])
def test_non_account_admin_cannot_create_staff_record(role, as_role, monkeypatch):
    """A roster/staff user cannot use the staff endpoint as a provisioning path."""
    reached: list[dict] = []
    monkeypatch.setattr(
        staff_router.svc,
        "create_staff",
        lambda *_args, **kwargs: reached.append(kwargs) or {"id": "should-not-exist"},
    )

    response = as_role(role).post(
        "/staff",
        json={
            "name": "Offline Test Staff",
            "rank": "RN",
            "employment_type": "local_ft",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"
    assert reached == [], "refused request must not reach the write service"


def test_staff_record_creation_rejects_client_selected_privileged_role(as_role, monkeypatch):
    """``POST /staff`` cannot attach a system role from caller-controlled JSON.

    A profile/invitation implementation must assign its own allow-listed role
    server-side; the existing staff-record endpoint is not an account endpoint.
    """
    reached: list[dict] = []
    monkeypatch.setattr(
        staff_router.svc,
        "create_staff",
        lambda *_args, **kwargs: reached.append(kwargs) or {"id": "should-not-exist"},
    )

    response = as_role("ADMIN_CLERK").post(
        "/staff",
        json={
            "name": "Offline Test Staff",
            "rank": "RN",
            "employment_type": "local_ft",
            "role": "OWNER",
        },
    )

    assert response.status_code == 422
    assert reached == [], "invalid role-bearing body must not reach the write service"


def test_canonical_owner_reaches_existing_facility_settings_write(as_role, monkeypatch):
    """Canonical OWNER retains the existing facility-config write privilege."""
    reached: list[dict] = []
    monkeypatch.setattr(configs_router.svc, "get_config", lambda *_args: None)
    monkeypatch.setattr(
        configs_router.svc,
        "put_config",
        lambda *_args, **kwargs: reached.append(kwargs) or {"id": "config-1", "version": 1},
    )
    monkeypatch.setattr(configs_router.audit, "record", lambda *_args, **_kwargs: None)

    response = as_role("OWNER").post(
        "/facility-configs",
        json={"config_key": "offline_probe", "config_json": {"enabled": True}},
    )

    assert response.status_code == 201
    assert reached and reached[0]["created_by"] == "profile-1"


@pytest.mark.parametrize("role", ["FRONTLINE", "not_a_role"])
def test_facility_settings_write_fails_closed_for_frontline_and_unknown(
    role, as_role, monkeypatch,
):
    """Self-only and unrecognized roles cannot reach the settings write service."""
    reached: list[dict] = []
    monkeypatch.setattr(
        configs_router.svc,
        "put_config",
        lambda *_args, **kwargs: reached.append(kwargs) or {"id": "must-not-write"},
    )

    response = as_role(role).post(
        "/facility-configs",
        json={"config_key": "offline_probe", "config_json": {"enabled": True}},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"
    assert reached == [], "a denied role must not reach the configuration service"


def test_canonical_owner_reaches_existing_scheduling_write(as_role, monkeypatch):
    """Canonical OWNER retains the legacy-equivalent scheduling write path."""
    reached: list[dict] = []
    monkeypatch.setattr(
        scheduling_router.svc,
        "create_facility_event",
        lambda *_args, **kwargs: reached.append(kwargs) or {
            "id": "event-1",
            "event_type": "visiting",
            "event_date": "2026-11-01",
            "staffing_requirements": [],
        },
    )

    response = as_role("OWNER").post(
        "/facility-events",
        json={"event_type": "visiting", "event_date": "2026-11-01"},
    )

    assert response.status_code == 201
    assert reached


@pytest.mark.parametrize("role", ["FRONTLINE", "not_a_role"])
def test_scheduling_write_fails_closed_for_frontline_and_unknown(
    role, as_role, monkeypatch,
):
    """Canonical FRONTLINE and unrecognized roles do not reach scheduling writes."""
    reached: list[dict] = []
    monkeypatch.setattr(
        scheduling_router.svc,
        "create_facility_event",
        lambda *_args, **kwargs: reached.append(kwargs) or {"id": "must-not-write"},
    )

    response = as_role(role).post(
        "/facility-events",
        json={"event_type": "visiting", "event_date": "2026-11-01"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"
    assert reached == [], "a denied role must not reach the scheduling service"


def test_nurse_manager_may_edit_a_shift_but_cannot_publish_or_create_period(as_role, monkeypatch):
    """Current supported roster route has the required nurse/draft versus owner/final split."""
    from api.routers import roster as roster_router

    calls: list[str] = []
    shift_def = SimpleNamespace(
        id="shift-def-a",
        shift_type="A",
        start_time="07:00",
        end_time="15:00",
        paid_minutes=480,
    )
    monkeypatch.setattr(roster_router.svc, "get_shift_defs", lambda *_args: [shift_def])
    monkeypatch.setattr(roster_router.scheduling_svc, "validate_task_labels", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(roster_router.scheduling_svc, "sync_task_rows_for_assignment", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(roster_router.svc, "set_cell", lambda *_args, **_kwargs: calls.append("set_cell") or "assignment-1")
    monkeypatch.setattr(roster_router.audit, "record", lambda *_args, **_kwargs: None)

    http = as_role("NURSE_MGR")
    payload = {
        "roster_version_id": "version-1",
        "staff_id": "staff-1",
        "date": "2026-11-01",
        "shift_type": "A",
        "tasks": [],
    }
    assert http.post("/shifts", json=payload).status_code == 201
    assert http.patch("/shifts", json=payload).status_code == 200
    assert calls == ["set_cell", "set_cell"]

    assert http.post(
        "/roster-periods",
        json={"period_start": "2026-11-01", "period_end": "2026-11-28", "cycle_type": "28day"},
    ).status_code == 403
    assert http.post("/rosters/version-1/publish").status_code == 403
