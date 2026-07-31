"""Offline Phase 5 API and migration contract checks."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app


def test_openapi_documents_phase5_compliance_surface():
    document = TestClient(app).get("/openapi.json").json()

    assert document["info"]["version"] == "0.6.0"
    assert "/compliance/minute-ratio" in document["paths"]
    assert "/compliance/rule-definitions" in document["paths"]
    assert "/validate-roster" in document["paths"]
    assert "/rosters/{version_id}/publish" in document["paths"]


def test_phase5_tables_and_new_foreign_keys_keep_rls_boundaries():
    migration = (
        Path(__file__).parents[1]
        / "supabase/migrations/20260729000010_phase5_compliance_engine.sql"
    ).read_text(encoding="utf-8")

    for table in (
        "rule_definitions",
        "roster_validation_runs",
        "leave_balances",
    ):
        assert f"alter table {table} enable row level security" in migration
    assert "create policy rule_definitions_read" in migration
    assert "create policy rule_definitions_write" in migration
    assert "create policy roster_validation_runs_read" in migration
    assert "create policy roster_validation_runs_insert" not in migration
    assert "create policy roster_validation_runs_update" not in migration
    assert "create policy leave_balances_read" in migration
    assert "create policy leave_balances_write" not in migration
    assert "create policy leave_requests_read" in migration
    assert "create policy leave_requests_insert" not in migration
    assert "create policy leave_requests_update" not in migration
    assert "public.current_role_name() in ('superintendent', 'admin', 'scheduler')" in migration
    assert "create trigger trg_sync_leave_balance_usage" in migration
    assert "after insert or update or delete on leave_requests" in migration
    assert "anchor_facility_id := old.facility_id" in migration
    assert "leave dates require exactly one configured balance" in migration
    assert "from generate_series(" in migration
    assert "create trigger trg_protect_violation_evidence" in migration
    assert "violation evidence is append-only" in migration
    assert "for update of lb" in migration
    assert "insufficient configured leave balance" in migration
    assert "create policy roster_validation_runs_delete" not in migration
    assert "create policy violation_log_delete" not in migration
    assert "validation_run_id uuid" in migration
    assert "staff_id uuid" in migration
    assert "rule_definition_id uuid" in migration
    assert "NIGHT_COOLDOWN" in migration


def test_phase5_evidence_and_workflow_writes_are_service_owned():
    migration = (
        Path(__file__).parents[1]
        / "supabase/migrations/20260729000010_phase5_compliance_engine.sql"
    ).read_text(encoding="utf-8").lower()

    for policy in (
        "roster_validation_runs_insert",
        "roster_validation_runs_update",
        "violation_log_insert",
        "violation_log_update",
        "future_debt_ledger_write",
        "leave_requests_insert",
        "leave_requests_update",
        "leave_balances_write",
    ):
        assert f"create policy {policy}" not in migration

    assert "create policy roster_publish_events_read" in migration
    assert "revoke insert, update, delete on" in migration
    for table in (
        "violation_log",
        "future_debt_ledger",
        "leave_requests",
        "roster_publish_events",
        "roster_option_scores",
    ):
        assert table in migration
    assert "grant select on roster_validation_runs, leave_balances" in migration


def test_phase5_ratio_configuration_rejects_unsafe_new_rows():
    migration = (
        Path(__file__).parents[1]
        / "supabase/migrations/20260729000010_phase5_compliance_engine.sql"
    ).read_text(encoding="utf-8")

    assert "staffing_ratio_rules_ratio_positive_check" in migration
    assert "ratio_residents_per_staff > 0" in migration
    assert "staffing_ratio_rules_min_staff_nonnegative_check" in migration
    assert "min_staff_any_rank >= 0" in migration
    assert "staffing_ratio_rules_requirement_present_check" in migration
    assert "public.is_nonnegative_numeric_json_object" in migration
    assert "staffing_ratio_rules_rank_weights_valid_check" in migration
