"""Authenticated, same-facility manager ↔ frontline direct messages.

This is a review-only synthetic-trial feature.  Existing notification and
replacement-offer flows remain separate resources and are not reused as chat.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.services import direct_messages as svc

router = APIRouter(tags=["messages"])


class DirectMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_profile_id: str
    body: str = Field(min_length=1, max_length=svc.MAX_BODY_LENGTH)


@router.get("/messages/contacts")
def list_contacts(ctx: AuthCtx = Depends(get_ctx)):
    return svc.contacts(
        ctx.client, ctx.facility_id, caller_profile_id=ctx.profile_id,
        caller_role=ctx.profile.role,
    )


@router.get("/messages")
def list_messages(ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_messages(ctx.client, ctx.facility_id, profile_id=ctx.profile_id)


@router.post("/messages", status_code=201)
def send_message(body: DirectMessageCreate, ctx: AuthCtx = Depends(get_ctx)):
    """Sender and facility derive solely from the authenticated context."""
    try:
        return svc.send(
            ctx.client, ctx.facility_id, sender_profile_id=ctx.profile_id,
            sender_role=ctx.profile.role,
            recipient_profile_id=body.recipient_profile_id, body=body.body,
        )
    except svc.NotFoundError as exc:
        raise api_error(404, "recipient_not_found", "recipient not found") from exc
    except svc.ForbiddenError as exc:
        raise api_error(403, "forbidden", str(exc)) from exc
    except svc.DirectMessageError as exc:
        raise api_error(422, "invalid_message", str(exc)) from exc


@router.patch("/messages/{message_id}/read")
def read_message(message_id: str, ctx: AuthCtx = Depends(get_ctx)):
    row = svc.mark_read(
        ctx.client, ctx.facility_id, message_id=message_id,
        recipient_profile_id=ctx.profile_id,
    )
    if not row:
        # Sender-only callers receive the same response as a missing UUID.
        raise api_error(404, "not_found", "message not found")
    return row
