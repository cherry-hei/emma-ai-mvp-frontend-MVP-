# Deploy Emma AI to AWS App Runner (auto-deploy from GitHub)

This is the AWS equivalent of "Azure App Service connected to GitHub": push to
your branch → App Runner rebuilds the container → the new version goes live at a
public HTTPS URL. No servers to manage.

**What gets deployed:** the Reflex manager dashboard (frontend + Python backend),
packaged by the repo-root [`Dockerfile`](Dockerfile).
**What does NOT get deployed here:** the database. The app talks to **Supabase
Cloud** (see [emma-ai-app/CLOUD_SETUP.md](emma-ai-app/CLOUD_SETUP.md)). A live app
cannot use your local `supabase start` database.

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

> Region tip: use **Singapore `ap-southeast-1`** for both Supabase and App Runner
> (closest to Hong Kong; Supabase has no HK region).

---

## Step 1 — (recommended) Test the image locally first

Catch build problems on your machine before wiring AWS. With Docker Desktop
running, from the repo root:

```bash
docker build -t emma-ai .
```

```bash
docker run --rm -p 8080:8080 -e API_URL=http://localhost:8080 -e APP_ENV=test -e SUPABASE_URL=... -e SUPABASE_ANON_KEY=... -e SUPABASE_SERVICE_ROLE_KEY=... -e DATABASE_URL=... emma-ai
```

Then open http://localhost:8080. If that works, App Runner will too.

---

## Step 2 — Create the App Runner service

AWS Console → **App Runner** → **Create service**.

1. **Source**
   - Repository type: **Source code repository**.
   - Click **Add new** to create a **GitHub connection** (this is the GitHub
     OAuth authorization — you must do this; it can't be automated). Pick the
     repo `cherry-hei/emma-ai-mvp-frontend-MVP-` and the **branch** you want to
     deploy (e.g. `main`).
   - **Deployment trigger: Automatic** ← this is the "auto-build on push" part.

2. **Build settings**
   - Configuration file: **Use a configuration file? → No / Configure here**.
   - Build type: **Dockerfile**.
   - Dockerfile path: `Dockerfile` (repo root). Build context / source
     directory: `/` (root).

3. **Service settings**
   - **Port: `8080`** (must match the Dockerfile / Caddy).
   - CPU / Memory: start with **1 vCPU / 2 GB** (bump to 2 GB+ if the build or
     OR-Tools runs out of memory).
   - **Environment variables** (plain):
     | Key | Value |
     |-----|-------|
     | `APP_ENV` | `test` (or `production`) |
     | `SUPABASE_URL` | your Supabase project URL |
     | `SUPABASE_ANON_KEY` | anon key |
     | `DATABASE_URL` | Supabase connection URI |
     | `API_URL` | *(leave empty for now — set in Step 4)* |
     | `DEPLOY_URL` | *(leave empty for now — set in Step 4)* |
   - **Secret** (do NOT put this in plain env): store
     `SUPABASE_SERVICE_ROLE_KEY` in **AWS Secrets Manager**, then reference it
     here as an environment variable sourced from the secret. (It bypasses RLS —
     treat it like a root password.)

4. **Health check**
   - Protocol: **HTTP**, Path: `/`.
   - Give it room for the slow first start: Interval `20s`, Timeout `10s`,
     Healthy threshold `1`, Unhealthy threshold `5`.

5. **Auto scaling** (important for Reflex)
   - Set **Min = 1, Max = 1** for now. Reflex keeps session state in memory, so
     multiple instances would split sessions. To scale past 1 instance later,
     add Redis (see Notes) and set `REDIS_URL`.

Click **Create & deploy**. First build takes ~10–15 min (installs OR-Tools +
compiles the Reflex frontend).

---

## Step 3 — Grab the public URL

When the service reaches **Running**, App Runner shows a **Default domain** like:

```
https://abc123xyz.ap-southeast-1.awsapprunner.com
```

At this point the site loads, but the UI **can't reach the backend yet** —
because the frontend was built pointing at `localhost`. Fix that in Step 4.

---

## Step 4 — Set `API_URL` / `DEPLOY_URL`, then redeploy

App Runner → your service → **Configuration → Edit** → Environment variables:

| Key | Value |
|-----|-------|
| `API_URL` | `https://abc123xyz.ap-southeast-1.awsapprunner.com` |
| `DEPLOY_URL` | `https://abc123xyz.ap-southeast-1.awsapprunner.com` |

Save. App Runner redeploys; the container entrypoint re-bakes the frontend so
the websocket/API calls target the public URL. After it's Running again, the
dashboard is fully live. ✅

*(This two-step exists only because the URL isn't known until the service is
created. It's a one-time thing — you never repeat it on future pushes.)*

---

## Ongoing — auto-deploy

From now on, every push to the deploy branch triggers a fresh build + release:

```bash
git push origin main
```

Watch progress in App Runner → your service → **Activity / Logs**.

---

## Notes & troubleshooting

- **Schema/seed on the cloud DB:** the app expects the tables to exist. Push
  migrations to the Supabase project once (`supabase db push`) and, for a test
  environment, seed it (`APP_ENV=test python scripts/seed.py`). Full steps in
  [CLOUD_SETUP.md](emma-ai-app/CLOUD_SETUP.md).
- **`test` vs `production`:** `APP_ENV=test` keeps dev conveniences and works
  with seeded demo logins; `production` disables dev mode (`State.is_dev`).
  Start with `test`.
- **Scaling beyond 1 instance:** provision Redis (AWS ElastiCache or Upstash),
  set `REDIS_URL` env var, and raise Max instances. Without it, keep Max = 1.
- **Build OOM / timeout:** increase instance memory, or switch to the
  build-in-GitHub-Actions → push-to-ECR → App Runner (image-based) flow if the
  managed source build is too constrained. Ask and I'll generate that workflow.
- **Cost (rough):** 1 vCPU / 2 GB always-on ≈ **$10–50/month** depending on
  traffic (App Runner bills active compute higher than idle "provisioned").
- **The REST API (FastAPI):** not deployed here. If you want it public too, it
  can be a second App Runner service or proxied under `/api/*` — say the word.
