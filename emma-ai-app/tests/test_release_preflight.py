"""Release checks must block unverifiable targets and keep credentials/records private."""

from types import SimpleNamespace

import pytest

from scripts import preflight_migrations as migrations
from scripts import prepare_bedrock_release as bedrock


class DatabaseError(Exception):
    def __init__(self, code):
        super().__init__("sensitive connection and record details")
        self.sqlstate = code


@pytest.mark.parametrize("code,applied,expected", [
    ("42P01", [], "not_present"),
    ("42703", [], "not_present"),
    ("42P01", ["20260729000010"], "block"),
    ("42501", [], "block"),
    ("57014", [], "block"),
])
def test_sql_errors_only_skip_absent_objects_from_pending_migrations(monkeypatch, code, applied, expected):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql):
            if sql == "first": raise DatabaseError(code)
        def fetchall(self): return []

    monkeypatch.setattr(migrations, "_applied", lambda cur: applied)
    monkeypatch.setattr(migrations, "CHECKS", [("first check", "10", "block", "first"), ("later check", "11", "block", "later")])
    report = migrations.inspect(SimpleNamespace(cursor=Cursor))
    assert report["checks"][0]["status"] == expected
    assert report["checks"][1]["status"] == "ok"
    assert report["blockers"] == (expected == "block")
    assert "sensitive" not in str(report)


def test_preflight_connection_is_read_only_and_does_not_print_connection_errors(monkeypatch, capsys):
    import psycopg
    seen = {}
    def connect(url, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("postgres://private-password@private-server/records")
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr("sys.argv", ["preflight", "--url", "synthetic", "--json"])
    assert migrations.main() == 2
    assert seen["autocommit"] is True
    assert "default_transaction_read_only=on" in seen["options"]
    assert "private-password" not in capsys.readouterr().err


def test_bedrock_plan_uses_only_target_scoped_policies_and_keeps_release_gated():
    plan = bedrock.prepare("arn:aws:ecs:ap-southeast-1:123456789012:service/default/emma-api", "emma-runtime", "global.moonshotai.kimi-k3", [])
    assert plan["resources_changed"] is False
    assert plan["workflow_variables"]["AI_SYNTHETIC_FACILITY_IDS"] == ""
    assert any("synthetic facility IDs" in value for value in plan["blockers"])
    assert plan["deployer_passrole_policy"]["Statement"][0]["Resource"] == "arn:aws:iam::123456789012:role/emma-runtime"
    resources = plan["runtime_policy"]["Statement"][0]["Resource"]
    assert "arn:aws:bedrock:*::foundation-model/moonshotai.kimi-k3" in resources
    assert not any(value.endswith("/*") for value in resources)
    assert plan["local_migrations"][-1]["file"].startswith("20261030000025")


def test_aws_inspection_refuses_a_different_account_before_reading_other_services():
    calls = []
    class Session:
        def client(self, name, **kwargs):
            calls.append(name)
            return SimpleNamespace(get_caller_identity=lambda: {"Account": "999999999999"})
    plan = bedrock.prepare("arn:aws:ecs:ap-southeast-1:123456789012:service/default/emma-api", "emma-runtime", "global.moonshotai.kimi-k3", [])
    with pytest.raises(ValueError, match="selected target account"):
        bedrock.inspect_aws(plan, Session())
    assert calls == ["sts"]


def test_runtime_inspection_redacts_unapproved_environment_values_and_never_treats_role_existence_as_permission():
    class Session:
        def client(self, name, **kwargs):
            return SimpleNamespace(
                get_caller_identity=lambda: {"Account": "123456789012"},
                describe_express_gateway_service=lambda **kw: {"service": {"activeConfigurations": [{
                    "primaryContainer": {"image": "synthetic@sha256:abc", "environment": [
                        {"name": "BEDROCK_ENABLED", "value": "false"},
                        {"name": "DATABASE_URL", "value": "sensitive-password"}]}}]}},
                get_role=lambda **kw: {"Role": {"Arn": "arn:aws:iam::123456789012:role/emma-runtime"}},
                get_inference_profile=lambda **kw: {"status": "ACTIVE", "models": []},
                list_tasks=lambda **kw: {"taskArns": ["synthetic-task"]},
                describe_tasks=lambda **kw: {"tasks": [{"taskDefinitionArn": "synthetic-definition"}]},
                describe_task_definition=lambda **kw: {"taskDefinition": {"containerDefinitions": [{"environment": [
                    {"name": "SUPABASE_SERVICE_ROLE_KEY", "value": "sensitive-key"}]}]}},
            )
    plan = bedrock.prepare("arn:aws:ecs:ap-southeast-1:123456789012:service/default/emma-api", "emma-runtime", "global.moonshotai.kimi-k3", [])
    bedrock.inspect_aws(plan, Session())
    assert "sensitive" not in str(plan)
    assert plan["aws_inspection"]["runtime_role_exists"]
    assert not plan["aws_inspection"]["runtime_policy_effectiveness_verified"]
    assert any("does not use the proposed runtime role" in value for value in plan["blockers"])
