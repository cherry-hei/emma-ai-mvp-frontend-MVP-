"""Review-only automatic leave candidate. Never writes a leave decision."""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from api.deps import api_error
from emma_core.permissions import SystemRole, normalise_role


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    org_id: str
    facility_id: str
    version: StrictInt = Field(ge=1)
    enabled: StrictBool
    allowed_types: list[str] = Field(max_length=32)
    rule_version: str = Field(min_length=1, max_length=128)


class PolicyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: StrictInt = Field(ge=0)
    retry_key: str = Field(min_length=1, max_length=128)
    enabled: StrictBool = False
    allowed_types: list[str] = Field(default_factory=list, max_length=32)
    rule_version: str = Field(min_length=1, max_length=128)


def owner(ctx):
    if (normalise_role(ctx.profile.role) != SystemRole.OWNER
            or not ctx.org_id or not ctx.facility_id):
        raise api_error(403, "forbidden", "A scoped owner account is required.")


def read_policy(ctx):
    owner(ctx)
    try:
        rows = (ctx.client.table("auto_approval_policies").select("*")
                .eq("org_id", ctx.org_id).eq("facility_id", ctx.facility_id)
                .limit(1).execute().data)
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError()
        if not rows:
            return None
        # DB metadata is not part of the public policy contract.
        row = Policy.model_validate({k: rows[0][k] for k in Policy.model_fields})
        if row.org_id != ctx.org_id or row.facility_id != ctx.facility_id:
            raise ValueError()
        return row.model_dump()
    except Exception as exc:
        raise api_error(503, "persistence_unavailable", "Policy could not be read.") from exc


def write_policy(ctx, body: PolicyWrite, *, create: bool):
    owner(ctx)
    if (create and body.expected_version != 0) or (not create and body.expected_version == 0):
        raise api_error(422, "invalid_version", "Create requires version 0; patch requires the current version.")
    if create and body.enabled:
        raise api_error(422, "disabled_default", "Create disabled, then explicitly activate by patch.")
    if (body.enabled and not body.allowed_types) or any(
            not t.strip() or len(t) > 64 for t in body.allowed_types):
        raise api_error(422, "invalid_policy", "Activation requires explicit allowed types.")
    if len(set(body.allowed_types)) != len(body.allowed_types):
        raise api_error(422, "invalid_policy", "Duplicate allowed types.")
    try:
        result = ctx.client.rpc("auto_approval_write_policy", {
            "p_org": ctx.org_id, "p_facility": ctx.facility_id,
            "p_expected": body.expected_version, "p_retry": body.retry_key,
            "p_enabled": body.enabled, "p_types": body.allowed_types,
            "p_rule": body.rule_version,
        }).execute().data
        if not isinstance(result, dict):
            raise ValueError()
        if result == {"error": "conflict"}:
            raise api_error(409, "version_or_retry_conflict", "Version or retry payload conflicts.")
        policy = Policy.model_validate(result)
        if (policy.org_id != ctx.org_id or policy.facility_id != ctx.facility_id
                or policy.version != body.expected_version + 1
                or policy.enabled != body.enabled or policy.allowed_types != body.allowed_types
                or policy.rule_version != body.rule_version):
            raise ValueError()
        return policy.model_dump()
    except Exception as exc:
        if getattr(exc, "status_code", None) == 409:
            raise
        raise api_error(503, "persistence_unavailable", "Policy save was not confirmed; retry with the same key and payload.") from exc


def evaluate(ctx, request_id: str, expected_policy_version: int):
    policy = read_policy(ctx)
    try:
        rows = (ctx.client.table("leave_requests").select("id,facility_id,status,leave_type,date_start,date_end")
                .eq("facility_id", ctx.facility_id).eq("id", request_id).limit(1).execute().data)
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError()
        if not rows:
            raise api_error(404, "not_found", "Request not found.")
        request = rows[0]
        if request["id"] != request_id or request["facility_id"] != ctx.facility_id:
            raise ValueError()
        start = date.fromisoformat(request["date_start"])
        end = date.fromisoformat(request["date_end"])
        status, leave_type = request["status"], request["leave_type"]
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            raise
        raise api_error(503, "persistence_unavailable", "Request evidence unavailable.") from exc
    reasons = []
    if policy is None:
        reasons.append("policy_missing")
    else:
        if policy["version"] != expected_policy_version:
            reasons.append("stale_policy_version")
        if not policy["enabled"]:
            reasons.append("policy_disabled")
        if leave_type not in policy["allowed_types"]:
            reasons.append("type_not_explicitly_allowed")
    if status not in ("pending", "reviewed"):
        reasons.append("request_not_pending")
    if end < start or start <= date.today():
        reasons.append("past_or_invalid_dates")
    # No cached policy_result_json, LLM score, or client evidence is trusted.
    # Source has no single transaction covering these authoritative invariants.
    reasons.extend(["fresh_balance_and_publication_lock_checks_unavailable",
                    "duty_window_staffing_qualification_rule_coverage_unverified",
                    "transactional_automatic_apply_unavailable"])
    return {"request_id": request_id, "policy_version": policy["version"] if policy else None,
            "outcome": "manual_review", "mutation_available": False,
            "applied": False, "reasons": reasons}
