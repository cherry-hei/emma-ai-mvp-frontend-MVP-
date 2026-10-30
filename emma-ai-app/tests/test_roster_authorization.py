"""Offline HTTP authorization regressions for the facility-wide roster router.

These tests intentionally replace ``get_ctx`` and every reached service with
in-memory fakes. They exercise FastAPI dependency wiring rather than direct
handler calls, without a Supabase URL, token, or database connection.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.deps import AuthCtx, get_ctx
from api.main import app
from api.routers import roster as roster_router
from emma_core.models import Profile, ShiftDef


class _VersionQuery:
    """The only client query reached by a successful publish request."""

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=[{"id": "version-1"}])


class FakeClient:
    """Pure test double; it deliberately has no URL, token, or live I/O."""

    def table(self, name: str):
        assert name == "roster_versions"
        return _VersionQuery()


def _ctx(role: str) -> AuthCtx:
    return AuthCtx(
        token="offline-test-token",
        client=FakeClient(),
        profile=Profile(
            id="profile-1",
            facility_id="facility-1",
            role=role,
            staff_id="staff-1",
        ),
    )


SHIFT_PAYLOAD = {
    "roster_version_id": "version-1",
    "staff_id": "staff-1",
    "date": "2026-11-01",
    "shift_type": "A",
    "tasks": [],
}
PERIOD_PAYLOAD = {
    "period_start": "2026-11-01",
    "period_end": "2026-11-28",
    "cycle_type": "28day",
}


@pytest.fixture
def as_role(monkeypatch):
    """Return an HTTP client wired to a role, plus calls made after a guard passes."""
    calls: list[str] = []
    shift_def = ShiftDef(
        id="shift-def-a",
        shift_type="A",
        start_time="07:00",
        end_time="15:00",
        paid_minutes=480,
    )

    monkeypatch.setattr(roster_router.svc, "list_periods", lambda *_args: [])
    monkeypatch.setattr(roster_router.svc, "list_versions", lambda *_args: [])
    monkeypatch.setattr(
        roster_router.svc,
        "get_roster_grid",
        lambda *_args, **_kwargs: {
            "version_id": "version-1",
            "period_id": "period-1",
            "status": "draft",
            "period_start": "2026-11-01",
            "period_end": "2026-11-28",
            "dates": [],
            "rows": [],
            "events": [],
        },
    )
    monkeypatch.setattr(roster_router.svc, "get_shift_defs", lambda *_args: [shift_def])
    monkeypatch.setattr(roster_router.svc, "list_task_definitions", lambda *_args: [])
    monkeypatch.setattr(
        roster_router.svc,
        "create_period",
        lambda *_args, **_kwargs: (
            {
                "id": "period-1",
                "period_start": "2026-11-01",
                "period_end": "2026-11-28",
                "cycle_type": "28day",
                "status": "planning",
            },
            {"id": "version-1"},
        ),
    )
    monkeypatch.setattr(
        roster_router.svc,
        "set_cell",
        lambda *_args, **_kwargs: calls.append("set_cell") or "assignment-1",
    )
    monkeypatch.setattr(
        roster_router.svc,
        "clear_cell",
        lambda *_args, **_kwargs: calls.append("clear_cell"),
    )
    monkeypatch.setattr(
        roster_router.svc,
        "save_draft",
        lambda *_args, **_kwargs: calls.append("save_draft"),
    )
    monkeypatch.setattr(roster_router.scheduling_svc, "validate_task_labels",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(roster_router.scheduling_svc, "sync_task_rows_for_assignment",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(roster_router.audit, "record", lambda *_args, **_kwargs: None)

    http = TestClient(app, raise_server_exceptions=False)

    def _as(role: str) -> tuple[TestClient, list[str]]:
        app.dependency_overrides[get_ctx] = lambda: _ctx(role)
        return http, calls

    yield _as
    app.dependency_overrides.pop(get_ctx, None)


FACILITY_WIDE_READS = [
    "/roster-periods",
    "/roster-versions",
    "/rosters/period-1",
    "/shift-definitions",
    "/task-definitions",
]


@pytest.mark.parametrize("path", FACILITY_WIDE_READS)
def test_frontline_cannot_read_any_facility_wide_roster_data(as_role, path):
    http, _calls = as_role("FRONTLINE")

    response = http.get(path)

    assert response.status_code == 403, f"frontline reached {path}"
    assert response.json()["detail"]["code"] == "forbidden"


MUTATIONS = [
    ("post", "/roster-periods", PERIOD_PAYLOAD),
    ("post", "/shifts", SHIFT_PAYLOAD),
    ("patch", "/shifts", SHIFT_PAYLOAD),
    ("delete", "/shifts?roster_version_id=version-1&staff_id=staff-1&date=2026-11-01", None),
    ("post", "/rosters/version-1/save-draft", None),
    ("post", "/rosters/version-1/publish", None),
]


@pytest.mark.parametrize(("method", "path", "payload"), MUTATIONS)
def test_frontline_cannot_mutate_a_facility_roster(as_role, method, path, payload):
    http, calls = as_role("FRONTLINE")

    request = getattr(http, method)
    response = request(path, json=payload) if payload is not None else request(path)

    assert response.status_code == 403, f"frontline reached {method.upper()} {path}"
    assert response.json()["detail"]["code"] == "forbidden"
    assert calls == [], "a refused request must not reach a roster write service"


def test_scheduler_can_read_edit_save_and_create_a_period_but_cannot_publish(as_role):
    http, calls = as_role("SCHEDULER")

    assert http.get("/rosters/period-1").status_code == 200
    assert http.post("/roster-periods", json=PERIOD_PAYLOAD).status_code == 201
    assert http.post("/shifts", json=SHIFT_PAYLOAD).status_code == 201
    assert http.patch("/shifts", json=SHIFT_PAYLOAD).status_code == 200
    assert http.delete(
        "/shifts?roster_version_id=version-1&staff_id=staff-1&date=2026-11-01"
    ).status_code == 204
    assert http.post("/rosters/version-1/save-draft").status_code == 200
    assert calls == ["set_cell", "set_cell", "clear_cell", "save_draft"]

    # An authorised scheduler can create a planning period but final publication
    # stays with the canonical facility OWNER.
    assert http.post("/rosters/version-1/publish").status_code == 403


def test_nurse_manager_can_edit_but_cannot_create_a_period_or_publish(as_role):
    http, calls = as_role("NURSE_MGR")

    assert http.patch("/shifts", json=SHIFT_PAYLOAD).status_code == 200
    assert calls == ["set_cell"]
    assert http.post("/roster-periods", json=PERIOD_PAYLOAD).status_code == 403
    assert http.post("/rosters/version-1/publish").status_code == 403


def test_owner_can_create_a_period_and_publish(as_role, monkeypatch):
    http, _calls = as_role("OWNER")
    published: list[tuple[str, str]] = []

    monkeypatch.setattr(roster_router, "get_service_client", lambda: object())
    monkeypatch.setattr(
        roster_router.validation_svc,
        "validate_roster",
        lambda *_args, **_kwargs: {"passes": True, "hard_violation_count": 0},
    )
    monkeypatch.setattr(roster_router.opt, "get_option_scores", lambda *_args: None)
    monkeypatch.setattr(
        roster_router.svc,
        "publish_version",
        lambda _client, *, facility_id, roster_version_id, created_by: published.append(
            (facility_id, roster_version_id)
        ),
    )
    monkeypatch.setattr(roster_router.svc, "notify_published", lambda *_args: None)

    assert http.post("/roster-periods", json=PERIOD_PAYLOAD).status_code == 201
    response = http.post("/rosters/version-1/publish")

    assert response.status_code == 200
    assert response.json() == {"roster_version_id": "version-1", "status": "published"}
    assert published == [("facility-1", "version-1")]
