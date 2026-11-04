"""Prepare a reviewable ECS/Bedrock plan. This command never changes AWS resources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parents[2]
MODELS = ("global.moonshotai.kimi-k3", "global.xai.grok-4.7")
SAFE_ENV = {"APP_ENV", "BEDROCK_ENABLED", "BEDROCK_REGION", "BEDROCK_MODEL_ID",
            "AI_SYNTHETIC_FACILITY_IDS", "CORS_ORIGINS", "CORS_ORIGIN_REGEX"}


def prepare(service_arn: str, runtime_role: str, model: str, facilities: list[str]) -> dict:
    target = re.fullmatch(r"arn:aws:ecs:([a-z0-9-]+):(\d{12}):service/([^/]+)/([^/]+)", service_arn)
    if not target or not re.fullmatch(r"[\w+=,.@-]+", runtime_role) or model not in MODELS:
        raise ValueError("Use an explicit ECS service ARN, IAM role name and supported model profile")
    region, account, cluster, service = target.groups()
    facilities = sorted({str(UUID(value)) for value in facilities})
    role_arn = f"arn:aws:iam::{account}:role/{runtime_role}"
    profile_arn = f"arn:aws:bedrock:{region}:{account}:inference-profile/{model}"
    policy = Path(__file__).with_name("bedrock_task_policy.example.json").read_text(encoding="utf-8")
    for token, value in {"SOURCE_REGION": region, "ACCOUNT_ID": account,
                         "INFERENCE_PROFILE_ID": model, "MODEL_ID": model.split(".", 1)[1]}.items():
        policy = policy.replace(token, value)
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()
    blockers = ["Exact committed source and release approval are required"]
    if dirty:
        blockers.append("The working tree has uncommitted changes")
    if not facilities:
        blockers.append("Approved synthetic facility IDs have not been supplied")
    migrations = []
    for path in sorted((ROOT / "emma-ai-app/supabase/migrations").glob("*.sql")):
        migrations.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return {
        "prepared_at": datetime.now(timezone.utc).isoformat(), "read_only": True,
        "resources_changed": False, "source_sha": source_sha,
        "working_tree_changes": dirty, "target": {"service_arn": service_arn, "region": region,
            "account_id": account, "cluster": cluster, "service": service, "runtime_role_arn": role_arn},
        "workflow_variables": {"BEDROCK_ENABLED": "true", "BEDROCK_REGION": region,
            "BEDROCK_MODEL_ID": model, "BEDROCK_TASK_ROLE_ARN": role_arn,
            "AI_SYNTHETIC_FACILITY_IDS": ",".join(facilities)},
        "runtime_policy": json.loads(policy),
        "runtime_trust_policy": {"Version": "2012-10-17", "Statement": [{
            "Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"},
            "Action": "sts:AssumeRole", "Condition": {
                "StringEquals": {"aws:SourceAccount": account},
                "ArnLike": {"aws:SourceArn": f"arn:aws:ecs:{region}:{account}:*"}}}]},
        "deployer_passrole_policy": {"Version": "2012-10-17", "Statement": [{
            "Effect": "Allow", "Action": "iam:PassRole", "Resource": role_arn,
            "Condition": {"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}},
            {"Effect": "Allow", "Action": "iam:GetRole", "Resource": role_arn}]},
        "local_migrations": migrations,
        "migration_review": [
            "Compare every local migration with the target migration ledger; the workflow uses --include-all",
            "24 adds leave snapshots/task suspension and changes approved-leave and published-roster guards",
            "25 adds designated event staff and rejects invalid participants/time ranges",
            "Confirm target-specific backup and restore evidence before running migrations"],
        "rollback": [
            "Stop rollout for broken sign-in, cross-tenant access, incorrect leave/task state or failed health checks",
            "Disable external AI and clear AI_SYNTHETIC_FACILITY_IDS if model behaviour is unsafe",
            "Use the reviewed previous ECS image and runtime configuration; re-read the service before applying",
            "Image rollback does not undo migrations, approved leave or event data",
            "Retain leave snapshots; do not drop new columns/triggers or restore a database over later writes automatically"],
        "blockers": blockers,
        "references": ["https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html",
                       "https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html"],
    }


def inspect_aws(plan: dict, session) -> None:
    """Inspect only; intentionally contains no create, update or invoke operations."""
    target = plan["target"]
    config = Config(connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 1})
    def client(name):
        return session.client(name, region_name=target["region"], config=config)

    identity = client("sts").get_caller_identity()
    if identity["Account"] != target["account_id"]:
        raise ValueError("AWS identity does not belong to the selected target account")
    results = {}
    for name, read in {
        "ecs": lambda: client("ecs").describe_express_gateway_service(serviceArn=target["service_arn"]),
        "role": lambda: client("iam").get_role(RoleName=target["runtime_role_arn"].rsplit("/", 1)[1]),
        "profile": lambda: client("bedrock").get_inference_profile(
            inferenceProfileIdentifier=plan["workflow_variables"]["BEDROCK_MODEL_ID"]),
    }.items():
        try:
            results[name] = read()
        except (ClientError, BotoCoreError) as exc:
            code = exc.response.get("Error", {}).get("Code") if isinstance(exc, ClientError) else type(exc).__name__
            results[name] = {"error": code}
            plan["blockers"].append(f"AWS {name} inspection failed: {code}")
    service = results["ecs"].get("service", {})
    configurations = [{
        "revision_arn": row.get("serviceRevisionArn"), "image": row.get("primaryContainer", {}).get("image"),
        "runtime_role_arn": row.get("taskRoleArn"), "execution_role_arn": row.get("executionRoleArn"),
        "environment": {v["name"]: v.get("value") for v in row.get("primaryContainer", {}).get("environment", []) if v["name"] in SAFE_ENV},
    } for row in service.get("activeConfigurations", [])]
    role = results["role"].get("Role", {})
    profile = results["profile"]
    running = []
    try:
        ecs = client("ecs")
        arns = ecs.list_tasks(cluster=target["cluster"], serviceName=target["service"], desiredStatus="RUNNING")["taskArns"]
        tasks = ecs.describe_tasks(cluster=target["cluster"], tasks=arns) if arns else {"tasks": []}
        if tasks.get("failures"):
            raise ValueError("Running task inspection returned failures")
        for arn in sorted({row["taskDefinitionArn"] for row in tasks["tasks"]}):
            definition = ecs.describe_task_definition(taskDefinition=arn)["taskDefinition"]
            running.append({"task_definition_arn": arn, "runtime_role_arn": definition.get("taskRoleArn"),
                "environment": {v["name"]: v.get("value") for container in definition.get("containerDefinitions", [])
                    for v in container.get("environment", []) if v["name"] in SAFE_ENV}})
    except (ValueError, ClientError, BotoCoreError) as exc:
        code = exc.response.get("Error", {}).get("Code") if isinstance(exc, ClientError) else type(exc).__name__
        plan["blockers"].append(f"Running task inspection failed: {code}")
    plan["aws_inspection"] = {
        "checked_at": datetime.now(timezone.utc).isoformat(), "account_id": identity["Account"],
        "active_configurations": configurations, "runtime_role_exists": role.get("Arn") == target["runtime_role_arn"],
        "running_task_definitions": running,
        "profile_status": profile.get("status"),
        "global_inference": plan["workflow_variables"]["BEDROCK_MODEL_ID"].startswith("global."),
        "inference_destination_regions": sorted({row["modelArn"].split(":")[3] for row in profile.get("models", []) if row["modelArn"].split(":")[3]}),
        "errors": {name: value["error"] for name, value in results.items() if "error" in value},
        "runtime_policy_effectiveness_verified": False,
    }
    if not configurations:
        plan["blockers"].append("No active ECS configuration was returned; rollback target is unverified")
    if profile.get("status") != "ACTIVE":
        plan["blockers"].append("The chosen inference profile is not verified ACTIVE")
    if not running:
        plan["blockers"].append("No running task definition was verified")
    if any(row["runtime_role_arn"] != target["runtime_role_arn"] for row in running):
        plan["blockers"].append("The running service does not use the proposed runtime role")
    plan["blockers"].append("Verify effective Bedrock permissions on the deployed task before enabling model traffic")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-arn", required=True)
    parser.add_argument("--runtime-role", required=True)
    parser.add_argument("--model", choices=MODELS, default=MODELS[0])
    parser.add_argument("--synthetic-facility-id", action="append", default=[])
    parser.add_argument("--inspect-aws", action="store_true")
    parser.add_argument("--profile")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = prepare(args.service_arn, args.runtime_role, args.model, args.synthetic_facility_id)
    if args.inspect_aws:
        try:
            inspect_aws(plan, boto3.Session(profile_name=args.profile))
        except (ValueError, ClientError, BotoCoreError) as exc:
            plan["blockers"].append(f"AWS inspection unavailable ({type(exc).__name__})")
    else:
        plan["blockers"].append("Current AWS configuration has not been inspected")
    args.output.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Prepared read-only release plan; {len(plan['blockers'])} gates remain. No AWS resources changed.")


if __name__ == "__main__":
    main()
