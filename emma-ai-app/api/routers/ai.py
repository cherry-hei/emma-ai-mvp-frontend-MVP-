"""/ai - the two assisted features, both answered from deterministic results.

Neither endpoint lets a model decide anything. The suggestion can only name
someone the candidate engine already cleared, and the compliance verdict is
computed before a model is asked to phrase it. When no provider is reachable
both still answer, with `explained` false.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.services import ai_compliance, ai_evidence, incidents

router = APIRouter(tags=["ai"])


class ComplianceQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    date: Date | None = None
    roster_version_id: str | None = None


@router.get("/ai/status")
def status(ctx: AuthCtx = Depends(get_ctx)) -> dict:
    """Which providers are wired, so the UI can say so instead of guessing."""
    from emma_core.services import ai_gateway

    return {"providers": [p.name for p in ai_gateway.default_gateway().providers],
            "intents": sorted(ai_compliance.INTENTS)}


@router.get("/sl-incidents/{incident_id}/ai-suggestion")
def replacement_suggestion(incident_id: str, ctx: AuthCtx = Depends(get_ctx)) -> dict:
    """Rank the cleared cover candidates for a vacant shift and explain the top one."""
    incident = incidents.get_incident(ctx.client, ctx.facility_id, incident_id)
    if not incident:
        raise api_error(404, "not_found", "incident not found")
    if not incident.get("shift_id"):
        raise api_error(422, "invalid_input",
                        "this incident has no roster shift to cover")
    return ai_evidence.suggest(ctx.client, ctx.facility_id, incident)


@router.post("/ai/compliance-qa")
def compliance_qa(body: ComplianceQuestion, ctx: AuthCtx = Depends(get_ctx)) -> dict:
    """Answer a compliance question from the checks this facility actually holds."""
    return ai_compliance.ask(
        ctx.client, ctx.facility_id, body.question,
        on_date=body.date, roster_version_id=body.roster_version_id).as_dict()


@router.get("/ai/compliance-qa")
def compliance_qa_get(question: str = Query(..., min_length=1, max_length=1000),
                      on_date: Date | None = Query(default=None, alias="date"),
                      roster_version_id: str | None = Query(default=None),
                      ctx: AuthCtx = Depends(get_ctx)) -> dict:
    """The same answer over GET, so a screen can link straight to one."""
    return ai_compliance.ask(
        ctx.client, ctx.facility_id, question,
        on_date=on_date, roster_version_id=roster_version_id).as_dict()
