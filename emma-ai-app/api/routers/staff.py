"""/staff — staff directory (hours, status, certs) + /staff/{id} profile detail."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import StaffDetail, StaffOut
from emma_core.services import staff as svc

router = APIRouter(tags=["staff"])


@router.get("/staff", response_model=list[StaffOut])
def list_staff(search: str | None = Query(default=None),
               rank: str | None = Query(default=None),
               ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_staff(ctx.client, ctx.facility_id, search=search, rank=rank)


@router.get("/staff/{staff_id}", response_model=StaffDetail)
def staff_detail(staff_id: str, ctx: AuthCtx = Depends(get_ctx)):
    detail = svc.get_staff_detail(ctx.client, ctx.facility_id, staff_id)
    if detail is None:
        raise api_error(404, "not_found", "staff member not found")
    return detail
