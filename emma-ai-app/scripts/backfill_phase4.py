"""Bring an already-seeded database up to the Phase 4 reference data.

`scripts/seed.py` builds a correct Phase 4 fixture, but it does so by wiping and
recreating both demo facilities. An environment seeded before Phase 4 landed
therefore still carries the Phase 3 task dictionary and the Phase 3 roster-cell
labels, which the Phase 4 rules then reject — the roster becomes permanently
unpublishable through no fault of the roster.

This script closes that gap in place. It never deletes a facility, a roster, a
shift or an assignment; it only reconciles the reference tables and rewrites the
task labels on existing cells. Running it twice changes nothing the second time.

    python scripts/backfill_phase4.py            # apply
    python scripts/backfill_phase4.py --dry-run  # report only
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from emma_core.db import get_service_client  # noqa: E402
from scripts.seed import (  # noqa: E402
    DEV_PASSWORD,
    seed_floor_rules,
    seed_staff_qualifications,
    seed_task_definitions,
)

sb = get_service_client()
DRY_RUN = "--dry-run" in sys.argv

# The Phase 4 roster cells, keyed by facility code then rank then shift code.
# This mirrors scripts/seed.py: Home A carries the daily task codes (`tasks_a`,
# rewritten per rank so it applies to staff that already exist rather than to
# seed-time list positions), while Home B carries none — its Phase 4 surface is
# floor coverage, not task codes.
LABELS_BY_FACILITY: dict[str, dict[str, dict[str, list[str]]]] = {
    "A": {
        "HW": {"A": ["Vital Signs"], "AN": ["Vital Signs"], "P": ["AOM (Oral)"]},
        "CW": {"A": ["Oral Feeding"], "P": ["Evening Diaper Change"]},
        "PTA": {"A": ["Rehab Session"]},
        "AW": {"P": ["Infection Control"]},
    },
    "B": {},
}


def log(message: str) -> None:
    print(("[dry-run] " if DRY_RUN else "") + message)


def _captured(seed_fn, *args) -> list[dict]:
    """Run a seed builder for its rows instead of its inserts.

    The seed functions are the single definition of the Phase 4 fixture. Reading
    the rows out of them keeps this script from drifting into a second, subtly
    different copy of the same reference data.
    """
    captured: list[dict] = []
    module = seed_fn.__globals__
    original = module["ins_many"]

    def capture(_table: str, rows: list[dict]):
        captured.extend(rows)
        return []

    module["ins_many"] = capture
    try:
        seed_fn(*args)
    finally:
        module["ins_many"] = original
    return captured


def reconcile_task_definitions(facility_id: str) -> set[str]:
    """Upsert the Phase 4 codes; retire anything the dictionary dropped.

    Retired rows are deactivated rather than deleted so historical
    task_assignments keep pointing at a real definition.

    Returns the set of labels (names and codes) that stay valid.
    """
    desired = _captured(seed_task_definitions, facility_id)
    existing = (sb.table("task_definitions").select("*")
                .eq("facility_id", facility_id).execute().data)
    by_key = {(row["task_code"], row.get("required_rank")): row for row in existing}

    inserts, updates = [], 0
    for row in desired:
        key = (row["task_code"], row.get("required_rank"))
        current = by_key.pop(key, None)
        if current is None:
            inserts.append(row)
            continue
        changes = {k: v for k, v in row.items()
                   if k != "facility_id" and current.get(k) != v}
        changes.setdefault("active", True)
        if current.get("active") is not True or len(changes) > 1:
            updates += 1
            if not DRY_RUN:
                (sb.table("task_definitions").update(changes)
                 .eq("id", current["id"]).execute())
    if inserts and not DRY_RUN:
        sb.table("task_definitions").insert(inserts).execute()
    retired = [row["id"] for row in by_key.values() if row.get("active")]
    if retired and not DRY_RUN:
        (sb.table("task_definitions").update({"active": False})
         .in_("id", retired).execute())
    log(f"  task_definitions: +{len(inserts)} new, {updates} updated, "
        f"{len(retired)} retired")

    valid: set[str] = set()
    for row in desired:
        valid.update(filter(None, (row.get("task_name"), row.get("task_code"))))
    return valid


def backfill_qualifications(facility_id: str) -> None:
    staff = (sb.table("staff").select("id,rank")
             .eq("facility_id", facility_id).execute().data)
    have = (sb.table("staff_qualifications").select("staff_id,qualification_type")
            .eq("facility_id", facility_id).execute().data)
    if have:
        log(f"  staff_qualifications: {len(have)} already present, left alone")
        return
    log(f"  staff_qualifications: seeding for {len(staff)} staff")
    if not DRY_RUN:
        seed_staff_qualifications(
            facility_id, [s["id"] for s in staff], [s["rank"] for s in staff])


def backfill_floor_rules(facility_id: str) -> None:
    units = (sb.table("facility_units").select("id,name,code")
             .eq("facility_id", facility_id).execute().data)
    floors = {}
    for unit in units:
        for key in (unit.get("code"), unit.get("name")):
            if key:
                floors[str(key).replace("/", "").upper()] = unit["id"]
    present = {k: floors[k] for k in ("1F", "2F", "6F") if k in floors}
    if not present:
        log("  floor rules: skipped — facility has no numbered floors")
        return
    have = (sb.table("floor_min_staffing_rules").select("id")
            .eq("facility_id", facility_id).execute().data)
    if have:
        log(f"  floor rules: {len(have)} already present, left alone")
        return
    # An environment seeded before Phase 4 may have fewer floors than the
    # current seed creates. Take the rules for the floors that exist rather
    # than inventing a unit the resident counts and ratios know nothing about.
    rows = [row for row in _captured(seed_floor_rules, facility_id,
                                     {k: floors.get(k) for k in ("1F", "2F", "6F")})
            if row.get("unit_id")]
    log(f"  floor rules: seeding {len(rows)} rules for {sorted(present)}")
    if not DRY_RUN and rows:
        sb.table("floor_min_staffing_rules").insert(rows).execute()


def relabel_roster_cells(facility_id: str, facility_code: str,
                         valid_labels: set[str]) -> None:
    """Rewrite each cell's task array to the Phase 4 duty for its shift code."""
    labels_by_rank = LABELS_BY_FACILITY.get(facility_code, {})
    staff = {s["id"]: s for s in sb.table("staff").select("id,rank")
             .eq("facility_id", facility_id).execute().data}
    shifts = {s["id"]: s for s in
              sb.table("shifts").select("id,shift_type,is_working")
              .eq("facility_id", facility_id).execute().data}
    assignments = (sb.table("shift_assignments").select("id,shift_id,staff_id,tasks")
                   .eq("facility_id", facility_id).execute().data)

    changed = 0
    for assignment in assignments:
        shift = shifts.get(assignment.get("shift_id"))
        if not shift:
            continue
        rank = (staff.get(assignment.get("staff_id")) or {}).get("rank")
        wanted = []
        if shift.get("is_working"):
            wanted = labels_by_rank.get(rank, {}).get(shift["shift_type"], [])
        if list(assignment.get("tasks") or []) == wanted:
            continue
        changed += 1
        if not DRY_RUN:
            (sb.table("shift_assignments").update({"tasks": wanted})
             .eq("id", assignment["id"]).execute())
    log(f"  roster cells relabelled: {changed} of {len(assignments)}")

    # Execution rows built against the old dictionary no longer describe
    # anything valid — either the label is gone, or the row still points at a
    # definition that has just been retired, which validation reports as an
    # unknown task. Drop both; validate_roster_rules re-materialises the current
    # labels, bound to the current definitions, on its next run.
    active_ids = {row["id"] for row in
                  sb.table("task_definitions").select("id")
                  .eq("facility_id", facility_id).eq("active", True).execute().data}
    stale = [row["id"] for row in
             sb.table("task_assignments").select("id,task_label,task_id")
             .eq("facility_id", facility_id).execute().data
             if row["task_label"] not in valid_labels
             or row.get("task_id") not in active_ids]
    if stale:
        log(f"  task_assignments: dropping {len(stale)} rows with retired labels")
        if not DRY_RUN:
            for start in range(0, len(stale), 100):
                (sb.table("task_assignments").delete()
                 .in_("id", stale[start:start + 100]).execute())


def backfill_care_side_staff_login(facility_id: str, facility_code: str) -> None:
    """Give the staff app a login that actually has daily tasks.

    Phase 4's dictionary is profession-specific: RN and EN hold no daily codes,
    so the original `staff_a` account — an RN — now shows an empty task list by
    design. Without a care-side account the staff app's task screen cannot be
    demonstrated at all.
    """
    if facility_code != "A":
        return
    email = "staff_hw_a@emma.local"
    existing = (sb.table("users_profile").select("id")
                .eq("facility_id", facility_id).eq("email", email).execute().data)
    if existing:
        log(f"  staff login: {email} already present")
        return
    hw = (sb.table("staff").select("id,name_en")
          .eq("facility_id", facility_id).eq("rank", "HW").limit(1).execute().data)
    if not hw:
        log("  staff login: skipped — facility has no HW to bind to")
        return
    log(f"  staff login: creating {email} for {hw[0]['name_en']}")
    if DRY_RUN:
        return
    created = sb.auth.admin.create_user({
        "email": email, "password": DEV_PASSWORD, "email_confirm": True,
    })
    sb.table("users_profile").insert({
        "auth_user_id": created.user.id, "facility_id": facility_id,
        "email": email, "role": "staff", "staff_id": hw[0]["id"],
    }).execute()


def main() -> None:
    facilities = sb.table("facilities").select("id,code,name").order("code").execute().data
    for facility in facilities:
        log(f"Home {facility['code']} — {facility['name']}")
        valid_labels = reconcile_task_definitions(facility["id"])
        backfill_qualifications(facility["id"])
        backfill_floor_rules(facility["id"])
        relabel_roster_cells(facility["id"], facility["code"], valid_labels)
        backfill_care_side_staff_login(facility["id"], facility["code"])
    log("Phase 4 backfill complete.")


if __name__ == "__main__":
    main()
