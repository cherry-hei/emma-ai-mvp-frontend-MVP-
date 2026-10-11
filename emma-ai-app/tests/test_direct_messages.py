"""Isolated unit tests for the shared manager ↔ staff message store.

These tests use an in-memory PostgREST-shaped client.  They do not connect to a
live API, Supabase project, or execute the SQL draft.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.deps import AuthCtx
from api.routers import messages as messages_router
from emma_core.models import Profile
from emma_core.services import direct_messages


class Query:
    def __init__(self, client, table: str):
        self.client, self.table = client, table
        self.action = "select"
        self.payload = None
        self.filters: list[tuple[str, str, object]] = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self.filters.append(("in", field, tuple(values)))
        return self

    def is_(self, field, value):
        self.filters.append(("is", field, value))
        return self

    def or_(self, _expression):
        # The service repeats participant filtering after the query, intentionally
        # defending against a permissive mock or a future query edit.
        return self

    def order(self, *_args, **_kwargs):
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
            if operator == "is" and expected == "null" and row.get(field) is not None:
                return False
        return True

    def execute(self):
        rows = self.client.rows.setdefault(self.table, [])
        if self.action == "insert":
            row = deepcopy(self.payload)
            row.setdefault("id", f"{self.table}-{len(rows) + 1}")
            row.setdefault("created_at", "2026-10-11T09:00:00+00:00")
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
    def __init__(self, rows: dict[str, list[dict]]):
        self.rows = deepcopy(rows)

    def table(self, name: str):
        return Query(self, name)


def _rows():
    return {
        "users_profile": [
            {"id": "p-manager", "facility_id": "f1", "role": "OWNER", "staff_id": "s-manager"},
            {"id": "p-staff", "facility_id": "f1", "role": "FRONTLINE", "staff_id": "s-staff"},
            {"id": "p-other-staff", "facility_id": "f1", "role": "staff", "staff_id": "s-other"},
            {"id": "p-scheduler", "facility_id": "f1", "role": "SCHEDULER", "staff_id": "s-scheduler"},
            {"id": "p-foreign", "facility_id": "f2", "role": "FRONTLINE", "staff_id": "s-foreign"},
        ],
        "staff": [
            {"id": "s-manager", "facility_id": "f1", "name": "Manager Name", "name_en": "Manager Name"},
            {"id": "s-staff", "facility_id": "f1", "name": "Staff Name", "name_en": "Staff Name"},
            {"id": "s-other", "facility_id": "f1", "name": "Other Staff", "name_en": "Other Staff"},
            {"id": "s-scheduler", "facility_id": "f1", "name": "Scheduler", "name_en": "Scheduler"},
            {"id": "s-foreign", "facility_id": "f2", "name": "Foreign", "name_en": "Foreign"},
        ],
        "direct_messages": [],
        "notifications": [],
        "audit_logs": [],
    }


def _ctx(client, profile_id: str, facility_id="f1", role="FRONTLINE"):
    return AuthCtx(
        token="mock-token",
        client=client,
        profile=Profile(id=profile_id, facility_id=facility_id, role=role),
    )


def test_manager_and_staff_share_one_scoped_message_store(monkeypatch):
    client = Client(_rows())
    sent_notifications = []
    monkeypatch.setattr(
        direct_messages.notifications, "push",
        lambda *_args, **kwargs: sent_notifications.append(kwargs) or {"id": "n1"},
    )

    manager_ctx = _ctx(client, "p-manager", role="OWNER")
    staff_ctx = _ctx(client, "p-staff", role="FRONTLINE")
    manager_to_staff = messages_router.send_message(
        messages_router.DirectMessageCreate(recipient_profile_id="p-staff", body="  synthetic hello  "),
        manager_ctx,
    )
    staff_to_manager = messages_router.send_message(
        messages_router.DirectMessageCreate(recipient_profile_id="p-manager", body="synthetic reply"),
        staff_ctx,
    )

    assert manager_to_staff["sender_profile_id"] == "p-manager"
    assert manager_to_staff["facility_id"] == "f1"
    assert manager_to_staff["body"] == "synthetic hello"
    assert [row["id"] for row in messages_router.list_messages(manager_ctx)] == [
        manager_to_staff["id"], staff_to_manager["id"]
    ]
    assert [row["id"] for row in messages_router.list_messages(staff_ctx)] == [
        manager_to_staff["id"], staff_to_manager["id"]
    ]
    assert sent_notifications[0]["body"] is None
    assert sent_notifications[0]["related_id"] == manager_to_staff["id"]
    assert client.rows["audit_logs"][0]["after_json"] == {"recipient_profile_id": "p-staff"}
    assert "synthetic hello" not in repr(client.rows["audit_logs"])


def test_contacts_use_same_facility_profiles_and_genuine_staff_names():
    client = Client(_rows())

    assert direct_messages.contacts(
        client, "f1", caller_profile_id="p-manager", caller_role="OWNER"
    ) == [
        {"id": "p-other-staff", "display_name": "Other Staff", "role": "FRONTLINE", "staff_id": "s-other"},
        {"id": "p-staff", "display_name": "Staff Name", "role": "FRONTLINE", "staff_id": "s-staff"},
    ]
    assert direct_messages.contacts(
        client, "f1", caller_profile_id="p-staff", caller_role="FRONTLINE"
    ) == [{"id": "p-manager", "display_name": "Manager Name", "role": "OWNER", "staff_id": "s-manager"}]


def test_cross_tenant_recipient_is_not_found_and_creates_nothing():
    client = Client(_rows())
    with pytest.raises(HTTPException) as raised:
        messages_router.send_message(
            messages_router.DirectMessageCreate(recipient_profile_id="p-foreign", body="nope"),
            _ctx(client, "p-manager", role="OWNER"),
        )

    assert raised.value.status_code == 404
    assert raised.value.detail["code"] == "recipient_not_found"
    assert client.rows["direct_messages"] == []


@pytest.mark.parametrize(
    ("sender_id", "sender_role", "recipient_id"),
    [
        ("p-scheduler", "SCHEDULER", "p-staff"),
        ("p-staff", "FRONTLINE", "p-other-staff"),
    ],
)
def test_ineligible_or_unauthorised_pairs_are_denied(sender_id, sender_role, recipient_id):
    client = Client(_rows())
    with pytest.raises(HTTPException) as raised:
        messages_router.send_message(
            messages_router.DirectMessageCreate(recipient_profile_id=recipient_id, body="not allowed"),
            _ctx(client, sender_id, role=sender_role),
        )

    assert raised.value.status_code == 403
    assert client.rows["direct_messages"] == []


def test_only_recipient_can_create_read_receipt_and_sender_sees_it(monkeypatch):
    client = Client(_rows())
    monkeypatch.setattr(direct_messages.notifications, "push", lambda *_args, **_kwargs: {"id": "n1"})
    manager_ctx = _ctx(client, "p-manager", role="OWNER")
    staff_ctx = _ctx(client, "p-staff", role="FRONTLINE")
    sent = messages_router.send_message(
        messages_router.DirectMessageCreate(recipient_profile_id="p-staff", body="please read"),
        manager_ctx,
    )

    with pytest.raises(HTTPException) as raised:
        messages_router.read_message(sent["id"], manager_ctx)
    assert raised.value.status_code == 404

    receipt = messages_router.read_message(sent["id"], staff_ctx)
    assert receipt["read_at"]
    assert messages_router.list_messages(manager_ctx)[0]["read_at"] == receipt["read_at"]
    assert client.rows["audit_logs"] and len(client.rows["audit_logs"]) == 1

    monkeypatch.setattr(direct_messages, "now_iso", lambda: "2030-01-01T00:00:00+00:00")
    repeated = messages_router.read_message(sent["id"], staff_ctx)
    assert repeated["read_at"] == receipt["read_at"]
    assert len(client.rows["audit_logs"]) == 1


def test_body_limit_and_sender_context_cannot_be_spoofed():
    client = Client(_rows())
    with pytest.raises(ValidationError):
        messages_router.DirectMessageCreate(recipient_profile_id="p-staff", body="x" * 1001)

    with pytest.raises(direct_messages.ForbiddenError):
        direct_messages.send(
            client, "f1", sender_profile_id="p-manager", sender_role="FRONTLINE",
            recipient_profile_id="p-staff", body="mismatched context",
        )
