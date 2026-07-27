"""/reports — generation plus the automated-report registry (spec 7.1 / 7.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import ReportGenerateRequest
from emma_core.services import reports as svc

router = APIRouter(tags=["reports"])


@router.get("/reports")
def list_reports(limit: int = Query(default=20, le=100), ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_reports(ctx.client, ctx.facility_id, limit=limit)


@router.get("/reports/types")
def report_types():
    return [{"report_type": k, "title": svc.TITLES.get(k, k)} for k in sorted(svc.GENERATORS)]


@router.get("/reports/schedules")
def schedules(ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_schedules(ctx.client, ctx.facility_id)


@router.post("/reports/schedules/{schedule_id}/run")
def run_schedule(schedule_id: str, ctx: AuthCtx = Depends(get_ctx)):
    if ctx.profile.role == "staff":
        raise api_error(403, "forbidden", "only a manager can generate reports")
    return svc.run_schedule(ctx.client, ctx.facility_id, schedule_id, ctx.profile_id)


@router.get("/reports/event-triggers")
def event_triggers(ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_event_triggers(ctx.client, ctx.facility_id)


@router.get("/reports/regulatory-docs")
def regulatory_docs(ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_regulatory_docs(ctx.client, ctx.facility_id)


@router.post("/reports/generate")
def generate(body: ReportGenerateRequest, ctx: AuthCtx = Depends(get_ctx)):
    if ctx.profile.role == "staff":
        raise api_error(403, "forbidden", "only a manager can generate reports")
    params = body.model_dump(exclude_none=True, exclude={"report_type"})
    return svc.generate(ctx.client, ctx.facility_id, body.report_type,
                        params={k: str(v) for k, v in params.items()},
                        profile_id=ctx.profile_id)


@router.get("/reports/download/{report_type}.csv")
def download(report_type: str, period_id: str | None = Query(default=None),
             ctx: AuthCtx = Depends(get_ctx)):
    """Generate on demand and stream as CSV — what the Reports page's cards link to."""
    params = {"period_id": period_id} if period_id else {}
    report = svc.generate(ctx.client, ctx.facility_id, report_type,
                          params=params, profile_id=ctx.profile_id, persist=False)
    return Response(
        content=svc.to_csv(report["payload"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report_type}.csv"'},
    )


@router.get("/reports/{report_id}")
def get_report(report_id: str, ctx: AuthCtx = Depends(get_ctx)):
    row = svc.get_report(ctx.client, ctx.facility_id, report_id)
    if not row:
        raise api_error(404, "not_found", "report not found")
    return row
