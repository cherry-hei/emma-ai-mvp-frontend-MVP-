"""Multi-tenancy proof: a Home A user must never see Home B data (and vice versa).

Requires local Supabase running and `scripts/seed.py` already run.
"""
import pytest
from supabase import create_client

from emma_core.config import settings

PASSWORD = "EmmaDev123!"


def client_for(email: str):
    c = create_client(settings.supabase_url, settings.supabase_anon_key)
    res = c.auth.sign_in_with_password({"email": email, "password": PASSWORD})
    c.postgrest.auth(res.session.access_token)  # enforce RLS as this user
    return c


@pytest.fixture(scope="module")
def home_a():
    return client_for("super_a@emma.local")


@pytest.fixture(scope="module")
def home_b():
    return client_for("super_b@emma.local")


def test_each_home_sees_only_its_own_staff(home_a, home_b):
    # Both calls issue the SAME statement; only the JWT differs. What makes the
    # results disjoint is the RLS predicate Postgres ANDs on:
    #
    # SQL: select id, facility_id from staff
    #      -- + RLS: and facility_id = public.current_facility_id()
    a_staff = home_a.table("staff").select("id,facility_id").execute().data
    b_staff = home_b.table("staff").select("id,facility_id").execute().data

    assert len(a_staff) == 7, "Home A should see its 7 seeded staff"
    assert len(b_staff) == 3, "Home B should see its 3 seeded staff"

    a_facs = {s["facility_id"] for s in a_staff}
    b_facs = {s["facility_id"] for s in b_staff}
    assert len(a_facs) == 1 and len(b_facs) == 1
    assert a_facs.isdisjoint(b_facs), "facilities must not overlap"


def test_facilities_scoped_to_own(home_a, home_b):
    # SQL: select code from facilities
    #      -- + RLS: and id = public.current_facility_id()
    a_facs = home_a.table("facilities").select("code").execute().data
    b_facs = home_b.table("facilities").select("code").execute().data
    assert [f["code"] for f in a_facs] == ["A"]
    assert [f["code"] for f in b_facs] == ["B"]


def test_cross_facility_read_is_blocked(home_a, home_b):
    # SQL: select facility_id from staff limit 1
    b_fac_id = home_b.table("staff").select("facility_id").limit(1).execute().data[0]["facility_id"]
    # Home A explicitly querying Home B's facility_id must get nothing.
    #
    # SQL: select id from staff where facility_id = :b_fac_id
    #      -- + RLS: and facility_id = public.current_facility_id()
    # The two predicates name different facilities, so the result is always empty.
    leaked = home_a.table("staff").select("id").eq("facility_id", b_fac_id).execute().data
    assert leaked == [], "RLS leak: Home A read Home B rows"


def test_cross_facility_write_is_blocked(home_a, home_b):
    # SQL: select facility_id from staff limit 1
    b_fac_id = home_b.table("staff").select("facility_id").limit(1).execute().data[0]["facility_id"]
    # Inserting a row tagged with Home B's facility_id must fail the WITH CHECK policy.
    #
    # SQL: insert into staff (facility_id, name, rank, employment_type)
    #      values (:b_fac_id, 'intruder', 'CW', 'agency')
    #      returning *
    #      -- + RLS WITH CHECK: facility_id = public.current_facility_id()
    with pytest.raises(Exception):
        home_a.table("staff").insert({
            "facility_id": b_fac_id, "name": "intruder", "rank": "CW",
            "employment_type": "agency",
        }).execute()
