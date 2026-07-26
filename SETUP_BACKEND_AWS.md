# Setup 2 — Backend API on AWS (App Runner, auto-deploy from GitHub)

Deploy the Emma AI **REST API** (FastAPI + uvicorn + OR-Tools) to **AWS App
Runner**. This is the AWS equivalent of "Azure App Service connected to GitHub":
push to your branch → App Runner rebuilds the container from the repo-root
[`Dockerfile`](Dockerfile) → the new version goes live at a public HTTPS URL. No
servers to manage.

**What gets deployed:** the JSON API only. **What does NOT:** the database (that
is Supabase Cloud — do [`SETUP_SUPABASE_DB.md`](SETUP_SUPABASE_DB.md) **first**)
and the UI (see [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md)).

> A live service **cannot** use your local `supabase start` database — the DB must
> already exist on Supabase Cloud before the API can serve anything real.

---

## Prerequisites

1. **Supabase Cloud project ready** — schema pushed + (for test) seeded. From its
   dashboard collect the four values:
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`.
2. An **AWS account** with permission to create App Runner services, IAM roles,
   and Secrets Manager secrets.
3. This repo pushed to **GitHub** (App Runner connects to the GitHub repo).
4. The deployed **frontend origin(s)** for CORS (fill this in after
   [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md); use a placeholder for the first deploy).

> **Region:** use **Singapore `ap-southeast-1`** for App Runner *and* Supabase —
> closest to Hong Kong, and keeps the API↔DB hop in-region.

---

## Step 1 — (recommended) Test the container locally first

Catch build problems on your machine before wiring AWS. With Docker Desktop
running, from the **repo root**:

```bash
docker build -t emma-ai-api .
```

```bash
docker run --rm -p 8080:8080 \
  -e APP_ENV=test \
  -e CORS_ORIGINS=http://localhost:3001 \
  -e SUPABASE_URL=... \
  -e SUPABASE_ANON_KEY=... \
  -e SUPABASE_SERVICE_ROLE_KEY=... \
  -e DATABASE_URL=... \
  emma-ai-api
```

Verify:
- http://localhost:8080/health → `{"status":"ok"}`
- http://localhost:8080/docs → interactive Swagger UI

If that works, App Runner will too. (The image is `python:3.12-slim`; OR-Tools,
`psycopg[binary]`, and `supabase` ship manylinux wheels, so no apt toolchain is
needed.)

---

## Step 2 — Store the service-role key as a secret

`SUPABASE_SERVICE_ROLE_KEY` bypasses RLS — treat it like a root password. Put it
in **AWS Secrets Manager**, not in plain env config.

```bash
aws secretsmanager create-secret \
  --name emma/test/supabase-service-role-key \
  --secret-string "<service_role_key_from_supabase>" \
  --region ap-southeast-1
```

Note the returned **ARN** — you reference it in Step 3. (The App Runner
instance role needs `secretsmanager:GetSecretValue` on this ARN; the console
wizard can create that role for you.)

---

## Step 3 — Create the App Runner service

AWS Console → **App Runner** → **Create service**.

**1. Source**
- Repository type: **Source code repository**.
- **Add new** → create a **GitHub connection** (GitHub OAuth authorization — you
  must do this interactively; it can't be automated). Pick this repo and the
  **branch** to deploy (e.g. `p2-python-app`).
- **Deployment trigger: Automatic** ← the "auto-build on push" part.

**2. Build settings**
- Build type: **Dockerfile**.
- Dockerfile path: `Dockerfile` (repo root). Source directory: `/`.

**3. Service settings**
- **Port: `8080`** (matches the Dockerfile).
- CPU / Memory: start with **1 vCPU / 2 GB** (bump if the OR-Tools solver runs out
  of memory).
- **Environment variables** (plain text):

  | Key | Value |
  |-----|-------|
  | `APP_ENV` | `test` (or `production`) |
  | `SUPABASE_URL` | your Supabase project URL |
  | `SUPABASE_ANON_KEY` | anon / public key |
  | `DATABASE_URL` | Supabase connection URI |
  | `CORS_ORIGINS` | comma-separated frontend origin(s), e.g. `https://main.xxxx.amplifyapp.com` |

- **Secret reference** (not plain env): map `SUPABASE_SERVICE_ROLE_KEY` to the
  Secrets Manager ARN from Step 2.

**4. Health check**
- Protocol **HTTP**, Path **`/health`**.
- Interval `10s`, Timeout `5s`, Healthy threshold `1`, Unhealthy threshold `5`.

**5. Auto scaling**
- Min `1` is a safe default. Job state (`optimization_jobs`) lives in Postgres, so
  polling works across instances. The one caveat: an `/optimize-roster` request's
  background solve runs on the instance that received it — for the pilot, **Min 1
  / Max 1** is simplest and avoids that concern entirely.

Click **Create & deploy**. First build takes **~5–10 min** (installs OR-Tools).
There is no frontend to bake, so the service is fully live as soon as it reaches
**Running**. ✅

---

## Step 4 — Grab the public URL

When the service reaches **Running**, App Runner shows a **Default domain**:

```
https://abc123xyz.ap-southeast-1.awsapprunner.com
```

Verify it: open `<url>/health` and `<url>/docs`. This URL is what the UI's
`NEXT_PUBLIC_API_URL` points at (see [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md)), and
this URL's origin must appear in the UI's own CORS story — the API must list the
**UI's** origin in `CORS_ORIGINS`.

---

## Step 5 — (optional) Custom domain

App Runner → your service → **Custom domains** → add e.g. `api.emma.example.com`.
It provisions an ACM certificate and gives you DNS records (CNAME) to add at your
registrar. After it validates, update the UI's `NEXT_PUBLIC_API_URL` to the custom
domain.

---

## Ongoing — auto-deploy

Every push to the deploy branch triggers a fresh build + release:

```bash
git push origin p2-python-app
```

Watch progress in App Runner → your service → **Activity / Logs**.

---

## Notes & troubleshooting

| Symptom | Fix |
|---|---|
| **CORS error** in the browser | The UI's origin isn't in `CORS_ORIGINS`. Add it (comma-separated), redeploy the service (env change triggers a release). |
| `500` / DB errors on every call | `DATABASE_URL` / `SUPABASE_*` wrong, or the schema was never pushed. Re-check Step 3 and [`SETUP_SUPABASE_DB.md`](SETUP_SUPABASE_DB.md). |
| Health check failing | Path must be `/health`, port `8080`. Check **Logs** for a startup traceback. |
| Build OOM / timeout | Increase instance memory, or build in GitHub Actions → push to **ECR** → run App Runner in image-based mode. |
| `401 unauthorized` from clients | Expected without a bearer token; log in via `/auth/login` first. Not a deploy issue. |
| `test` vs `production` | `APP_ENV=test` uses the seeded demo project; `production` points at `emma-prod`. Start with `test`. |

**Cost (rough):** 1 vCPU / 2 GB always-on ≈ **$10–50/month** depending on traffic.
App Runner also bills a small "provisioned but idle" rate — scale Max down for a
pilot.

---

## What's next

API is live. Point the UI at its URL → [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md).
