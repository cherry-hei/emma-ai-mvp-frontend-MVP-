"""/dashboard, /roi, /kpi, /insights - the read-only analytics surface.

These are aggregates over many tables; each returns the exact shape its screen
renders so a page paints from one round trip.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import RoiSettingsPatch
from emma_core.services import dashboard as dash
from emma_core.services import insights as insight_svc
from emma_core.services import kpi as kpi_svc
from emma_core.services import roi as roi_svc

router = APIRouter(tags=["analytics"])


# ── dashboard ────────────────────────────────────────────────────────────────
@router.get("/dashboard/summary")
def dashboard_summary(ctx: AuthCtx = Depends(get_ctx)):
    return {**dash.summary(ctx.client, ctx.facility_id),
            "highlights": insight_svc.facility_highlights(ctx.client, ctx.facility_id)}


# ── ROI ──────────────────────────────────────────────────────────────────────
@router.get("/roi/settings")
def roi_settings(ctx: AuthCtx = Depends(get_ctx)):
    return roi_svc.get_settings(ctx.client, ctx.facility_id)


@router.put("/roi/settings")
def update_roi_settings(body: RoiSettingsPatch, ctx: AuthCtx = Depends(get_ctx)):
    if ctx.profile.role == "staff":
        raise api_error(403, "forbidden", "only a manager can change the ROI baseline")
    return roi_svc.update_settings(ctx.client, ctx.facility_id,
                                   body.model_dump(exclude_none=True), ctx.profile_id)


@router.get("/roi/summary")
def roi_summary(on: Date | None = Query(default=None, alias="date"),
                ctx: AuthCtx = Depends(get_ctx)):
    return roi_svc.summary(ctx.client, ctx.facility_id, on)


# ── KPI framework ────────────────────────────────────────────────────────────
@router.get("/kpi/overview")
def kpi_overview(period_id: str | None = Query(default=None),
                 ctx: AuthCtx = Depends(get_ctx)):
    return kpi_svc.overview(ctx.client, ctx.facility_id, period_id)


@router.get("/kpi/conflict-rate")
def conflict_rate(period_id: str | None = Query(default=None),
                  ctx: AuthCtx = Depends(get_ctx)):
    return kpi_svc.conflict_rate(ctx.client, ctx.facility_id, period_id)


@router.get("/kpi/an-gini")
def an_gini(period_id: str | None = Query(default=None), ctx: AuthCtx = Depends(get_ctx)):
    return kpi_svc.an_gini(ctx.client, ctx.facility_id, period_id)


@router.get("/kpi/shift-fairness")
def shift_fairness(period_id: str | None = Query(default=None),
                   ctx: AuthCtx = Depends(get_ctx)):
    return kpi_svc.shift_fairness(ctx.client, ctx.facility_id, period_id)


@router.get("/kpi/ai-acceptance")
def ai_acceptance(period_id: str | None = Query(default=None),
                  ctx: AuthCtx = Depends(get_ctx)):
    return kpi_svc.ai_acceptance(ctx.client, ctx.facility_id, period_id)


@router.get("/kpi/external-workforce")
def external_workforce(period_id: str | None = Query(default=None),
                       ctx: AuthCtx = Depends(get_ctx)):
    return kpi_svc.external_workforce(ctx.client, ctx.facility_id, period_id)


@router.get("/kpi/staffing-ratio-compliance")
def staffing_ratio_compliance(period_id: str | None = Query(default=None),
                              ctx: AuthCtx = Depends(get_ctx)):
    return kpi_svc.staffing_ratio_compliance(ctx.client, ctx.facility_id, period_id)


# ── staff AI analysis ────────────────────────────────────────────────────────
@router.get("/staff/{staff_id}/ai-analysis")
def staff_ai_analysis(staff_id: str, ctx: AuthCtx = Depends(get_ctx)):
    return insight_svc.staff_analysis(ctx.client, ctx.facility_id, staff_id)
