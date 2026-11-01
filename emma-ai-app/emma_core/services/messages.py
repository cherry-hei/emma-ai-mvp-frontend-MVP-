"""Direct-message persistence through the caller's authenticated Supabase client.

``send_direct_message`` and ``mark_direct_message_read`` are database transactions
which derive the profile from ``auth.uid()``. This service deliberately does not
create or use a service-role client.
"""
from __future__ import annotations

from datetime import datetime

MAX_BODY_CHARS = 4_000
MAX_PAGE_SIZE = 100

_MESSAGE_FIELDS = (
    "id,sender_profile_id,recipient_profile_id,body,created_at,read_at"
)


def _one(rows) -> dict | None:
    """Return exactly one RPC row; never manufacture a confirmation response."""
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return None
    return rows[0]


def list_contacts(client) -> list[dict]:
    """Call the DB-scoped directory RPC; no profiles are read in application code."""
    rows = client.rpc("list_direct_message_contacts", {}).execute().data
    return rows if isinstance(rows, list) else []


def list_messages(
    client,
    *,
    facility_id: str,
    profile_id: str,
    before: datetime | None,
    limit: int,
    peer_profile_id: str | None = None,
) -> list[dict]:
    """Read a bounded page through participant RLS, newest first.

    The explicit facility/profile predicates keep the API query narrow; table RLS
    repeats the participant and eligible-profile checks if either predicate is
    accidentally removed later.
    """
    query = (client.table("direct_messages").select(_MESSAGE_FIELDS)
             .eq("facility_id", facility_id))
    if peer_profile_id:
        query = query.or_(
            "and(sender_profile_id.eq.%s,recipient_profile_id.eq.%s),"
            "and(sender_profile_id.eq.%s,recipient_profile_id.eq.%s)" % (
                profile_id, peer_profile_id, peer_profile_id, profile_id,
            )
        )
    else:
        query = query.or_(
            "sender_profile_id.eq.%s,recipient_profile_id.eq.%s" % (
                profile_id, profile_id,
            )
        )
    if before is not None:
        query = query.lt("created_at", before.isoformat())
    rows = query.order("created_at", desc=True).limit(limit).execute().data
    return rows if isinstance(rows, list) else []


def send_message(
    client,
    *,
    recipient_profile_id: str,
    body: str,
    client_message_id: str | None = None,
) -> dict | None:
    """Create or retry one message atomically and return its durable DB row."""
    rows = client.rpc("send_direct_message", {
        "p_recipient_profile_id": recipient_profile_id,
        "p_body": body,
        "p_client_message_id": client_message_id,
    }).execute().data
    return _one(rows)


def mark_read(client, *, message_id: str) -> dict | None:
    """Set read_at once for the authenticated recipient, returning the real row."""
    rows = client.rpc("mark_direct_message_read", {
        "p_message_id": message_id,
    }).execute().data
    return _one(rows)
