# Emma AI — Python API service

Intelligent nurse/care-worker rostering for HK residential care homes. This
package is the **FastAPI REST backend** (domain logic, Supabase data/auth, and
the OR-Tools Roster A/B/C solver). It's the backend half of a monorepo — the
**Next.js frontend lives at the repo root** ([`../`](..)) and consumes this API;
there is no Python UI here.

## Stack
| Concern | Tech |
|---|---|
| REST API | **FastAPI** (uvicorn) |
| Domain / AI | `emma_core` + **OR-Tools** CP-SAT + Phase 4 operational rules |
| Data + Auth | **Supabase** (Postgres + GoTrue + RLS) |
| Frontend (separate repo) | **Next.js** — consumes this API |

## Layout
```
emma_core/   shared domain: config, db, models, services, scheduling rules, solver/
api/         FastAPI app + thin routers, including task/event scheduling
supabase/    migrations + seed
scripts/     seed.py
tests/       pytest (offline solver/service tests + HTTP router tests)
```

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

## Phase 4 extension points

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
