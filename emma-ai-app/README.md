# Emma AI - Python API service

Intelligent nurse/care-worker rostering for HK residential care homes. This
package is the **FastAPI REST backend** (domain logic, Supabase data/auth, and
the OR-Tools Roster A/B/C solver). It's the backend half of a monorepo - the
**Next.js frontend lives at the repo root** ([`../`](..)) and consumes this API;
there is no Python UI here.

## Stack
| Concern | Tech |
|---|---|
| REST API | **FastAPI** (uvicorn) |
| Domain / AI | `emma_core` + **OR-Tools** CP-SAT + Phase 5 deterministic compliance |
| Data + Auth | **Supabase** (Postgres + GoTrue + RLS) |
| Frontend (separate repo) | **Next.js** - consumes this API |

## Layout
```
emma_core/             shared domain: config, db, models, services, rules
emma_core/importers/   reads the homes' real roster workbooks (spec 1.4)
emma_core/solver/      OR-Tools CP-SAT Roster A/B/C engine
api/                   FastAPI app + thin routers
supabase/              migrations + seed
scripts/               seed.py (demo data) · import_real_rosters.py (real data)
tests/                 pytest (offline parser/solver/service tests + HTTP tests)
```

Two ways to fill the database, and they are alternatives:

```bash
python scripts/seed.py                                  # generated demo fixture
python scripts/import_real_rosters.py --validate        # parse the real rosters
python scripts/import_real_rosters.py --commit --replace-demo-data
```

The importer records an `import_jobs` row with the file's digest, every
unresolved cell in `import_issues`, and an `audit_logs` entry - the same trail an
upload through `POST /imports/roster-excel` leaves, because both go through
`emma_core/services/imports.py`.

DB-backed tests state the data they need and skip when the database holds the
other fixture (see `tests/_dbstate.py`); a roster spreadsheet carries no
certificates, incidents, agency invoices or clock-ins.

## Dev setup
See **[RUNBOOK.md](RUNBOOK.md)** for the full step-by-step. Quick version
(global Python, no virtualenv):
```bash
pip install -r requirements.txt
npx supabase start                       # local Supabase (Docker); prints keys
npx supabase db reset                    # apply supabase/migrations/*
python scripts/seed.py                   # demo data + dev logins
uvicorn api.main:app --reload            # API → http://localhost:8000 (docs at /docs)
python -m pytest                         # tests
```

The interactive OpenAPI docs live at `http://localhost:8000/docs`; the Next.js
frontend codegens its typed client from `http://localhost:8000/openapi.json`.

CORS: set `CORS_ORIGINS` (comma-separated) to the frontend origin(s); it defaults
to `http://localhost:3000`.

Switching to cloud Supabase later = change the four `SUPABASE_*`/`DATABASE_URL`
values in `.env`; nothing else.

## Phase 5 extension points

`emma_core/services/validation.py` is the roster compliance source of truth and
composes the Phase 4 task/event/floor evaluators from
`emma_core/services/scheduling.py`. The optimizer, manual validation and publish
guard share those rules; new explanations should consume their structured
evidence rather than reimplementing policy. Ratio and rule configuration are
effective-dated, facility-scoped and protected by RLS. Home-specific night,
agency, part-time, leave and consecutive-day policies live in the same versioned
rule model; publication is an atomic, validation-gated database operation with
one operative roster per period.

`emma_core/services/scheduling.py` owns the pure task-eligibility, event-staffing
and floor-coverage evaluators. API writes, roster validation and publishing all
call those functions. Add later automatic checks and explanations there rather
than duplicating policy in routers or UI code. The Phase 4 migration stores
versionable qualification, event-requirement and floor-rule data with facility
RLS, and `/staff-qualifications` + `/floor-rules` expose them for editing.

A rejection that carries reasons raises `emma_core.errors.RuleViolationError`
rather than a bare `ValueError`, so the issue list survives to the client as
`detail.issues` instead of being flattened into one sentence.

### Upgrading an environment seeded before Phase 4

`scripts/seed.py` produces a correct Phase 4 fixture, but only by wiping and
recreating both demo facilities. For a database that already carries real
rosters, use the additive backfill instead — it reconciles the task dictionary,
qualifications and floor rules, rewrites roster-cell task labels to the codes
that match each shift, and never deletes a roster:

```bash
python scripts/backfill_phase4.py --dry-run   # report
python scripts/backfill_phase4.py             # apply (idempotent)
```

### Tests

`tests/test_phase4.py` covers the pure evaluators offline.
`tests/test_phase4_live.py` runs the same rules through real logins, real HTTP
and real rows — it is what catches an unapplied migration, a column the service
selects but the schema lacks, or an RLS policy that hides a rule table. Both
need to pass; the offline file alone cannot tell you the feature works.
