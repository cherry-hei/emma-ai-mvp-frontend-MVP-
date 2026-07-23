"""/optimize-roster + /optimization-jobs — thin HTTP wrapper over
``emma_core.services.optimize``.

All logic lives in the service; the Reflex UI calls the same functions in-process
(no HTTP needed). Kept deliberately minimal.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException

from emma_core.db import get_service_client, get_user_client
from emma_core.models import JobView, OptimizeRequest, OptimizeResponse
from emma_core.services import optimize as opt

router = APIRouter(tags=["optimize"])


def _client(authorization: str | None):
    """Prefer the caller's token (RLS-scoped); fall back to the service client."""
    if authorization and authorization.lower().startswith("bearer "):
        return get_user_client(authorization.split(None, 1)[1])
    return get_service_client()


@router.post("/optimize-roster", response_model=OptimizeResponse)
def optimize_roster(req: OptimizeRequest, authorization: str | None = Header(default=None)):
    return opt.run_optimization(_client(authorization), req, persist=req.writeback.persist)


@router.get("/optimization-jobs/{job_id}", response_model=JobView)
def optimization_job(job_id: str):
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="optimization job not found")
    row = opt.get_job(get_service_client(), job_id)
    if not row:
        raise HTTPException(status_code=404, detail="optimization job not found")
    return JobView.model_validate(row)
