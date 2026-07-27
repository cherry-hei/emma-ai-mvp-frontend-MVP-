"""Roster A/B/C: generate, poll, compare, validate, publish-guard.

POST /optimize-roster enqueues a background job (three ~10s CP-SAT solves) and
returns a pending job_id; the frontend polls /optimization-jobs/{id}. ?sync=true
blocks and returns the scored options inline. The solve writes back via the
service-role client (bypasses RLS, rows still stamped with facility_id); every
read uses the caller's RLS client, so results stay facility-scoped.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.constants import PUBLISH_THRESHOLD, JobStatus
from emma_core.db import get_service_client
from emma_core.models import (
    JobView, OptimizeRequest, OptimizeResponse, OptionScoreOut, ValidationOut,
    ViolationOut,
)
from emma_core.services import optimize as opt
from emma_core.services.compliance import compute_ratios
from emma_core.services.roster import get_roster_grid

router = APIRouter(tags=["optimize"])


class ValidateRequest(BaseModel):
    roster_version_id: str


def _to_option_score_out(row: dict, *, with_violations: bool = True) -> OptionScoreOut:
    cs = int(row.get("constraint_score") or 0)
    hv = int(row.get("hard_violation_count") or 0)
    return OptionScoreOut(
        roster_version_id=row["roster_version_id"],
        plan_mode=row.get("plan_mode", ""),
        constraint_score=cs, hard_violation_count=hv,
        soft_penalty_total=int(row.get("soft_penalty_total") or 0),
        objective_weights=row.get("objective_weights_json"),
        infeasible_reasons=row.get("infeasible_reasons_json") or [],
        publishable=(cs >= PUBLISH_THRESHOLD and hv == 0),
        version_label=row.get("version_label"),      # set by list_period_option_scores (compare)
        version_status=row.get("version_status"),
        violations=([ViolationOut.model_validate(v) for v in row.get("violations", [])]
                    if with_violations else []),
    )


# ── generate (async) + poll ──────────────────────────────────────────────────
def _authorize_optimize(req: OptimizeRequest, ctx: AuthCtx) -> None:
    """Stamp the tenant from the token and authorize caller-supplied ids under RLS
    before the service-role solver touches them — else a foreign source_version_id
    would leak another facility's roster."""
    req.facility_id = ctx.facility_id
    if req.created_by is None:
        req.created_by = ctx.profile_id
    if not ctx.client.table("roster_periods").select("id").eq("id", req.period_id).execute().data:
        raise api_error(404, "not_found", "roster period not found")
    if req.source_version_id and not (
            ctx.client.table("roster_versions").select("id")
            .eq("id", req.source_version_id).execute().data):
        raise api_error(404, "not_found", "source roster version not found")


@router.post("/optimize-roster", response_model=OptimizeResponse)
def optimize_roster(req: OptimizeRequest, background: BackgroundTasks,
                    sync: bool = Query(default=False),
                    ctx: AuthCtx = Depends(get_ctx)):
    _authorize_optimize(req, ctx)
    service_client = get_service_client()
    if sync:
        return opt.run_optimization(service_client, req)
    job_id = opt.enqueue_optimization(service_client, req)
    background.add_task(opt.run_optimization, service_client, req, job_id=job_id)
    return OptimizeResponse(job_id=job_id, status=JobStatus.PENDING, roster_options=[])


@router.post("/optimize-pareto", response_model=OptimizeResponse)
def optimize_pareto(req: OptimizeRequest, background: BackgroundTasks,
                    sync: bool = Query(default=False),
                    ctx: AuthCtx = Depends(get_ctx)):
    """Phase 3 multi-objective variant: sweep the weight space, discard dominated
    candidates and return the cost extreme, the satisfaction extreme and the knee.
    Same job/poll contract as /optimize-roster; the frontier lands in
    result_json.pareto."""
    _authorize_optimize(req, ctx)
    service_client = get_service_client()
    if sync:
        return opt.run_optimization(service_client, req, pareto=True)
    job_id = opt.enqueue_optimization(service_client, req)
    background.add_task(opt.run_optimization, service_client, req,
                        job_id=job_id, pareto=True)
    return OptimizeResponse(job_id=job_id, status=JobStatus.PENDING, roster_options=[])


@router.get("/optimization-jobs/{job_id}", response_model=JobView)
def optimization_job(job_id: str, ctx: AuthCtx = Depends(get_ctx)):
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise api_error(404, "not_found", "optimization job not found")
    row = opt.get_job(ctx.client, job_id)   # RLS-scoped — only own-facility jobs
    if not row:
        raise api_error(404, "not_found", "optimization job not found")
    return JobView.model_validate(row)


# ── option scores (compare / review) ─────────────────────────────────────────
@router.get("/roster-option-scores/compare/{period_id}")
def compare_options(period_id: str, ctx: AuthCtx = Depends(get_ctx)):
    rows = opt.list_period_option_scores(ctx.client, period_id)
    return {"period_id": period_id,
            "options": [_to_option_score_out(r, with_violations=False) for r in rows]}


@router.get("/roster-option-scores/{roster_version_id}", response_model=OptionScoreOut)
def option_scores(roster_version_id: str, ctx: AuthCtx = Depends(get_ctx)):
    row = opt.get_option_scores(ctx.client, roster_version_id)
    if row is None:
        raise api_error(404, "not_found", "no solver scores for this roster version")
    return _to_option_score_out(row)


# ── validate ──────────────────────────────────────────────────────────────────
@router.post("/validate-roster", response_model=ValidationOut)
def validate_roster(body: ValidateRequest, ctx: AuthCtx = Depends(get_ctx)):
    vid = body.roster_version_id
    # Solver option: return its persisted hard-constraint result.
    score = opt.get_option_scores(ctx.client, vid)
    if score is not None:
        out = _to_option_score_out(score)
        # passes == no hard violations; the publish threshold is enforced at publish time.
        return ValidationOut(
            roster_version_id=vid, method="solver-scored",
            passes=(out.hard_violation_count == 0), constraint_score=out.constraint_score,
            hard_violation_count=out.hard_violation_count, violations=out.violations,
        )
    # Manual roster (no solver score): live SWD ratio check across its dated shifts.
    grid = get_roster_grid(ctx.client, ctx.facility_id, version_id=vid, version_type=None)
    checks = []
    for d in grid.dates:
        checks.extend(compute_ratios(ctx.client, ctx.facility_id, d, roster_version_id=vid))
    breaches = [c for c in checks if not c.passes]
    return ValidationOut(
        roster_version_id=vid, method="ratio-check",
        # an empty roster covers nothing — not a vacuous pass.
        passes=bool(grid.dates) and not breaches,
        hard_violation_count=len(breaches), ratio_checks=checks,
    )
