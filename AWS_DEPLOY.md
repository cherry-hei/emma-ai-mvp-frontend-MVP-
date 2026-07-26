# Deploy the Emma AI API to AWS App Runner (auto-deploy from GitHub)

This is the AWS equivalent of "Azure App Service connected to GitHub": push to
your branch → App Runner rebuilds the container → the new version goes live at a
public HTTPS URL. No servers to manage.

**What gets deployed:** the Emma AI **REST API** (FastAPI + uvicorn), packaged by
the repo-root [`Dockerfile`](Dockerfile). It serves JSON only — the Next.js
frontend (repo root, same monorepo) is deployed on its own (e.g. Vercel).
**What does NOT get deployed here:** the database. The app talks to **Supabase
Cloud** (see [emma-ai-app/CLOUD_SETUP.md](emma-ai-app/CLOUD_SETUP.md)). A live
service cannot use your local `supabase start` database.

---

## Prerequisites

1. An **AWS account** with permission to create App Runner services, IAM roles,
   and (optionally) Secrets Manager secrets.
2. This repo pushed to **GitHub** (App Runner connects to the GitHub repo).
3. A **Supabase Cloud** project ready (`emma-test` recommended for the first
   deploy — it has seed data + dev logins). From its dashboard collect:
   - `SUPABASE_URL`  (Settings → API → Project URL)
   - `SUPABASE_ANON_KEY`  (Settings → API → anon/public)
   - `SUPABASE_SERVICE_ROLE_KEY`  (Settings → API → service_role — **secret**)
   - `DATABASE_URL`  (Settings → Database → Connection string → URI)
4. The deployed **frontend origin(s)** for CORS (e.g. `https://emma.vercel.app`).

> Region tip: use **Singapore `ap-southeast-1`** for both Supabase and App Runner
> (closest to Hong Kong; Supabase has no HK region).

---

## Step 1 — (recommended) Test the image locally first

Catch build problems on your machine before wiring AWS. With Docker Desktop
running, from the repo root:

```bash
docker build -t emma-ai-api .
```

```bash
docker run --rm -p 8080:8080 -e APP_ENV=test -e CORS_ORIGINS=http://localhost:3000 -e SUPABASE_URL=... -e SUPABASE_ANON_KEY=... -e SUPABASE_SERVICE_ROLE_KEY=... -e DATABASE_URL=... emma-ai-api
```

Then open http://localhost:8080/health (expect `{"status":"ok"}`) and
http://localhost:8080/docs. If that works, App Runner will too.

---

## Step 2 — Create the App Runner service

AWS Console → **App Runner** → **Create service**.

1. **Source**
   - Repository type: **Source code repository**.
   - Click **Add new** to create a **GitHub connection** (GitHub OAuth
     authorization — you must do this; it can't be automated). Pick the repo and
     the **branch** you want to deploy (e.g. `p2-python-app`).
   - **Deployment trigger: Automatic** ← the "auto-build on push" part.

2. **Build settings**
   - Build type: **Dockerfile**.
   - Dockerfile path: `Dockerfile` (repo root). Source directory: `/` (root).

3. **Service settings**
   - **Port: `8080`** (matches the Dockerfile).
   - CPU / Memory: start with **1 vCPU / 2 GB** (bump if OR-Tools runs out of
     memory).
   - **Environment variables** (plain):
     | Key | Value |
     |-----|-------|
     | `APP_ENV` | `test` (or `production`) |
     | `SUPABASE_URL` | your Supabase project URL |
     | `SUPABASE_ANON_KEY` | anon key |
     | `DATABASE_URL` | Supabase connection URI |
     | `CORS_ORIGINS` | comma-separated frontend origin(s), e.g. `https://emma.vercel.app` |
   - **Secret** (do NOT put this in plain env): store
     `SUPABASE_SERVICE_ROLE_KEY` in **AWS Secrets Manager** and reference it here.
     (It bypasses RLS — treat it like a root password. The solver's background
     writeback uses it.)

4. **Health check**
   - Protocol: **HTTP**, Path: **`/health`**.
   - Interval `10s`, Timeout `5s`, Healthy threshold `1`, Unhealthy threshold `5`.

5. **Auto scaling**
   - Min = 1 is a safe default. Job state (`optimization_jobs`) lives in Postgres,
     so polling works across instances; the only caveat is that an optimize
     request's background solve runs on the instance that received it. For the
     pilot, Min = 1 / Max = 1 is simplest.

Click **Create & deploy**. First build takes ~5–10 min (installs OR-Tools).
There is **no frontend to bake**, so the old two-step `API_URL` dance is gone —
the service is fully live as soon as it reaches **Running**. ✅

---

## Step 3 — Grab the public URL

When the service reaches **Running**, App Runner shows a **Default domain** like:

```
https://abc123xyz.ap-southeast-1.awsapprunner.com
```

Point the Next.js frontend's API base URL at it, and make sure that frontend's
origin is in `CORS_ORIGINS`.

---

## Ongoing — auto-deploy

Every push to the deploy branch triggers a fresh build + release:

```bash
git push origin p2-python-app
```

Watch progress in App Runner → your service → **Activity / Logs**.

---

## Notes & troubleshooting

- **Schema/seed on the cloud DB:** the API expects the tables to exist. Push
  migrations once (`supabase db push`) and, for a test environment, seed it
  (`APP_ENV=test python scripts/seed.py`). Full steps in
  [CLOUD_SETUP.md](emma-ai-app/CLOUD_SETUP.md).
- **CORS errors in the browser:** the frontend origin isn't in `CORS_ORIGINS`.
  Add it (comma-separated) and redeploy.
- **`test` vs `production`:** `APP_ENV=test` works with seeded demo logins;
  `production` points at the prod Supabase project. Start with `test`.
- **Build OOM / timeout:** increase instance memory, or build in GitHub Actions →
  push to ECR → App Runner (image-based) if the managed source build is too
  constrained.
- **Cost (rough):** 1 vCPU / 2 GB always-on ≈ **$10–50/month** depending on
  traffic.
