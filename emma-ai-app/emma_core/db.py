"""Supabase client factories. The service client bypasses RLS (migrations/seeding/trusted server tasks only); the anon client is subject to RLS.

Reading the queries
-------------------
Everything in ``emma_core.services`` talks to Postgres through the PostgREST
query builder (``client.table("staff").select(...).eq(...)``), not through SQL
text. Each call site carries a ``# SQL:`` comment with the statement PostgREST
actually runs, so a reader can see the query without unpicking the builder
chain. Conventions used in those comments:

- ``:name`` is the Python argument supplying the value (``:facility_id`` is the
  ``facility_id`` parameter), matching psycopg's named-placeholder style.
- ``[ ... ]`` wraps a predicate that is only added on some code paths; the
  trailing note says which.
- Embeds (``select("*, unit:facility_units(name)")``) are shown as the LEFT JOIN
  PostgREST performs, with the nested object it returns.
- **Not shown, but always applied:** every statement issued through a user
  client (``get_user_client``) additionally gets the RLS predicate
  ``facility_id = public.current_facility_id()`` ANDed on by Postgres - see
  ``supabase/migrations/20260721000002_rls_tenancy.sql``. The service client
  bypasses that, which is why it is limited to seeding and migrations.
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
