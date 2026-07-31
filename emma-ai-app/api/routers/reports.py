"""/reports - generation plus the automated-report registry (spec 7.1 / 7.2).

Matrix row "Reports R1-R4": F for OWNER, V for NURSE_MGR, V + download for
ADMIN_CLERK, hidden from ALLIED_HEALTH and FRONTLINE. Reading and downloading a
report is therefore open to managers; *generating* one persists a record and is
OWNER-only. The previous `role == "staff"` literal let ALLIED_HEALTH through and
left every GET here open to any signed-in account.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, require_read, require_write
from emma_core.models import ReportGenerateRequest, ReportRequest
from emma_core.permissions import Feature
from emma_core.services import reports as svc

router = APIRouter(tags=["reports"])

# The named endpoints the delivery plan lists, each fixing one report_type. They
# share `svc.generate`, so a report requested by name is byte-for-byte the report
# requested by type - and equally reproducible from its stored payload.
NAMED_REPORTS = {
    "compliance": "compliance_summary",   # 7.1
    "roster": "roster_export",            # 7.2
    "staffing-ratio": "staffing_ratio",   # 3.7
    "evidence": "evidence_pack",          # 1.6 / 8.2
}


@router.get("/reports")
def list_reports(limit: int = Query(default=20, le=100),
                 ctx: AuthCtx = Depends(require_read(Feature.REPORTS))):
    return svc.list_reports(ctx.client, ctx.facility_id, limit=limit)


@router.get("/reports/types")
def report_types(ctx: AuthCtx = Depends(require_read(Feature.REPORTS))):
    return [{"report_type": k, "title": svc.TITLES.get(k, k)} for k in sorted(svc.GENERATORS)]


@router.get("/reports/schedules")
def schedules(ctx: AuthCtx = Depends(require_read(Feature.REPORTS))):
    return svc.list_schedules(ctx.client, ctx.facility_id)


@router.post("/reports/schedules/{schedule_id}/run")
def run_schedule(schedule_id: str,
                 ctx: AuthCtx = Depends(require_write(Feature.REPORTS))):
    return svc.run_schedule(ctx.client, ctx.facility_id, schedule_id, ctx.profile_id)


@router.get("/reports/event-triggers")
def event_triggers(ctx: AuthCtx = Depends(require_read(Feature.REPORTS))):
    return svc.list_event_triggers(ctx.client, ctx.facility_id)


@router.get("/reports/regulatory-docs")
def regulatory_docs(ctx: AuthCtx = Depends(require_read(Feature.REPORTS))):
    return svc.list_regulatory_docs(ctx.client, ctx.facility_id)


@router.post("/reports/generate")
def generate(body: ReportGenerateRequest,
             ctx: AuthCtx = Depends(require_write(Feature.REPORTS))):
    params = body.model_dump(exclude_none=True, exclude={"report_type"})
    return svc.generate(ctx.client, ctx.facility_id, body.report_type,
                        params={k: str(v) for k, v in params.items()},
                        profile_id=ctx.profile_id)


@router.post("/reports/{name}", status_code=201)
def generate_named(name: str, body: ReportRequest | None = None,
                   ctx: AuthCtx = Depends(require_write(Feature.REPORTS))):
    """POST /reports/compliance | /reports/roster | /reports/staffing-ratio |
    /reports/evidence - the named exports, each a fixed report type."""
    report_type = NAMED_REPORTS.get(name)
    if not report_type:
        raise api_error(404, "unknown_report",
                        f"No report named {name!r} (expected one of "
                        f"{', '.join(sorted(NAMED_REPORTS))}).")
    params = (body or ReportRequest()).model_dump(exclude_none=True)
    return svc.generate(ctx.client, ctx.facility_id, report_type,
                        params={k: str(v) for k, v in params.items()},
                        profile_id=ctx.profile_id)


@router.get("/reports/download/{report_type}.csv")
def download(report_type: str, period_id: str | None = Query(default=None),
             ctx: AuthCtx = Depends(require_read(Feature.REPORTS))):
    """Generate on demand and stream as CSV - what the Reports page's cards link to.

    A read despite calling `generate`: nothing is persisted (`persist=False`), and
    the matrix grants ADMIN_CLERK download rights explicitly."""
    params = {"period_id": period_id} if period_id else {}
    report = svc.generate(ctx.client, ctx.facility_id, report_type,
                          params=params, profile_id=ctx.profile_id, persist=False)
    return Response(
        content=svc.to_csv(report["payload"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report_type}.csv"'},
    )


@router.get("/reports/{report_id}")
def get_report(report_id: str, ctx: AuthCtx = Depends(require_read(Feature.REPORTS))):
    row = svc.get_report(ctx.client, ctx.facility_id, report_id)
    if not row:
        raise api_error(404, "not_found", "report not found")
    return row
