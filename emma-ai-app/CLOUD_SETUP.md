# Cloud setup - Supabase (test + production)

We host on **Supabase Cloud** rather than raw Amazon RDS because the app is
built on Supabase's managed layer - PostgREST (`client.table(...)`), GoTrue auth
(`sign_in_with_password`), and JWT-driven **RLS multi-tenancy** (the Home A vs
Home B isolation proven in `tests/test_rls_isolation.py`). Plain RDS provides
none of those, so it would mean rewriting the data layer, auth, and RLS. Supabase
Cloud keeps 100% of the code; switching environments is a config change only.

Two isolated projects, one per environment:

| Environment | APP_ENV      | env file          | Supabase project |
|-------------|--------------|-------------------|------------------|
| Local dev   | (unset)      | `.env`            | `supabase start` |
| Test        | `test`       | `.env.test`       | `emma-test`      |
| Production  | `production` | `.env.production` | `emma-prod`      |

## What's already wired (in the repo)

- `emma_core/config.py` selects the env file from `APP_ENV` (falls back to `.env`).
- `.env.example` documents every value and where to find it in the dashboard.
- `.gitignore` blocks `.env` / `.env.*` (only `.env.example` is tracked).

## What you need to do

Prereqs: a Supabase account and the Supabase CLI (already used locally for
`supabase start`). Run everything below from the `emma-ai-app/` directory.

### 1. Create the two projects
In the Supabase dashboard, create **`emma-test`** and **`emma-prod`**, both in the
**Singapore (`ap-southeast-1`)** region - closest to Hong Kong (Supabase has no HK
region). Save each project's database password somewhere safe (a secrets manager,
not this repo).

### 2. Fill the env files
Copy the template once per cloud environment and fill in the values from each
project's **Settings → API** (URL, anon key, service_role key) and
**Settings → Database → Connection string → URI** (`DATABASE_URL`):

```bash
cp .env.example .env.test          # set APP_ENV=test,       emma-test values
cp .env.example .env.production    # set APP_ENV=production,  emma-prod values
```

### 3. Push the schema + RLS to each project
This applies `supabase/migrations/` (schema, RLS tenancy, grants) to the remote.
Do it once per project - link, push, repeat:

```bash
supabase login
supabase link --project-ref <emma-test-ref>
supabase db push
supabase link --project-ref <emma-prod-ref>
supabase db push
```

### 4. Seed demo data - TEST ONLY
The seed creates the Home A / Home B demo facilities and dev auth users. Run it
against **test only** - never production (prod starts empty and gets real data
through the app):

```powershell
$env:APP_ENV = "test"; python scripts/seed.py      # PowerShell
```
```bash
APP_ENV=test python scripts/seed.py                 # bash
```

### 5. Verify RLS isolation against test
After seeding, prove the multi-tenancy boundary holds on cloud:

```powershell
$env:APP_ENV = "test"; python -m pytest tests/test_rls_isolation.py -v
```

## Switching environments day-to-day

```powershell
$env:APP_ENV = "test"        # or "production"; unset for local dev
```
```bash
export APP_ENV=test          # or "production"; unset for local dev
```

`APP_ENV` also flips the app out of dev mode - `State.is_dev`
(`emma_web/state.py`) is `True` only when `APP_ENV=development`.

## Security notes

- **`SUPABASE_SERVICE_ROLE_KEY` bypasses RLS entirely** - it's effectively a root
  key over all tenants. Keep it only in the local (gitignored) env file and in
  your deploy platform's secret store. Never commit it, never ship it to the
  browser/frontend client (server-side use only).
- Use **separate** service-role keys for test and prod (each project has its own).
- The AWS access key pasted in chat is not used by this setup - delete it in
  **IAM → Users → Security credentials** since it's been exposed.
