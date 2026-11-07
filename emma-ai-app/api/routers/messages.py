"""Bounded facility direct messages.

Route registration intentionally remains in ``api.main`` for the integration owner.
The database RPCs are the write authority: the API never accepts a sender, tenant,
role, unit, or read timestamp from the request body.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.permissions import normalise_role
from emma_core.services import messages as svc

router = APIRouter(tags=["messages"])


class MessageContactOut(BaseModel):
    """The deliberately minimal contact card safe to put in the composer."""

    id: UUID
    display_name: str
    role: str
    staff_id: UUID | None = None


class DirectMessageOut(BaseModel):
    """The durable direct-message row exposed by the frontend contract."""

    id: UUID
    sender_profile_id: UUID
    recipient_profile_id: UUID
    body: str
    created_at: datetime
    read_at: datetime | None = None


class DirectMessageCreate(BaseModel):
    """Client input; sender, scope, and receipt time are never client fields."""

    model_config = ConfigDict(extra="forbid")

    recipient_profile_id: UUID
    body: Annotated[str, Field(min_length=1, max_length=svc.MAX_BODY_CHARS)]
    client_message_id: UUID | None = None

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        # Preserve intentional leading/trailing whitespace in durable content, but
        # a whitespace-only row is not a message and is also rejected in SQL.
        if not value.strip():
            raise ValueError("body must not be blank")
        return value


def _chat_context(ctx: AuthCtx) -> AuthCtx:
    """Fail closed before querying when the resolved server profile is malformed.

    The database repeats this test against ``auth.uid()`` and the current staff
    row. This early check is only a safe API error, never the authorization source.
    """
    if (not ctx.facility_id or not ctx.org_id or not ctx.profile.staff_id
            or normalise_role(ctx.profile.role) is None):
        raise api_error(403, "message_profile_ineligible",
                        "This account is not eligible for direct messages.")
    return ctx


@router.get("/messages/contacts", response_model=list[MessageContactOut])
def contacts(ctx: AuthCtx = Depends(get_ctx)):
    """Return only same-facility, same-org, same-unit eligible message peers."""
    ctx = _chat_context(ctx)
    return svc.list_contacts(ctx.client)


@router.get("/messages", response_model=list[DirectMessageOut])
def list_messages(
    before: datetime | None = Query(
        default=None,
        description="Exclusive created_at cursor; results are newest first.",
    ),
    limit: int = Query(default=50, ge=1, le=svc.MAX_PAGE_SIZE),
    peer: UUID | None = Query(
        default=None,
        description="Optional peer profile id; unshared/foreign peers return no rows.",
    ),
    ctx: AuthCtx = Depends(get_ctx),
):
    """Return a bounded participant-only message page, newest first."""
    ctx = _chat_context(ctx)
    return svc.list_messages(
        ctx.client,
        facility_id=ctx.facility_id,
        profile_id=ctx.profile_id,
        before=before,
        limit=limit,
        peer_profile_id=str(peer) if peer else None,
    )


@router.post("/messages", response_model=DirectMessageOut, status_code=201)
def send_message(body: DirectMessageCreate, ctx: AuthCtx = Depends(get_ctx)):
    """Persist and return one message; optional UUID makes retries idempotent."""
    _chat_context(ctx)
    row = svc.send_message(
        ctx.client,
        recipient_profile_id=str(body.recipient_profile_id),
        body=body.body,
        client_message_id=str(body.client_message_id) if body.client_message_id else None,
    )
    if row is None:
        # A write acknowledgement without a durable row is not a success contract.
        raise api_error(500, "message_write_failed",
                        "Messages service did not return a durable message.")
    return row


@router.patch("/messages/{message_id}/read", response_model=DirectMessageOut)
def mark_message_read(message_id: UUID, ctx: AuthCtx = Depends(get_ctx)):
    """Persist a recipient-only read receipt and return the actual message row."""
    _chat_context(ctx)
    row = svc.mark_read(ctx.client, message_id=str(message_id))
    if row is None:
        # The secure RPC intentionally makes a non-recipient/foreign id indistinguishable
        # from a missing id so this route cannot become an existence oracle.
        raise api_error(404, "not_found", "message not found")
    return row
