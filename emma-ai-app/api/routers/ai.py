"""/ai - the two assisted features, both answered from deterministic results.

Neither endpoint lets a model decide anything. The suggestion can only name
someone the candidate engine already cleared, and the compliance verdict is
computed before a model is asked to phrase it. When no provider is reachable
both still answer, with `explained` false.
"""
from __future__ import annotations

from datetime import date as Date
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.deps import AuthCtx, api_error, get_ctx, require_read
from emma_core.permissions import Feature
from emma_core.services import ai_compliance, ai_evidence, incidents

router = APIRouter(tags=["ai"])


class ComplianceQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    date: Date | None = None
    roster_version_id: str | None = None
    unit_id: str | None = None
    intent: Literal["staffing_ratio", "breach_minutes", "thresholds", "roster_validation"] | None = None
    explain: bool = True


@router.get("/ai/status")
def status(ctx: AuthCtx = Depends(get_ctx)) -> dict:
    """Which providers are wired, so the UI can say so instead of guessing."""
    from emma_core.services import ai_gateway

    from emma_core.config import settings
    providers = ai_gateway.default_gateway(facility_id=ctx.facility_id).providers
    enabled = any(p.name == "bedrock" for p in providers)
    return {"providers": [p.name for p in providers],
            "intents": sorted(ai_compliance.INTENTS),
            "bedrock_enabled": enabled,
            "model_id": settings.bedrock_model_id if enabled else None,
            "inference_region": settings.bedrock_region if enabled else None}


@router.get("/sl-incidents/{incident_id}/ai-suggestion")
def replacement_suggestion(incident_id: str, ctx: AuthCtx = Depends(require_read(Feature.COVER_VIEW_ANALYSIS))) -> dict:
    """Rank the cleared cover candidates for a vacant shift and explain the top one."""
    incident = incidents.get_incident(ctx.client, ctx.facility_id, incident_id)
    if not incident:
        raise api_error(404, "not_found", "incident not found")
    if not incident.get("shift_id"):
        raise api_error(422, "invalid_input",
                        "this incident has no roster shift to cover")
    return ai_evidence.suggest(ctx.client, ctx.facility_id, incident)


@router.post("/ai/compliance-qa")
def compliance_qa(body: ComplianceQuestion, ctx: AuthCtx = Depends(require_read(Feature.COMPLIANCE))) -> dict:
    """Answer a compliance question from the checks this facility actually holds."""
    from emma_core.services import audit
    answer = ai_compliance.ask(
        ctx.client, ctx.facility_id, body.question,
        on_date=body.date, roster_version_id=body.roster_version_id,
        unit_id=body.unit_id,
        intent=body.intent, explain=body.explain).as_dict()
    request_id = str(uuid4())
    audit.record(ctx.client, facility_id=ctx.facility_id, action="compliance.qa",
                 entity_table="roster_versions", entity_id=body.roster_version_id,
                 actor_profile_id=ctx.profile_id, request_id=request_id,
                 after={key: answer[key] for key in
                        ("intent", "verdict", "explained", "degraded", "provider", "metrics")})
    answer["request_id"] = request_id
    return answer


@router.get("/ai/compliance-qa")
def compliance_qa_get(question: str = Query(..., min_length=1, max_length=1000),
                      on_date: Date | None = Query(default=None, alias="date"),
                      roster_version_id: str | None = Query(default=None),
                      unit_id: str | None = Query(default=None),
                      ctx: AuthCtx = Depends(require_read(Feature.COMPLIANCE))) -> dict:
    """The same answer over GET, so a screen can link straight to one."""
    return compliance_qa(ComplianceQuestion(question=question, date=on_date,
        roster_version_id=roster_version_id, unit_id=unit_id), ctx)
