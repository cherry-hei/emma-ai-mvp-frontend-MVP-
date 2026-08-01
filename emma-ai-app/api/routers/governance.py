"""Audit trail, architecture decisions, scope lock and evidence (spec 0.1-1.6).

Everything here is read-only apart from recording the result of an evidence
check. The architecture decision and the MVP scope lock are authored during a
migration or a governance review, not from the application: a decision record
that the app could rewrite is not a decision record.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import EvidenceStatusRequest
from emma_core.services import audit
from emma_core.services import governance as svc

router = APIRouter(tags=["governance"])
AUDIT_ROLES = {"superintendent", "admin", "auditor"}
EVIDENCE_WRITE_ROLES = {"superintendent", "admin"}


# ── 1.3 audit trail ──────────────────────────────────────────────────────────
@router.get("/audit-logs")
def list_audit_logs(entity_table: str | None = Query(default=None),
                    entity_id: str | None = Query(default=None),
                    action: str | None = Query(default=None),
                    date_from: Date | None = Query(default=None),
                    date_to: Date | None = Query(default=None),
                    limit: int = Query(default=100, le=500),
                    ctx: AuthCtx = Depends(get_ctx)):
    """Append-only history, newest first. Not visible to a staff-app login."""
    if str(ctx.profile.role) not in AUDIT_ROLES:
        raise api_error(403, "forbidden",
                        "Only a superintendent, admin or auditor may read the audit log.")
    return audit.list_logs(ctx.client, ctx.facility_id, entity_table=entity_table,
                           entity_id=entity_id, action=action,
                           date_from=date_from, date_to=date_to, limit=limit)


@router.get("/audit-logs/actions")
def audit_actions():
    return [{"action": action} for action in audit.ACTIONS]


# ── 0.1 architecture decisions ───────────────────────────────────────────────
@router.get("/architecture-decisions")
def list_decisions(status: str | None = Query(default=None),
                   ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_decisions(ctx.client, status=status)


@router.get("/architecture-decisions/{code}")
def get_decision(code: str, ctx: AuthCtx = Depends(get_ctx)):
    row = svc.get_decision(ctx.client, code)
    if not row:
        raise api_error(404, "not_found", "architecture decision not found")
    return row


# ── 0.2 MVP scope lock ───────────────────────────────────────────────────────
@router.get("/project-scope")
def list_scope(scope: str | None = Query(default=None, description="mvp | deferred"),
               ctx: AuthCtx = Depends(get_ctx)):
    return svc.list_scope(ctx.client, scope=scope)


@router.get("/project-scope/summary")
def scope_summary(ctx: AuthCtx = Depends(get_ctx)):
    return svc.scope_summary(ctx.client)


# ── 1.6 evidence checklist ───────────────────────────────────────────────────
@router.get("/evidence-items")
def evidence_items(category: str | None = Query(default=None),
                   ctx: AuthCtx = Depends(get_ctx)):
    """The checklist with its counts and the caveats that must accompany it."""
    if category:
        return svc.list_evidence(ctx.client, ctx.facility_id, category=category)
    return svc.evidence_checklist(ctx.client, ctx.facility_id)


@router.patch("/evidence-items/{code}")
def set_evidence_status(code: str, body: EvidenceStatusRequest,
                        ctx: AuthCtx = Depends(get_ctx)):
    if str(ctx.profile.role) not in EVIDENCE_WRITE_ROLES:
        raise api_error(403, "forbidden",
                        "Only a superintendent or admin may record an evidence result.")
    row = svc.set_evidence_status(
        ctx.client, ctx.facility_id, code, status=body.status,
        sample_output=body.sample_output, notes=body.notes,
        checked_on=body.checked_on.isoformat() if body.checked_on else None,
    )
    audit.record(ctx.client, facility_id=ctx.facility_id, action="update",
                 entity_table="evidence_items", entity_id=row["id"], after=row,
                 actor_profile_id=ctx.profile_id, actor_email=ctx.profile.email,
                 reason=f"evidence {code} -> {body.status}")
    return row
