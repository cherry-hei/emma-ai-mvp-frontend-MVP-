"""Retrieval at the charity level, proved through the API rather than the tables.

`test_org_architecture.py` proves the boundary exists in the database. This file
proves the product reads it: the duty codes, task codes and escort codes a home
sees are its charity's, and a charity never sees another's through any endpoint
that serves them.

The distinction matters. A policy can be correct while every service still
filters by the home, which looks identical on a one-home charity and silently
hides the shared dictionary from a charity's second home. These go through real
logins and real HTTP.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)
PASSWORD = "EmmaDev123!"

DICTIONARY_ROUTES = ["/shift-definitions", "/task-definitions", "/escort-locations"]


def _token(email: str) -> str:
    from emma_core.services.auth import sign_in
    try:
        _, session = sign_in(email, PASSWORD)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Supabase not reachable/seeded: {exc}")
    return session.access_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def head_a() -> dict:
    return _auth(_token("super_a@emma.local"))


@pytest.fixture(scope="module")
def head_b() -> dict:
    return _auth(_token("super_b@emma.local"))


def test_each_home_reads_its_own_charity(head_a, head_b):
    a = client.get("/organisations/current", headers=head_a).json()
    b = client.get("/organisations/current", headers=head_b).json()
    assert a["id"] != b["id"]
    assert {a["code"], b["code"]} == {"ORG_A", "ORG_B"}


def test_the_charity_lists_its_own_homes_and_no_others(head_a, head_b):
    a = client.get("/organisations/current/facilities", headers=head_a).json()
    b = client.get("/organisations/current/facilities", headers=head_b).json()
    assert [f["code"] for f in a] == ["A"]
    assert [f["code"] for f in b] == ["B"]


@pytest.mark.parametrize("route", DICTIONARY_ROUTES)
def test_dictionaries_are_served_at_charity_scope(route, head_a, head_b):
    """The same request from two charities must not return a shared row.

    Ids rather than codes: two charities are free to use the same code for
    different duties, and it is the row that must not cross.
    """
    rows_a = client.get(route, headers=head_a).json()
    rows_b = client.get(route, headers=head_b).json()
    assert isinstance(rows_a, list) and isinstance(rows_b, list)
    ids_a = {r["id"] for r in rows_a if r.get("id")}
    ids_b = {r["id"] for r in rows_b if r.get("id")}
    assert ids_a.isdisjoint(ids_b), f"{route} served the same row to both charities"


def test_the_duty_dictionary_is_not_empty_at_charity_scope(head_a):
    """Scoping to the charity must not quietly return nothing.

    The failure worth catching is the opposite of a leak: read by a column the
    rows do not carry and every list comes back empty, which looks like a clean
    boundary and is an outage.
    """
    rows = client.get("/shift-definitions", headers=head_a).json()
    assert rows, "the charity's duty dictionary came back empty"
    assert all(r.get("shift_type") for r in rows)


def test_the_roster_grid_renders_on_the_charity_dictionary(head_a):
    """The grid is where a missing dictionary shows up as blank cells."""
    periods = client.get("/roster-periods", headers=head_a).json()
    for period in periods:
        versions = client.get("/roster-versions", headers=head_a,
                              params={"period_id": period["id"]}).json()
        manual = next((v for v in versions if v["version_type"] == "manual"), None)
        if not manual:
            continue
        grid = client.get(f"/rosters/{period['id']}", headers=head_a,
                          params={"version_id": manual["id"]}).json()
        codes = {cell.get("shift_type") for row in grid.get("rows", [])
                 for cell in row.get("cells", []) if cell.get("assignment_id")}
        if not codes:
            continue
        known = {r["shift_type"] for r in
                 client.get("/shift-definitions", headers=head_a).json()}
        assert codes <= known, f"grid used codes absent from the charity: {codes - known}"
        return
    pytest.skip("no rostered cell in this fixture to render")


def test_a_second_home_in_the_charity_reads_the_same_dictionary():
    """The proof the fixture cannot otherwise give.

    Both demo homes are their own charity, so charity scope and home scope return
    the same rows and a service still filtering by the home would look correct.
    This stands up a second home inside an existing charity, reads the
    dictionaries as that home, and removes it again. If retrieval were still
    scoped to the home, the new one would see nothing at all, which is precisely
    how the second centre onboarding would have failed.
    """
    from emma_core.db import get_service_client
    from emma_core.services import organisations, roster, tasks

    sb = get_service_client()
    parent = sb.table("facilities").select("id,org_id").eq("code", "A").execute().data
    if not parent:
        pytest.skip("demo home A is not present")
    org_id = parent[0]["org_id"]
    expected_codes = {d.shift_type for d in roster.get_shift_defs(sb, parent[0]["id"])}
    assert expected_codes, "home A has no duty codes to compare against"

    sister = None
    try:
        sister = sb.table("facilities").insert({
            "code": "ZZTEMP", "name": "temporary sister home, charity scope test",
            "type": "RCHE", "scheduling_cycle_days": 28, "capacity": 10,
            "org_id": org_id,
        }).execute().data[0]
        organisations._ORG_BY_FACILITY.pop(sister["id"], None)

        codes = {d.shift_type for d in roster.get_shift_defs(sb, sister["id"])}
        assert codes == expected_codes, (
            "a second home in the charity did not inherit the duty dictionary")

        labels = tasks.task_definitions_by_label(sb, sister["id"])
        assert labels, "a second home in the charity saw no task codes"
    finally:
        if sister:
            sb.table("facilities").delete().eq("id", sister["id"]).execute()
            organisations._ORG_BY_FACILITY.pop(sister["id"], None)
