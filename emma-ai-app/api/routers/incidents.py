"""/sl-incidents, /replacement-candidates, /alerts, /future-debt — the Alert
centre and emergency-cover loop (spec 4.3 / 4.5 / 3.8)."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import IncidentCreate, IncidentResolveRequest
from emma_core.services import incidents as svc
from emma_core.services.me import resolve_staff_id

router = APIRouter(tags=["alerts"])


@router.get("/sl-incidents")
def list_incidents(status: str | None = Query(default=None),
                   since: Date | None = Query(default=None),
                   staff_id: str | None = Query(default=None),
                   limit: int = Query(default=50, le=200),
                   ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_incidents(ctx.client, ctx.facility_id, status=status, since=since,
                              staff_id=staff_id, limit=limit)


@router.get("/sl-incidents/stats")
def incident_stats(on: Date | None = Query(default=None, alias="date"),
                   ctx: AuthCtx = Depends(get_ctx)):
    return svc.stats(ctx.client, ctx.facility_id, on)


@router.post("/sl-incidents", status_code=201)
def create_incident(body: IncidentCreate, ctx: AuthCtx = Depends(get_ctx)):
    staff_id = body.staff_id or resolve_staff_id(ctx.profile)
    return svc.open_incident(ctx.client, ctx.facility_id, staff_id=staff_id,
                             incident_type=body.incident_type, on_date=body.date,
                             reason=body.reason, shift_id=body.shift_id)


@router.get("/sl-incidents/{incident_id}")
def get_incident(incident_id: str, ctx: AuthCtx = Depends(get_ctx)):
    row = svc.get_incident(ctx.client, ctx.facility_id, incident_id)
    if not row:
        raise api_error(404, "not_found", "incident not found")
    return row


@router.get("/replacement-candidates")
def replacement_candidates(incident_id: str = Query(...),
                           compliance_checked: bool = Query(default=True),
                           refresh: bool = Query(default=False),
                           limit: int = Query(default=5, le=50),
                           ctx: AuthCtx = Depends(get_ctx)):
    """Ranked cover options. compliance_checked=true (the default) returns only
    candidates that break no rest, hour, leave or eligibility rule."""
    if refresh:
        svc.refresh_candidates(ctx.client, ctx.facility_id, incident_id)
    return svc.list_candidates(ctx.client, ctx.facility_id, incident_id,
                               compliance_checked=compliance_checked, limit=limit)


@router.post("/sl-incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str, body: IncidentResolveRequest,
                     ctx: AuthCtx = Depends(get_ctx)):
    if ctx.profile.role == "staff":
        raise api_error(403, "forbidden", "only a manager can assign emergency cover")
    return svc.resolve_incident(ctx.client, ctx.facility_id, incident_id,
                                replacement_staff_id=body.replacement_staff_id,
                                profile_id=ctx.profile_id, auto=body.auto, note=body.note)


@router.get("/alerts")
def alerts(ctx: AuthCtx = Depends(get_ctx)):
    return svc.active_alerts(ctx.client, ctx.facility_id)


@router.get("/future-debt")
def future_debt(staff_id: str | None = Query(default=None),
                status: str = Query(default="open"),
                ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_future_debt(ctx.client, ctx.facility_id,
                                staff_id=staff_id, status=status)
