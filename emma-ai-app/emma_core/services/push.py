"""Firebase Cloud Messaging delivery for the Staff App (spec SA.4).

SA.4 has two halves. The manager half - Server-Sent Events to the dashboard -
has worked since 31 July. This is the other half: the notification that reaches
a care worker's phone when their leave is approved while the app is closed.

What was here before was device registration and nothing else. `push_subscriptions`
collected FCM tokens and no code ever sent to one, so "staff receives push
notification on approval/rejection" was false however many tokens were stored.

The credential problem, stated plainly
--------------------------------------
Sending needs a Firebase service account, and no Firebase project exists yet.
Provisioning it is mine (confirmed by Cherry, 1 Aug) and cannot be done from
here. So this module is written to be correct the moment the credential lands
and to be honest until then:

* with no credential configured, `deliver()` returns a result saying so and
  leaves the notification row `queued`. It does not raise, and it does not mark
  anything `sent`. A row that claims it was delivered when no request left the
  building is the failure this whole module exists to prevent;
* with a credential, it posts to the FCM HTTP v1 API per device token, and a
  token FCM rejects as UNREGISTERED is revoked rather than retried forever -
  an uninstalled app otherwise leaves a token that fails on every future send.

`transport` is injectable so the send path is tested without a Firebase project:
the tests drive it with a fake that records requests and returns canned FCM
responses.
"""
from __future__ import annotations

import json
from typing import Protocol
from urllib import error as urlerror, request as urlrequest

from ._common import now_iso

FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

# FCM's answers to "this token is dead". Anything else is treated as transient
# and left alone - revoking a token because of a 500 would silently unsubscribe
# a working phone.
DEAD_TOKEN_ERRORS = {"UNREGISTERED", "INVALID_ARGUMENT", "SENDER_ID_MISMATCH"}


class Transport(Protocol):
    """Post one message to FCM. Returns (status_code, body)."""

    def __call__(self, url: str, payload: dict, token: str) -> tuple[int, dict]:
        ...


def _http_transport(url: str, payload: dict, access_token: str) -> tuple[int, dict]:
    req = urlrequest.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urlerror.HTTPError as exc:                       # 4xx/5xx from FCM
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:  # noqa: BLE001 - a non-JSON error body is still an error
            return exc.code, {}
    except Exception as exc:  # noqa: BLE001 - DNS, TLS, timeout
        return 0, {"error": {"status": "TRANSPORT_ERROR", "message": str(exc)}}


def is_configured() -> bool:
    """Whether a Firebase project and credential are available to send with."""
    return bool(_credentials()[0] and _credentials()[1])


def _credentials() -> tuple[str | None, str | None]:
    """(project_id, access_token) from the environment, or (None, None).

    Read at call time rather than import time so provisioning the project does
    not need a code change - only the deploy's environment.
    """
    from ..config import settings

    project = getattr(settings, "fcm_project_id", "") or None
    token = getattr(settings, "fcm_access_token", "") or None
    return project, token


def _tokens_for(client, facility_id: str, *, staff_id: str | None,
                profile_id: str | None) -> list[dict]:
    # SQL: select id, token from push_subscriptions
    #      where facility_id = :facility_id and revoked_at is null
    #        and (staff_id = :staff_id or profile_id = :profile_id)
    query = (client.table("push_subscriptions").select("id,token,staff_id,profile_id")
             .eq("facility_id", facility_id).is_("revoked_at", "null"))
    if staff_id:
        query = query.eq("staff_id", staff_id)
    elif profile_id:
        query = query.eq("profile_id", profile_id)
    else:
        return []
    return query.execute().data or []


def _revoke(client, subscription_id: str) -> None:
    (client.table("push_subscriptions").update({"revoked_at": now_iso()})
     .eq("id", subscription_id).execute())


def deliver(client, facility_id: str, notification: dict, *,
            transport: Transport | None = None) -> dict:
    """Push one already-persisted notification to its recipient's devices.

    Returns a report - `{"sent": n, "failed": n, "revoked": n, "skipped": reason}`
    - rather than raising, because delivery is a best effort layered on top of a
    notification that already exists in the database and is already readable in
    the app. A phone that is off must not turn an approved leave request into an
    error for the manager who approved it.
    """
    project_id, access_token = _credentials()
    if not (project_id and access_token):
        return {"sent": 0, "failed": 0, "revoked": 0,
                "skipped": "fcm_not_configured"}

    devices = _tokens_for(client, facility_id,
                          staff_id=notification.get("staff_id"),
                          profile_id=notification.get("profile_id"))
    if not devices:
        return {"sent": 0, "failed": 0, "revoked": 0, "skipped": "no_devices"}

    send: Transport = transport or _http_transport
    url = FCM_ENDPOINT.format(project_id=project_id)
    sent = failed = revoked = 0

    for device in devices:
        payload = {"message": {
            "token": device["token"],
            "notification": {
                "title": notification.get("title") or "Emma AI",
                "body": notification.get("body") or "",
            },
            # The app needs to know what to open. Sent as data rather than in the
            # visible notification so the payload can change without changing
            # what the staff member reads.
            "data": {
                "notification_id": str(notification.get("id") or ""),
                "event_type": str(notification.get("event_type") or ""),
                "related_type": str(notification.get("related_type") or ""),
                "related_id": str(notification.get("related_id") or ""),
            },
        }}
        status, body = send(url, payload, access_token)
        if 200 <= status < 300:
            sent += 1
            continue
        failed += 1
        if str((body.get("error") or {}).get("status", "")) in DEAD_TOKEN_ERRORS:
            # The app was uninstalled or the token re-issued. Left alone it fails
            # on every send from now on.
            _revoke(client, device["id"])
            revoked += 1

    if sent:
        # Only now is 'sent' true of the phone as well as of the database.
        (client.table("notifications")
         .update({"status": "sent", "sent_at": now_iso()})
         .eq("id", notification["id"]).execute())
    return {"sent": sent, "failed": failed, "revoked": revoked, "skipped": None}
