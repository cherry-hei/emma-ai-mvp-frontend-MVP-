"""B1 authenticated RLS specification: NOT TESTED.

Do not execute until Founder separately authorises disposable local Auth/DB
setup, migrations and synthetic writes. This module loads no settings, keys,
environment files or client factories. It neither provisions nor seeds anything.

A separately reviewed local-only harness must provide b1_local_clients:
  admin: local synthetic fixture writer (never isolation proof);
  x1, x2, y1: authenticated users bound to X1, X2, Y1 respectively.
Org X / X1 / X2 and Org Y / Y1 must already exist with the UUIDs below.
Their auth user IDs must differ from profile IDs. The harness must refuse
non-loopback destinations and fail on unavailable fixtures, not skip.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

ORG_X = "00000000-0000-4000-8000-000000000001"
ORG_Y = "00000000-0000-4000-8000-000000000002"
X1 = "00000000-0000-4000-8000-000000000101"
X2 = "00000000-0000-4000-8000-000000000102"
Y1 = "00000000-0000-4000-8000-000000000201"

TABLES = [("task_definitions", "task_code"), ("escort_locations", "code")]


@pytest.fixture(scope="module")
def clients(b1_local_clients):
    # No fallback to deployed/demo accounts. Missing harness is a setup error.
    assert set(b1_local_clients) == {"admin", "x1", "x2", "y1"}
    for key, facility, org in (("x1", X1, ORG_X), ("x2", X2, ORG_X), ("y1", Y1, ORG_Y)):
        actual = (b1_local_clients[key].table("facilities").select("id,org_id")
                  .eq("id", facility).execute().data)
        assert actual == [{"id": facility, "org_id": org}]
    return b1_local_clients


@pytest.mark.parametrize("table,code_field", TABLES)
def test_same_org_shared_rows_visible_and_foreign_org_denied(clients, table, code_field):
    created = []
    admin = clients["admin"]
    try:
        for org, facility in ((ORG_X, None), (ORG_X, X2), (ORG_Y, None), (ORG_Y, Y1)):
            row = admin.table(table).insert({
                "org_id": org, "facility_id": facility,
                code_field: "B1_" + uuid4().hex[:10],
            }).execute().data[0]
            created.append(row["id"])
        for key, permitted in (("x1", created[:2]), ("x2", created[:2]), ("y1", created[2:])):
            rows = clients[key].table(table).select("id").in_("id", created).execute().data
            assert {r["id"] for r in rows} == set(permitted)
    finally:
        for row_id in created:
            admin.table(table).delete().eq("id", row_id).execute()


@pytest.mark.parametrize("table,code_field", TABLES)
def test_unapproved_global_row_denied_to_every_tenant(clients, table, code_field):
    admin = clients["admin"]
    row = admin.table(table).insert({
        "org_id": None, "facility_id": None, code_field: "B1_" + uuid4().hex[:10],
    }).execute().data[0]
    try:
        for key in ("x1", "x2", "y1"):
            assert clients[key].table(table).select("id").eq("id", row["id"]).execute().data == []
    finally:
        admin.table(table).delete().eq("id", row["id"]).execute()


@pytest.mark.parametrize("table,code_field", TABLES)
def test_cross_org_mismatched_insert_denied(clients, table, code_field):
    from postgrest.exceptions import APIError

    for key, own_org, foreign_facility in (("x1", ORG_X, Y1), ("y1", ORG_Y, X1)):
        marker = "B1_" + uuid4().hex[:10]
        with pytest.raises(APIError) as denied:
            clients[key].table(table).insert({
                "org_id": own_org, "facility_id": foreign_facility, code_field: marker,
            }).execute()
        assert denied.value.code == "P0001"
        assert "org_id must match facility owner" in denied.value.message
        assert clients["admin"].table(table).select("id").eq(code_field, marker).execute().data == []


@pytest.mark.parametrize("table,code_field", TABLES)
def test_nulling_scope_cannot_promote_row_to_global(clients, table, code_field):
    from postgrest.exceptions import APIError

    admin = clients["admin"]
    row = admin.table(table).insert({
        "org_id": ORG_X, "facility_id": None, code_field: "B1_" + uuid4().hex[:10],
    }).execute().data[0]
    try:
        with pytest.raises(APIError) as denied:
            clients["x1"].table(table).update({
                "org_id": None, "facility_id": None,
            }).eq("id", row["id"]).execute()
        assert denied.value.code == "42501"
        assert "row-level security" in denied.value.message.lower()
        actual = admin.table(table).select("org_id,facility_id").eq("id", row["id"]).execute().data
        assert actual == [{"org_id": ORG_X, "facility_id": None}]
        assert clients["y1"].table(table).select("id").eq("id", row["id"]).execute().data == []
    finally:
        admin.table(table).delete().eq("id", row["id"]).execute()
