"""Apply pending migrations from `supabase/migrations/` to a database.

    python scripts/apply_migrations.py --dry-run          # list what would run
    python scripts/apply_migrations.py                    # apply, using DATABASE_URL
    python scripts/apply_migrations.py --url postgres://...

Writes the same `supabase_migrations.schema_migrations` ledger the Supabase CLI
uses - same table, same `version` / `name` / `statements` columns - so the two
are interchangeable and `supabase migration list` reads what this wrote.

Why this exists rather than just `supabase db push`
---------------------------------------------------
The CLI is a Go binary that has to be installed. This is the thing that decides
whether the production schema moves, so it should be runnable from any developer
machine and from CI without a toolchain step in between, and it should be the
*same* code in both places. A migration path that only works where the CLI
happens to be installed is how a schema ends up ten versions behind.

Two properties worth stating, because they are the ones that matter at 2am:

*Each migration is one transaction.* A file that fails rolls back whole, and the
ledger is written inside the same transaction as the DDL. There is no state where
a migration half-applied or where the ledger claims a migration that did not run.

*It stops at the first failure.* The remaining files are not attempted. A partial
sequence is recoverable - fix the cause and re-run, and it resumes from where it
stopped - whereas skipping past a failure to "get the rest in" produces a schema
nobody can reason about.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "supabase" / "migrations"
NAME = re.compile(r"^(?P<version>\d{14})_(?P<name>.+)\.sql$")


def discover() -> list[tuple[str, str, pathlib.Path]]:
    """(version, name, path) for every migration, in version order."""
    out = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        match = NAME.match(path.name)
        if not match:
            print(f"  ! skipping {path.name} - not <14-digit version>_<name>.sql")
            continue
        out.append((match.group("version"), match.group("name"), path))
    return out


def applied(cur) -> set[str]:
    cur.execute("""
        create schema if not exists supabase_migrations;
        create table if not exists supabase_migrations.schema_migrations (
            version text primary key,
            statements text[],
            name text
        );
    """)
    cur.execute("select version from supabase_migrations.schema_migrations")
    return {r[0] for r in cur.fetchall()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true",
                        help="list pending migrations and exit without connecting "
                             "for writes")
    args = parser.parse_args()
    if not args.url:
        print("error: no DATABASE_URL. Pass --url or set the environment variable.",
              file=sys.stderr)
        return 2

    try:
        import psycopg
    except ImportError:
        print("error: psycopg is not installed (pip install 'psycopg[binary]')",
              file=sys.stderr)
        return 2

    all_migrations = discover()
    try:
        conn = psycopg.connect(args.url, connect_timeout=20)
    except Exception as exc:  # noqa: BLE001
        print(f"error: could not connect - {exc}", file=sys.stderr)
        return 2

    with conn:
        with conn.cursor() as cur:
            done = applied(cur)
        conn.commit()

        pending = [m for m in all_migrations if m[0] not in done]
        print(f"{len(all_migrations)} migration file(s), {len(done)} already "
              f"applied, {len(pending)} pending.")
        if not pending:
            print("Nothing to do.")
            return 0
        for version, name, _ in pending:
            print(f"  pending  {version}  {name}")
        if args.dry_run:
            print("\nDry run - nothing applied.")
            return 0
        print()

        for version, name, path in pending:
            sql = path.read_text(encoding="utf-8")
            print(f"  applying {version}  {name} ... ", end="", flush=True)
            try:
                # One transaction per migration, ledger row included. psycopg
                # opens a transaction implicitly and this commits it, so a raise
                # anywhere inside rolls back both the DDL and the ledger write.
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "insert into supabase_migrations.schema_migrations "
                        "(version, name, statements) values (%s, %s, %s) "
                        "on conflict (version) do nothing",
                        (version, name, [sql]))
                conn.commit()
                print("ok")
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                print("FAILED")
                print(f"\n{version}_{name}.sql rolled back whole. Nothing after "
                      f"it was attempted.\n\n{exc}\n", file=sys.stderr)
                print("Fix the cause and re-run - it resumes from here.",
                      file=sys.stderr)
                return 1

    print("\nAll pending migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
