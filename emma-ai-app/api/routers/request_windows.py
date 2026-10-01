"""Owner-controlled duty/day-off request windows for the synthetic trial only."""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, model_validator

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.permissions import SystemRole, normalise_role
from emma_core.services import duty_request_window as svc

router = APIRouter(tags=["request-windows"])


class DutyRequestWindowInput(BaseModel):
    """No facility field: target facility is always the authenticated caller's."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    target_start: Date | None = None
    target_end: Date | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        supplied = (self.opens_at, self.closes_at, self.target_start, self.target_end)
        if any(value is not None for value in supplied) and not all(
            value is not None for value in supplied
        ):
            raise ValueError("opens_at, closes_at, target_start and target_end must be supplied together")
        if self.enabled and not all(value is not None for value in supplied):
            raise ValueError("an enabled duty request window requires all window and target fields")
        if self.opens_at and self.opens_at.tzinfo is None:
            raise ValueError("opens_at must include a timezone offset")
        if self.closes_at and self.closes_at.tzinfo is None:
            raise ValueError("closes_at must include a timezone offset")
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be after opens_at")
        if self.target_start and self.target_end and self.target_end < self.target_start:
            raise ValueError("target_end must be on or after target_start")
        return self


def _require_owner(ctx: AuthCtx) -> None:
    if normalise_role(ctx.profile.role) is not SystemRole.OWNER:
        raise api_error(403, "forbidden", "Only an owner may change the duty request window.")


@router.get("/request-windows/duty")
def get_duty_window(ctx: AuthCtx = Depends(get_ctx)):
    """Any authenticated profile can read the active window in its own facility."""
    return svc.get(ctx.client, ctx.facility_id)


@router.post("/request-windows/duty")
def put_duty_window(body: DutyRequestWindowInput, ctx: AuthCtx = Depends(get_ctx)):
    """Owner-only, versioned facility config; manager assist never changes its scope."""
    _require_owner(ctx)
    try:
        row = svc.put(
            ctx.client, ctx.facility_id, enabled=body.enabled,
            opens_at=body.opens_at, closes_at=body.closes_at,
            target_start=body.target_start, target_end=body.target_end,
            created_by=ctx.profile_id,
        )
        return svc.public_window(row)
    except ValueError as exc:
        raise api_error(422, "invalid_request_window", str(exc)) from exc
    except svc.DutyRequestWindowUnavailable as exc:
        raise api_error(503, "request_window_unavailable", str(exc)) from exc
