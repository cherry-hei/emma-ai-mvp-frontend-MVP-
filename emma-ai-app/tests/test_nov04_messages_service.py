"""Offline service and migration assertions for Nov 04 direct messaging."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from emma_core.services import messages

SENDER = "00000000-0000-0000-0000-000000000001"
RECIPIENT = "00000000-0000-0000-0000-000000000002"
MESSAGE = "00000000-0000-0000-0000-000000000003"
CLIENT_MESSAGE = "00000000-0000-0000-0000-000000000004"
FACILITY = "00000000-0000-0000-0000-000000000010"


def _row() -> dict:
    return {
        "id": MESSAGE,
        "sender_profile_id": SENDER,
        "recipient_profile_id": RECIPIENT,
        "body": "handover complete",
        "created_at": "2026-10-31T07:00:00+00:00",
        "read_at": None,
    }


class _Result:
    def __init__(self, data):
        self.data = data


class _RpcClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self._pending = None

    def rpc(self, name, params):
        self.calls.append((name, params))
        self._pending = self.responses[name]
        return self

    def execute(self):
        return _Result(self._pending)


class _Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.calls = []

    def select(self, value):
        self.calls.append(("select", value))
        return self

    def eq(self, key, value):
        self.calls.append(("eq", key, value))
        return self

    def or_(self, value):
        self.calls.append(("or", value))
        return self

    def lt(self, key, value):
        self.calls.append(("lt", key, value))
        return self

    def order(self, key, **kwargs):
        self.calls.append(("order", key, kwargs))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def execute(self):
        return _Result(self.client.rows)


class _TableClient:
    def __init__(self, rows):
        self.rows = rows
        self.query = None

    def table(self, table):
        self.query = _Query(self, table)
        return self.query


def test_send_and_read_use_authenticated_rpc_and_require_exactly_one_durable_row():
    client = _RpcClient({
        "send_direct_message": [_row()],
        "mark_direct_message_read": [_row()],
    })

    sent = messages.send_message(
        client,
        recipient_profile_id=RECIPIENT,
        body="handover complete",
        client_message_id=CLIENT_MESSAGE,
    )
    read = messages.mark_read(client, message_id=MESSAGE)

    assert sent == _row()
    assert read == _row()
    assert client.calls == [
        ("send_direct_message", {
            "p_recipient_profile_id": RECIPIENT,
            "p_body": "handover complete",
            "p_client_message_id": CLIENT_MESSAGE,
        }),
        ("mark_direct_message_read", {"p_message_id": MESSAGE}),
    ]


def test_service_never_turns_empty_or_ambiguous_rpc_result_into_success():
    client = _RpcClient({
        "send_direct_message": [],
        "mark_direct_message_read": [_row(), _row()],
    })

    assert messages.send_message(
        client, recipient_profile_id=RECIPIENT, body="x",
    ) is None
    assert messages.mark_read(client, message_id=MESSAGE) is None


def test_list_query_has_explicit_facility_participant_peer_cursor_and_limit():
    client = _TableClient([_row()])
    before = datetime(2026, 10, 31, 7, 1, tzinfo=timezone.utc)

    result = messages.list_messages(
        client,
        facility_id=FACILITY,
        profile_id=SENDER,
        peer_profile_id=RECIPIENT,
        before=before,
        limit=19,
    )

    assert result == [_row()]
    assert client.query.table == "direct_messages"
    assert ("eq", "facility_id", FACILITY) in client.query.calls
    assert ("or", f"and(sender_profile_id.eq.{SENDER},recipient_profile_id.eq.{RECIPIENT}),"
            f"and(sender_profile_id.eq.{RECIPIENT},recipient_profile_id.eq.{SENDER})") in client.query.calls
    assert ("lt", "created_at", before.isoformat()) in client.query.calls
    assert ("order", "created_at", {"desc": True}) in client.query.calls
    assert ("limit", 19) in client.query.calls


def test_migration_has_bounded_contract_and_secure_write_boundary():
    migration = (
        Path(__file__).parents[1]
        / "supabase/migrations/20261031000100_direct_messages.sql"
    ).read_text(encoding="utf-8").lower()

    assert "create table if not exists direct_messages" in migration
    assert "create table if not exists direct_message_audit" in migration
    assert "char_length(body) <= 4000" in migration
    assert "sender_profile_id <> recipient_profile_id" in migration
    assert "uq_direct_messages_sender_client_message" in migration
    assert "pg_advisory_xact_lock" in migration
    assert "alter table direct_messages enable row level security" in migration
    assert "create policy direct_messages_select_participant" in migration
    assert "create policy direct_messages_insert_sender" in migration
    assert "create policy direct_messages_update_recipient" in migration
    assert "current_user_can_read_direct_message" in migration
    assert "revoke all privileges on direct_messages, direct_message_audit" in migration
    assert "grant select on direct_messages to authenticated" in migration
    assert "grant insert" not in migration.split("revoke all privileges on direct_messages", 1)[1]

    for function in (
        "public.list_direct_message_contacts()",
        "public.send_direct_message(uuid, text, uuid)",
        "public.mark_direct_message_read(uuid)",
    ):
        assert f"grant execute on function {function}" in migration
    assert "to authenticated;" in migration
    assert "security definer" in migration
    assert "auth.uid() is null or auth.role() is distinct from 'authenticated'" in migration
    assert "set search_path = pg_catalog, public, auth" in migration
    assert "from public, anon;" in migration


def test_migration_protects_content_receipts_and_audit_from_forgery():
    migration = (
        Path(__file__).parents[1]
        / "supabase/migrations/20261031000100_direct_messages.sql"
    ).read_text(encoding="utf-8").lower()

    assert "create or replace function public.protect_direct_message()" in migration
    assert "direct messages cannot be deleted" in migration
    assert "emma.direct_message_read_guard" in migration
    assert "direct message content and identity are immutable" in migration
    assert "create trigger trg_protect_direct_message" in migration
    assert "create or replace function public.protect_direct_message_audit()" in migration
    assert "direct_message_audit is append-only" in migration
    assert "create trigger trg_protect_direct_message_audit" in migration
    assert "insert into public.direct_message_audit" in migration
    assert "action = 'sent'" not in migration  # insert carries a literal action value, no broad mutable state.
    assert "'sent'" in migration and "'read'" in migration


def test_migration_scopes_contacts_from_database_relationships_not_client_role():
    migration = (
        Path(__file__).parents[1]
        / "supabase/migrations/20261031000100_direct_messages.sql"
    ).read_text(encoding="utf-8").lower()

    assert "join public.staff st" in migration
    assert "st.status = 'active'" in migration
    assert "join public.facility_units u" in migration
    assert "st.primary_unit_id" in migration
    assert "f.org_id = up.org_id" in migration
    assert "up.role in (" in migration
    assert "list_direct_message_contacts" in migration
    assert "up.id <> caller_scope.profile_id" in migration
    assert "unit transfer or inactivation hides a former peer's history" in migration
