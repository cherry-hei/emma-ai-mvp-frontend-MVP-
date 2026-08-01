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
    return _delivered(client, facility_id, _record(
        client, facility_id, event_type=event_type, title=title, body=body,
        staff_id=staff_id, profile_id=profile_id, channel=channel, sent=sent,
        related_type=related_type, related_id=related_id))


def _record(client, facility_id: str, *, event_type: str, title: str,
            body: str | None, staff_id: str | None, profile_id: str | None,
            channel: str, sent: bool, related_type: str | None,
            related_id: str | None) -> dict:
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


def _delivered(client, facility_id: str, row: dict) -> dict:
    """Try the recipient's phone as well, if FCM has been provisioned (SA.4).

    The row is written first and returned whatever happens here. In-app delivery
    is the guarantee - the notification is in the list the moment the row
    exists - and push is the extra that reaches someone who does not have the
    app open. Ordering it the other way would make a failed push able to lose a
    notification the app could have shown.

    While no Firebase project exists this is one dictionary lookup and a return;
    `push.deliver` checks its credentials before touching the database.
    """
    from . import push

    try:
        push.deliver(client, facility_id, row)
    except Exception:  # noqa: BLE001 - see docstring
        pass
    return row


def _profiles_where(client, facility_id: str, predicate) -> list[dict]:
    # SQL: select id, role from users_profile where facility_id = :facility_id
    rows = (client.table("users_profile").select("id,role")
            .eq("facility_id", facility_id).execute().data)
    return [r for r in rows if predicate(r.get("role"))]


def approver_profiles(client, facility_id: str, feature) -> list[dict]:
    """Profiles in this facility whose role may act on `feature`.

    Resolved through the permission matrix rather than a hard-coded role list:
    `users_profile.role` still holds legacy spellings ('superintendent', 'admin')
    alongside the seven canonical ones, and `can_recommend` already knows how to
    read both. A literal list here would silently stop notifying whichever
    generation of spelling it was not written against.
    """
    from ..permissions import can_recommend           # local: avoids a cycle

    return _profiles_where(client, facility_id,
                           lambda role: can_recommend(role, feature))


def responder_profiles(client, facility_id: str, feature) -> list[dict]:
    """Profiles who can *act on* `feature` - the F and E grades.

    Distinct from `approver_profiles`, which is F and R. The difference matters
    for anything that is work rather than a decision: nobody "recommends" a
    response to a missed medication round. On `task_codes` the recommend set is
    OWNER alone, while the people who would actually re-assign the task are the
    nursing officer and the clerk - both E. Fanning operational alerts out
    through the approval predicate would deliver them to exactly one person, and
    not the one holding the ward.
    """
    from ..permissions import can_write               # local: avoids a cycle

    return _profiles_where(client, facility_id,
                           lambda role: can_write(role, feature))


def push_to_approvers(client, facility_id: str, feature, *, event_type: str,
                      title: str, body: str | None = None,
                      related_type: str | None = None,
                      related_id: str | None = None) -> list[dict]:
    """Fan one event out to everyone who can act on it (spec SA.1, SA.6).

    Recommenders are included, not just the final approver: the RBAC definition
    makes first-pass review a real step, and a reviewer who is never told a
    request arrived cannot perform it.
    """
    return _fan_out(client, facility_id,
                    approver_profiles(client, facility_id, feature),
                    event_type=event_type, title=title, body=body,
                    related_type=related_type, related_id=related_id)


def push_to_responders(client, facility_id: str, feature, *, event_type: str,
                       title: str, body: str | None = None,
                       related_type: str | None = None,
                       related_id: str | None = None) -> list[dict]:
    """Fan one operational event out to everyone who can act on it (spec SA.3)."""
    return _fan_out(client, facility_id,
                    responder_profiles(client, facility_id, feature),
                    event_type=event_type, title=title, body=body,
                    related_type=related_type, related_id=related_id)


def _fan_out(client, facility_id: str, profiles: list[dict], **kwargs) -> list[dict]:
    return [
        push(client, facility_id, profile_id=profile["id"], **kwargs)
        for profile in profiles
    ]


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


def register_device(client, facility_id: str, *, token: str, platform: str = "web",
                    user_agent: str | None = None, staff_id: str | None = None,
                    profile_id: str | None = None) -> dict:
    """Register or refresh one device's push token (spec SA.4).

    Upsert on the token, not insert: a PWA re-registers on every launch, and a
    fresh row each time would mean one notification per launch since install.
    Re-registering also clears `revoked_at` - the same device coming back is a
    live subscription again, not a resurrection that needs a second row.
    """
    row = {
        "facility_id": facility_id, "staff_id": staff_id, "profile_id": profile_id,
        "platform": platform, "token": token, "user_agent": user_agent,
        "last_seen_at": now_iso(), "revoked_at": None,
    }
    # SQL: insert into push_subscriptions (...) values (...)
    #      on conflict (token) do update set
    #        facility_id = excluded.facility_id, staff_id = excluded.staff_id,
    #        profile_id = excluded.profile_id, platform = excluded.platform,
    #        user_agent = excluded.user_agent, last_seen_at = now(),
    #        revoked_at = null
    #      returning *
    return client.table("push_subscriptions").upsert(
        row, on_conflict="token").execute().data[0]


def since(client, facility_id: str, *, after_iso: str,
          profile_id: str | None = None, staff_id: str | None = None,
          limit: int = 50) -> list[dict]:
    """Notifications created strictly after `after_iso`, oldest first.

    The SSE stream's page query. Oldest first because the client replays them in
    order and keeps the last `created_at` as its cursor; newest-first would make
    that cursor skip everything in between.
    """
    # SQL: select * from notifications
    #      where facility_id = :facility_id and created_at > :after_iso
    #        [and profile_id = :profile_id] [and staff_id = :staff_id]
    #      order by created_at limit :limit
    query = (client.table("notifications").select("*")
             .eq("facility_id", facility_id).gt("created_at", after_iso))
    if profile_id:
        query = query.eq("profile_id", profile_id)
    if staff_id:
        query = query.eq("staff_id", staff_id)
    return query.order("created_at").limit(limit).execute().data


def mark_read(client, facility_id: str, notification_id: str) -> dict | None:
    # SQL: update notifications
    #      set status = 'read', read_at = now()
    #      where facility_id = :facility_id and id = :notification_id
    #      returning *
    rows = (client.table("notifications")
            .update({"status": "read", "read_at": now_iso()})
            .eq("facility_id", facility_id).eq("id", notification_id).execute().data)
    return rows[0] if rows else None
