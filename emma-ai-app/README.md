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
| Domain / AI | `emma_core` + **OR-Tools** CP-SAT + Phase 5 deterministic compliance |
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

## Phase 5 extension points

`emma_core/services/validation.py` is the roster compliance source of truth and
composes the Phase 4 task/event/floor evaluators from
`emma_core/services/scheduling.py`. The optimizer, manual validation and publish
guard share those rules; new Phase 6 explanations should consume their structured
evidence rather than reimplementing policy. Ratio and rule configuration are
effective-dated, facility-scoped and protected by RLS. Phase 5 also keeps
Home-specific night, agency, part-time and leave policies in the same versioned
rule model; publication is an atomic, validation-gated database operation with
one operative roster per period.
