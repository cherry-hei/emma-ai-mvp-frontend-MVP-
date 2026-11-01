"""Offline request-window contract tests using disposable RPC fixtures only."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.deps import AuthCtx
from api.routers import request_windows as router
from emma_core.models import Profile
from emma_core.services import leave as leave_svc
from emma_core.services import request_windows as svc


class RpcClient:
    def __init__(self, results: dict[str, object] | None = None, error: Exception | None = None):
        self.results = results or {}
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def rpc(self, name, params):
        self.calls.append((name, params))

        def execute():
            if self.error:
                raise self.error
            return SimpleNamespace(data=self.results.get(name))

        return SimpleNamespace(execute=execute)

    def table(self, name):
        assert name == "staff"
        return _StaffQuery()


class _StaffQuery:
    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=[{"primary_unit_id": "unit-1"}])


def _ctx(client, *, role="FRONTLINE", staff_id="staff-1"):
    return AuthCtx(
        token="offline-window-token",
        client=client,
        profile=Profile(
            id="profile-1",
            facility_id="facility-1",
            org_id="org-1",
            role=role,
            staff_id=staff_id,
        ),
    )


def _open_result(*, kind="duty"):
    window = {
        "id": "window-1",
        "kind": kind,
        "scope": "facility",
        "unit_id": None,
        "state": "open",
        "opens_at": "2026-11-01T00:00:00+00:00",
        "closes_at": "2026-11-03T00:00:00+00:00",
        "target_start": "2026-11-10",
        "target_end_exclusive": "2026-12-01",
        "version": 1,
        "status": "open",
        "server_now": "2026-11-01T01:00:00+00:00",
    }
    return {
        "kind": kind,
        "available": True,
        "status": "open",
        "reason": None,
        "server_now": "2026-11-01T01:00:00+00:00",
        "window": window,
    }


def _create_body(**overrides):
    data = {
        "kind": "duty",
        "scope": "facility",
        "state": "open",
        "opens_at": "2026-11-01T09:00:00+08:00",
        "closes_at": "2026-11-03T17:00:00+08:00",
        "target_start": "2026-11-10",
        "target_end_exclusive": "2026-12-01",
        "idempotency_key": "offline-window-create-1",
    }
    data.update(overrides)
    return router.RequestWindowCreate.model_validate(data)


def test_create_model_requires_timezone_offsets_and_exclusive_target_end():
    with pytest.raises(ValidationError, match="timezone"):
        _create_body(opens_at="2026-11-01T09:00:00")
    with pytest.raises(ValidationError, match="after target_start"):
        _create_body(target_start="2026-11-10", target_end_exclusive="2026-11-10")


def test_create_model_has_no_tenant_or_organisation_spoofing_fields():
    with pytest.raises(ValidationError):
        _create_body(facility_id="foreign-facility")
    with pytest.raises(ValidationError):
        _create_body(organization_id="foreign-org")


def test_duty_gate_uses_rpc_dates_and_accepts_exclusive_end_boundary_before_it():
    client = RpcClient({"request_window_availability": _open_result()})
    svc.assert_request_allowed(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type="DO",
        date_start=date(2026, 11, 10),
        date_end=date(2026, 11, 30),
    )
    name, params = client.calls[0]
    assert name == "request_window_availability"
    assert params == {
        "p_facility_id": "facility-1",
        "p_staff_id": "staff-1",
        "p_leave_type": "DO",
        "p_date_start": "2026-11-10",
        "p_date_end": "2026-11-30",
    }


@pytest.mark.parametrize("leave_type", ["SL", "DSL", "urgent", "late"])
def test_emergency_sick_reporting_never_requires_a_window_rpc(leave_type):
    client = RpcClient()
    svc.assert_request_allowed(
        client,
        "facility-1",
        staff_id="staff-1",
        leave_type=leave_type,
        date_start=date(2026, 11, 10),
        date_end=date(2026, 11, 10),
    )
    assert client.calls == []


def test_duty_gate_fails_closed_for_missing_or_closed_window():
    client = RpcClient({
        "request_window_availability": {
            "available": False,
            "status": "closed",
            "reason": "The request window is not open.",
        }
    })
    with pytest.raises(svc.RequestWindowUnavailable, match="closed"):
        svc.assert_request_allowed(
            client,
            "facility-1",
            staff_id="staff-1",
            leave_type="duty_request",
            date_start=date(2026, 11, 10),
            date_end=date(2026, 11, 10),
        )


def test_absent_database_rpc_fails_closed_for_gated_duty():
    with pytest.raises(svc.RequestWindowDatabaseUnavailable, match="unavailable"):
        svc.assert_request_allowed(
            object(),
            "facility-1",
            staff_id="staff-1",
            leave_type="shift_swap",
            date_start=date(2026, 11, 10),
            date_end=date(2026, 11, 10),
        )


def test_real_rpc_capable_leave_service_caller_is_preflight_gated(monkeypatch):
    """A trusted service caller cannot silently skip the window check.

    Legacy pure-Python policy fixtures deliberately have no RPC surface. This
    fixture has one, modelling the actual Supabase service client and ensuring
    the service-layer mirror calls the gate before its insert.
    """
    calls = []

    class InsertQuery:
        def insert(self, row):
            self.row = row
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": "request-1", **self.row}])

    class ServiceClient:
        def rpc(self, *_args, **_kwargs):
            pytest.fail("the gate is mocked below and must run before DB RPC")

        def table(self, name):
            assert name == "leave_requests"
            return InsertQuery()

    monkeypatch.setattr(
        leave_svc.request_windows,
        "assert_request_allowed",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        leave_svc,
        "_evaluate_request_policy",
        lambda *_args, **_kwargs: ("normal", "", {"passes": True, "issues": []}),
    )
    monkeypatch.setattr(leave_svc.notify, "push_to_approvers", lambda *_args, **_kwargs: None)

    row = leave_svc.create_request(
        ServiceClient(),
        "facility-1",
        staff_id="staff-1",
        leave_type="duty_request",
        requested_shift_type="A",
        date_start=date(2026, 11, 10),
        date_end=date(2026, 11, 10),
    )
    assert row["id"] == "request-1"
    assert calls[0][1] == {
        "staff_id": "staff-1",
        "leave_type": "duty_request",
        "date_start": date(2026, 11, 10),
        "date_end": date(2026, 11, 10),
    }


def test_create_rpc_uses_authenticated_facility_not_body_scope():
    client = RpcClient({"create_request_window": _open_result()["window"]})
    body = _create_body()
    result = router.create_request_window(body, _ctx(client, role="superintendent"))
    assert result["id"] == "window-1"
    name, params = client.calls[0]
    assert name == "create_request_window"
    assert params["p_facility_id"] == "facility-1"
    assert params["p_scope_level"] == "facility"
    assert params["p_target_end_exclusive"] == "2026-12-01"


@pytest.mark.parametrize("role", ["FRONTLINE", "NURSE_MGR", "ADMIN_CLERK", "SCHEDULER"])
def test_only_existing_owner_superintendent_mapping_can_create(role):
    client = RpcClient({"create_request_window": _open_result()["window"]})
    with pytest.raises(HTTPException) as exc:
        router.create_request_window(_create_body(), _ctx(client, role=role))
    assert exc.value.status_code == 403
    assert client.calls == []


def test_patch_model_requires_a_real_change_and_emits_json_safe_patch():
    with pytest.raises(ValidationError, match="at least one"):
        router.RequestWindowPatch(version=1)
    body = router.RequestWindowPatch(
        version=1,
        closes_at=datetime(2026, 11, 4, 17, tzinfo=timezone.utc),
    )
    client = RpcClient({"patch_request_window": _open_result()["window"]})
    router.patch_request_window("window-1", body, _ctx(client, role="OWNER"))
    assert client.calls[0][1]["p_patch"] == {"closes_at": "2026-11-04T17:00:00Z"}


def test_router_surfaces_stale_compare_and_swap_as_explicit_conflict(monkeypatch):
    body = router.RequestWindowPatch(version=2, state="closed")
    monkeypatch.setattr(
        router.svc,
        "patch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            svc.RequestWindowConflict("request window was changed by another manager")
        ),
    )
    with pytest.raises(HTTPException) as exc:
        router.patch_request_window("window-1", body, _ctx(object(), role="OWNER"))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "request_window_conflict"


def test_me_and_legacy_pwa_reads_are_db_time_and_scope_backed():
    client = RpcClient({"request_window_availability": _open_result()})
    current = router.my_request_window("duty", _ctx(client))
    assert current["available"] is True
    assert current["server_now"] == "2026-11-01T01:00:00+00:00"

    client = RpcClient({"request_window_availability": _open_result()})
    legacy = router.legacy_duty_request_window(_ctx(client))
    assert legacy == {
        "enabled": True,
        "opens_at": "2026-11-01T00:00:00+00:00",
        "closes_at": "2026-11-03T00:00:00+00:00",
        "target_start": "2026-11-10",
        "target_end": "2026-11-30",
        "status": "open",
        "server_now": "2026-11-01T01:00:00+00:00",
    }


def test_list_route_uses_db_catalog_without_manager_privilege_requirement():
    catalog = {"server_now": "2026-11-01T01:00:00+00:00", "windows": []}
    client = RpcClient({"request_window_catalog": catalog})
    assert router.list_request_windows(_ctx(client, role="FRONTLINE")) == catalog
    assert client.calls == [("request_window_catalog", {"p_facility_id": "facility-1"})]


def test_legacy_status_fails_closed_when_no_window_is_configured():
    legacy = svc.legacy_duty_window({
        "available": False,
        "status": "unavailable",
        "server_now": "2026-11-01T01:00:00+00:00",
        "window": None,
    })
    assert legacy["enabled"] is False
    assert legacy["status"] == "closed"
    assert legacy["target_start"] is None
