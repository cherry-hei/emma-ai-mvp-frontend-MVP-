"""Read-only duplicate checks for migrations 10-20, before `supabase db push`.

Use DATABASE_URL and --json for aggregate evidence. Every query is a SELECT;
permission errors and timeouts are blockers. Missing objects are skipped only
when their migration has not been applied. This is not a backup, restore test
or a completeness check for later migrations.

Exit codes: 0 no detected blockers, 1 blockers, 2 inspection unavailable.
"""
from __future__ import annotations

import argparse
import json
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
    except Exception as exc:
        if getattr(exc, "sqlstate", None) in {"42P01", "3F000"}:
            return []
        raise


def inspect(conn) -> dict:
    """Return aggregate evidence only; never include record contents or a DSN."""
    versions = {
        str(int(path.stem.split("_", 1)[0][-6:])): path.stem.split("_", 1)[0]
        for path in (pathlib.Path(__file__).parents[1] / "supabase/migrations").glob("*.sql")
    }
    checks = []
    with conn.cursor() as cur:
        applied = _applied(cur)
        for label, migration, severity, sql in CHECKS:
            result = {"check": label, "migration": migration}
            try:
                cur.execute(sql)
                count = len(cur.fetchall())
            except Exception as exc:
                code = getattr(exc, "sqlstate", None)
                pending = versions.get(migration) not in applied
                if code in {"42P01", "42703"} and pending:
                    result.update(status="not_present", groups=0)
                else:
                    result.update(status="block", error=code or type(exc).__name__)
            else:
                result.update(status=severity if count else "ok", groups=count)
            checks.append(result)
    return {
        "read_only": True,
        "applied": applied,
        "checks": checks,
        "blockers": sum(row["status"] == "block" for row in checks),
        "warnings": sum(row["status"] == "warn" for row in checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("DATABASE_URL"),
                        help="Postgres URI. Use the SESSION pooler (port 5432), "
                             "not the transaction pooler (6543).")
    parser.add_argument("--json", action="store_true", help="Emit aggregate evidence without database records")
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
        conn = psycopg.connect(
            args.url, connect_timeout=15, autocommit=True,
            options="-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: could not connect ({type(exc).__name__})", file=sys.stderr)
        return 2

    try:
        with conn:
            report = inspect(conn)
    except Exception as exc:
        print(f"error: pre-flight unavailable ({getattr(exc, 'sqlstate', None) or type(exc).__name__})", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Connected. {len(report['applied'])} migrations recorded as applied.")
        for row in report["checks"]:
            detail = row.get("error") or f"{row.get('groups', 0)} group(s)"
            print(f"  {row['status']} [{row['migration']}] {row['check']}: {detail}")
        print(f"{report['blockers']} blockers; {report['warnings']} warnings requiring review.")
    return 1 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
