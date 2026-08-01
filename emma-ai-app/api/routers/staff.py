"""/staff - staff directory (hours, status, certs) + /staff/{id} profile detail,
and the certificate vault (spec SA.7)."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Query, Response

from api.deps import AuthCtx, api_error, get_ctx, require_read, require_write
from emma_core.models import (
    CertificateOut,
    CertificateUpsert,
    StaffCreate,
    StaffDetail,
    StaffOut,
    StaffUpdate,
)
from emma_core.permissions import Feature
from emma_core.services import certificates as cert_svc
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


# ── writes (spec 2.1) ────────────────────────────────────────────────────────
# Gated on staff.profile_write, which the matrix grants to OWNER and ADMIN_CLERK
# only - a nursing officer who can see the whole portfolio still cannot edit a
# contract, because rank and employment_type decide which rules apply to a
# person's roster.

@router.post("/staff", status_code=201)
def create_staff(body: StaffCreate,
                 ctx: AuthCtx = Depends(require_write(Feature.STAFF_PROFILE_WRITE))):
    return svc.create_staff(ctx.client, ctx.facility_id, body.model_dump(),
                            actor_profile_id=ctx.profile_id,
                            actor_email=ctx.profile.email)


@router.patch("/staff/{staff_id}")
def update_staff(staff_id: str, body: StaffUpdate,
                 ctx: AuthCtx = Depends(require_write(Feature.STAFF_PROFILE_WRITE))):
    return svc.update_staff(ctx.client, ctx.facility_id, staff_id,
                            body.model_dump(exclude_unset=True),
                            actor_profile_id=ctx.profile_id,
                            actor_email=ctx.profile.email)


# ── certificate vault (spec SA.7) ────────────────────────────────────────────
# Gated on staff.certificates, not staff.profile_write. The matrix gives
# HR_AUDITOR edit on certificates and nothing else - it is the one thing that
# role writes, and folding it into profile_write would either lock HR out of
# its own job or hand it contract editing it must not have.

@router.get("/staff/{staff_id}/certificates", response_model=list[CertificateOut])
def staff_certificates(staff_id: str,
                       ctx: AuthCtx = Depends(require_read(Feature.CERTIFICATES))):
    return cert_svc.list_for_staff(ctx.client, ctx.facility_id, staff_id)


@router.put("/staff/{staff_id}/certificates", response_model=CertificateOut,
            status_code=201)
def upsert_certificate(staff_id: str, body: CertificateUpsert,
                       ctx: AuthCtx = Depends(require_write(Feature.CERTIFICATES))):
    """Add a certificate, or replace the one of the same type.

    A renewal updates the row and resets the warning ladder, so the new expiry
    date gets its own 90/60/30/14/7-day sequence instead of inheriting how far
    the old one had already been announced.
    """
    try:
        return cert_svc.upsert(
            ctx.client, ctx.facility_id, staff_id, cert_type=body.cert_type,
            expiry_date=body.expiry_date, file_url=body.file_url,
            certificate_id=body.certificate_id)
    except ValueError as exc:
        raise api_error(404 if "not found" in str(exc) else 400,
                        "invalid_certificate", str(exc)) from exc


@router.delete("/staff/{staff_id}/certificates/{certificate_id}", status_code=204)
def delete_certificate(staff_id: str, certificate_id: str,
                       ctx: AuthCtx = Depends(require_write(Feature.CERTIFICATES))):
    cert_svc.delete(ctx.client, ctx.facility_id, certificate_id)
    return Response(status_code=204)


@router.get("/certificates/expiring", response_model=list[CertificateOut])
def expiring_certificates(
    within_days: int = Query(default=90, ge=1, le=365),
    include_expired: bool = Query(default=True),
    ctx: AuthCtx = Depends(require_read(Feature.CERTIFICATES)),
):
    """Everything due or overdue, soonest first - the manager's renewal queue."""
    return cert_svc.expiring(ctx.client, ctx.facility_id,
                             within_days=within_days,
                             include_expired=include_expired)


@router.post("/certificates/notify-expiring")
def notify_expiring_certificates(
    dry_run: bool = Query(default=False,
                          description="list what would be sent without sending"),
    on: Date | None = Query(default=None,
                            description="evaluate as at this date (testing)"),
    ctx: AuthCtx = Depends(require_write(Feature.CERTIFICATES)),
):
    """Send each certificate's next due warning.

    Idempotent within a stage, so a scheduler may call it as often as it likes;
    a certificate already told it has 30 days left is not told again until it
    reaches 14.
    """
    sent = cert_svc.notify_expiring(ctx.client, ctx.facility_id,
                                    today=on, dry_run=dry_run)
    return {"dry_run": dry_run, "notified": len(sent), "certificates": sent}
