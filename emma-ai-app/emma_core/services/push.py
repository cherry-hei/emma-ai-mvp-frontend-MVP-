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

Where the access token comes from (SA.4b)
-----------------------------------------
FCM HTTP v1 authenticates with an OAuth2 bearer token, and Google mints those
with a one-hour life. This module used to read one out of `FCM_ACCESS_TOKEN`,
which would have worked for the first hour after provisioning and then failed
every send afterwards with a 401 - not in `DEAD_TOKEN_ERRORS`, so every phone
would have kept its token and every notification would have sat `queued` with
nothing in the report to say why. Tokens are therefore minted here from the
service account key and cached until they expire.

`FCM_ACCESS_TOKEN` is still honoured as an override, for holding a hand-pasted
token from `gcloud auth print-access-token` while testing against a project
whose key is not on the machine. It is not a way to run this in production.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from urllib import error as urlerror, request as urlrequest

from ._common import now_iso

FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

# The one scope FCM sending needs. Narrower than cloud-platform on purpose: the
# same key is what a leaked service account file would hand over.
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

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


class AuthError(RuntimeError):
    """A credential is configured but no access token could be minted from it.

    Distinct from "not configured": the deploy has been told to send, so silence
    here would be a misconfiguration nobody is told about. `deliver()` turns this
    into a `fcm_auth_failed` report rather than `fcm_not_configured`.
    """


def is_configured() -> bool:
    """Whether a Firebase project and credential are available to send with.

    Answers from configuration alone and never mints a token - callers use this
    to decide whether push is available at all, and a network round trip (or an
    `AuthError`) is not an answer to that question.
    """
    from ..config import settings

    if getattr(settings, "fcm_access_token", "") and _project_id_setting():
        return True
    return _service_account_info() is not None


def _project_id_setting() -> str | None:
    from ..config import settings

    return getattr(settings, "fcm_project_id", "") or None


def _service_account_info() -> dict | None:
    """The service account key as a dict, or None if none is configured.

    Accepts either the JSON itself or a path to the downloaded key file: the
    first is what a container gets from a secret manager, the second what a
    developer has on disk after clicking through the Firebase console.
    """
    from ..config import settings

    raw = (getattr(settings, "fcm_service_account_json", "") or "").strip()
    if not raw:
        return None
    try:
        if raw.startswith("{"):
            return json.loads(raw)
        path = Path(raw)
        if not path.is_file():
            raise AuthError(f"FCM_SERVICE_ACCOUNT_JSON points at {raw}, which is not a file")
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuthError(f"FCM service account key is not valid JSON: {exc}") from exc


# Cached across calls because minting is an HTTPS round trip to Google and a
# notification fan-out to a whole shift would otherwise pay for one per
# recipient. google-auth owns the expiry check, including its clock-skew margin.
_cached_credentials = None


def _invalidate() -> None:
    """Drop the cached credential so the next call mints a fresh token."""
    global _cached_credentials
    _cached_credentials = None


def _minted_token(info: dict) -> tuple[str | None, str]:
    """(project_id, access_token) minted from the service account key."""
    global _cached_credentials

    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - a deploy missing its deps
        raise AuthError(
            "google-auth is required to mint FCM access tokens; it is in "
            "requirements.txt, so this image was built without installing it"
        ) from exc

    if _cached_credentials is None:
        try:
            _cached_credentials = service_account.Credentials.from_service_account_info(
                info, scopes=[FCM_SCOPE])
        except ValueError as exc:
            raise AuthError(f"FCM service account key is unusable: {exc}") from exc

    if not _cached_credentials.valid:
        try:
            _cached_credentials.refresh(Request())
        except Exception as exc:  # noqa: BLE001 - network, clock skew, revoked key
            _invalidate()
            raise AuthError(f"could not mint an FCM access token: {exc}") from exc

    # The key names the project, so provisioning does not need FCM_PROJECT_ID set
    # as well; an explicit setting still wins, for pointing a staging deploy at a
    # different project with the same key.
    return _project_id_setting() or info.get("project_id"), _cached_credentials.token


def _credentials() -> tuple[str | None, str | None]:
    """(project_id, access_token), or (None, None) when FCM is not configured.

    Read at call time rather than import time so provisioning the project does
    not need a code change - only the deploy's environment.
    """
    from ..config import settings

    override = getattr(settings, "fcm_access_token", "") or None
    if override:
        return _project_id_setting(), override

    info = _service_account_info()
    if info is None:
        return None, None
    return _minted_token(info)


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
    try:
        project_id, access_token = _credentials()
    except AuthError as exc:
        # Configured but broken. Reported separately from "not configured" so a
        # rotated-out key reads as a fault and not as "push isn't on yet".
        return {"sent": 0, "failed": 0, "revoked": 0,
                "skipped": "fcm_auth_failed", "detail": str(exc)}
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
    reauthed = False

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
        if status == 401 and not reauthed:
            # The token expired part-way through a fan-out, or was minted just
            # before a key rotation. Re-mint once and replay this device; the
            # loop must not spend a mint per remaining device, hence the flag.
            reauthed = True
            _invalidate()
            try:
                _, access_token = _credentials()
            except AuthError:
                access_token = None
            if access_token:
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
