"""RLS-scoped direct messages for the synthetic trial.

Every function receives the authenticated user's client.  This module deliberately
never imports or uses a service-role client: database RLS is part of chat's
confidentiality boundary, not a convenience that application code may bypass.
"""
from __future__ import annotations

import logging

from . import audit, notifications
from ._common import now_iso
from ..permissions import SystemRole, normalise_role


logger = logging.getLogger(__name__)

MANAGER_ROLES = frozenset({SystemRole.OWNER, SystemRole.NURSE_MGR})
FRONTLINE_ROLE = SystemRole.FRONTLINE
MAX_BODY_LENGTH = 1000


class DirectMessageError(ValueError):
    """A syntactically valid message that is not acceptable for this feature."""


class NotFoundError(DirectMessageError):
    """A recipient outside the caller's visible facility scope."""


class ForbiddenError(DirectMessageError):
    """A caller or pair that is not eligible for direct messaging."""


def _role(value) -> SystemRole | None:
    return normalise_role(value)


def _allowed_pair(sender_role, recipient_role) -> bool:
    sender, recipient = _role(sender_role), _role(recipient_role)
    return ((sender in MANAGER_ROLES and recipient is FRONTLINE_ROLE)
            or (sender is FRONTLINE_ROLE and recipient in MANAGER_ROLES))


def _profile(client, facility_id: str, profile_id: str) -> dict | None:
    """Return a minimal same-facility profile projection, never email data."""
    rows = (client.table("users_profile").select("id,role,staff_id")
            .eq("facility_id", facility_id).eq("id", profile_id).execute().data)
    return rows[0] if rows else None


def contacts(client, facility_id: str, *, caller_profile_id: str,
             caller_role: str) -> list[dict]:
    """Return only eligible, provisioned contacts in the caller's own facility."""
    role = _role(caller_role)
    if role in MANAGER_ROLES:
        permitted = {FRONTLINE_ROLE}
    elif role is FRONTLINE_ROLE:
        permitted = MANAGER_ROLES
    else:
        return []

    rows = (client.table("users_profile").select("id,role,staff_id")
            .eq("facility_id", facility_id).execute().data)
    staff_ids = [row["staff_id"] for row in rows if row.get("staff_id")]
    staff_by_id: dict[str, dict] = {}
    if staff_ids:
        staff_rows = (client.table("staff").select("id,name,name_en")
                      .eq("facility_id", facility_id).in_("id", staff_ids)
                      .execute().data)
        staff_by_id = {row["id"]: row for row in staff_rows}

    out = []
    for row in rows:
        contact_role = _role(row.get("role"))
        if row.get("id") == caller_profile_id or contact_role not in permitted:
            continue
        staff = staff_by_id.get(row.get("staff_id"), {})
        # Names come from same-facility staff profiles.  The role fallback avoids
        # exposing email and still allows an account whose staff link is pending.
        display_name = staff.get("name") or staff.get("name_en") or contact_role.value
        item = {"id": row["id"], "display_name": display_name,
                "role": contact_role.value}
        if row.get("staff_id"):
            item["staff_id"] = row["staff_id"]
        out.append(item)
    return sorted(out, key=lambda item: (item["display_name"].casefold(), item["id"]))


def list_messages(client, facility_id: str, *, profile_id: str) -> list[dict]:
    """Return only the authenticated participant's own conversation rows."""
    rows = (client.table("direct_messages")
            .select("id,sender_profile_id,recipient_profile_id,body,created_at,read_at")
            .eq("facility_id", facility_id)
            .or_(f"sender_profile_id.eq.{profile_id},recipient_profile_id.eq.{profile_id}")
            .order("created_at").execute().data)
    # RLS is authoritative.  This explicit predicate makes mocks, a future query
    # edit, or an accidental lost PostgREST filter unable to return a transcript.
    return [row for row in rows if profile_id in {
        row.get("sender_profile_id"), row.get("recipient_profile_id")
    }]


def send(client, facility_id: str, *, sender_profile_id: str, sender_role: str,
         recipient_profile_id: str, body: str) -> dict:
    """Insert a chat row using only authenticated sender/facility context.

    The endpoint never accepts sender or facility in the request payload.  This
    defense-in-depth service check also refuses a mismatched caller identity when
    called outside the route in tests or future code.
    """
    if not isinstance(body, str):
        raise DirectMessageError("body must be text")
    body = body.strip()
    if not body:
        raise DirectMessageError("body must not be blank")
    if len(body) > MAX_BODY_LENGTH:
        raise DirectMessageError(f"body must be at most {MAX_BODY_LENGTH} characters")

    sender = _profile(client, facility_id, sender_profile_id)
    if not sender or _role(sender_role) is not _role(sender.get("role")):
        raise ForbiddenError("sender is not authorised for this facility")
    recipient = _profile(client, facility_id, recipient_profile_id)
    if not recipient:
        # Do not reveal whether an otherwise valid profile ID is in another home.
        raise NotFoundError("recipient not found")
    if not _allowed_pair(sender.get("role"), recipient.get("role")):
        raise ForbiddenError("messages are only allowed between a manager and frontline staff")

    rows = (client.table("direct_messages").insert({
        "facility_id": facility_id,
        "sender_profile_id": sender_profile_id,
        "recipient_profile_id": recipient_profile_id,
        "body": body,
    }).execute().data)
    if not rows:
        raise ForbiddenError("message was not accepted")
    message = rows[0]

    # Audit only the act and relationship, never the message body.  Read events
    # are deliberately not audit rows: the message's immutable read_at is the
    # receipt and recording every view would create an unnecessary activity log.
    audit.record(
        client, facility_id=facility_id, action="create", entity_table="direct_messages",
        entity_id=message["id"], actor_profile_id=sender_profile_id,
        after={"recipient_profile_id": recipient_profile_id},
    )

    # Notification routing metadata deliberately contains no chat text.  A failed
    # notification cannot make a committed message appear retryable (and duplicate).
    recipient_role = _role(recipient.get("role"))
    try:
        notifications.push(
            client, facility_id, event_type="direct_message", title="New message", body=None,
            staff_id=recipient.get("staff_id") if recipient_role is FRONTLINE_ROLE else None,
            profile_id=recipient["id"], related_type="direct_message", related_id=message["id"],
        )
    except Exception:  # noqa: BLE001 - the chat row is authoritative
        logger.warning("direct-message notification enqueue failed")
    return message


def mark_read(client, facility_id: str, *, message_id: str,
              recipient_profile_id: str) -> dict | None:
    """Set a receipt only for the current recipient's own inbound message."""
    def own_message():
        rows = (client.table("direct_messages")
                .select("id,sender_profile_id,recipient_profile_id,body,created_at,read_at")
                .eq("facility_id", facility_id).eq("id", message_id)
                .eq("recipient_profile_id", recipient_profile_id).execute().data)
        return rows[0] if rows else None

    before = own_message()
    if not before or before.get("read_at"):
        return before

    rows = (client.table("direct_messages").update({"read_at": now_iso()})
            .eq("facility_id", facility_id).eq("id", message_id)
            .eq("recipient_profile_id", recipient_profile_id)
            .is_("read_at", "null").execute().data)
    # Another tab may have committed the immutable receipt between read/update.
    return rows[0] if rows else own_message()
