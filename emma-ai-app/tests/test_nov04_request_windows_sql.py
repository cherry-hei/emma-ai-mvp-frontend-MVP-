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
    assert "before insert on public.leave_requests" in sql
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


def test_historical_records_are_not_updated_or_revalidated_by_migration():
    sql = _sql()
    trigger_region = sql.split("create trigger trg_enforce_request_window_on_leave_insert", 1)[1]
    assert "before insert on public.leave_requests" in trigger_region
    assert "before update on public.leave_requests" not in trigger_region
    assert "update public.leave_requests" not in sql
