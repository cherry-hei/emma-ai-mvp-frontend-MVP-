"""/sl-incidents, /replacement-candidates, /alerts, /future-debt - the Alert
centre and emergency-cover loop (spec 4.3 / 4.5 / 3.8)."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import (
    IncidentCreate, IncidentResolveRequest, OfferDecisionRequest,
    ReplacementOfferRequest,
)
from emma_core.services import audit, incidents as svc
from emma_core.services import replacement_offers as offers
from emma_core.services.me import resolve_staff_id

router = APIRouter(tags=["alerts"])


# Who called in sick, and who ended up covering it.
def _audit(ctx: AuthCtx, action: str, *, entity_id: str | None = None,
           before: dict | None = None, after: dict | None = None) -> None:
    audit.record(
        ctx.client, facility_id=ctx.facility_id, action=action,
        entity_table="sl_incidents", entity_id=entity_id,
        before=before, after=after,
        actor_profile_id=ctx.profile_id, actor_email=ctx.profile.email,
    )


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
    row = svc.open_incident(ctx.client, ctx.facility_id, staff_id=staff_id,
                            incident_type=body.incident_type, on_date=body.date,
                            reason=body.reason, shift_id=body.shift_id)
    _audit(ctx, "create", entity_id=row["id"],
           after={"staff_id": staff_id, "shift_id": body.shift_id,
                  "incident_type": body.incident_type, "date": body.date,
                  "replacement_status": "open"})
    return row


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
    before = svc.get_incident(ctx.client, ctx.facility_id, incident_id)
    result = svc.resolve_incident(ctx.client, ctx.facility_id, incident_id,
                                  replacement_staff_id=body.replacement_staff_id,
                                  profile_id=ctx.profile_id, auto=body.auto,
                                  note=body.note)
    incident = result["incident"]
    # The incident alone does not show that someone now owes hours.
    debts = [{"debt_type": d.get("debt_type"), "quantity": d.get("quantity"),
              "unit": d.get("unit")} for d in (result.get("future_debts") or [])]
    _audit(ctx, "update", entity_id=incident_id,
           before={"replacement_status": (before or {}).get("replacement_status"),
                   "replacement_staff_id": (before or {}).get("replacement_staff_id")},
           after={"replacement_status": incident.get("replacement_status"),
                  "replacement_staff_id": incident.get("replacement_staff_id"),
                  "resolution_minutes": result.get("resolution_minutes"),
                  "auto_resolved": incident.get("auto_resolved"),
                  "future_debts": debts})
    return result


@router.get("/alerts")
def alerts(ctx: AuthCtx = Depends(get_ctx)):
    return svc.active_alerts(ctx.client, ctx.facility_id)


@router.get("/future-debt")
def future_debt(staff_id: str | None = Query(default=None),
                status: str = Query(default="open"),
                ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_future_debt(ctx.client, ctx.facility_id,
                                staff_id=staff_id, status=status)


# ── replacement offers ───────────────────────────────────────────────────────
@router.post("/sl-incidents/{incident_id}/offers", status_code=201)
def make_offers(incident_id: str, body: ReplacementOfferRequest,
                ctx: AuthCtx = Depends(get_ctx)):
    if ctx.profile.role == "staff":
        raise api_error(403, "forbidden", "only a manager can ask someone to cover")
    rows = offers.offer(ctx.client, ctx.facility_id, incident_id,
                        staff_ids=body.staff_ids, profile_id=ctx.profile_id,
                        note=body.note)
    for row in rows:
        _audit(ctx, "create", entity_id=incident_id,
               after={"offer_id": row["id"], "offered_staff_id": row["offered_staff_id"]})
    return rows


@router.get("/sl-incidents/{incident_id}/offers")
def list_incident_offers(incident_id: str, ctx: AuthCtx = Depends(get_ctx)):
    return offers.list_offers(ctx.client, ctx.facility_id, incident_id=incident_id)


@router.post("/replacement-offers/{offer_id}/approve")
def approve_offer(offer_id: str, body: OfferDecisionRequest,
                  ctx: AuthCtx = Depends(get_ctx)):
    if ctx.profile.role == "staff":
        raise api_error(403, "forbidden", "only a manager can assign emergency cover")
    return offers.approve(ctx.client, ctx.facility_id, offer_id,
                          profile_id=ctx.profile_id, note=body.note)


@router.patch("/replacement-offers/{offer_id}/withdraw")
def withdraw_offer(offer_id: str, ctx: AuthCtx = Depends(get_ctx)):
    if ctx.profile.role == "staff":
        raise api_error(403, "forbidden", "only a manager can withdraw a cover request")
    return offers.withdraw(ctx.client, ctx.facility_id, offer_id,
                           profile_id=ctx.profile_id)
