"""The NAAC code import, proved on a throwaway charity before the real one exists.

The import is the piece that waits on NAAC's confirmed sheet, so what it is
waiting for is the data, not the machinery. This runs the whole load into a
charity of its own, checks what landed, runs it a second time to show it does not
duplicate, and deletes it again. When the sheet arrives it should be a data swap
rather than a debugging session.

It is safe to delete afterwards only because nothing in the seed path writes to
the audit log. A home that has ever been audited cannot be removed by anyone.
"""
from __future__ import annotations

import csv
import pathlib

import pytest

DATA = pathlib.Path(__file__).resolve().parent.parent / "emma_core" / "importers" / "data"
ORG_CODE = "ZZNAACIMPORT"
HOME_CODE = "ZZNAACHOME"


def _sheet_codes(name: str) -> list[str]:
    with open(DATA / name, encoding="utf-8") as handle:
        return [(r["code"] or "").strip() for r in csv.DictReader(handle)]


def _dictionary() -> dict[str, int]:
    """How many codes of each kind the home actually gets.

    Not the row count of the sheet. Two kinds of row collapse on the way in, both
    on purpose and both covered by the test below, so the sheet is the wrong
    number to hold the load to and the loaders are the right one.
    """
    from emma_core.importers import naac
    return {"shift_definitions": len(naac.load_shift_codes()),
            "task_definitions": len(naac.load_task_codes()),
            "escort_locations": len(naac.load_escort_locations())}


def test_the_sheet_collapses_only_where_it_is_meant_to():
    """A duty lost between the sheet and the dictionary is one nobody can roster.

    `/` is the home's spacer for a post nobody is in, so it is not a duty. The
    repeated codes are the home writing one code against two things, and the
    dictionary is keyed by code, so they are one entry by definition. Anything
    else going missing is a defect and this is what would catch it.
    """
    from emma_core.importers import naac

    shift = _sheet_codes("naac_shift_codes.csv")
    assert set(shift) - set(naac.load_shift_codes()) == {"/"}
    assert len(shift) - len(set(shift)) == 1, "the duty sheet gained a repeated code"

    assert set(_sheet_codes("naac_task_codes.csv")) == set(naac.load_task_codes())

    escort = _sheet_codes("naac_escort_locations.csv")
    assert set(escort) == set(naac.load_escort_locations())
    assert len(escort) - len(set(escort)) == 2, "the escort sheet gained a repeated code"


@pytest.fixture(scope="module")
def sb():
    try:
        from emma_core.db import get_service_client
        client = get_service_client()
        client.table("facilities").select("id").limit(1).execute()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Supabase not reachable: {exc}")
    return client


def _teardown(sb) -> None:
    from emma_core.services import organisations
    homes = sb.table("facilities").select("id").eq("code", HOME_CODE).execute().data
    for home in homes:
        for table in ("shift_definitions", "task_definitions", "escort_locations",
                      "facility_json_configs", "facility_units"):
            sb.table(table).delete().eq("facility_id", home["id"]).execute()
        sb.table("facilities").delete().eq("id", home["id"]).execute()
        organisations._ORG_BY_FACILITY.pop(home["id"], None)
    sb.table("organisations").delete().eq("code", ORG_CODE).execute()


def test_the_naac_dictionaries_load_into_their_own_charity(sb):
    from emma_core.services import naac_seed, organisations

    _teardown(sb)  # a previous failed run must not colour the result
    try:
        org = organisations.provision(sb, ORG_CODE, "NAAC import test charity")
        home = sb.table("facilities").insert({
            "code": HOME_CODE, "name": "NAAC import test home", "type": "RCHE",
            "scheduling_cycle_days": 42, "capacity": 20, "org_id": org["id"],
        }).execute().data[0]
        organisations._ORG_BY_FACILITY.pop(home["id"], None)

        result = naac_seed.provision(sb, facility_code=HOME_CODE)

        # Every code in the shipped files has to arrive. A partial load is the
        # failure that looks like success: the home works, and the duty its
        # roster needs is the one that did not come across.
        expected = _dictionary()
        for table, count in expected.items():
            assert result[table] == count, f"{table} loaded short"

        # And they must land on the charity, not loose in the home, or a second
        # NAAC home would not see the dictionary it was onboarded to share.
        for table, count in expected.items():
            rows = (sb.table(table).select("id,org_id")
                    .eq("org_id", org["id"]).execute().data)
            assert len(rows) == count, f"{table} did not land on the charity"
            assert all(r["org_id"] == org["id"] for r in rows)
    finally:
        _teardown(sb)


def test_a_corrected_sheet_updates_rather_than_duplicates(sb):
    """Cherry sends a corrected sheet and the load runs again. It must not fork.

    This is the run that actually happens in practice: the first load goes in on
    a draft sheet, NAAC returns exceptions, and the file is reloaded. If that
    produced a second set of codes the roster would offer each duty twice.
    """
    from emma_core.services import naac_seed, organisations

    _teardown(sb)
    try:
        org = organisations.provision(sb, ORG_CODE, "NAAC import test charity")
        home = sb.table("facilities").insert({
            "code": HOME_CODE, "name": "NAAC import test home", "type": "RCHE",
            "scheduling_cycle_days": 42, "capacity": 20, "org_id": org["id"],
        }).execute().data[0]
        organisations._ORG_BY_FACILITY.pop(home["id"], None)

        naac_seed.provision(sb, facility_code=HOME_CODE)
        before = (sb.table("shift_definitions").select("id", count="exact")
                  .eq("org_id", org["id"]).execute().count)

        naac_seed.provision(sb, facility_code=HOME_CODE, overwrite=True)
        after = (sb.table("shift_definitions").select("id", count="exact")
                 .eq("org_id", org["id"]).execute().count)

        assert after == before, "the second load forked the duty dictionary"
    finally:
        _teardown(sb)
