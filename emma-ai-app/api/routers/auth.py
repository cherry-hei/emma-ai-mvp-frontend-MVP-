"""/auth/login + /auth/me — thin wrappers over emma_core.services.auth.

Login runs Supabase email/password sign-in server-side and returns a *serializable*
session (tokens + resolved profile), never a live client. The Next.js app stores the
access_token and sends it as ``Authorization: Bearer`` on every other call.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import LoginRequest, Profile, SessionOut
from emma_core.services.auth import get_profile, sign_in

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=SessionOut)
def login(body: LoginRequest):
    try:
        client, session = sign_in(body.email, body.password)
    except Exception as exc:  # noqa: BLE001 — never echo the raw auth error
        raise api_error(401, "login_failed", "Invalid email or password.") from exc
    prof = get_profile(client, session.user.id)
    if not prof:
        raise api_error(403, "no_profile", "No facility profile is linked to this account.")
    return SessionOut(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_at=session.expires_at,
        user_id=session.user.id,
        email=session.user.email,
        role=prof.role,
        facility_id=prof.facility_id,
        facility_name=prof.facility.name if prof.facility else None,
    )


@router.get("/auth/me", response_model=Profile)
def me(ctx: AuthCtx = Depends(get_ctx)):
    return ctx.profile
