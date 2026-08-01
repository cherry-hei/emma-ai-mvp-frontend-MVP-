# Setup 1 - Supabase database (on Supabase Cloud)

How to stand up the Emma AI database on **Supabase Cloud** for the `test` and
`production` environments: create the projects, apply the schema + RLS, seed demo
data (test only), and verify the multi-tenancy boundary.

> **Why Supabase (not raw RDS)?** The app is built on Supabase's managed layer -
> PostgREST (`client.table(...)`), GoTrue auth (`sign_in_with_password`), and
> JWT-driven **RLS multi-tenancy** (Home A vs Home B isolation). Plain RDS gives
> none of those, so it would mean rewriting the data layer, auth, and RLS.
> Supabase Cloud keeps 100% of the code - switching environments is config only.

This is the database half of the deployment. It pairs with:
- [`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md) - the API that talks to this DB.
- [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md) - the UI that talks to the API.

---

## Environments

> **Reality as of 1 Aug 2026: there is one Supabase project, not the three below.**
> `.env` here holds `DATABASE_URL`/`SUPABASE_URL` for `eadisvkosqdnikhzmndz` -
> that is the same project the deployed API uses. The `emma-test` / `emma-prod`
> split this section describes was never actually created. Do not stand up a
> second project by following this table literally; the single-project setup is
> the current, intentional state, confirmed with Kien and Cherry. The table is
> left below as a record of the originally-planned layout, in case a real
> test/prod split is wanted later - it is not a live setup guide right now.

Originally-planned layout - two **isolated** cloud projects, one per environment
(plus a local dev DB), never built:

| Environment | `APP_ENV`    | env file          | Supabase project |
|-------------|--------------|-------------------|------------------|
| Local dev   | (unset)      | `.env`            | `supabase start` |
| Test        | `test`       | `.env.test`       | `emma-test`      |
| Production  | `production` | `.env.production` | `emma-prod`      |

`emma_core/config.py` picks the env file from `APP_ENV` (falls back to `.env`).
`.gitignore` blocks `.env` / `.env.*` - only `.env.example` is tracked.

---

## Prerequisites

| Tool | Notes |
|---|---|
| Supabase account | https://supabase.com |
| Supabase CLI | `npx supabase --version` (same CLI used for `supabase start` locally) |
| Python 3.12+ | for `scripts/seed.py` and the RLS verification test |
| Repo checked out | run all commands below from **`emma-ai-app/`** |

```powershell
cd E:\kuro\test\emma-ai\emma-ai-app
```

---

## Step 1 - Create the two projects

In the Supabase dashboard, create **`emma-test`** and **`emma-prod`**, both in the
**Singapore (`ap-southeast-1`)** region - closest to Hong Kong (Supabase has no HK
region). Use the **same region for the API** so the API↔DB hop stays in-region.

For each project, **save the database password** in a secrets manager (never in
this repo). You will also need, from each project's dashboard:

| Value | Where in the dashboard |
|---|---|
| `SUPABASE_URL` | Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | Settings → API → Project API keys → **anon / public** |
| `SUPABASE_SERVICE_ROLE_KEY` | Settings → API → Project API keys → **service_role** (secret) |
| `DATABASE_URL` | Settings → Database → Connection string → **URI** |

> For migrations/seed against a cloud project, prefer the **Session pooler** /
> direct connection URI (port `5432`). The transaction pooler (port `6543`) is for
> the app's runtime pooled traffic.

---

## Step 2 - Fill the env files

Copy the template once per cloud environment and paste the four values above:

```bash
cp .env.example .env.test          # APP_ENV=test,       emma-test values
cp .env.example .env.production    # APP_ENV=production,  emma-prod values
```

Each file needs: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
`DATABASE_URL`, and the matching `APP_ENV`.

---

## Step 3 - Push the schema + RLS to each project

This applies everything in `supabase/migrations/` (schema, RLS tenancy, grants,
Phase 2 solver tables, staff certificates) to the remote. Do it **once per
project** - link, push, repeat:

```bash
supabase login
supabase link --project-ref <emma-test-ref>
supabase db push

supabase link --project-ref <emma-prod-ref>
supabase db push
```

The project ref is the `xxxx` in `https://<ref>.supabase.co` (Settings → General).

Migrations applied (in order):

| File | What it creates |
|---|---|
| `20260721000001_init_slice_schema.sql` | Core schema (facilities, staff, roster, ratio rules, …) |
| `20260721000002_rls_tenancy.sql` | Row-Level Security policies (per-facility isolation) |
| `20260721000003_grants.sql` | Role grants for `anon` / `authenticated` / `service_role` |
| `20260722000004_solver_phase2.sql` | `optimization_jobs` + solver tables |
| `20260725000005_extend_ranks_roles_tasks.sql` | Ranks / roles / tasks extensions |
| `20260726000006_staff_certificates.sql` | Staff certificates |

> **Alternative (no CLI link):** paste each migration file, **in order**, into the
> project's SQL Editor and run it. `supabase db push` is preferred - it tracks
> which migrations have already been applied.

---

## Step 4 - Seed demo data (⚠ TEST ONLY)

The seed creates the Home A / Home B demo facilities, staff, demo roster, ratio
rules, and dev auth users. Run it against **test only** - never production.
Production starts empty and gets real data through the app.

```powershell
$env:APP_ENV = "test"; python scripts/seed.py      # PowerShell
```
```bash
APP_ENV=test python scripts/seed.py                 # bash
```

Seeded dev logins (password `EmmaDev123!`):

| Email | Role | Facility |
|---|---|---|
| `super_a@emma.local` | Superintendent | Home A |
| `admin_a@emma.local` | Admin | Home A |
| `super_b@emma.local` | Superintendent | Home B |

---

## Step 5 - Verify RLS isolation (against test)

Prove the multi-tenancy boundary holds on the cloud project - a Home A token must
never see Home B data:

```powershell
$env:APP_ENV = "test"; python -m pytest tests/test_rls_isolation.py -v
```

All tests passing = the tenant boundary is enforced by the database, not just the
app.

---

## Step 6 - Sanity-check production is empty but healthy

```powershell
$env:APP_ENV = "production"; python -c "from emma_core.config import get_settings; print(get_settings().supabase_url)"
```

Confirm it prints the **emma-prod** URL (not test). Do **not** seed it.

---

## Day-to-day: switching environments

```powershell
$env:APP_ENV = "test"        # or "production"; unset for local dev
```
```bash
export APP_ENV=test          # or "production"; unset for local dev
```

---

## Security notes

- **`SUPABASE_SERVICE_ROLE_KEY` bypasses RLS entirely** - it is effectively a root
  key over all tenants. Keep it only in the local (gitignored) env file and in
  your deploy platform's secret store (AWS Secrets Manager - see
  [`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md)). Never commit it, never ship it to
  the browser/frontend.
- Use **separate** service-role keys for test and prod (each project has its own).
- Enable **daily backups / PITR** on the prod project (Settings → Database).
- Restrict who can view the prod project's keys in the Supabase org settings.

---

## What's next

The database is ready. Deploy the API against it →
[`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md).
