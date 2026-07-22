# Emma AI — all-Python app

Intelligent nurse/care-worker rostering for HK residential care homes.
Manager dashboard, REST API, domain logic and (later) the OR-Tools solver —
all authored in Python.

## Stack
| Concern | Tech |
|---|---|
| UI (manager dashboard) | **Reflex** (Python → React) |
| REST API | **FastAPI** |
| Domain / AI | `emma_core` + **OR-Tools** (later phase) |
| Data + Auth | **Supabase** (Postgres + GoTrue + RLS) |

## Layout
```
emma_core/   shared domain: config, db (Supabase), models, services
api/         FastAPI — REST contract + future mobile PWA
webui/       Reflex — manager dashboard (created by `reflex init`)
supabase/    migrations + seed
tests/       pytest
```

## Dev setup
See **[RUNBOOK.md](RUNBOOK.md)** for the full step-by-step. Quick version
(global Python, no virtualenv):
```bash
pip install -r requirements.txt
npx supabase start          # local Supabase (Docker); prints keys
npx supabase db reset       # apply supabase/migrations/*
python scripts/seed.py      # demo data + dev logins
reflex run                  # UI → http://localhost:3000
python -m pytest            # 11 tests
```

Switching to cloud Supabase later = change the four SUPABASE_*/DATABASE_URL
values in `.env`; nothing else.
