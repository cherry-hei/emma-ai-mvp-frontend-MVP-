"""Request-window API routes.

This module is deliberately not imported by ``api.main`` in this worktree:
``api/main.py`` is owned by the integration parent.  The parent adds one router
import/include after reviewing this contract and migration together.
"""
from __future__ import annotations

from datetime import date as Date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.permissions import SystemRole, normalise_role
from emma_core.services import request_windows as svc


router = APIRouter(tags=["request-windows"])


class RequestWindowCreate(BaseModel):
    """Tenant and organisation scope are always derived from the login profile."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["duty", "leave"]
    scope: Literal["facility", "unit"] = "facility"
    unit_id: str | None = None
    state: Literal["open", "closed"] = "open"
    opens_at: datetime
    closes_at: datetime
    target_start: Date
    target_end_exclusive: Date = Field(
        validation_alias=AliasChoices("target_end_exclusive", "target_end"),
        description="First date outside the allowed requested-date range.",
    )
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_window(self):
        _validate_aware(self.opens_at, "opens_at")
        _validate_aware(self.closes_at, "closes_at")
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be after opens_at")
        if self.target_end_exclusive <= self.target_start:
            raise ValueError("target_end_exclusive must be after target_start")
        if self.scope == "unit" and not self.unit_id:
            raise ValueError("unit_id is required for a unit-scoped window")
        if self.scope == "facility" and self.unit_id:
            raise ValueError("unit_id is only valid for a unit-scoped window")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key cannot be blank")
        return self


class RequestWindowPatch(BaseModel):
    """A partial update protected by the row version supplied by the manager."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    state: Literal["open", "closed"] | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    target_start: Date | None = None
    target_end_exclusive: Date | None = Field(
        default=None,
        validation_alias=AliasChoices("target_end_exclusive", "target_end"),
    )
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_patch(self):
        if self.opens_at is not None:
            _validate_aware(self.opens_at, "opens_at")
        if self.closes_at is not None:
            _validate_aware(self.closes_at, "closes_at")
        changed = self.model_dump(exclude_unset=True, exclude={"version", "reason"})
        if not changed:
            raise ValueError("provide at least one request-window field to update")
        return self


def _validate_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")


def _require_window_admin(ctx: AuthCtx) -> None:
    """Only the configured OWNER/superintendent mapping may administer windows.

    Existing role data maps legacy ``superintendent`` to canonical ``OWNER``.
    There is no trustworthy deputy role mapping in this baseline, so an
    unrecognised deputy title fails closed rather than gaining write authority.
    """
    if normalise_role(ctx.profile.role) is not SystemRole.OWNER:
        raise api_error(403, "forbidden", "Only an owner/superintendent may administer request windows.")


def _staff_id_or_403(ctx: AuthCtx) -> str:
    if not ctx.profile.staff_id:
        raise api_error(403, "no_staff_profile", "No staff profile is linked to this account.")
    return ctx.profile.staff_id


@router.get("/request-windows")
def list_request_windows(ctx: AuthCtx = Depends(get_ctx)):
    """List windows only in the authenticated caller's facility/org scope."""
    try:
        return svc.list_scoped(ctx.client, ctx.facility_id)
    except svc.RequestWindowDatabaseUnavailable as exc:
        raise api_error(503, "request_window_unavailable", str(exc)) from exc


@router.post("/request-windows", status_code=201)
def create_request_window(body: RequestWindowCreate, ctx: AuthCtx = Depends(get_ctx)):
    """Create or replay a durable scope/kind window with an idempotency key."""
    _require_window_admin(ctx)
    try:
        return svc.create(
            ctx.client,
            ctx.facility_id,
            kind=body.kind,
            scope=body.scope,
            unit_id=body.unit_id,
            state=body.state,
            opens_at=body.opens_at.isoformat(),
            closes_at=body.closes_at.isoformat(),
            target_start=body.target_start.isoformat(),
            target_end_exclusive=body.target_end_exclusive.isoformat(),
            idempotency_key=body.idempotency_key.strip(),
            reason=body.reason,
        )
    except svc.RequestWindowConflict as exc:
        raise api_error(409, "request_window_conflict", str(exc)) from exc
    except svc.RequestWindowNotFound as exc:
        raise api_error(404, "not_found", str(exc)) from exc
    except svc.RequestWindowDatabaseUnavailable as exc:
        raise api_error(503, "request_window_unavailable", str(exc)) from exc


@router.patch("/request-windows/{window_id}")
def patch_request_window(
    window_id: str,
    body: RequestWindowPatch,
    ctx: AuthCtx = Depends(get_ctx),
):
    """CAS update a durable window; a stale version is an explicit 409."""
    _require_window_admin(ctx)
    values = body.model_dump(
        exclude_unset=True,
        exclude={"version", "reason"},
        mode="json",
    )
    try:
        return svc.patch(
            ctx.client,
            ctx.facility_id,
            window_id,
            version=body.version,
            patch_values=values,
            reason=body.reason,
        )
    except svc.RequestWindowConflict as exc:
        raise api_error(409, "request_window_conflict", str(exc)) from exc
    except svc.RequestWindowNotFound as exc:
        raise api_error(404, "not_found", str(exc)) from exc
    except svc.RequestWindowDatabaseUnavailable as exc:
        raise api_error(503, "request_window_unavailable", str(exc)) from exc


@router.get("/me/request-window")
def my_request_window(
    kind: Literal["duty", "leave"] = Query(...),
    ctx: AuthCtx = Depends(get_ctx),
):
    """Return the caller's effective window using database time and own unit."""
    try:
        return svc.my_window(ctx.client, ctx.facility_id, _staff_id_or_403(ctx), kind=kind)
    except svc.RequestWindowDatabaseUnavailable as exc:
        raise api_error(503, "request_window_unavailable", str(exc)) from exc


@router.get("/request-windows/duty")
def legacy_duty_request_window(ctx: AuthCtx = Depends(get_ctx)):
    """Compatibility read alias for the currently shipped Staff PWA client.

    New clients should use ``GET /me/request-window?kind=duty``.  This alias is
    read-only and does not retain the old owner-only PUT/POST mutation surface.
    """
    try:
        result = svc.my_window(ctx.client, ctx.facility_id, _staff_id_or_403(ctx), kind="duty")
        return svc.legacy_duty_window(result)
    except svc.RequestWindowDatabaseUnavailable as exc:
        raise api_error(503, "request_window_unavailable", str(exc)) from exc
