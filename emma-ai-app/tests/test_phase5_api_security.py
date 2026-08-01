from __future__ import annotations

from datetime import date

from fastapi import HTTPException
import pytest

from api.deps import AuthCtx
from api.routers import leave as leave_router
from api.routers import optimize as optimize_router
from api.routers import roster as roster_router
from emma_core.models import LeaveDecisionRequest, LeaveRequestCreate, Profile

from tests.test_optimize_service import build_store


def _ctx(
    client,
    *,
    role: str = "scheduler",
    staff_id: str | None = None,
) -> AuthCtx:
    return AuthCtx(
        token="test-token",
        client=client,
        profile=Profile(
            id="profile-1",
            facility_id="f1",
            role=role,
            staff_id=staff_id,
        ),
    )


def _validation_result(version_id: str) -> dict:
    return {
        "roster_version_id": version_id,
        "method": "deterministic_phase5",
        "passes": True,
        "hard_violation_count": 0,
        "violations": [],
        "ratio_checks": [],
    }


def test_manager_validation_authorizes_with_rls_then_persists_as_service(
    monkeypatch,
):
    user_client = build_store()
    service_client = object()
    calls: list[tuple[object, str | None, bool]] = []

    monkeypatch.setattr(
        optimize_router,
        "get_service_client",
        lambda: service_client,
    )
    monkeypatch.setattr(
        optimize_router.validation_svc,
        "validate_roster",
        lambda client, _facility_id, version_id, *, validated_by, persist: (
            calls.append((client, validated_by, persist))
            or _validation_result(version_id)
        ),
    )
    monkeypatch.setattr(
        optimize_router.opt,
        "get_option_scores",
        lambda _client, _version_id: None,
    )

    result = optimize_router.validate_roster(
        optimize_router.ValidateRequest(roster_version_id="mv1"),
        _ctx(user_client),
    )

    assert result.passes
    assert calls == [(service_client, "profile-1", True)]


def test_validation_rejects_unknown_version_before_service_escalation(
    monkeypatch,
):
    user_client = build_store()
    called = False

    def service_client():
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(
        optimize_router,
        "get_service_client",
        service_client,
    )

    with pytest.raises(HTTPException) as exc:
        optimize_router.validate_roster(
            optimize_router.ValidateRequest(roster_version_id="foreign"),
            _ctx(user_client),
        )

    assert exc.value.status_code == 404
    assert not called


def test_publish_uses_one_service_client_after_rls_authorization(monkeypatch):
    user_client = build_store()
    service_client = object()
    validation_clients: list[object] = []
    publication_clients: list[object] = []

    monkeypatch.setattr(
        roster_router,
        "get_service_client",
        lambda: service_client,
    )
    monkeypatch.setattr(
        roster_router.validation_svc,
        "validate_roster",
        lambda client, _facility_id, version_id, **_kwargs: (
            validation_clients.append(client)
            or _validation_result(version_id)
        ),
    )
    monkeypatch.setattr(
        roster_router.opt,
        "get_option_scores",
        lambda _client, _version_id: None,
    )
    monkeypatch.setattr(
        roster_router.svc,
        "publish_version",
        lambda client, **_kwargs: publication_clients.append(client),
    )

    result = roster_router.publish("mv1", _ctx(user_client))

    assert result["status"] == "published"
    assert validation_clients == [service_client]
    assert publication_clients == [service_client]


def test_leave_decision_authorizes_with_rls_then_uses_service_client(
    monkeypatch,
):
    user_client = build_store()
    user_client.data["leave_requests"] = [{
        "id": "leave-1",
        "facility_id": "f1",
        "staff_id": "cw1",
        "status": "pending",
    }]
    service_client = object()
    calls: list[object] = []

    monkeypatch.setattr(
        leave_router,
        "get_service_client",
        lambda: service_client,
    )
    monkeypatch.setattr(
        leave_router.svc,
        "decide",
        lambda client, *_args, **_kwargs: (
            calls.append(client) or {"id": "leave-1", "status": "approved"}
        ),
    )

    result = leave_router.decide_request(
        "leave-1",
        LeaveDecisionRequest(decision="approve"),
        _ctx(user_client),
    )

    assert result["status"] == "approved"
    assert calls == [service_client]


def test_leave_create_blocks_staff_impersonation_before_service_escalation(
    monkeypatch,
):
    user_client = build_store()
    called = False

    def service_client():
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(leave_router, "get_service_client", service_client)
    body = LeaveRequestCreate(
        staff_id="cw2",
        leave_type="AL",
        date_start=date(2026, 7, 1),
        date_end=date(2026, 7, 1),
    )

    with pytest.raises(HTTPException) as exc:
        leave_router.create_request(
            body,
            _ctx(user_client, role="staff", staff_id="cw1"),
        )

    assert exc.value.status_code == 403
    assert not called


def test_leave_create_authorizes_target_then_uses_service_client(monkeypatch):
    user_client = build_store()
    service_client = object()
    calls: list[tuple[object, str]] = []

    monkeypatch.setattr(
        leave_router,
        "get_service_client",
        lambda: service_client,
    )
    monkeypatch.setattr(
        leave_router.svc,
        "create_request",
        lambda client, _facility_id, *, staff_id, **_kwargs: (
            calls.append((client, staff_id))
            or {"id": "leave-1", "status": "pending"}
        ),
    )
    body = LeaveRequestCreate(
        staff_id="cw1",
        leave_type="AL",
        date_start=date(2026, 7, 1),
        date_end=date(2026, 7, 1),
    )

    result = leave_router.create_request(body, _ctx(user_client))

    assert result["status"] == "pending"
    assert calls == [(service_client, "cw1")]
