"""Auth helpers: sign in and resolve the caller's facility + role."""
from __future__ import annotations

from supabase import create_client

from ..config import settings
from ..models import Profile


def sign_in(email: str, password: str):
    """Return (client, session). The client is bound to the user's token so RLS
    applies to every subsequent query."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    res = client.auth.sign_in_with_password({"email": email, "password": password})
    client.postgrest.auth(res.session.access_token)
    return client, res.session


def get_profile(client, auth_user_id: str) -> Profile | None:
    rows = (client.table("users_profile")
            .select("*, facility:facilities(code,name)")
            .eq("auth_user_id", auth_user_id).limit(1).execute().data)
    return Profile.model_validate(rows[0]) if rows else None
