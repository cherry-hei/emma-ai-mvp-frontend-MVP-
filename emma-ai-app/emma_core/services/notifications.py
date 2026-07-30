"""In-app / email / WhatsApp notification fan-out (spec 4.4).

`push` writes the record and marks it sent for in-app delivery, which is the
only channel wired end-to-end. Email and WhatsApp rows are persisted as
`queued` - a delivery worker owns them; nothing here pretends they were sent.
"""
from __future__ import annotations

from ._common import now_iso

IN_APP = "in_app"


def push(client, facility_id: str, *, event_type: str, title: str,
         body: str | None = None, staff_id: str | None = None,
         profile_id: str | None = None, channel: str = IN_APP,
         related_type: str | None = None, related_id: str | None = None) -> dict:
    sent = channel == IN_APP
    # SQL: insert into notifications
    #        (facility_id, staff_id, profile_id, channel, event_type, title, body,
    #         related_type, related_id, status, sent_at)
    #      values (:facility_id, :staff_id, :profile_id, :channel, :event_type, :title,
    #              :body, :related_type, :related_id,
    #              case when :sent then 'sent' else 'queued' end,
    #              case when :sent then now() end)
    #      returning *
    return client.table("notifications").insert({
        "facility_id": facility_id, "staff_id": staff_id, "profile_id": profile_id,
        "channel": channel, "event_type": event_type, "title": title, "body": body,
        "related_type": related_type, "related_id": related_id,
        "status": "sent" if sent else "queued",
        "sent_at": now_iso() if sent else None,
    }).execute().data[0]


def list_for(client, facility_id: str, *, staff_id: str | None = None,
             profile_id: str | None = None, unread_only: bool = False,
             limit: int = 30) -> list[dict]:
    # SQL: select * from notifications
    #      where facility_id = :facility_id
    #        [and staff_id = :staff_id]        -- when staff_id is given
    #        [and profile_id = :profile_id]    -- when profile_id is given
    #        [and status <> 'read']            -- when unread_only
    #      order by created_at desc
    #      limit :limit
    q = client.table("notifications").select("*").eq("facility_id", facility_id)
    if staff_id:
        q = q.eq("staff_id", staff_id)
    if profile_id:
        q = q.eq("profile_id", profile_id)
    if unread_only:
        q = q.neq("status", "read")
    return q.order("created_at", desc=True).limit(limit).execute().data


def mark_read(client, facility_id: str, notification_id: str) -> dict | None:
    # SQL: update notifications
    #      set status = 'read', read_at = now()
    #      where facility_id = :facility_id and id = :notification_id
    #      returning *
    rows = (client.table("notifications")
            .update({"status": "read", "read_at": now_iso()})
            .eq("facility_id", facility_id).eq("id", notification_id).execute().data)
    return rows[0] if rows else None
