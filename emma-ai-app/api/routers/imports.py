"""/imports - load a real roster Excel workbook into the facility (spec 1.4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.db import get_service_client
from emma_core.importers import LAYOUT_NAMES
from emma_core.services import imports as svc

router = APIRouter(tags=["imports"])
WRITE_ROLES = {"superintendent", "admin", "scheduler"}
# openpyxl loads the whole workbook, so the ceiling is memory, not storage. The
# real rosters are ~400 KB; 20 MB leaves room for a home with a year per file.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.get("/imports")
def list_imports(limit: int = Query(default=20, le=100),
                 ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_jobs(ctx.client, ctx.facility_id, limit=limit)


@router.get("/imports/layouts")
def layouts():
    """The roster layouts the parser recognises."""
    return [{"layout": name} for name in LAYOUT_NAMES]


@router.get("/imports/{job_id}")
def get_import(job_id: str, ctx: AuthCtx = Depends(get_ctx)):
    job = svc.get_job(ctx.client, ctx.facility_id, job_id)
    if not job:
        raise api_error(404, "not_found", "import job not found")
    return job


@router.post("/imports/roster-excel", status_code=201)
async def import_roster_excel(
    file: UploadFile = File(..., description="The home's roster .xlsx"),
    mode: str = Form(default="validate", description="validate | commit"),
    variant: str = Form(default="after", description="Home A's before | after sheet"),
    version_label: str | None = Form(default=None),
    version_status: str = Form(default="draft", description="draft | published"),
    replace_period: bool = Form(default=True),
    ctx: AuthCtx = Depends(get_ctx),
):
    """Parse an uploaded roster workbook; in `commit` mode also load it.

    `validate` is the default on purpose: an import is easier to review than to
    undo, so the caller sees the validation summary before anything is written.
    """
    if str(ctx.profile.role) not in WRITE_ROLES:
        raise api_error(403, "forbidden",
                        "Only a superintendent, admin or scheduler may import a roster.")
    content = await file.read()
    if not content:
        raise api_error(422, "empty_upload", "The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise api_error(413, "upload_too_large",
                        f"Workbook exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    # Creating staff records and making an imported roster operative are trusted
    # server operations; the job and issue rows stay on the caller's RLS client.
    return svc.run_import(
        ctx.client, get_service_client(), ctx.facility_id,
        filename=file.filename or "roster.xlsx", content=content, mode=mode,
        variant=variant, version_label=version_label,
        version_status=version_status, replace_period=replace_period,
        profile_id=ctx.profile_id, actor_email=ctx.profile.email,
    )
