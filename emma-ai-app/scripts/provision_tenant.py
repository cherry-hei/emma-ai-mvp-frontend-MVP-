"""Stand a charity, a home, its people and a working synthetic roster up in one run.

    python scripts/provision_tenant.py scripts/tenants/naac.json
    python scripts/provision_tenant.py scripts/tenants/naac.json --dry-run

Everything it needs comes from the config file, so onboarding a home is filling
one file in rather than editing this script. It is idempotent: run it again after
a corrected sheet and it reuses what is there instead of building a second copy.

What it does not do is invent duty codes. A config names the shipped dictionary
its charity works from and the roster is written in that, so a pattern using a
code the home does not have stops the run instead of producing a plausible
roster that matches nothing.

Synthetic only. Every name in a config file here is invented, and nothing in this
script may be pointed at a real staff list.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date as Date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# The home names are Chinese and a Windows console is not UTF-8 by default.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from emma_core.db import get_service_client  # noqa: E402
from emma_core.services import organisations, roster as roster_svc  # noqa: E402

PASSWORD = "EmmaDev123!"

sb = get_service_client()


# ── charity, home, units ─────────────────────────────────────────────────────
def organisation(spec: dict) -> dict:
    org = organisations.provision(sb, spec["code"], spec["name"])
    print(f"  charity   {org['code']}  {org['name']}")
    return org


def facility(org_id: str, spec: dict) -> dict:
    rows = sb.table("facilities").select("*").eq("code", spec["code"]).execute().data
    if rows:
        home = rows[0]
        if home.get("org_id") != org_id:
            raise SystemExit(
                f"facility {spec['code']!r} already belongs to another charity; "
                "move it deliberately rather than through this script")
    else:
        home = sb.table("facilities").insert({
            "code": spec["code"], "name": spec["name"],
            "type": spec.get("type", "RCHE"),
            "scheduling_cycle_days": spec.get("scheduling_cycle_days", 42),
            "capacity": spec.get("capacity"), "org_id": org_id,
        }).execute().data[0]
    print(f"  home      {home['code']}  {home['name']}")
    return home


def units(facility_id: str, specs: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for spec in specs:
        rows = (sb.table("facility_units").select("id")
                .eq("facility_id", facility_id).eq("code", spec["code"])
                .execute().data)
        if rows:
            out[spec["code"]] = rows[0]["id"]
            continue
        out[spec["code"]] = sb.table("facility_units").insert({
            "facility_id": facility_id, "code": spec["code"], "name": spec["name"],
            "unit_type": spec.get("unit_type", "floor"),
        }).execute().data[0]["id"]
    print(f"  units     {', '.join(out) or 'none'}")
    return out


# ── the duty dictionary ──────────────────────────────────────────────────────────────────────
def codes(home: dict, spec: dict | None) -> None:
    """Load a shipped code dictionary into the charity, if the config names one."""
    if not spec:
        print("  codes     not named here, so they must already be loaded")
        return
    source = spec.get("source")
    if source != "naac":
        raise SystemExit(f"no shipped code dictionary called {source!r}")
    from emma_core.services import naac_seed
    naac_seed.provision(sb, facility_code=home["code"],
                        overwrite=spec.get("overwrite", False))
    # Counted from the charity rather than from what this run wrote, because a
    # second run writes nothing and the useful number is what the home now has.
    org_id = organisations.org_id_for(sb, home["id"])
    held = {table: sb.table(table).select("id", count="exact")
            .eq("org_id", org_id).execute().count
            for table in ("shift_definitions", "task_definitions", "escort_locations")}
    print(f"  codes     {held['shift_definitions']} duty, "
          f"{held['task_definitions']} task, {held['escort_locations']} escort")


# ── people and their logins ──────────────────────────────────────────────────
def staff(facility_id: str, specs: list[dict], unit_ids: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for spec in specs:
        rows = (sb.table("staff").select("id").eq("facility_id", facility_id)
                .eq("name_en", spec["name_en"]).execute().data)
        if rows:
            out[spec["name_en"]] = rows[0]["id"]
            continue
        hours = spec.get("contracted_hours", 44)
        staff_id = sb.table("staff").insert({
            "facility_id": facility_id, "name": spec["name"],
            "name_en": spec["name_en"], "rank": spec["rank"],
            "employment_type": spec.get("employment_type", "local_ft"),
            "contracted_hours": hours, "gender": spec.get("gender"),
            "primary_unit_id": unit_ids.get(spec.get("unit")),
            "is_audited_for_medication": spec["rank"] in ("RN", "EN"),
            "status": "active",
        }).execute().data[0]["id"]
        sb.table("staff_contracts").insert({
            "facility_id": facility_id, "staff_id": staff_id,
            "weekly_hours": hours, "max_weekly_hours": hours + 8,
        }).execute()
        out[spec["name_en"]] = staff_id
    print(f"  staff     {len(out)}")
    return out


def _auth_user(email: str) -> str:
    """Create the login, or reuse the one already there and reset its password."""
    for user in sb.auth.admin.list_users():
        if (user.email or "").lower() == email.lower():
            sb.auth.admin.update_user_by_id(user.id, {"password": PASSWORD})
            return user.id
    return sb.auth.admin.create_user({
        "email": email, "password": PASSWORD, "email_confirm": True}).user.id


def accounts(facility_id: str, org_id: str, specs: list[dict],
             staff_ids: dict[str, str]) -> None:
    for spec in specs:
        auth_id = _auth_user(spec["email"])
        row = {"auth_user_id": auth_id, "facility_id": facility_id, "org_id": org_id,
               "email": spec["email"], "role": spec["role"],
               "staff_id": staff_ids.get(spec.get("staff"))}
        existing = (sb.table("users_profile").select("id")
                    .eq("auth_user_id", auth_id).execute().data)
        if existing:
            sb.table("users_profile").update(row).eq("id", existing[0]["id"]).execute()
        else:
            sb.table("users_profile").insert(row).execute()
        print(f"  login     {spec['email']:<34} {spec['role']}")


# ── the roster itself ────────────────────────────────────────────────────────
def _dictionary(facility_id: str) -> dict[str, dict]:
    return {d.shift_type: d.model_dump()
            for d in roster_svc.get_shift_defs(sb, facility_id)}


def _pattern_for(person: dict, patterns: dict[str, list[str]]) -> list[str]:
    """One person's cycle. Their own if the config gives them one, else their rank's.

    A part timer on the rank's cycle is scheduled a full timer's hours, which the
    validator is right to reject and which makes the whole roster look careless.
    """
    own = person.get("pattern")
    if own:
        return own
    pattern = patterns.get(person["rank"])
    if not pattern:
        raise SystemExit(f"no duty pattern for rank {person['rank']!r}")
    return pattern


def roster(home: dict, spec: dict, staff_specs: list[dict],
           staff_ids: dict[str, str], unit_ids: dict[str, str]) -> None:
    """A whole cycle of invented duty, written in the charity's own codes."""
    dictionary = _dictionary(home["id"])
    if not dictionary:
        raise SystemExit(
            "this charity has no duty codes yet, so there is nothing to roster in. "
            "Load the code dictionary first.")

    patterns = spec["pattern"]
    wanted = {code for person in staff_specs for code in _pattern_for(person, patterns)}
    missing = sorted(wanted - set(dictionary))
    if missing:
        raise SystemExit(
            f"the roster pattern uses codes this charity does not define: {missing}. "
            "Either the dictionary is incomplete or the pattern is written in "
            "another home's codes.")

    start = Date.fromisoformat(spec["start"])
    days = spec.get("weeks", 6) * 7
    end = start + timedelta(days=days - 1)

    existing = (sb.table("roster_periods").select("id")
                .eq("facility_id", home["id"])
                .eq("period_start", str(start)).execute().data)
    if existing:
        print(f"  roster    already present for {start}, left alone")
        return

    period, version = roster_svc.create_period(
        sb, facility_id=home["id"], period_start=start, period_end=end,
        cycle_type=spec.get("cycle_type", "6week"), create_manual_version=True)

    shift_rows, meta = [], []
    for index, person in enumerate(staff_specs):
        pattern = _pattern_for(person, patterns)
        staff_id = staff_ids[person["name_en"]]
        for offset in range(days):
            # Rotate each person through the pattern so a home does not come out
            # with every nurse on the same day off.
            code = pattern[(offset + index) % len(pattern)]
            definition = dictionary[code]
            shift_rows.append({
                "facility_id": home["id"], "roster_version_id": version["id"],
                "date": str(start + timedelta(days=offset)), "shift_type": code,
                "start_time": definition.get("start_time"),
                "end_time": definition.get("end_time"),
                "cross_midnight": definition.get("cross_midnight", False),
                "unit_id": unit_ids.get(person.get("unit")),
                "required_rank": person["rank"], "required_count": 1,
                "is_working": definition.get("is_working", True),
                "segments": definition.get("segments"),
                "paid_minutes": definition.get("paid_minutes"),
            })
            meta.append((staff_id, person["rank"], definition.get("is_working", True)))

    shift_ids = [r["id"] for r in sb.table("shifts").insert(shift_rows).execute().data]
    sb.table("shift_assignments").insert([
        {"facility_id": home["id"], "shift_id": shift_id, "staff_id": staff_id,
         "role": rank, "status": "assigned", "is_agency": False, "tasks": []}
        for shift_id, (staff_id, rank, _working) in zip(shift_ids, meta)
    ]).execute()
    print(f"  roster    {spec.get('weeks', 6)} weeks from {start}, "
          f"{len(shift_rows)} cells")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="path to the tenant config JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="read and check the config, write nothing")
    args = parser.parse_args()

    spec = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
    print(f"Provisioning from {args.config}")
    if args.dry_run:
        ranks = {p["rank"] for p in spec.get("staff", [])}
        source = (spec.get("codes") or {}).get("source")
        print(f"  charity   {spec['organisation']['code']}")
        print(f"  home      {spec['facility']['code']}")
        print(f"  units     {len(spec.get('units', []))}")
        print(f"  codes     {source or 'expected to be loaded already'}")
        print(f"  staff     {len(spec.get('staff', []))} across {sorted(ranks)}")
        print(f"  logins    {len(spec.get('accounts', []))}")
        if spec.get("roster"):
            patterns = spec["roster"]["pattern"]
            cycles = [_pattern_for(p, patterns) for p in spec.get("staff", [])]
            # Checking the pattern against the shipped sheet here is the whole
            # point of a dry run: the same mistake found after provisioning has
            # already left a half built home behind.
            if source == "naac":
                from emma_core.importers import naac
                known = set(naac.load_shift_codes())
                unknown = sorted({c for cycle in cycles for c in cycle} - known)
                if unknown:
                    raise SystemExit(
                        f"  duty codes absent from the {source} sheet: {unknown}")
            print(f"  roster    {spec['roster']['weeks']} weeks "
                  f"from {spec['roster']['start']}")
        print("  config reads cleanly. Nothing written.")
        return

    org = organisation(spec["organisation"])
    home = facility(org["id"], spec["facility"])
    unit_ids = units(home["id"], spec.get("units", []))
    codes(home, spec.get("codes"))
    staff_ids = staff(home["id"], spec.get("staff", []), unit_ids)
    accounts(home["id"], org["id"], spec.get("accounts", []), staff_ids)
    if spec.get("roster"):
        roster(home, spec["roster"], spec["staff"], staff_ids, unit_ids)
    print(f"\nPassword for every login above: {PASSWORD}")
    print("Synthetic data. Not for real staff records.")


if __name__ == "__main__":
    main()
