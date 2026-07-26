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
from emma_core.services.auth import get_profile

# Drives the Swagger "Authorize" button. auto_error=False so we can return our own
# 401 shape and also accept a bare token (no "Bearer " prefix).
_bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access_token from /auth/login.")


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _jwt_sub(token: str) -> str | None:
    # 'sub' = Supabase auth user id. No signature check — Supabase verifies on every query.
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
