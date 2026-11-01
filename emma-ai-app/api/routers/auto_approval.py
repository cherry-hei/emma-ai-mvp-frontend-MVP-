"""Owner-only review candidate; parent must register this router explicitly."""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from api.deps import AuthCtx, get_ctx
from emma_core.services import auto_approval as svc

router = APIRouter(prefix="/auto-approval", tags=["auto-approval"])


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_policy_version: StrictInt = Field(ge=1)


@router.get("/policy")
def get_policy(ctx: AuthCtx = Depends(get_ctx)):
    return {"policy": svc.read_policy(ctx), "mutation_available": False}


@router.post("/policy", status_code=201)
def create_policy(body: svc.PolicyWrite, ctx: AuthCtx = Depends(get_ctx)):
    return svc.write_policy(ctx, body, create=True)


@router.patch("/policy")
def patch_policy(body: svc.PolicyWrite, ctx: AuthCtx = Depends(get_ctx)):
    return svc.write_policy(ctx, body, create=False)


@router.post("/evaluations/{request_id}")
def evaluate(request_id: UUID, body: EvaluationRequest, ctx: AuthCtx = Depends(get_ctx)):
    return svc.evaluate(ctx, str(request_id), body.expected_policy_version)
