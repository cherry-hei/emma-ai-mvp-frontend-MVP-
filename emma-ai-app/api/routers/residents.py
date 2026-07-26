"""/units + /resident-counts — units and the daily resident-count ratio denominator."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, get_ctx
from emma_core.models import ResidentCountOut, ResidentCountRequest, Unit
from emma_core.services import residents as svc

router = APIRouter(tags=["residents"])


@router.get("/units", response_model=list[Unit])
def units(ctx: AuthCtx = Depends(get_ctx)):
    return svc.get_units(ctx.client, ctx.facility_id)


@router.get("/resident-counts", response_model=list[ResidentCountOut])
def resident_counts(on_date: Date | None = Query(default=None, alias="date"),
                    ctx: AuthCtx = Depends(get_ctx)):
    return svc.get_resident_counts(ctx.client, ctx.facility_id, on_date=on_date)


@router.post("/resident-counts")
def set_resident_count(body: ResidentCountRequest, ctx: AuthCtx = Depends(get_ctx)):
    svc.set_resident_count(
        ctx.client, facility_id=ctx.facility_id, date=body.date,
        unit_id=body.unit_id, care_level=body.care_level, count=body.count,
        entered_by=ctx.profile_id,
    )
    return {"ok": True}
