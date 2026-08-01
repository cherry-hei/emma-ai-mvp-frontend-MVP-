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

from collections import defaultdict

import pytest

from emma_core.services import notifications as notify
from emma_core.services import push


class _Query:
    def __init__(self, store, table):
        self.store, self.name = store, table
        self.filters, self.payload, self.mode = [], None, "select"

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

    def _match(self, row):
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


# ── the call site ───────────────────────────────────────────────────────────
def test_pushing_a_notification_attempts_the_phone_too(monkeypatch):
    seen = {}
    monkeypatch.setattr(push, "deliver",
                        lambda client, facility_id, row, **_: seen.update(row=row))
    db = _DB()
    notify.push(db, "f1", staff_id="s1", event_type="leave_decided",
                title="Leave approved")
    assert seen["row"]["title"] == "Leave approved"


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
