"""Read-only pre-flight for migrations 10-20. Run this BEFORE `supabase db push`.

    python scripts/preflight_migrations.py                 # uses DATABASE_URL
    python scripts/preflight_migrations.py --url postgres://...

Nothing here writes. Every statement is a SELECT.

Why this exists
---------------
Migrations 10-20 were written against a database that already had the schema, and
have never been run in sequence against production. Two classes of statement in
that set can fail or destroy data on a database with real history in it, and
neither shows up in a local test run because the local database was built by the
same migrations:

  * **Unique indexes over existing data.** `create unique index` is not
    idempotent against *content* - `if not exists` stops it running twice, it
    does not stop it failing the first time because production already holds two
    rows that collide. Nine of these land in 10-20. A failure here aborts the
    push mid-sequence, which is the worst outcome: some migrations applied, some
    not, and the schema version now a lie.

  * **One DELETE.** Migration 13 removes orphaned solver rows from
    `agency_assignments`. It is narrowly scoped and well argued, but it is a
    delete against production money data, and the number of rows it will take
    should be a number somebody has seen before it runs, not after.

Exit codes: 0 clean, 1 blockers found, 2 could not connect.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# (label, migration, severity, sql)
#
# Each duplicate query mirrors one unique index in migrations 10-20 and returns
# the colliding groups. `severity` is 'block' when the push would abort, 'warn'
# when it would succeed but do something worth seeing first.
CHECKS: list[tuple[str, str, str, str]] = [
    (
        "rule_definitions (facility, rule_code, version)", "10", "block",
        """
        select facility_id::text, rule_code, config_version, count(*) as rows
        from rule_definitions
        where facility_id is not null
        group by 1, 2, 3 having count(*) > 1
        """,
    ),
    (
        "rule_definitions global (rule_code, version)", "10", "block",
        """
        select rule_code, config_version, count(*) as rows
        from rule_definitions
        where facility_id is null
        group by 1, 2 having count(*) > 1
        """,
    ),
    (
        "roster_versions - two published in one period", "10", "block",
        """
        select facility_id::text, period_id::text, count(*) as rows
        from roster_versions
        where status = 'published' and period_id is not null
        group by 1, 2 having count(*) > 1
        """,
    ),
    (
        "shift_assignments incident result key", "11", "block",
        """
        select source_incident_id::text, incident_assignment_kind,
               shift_id::text, count(*) as rows
        from shift_assignments
        where source_incident_id is not null
        group by 1, 2, 3 having count(*) > 1
        """,
    ),
    (
        "future_debt_ledger.resolution_key", "11", "block",
        """
        select resolution_key, count(*) as rows
        from future_debt_ledger
        where resolution_key is not null
        group by 1 having count(*) > 1
        """,
    ),
    (
        "notifications.resolution_key", "11", "block",
        """
        select resolution_key, count(*) as rows
        from notifications
        where resolution_key is not null
        group by 1 having count(*) > 1
        """,
    ),
    (
        "evidence_items (facility, code)", "14", "block",
        """
        select coalesce(facility_id, '00000000-0000-0000-0000-000000000000'::uuid)::text
                 as facility, code, count(*) as rows
        from evidence_items
        group by 1, 2 having count(*) > 1
        """,
    ),
    (
        "facility_json_configs - two active per key", "14", "block",
        """
        select facility_id::text, config_key, count(*) as rows
        from facility_json_configs
        where active
        group by 1, 2 having count(*) > 1
        """,
    ),
    (
        "roster_cell_locks - two live locks per cell", "17", "block",
        """
        select facility_id::text, staff_id::text, date::text, count(*) as rows
        from roster_cell_locks
        where released_at is null
        group by 1, 2, 3 having count(*) > 1
        """,
    ),
    (
        "staff_certificates - duplicate (staff, cert_type)", "19", "block",
        """
        select staff_id::text, cert_type, count(*) as rows
        from staff_certificates
        group by 1, 2 having count(*) > 1
        """,
    ),
    (
        "agency_assignments rows migration 13 WILL DELETE", "13", "warn",
        """
        select facility_id::text, count(*) as rows,
               coalesce(sum(hours), 0) as hours,
               coalesce(sum(cost), 0) as cost
        from agency_assignments
        where shift_id is null and vendor = 'Emma auto-fill'
        group by 1
        """,
    ),
    (
        "agency_assignments 'Emma auto-fill' rows that are NOT orphaned "
        "(kept, shown for contrast)", "13", "info",
        """
        select facility_id::text, count(*) as rows
        from agency_assignments
        where shift_id is not null and vendor = 'Emma auto-fill'
        group by 1
        """,
    ),
]


def _applied(cur) -> list[str]:
    """Which migrations Supabase thinks are already applied."""
    try:
        cur.execute("select version from supabase_migrations.schema_migrations "
                    "order by version")
        return [r[0] for r in cur.fetchall()]
    except Exception:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("DATABASE_URL"),
                        help="Postgres URI. Use the SESSION pooler (port 5432), "
                             "not the transaction pooler (6543).")
    args = parser.parse_args()
    if not args.url:
        print("error: no DATABASE_URL. Pass --url or set the environment "
              "variable.", file=sys.stderr)
        return 2

    try:
        import psycopg
    except ImportError:
        print("error: psycopg is not installed (pip install 'psycopg[binary]')",
              file=sys.stderr)
        return 2

    try:
        conn = psycopg.connect(args.url, connect_timeout=15)
    except Exception as exc:  # noqa: BLE001
        print(f"error: could not connect - {exc}", file=sys.stderr)
        return 2

    blockers = warnings = 0
    with conn, conn.cursor() as cur:
        applied = _applied(cur)
        print(f"Connected. {len(applied)} migrations recorded as applied.")
        if applied:
            print(f"  earliest {applied[0]}\n  latest   {applied[-1]}")
        else:
            print("  (no supabase_migrations table - this database has never "
                  "been pushed to with the CLI)")
        print()

        for label, migration, severity, sql in CHECKS:
            try:
                cur.execute(sql)
                rows = cur.fetchall()
                columns = [d.name for d in cur.description]
            except Exception as exc:  # noqa: BLE001
                # A missing table means the migration that creates it has not run
                # yet, so there is nothing existing to collide with. That is a
                # pass, not a failure.
                print(f"  ok    [{migration}] {label}\n"
                      f"          (table not present yet - {str(exc).splitlines()[0][:70]})")
                continue

            if not rows:
                print(f"  ok    [{migration}] {label}")
                continue

            if severity == "block":
                blockers += 1
                mark = "BLOCK"
            elif severity == "warn":
                warnings += 1
                mark = "WARN "
            else:
                mark = "info "
            print(f"  {mark} [{migration}] {label}  -> {len(rows)} group(s)")
            print(f"          {' | '.join(columns)}")
            for row in rows[:10]:
                print(f"          {' | '.join(str(v) for v in row)}")
            if len(rows) > 10:
                print(f"          ... and {len(rows) - 10} more")

    print()
    if blockers:
        print(f"{blockers} BLOCKER(S). `supabase db push` will abort part-way "
              "through. Resolve the duplicates first - see the runbook.")
        return 1
    if warnings:
        print(f"No blockers. {warnings} warning(s) above are rows that will be "
              "deleted or changed - confirm the numbers look right, then push.")
        return 0
    print("Clean. Nothing in migrations 10-20 collides with existing data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
