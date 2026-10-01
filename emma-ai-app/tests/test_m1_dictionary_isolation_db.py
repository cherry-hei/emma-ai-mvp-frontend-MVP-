"""Optional RLS proof against a LOCAL synthetic Supabase only.

Run only after the migration has been inspected and applied to a disposable local DB:
    EMMA_RUN_LOCAL_RLS_TESTS=1 APP_ENV=development \
      python -m pytest -q tests/test_m1_dictionary_isolation_db.py
Never point this test at a customer's or deployed database: it writes test rows.
"""
from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

import pytest


@pytest.fixture(scope="module")
def clients():
    if os.getenv("EMMA_RUN_LOCAL_RLS_TESTS") != "1":
        pytest.skip("write test requires explicit EMMA_RUN_LOCAL_RLS_TESTS=1")

    from emma_core.config import settings
    from emma_core.db import get_service_client
    from supabase import create_client

    hostname = urlparse(settings.supabase_url).hostname
    if hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("refusing to write test rows outside local synthetic Supabase")
    if not settings.supabase_anon_key or not settings.supabase_service_role_key:
        pytest.skip("local synthetic Supabase keys not configured")
    password = os.getenv("EMMA_SYNTHETIC_TEST_PASSWORD")
    if not password:
        pytest.skip("synthetic test credential must be supplied out of band")

    def as_demo(email):
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        result = client.auth.sign_in_with_password({
            "email": email, "password": password
        })
        client.postgrest.auth(result.session.access_token)
        return client

    try:
        return get_service_client(), as_demo("super.naac@emma.local"), as_demo("super_a@emma.local")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"local synthetic tenants unavailable: {type(exc).__name__}")


@pytest.mark.parametrize("table,code_field", [
    ("task_definitions", "task_code"),
    ("escort_locations", "code"),
])
def test_org_owned_null_facility_is_never_global(clients, table, code_field):
    admin, naac, sa_style = clients
    naac_org = naac.table("organisations").select("id").execute().data[0]["id"]
    sa_org = sa_style.table("organisations").select("id").execute().data[0]["id"]
    assert naac_org != sa_org

    created = []
    suffix = uuid.uuid4().hex[:10]
    try:
        for org_id, marker in ((naac_org, "NAAC"), (sa_org, "SA")):
            row = admin.table(table).insert({
                "facility_id": None, "org_id": org_id,
                code_field: f"ZZ{marker}_{suffix}",
            }).execute().data[0]
            created.append(row["id"])
        assert len(naac.table(table).select("id").eq("id", created[0]).execute().data) == 1
        assert len(sa_style.table(table).select("id").eq("id", created[1]).execute().data) == 1
        assert naac.table(table).select("id").eq("id", created[1]).execute().data == []
        assert sa_style.table(table).select("id").eq("id", created[0]).execute().data == []
    finally:
        for row_id in created:
            admin.table(table).delete().eq("id", row_id).execute()


def test_truly_global_template_stays_readable_to_both_tenants(clients):
    admin, naac, sa_style = clients
    marker = f"ZZGLOBAL_{uuid.uuid4().hex[:10]}"
    created = admin.table("task_definitions").insert({
        "facility_id": None, "org_id": None,
        "task_code": marker, "task_name": "synthetic global template",
    }).execute().data[0]
    try:
        for tenant in (naac, sa_style):
            assert len(tenant.table("task_definitions").select("id")
                       .eq("id", created["id"]).execute().data) == 1
    finally:
        admin.table("task_definitions").delete().eq("id", created["id"]).execute()


def test_cannot_write_other_org_code_even_if_client_supplies_own_org_id(clients):
    admin, naac, sa_style = clients
    # Server-side trigger must reconcile org_id with facility owner; RLS alone
    # does not catch inconsistent rows if the caller supplies its own org_id.
    naac_org = naac.table("organisations").select("id").execute().data[0]["id"]
    sa_org = sa_style.table("organisations").select("id").execute().data[0]["id"]
    sa_facility = sa_style.table("facilities").select("id").limit(1).execute().data[0]["id"]
    naac_facility = naac.table("facilities").select("id").limit(1).execute().data[0]["id"]
    from postgrest.exceptions import APIError
    for attacker, own_org, foreign_facility in (
        (naac, naac_org, sa_facility),
        (sa_style, sa_org, naac_facility),
    ):
        marker = f"ZZBOUNDARY_{uuid.uuid4().hex[:10]}"
        with pytest.raises(APIError):
            attacker.table("task_definitions").insert({
                "facility_id": foreign_facility, "org_id": own_org,
                "task_code": marker, "task_name": "must fail",
            }).execute()
        # If an error class changes, first verify no row landed before updating
        # this assertion; never weaken the tenant boundary to satisfy a test.
        assert admin.table("task_definitions").select("id").eq("task_code", marker).execute().data == []
