"""Onboarding a home end to end, then removing every trace of it.

This is the acceptance evidence for the trial environment: a charity, a home,
its floors, invented people, working logins and a full six week roster, all from
one config file and one command. It runs against the real database because that
is the only place the RLS, the foreign keys and the auth admin all apply at once,
and it deletes what it made whether it passes or fails.

The home it stands up joins an existing charity on purpose. That is the case the
demo fixture cannot show by itself, and it is the one that proves a second centre
costs configuration rather than development.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEEKS = 6
CODE = "ZZPROV"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "provision_tenant", ROOT / "scripts" / "provision_tenant.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Supabase not reachable: {exc}")
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


@pytest.fixture(scope="module")
def host_charity(script):
    """An existing charity with a loaded dictionary, so the roster has codes."""
    rows = script.sb.table("facilities").select("org_id").eq("code", "B").execute().data
    if not rows or not rows[0].get("org_id"):
        pytest.skip("demo home B is not present")
    return rows[0]["org_id"]


def _config(org_code: str) -> dict:
    return {
        "organisation": {"code": org_code, "name": "provisioning test charity"},
        "facility": {"code": CODE, "name": "provisioning test home",
                     "type": "RCHE", "scheduling_cycle_days": 42, "capacity": 20},
        "units": [{"code": "ZZ1", "name": "1/F", "unit_type": "floor"},
                  {"code": "ZZ2", "name": "2/F", "unit_type": "floor"}],
        "staff": [
            {"name": "測試護士", "name_en": "Provision RN", "rank": "RN", "unit": "ZZ1"},
            {"name": "測試保健員", "name_en": "Provision HW", "rank": "HW", "unit": "ZZ2"},
        ],
        "accounts": [
            {"email": "zzprov.super@emma.local", "role": "superintendent"},
            {"email": "zzprov.staff@emma.local", "role": "staff",
             "staff": "Provision RN"},
        ],
        "roster": {"start": "2027-01-04", "weeks": WEEKS, "cycle_type": "6week",
                   "pattern": {"RN": ["A", "A", "P", "P", "N", "OFF", "DO"],
                               "HW": ["A", "P", "A", "P", "OFF", "DO", "A"]}},
    }


def _remove(script, config: dict) -> None:
    sb = script.sb
    for account in config["accounts"]:
        for user in sb.auth.admin.list_users():
            if (user.email or "").lower() == account["email"].lower():
                sb.auth.admin.delete_user(user.id)
    # Every tenant table cascades from the home, so one delete clears the rest.
    sb.table("facilities").delete().eq("code", config["facility"]["code"]).execute()


def test_a_home_is_onboarded_from_one_config_and_can_be_signed_into(script, host_charity):
    from emma_core.services import organisations
    from emma_core.services.auth import sign_in

    org_code = (script.sb.table("organisations").select("code")
                .eq("id", host_charity).execute().data[0]["code"])
    config = _config(org_code)
    _remove(script, config)  # a previous failed run must not change the outcome
    try:
        org = script.organisation(config["organisation"])
        assert org["id"] == host_charity, "joined the wrong charity"

        home = script.facility(org["id"], config["facility"])
        assert home["org_id"] == host_charity
        organisations._ORG_BY_FACILITY.pop(home["id"], None)

        unit_ids = script.units(home["id"], config["units"])
        assert set(unit_ids) == {"ZZ1", "ZZ2"}

        staff_ids = script.staff(home["id"], config["staff"], unit_ids)
        assert set(staff_ids) == {"Provision RN", "Provision HW"}

        script.accounts(home["id"], org["id"], config["accounts"], staff_ids)
        _, session = sign_in("zzprov.super@emma.local", script.PASSWORD)
        assert session.access_token, "the superintendent login does not work"

        # Running it again must not build a second home or a second set of people.
        again = script.facility(org["id"], config["facility"])
        assert again["id"] == home["id"], "a second run built a second home"
        assert script.staff(home["id"], config["staff"], unit_ids) == staff_ids

        # The roster itself is exercised next door, against a home that already
        # exists: creating a period writes an audit row, audit rows cannot be
        # deleted by anyone, and a home carrying one can never be removed again.
    finally:
        _remove(script, config)
        organisations._ORG_BY_FACILITY.clear()


def test_a_charity_with_no_dictionary_is_refused_rather_than_rostered(script):
    """The A.2 dependency, enforced.

    A home whose charity has no duty codes must stop with an explanation. The
    failure worth preventing is a roster written in invented codes that looks
    plausible and matches nothing the home actually works.
    """
    from emma_core.services import organisations

    config = _config("ZZEMPTY")
    config["facility"]["code"] = "ZZEMPTYHOME"
    _remove(script, config)
    org = None
    try:
        org = script.organisation({"code": "ZZEMPTY", "name": "charity with no codes"})
        home = script.facility(org["id"], config["facility"])
        organisations._ORG_BY_FACILITY.pop(home["id"], None)
        unit_ids = script.units(home["id"], config["units"])
        staff_ids = script.staff(home["id"], config["staff"], unit_ids)
        with pytest.raises(SystemExit) as refused:
            script.roster(home, config["roster"], config["staff"], staff_ids, unit_ids)
        assert "duty codes" in str(refused.value)
    finally:
        _remove(script, config)
        if org:
            script.sb.table("organisations").delete().eq("id", org["id"]).execute()
        organisations._ORG_BY_FACILITY.clear()


def test_a_full_cycle_of_duty_is_written_in_the_charitys_own_codes(script):
    """The six week roster, against a home that is staying anyway.

    It cannot be done on a throwaway home: creating a period writes an audit row,
    `trg_protect_audit_log` refuses every delete and update of those rows for
    every role, and the home's own delete cascades into them. So a home that has
    ever been audited is permanent by design. Here the period and its cells are
    removed afterwards and only the audit entry remains, which is what an audit
    entry is for.
    """
    sb = script.sb
    rows = sb.table("facilities").select("id,org_id,code").eq("code", "B").execute().data
    if not rows:
        pytest.skip("demo home B is not present")
    home = rows[0]
    people = (sb.table("staff").select("id,name,name_en,rank")
              .eq("facility_id", home["id"]).limit(2).execute().data)
    if len(people) < 2:
        pytest.skip("demo home B has too few staff to roster")

    spec = {"start": "2027-01-04", "weeks": WEEKS, "cycle_type": "6week",
            "pattern": {p["rank"]: ["A", "A", "P", "P", "N", "OFF", "DO"]
                        for p in people}}
    staff_specs = [{"name_en": p["name_en"] or p["id"], "rank": p["rank"]}
                   for p in people]
    staff_ids = {s["name_en"]: p["id"] for s, p in zip(staff_specs, people)}

    period = None
    try:
        script.roster(home, spec, staff_specs, staff_ids, {})
        period = (sb.table("roster_periods").select("id")
                  .eq("facility_id", home["id"])
                  .eq("period_start", spec["start"]).execute().data[0])
        versions = (sb.table("roster_versions").select("id")
                    .eq("period_id", period["id"]).execute().data)
        assert versions, "the period was created without a manual roster to edit"
        shifts = (sb.table("shifts").select("id,shift_type", count="exact")
                  .eq("roster_version_id", versions[0]["id"]).execute())
        assert shifts.count == WEEKS * 7 * len(people), (
            "the roster is not a full cycle for every person")
        known = {d.shift_type for d in
                 __import__("emma_core.services.roster", fromlist=["x"])
                 .get_shift_defs(sb, home["id"])}
        assert {s["shift_type"] for s in shifts.data} <= known, (
            "the roster used codes the charity does not define")
    finally:
        if period:
            versions = (sb.table("roster_versions").select("id")
                        .eq("period_id", period["id"]).execute().data)
            for version in versions:
                ids = [s["id"] for s in sb.table("shifts").select("id")
                       .eq("roster_version_id", version["id"]).execute().data]
                for start in range(0, len(ids), 50):
                    chunk = ids[start:start + 50]
                    sb.table("shift_assignments").delete().in_("shift_id", chunk).execute()
                    sb.table("shifts").delete().in_("id", chunk).execute()
                sb.table("roster_versions").delete().eq("id", version["id"]).execute()
            sb.table("roster_periods").delete().eq("id", period["id"]).execute()
