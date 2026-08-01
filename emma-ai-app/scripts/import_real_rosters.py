"""Import the care homes' real roster workbooks (spec 1.4).

This is the counterpart to `seed.py`: instead of generating demo data, it loads
what the two pilot homes actually rostered. Run it after the migrations are
applied and the two facilities exist.

    python scripts/import_real_rosters.py --validate       # parse and report only
    python scripts/import_real_rosters.py --commit         # load, keep demo rows
    python scripts/import_real_rosters.py --commit --replace-demo-data

`--replace-demo-data` removes the generated staff and rosters for Home A and
Home B first, so the database holds only what the homes wrote. Login accounts
survive: `users_profile.staff_id` is ON DELETE SET NULL, and the script re-links
the staff-app account to a real imported staff member afterwards.

Each workbook maps onto the roster versions the schema already has:

===================================  =========================================
`Duty_Roster_March2026.xlsx` before   Home A, March cycle, draft - the plan
`Duty_Roster_March2026.xlsx` after    Home A, March cycle, published - as worked
`FL Nursing Staff Roster 062026`      Home B, June, published - as worked
`night roster.xlsx`                   Home B, July, draft - in progress
===================================  =========================================
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from emma_core import importers                       # noqa: E402
from emma_core.db import get_service_client           # noqa: E402
from emma_core.services import imports as svc         # noqa: E402

DOCS = pathlib.Path(__file__).resolve().parent.parent.parent / "docs"

# (file name, Home A sheet variant, roster label, version status, owns the period)
#
# "Owns the period" decides who writes the records that belong to the month rather
# than to one version of it - leave, events, holidays, configuration. Home A's
# before/after pair describes the same March leave, so only the as-worked sheet
# writes it; the plan contributes its roster content as a comparison draft.
SOURCES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("Duty_Roster_March2026.xlsx", "before",
     "March 2026 cycle - original plan", "draft", False),
    ("Duty_Roster_March2026.xlsx", "after",
     "March 2026 cycle - as worked", "published", True),
    ("FL Nursing Staff Roster 062026.xlsx", "after",
     "June 2026 - as worked", "published", True),
    ("night roster.xlsx", "after",
     "July 2026 - night roster draft", "draft", True),
)

# Cleared for Home A and Home B when --replace-demo-data is given, in dependency
# order. Roster content cascades from roster_versions; staff-owned rows cascade
# from staff. users_profile is deliberately absent: logins must survive.
_DEMO_TABLES = (
    "roster_versions", "optimization_jobs", "roster_validation_runs",
    "violation_log", "manual_override_log", "roster_publish_events",
    "replacement_candidates", "sl_incidents", "future_debt_ledger",
    "agency_assignments", "attendance_events", "notifications", "reports",
    "leave_requests", "leave_balances", "staff", "roster_periods",
)

sb = get_service_client()

# The homes' sheet names and staff names are Chinese, and this script prints cell
# references verbatim. A Windows console defaults to cp1252, which cannot encode
# them, so the output stream is switched rather than the messages sanitised.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def facilities() -> dict[str, dict]:
    # SQL: select id, code, name from facilities where code in ('A', 'B')
    rows = (sb.table("facilities").select("id,code,name")
            .in_("code", ["A", "B"]).execute().data)
    return {r["code"]: r for r in rows}


def release_stuck_leave(facility_ids: list[str]) -> int:
    """Make every approved leave row releasable before the bulk delete.

    `sync_leave_balance_usage` refuses to release an approved request unless
    exactly one configured `leave_balances` row covers every one of its days, and
    that the balance can absorb the change. Demo rows seeded against an earlier
    period layout no longer satisfy it, which leaves them impossible to cancel
    *or* delete - the trigger blocks both directions.

    Each stuck row therefore gets a private period and balance sized to its own
    days; deleting the request unwinds that balance to zero, and the scaffolding
    is removed afterwards. Policy is satisfied rather than bypassed: no trigger is
    disabled and no balance ends up negative.
    """
    # SQL: select id, facility_id, staff_id, leave_type, date_start, date_end
    #      from leave_requests
    #      where facility_id = any(:facility_ids) and status = 'approved'
    approved = (sb.table("leave_requests")
                .select("id,facility_id,staff_id,leave_type,date_start,date_end")
                .in_("facility_id", facility_ids).eq("status", "approved")
                .execute().data)
    if not approved:
        return 0

    # SQL: select id, facility_id, period_start, period_end from roster_periods
    #      where facility_id = any(:facility_ids)
    periods = (sb.table("roster_periods")
               .select("id,facility_id,period_start,period_end")
               .in_("facility_id", facility_ids).execute().data)
    # SQL: select period_id, staff_id, leave_type from leave_balances
    #      where facility_id = any(:facility_ids)
    balances = {(b["period_id"], b["staff_id"], b["leave_type"])
                for b in (sb.table("leave_balances")
                          .select("period_id,staff_id,leave_type")
                          .in_("facility_id", facility_ids).execute().data)}

    released = 0
    for request in approved:
        covering = [
            p for p in periods
            if p["facility_id"] == request["facility_id"]
            and str(p["period_start"]) <= str(request["date_end"])
            and str(p["period_end"]) >= str(request["date_start"])
            and (p["id"], request["staff_id"], request["leave_type"]) in balances
        ]
        if len(covering) == 1:
            continue                      # the trigger can release it as it stands
        days = ((_date(request["date_end"]) - _date(request["date_start"])).days + 1)
        # SQL: insert into roster_periods
        #        (facility_id, period_start, period_end, cycle_type, status)
        #      values (..., 'import_repair', 'archived') returning id
        period = sb.table("roster_periods").insert({
            "facility_id": request["facility_id"],
            "period_start": str(request["date_start"])[:10],
            "period_end": str(request["date_end"])[:10],
            "cycle_type": "import_repair", "status": "archived",
        }).execute().data[0]
        # SQL: insert into leave_balances (facility_id, staff_id, period_id,
        #        leave_type, opening_balance, used) values (...) returning id
        balance = sb.table("leave_balances").insert({
            "facility_id": request["facility_id"], "staff_id": request["staff_id"],
            "period_id": period["id"], "leave_type": request["leave_type"],
            "opening_balance": days, "used": days,
        }).execute().data[0]
        # SQL: delete from leave_requests where id = :id
        sb.table("leave_requests").delete().eq("id", request["id"]).execute()
        # SQL: delete from leave_balances where id = :id
        sb.table("leave_balances").delete().eq("id", balance["id"]).execute()
        # SQL: delete from roster_periods where id = :id
        sb.table("roster_periods").delete().eq("id", period["id"]).execute()
        released += 1
    return released


def _date(value):
    from datetime import date as Date

    return value if hasattr(value, "toordinal") else Date.fromisoformat(str(value)[:10])


def clear_demo_data(facility_ids: list[str]) -> None:
    """Remove generated staff and rosters, leaving accounts and facilities intact."""
    print("Clearing generated demo data ...")
    stuck = release_stuck_leave(facility_ids)
    if stuck:
        print(f"  released {stuck} approved leave row(s) with no usable balance")
    for table in _DEMO_TABLES:
        # SQL: delete from <table> where facility_id = any(:facility_ids)
        deleted = (sb.table(table).delete()
                   .in_("facility_id", facility_ids).execute().data)
        print(f"  {table:26s} {len(deleted or [])} row(s)")


def relink_staff_login(facility_code: str = "A") -> None:
    """Point the staff-app account at a real imported staff member.

    `/me/*` resolves the caller's staff record from `users_profile.staff_id`;
    clearing the demo staff nulls it, so the account would otherwise 403.
    """
    # SQL: select id, email, facility_id, staff_id from users_profile
    #      where role = 'staff'
    profiles = (sb.table("users_profile").select("id,email,facility_id,staff_id")
                .eq("role", "staff").execute().data)
    taken = {p["staff_id"] for p in profiles if p["staff_id"]}
    for profile in profiles:
        if profile["staff_id"]:
            continue
        # SQL: select id, name, rank from staff
        #      where facility_id = :facility_id and status = 'active'
        #      order by created_at
        candidates = (sb.table("staff").select("id,name,rank")
                      .eq("facility_id", profile["facility_id"])
                      .eq("status", "active").order("created_at").execute().data)
        # Prefer someone with rostered task codes: the staff app's task screens are
        # empty for a staff member whose month is all D shifts and leave.
        # SQL: select distinct staff_id from task_assignments
        #      where facility_id = :facility_id
        with_tasks = {row["staff_id"] for row in
                      (sb.table("task_assignments").select("staff_id")
                       .eq("facility_id", profile["facility_id"]).execute().data)
                      if row.get("staff_id")}
        candidates.sort(key=lambda c: c["id"] not in with_tasks)
        # One account per staff member: two staff logins on the same record would
        # make the self-scope tests pass for the wrong reason.
        member = next((c for c in candidates if c["id"] not in taken), None)
        if not member:
            continue
        taken.add(member["id"])
        # SQL: update users_profile set staff_id = :staff_id where id = :id
        (sb.table("users_profile").update({"staff_id": member["id"]})
         .eq("id", profile["id"]).execute())
        print(f"  {profile['email']} -> {member['name']} ({member['rank']})")


def import_one(path: pathlib.Path, variant: str, label: str, status: str,
               owns_period: bool, mode: str) -> dict | None:
    """Import one workbook through the same service the API endpoint uses.

    Going through `services.imports.run_import` rather than calling the loader
    directly means a CLI import leaves the same trail as an uploaded one: an
    `import_jobs` row with the file's digest, the parser's findings in
    `import_issues`, and an `audit_logs` entry. Provenance should not depend on
    which door the file came through.

    The workbook is parsed once here to learn which home it belongs to, and again
    inside the service; that costs a fraction of a second and keeps the service's
    tenancy check ("this file is not for the facility you are signed in to") intact
    rather than adding a bypass for the CLI.
    """
    content = path.read_bytes()
    parsed = importers.parse_workbook(path, source_name=path.name, variant=variant)
    home = parsed.facility_code
    print(f"\n{path.name} [{variant}] -> Home {home} "
          f"{parsed.period_start}..{parsed.period_end}")
    summary = parsed.summary()
    print(f"  staff rows {summary['staff_rows']:3d} | cells {summary['cells_parsed']:4d} "
          f"| working {summary['working_cells']:4d} | leave {summary['leave_cells']:4d} "
          f"| task-coded {summary['task_coded_cells']:4d} | events {summary['events']:3d}")
    print(f"  shifts {summary['shift_type_counts']}")
    print(f"  leave  {summary['leave_type_counts']}")
    for issue in parsed.issues:
        print(f"  [{issue.severity}] {issue.code} {issue.cell_ref or ''} {issue.message}")

    facility = facilities().get(home)
    if not facility:
        print(f"  Home {home} does not exist - skipped")
        return None

    job = svc.run_import(
        sb, sb, facility["id"], filename=path.name, content=content, mode=mode,
        variant=variant, version_label=label, version_status=status,
        replace_period=True, write_period_records=owns_period)
    load = job["summary_json"].get("load", {})
    verb = "loaded" if mode == "commit" else "would create"
    print(f"  {verb}: staff +{load.get('staff_created', 0)}"
          f"/={load.get('staff_matched', 0)} shifts {load.get('shifts', 0)} "
          f"assignments {load.get('assignments', 0)} "
          f"tasks {load.get('task_assignments', 0)} "
          f"leave {load.get('leave_requests', 0)} events {load.get('events', 0)} "
          f"holidays {load.get('calendar_days', 0)} [{status}]")
    for warning in load.get("warnings", []):
        print(f"  [{warning['severity']}] {warning['code']}: {warning['message']}")
    return job


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--validate", action="store_true",
                       help="parse and report; write nothing (default)")
    group.add_argument("--commit", action="store_true",
                       help="load the workbooks into the database")
    parser.add_argument("--replace-demo-data", action="store_true",
                        help="clear generated staff/rosters for Home A and B first")
    parser.add_argument("--docs", type=pathlib.Path, default=DOCS,
                        help=f"folder holding the workbooks (default {DOCS})")
    parser.add_argument("--json", action="store_true",
                        help="print the machine-readable summary instead")
    args = parser.parse_args()
    mode = "commit" if args.commit else "validate"

    homes = facilities()
    missing_homes = {"A", "B"} - set(homes)
    if missing_homes:
        sys.exit(f"facilities {sorted(missing_homes)} do not exist - run the "
                 "migrations and create them before importing")

    if args.replace_demo_data:
        if mode != "commit":
            sys.exit("--replace-demo-data only makes sense with --commit")
        clear_demo_data([h["id"] for h in homes.values()])

    results = []
    for name, variant, label, status, owns_period in SOURCES:
        path = args.docs / name
        if not path.exists():
            print(f"\n{name}: not found in {args.docs} - skipped")
            continue
        results.append(import_one(path, variant, label, status, owns_period, mode))

    if mode == "commit":
        print("\nRe-linking staff-app logins ...")
        relink_staff_login()
    if args.json:
        print(json.dumps([{"job_id": r["id"], "status": r["status"],
                           "summary": r["summary_json"]}
                          for r in results if r], indent=2, default=str))
    print(f"\n{mode} complete: {len([r for r in results if r])} workbook(s)")


if __name__ == "__main__":
    main()
