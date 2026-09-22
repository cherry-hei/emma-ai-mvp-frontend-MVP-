"""The charity boundary: one NGO above its homes, and no reach across it.

The facility boundary already has its own proof next door. This file is about
the layer above it, which is the one that decides whether two charities can
share an installation: the duty code dictionaries now hang off the charity, so a
leak here would hand one NGO another's shift structure even though every roster
row stayed correctly separated.

Needs a reachable Supabase carrying the demo fixture, same as the isolation
suite. Assertions are about scoping, so they hold at any data volume.
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


def _own_org(client) -> dict:
    # SQL: select id, code from organisations
    #      -- + RLS: where id = public.current_org_id()
    rows = client.table("organisations").select("id,code").execute().data
    assert len(rows) == 1, "a signed-in client resolves to exactly one charity"
    return rows[0]


def test_each_home_resolves_to_its_own_charity(home_a, home_b):
    a_org, b_org = _own_org(home_a), _own_org(home_b)
    assert a_org["id"] != b_org["id"], "the two demo homes are different charities"


def test_cross_charity_read_is_blocked(home_a, home_b):
    b_org_id = _own_org(home_b)["id"]
    # Naming the other charity explicitly changes nothing: the policy predicate
    # is ANDed on, and the two predicates name different charities.
    #
    # SQL: select id from organisations where id = :b_org_id
    #      -- + RLS: and id = public.current_org_id()
    leaked = home_a.table("organisations").select("id").eq("id", b_org_id).execute().data
    assert leaked == [], "RLS leak: Home A read Home B's charity"


def test_facilities_are_scoped_to_the_charity(home_a, home_b):
    # SQL: select code, org_id from facilities
    #      -- + RLS: and org_id = public.current_org_id()
    a_facs = home_a.table("facilities").select("code,org_id").execute().data
    b_facs = home_b.table("facilities").select("code,org_id").execute().data
    assert [f["code"] for f in a_facs] == ["A"]
    assert [f["code"] for f in b_facs] == ["B"]
    assert {f["org_id"] for f in a_facs}.isdisjoint({f["org_id"] for f in b_facs})


@pytest.mark.parametrize("table", ["shift_definitions", "task_definitions", "escort_locations"])
def test_dictionaries_do_not_leak_across_charities(home_a, home_b, table):
    """The dictionaries moved up a level, so they need the proof at that level.

    A charity-scoped read that still returned another charity's codes would be
    invisible on the roster and obvious in an export.
    """
    b_org_id = _own_org(home_b)["id"]
    leaked = home_a.table(table).select("id").eq("org_id", b_org_id).execute().data
    assert leaked == [], f"RLS leak: Home A read Home B {table}"


def test_every_dictionary_row_names_a_charity(home_a):
    """No row may sit outside the boundary, because a null charity is invisible
    to every reader and reappears the moment someone queries without RLS."""
    for table in ("shift_definitions", "task_definitions"):
        rows = home_a.table(table).select("id,org_id").execute().data
        assert rows, f"{table} should hold the demo fixture"
        assert all(r["org_id"] for r in rows), f"{table} holds a row with no charity"


def test_cross_charity_write_is_blocked(home_a, home_b):
    b_org_id = _own_org(home_b)["id"]
    b_fac_id = home_b.table("facilities").select("id").limit(1).execute().data[0]["id"]
    # Tagging a duty code with the other charity must fail the WITH CHECK.
    with pytest.raises(Exception):
        home_a.table("shift_definitions").insert({
            "facility_id": b_fac_id, "org_id": b_org_id, "shift_type": "ZZTEST",
            "label": "intruder", "start_time": "09:00", "end_time": "17:00",
        }).execute()


def test_a_new_code_inherits_the_charity_of_its_home(home_a):
    """An insert that names only the home still lands inside the boundary.

    This is what lets the existing importers and seed scripts keep working
    unchanged: they were written before charities existed and none of them pass
    an org_id.
    """
    fac_id = home_a.table("facilities").select("id").limit(1).execute().data[0]["id"]
    org_id = _own_org(home_a)["id"]
    created = None
    try:
        created = home_a.table("shift_definitions").insert({
            "facility_id": fac_id, "shift_type": "ZZ_ORGTEST",
            "label": "temporary, written by the charity boundary test",
            "start_time": "09:00", "end_time": "17:00",
        }).execute().data[0]
        assert created["org_id"] == org_id, "the code did not inherit its home's charity"
    finally:
        if created:
            home_a.table("shift_definitions").delete().eq("id", created["id"]).execute()


# ── NAAC against the Salvation Army home ─────────────────────────────────────
# The pair above are two demo homes. This pair is the one the trial is actually
# judged on, and it only exists once the trial tenant has been provisioned.

DICTIONARIES = ["shift_definitions", "task_definitions", "escort_locations"]
TENANT_TABLES = ["facilities", "staff", "shifts", "roster_periods"]


@pytest.fixture(scope="module")
def naac():
    try:
        return client_for("super.naac@emma.local")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"the NAAC trial tenant is not provisioned: {exc}")


def _dictionary_ids(client, org_id: str, table: str, limit: int = 25) -> list[str]:
    """Ids this charity owns.

    Filtered by charity rather than taken as they come, because the read policy
    on two of these tables also admits a row belonging to no home at all. Such a
    row is shared on purpose, and counting it as a leak would be wrong.
    """
    rows = (client.table(table).select("id,org_id").eq("org_id", org_id)
            .limit(limit).execute().data)
    return [r["id"] for r in rows]


def _tenant_ids(client, table: str, limit: int = 25) -> list[str]:
    return [r["id"] for r in client.table(table).select("id").limit(limit).execute().data]


def test_naac_is_a_charity_of_its_own(naac, home_a):
    assert _own_org(naac)["code"] == "NAAC"
    assert _own_org(naac)["id"] != _own_org(home_a)["id"]


def test_naac_lists_its_own_home_and_nothing_else(naac):
    homes = naac.table("facilities").select("code").execute().data
    assert [h["code"] for h in homes] == ["NAAC"]


@pytest.mark.parametrize("table", DICTIONARIES)
def test_neither_charity_reads_the_others_codes(naac, home_a, table):
    naac_org, a_org = _own_org(naac)["id"], _own_org(home_a)["id"]
    ours = _dictionary_ids(naac, naac_org, table)
    assert ours, f"NAAC holds no {table} to compare"
    reached = home_a.table(table).select("id").in_("id", ours).execute().data
    assert reached == [], f"RLS leak: the Salvation Army home read NAAC {table}"
    # The escort dictionary came in with NAAC and the demo home has never had
    # one, so on that table the other direction has nothing to reach for.
    theirs = _dictionary_ids(home_a, a_org, table)
    if theirs:
        reached = naac.table(table).select("id").in_("id", theirs).execute().data
        assert reached == [], f"RLS leak: NAAC read Salvation Army {table}"


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_neither_charity_reads_the_others_records(naac, home_a, table):
    theirs = _tenant_ids(home_a, table)
    ours = _tenant_ids(naac, table)
    assert ours and theirs, f"one of the two homes holds no {table} to compare"
    assert naac.table(table).select("id").in_("id", theirs).execute().data == [], \
        f"RLS leak: NAAC read Salvation Army {table}"
    assert home_a.table(table).select("id").in_("id", ours).execute().data == [], \
        f"RLS leak: the Salvation Army home read NAAC {table}"


def test_naac_cannot_write_into_the_other_charity(naac, home_a):
    """A read that is blocked and a write that is not is the worse of the two."""
    a_org = _own_org(home_a)["id"]
    a_fac = home_a.table("facilities").select("id").limit(1).execute().data[0]["id"]
    with pytest.raises(Exception):
        naac.table("shift_definitions").insert({
            "facility_id": a_fac, "org_id": a_org, "shift_type": "ZZNAAC",
            "label": "intruder", "start_time": "09:00", "end_time": "17:00",
        }).execute()
