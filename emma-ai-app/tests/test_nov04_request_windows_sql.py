"""Static migration checks for the request-window database safety boundary.

These tests are deliberately offline. They cannot substitute for applying the
migration to the confirmed Supabase project and exercising RLS with real tokens.
"""
from __future__ import annotations

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase" / "migrations" / "20261031000200_request_windows.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_creates_durable_scoped_windows_and_append_only_audit():
    sql = _sql()
    assert "create table if not exists public.request_windows" in sql
    assert "org_id" in sql and "facility_id" in sql and "unit_id" in sql
    assert "target_end_exclusive" in sql
    assert "create table if not exists public.request_window_audit" in sql
    assert "request_window_audit is append-only" in sql
    assert "before update or delete on public.request_window_audit" in sql


def test_create_is_idempotent_and_patch_uses_explicit_compare_and_swap_version():
    sql = _sql()
    assert "uq_request_windows_idempotency" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "v_create_reason text" in sql
    assert "a.action = 'create'" in sql
    assert "v_create_reason is not distinct from p_reason" in sql
    assert "idempotency key already belongs to a different request window" in sql
    assert "p_expected_version" in sql
    assert "stale request-window version" in sql
    assert "version = v_before.version + 1" in sql


def test_database_time_and_exclusive_bounds_are_authoritative():
    sql = _sql()
    assert "v_now timestamptz := clock_timestamp()" in sql
    assert "p_now >= p_window.closes_at" in sql
    assert "p_date_end >= v_window.target_end_exclusive" in sql
    assert "p_date_start < v_window.target_start" in sql
    assert "request-window timestamps require timezone offsets" in sql


def test_leave_insert_trigger_rechecks_gated_duty_writes_in_database():
    sql = _sql()
    assert "create or replace function public.enforce_request_window_on_leave_insert" in sql
    assert "before insert or update of facility_id, staff_id, leave_type, date_start, date_end on public.leave_requests" in sql
    assert "tg_op = 'update'" in sql
    assert "new.leave_type is not distinct from old.leave_type" in sql
    assert "public.request_window_availability(" in sql
    assert "request window unavailable:" in sql
    assert "when 'do' then 'duty'" in sql
    assert "when 'duty_request' then 'duty'" in sql
    assert "when 'shift_swap' then 'duty'" in sql
    assert "when 'sl' then" not in sql
    assert "when 'urgent' then" not in sql


def test_window_writes_are_owner_superintendent_only_and_deputy_is_not_guessed():
    sql = _sql()
    assert "lower(coalesce(public.current_role_name(), '')) not in ('owner', 'superintendent')" in sql
    assert "not authorized to administer request windows" in sql
    assert "p_facility_id is distinct from public.current_facility_id()" in sql


def test_rls_and_grants_make_direct_client_access_tenant_read_only():
    sql = _sql()
    assert "alter table public.request_windows enable row level security" in sql
    assert "alter table public.request_window_audit enable row level security" in sql
    assert "request_windows_tenant_read" in sql
    assert "request_window_audit_tenant_read" in sql
    assert "revoke all on public.request_windows, public.request_window_audit from public, anon, authenticated" in sql
    assert "grant select on public.request_windows, public.request_window_audit to authenticated" in sql


def test_frontline_availability_rpc_is_limited_to_their_own_staff_identity():
    sql = _sql()
    assert "v_role in ('staff', 'frontline')" in sql
    assert "p_staff_id is distinct from public.current_staff_id()" in sql
    assert "request-window staff is not available" in sql


def test_effective_configuration_is_share_locked_through_the_leave_transaction():
    sql = _sql()
    assert "for share of f" in sql
    assert "limit 1\n     for share;" in sql
    assert "for update;" in sql


def test_known_role_vocabulary_fails_closed_in_rpc_catalog_and_rls():
    sql = _sql()
    known_roles = (
        "'superintendent', 'admin', 'staff', 'scheduler', 'hr', 'auditor',\n"
        "        'owner', 'nurse_mgr', 'allied_health', 'admin_clerk', 'frontline', 'hr_auditor'"
    )
    assert sql.count(known_roles) >= 2
    windows_policy = sql.split("create policy request_windows_tenant_read", 1)[1].split(
        "drop policy if exists request_window_audit_tenant_read", 1
    )[0]
    audit_policy = sql.split("create policy request_window_audit_tenant_read", 1)[1].split(
        "revoke all on public.request_windows", 1
    )[0]
    for role in ("superintendent", "admin", "staff", "scheduler", "hr", "auditor",
                 "owner", "nurse_mgr", "allied_health", "admin_clerk", "frontline", "hr_auditor"):
        assert f"'{role}'" in windows_policy
        assert f"'{role}'" in audit_policy
    assert "or not v_known_role" in sql
    assert "nullif(btrim(coalesce(public.current_role_name(), '')), '') is not null" not in sql


def test_only_policy_input_updates_are_revalidated_not_status_only_history_updates():
    sql = _sql()
    trigger_region = sql.split("create trigger trg_enforce_request_window_on_leave_insert", 1)[1]
    assert "before insert or update of facility_id, staff_id, leave_type, date_start, date_end" in trigger_region
    assert "before update on public.leave_requests" not in trigger_region
    assert "update public.leave_requests" not in sql
