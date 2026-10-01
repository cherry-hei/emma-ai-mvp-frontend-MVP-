"""No-secret authorization tests for chat and the duty request window."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.deps import AuthCtx
from api.routers import leave as leave_router
from api.routers import messages as messages_router
from api.routers import request_windows as windows_router
from emma_core.models import LeaveRequestCreate, Profile
from emma_core.services import direct_messages, duty_request_window


class Query:
    """Small in-memory subset of the Supabase query builder used by these paths."""

    def __init__(self, client, table: str):
        self.client, self.table = client, table
        self.action = "select"
        self.payload = None
        self.filters: list[tuple[str, str, object]] = []

    def select(self, *_args, **_kwargs):
        self.action = "select"
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self.filters.append(("in", field, tuple(values)))
        return self

    def or_(self, _expression):
        # Services also filter returned messages defensively. This fake does not
        # parse PostgREST syntax, so it intentionally returns the facility rows.
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", deepcopy(payload)
        return self

    def update(self, payload):
        self.action, self.payload = "update", deepcopy(payload)
        return self

    def _matches(self, row):
        for operator, field, expected in self.filters:
            if operator == "eq" and row.get(field) != expected:
                return False
            if operator == "in" and row.get(field) not in expected:
                return False
        return True

    def execute(self):
        rows = self.client.rows.setdefault(self.table, [])
        if self.action == "insert":
            row = deepcopy(self.payload)
            row.setdefault("id", f"{self.table}-{len(rows) + 1}")
            row.setdefault("created_at", "2026-10-01T09:00:00+00:00")
            row.setdefault("read_at", None)
            rows.append(row)
            return SimpleNamespace(data=[deepcopy(row)])
        if self.action == "update":
            result = []
            for row in rows:
                if self._matches(row):
                    row.update(deepcopy(self.payload))
                    result.append(deepcopy(row))
            return SimpleNamespace(data=result)
        return SimpleNamespace(data=[deepcopy(row) for row in rows if self._matches(row)])


class Client:
    def __init__(self, rows: dict[str, list[dict]] | None = None):
        self.rows = deepcopy(rows or {})

    def table(self, name: str):
        return Query(self, name)


def _ctx(client, *, profile_id="p-front", facility_id="f1", role="FRONTLINE", staff_id=None):
    return AuthCtx(
        token="mock-token",
        client=client,
        profile=Profile(id=profile_id, facility_id=facility_id, role=role, staff_id=staff_id),
    )


def _message_rows():
    return {
        "users_profile": [
            {"id": "p-owner", "facility_id": "f1", "role": "OWNER", "staff_id": "s-owner"},
            {"id": "p-front", "facility_id": "f1", "role": "FRONTLINE", "staff_id": "s-front"},
            {"id": "p-front-2", "facility_id": "f1", "role": "staff", "staff_id": "s-front-2"},
            {"id": "p-scheduler", "facility_id": "f1", "role": "SCHEDULER", "staff_id": "s-scheduler"},
            {"id": "p-foreign", "facility_id": "f2", "role": "FRONTLINE", "staff_id": "s-foreign"},
        ],
        "staff": [
            {"id": "s-owner", "facility_id": "f1", "name": "Owner", "name_en": "Owner"},
            {"id": "s-front", "facility_id": "f1", "name": "Chan", "name_en": "Ada Chan"},
            {"id": "s-front-2", "facility_id": "f1", "name": "Lee", "name_en": "Bea Lee"},
            {"id": "s-scheduler", "facility_id": "f1", "name": "Scheduler", "name_en": "Scheduler"},
            {"id": "s-foreign", "facility_id": "f2", "name": "Foreign", "name_en": "Foreign"},
        ],
        "direct_messages": [],
    }


@pytest.mark.parametrize(
    ("sender", "recipient", "allowed"),
    [
        ("OWNER", "FRONTLINE", True),
        ("NURSE_MGR", "staff", True),
        ("superintendent", "FRONTLINE", True),
        ("FRONTLINE", "superintendent", True),
        ("OWNER", "NURSE_MGR", False),
        ("FRONTLINE", "FRONTLINE", False),
        ("SCHEDULER", "FRONTLINE", False),
    ],
)
def test_direct_message_role_direction_including_legacy_aliases(sender, recipient, allowed):
    assert direct_messages._allowed_pair(sender, recipient) is allowed


def test_contacts_load_distinct_staff_names_without_email_and_filter_roles():
    contacts = direct_messages.contacts(
        Client(_message_rows()), "f1", caller_profile_id="p-owner", caller_role="OWNER"
    )

    assert contacts == [
        {"id": "p-front", "display_name": "Chan", "role": "FRONTLINE", "staff_id": "s-front"},
        {"id": "p-front-2", "display_name": "Lee", "role": "FRONTLINE", "staff_id": "s-front-2"},
    ]
    assert "email" not in repr(contacts)


def test_send_rejects_cross_facility_recipient_without_cross_home_disclosure(monkeypatch):
    client = Client(_message_rows())
    monkeypatch.setattr(direct_messages.notifications, "push", lambda *_a, **_k: pytest.fail("must not notify"))

    with pytest.raises(direct_messages.NotFoundError, match="recipient not found"):
        direct_messages.send(
            client, "f1", sender_profile_id="p-owner", sender_role="OWNER",
            recipient_profile_id="p-foreign", body="Hello",
        )
    assert client.rows["direct_messages"] == []


def test_send_uses_authenticated_sender_and_notification_never_gets_body(monkeypatch):
    client = Client(_message_rows())
    notifications = []
    monkeypatch.setattr(
        direct_messages.notifications, "push",
        lambda *_a, **kwargs: notifications.append(kwargs) or {"id": "n1"},
    )

    result = messages_router.send_message(
        messages_router.DirectMessageCreate(recipient_profile_id="p-front", body="  synthetic hello  "),
        _ctx(client, profile_id="p-owner", role="OWNER"),
    )

    assert result["sender_profile_id"] == "p-owner"
    assert result["facility_id"] == "f1"
    assert result["body"] == "synthetic hello"
    assert notifications == [{
        "event_type": "direct_message", "title": "New message", "body": None,
        "staff_id": "s-front", "profile_id": "p-front", "related_type": "direct_message",
        "related_id": result["id"],
    }]


def test_message_create_payload_forbids_sender_or_facility_spoofing():
    with pytest.raises(ValidationError):
        messages_router.DirectMessageCreate.model_validate({
            "recipient_profile_id": "p-front", "body": "hello", "sender_profile_id": "p-owner",
        })
    with pytest.raises(ValidationError):
        messages_router.DirectMessageCreate.model_validate({
            "recipient_profile_id": "p-front", "body": "hello", "facility_id": "f2",
        })


def test_notification_failure_does_not_turn_a_committed_message_into_retryable_error(monkeypatch, caplog):
    client = Client(_message_rows())

    def fail_notification(*_args, **_kwargs):
        raise RuntimeError("notification down")

    monkeypatch.setattr(direct_messages.notifications, "push", fail_notification)
    result = direct_messages.send(
        client, "f1", sender_profile_id="p-owner", sender_role="OWNER",
        recipient_profile_id="p-front", body="No duplicate please",
    )

    assert result["id"]
    assert len(client.rows["direct_messages"]) == 1
    assert "No duplicate please" not in caplog.text


def test_list_and_mark_read_are_limited_to_message_participant_and_recipient():
    rows = _message_rows()
    rows["direct_messages"] = [
        {"id": "inbound", "facility_id": "f1", "sender_profile_id": "p-owner", "recipient_profile_id": "p-front", "body": "in", "created_at": "1", "read_at": None},
        {"id": "outbound", "facility_id": "f1", "sender_profile_id": "p-front", "recipient_profile_id": "p-owner", "body": "out", "created_at": "2", "read_at": None},
        {"id": "other", "facility_id": "f1", "sender_profile_id": "p-owner", "recipient_profile_id": "p-front-2", "body": "hidden", "created_at": "3", "read_at": None},
    ]
    client = Client(rows)

    assert [row["id"] for row in direct_messages.list_messages(client, "f1", profile_id="p-front")] == ["inbound", "outbound"]
    assert direct_messages.mark_read(client, "f1", message_id="inbound", recipient_profile_id="p-front")["id"] == "inbound"
    assert direct_messages.mark_read(client, "f1", message_id="outbound", recipient_profile_id="p-front") is None
    assert next(row for row in client.rows["direct_messages"] if row["id"] == "outbound")["read_at"] is None


def test_missing_window_is_closed_by_default_without_a_configuration_read():
    assert duty_request_window.public_window(None) == {
        "enabled": False, "opens_at": None, "closes_at": None,
        "target_start": None, "target_end": None, "status": "closed",
    }


def test_window_post_is_owner_only_and_uses_authenticated_facility(monkeypatch):
    body = windows_router.DutyRequestWindowInput(
        enabled=True,
        opens_at=datetime(2026, 10, 1, 9, tzinfo=timezone.utc),
        closes_at=datetime(2026, 10, 2, 9, tzinfo=timezone.utc),
        target_start=date(2026, 10, 3), target_end=date(2026, 10, 5),
    )
    called = []
    monkeypatch.setattr(
        windows_router.svc, "put",
        lambda client, facility_id, **kwargs: called.append((client, facility_id, kwargs)) or {
            "config_json": {"enabled": True, "opens_at": body.opens_at.isoformat(),
                            "closes_at": body.closes_at.isoformat(), "target_start": "2026-10-03",
                            "target_end": "2026-10-05"},
        },
    )

    with pytest.raises(HTTPException) as exc:
        windows_router.put_duty_window(body, _ctx(object(), role="NURSE_MGR"))
    assert exc.value.status_code == 403

    result = windows_router.put_duty_window(body, _ctx(object(), profile_id="owner", role="superintendent"))
    assert result["status"] == "open"
    assert called[0][1] == "f1"
    assert called[0][2]["created_by"] == "owner"


def test_window_publishes_only_through_atomic_rpc_with_authenticated_facility():
    calls = []

    class AtomicClient:
        def rpc(self, name, params):
            calls.append((name, params))
            return SimpleNamespace(execute=lambda: SimpleNamespace(data={
                "config_json": params["p_config_json"], "active": True, "version": 2,
            }))

        def table(self, *_args):
            pytest.fail("window publishing must never use non-atomic table writes")

    client = AtomicClient()
    row = duty_request_window.put(
        client, "f1", enabled=True,
        opens_at=datetime(2026, 10, 1, 9, tzinfo=timezone.utc),
        closes_at=datetime(2026, 10, 2, 9, tzinfo=timezone.utc),
        target_start=date(2026, 10, 3), target_end=date(2026, 10, 5),
        created_by="ignored-by-rpc",
    )
    assert row["version"] == 2
    assert len(calls) == 1
    assert calls[0][0] == "publish_duty_request_window"
    assert calls[0][1]["p_facility_id"] == "f1"
    assert "created_by" not in calls[0][1]  # DB derives it from auth.uid()


def test_window_missing_atomic_rpc_fails_closed_without_retiring_old_version():
    rows = {"facility_json_configs": [{"facility_id": "f1", "config_key": "duty_request_window",
                                      "active": True, "version": 1}]}
    client = Client(rows)
    body = windows_router.DutyRequestWindowInput(enabled=False)
    with pytest.raises(HTTPException) as exc:
        windows_router.put_duty_window(body, _ctx(client, profile_id="p-owner", role="OWNER"))
    assert exc.value.status_code == 503
    assert client.rows["facility_json_configs"][0]["active"] is True


def test_window_atomic_rpc_error_keeps_old_config_and_never_falls_back_to_two_writes():
    rows = [{"facility_id": "f1", "config_key": "duty_request_window", "active": True, "version": 1}]

    class FailingClient:
        def rpc(self, *_args, **_kwargs):
            return SimpleNamespace(execute=lambda: (_ for _ in ()).throw(RuntimeError("synthetic DB error")))

        def table(self, *_args):
            pytest.fail("window publishing must not fall back to two-step writes")

    client = FailingClient()
    with pytest.raises(RuntimeError, match="synthetic DB error"):
        duty_request_window.put(
            client, "f1", enabled=False, opens_at=None, closes_at=None,
            target_start=None, target_end=None, created_by="p-owner",
        )
    assert rows[0]["active"] is True


def test_window_enforces_timezone_and_inclusive_time_and_target_boundaries(monkeypatch):
    config = {"config_json": {
        "enabled": True,
        "opens_at": "2026-10-01T09:00:00+08:00",
        "closes_at": "2026-10-02T09:00:00+08:00",
        "target_start": "2026-10-03",
        "target_end": "2026-10-05",
    }}
    monkeypatch.setattr(duty_request_window.facility_config, "get_config", lambda *_a: config)

    duty_request_window.assert_request_allowed(
        object(), "f1", leave_type="DO", date_start=date(2026, 10, 3), date_end=date(2026, 10, 5),
        now=datetime(2026, 10, 2, 1, tzinfo=timezone.utc),  # exactly closes_at
    )
    with pytest.raises(duty_request_window.DutyRequestWindowError, match="target period"):
        duty_request_window.assert_request_allowed(
            object(), "f1", leave_type="DO", date_start=date(2026, 10, 2), date_end=date(2026, 10, 3),
            now=datetime(2026, 10, 1, 1, tzinfo=timezone.utc),
        )
    with pytest.raises(duty_request_window.DutyRequestWindowError, match="expired"):
        duty_request_window.assert_request_allowed(
            object(), "f1", leave_type="duty_request", date_start=date(2026, 10, 3), date_end=date(2026, 10, 3),
            now=datetime(2026, 10, 2, 1, 1, tzinfo=timezone.utc),
        )
    with pytest.raises(ValidationError, match="timezone"):
        windows_router.DutyRequestWindowInput(
            enabled=True, opens_at=datetime(2026, 10, 1, 9),
            closes_at=datetime(2026, 10, 2, 9, tzinfo=timezone.utc),
            target_start=date(2026, 10, 3), target_end=date(2026, 10, 3),
        )


def test_urgent_leave_is_unaffected_by_the_duty_window():
    # An urgent/sick/annual leave path must not even require a config lookup.
    duty_request_window.assert_request_allowed(
        object(), "f1", leave_type="urgent", date_start=date(2026, 10, 3), date_end=date(2026, 10, 3),
    )


def test_manager_assisted_duty_request_is_blocked_before_service_role_write(monkeypatch):
    client = Client({"staff": [{"id": "target-staff", "facility_id": "f1"}]})
    escalated = False

    def service_client():
        nonlocal escalated
        escalated = True
        return object()

    monkeypatch.setattr(leave_router, "get_service_client", service_client)
    monkeypatch.setattr(
        leave_router.window_svc, "assert_request_allowed",
        lambda *_a, **_k: (_ for _ in ()).throw(
            duty_request_window.DutyRequestWindowError("duty/day-off requests are not open (window status: closed)")
        ),
    )
    body = LeaveRequestCreate(
        staff_id="target-staff", leave_type="DO", date_start=date(2026, 10, 3), date_end=date(2026, 10, 3),
    )

    with pytest.raises(HTTPException) as exc:
        leave_router.create_request(body, _ctx(client, profile_id="manager", role="NURSE_MGR"))
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "duty_request_window_closed"
    assert not escalated


def test_unauthorized_nonself_role_cannot_create_manager_assisted_leave(monkeypatch):
    client = Client({"staff": [{"id": "target-staff", "facility_id": "f1"}]})
    escalated = False

    def service_client():
        nonlocal escalated
        escalated = True
        return object()

    monkeypatch.setattr(leave_router, "get_service_client", service_client)
    body = LeaveRequestCreate(
        staff_id="target-staff", leave_type="AL", date_start=date(2026, 10, 3), date_end=date(2026, 10, 3),
    )

    with pytest.raises(HTTPException) as exc:
        leave_router.create_request(body, _ctx(client, profile_id="hr", role="HR_AUDITOR"))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "forbidden"
    assert not escalated


def test_duty_request_rejects_code_not_in_authenticated_organisation(monkeypatch):
    client = Client({"staff": [{"id": "target-staff", "facility_id": "f1"}]})
    monkeypatch.setattr(leave_router.window_svc, "assert_request_allowed", lambda *_a, **_k: None)
    monkeypatch.setattr(leave_router.roster_svc, "get_shift_defs", lambda _db, fid: [
        SimpleNamespace(shift_type="NAAC_A") if fid == "f1" else SimpleNamespace(shift_type="OTHER")
    ])
    monkeypatch.setattr(leave_router, "get_service_client", lambda: pytest.fail("must not escalate"))

    with pytest.raises(HTTPException) as exc:
        leave_router.create_request(
            LeaveRequestCreate(staff_id="target-staff", leave_type="duty_request",
                               date_start=date(2026, 10, 3), date_end=date(2026, 10, 3),
                               requested_shift_type="SA_P"),
            _ctx(client, profile_id="owner", role="OWNER"),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "invalid_shift_code"
