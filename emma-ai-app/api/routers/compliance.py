"""/compliance/ratio — per-shift staff-to-resident ratio check for one day.

Pass ``roster_version_id`` to scope the count to a specific roster version; without
it, shifts from co-existing A/B/C drafts on the same dates would double-count.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, get_ctx
from emma_core.models import RatioResult
from emma_core.services.compliance import compute_ratios

router = APIRouter(tags=["compliance"])


@router.get("/compliance/ratio", response_model=list[RatioResult])
def ratio(on_date: Date = Query(..., alias="date"),
          roster_version_id: str | None = Query(default=None),
          ctx: AuthCtx = Depends(get_ctx)):
    return compute_ratios(ctx.client, ctx.facility_id, on_date,
                          roster_version_id=roster_version_id)
