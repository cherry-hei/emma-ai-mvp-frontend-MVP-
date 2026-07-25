"""/staff — facility staff directory for the personnel/admin screens and the
shift-editor dropdowns."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, get_ctx
from emma_core.models import StaffOut
from emma_core.services import staff as svc

router = APIRouter(tags=["staff"])


@router.get("/staff", response_model=list[StaffOut])
def list_staff(search: str | None = Query(default=None),
               rank: str | None = Query(default=None),
               ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_staff(ctx.client, ctx.facility_id, search=search, rank=rank)
