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
RLS.
