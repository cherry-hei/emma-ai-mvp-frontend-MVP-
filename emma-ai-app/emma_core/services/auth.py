"""Auth helpers: sign in and resolve the caller's facility + role."""
from __future__ import annotations

from supabase import create_client

from ..config import settings
from ..models import Profile


def sign_in(email: str, password: str):
    """Return (client, session); the client is bound to the user's token so RLS applies."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    res = client.auth.sign_in_with_password({"email": email, "password": password})
    client.postgrest.auth(res.session.access_token)
    return client, res.session


def refresh_session(refresh_token: str):
    """Exchange a refresh token for a fresh session (new access + refresh token).

    Powers POST /auth/refresh so the frontend can keep a session alive silently
    instead of forcing a re-login when the short-lived access token expires.
    """
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    res = client.auth.refresh_session(refresh_token)
    client.postgrest.auth(res.session.access_token)
    return client, res.session


def get_profile(client, auth_user_id: str) -> Profile | None:
    rows = (client.table("users_profile")
            .select("*, facility:facilities(code,name)")
            .eq("auth_user_id", auth_user_id).limit(1).execute().data)
    return Profile.model_validate(rows[0]) if rows else None
