"""RLS-scoped direct messages for the synthetic trial.

The client supplied to every function is the authenticated user's client.  This
module deliberately never uses ``get_service_client``: RLS is part of chat's
security boundary, not just a database convenience.
"""
from __future__ import annotations

import logging

from . import notifications
from ._common import now_iso
from ..permissions import SystemRole, normalise_role


logger = logging.getLogger(__name__)

MANAGER_ROLES = frozenset({SystemRole.OWNER, SystemRole.NURSE_MGR})
FRONTLINE_ROLE = SystemRole.FRONTLINE
MAX_BODY_LENGTH = 1000


class DirectMessageError(ValueError):
    pass


class NotFoundError(DirectMessageError):
    pass


class ForbiddenError(DirectMessageError):
    pass


def _role(value) -> SystemRole | None:
    return normalise_role(value)


def _allowed_pair(sender_role, recipient_role) -> bool:
    sender, recipient = _role(sender_role), _role(recipient_role)
    return ((sender in MANAGER_ROLES and recipient is FRONTLINE_ROLE)
            or (sender is FRONTLINE_ROLE and recipient in MANAGER_ROLES))


def _profile(client, facility_id: str, profile_id: str) -> dict | None:
    rows = (client.table("users_profile").select("id,role,staff_id")
            .eq("facility_id", facility_id).eq("id", profile_id).execute().data)
    return rows[0] if rows else None


def contacts(client, facility_id: str, *, caller_profile_id: str,
             caller_role: str) -> list[dict]:
    """Return only permitted same-home contacts; email never leaves the API."""
    role = _role(caller_role)
    if role in MANAGER_ROLES:
        permitted = FRONTLINE_ROLE
    elif role is FRONTLINE_ROLE:
        permitted = MANAGER_ROLES
    else:
        return []
    rows = (client.table("users_profile").select("id,role,staff_id")
            .eq("facility_id", facility_id).execute().data)
    # `users_profile` has no name columns.  Do a same-facility, ID-bounded
    # lookup rather than relying on a PostgREST embed that an RLS policy may
    # suppress.  The selected projection deliberately excludes staff email and
    # other personal fields not needed by the contact picker.
    staff_ids = [row["staff_id"] for row in rows if row.get("staff_id")]
    staff_by_id = {}
    if staff_ids:
        staff_rows = (client.table("staff").select("id,name,name_en")
                      .eq("facility_id", facility_id).in_("id", staff_ids)
                      .execute().data)
        staff_by_id = {row["id"]: row for row in staff_rows}
    out = []
    for row in rows:
        if row.get("id") == caller_profile_id or _role(row.get("role")) not in (
            permitted if isinstance(permitted, frozenset) else {permitted}
        ):
            continue
        staff = staff_by_id.get(row.get("staff_id"), {})
        display_name = (staff.get("name") or staff.get("name_en")
                        or _role(row.get("role")).value)
        item = {"id": row["id"], "display_name": display_name,
                "role": _role(row.get("role")).value}
        if row.get("staff_id"):
            item["staff_id"] = row["staff_id"]
        out.append(item)
    return sorted(out, key=lambda item: (item["display_name"].casefold(), item["id"]))


def list_messages(client, facility_id: str, *, profile_id: str) -> list[dict]:
    """RLS limits this to sender-or-recipient rows even if the query is altered."""
    rows = (client.table("direct_messages")
            .select("id,sender_profile_id,recipient_profile_id,body,created_at,read_at")
            .eq("facility_id", facility_id)
            .or_(f"sender_profile_id.eq.{profile_id},recipient_profile_id.eq.{profile_id}")
            .order("created_at").execute().data)
    # SQL RLS is authoritative. Keeping this second predicate means a faulty
    # mock, future client change, or accidental removal of the PostgREST `or_`
    # cannot turn an endpoint response into a facility transcript.
    return [row for row in rows if profile_id in {
        row.get("sender_profile_id"), row.get("recipient_profile_id")
    }]


def send(client, facility_id: str, *, sender_profile_id: str, sender_role: str,
         recipient_profile_id: str, body: str) -> dict:
    if not isinstance(body, str):
        raise DirectMessageError("body must be text")
    if not body.strip():
        raise DirectMessageError("body must not be blank")
    if len(body) > MAX_BODY_LENGTH:
        raise DirectMessageError(f"body must be at most {MAX_BODY_LENGTH} characters")
    recipient = _profile(client, facility_id, recipient_profile_id)
    if not recipient:
        # Do not reveal whether the UUID belongs to another facility.
        raise NotFoundError("recipient not found")
    if not _allowed_pair(sender_role, recipient.get("role")):
        raise ForbiddenError("messages are only allowed between a manager and frontline staff")
    row = (client.table("direct_messages").insert({
        "facility_id": facility_id,
        "sender_profile_id": sender_profile_id,
        "recipient_profile_id": recipient_profile_id,
        "body": body.strip(),
    }).execute().data)
    if not row:
        raise ForbiddenError("message was not accepted")
    message = row[0]
    # Notification has no chat text.  Staff PWA routes by staff_id while the
    # manager console can route by profile_id; a linked frontline profile gets both.
    recipient_role = _role(recipient.get("role"))
    try:
        notifications.push(
            client, facility_id, event_type="direct_message",
            title="New message", body=None,
            staff_id=recipient.get("staff_id") if recipient_role is FRONTLINE_ROLE else None,
            profile_id=recipient["id"], related_type="direct_message",
            related_id=message["id"],
        )
    except Exception:  # noqa: BLE001 - the committed chat row is authoritative
        # Do not log `body`, and do not turn a successful insert into a 5xx: the
        # polling client can already retrieve the message and would otherwise
        # retry and create a duplicate.
        logger.warning("direct-message notification enqueue failed")
    return message


def mark_read(client, facility_id: str, *, message_id: str,
              recipient_profile_id: str) -> dict | None:
    """The API sends only read_at; SQL trigger rejects all other edits."""
    rows = (client.table("direct_messages").update({"read_at": now_iso()})
            .eq("facility_id", facility_id).eq("id", message_id)
            .eq("recipient_profile_id", recipient_profile_id).execute().data)
    return rows[0] if rows else None
