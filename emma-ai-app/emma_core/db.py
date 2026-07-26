"""Supabase client factories.

- service client: bypasses RLS — use ONLY for migrations, seeding and trusted
  admin/server tasks.
- anon client: subject to RLS — use with a signed-in user's access token so
  facility_id isolation is enforced.
"""
from functools import lru_cache

from .config import settings


@lru_cache
def get_service_client():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@lru_cache
def get_anon_client():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_user_client(access_token: str):
    """Anon client acting as a specific signed-in user (RLS enforced)."""
    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client
