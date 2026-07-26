"""FastAPI dependencies — one place that turns a request's bearer token into an
RLS-scoped Supabase client plus the caller's resolved profile.

Every ``emma_core.services`` function takes an RLS ``client`` as its first arg
(the in-process convention the Reflex UI used). This dependency reproduces that
client from the ``Authorization: Bearer <token>`` header, so the HTTP layer wraps
the services 1:1. Because the client is the *user* client, Postgres RLS scopes
every query to the caller's facility automatically — no manual facility checks
needed on read paths.
"""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from emma_core.db import get_user_client
from emma_core.models import Profile
from emma_core.services.auth import get_profile


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    """Consistent { detail: { code, message } } error body."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _jwt_sub(token: str) -> str | None:
    """Extract the ``sub`` (Supabase auth user id) from a JWT without verifying
    the signature — Supabase already validates it server-side on every query, so
    a forged token can't read anything. We only need ``sub`` to look up the row."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("sub")
    except (IndexError, ValueError, binascii.Error):
        return None


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise api_error(401, "unauthorized", "Missing or malformed Authorization header.")
    return authorization.split(None, 1)[1].strip()


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
    except Exception as exc:  # noqa: BLE001 — surface as 401, not 500
        raise api_error(401, "unauthorized", "Session is invalid or expired.") from exc
    if not profile:
        raise api_error(403, "no_profile", "No facility profile is linked to this account.")
    return AuthCtx(token=token, client=client, profile=profile)
