"""/calendar-days - public / statutory / special-pay day flags (spec 1.5)."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import CalendarDayRequest
from emma_core.services import audit
from emma_core.services import calendar_days as svc

router = APIRouter(tags=["calendar"])
WRITE_ROLES = {"superintendent", "admin", "scheduler"}


@router.get("/calendar-days")
def list_calendar_days(date_from: Date | None = Query(default=None),
                       date_to: Date | None = Query(default=None),
                       include_shared: bool = Query(default=True),
                       ctx: AuthCtx = Depends(get_ctx)):
    """Defaults to the current month when no range is given."""
    return svc.list_days(ctx.client, ctx.facility_id, date_from=date_from,
                         date_to=date_to, include_shared=include_shared)


@router.post("/calendar-days", status_code=201)
def upsert_calendar_day(body: CalendarDayRequest, ctx: AuthCtx = Depends(get_ctx)):
    if str(ctx.profile.role) not in WRITE_ROLES:
        raise api_error(403, "forbidden",
                        "Only a superintendent, admin or scheduler may edit the calendar.")
    row = svc.upsert_day(
        ctx.client, ctx.facility_id, date=body.day_date, day_type=body.day_type,
        holiday_name=body.holiday_name, is_agency_allowed=body.is_agency_allowed,
        agency_cost_multiplier=body.agency_cost_multiplier,
        staff_cost_multiplier=body.staff_cost_multiplier, notes=body.notes,
    )
    audit.record(ctx.client, facility_id=ctx.facility_id, action="update",
                 entity_table="calendar_days", entity_id=row["id"], after=row,
                 actor_profile_id=ctx.profile_id, actor_email=ctx.profile.email,
                 reason=f"calendar day {body.day_date} set to {body.day_type}")
    return row
