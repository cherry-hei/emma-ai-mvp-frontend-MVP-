"""/compliance — staffing-ratio checks and the live threshold monitors.

Scope ratio reads with roster_version_id, else co-existing A/B/C drafts
double-count staff and a failing roster looks compliant.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, get_ctx
from emma_core.models import RatioResult
from emma_core.services.compliance import (
    compute_ratios, minute_ratio, ratio_series, threshold_monitors,
)

router = APIRouter(tags=["compliance"])


@router.get("/compliance/ratio", response_model=list[RatioResult])
def ratio(on_date: Date = Query(..., alias="date"),
          roster_version_id: str | None = Query(default=None),
          ctx: AuthCtx = Depends(get_ctx)):
    return compute_ratios(ctx.client, ctx.facility_id, on_date,
                          roster_version_id=roster_version_id)


@router.get("/compliance/minute-ratio")
def minute_level_ratio(on_date: Date = Query(..., alias="date"),
                       roster_version_id: str | None = Query(default=None),
                       ctx: AuthCtx = Depends(get_ctx)):
    """Minute-level overlap between actual shifts and each statutory window —
    the audit-grade check (spec 3.6). Reports breach minutes per rule."""
    return minute_ratio(ctx.client, ctx.facility_id, on_date,
                        roster_version_id=roster_version_id)


@router.get("/compliance/ratio-series")
def ratio_days(date_from: Date = Query(...), date_to: Date = Query(...),
               roster_version_id: str | None = Query(default=None),
               ctx: AuthCtx = Depends(get_ctx)):
    return ratio_series(ctx.client, ctx.facility_id, date_from, date_to,
                        roster_version_id=roster_version_id)


@router.get("/compliance/thresholds")
def thresholds(ctx: AuthCtx = Depends(get_ctx)):
    """Live threshold monitors: certificate expiry, PT cap, AN limit, RN-absent
    shifts, CL accrual and occupancy — measured, not configured."""
    return threshold_monitors(ctx.client, ctx.facility_id)
