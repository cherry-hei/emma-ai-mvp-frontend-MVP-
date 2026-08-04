"""FCM delivery for the Staff App - MVP SA.4, second half.

The manager's SSE stream has worked since 31 July. This is the half that was
missing: "staff receives push notification on approval/rejection". Device
registration existed and nothing ever sent to a registered device, so the
acceptance criterion was false however many tokens were in the table.

No Firebase project exists yet - provisioning it is Kien's, confirmed by Cherry
on 1 Aug - so the transport is injected and these tests drive it with a fake.
The behaviour worth pinning is what happens at the edges: no credential, a dead
token, and a failure that must not propagate into whatever triggered it.
"""
from __future__ import annotations

import json
from collections import defaultdict

import pytest

from emma_core.services import notifications as notify
from emma_core.services import push


class _Query:
    def __init__(self, store, table):
        self.store, self.name = store, table
        self.filters, self.payload, self.mode = [], None, "select"
        self.any_of = None

    def select(self, *_a, **_k):
        return self

    def insert(self, payload, **_k):
        self.mode, self.payload = "insert", payload
        return self

    def update(self, payload, **_k):
        self.mode, self.payload = "update", payload
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def is_(self, col, _val):
        self.filters.append((col, None))
        return self

    def in_(self, col, vals):
        self.any_of = (col, list(vals))
        return self

    def _match(self, row):
        col_vals = getattr(self, "any_of", None)
        if col_vals and row.get(col_vals[0]) not in col_vals[1]:
            return False
        return all(row.get(col) == val for col, val in self.filters)

    def execute(self):
        rows = self.store[self.name]
        if self.mode == "insert":
            made = {"id": f"{self.name}-{len(rows) + 1}", **self.payload}
            rows.append(made)
            return type("R", (), {"data": [made]})()
        hit = [r for r in rows if self._match(r)]
        if self.mode == "update":
            for row in hit:
                row.update(self.payload)
        return type("R", (), {"data": hit})()


class _DB:
    def __init__(self, **tables):
        self.store = defaultdict(list)
        for name, rows in tables.items():
            self.store[name].extend(rows)

    def table(self, name):
        return _Query(self.store, name)


def _device(token="tok-1", **extra):
    return {"id": f"sub-{token}", "facility_id": "f1", "staff_id": "s1",
            "profile_id": None, "token": token, "revoked_at": None, **extra}


def _note(**extra):
    return {"id": "n1", "facility_id": "f1", "staff_id": "s1", "profile_id": None,
            "title": "Leave approved", "body": "3 Aug", "event_type": "leave_decided",
            "related_type": "leave_request", "related_id": "lr-1",
            "status": "queued", **extra}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(push, "_credentials", lambda: ("emma-test", "ya29.token"))


@pytest.fixture(autouse=True)
def _no_cached_credential():
    """A token cached by one test must not be reused by the next."""
    push._invalidate()
    yield
    push._invalidate()


@pytest.fixture
def fcm_settings(monkeypatch):
    """Point the FCM settings wherever a test needs them."""
    from emma_core.config import settings

    def _set(**values):
        for field in ("fcm_service_account_json", "fcm_project_id", "fcm_access_token"):
            monkeypatch.setattr(settings, field, values.get(field, ""), raising=False)

    return _set


KEY = {"type": "service_account", "project_id": "emma-naac",
       "client_email": "push@emma-naac.iam.gserviceaccount.com",
       "private_key": "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n"}


class _FakeCredentials:
    """Stands in for google.oauth2.service_account.Credentials.

    Counts refreshes, because "how many times did we mint?" is the behaviour
    under test - a mint per recipient would be a round trip to Google for every
    phone on a shift.
    """

    instances = 0
    refreshes = 0

    def __init__(self, info, scopes):
        self.info, self.scopes = info, scopes
        self.token, self.valid = None, False
        type(self).instances += 1

    @classmethod
    def from_service_account_info(cls, info, scopes):
        return cls(info, scopes)

    def refresh(self, _request):
        type(self).refreshes += 1
        self.token, self.valid = f"ya29.minted-{type(self).refreshes}", True


@pytest.fixture
def fake_google(monkeypatch):
    """Swap google-auth's signing for a counter. Real minting is an HTTPS round
    trip to Google against a project that does not exist yet."""
    _FakeCredentials.instances = _FakeCredentials.refreshes = 0
    monkeypatch.setattr("google.oauth2.service_account.Credentials", _FakeCredentials)
    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: object())
    return _FakeCredentials


class _Fake:
    """Records what was posted; answers with whatever it was told to."""

    def __init__(self, *responses):
        self.responses = list(responses) or [(200, {})]
        self.calls = []

    def __call__(self, url, payload, token):
        self.calls.append({"url": url, "payload": payload, "token": token})
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


# ── no credential: honest, not optimistic ───────────────────────────────────
def test_without_a_firebase_project_nothing_is_claimed_as_sent(monkeypatch):
    """The whole point of this module. A row saying 'sent' when no request left
    the building is worse than a row saying 'queued'."""
    monkeypatch.setattr(push, "_credentials", lambda: (None, None))
    db = _DB(push_subscriptions=[_device()], notifications=[_note()])

    report = push.deliver(db, "f1", _note())

    assert report["skipped"] == "fcm_not_configured"
    assert report["sent"] == 0
    assert db.store["notifications"][0]["status"] == "queued"


def test_no_credential_does_not_even_query_for_devices(monkeypatch):
    """Called on every notification, including manager fan-outs. Until FCM is
    provisioned it must not add a query per recipient to every write."""
    monkeypatch.setattr(push, "_credentials", lambda: (None, None))

    class _Explode(_DB):
        def table(self, name):
            raise AssertionError(f"queried {name} with no credential")

    assert push.deliver(_Explode(), "f1", _note())["skipped"] == "fcm_not_configured"


# ── the send path ───────────────────────────────────────────────────────────
def test_a_registered_device_is_sent_the_notification(configured):
    db = _DB(push_subscriptions=[_device()], notifications=[_note()])
    transport = _Fake((200, {"name": "projects/emma-test/messages/1"}))

    report = push.deliver(db, "f1", _note(), transport=transport)

    assert report["sent"] == 1 and report["failed"] == 0
    message = transport.calls[0]["payload"]["message"]
    assert message["token"] == "tok-1"
    assert message["notification"]["title"] == "Leave approved"
    # The app has to know what to open when the notification is tapped.
    assert message["data"]["related_id"] == "lr-1"
    assert "emma-test" in transport.calls[0]["url"]
    assert db.store["notifications"][0]["status"] == "sent"


def test_every_device_the_person_registered_is_sent_to(configured):
    db = _DB(push_subscriptions=[_device("tok-1"), _device("tok-2")],
             notifications=[_note()])
    transport = _Fake((200, {}))
    assert push.deliver(db, "f1", _note(), transport=transport)["sent"] == 2


def test_another_persons_device_is_not_sent_to(configured):
    db = _DB(push_subscriptions=[_device("tok-mine"),
                                 _device("tok-theirs", staff_id="s2")],
             notifications=[_note()])
    transport = _Fake((200, {}))
    push.deliver(db, "f1", _note(), transport=transport)
    assert [c["payload"]["message"]["token"] for c in transport.calls] == ["tok-mine"]


def test_a_revoked_device_is_not_sent_to(configured):
    db = _DB(push_subscriptions=[_device("tok-old", revoked_at="2026-07-01")],
             notifications=[_note()])
    transport = _Fake((200, {}))
    report = push.deliver(db, "f1", _note(), transport=transport)
    assert report["skipped"] == "no_devices"
    assert transport.calls == []


# ── dead tokens ─────────────────────────────────────────────────────────────
def test_an_uninstalled_app_has_its_token_revoked(configured):
    """Left alone, an UNREGISTERED token fails on every send for ever."""
    db = _DB(push_subscriptions=[_device()], notifications=[_note()])
    transport = _Fake((404, {"error": {"status": "UNREGISTERED"}}))

    report = push.deliver(db, "f1", _note(), transport=transport)

    assert (report["sent"], report["failed"], report["revoked"]) == (0, 1, 1)
    assert db.store["push_subscriptions"][0]["revoked_at"]


def test_a_transient_failure_keeps_the_token(configured):
    """Revoking on a 503 would silently unsubscribe a working phone."""
    db = _DB(push_subscriptions=[_device()], notifications=[_note()])
    transport = _Fake((503, {"error": {"status": "UNAVAILABLE"}}))

    report = push.deliver(db, "f1", _note(), transport=transport)

    assert (report["failed"], report["revoked"]) == (1, 0)
    assert db.store["push_subscriptions"][0]["revoked_at"] is None
    assert db.store["notifications"][0]["status"] == "queued"


def test_one_dead_device_does_not_stop_the_others(configured):
    db = _DB(push_subscriptions=[_device("dead"), _device("live")],
             notifications=[_note()])
    transport = _Fake((404, {"error": {"status": "UNREGISTERED"}}), (200, {}))

    report = push.deliver(db, "f1", _note(), transport=transport)

    assert (report["sent"], report["revoked"]) == (1, 1)
    assert db.store["notifications"][0]["status"] == "sent"


# ── minting the access token (SA.4b) ────────────────────────────────────────
# The bug these cover: the token used to come from FCM_ACCESS_TOKEN, and Google
# expires those after an hour. Push would have worked on the day it was
# provisioned and been silently dead every day after.
def test_the_token_is_minted_from_the_service_account_key(fcm_settings, fake_google):
    fcm_settings(fcm_service_account_json=json.dumps(KEY))

    project_id, token = push._credentials()

    assert token == "ya29.minted-1"
    # The key names its own project; requiring FCM_PROJECT_ID as well is a second
    # setting to get wrong.
    assert project_id == "emma-naac"
    assert fake_google.refreshes == 1


def test_the_key_may_be_a_path_to_the_downloaded_file(fcm_settings, fake_google, tmp_path):
    """What a developer has after clicking through the Firebase console."""
    key_file = tmp_path / "emma-fcm.json"
    key_file.write_text(json.dumps(KEY), encoding="utf-8")
    fcm_settings(fcm_service_account_json=str(key_file))

    assert push._credentials() == ("emma-naac", "ya29.minted-1")


def test_a_valid_token_is_reused_rather_than_reminted(fcm_settings, fake_google):
    """One notification to a ward is one fan-out. Minting per recipient would be
    an HTTPS round trip to Google per phone."""
    fcm_settings(fcm_service_account_json=json.dumps(KEY))

    for _ in range(5):
        push._credentials()

    assert fake_google.refreshes == 1
    assert fake_google.instances == 1


def test_an_expired_token_is_reminted(fcm_settings, fake_google):
    fcm_settings(fcm_service_account_json=json.dumps(KEY))
    push._credentials()

    push._cached_credentials.valid = False          # an hour has passed
    _, token = push._credentials()

    assert token == "ya29.minted-2"
    assert fake_google.refreshes == 2


def test_an_explicit_project_id_overrides_the_key(fcm_settings, fake_google):
    """For pointing staging at its own project with the same key."""
    fcm_settings(fcm_service_account_json=json.dumps(KEY), fcm_project_id="emma-staging")

    assert push._credentials()[0] == "emma-staging"


def test_a_hand_pasted_token_is_still_honoured(fcm_settings):
    """The documented escape hatch for testing without the key on the machine."""
    fcm_settings(fcm_access_token="ya29.by-hand", fcm_project_id="emma-test")

    assert push._credentials() == ("emma-test", "ya29.by-hand")


def test_no_key_and_no_token_is_not_configured(fcm_settings):
    fcm_settings()
    assert push._credentials() == (None, None)
    assert push.is_configured() is False


def test_is_configured_does_not_mint(fcm_settings, fake_google):
    """Callers ask this to decide whether push is available at all; it must not
    cost a round trip, and a network failure is not an answer to it."""
    fcm_settings(fcm_service_account_json=json.dumps(KEY))

    assert push.is_configured() is True
    assert fake_google.refreshes == 0


# ── a configured-but-broken credential is a fault, not silence ───────────────
def test_a_malformed_key_reads_as_auth_failed_not_unconfigured(fcm_settings):
    """"Not configured" would send an operator looking for an unset variable that
    is in fact set."""
    fcm_settings(fcm_service_account_json="{ this is not json")
    db = _DB(push_subscriptions=[_device()], notifications=[_note()])

    report = push.deliver(db, "f1", _note())

    assert report["skipped"] == "fcm_auth_failed"
    assert "not valid JSON" in report["detail"]
    assert db.store["notifications"][0]["status"] == "queued"


def test_a_key_pointing_at_a_missing_file_reads_as_auth_failed(fcm_settings):
    fcm_settings(fcm_service_account_json="/etc/emma/no-such-key.json")

    report = push.deliver(_DB(), "f1", _note())

    assert report["skipped"] == "fcm_auth_failed"


def test_a_refusal_from_google_reads_as_auth_failed(fcm_settings, fake_google, monkeypatch):
    """A revoked or deleted key. The notification stays queued and the report
    says why, rather than every phone looking merely unreachable."""
    def _refuse(self, _request):
        raise RuntimeError("invalid_grant: account not found")

    monkeypatch.setattr(fake_google, "refresh", _refuse)
    fcm_settings(fcm_service_account_json=json.dumps(KEY))

    report = push.deliver(_DB(), "f1", _note())

    assert report["skipped"] == "fcm_auth_failed"
    assert "invalid_grant" in report["detail"]


def test_a_failed_mint_is_not_cached(fcm_settings, fake_google, monkeypatch):
    """A transient failure must not poison every later send until restart."""
    calls = {"n": 0}

    def _fail_once(self, _request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connection reset")
        self.token, self.valid = "ya29.second-try", True

    monkeypatch.setattr(fake_google, "refresh", _fail_once)
    fcm_settings(fcm_service_account_json=json.dumps(KEY))

    with pytest.raises(push.AuthError):
        push._credentials()
    assert push._credentials()[1] == "ya29.second-try"


# ── expiry part-way through a fan-out ───────────────────────────────────────
def test_a_401_remints_and_replays_the_send(fcm_settings, fake_google):
    """The token can expire between the mint and the last phone of a ward."""
    fcm_settings(fcm_service_account_json=json.dumps(KEY))
    db = _DB(push_subscriptions=[_device()], notifications=[_note()])
    transport = _Fake((401, {"error": {"status": "UNAUTHENTICATED"}}), (200, {}))

    report = push.deliver(db, "f1", _note(), transport=transport)

    assert report["sent"] == 1 and report["revoked"] == 0
    assert [c["token"] for c in transport.calls] == ["ya29.minted-1", "ya29.minted-2"]
    assert db.store["notifications"][0]["status"] == "sent"


def test_a_401_does_not_revoke_the_device(fcm_settings, fake_google):
    """A credential fault on our side must not unsubscribe a working phone."""
    fcm_settings(fcm_service_account_json=json.dumps(KEY))
    db = _DB(push_subscriptions=[_device()], notifications=[_note()])
    transport = _Fake((401, {"error": {"status": "UNAUTHENTICATED"}}))

    report = push.deliver(db, "f1", _note(), transport=transport)

    assert (report["sent"], report["failed"], report["revoked"]) == (0, 1, 0)
    assert db.store["push_subscriptions"][0]["revoked_at"] is None


def test_the_token_is_reminted_once_per_fanout_not_once_per_device(fcm_settings, fake_google):
    """Three dead-token 401s must not be three mints."""
    fcm_settings(fcm_service_account_json=json.dumps(KEY))
    db = _DB(push_subscriptions=[_device("a"), _device("b"), _device("c")],
             notifications=[_note()])
    transport = _Fake((401, {"error": {"status": "UNAUTHENTICATED"}}))

    push.deliver(db, "f1", _note(), transport=transport)

    assert fake_google.refreshes == 2       # the initial mint, plus one retry


# ── the call site ───────────────────────────────────────────────────────────
def test_pushing_a_notification_attempts_the_phone_too(monkeypatch):
    seen = {}
    monkeypatch.setattr(push, "deliver",
                        lambda client, facility_id, row, **_: seen.update(row=row))
    db = _DB()
    notify.push(db, "f1", staff_id="s1", event_type="leave_decided",
                title="Leave approved")
    assert seen["row"]["title"] == "Leave approved"


# ── roster changes as a push trigger (SA.4b) ────────────────────────────────
def _roster_db(**extra):
    return _DB(
        shifts=[{"id": "sh-1", "roster_version_id": "rv-1", "date": "2026-09-01"},
                {"id": "sh-2", "roster_version_id": "rv-1", "date": "2026-09-02"},
                {"id": "sh-other", "roster_version_id": "rv-2", "date": "2026-10-01"}],
        shift_assignments=[
            {"id": "a1", "shift_id": "sh-1", "staff_id": "s1"},
            {"id": "a2", "shift_id": "sh-2", "staff_id": "s1"},
            {"id": "a3", "shift_id": "sh-2", "staff_id": "s2"},
            {"id": "a4", "shift_id": "sh-other", "staff_id": "s3"},
        ],
        **extra)


def test_publishing_a_roster_notifies_everyone_rostered_in_it():
    from emma_core.services import roster as roster_svc

    made = roster_svc.notify_published(_roster_db(), "f1", "rv-1")

    assert {n["staff_id"] for n in made} == {"s1", "s2"}
    assert made[0]["event_type"] == "roster_published"
    # The span the staff member is being told about, from the version's shifts.
    assert made[0]["body"] == "2026-09-01 – 2026-09-02"


def test_one_notification_per_person_not_per_shift():
    """s1 works two of the published shifts. Forty buzzes for a six-week NAAC
    cycle is a reason to turn notifications off."""
    from emma_core.services import roster as roster_svc

    made = roster_svc.notify_published(_roster_db(), "f1", "rv-1")

    assert [n["staff_id"] for n in made].count("s1") == 1


def test_staff_in_another_version_are_not_notified():
    from emma_core.services import roster as roster_svc

    made = roster_svc.notify_published(_roster_db(), "f1", "rv-1")

    assert "s3" not in {n["staff_id"] for n in made}


def test_publishing_an_empty_version_notifies_nobody():
    from emma_core.services import roster as roster_svc

    assert roster_svc.notify_published(_DB(shifts=[], shift_assignments=[]),
                                       "f1", "rv-1") == []


def test_a_broken_push_does_not_break_the_notification(monkeypatch):
    """The in-app notification is the guarantee; the phone is the extra. A push
    failure must not lose the row the app would have shown."""
    def _boom(*_a, **_k):
        raise RuntimeError("FCM is down")

    monkeypatch.setattr(push, "deliver", _boom)
    db = _DB()
    row = notify.push(db, "f1", staff_id="s1", event_type="leave_decided",
                      title="Leave approved")
    assert row["title"] == "Leave approved"
    assert db.store["notifications"][0]["status"] == "sent"
