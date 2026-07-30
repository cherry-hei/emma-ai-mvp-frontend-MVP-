"""/auth/login + /auth/refresh + /auth/me. Login/refresh return a serializable session
(tokens + profile), not a live client; the frontend sends the access_token as a bearer
on every call and swaps the refresh_token for a new session when the access token expires."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import AuthCtx, api_error, get_ctx
from emma_core.models import LoginRequest, Profile, SessionOut
from emma_core.services.auth import get_profile, refresh_session, sign_in

router = APIRouter(tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


def _session_out(session, prof: Profile) -> SessionOut:
    """Shape a Supabase session + resolved profile into the API's SessionOut."""
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


@router.post("/auth/login", response_model=SessionOut)
def login(body: LoginRequest):
    try:
        client, session = sign_in(body.email, body.password)
    except Exception as exc:  # noqa: BLE001 - never echo the raw auth error
        raise api_error(401, "login_failed", "Invalid email or password.") from exc
    prof = get_profile(client, session.user.id)
    if not prof:
        raise api_error(403, "no_profile", "No facility profile is linked to this account.")
    return _session_out(session, prof)


@router.post("/auth/refresh", response_model=SessionOut)
def refresh(body: RefreshRequest):
    # Exchange a still-valid refresh token for a fresh session. A rejected/expired
    # refresh token is a 401 → the frontend clears state and routes to /login.
    try:
        client, session = refresh_session(body.refresh_token)
    except Exception as exc:  # noqa: BLE001 - never echo the raw auth error
        raise api_error(401, "refresh_failed", "Session expired; please sign in again.") from exc
    prof = get_profile(client, session.user.id)
    if not prof:
        raise api_error(403, "no_profile", "No facility profile is linked to this account.")
    return _session_out(session, prof)


@router.get("/auth/me", response_model=Profile)
def me(ctx: AuthCtx = Depends(get_ctx)):
    return ctx.profile
