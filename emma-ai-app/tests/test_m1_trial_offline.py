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
    """Record and apply equality predicates; never return a canned answer."""
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def select(self, *_args):
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def order(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=[
            row for row in self.rows
            if all(value is not None and row.get(field) == value
                   for field, value in self.filters)
        ])


class RecordingClient:
    def __init__(self, rows):
        self.query = RecordingQuery(rows)

    def table(self, _name):
        return self.query


@pytest.mark.parametrize("module_name,function_name", [
    ("tasks", "task_definitions_by_label"),
    ("escort", "list_locations"),
])
def test_service_role_dictionary_queries_deny_unapproved_global_rows(
    monkeypatch, module_name, function_name
):
    from emma_core.services import escort, tasks

    org_x = "00000000-0000-4000-8000-000000000001"
    org_y = "00000000-0000-4000-8000-000000000002"
    facility_x1 = "00000000-0000-4000-8000-000000000101"
    module = {"tasks": tasks, "escort": escort}[module_name]
    monkeypatch.setattr(module, "org_id_for", lambda _client, _facility: org_x)
    rows = [
        {"id": "own", "org_id": org_x, "facility_id": None,
         "active": True, "task_code": "X", "code": "X"},
        {"id": "foreign", "org_id": org_y, "facility_id": None,
         "active": True, "task_code": "Y", "code": "Y"},
        {"id": "global", "org_id": None, "facility_id": None,
         "active": True, "task_code": "G", "code": "G"},
    ]
    client = RecordingClient(rows)
    result = getattr(module, function_name)(client, facility_x1)
    values = result.values() if isinstance(result, dict) else result
    assert {row["id"] for row in values} == {"own"}
    assert client.query.filters == [("org_id", org_x), ("active", True)]


def test_rls_policy_does_not_treat_every_facility_null_row_as_global():
    # Inspect the final definition across the migration chain, not migration 24
    # in isolation. The standalone B1 suite also checks the FOR ALL policies.
    import re

    policies = {}
    for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
        sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8").lower())
        for statement in sql.split(";"):
            statement = " ".join(statement.split())
            for table in ("task_definitions", "escort_locations"):
                name = table + "_read"
                if re.match(r"drop policy if exists " + name +
                            r" on (?:public\.)?" + table + r"$", statement):
                    policies.pop(name, None)
                if re.match(r"create policy " + name +
                            r" on (?:public\.)?" + table + r" ", statement):
                    policies[name] = statement
    for table in ("task_definitions", "escort_locations"):
        block = policies[table + "_read"]
        assert "using (org_id is not null and org_id = public.current_org_id())" in block
        assert "facility_id is null" not in block
        assert " or " not in block
    historical = MIGRATION.read_text(encoding="utf-8").lower()
    assert "org_id must match facility owner" in historical
    assert "org_id/facility_id mismatch" in historical
