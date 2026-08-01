"""Roster Excel import jobs (spec 1.4).

Every upload becomes an `import_jobs` row, whether it is a dry-run validation or
a commit, so "where did this roster come from?" has an answer with a file name, a
digest and a timestamp against it. Whatever the parser could not resolve is
written to `import_issues` against its exact source cell, which is the validation
summary the acceptance criteria asks for.

Two modes, one code path:

``validate``
    Parse, report, write nothing to the roster. The job row and its issues are
    still recorded - a rejected file is evidence too.
``commit``
    The same parse, then `importers.loader.apply` writes the roster.

The commit path needs the service-role client: creating staff records and making
an imported "as worked" roster operative are trusted server operations, not
tenant writes. The job and issue rows stay on the caller's RLS-scoped client so
they are visible to exactly the facility that uploaded them.
"""
from __future__ import annotations

import hashlib
import io

from .. import importers
from ..importers import loader
from ._common import now_iso
from . import audit

MODES = ("validate", "commit")
# Home A publishes each cycle twice: the plan, then the roster as worked.
VARIANTS = ("after", "before")


def list_jobs(client, facility_id: str, *, limit: int = 20) -> list[dict]:
    # SQL: select id, source_name, source_layout, mode, status, period_id,
    #             roster_version_id, summary_json, created_at, completed_at
    #      from import_jobs
    #      where facility_id = :facility_id
    #      order by created_at desc
    #      limit :limit
    return (client.table("import_jobs")
            .select("id,source_name,source_layout,source_sha256,mode,status,"
                    "period_id,roster_version_id,summary_json,error_json,"
                    "created_at,completed_at")
            .eq("facility_id", facility_id)
            .order("created_at", desc=True).limit(limit).execute().data)


def get_job(client, facility_id: str, job_id: str, *,
            issue_limit: int = 200) -> dict | None:
    """One job with its issues - what the import screen shows after an upload."""
    # SQL: select * from import_jobs
    #      where facility_id = :facility_id and id = :job_id
    rows = (client.table("import_jobs").select("*")
            .eq("facility_id", facility_id).eq("id", job_id).execute().data)
    if not rows:
        return None
    # SQL: select * from import_issues where job_id = :job_id
    #      order by severity, created_at
    #      limit :issue_limit
    issues = (client.table("import_issues").select("*")
              .eq("job_id", job_id).order("severity").order("created_at")
              .limit(issue_limit).execute().data)
    return {**rows[0], "issues": issues}


def run_import(client, service_client, facility_id: str, *, filename: str,
               content: bytes, mode: str = "validate", variant: str = "after",
               version_label: str | None = None, version_status: str = "draft",
               profile_id: str | None = None, actor_email: str | None = None,
               replace_period: bool = True,
               write_period_records: bool = True) -> dict:
    """Parse an uploaded workbook and, in commit mode, load it.

    Raises ``ValueError`` for anything the caller can fix - an unreadable
    workbook, an unknown layout, or a workbook belonging to another facility -
    which the API maps to a 422 rather than a 500.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {', '.join(VARIANTS)}")

    facility = _facility(client, facility_id)
    parsed = _parse(content, filename, variant)
    if parsed.facility_code != facility["code"]:
        raise ValueError(
            f"{filename} is a Home {parsed.facility_code} roster; you are signed "
            f"in to Home {facility['code']}")

    job = _create_job(client, facility_id, parsed, filename, content, mode,
                      profile_id)
    try:
        result = loader.apply(
            service_client, parsed, mode=mode, version_label=version_label,
            version_status=version_status, created_by=profile_id,
            replace_period=replace_period,
            write_period_records=write_period_records)
    except Exception as exc:  # noqa: BLE001 - recorded on the job, then re-raised
        _fail_job(client, job["id"], exc)
        raise

    _record_issues(client, facility_id, job["id"], parsed, result.warnings)
    summary = {**parsed.summary(), "load": result.as_dict()}
    job = _complete_job(client, job["id"], summary, result)
    audit.record(
        client, facility_id=facility_id, action="import",
        entity_table="import_jobs", entity_id=job["id"],
        after={"source_name": filename, "mode": mode,
               "roster_version_id": result.roster_version_id,
               "cells": summary.get("cells_parsed")},
        actor_profile_id=profile_id, actor_email=actor_email,
        reason=f"{mode} import of {filename}")
    return get_job(client, facility_id, job["id"]) or job


# ── internals ────────────────────────────────────────────────────────────────
def _facility(client, facility_id: str) -> dict:
    # SQL: select id, code, name from facilities where id = :facility_id
    rows = (client.table("facilities").select("id,code,name")
            .eq("id", facility_id).execute().data)
    if not rows:
        raise ValueError("facility not found")
    return rows[0]


def _parse(content: bytes, filename: str, variant: str):
    try:
        return importers.parse_workbook(
            io.BytesIO(content), source_name=filename, variant=variant)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - openpyxl raises many shapes
        raise ValueError(f"{filename} could not be read as an Excel workbook: "
                         f"{exc}") from exc


def _create_job(client, facility_id: str, parsed, filename: str, content: bytes,
                mode: str, profile_id: str | None) -> dict:
    # SQL: insert into import_jobs (facility_id, source_name, source_layout,
    #        source_sha256, mode, status, created_by, started_at)
    #      values (..., 'running', :profile_id, now()) returning *
    return client.table("import_jobs").insert({
        "facility_id": facility_id, "source_name": filename,
        "source_layout": parsed.layout,
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "mode": mode, "status": "running", "created_by": profile_id,
        "started_at": now_iso(),
    }).execute().data[0]


def _record_issues(client, facility_id: str, job_id: str, parsed,
                   load_warnings: list[dict] | None = None) -> None:
    """Persist the parser's findings and the loader's, against one job."""
    rows = [issue.as_row() for issue in parsed.issues]
    for warning in load_warnings or []:
        rows.append({"severity": "warning", "code": "load_warning", "sheet": None,
                     "cell_ref": None, "raw_value": None, "message": "", **warning})
    if not rows:
        return
    # SQL: insert into import_issues (facility_id, job_id, severity, code, sheet,
    #        cell_ref, raw_value, message)
    #      values ...
    client.table("import_issues").insert([
        {"facility_id": facility_id, "job_id": job_id, **row} for row in rows
    ]).execute()


def _complete_job(client, job_id: str, summary: dict,
                  result: loader.LoadResult) -> dict:
    # SQL: update import_jobs
    #      set status = 'completed', summary_json = :summary, period_id = ...,
    #          roster_version_id = ..., completed_at = now()
    #      where id = :job_id
    #      returning *
    return (client.table("import_jobs").update({
        "status": "completed", "summary_json": summary,
        "period_id": result.period_id,
        "roster_version_id": result.roster_version_id,
        "completed_at": now_iso(),
    }).eq("id", job_id).execute().data[0])


def _fail_job(client, job_id: str, exc: Exception) -> None:
    # SQL: update import_jobs
    #      set status = 'failed', error_json = :error, completed_at = now()
    #      where id = :job_id
    (client.table("import_jobs").update({
        "status": "failed",
        "error_json": {"type": type(exc).__name__, "message": str(exc)[:2000]},
        "completed_at": now_iso(),
    }).eq("id", job_id).execute())
