"""No-secret M1 regression checks. Never uses a live database or demo login."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = ROOT.parent
SCRIPT = ROOT / "scripts" / "provision_tenant.py"
CONFIG = ROOT / "scripts" / "tenants" / "naac.json"
MIGRATION = (ROOT / "supabase" / "migrations" /
             "20261001000024_tenant_dictionary_boundary.sql")


def _run_dry_run(config: pathlib.Path):
    env = os.environ.copy()
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
                "DATABASE_URL"):
        env.pop(key, None)
    # A cloud-configured process must not make an offline config check fail, or
    # silently fall back to a different database from a developer's local .env.
    env["APP_ENV"] = "prod"
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(config), "--dry-run"],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=20,
        check=False,
    )


def test_naac_config_dry_run_needs_no_secret_or_network():
    completed = _run_dry_run(CONFIG)
    assert completed.returncode == 0, completed.stderr
    assert "Nothing written" in completed.stdout
    assert "no Supabase" not in completed.stderr
    assert "Password for every login" not in completed.stdout


def test_dry_run_rejects_an_unknown_duty_without_connecting(tmp_path):
    spec = json.loads(CONFIG.read_text(encoding="utf-8"))
    spec["roster"]["pattern"]["RN"][0] = "NOT_A_DUTY_CODE"
    config = tmp_path / "bad-synthetic-tenant.json"
    config.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    completed = _run_dry_run(config)
    assert completed.returncode != 0
    assert "absent from the naac sheet" in (completed.stdout + completed.stderr)
    assert "NOT_A_DUTY_CODE" in (completed.stdout + completed.stderr)
    assert "Neither" not in completed.stdout  # no false success notice


class RecordingQuery:
    def __init__(self):
        self.filters = []

    def select(self, *_args):
        return self

    def or_(self, expression):
        self.filters.append(expression)
        return self

    def eq(self, *_args):
        return self

    def order(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class RecordingClient:
    def __init__(self):
        self.query = RecordingQuery()

    def table(self, _name):
        return self.query


@pytest.mark.parametrize("module_name,function_name", [
    ("tasks", "task_definitions_by_label"),
    ("escort", "list_locations"),
])
def test_service_role_dictionary_queries_only_include_true_global_templates(
    monkeypatch, module_name, function_name
):
    from emma_core.services import escort, tasks

    module = {"tasks": tasks, "escort": escort}[module_name]
    monkeypatch.setattr(module, "org_id_for", lambda _client, _facility: "synthetic-org-a")
    client = RecordingClient()
    getattr(module, function_name)(client, "synthetic-home-a")
    assert client.query.filters == [
        "org_id.eq.synthetic-org-a,and(org_id.is.null,facility_id.is.null)"
    ]


def test_rls_policy_does_not_treat_every_facility_null_row_as_global():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for table in ("task_definitions", "escort_locations"):
        block = sql.split(f"create policy {table}_read on {table}", 1)[1].split(";", 1)[0]
        assert "org_id = public.current_org_id()" in block
        assert "org_id is null and facility_id is null" in block
        assert "facility_id is null or" not in block
    assert "org_id must match facility owner" in sql
    assert "org_id/facility_id mismatch" in sql
