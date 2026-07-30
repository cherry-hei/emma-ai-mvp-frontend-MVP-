# Emma AI - Run Guide (step by step)

Everything below is run from **`emma-ai-app/`** in **PowerShell** on Windows,
using your **global Python** (no virtualenv).

```powershell
cd E:\kuro\test\emma-ai\emma-ai-app
```

> This package is Python only: **FastAPI** (REST API) · **Supabase** (Postgres +
> Auth + RLS) · `emma_core` (domain + OR-Tools solver). The UI is a separate
> Next.js app (repo `main`) that calls this API.
>
> **Note (global Python):** dependencies are shared with your other projects, so
> versions can clash. If that ever bites, `uv` or `pipx` give isolation without
> the venv-activation friction.

---

## 0. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.12+ | `python --version` |
| Node + npm | 18+ | `node --version` (for the `supabase` CLI) |
| Docker Desktop | **running** | `docker ps` |
| Git | any | `git --version` |

Docker Desktop must be running before you start Supabase.

---

## 1. First-time setup (do once)

### 1.1 Install dependencies (into global Python)
```powershell
pip install -r requirements.txt
```

### 1.2 Start local Supabase (first run pulls Docker images - a few GB)
```powershell
npx supabase start
```
It prints the API URL, anon key, service_role key and DB URL when ready.

### 1.3 `.env`
A working `.env` already exists with the standard local Supabase keys. If your
keys differ, copy the template and paste the values `supabase start` printed:
```powershell
copy .env.example .env    # then edit the 4 SUPABASE_*/DATABASE_URL values
```

### 1.4 Create schema + demo data
```powershell
npx supabase db reset      # applies supabase/migrations/*  (schema + RLS + grants)
python scripts/seed.py     # Home A/B, staff, demo roster, ratio rules, dev logins
```

---

## 2. Run the API (every time)

**Supabase** (skip if `docker ps` already shows `supabase_*_emma-ai-app`):
```powershell
npx supabase start
```

**FastAPI:**
```powershell
uvicorn api.main:app --reload
```
Serves on **http://localhost:8000**. Interactive docs at
**http://localhost:8000/docs**; the OpenAPI schema the frontend codegens from is
at **http://localhost:8000/openapi.json**.

> **CORS:** the Next.js frontend is a separate origin. It defaults to
> `http://localhost:3000`; set `CORS_ORIGINS` (comma-separated) in `.env` to add
> more.

---

## 3. Call the API

Authenticate, then send the returned `access_token` as a bearer token:

```powershell
# 1) log in (seeded dev accounts, password EmmaDev123!)
curl -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"super_a@emma.local","password":"EmmaDev123!"}'
# 2) use the access_token from the response:
curl http://localhost:8000/auth/me -H "Authorization: Bearer <access_token>"
```

The login response also returns a `refresh_token`. When the short-lived
`access_token` expires, `POST /auth/refresh` with `{"refresh_token":"<...>"}` mints a
fresh session - the Next.js frontend does this automatically on a `401`, falling back
to the `/login` screen only when the refresh token is itself expired.

Seeded accounts:

| Email | Role | Facility |
|---|---|---|
| `super_a@emma.local` | Superintendent | Home A |
| `admin_a@emma.local` | Admin | Home A |
| `super_b@emma.local` | Superintendent | Home B |

Every non-auth endpoint is RLS-scoped by the bearer token's facility, so Home A
tokens never see Home B data. Try `/roster-periods`, `/rosters/{period_id}`,
`/compliance/ratio?date=YYYY-MM-DD`, and the Phase 2 `/optimize-roster` flow from
`/docs`.

---

## 4. Run the tests
```powershell
python -m pytest -q
```
Offline solver/service unit tests need no DB; the DB-backed service tests and the
HTTP router tests use the seeded local Supabase.

---

## 5. Reset / reseed the database
```powershell
npx supabase db reset
python scripts/seed.py
```

---

## 6. Inspect data
- **Supabase Studio**: http://localhost:54323 (tables, SQL, auth users)
- **Mailpit** (auth emails): http://localhost:54324

---

## 7. Stop everything
- **API**: `Ctrl+C` in the uvicorn terminal.
- **Supabase**: `npx supabase stop`

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `supabase start` errors | Ensure **Docker Desktop is running** (`docker ps`). |
| Port 8000 in use | `uvicorn api.main:app --reload --port 8001`. |
| Browser **CORS error** from the frontend | Add the frontend origin to `CORS_ORIGINS` in `.env` and restart uvicorn. |
| `401 unauthorized` | Send `Authorization: Bearer <access_token>` from `/auth/login`; the token expires - log in again. |
| Login fails | Run `python scripts/seed.py` after `db reset`; password `EmmaDev123!`. |
| Schema/permission errors | Re-run `npx supabase db reset`, then reseed. |

---

## 9. Switch to cloud Supabase (later)
1. Create a project at supabase.com.
2. Run the files in `supabase/migrations/` (in order) in its SQL editor, or
   `supabase db push`.
3. Run `python scripts/seed.py` against the cloud DB.
4. Replace the four `SUPABASE_*`/`DATABASE_URL` values in `.env`. No code changes.

---

## Reference - ports

| Service | URL |
|---|---|
| FastAPI | http://localhost:8000 (docs at `/docs`) |
| Supabase API | http://localhost:54321 |
| Supabase DB | postgresql://postgres:postgres@localhost:54322/postgres |
| Supabase Studio | http://localhost:54323 |
| Mailpit | http://localhost:54324 |
