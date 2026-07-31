"""Request auth: turn a bearer token into an RLS-scoped Supabase client + profile."""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from emma_core.db import get_user_client
from emma_core.models import Profile
from emma_core.permissions import (
    Feature,
    Grant,
    SystemRole,
    can_decide,
    can_read,
    can_recommend,
    can_write,
    grant_for,
    normalise_role,
)
from emma_core.services.auth import get_profile

# Drives the Swagger "Authorize" button. auto_error=False so we can return our own
# 401 shape and also accept a bare token (no "Bearer " prefix).
_bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access_token from /auth/login.")


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _jwt_sub(token: str) -> str | None:
    # 'sub' = Supabase auth user id. No signature check - Supabase verifies on every query.
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("sub")
    except (IndexError, ValueError, binascii.Error):
        return None


def bearer_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    # Accept "Authorization: Bearer <token>" or a bare "Authorization: <token>".
    if creds and creds.credentials:
        return creds.credentials.strip()
    raw = (request.headers.get("authorization") or "").strip()
    if raw:
        return raw.split(None, 1)[1].strip() if raw.lower().startswith("bearer ") else raw
    raise api_error(401, "unauthorized", "Missing access token.")


@dataclass
class AuthCtx:
    token: str
    client: object          # RLS-scoped supabase client
    profile: Profile

    @property
    def facility_id(self) -> str:
        return self.profile.facility_id or ""

    @property
    def profile_id(self) -> str:
        return self.profile.id

    @property
    def role(self) -> SystemRole | None:
        """Canonical role, resolved from whichever spelling the DB holds."""
        return normalise_role(self.profile.role)

    def grant(self, feature: Feature) -> Grant:
        return grant_for(self.profile.role, feature)


def get_ctx(token: str = Depends(bearer_token)) -> AuthCtx:
    client = get_user_client(token)
    sub = _jwt_sub(token)
    if not sub:
        raise api_error(401, "unauthorized", "Bearer token is not a valid JWT.")
    try:
        profile = get_profile(client, sub)
    except Exception as exc:  # noqa: BLE001
        raise api_error(401, "unauthorized", "Session is invalid or expired.") from exc
    if not profile:
        raise api_error(403, "no_profile", "No facility profile is linked to this account.")
    return AuthCtx(token=token, client=client, profile=profile)


# ── permission guards (spec 1.1) ─────────────────────────────────────────────
# Each returns a FastAPI dependency, so a route declares what it needs:
#
#     @router.get("/roi/summary")
#     def roi_summary(ctx: AuthCtx = Depends(require_read(Feature.ROI))): ...
#
# The guard replaces the per-router `WRITE_ROLES` sets. Those were duplicated in
# nine files, listed role names as literals, and - because each only wrapped the
# write handlers - left every GET in the same router open to any signed-in user.

def _denied(feature: Feature, action: str) -> HTTPException:
    return api_error(403, "forbidden",
                     f"Your role may not {action} {feature.value.replace('.', ' ')}.")


def require_read(feature: Feature):
    """Facility-wide read. Self-only roles are refused here on purpose: a
    self-only caller needs a `/me`-shaped endpoint that filters by user, not the
    facility aggregate."""
    def dep(ctx: AuthCtx = Depends(get_ctx)) -> AuthCtx:
        if not can_read(ctx.profile.role, feature):
            raise _denied(feature, "view")
        return ctx
    return dep


def require_write(feature: Feature):
    def dep(ctx: AuthCtx = Depends(get_ctx)) -> AuthCtx:
        if not can_write(ctx.profile.role, feature):
            raise _denied(feature, "change")
        return ctx
    return dep


def require_recommend(feature: Feature):
    """Attach a suggest-approve/reject with a reason. Held by OWNER and the R
    roles; the decision itself still needs `require_decide`."""
    def dep(ctx: AuthCtx = Depends(get_ctx)) -> AuthCtx:
        if not can_recommend(ctx.profile.role, feature):
            raise _denied(feature, "recommend on")
        return ctx
    return dep


def require_decide(feature: Feature):
    """Final approve/reject/cancel/revoke - OWNER only.

    This is the guard that makes "recommend != approve" real: a nursing officer
    passes `require_recommend` on the same feature and is refused here."""
    def dep(ctx: AuthCtx = Depends(get_ctx)) -> AuthCtx:
        if not can_decide(ctx.profile.role, feature):
            raise _denied(feature, "give the final decision on")
        return ctx
    return dep
