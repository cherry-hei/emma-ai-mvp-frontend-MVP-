"""Offline contract tests for the unregistered Nov 04 direct-message router."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.deps import AuthCtx
from api.routers import messages as router
from emma_core.models import Profile

SENDER = "00000000-0000-0000-0000-000000000001"
RECIPIENT = "00000000-0000-0000-0000-000000000002"
MESSAGE = "00000000-0000-0000-0000-000000000003"
CLIENT_MESSAGE = "00000000-0000-0000-0000-000000000004"
FACILITY = "00000000-0000-0000-0000-000000000010"
ORG = "00000000-0000-0000-0000-000000000011"
STAFF = "00000000-0000-0000-0000-000000000012"


def _ctx(*, role: str = "staff", staff_id: str | None = STAFF,
         facility_id: str | None = FACILITY, org_id: str | None = ORG) -> AuthCtx:
    return AuthCtx(
        token="test-token",
        client=object(),
        profile=Profile(
            id=SENDER,
            facility_id=facility_id,
            org_id=org_id,
            role=role,
            staff_id=staff_id,
        ),
    )


def _row(*, read_at: str | None = None) -> dict:
    return {
        "id": MESSAGE,
        "sender_profile_id": SENDER,
        "recipient_profile_id": RECIPIENT,
        "body": "handover complete",
        "created_at": "2026-10-31T07:00:00+00:00",
        "read_at": read_at,
    }


def test_create_input_forbids_spoofed_sender_and_enforces_bounded_nonblank_body():
    with pytest.raises(ValidationError):
        router.DirectMessageCreate(
            recipient_profile_id=RECIPIENT,
            body="x",
            sender_profile_id="forged",
        )
    with pytest.raises(ValidationError):
        router.DirectMessageCreate(recipient_profile_id=RECIPIENT, body=" \t\n ")
    with pytest.raises(ValidationError):
        router.DirectMessageCreate(
            recipient_profile_id=RECIPIENT,
            body="x" * (router.svc.MAX_BODY_CHARS + 1),
        )


def test_create_accepts_optional_uuid_idempotency_key():
    body = router.DirectMessageCreate(
        recipient_profile_id=RECIPIENT,
        body=" hello ",
        client_message_id=CLIENT_MESSAGE,
    )
    assert str(body.recipient_profile_id) == RECIPIENT
    assert str(body.client_message_id) == CLIENT_MESSAGE
    assert body.body == " hello "


def test_list_passes_bounded_page_and_optional_peer_to_service(monkeypatch):
    calls = []
    expected = [_row()]
    monkeypatch.setattr(
        router.svc,
        "list_messages",
        lambda client, **kwargs: calls.append((client, kwargs)) or expected,
    )
    before = datetime(2026, 10, 31, 7, 1, tzinfo=timezone.utc)
    ctx = _ctx()

    result = router.list_messages(before=before, limit=17,
                                  peer=UUID(RECIPIENT), ctx=ctx)

    assert result == expected
    assert calls == [(ctx.client, {
        "facility_id": FACILITY,
        "profile_id": SENDER,
        "before": before,
        "limit": 17,
        "peer_profile_id": RECIPIENT,
    })]


def test_contacts_and_send_return_only_durable_rows(monkeypatch):
    contact = {
        "id": RECIPIENT,
        "display_name": "Nurse B",
        "role": "staff",
        "staff_id": STAFF,
    }
    sent = []
    monkeypatch.setattr(router.svc, "list_contacts", lambda _client: [contact])
    monkeypatch.setattr(
        router.svc,
        "send_message",
        lambda client, **kwargs: sent.append((client, kwargs)) or _row(),
    )

    contacts = router.contacts(_ctx())
    result = router.send_message(
        router.DirectMessageCreate(
            recipient_profile_id=RECIPIENT,
            body="handover complete",
            client_message_id=CLIENT_MESSAGE,
        ),
        _ctx(),
    )

    # Response-model coercion happens when FastAPI dispatches the endpoint; a
    # direct unit call intentionally returns the service's raw durable row.
    assert contacts[0]["display_name"] == "Nurse B"
    assert result["id"] == MESSAGE
    assert sent[0][1] == {
        "recipient_profile_id": RECIPIENT,
        "body": "handover complete",
        "client_message_id": CLIENT_MESSAGE,
    }


def test_send_refuses_missing_durable_rpc_row(monkeypatch):
    monkeypatch.setattr(router.svc, "send_message", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as exc:
        router.send_message(
            router.DirectMessageCreate(recipient_profile_id=RECIPIENT, body="x"),
            _ctx(),
        )

    assert exc.value.status_code == 500
    assert exc.value.detail["code"] == "message_write_failed"


def test_mark_read_requires_durable_recipient_row_and_hides_existence(monkeypatch):
    monkeypatch.setattr(router.svc, "mark_read", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as exc:
        router.mark_message_read(UUID(MESSAGE), _ctx())

    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "not_found"


def test_malformed_or_unlinked_profile_fails_closed_before_service(monkeypatch):
    called = False

    def contacts(_client):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(router.svc, "list_contacts", contacts)
    with pytest.raises(HTTPException) as exc:
        router.contacts(_ctx(staff_id=None))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "message_profile_ineligible"
    assert not called


def test_unknown_role_fails_closed_even_if_model_is_constructed_from_stale_db_data(monkeypatch):
    # ``model_construct`` represents a DB row introduced outside the current
    # Pydantic enum. The production DB RPC repeats this check against auth.uid().
    profile = Profile.model_construct(
        id=SENDER, facility_id=FACILITY, org_id=ORG,
        role="made_up_role", staff_id=STAFF,
    )
    ctx = AuthCtx(token="test-token", client=object(), profile=profile)
    monkeypatch.setattr(router.svc, "list_contacts",
                        lambda _client: pytest.fail("service must not be called"))

    with pytest.raises(HTTPException) as exc:
        router.contacts(ctx)

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "message_profile_ineligible"
