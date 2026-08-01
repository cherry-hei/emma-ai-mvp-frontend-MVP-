# Setup 3 - UI on AWS (Amplify Hosting, auto-deploy from GitHub)

Deploy the Emma AI **frontend** (Next.js 16 · React 19 · Tailwind v4 · shadcn) to
**AWS Amplify Hosting**. Amplify is the natural "push-to-deploy" home for Next.js
on AWS: it detects Next.js, runs the managed **SSR** adapter (the app uses server
components and `/api` route handlers, so a plain static export won't work), and
redeploys on every push - the frontend analog of the API's push-to-deploy setup.

Do these first:
1. [`SETUP_SUPABASE_DB.md`](SETUP_SUPABASE_DB.md) - the database.
2. [`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md) - the API. **You need its public
   URL** for `NEXT_PUBLIC_API_URL` below.

> The frontend lives at the **repo root** (`src/`), on the frontend branch (e.g.
> `main`). It calls the backend's REST API and codegens its typed client from the
> API's `/openapi.json`.

---

## Prerequisites

1. Backend API deployed and reachable at an HTTPS URL, e.g.
   `https://emma-ai-api.ecs.ap-southeast-1.on.aws`.
2. This repo on **GitHub**, frontend branch pushed.
3. An **AWS account** with permission to create Amplify apps.

> **Region:** `ap-southeast-1` (Singapore) to match the API and DB.

---

## Step 1 - Create the Amplify app

AWS Console → **AWS Amplify** → **Create new app** → **Deploy with GitHub**.

1. Authorize GitHub (OAuth - interactive, one-time), pick this **repo** and the
   frontend **branch** (e.g. `main`).
2. Amplify auto-detects **Next.js (SSR)**. Accept the detected build settings -
   confirm the app root is the **repo root** (where `package.json` lives), not
   `emma-ai-app/`.
3. Leave the default build image and Node 18+.

If Amplify does not auto-fill the build spec, use this `amplify.yml`:

```yaml
version: 1
frontend:
  phases:
    preBuild:
      commands:
        - npm ci
    build:
      commands:
        - npm run build
  artifacts:
    baseDirectory: .next
    files:
      - '**/*'
  cache:
    paths:
      - node_modules/**/*
      - .next/cache/**/*
```

(Matches `package.json`: `build` = `next build`, `dev` = port 3001 for local only.)

---

## Step 2 - Environment variables

Amplify → your app → **Hosting → Environment variables**. Set:

| Variable | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | your API URL from Setup 2, e.g. `https://emma-ai-api.ecs.ap-southeast-1.on.aws` | Base URL of the backend API. **No trailing slash.** |

**Do NOT set** the local-dev auto-login vars in a hosted environment:

| Variable | Why not |
|---|---|
| `NEXT_PUBLIC_DEV_EMAIL` / `NEXT_PUBLIC_DEV_PASSWORD` | Local-dev auto-login only. In a hosted env, use the real login UI built on `api.login()`. Never ship demo credentials to the browser. |

> `NEXT_PUBLIC_*` values are **inlined into the client bundle at build time** - they
> are public. Never put secrets (service-role key, DB URL) here. Those belong only
> to the backend ([`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md)).

Save, then trigger a build (**Redeploy this version**) so the new env is baked in.

---

## Step 3 - First deploy

Amplify builds and deploys automatically. First build takes a few minutes. When it
finishes you get a default domain:

```
https://main.d1a2b3c4e5.amplifyapp.com
```

Open it and confirm the app loads.

---

## Step 4 - Wire up CORS (the two-way handshake)

The API and UI are on **different origins**, so the browser enforces CORS. Take the
Amplify URL from Step 3 and add it to the backend's `CORS_ORIGINS`:

- Set the `CORS_ORIGINS` **repository variable** (GitHub → Settings → Secrets and
  variables → Actions → Variables) to the Amplify origin, comma-separated if
  several, e.g. `https://main.d1a2b3c4e5.amplifyapp.com`.
- Re-run the *Deploy API to AWS* workflow (Actions → **Run workflow**) so the new
  value reaches the running service.

Then reload the UI. If the browser console shows a **CORS error**, the origin in
`CORS_ORIGINS` doesn't exactly match (scheme + host + no trailing slash).

> **Chicken-and-egg:** you need the UI's origin to set backend CORS, but the UI
> needs the API URL to build. Order that works: deploy API first (Setup 2) → deploy
> UI with `NEXT_PUBLIC_API_URL` (Steps 1–3) → copy the UI origin back into the API's
> `CORS_ORIGINS` (Step 4).

---

## Step 5 - (optional) Custom domain

Amplify → your app → **Hosting → Custom domains** → add e.g. `emma.example.com`.
Amplify manages the certificate and gives you DNS records to add at your registrar.
After it validates:
- Add the custom domain to the backend's `CORS_ORIGINS` too.
- (Optional) Point `NEXT_PUBLIC_API_URL` at a custom API domain if you set one up.

---

## Ongoing - auto-deploy

Every push to the connected branch rebuilds and redeploys:

```bash
git push origin main
```

Watch progress in Amplify → your app → the branch's build log.

---

## Alternative - containerized UI on ECS Express Mode

If you'd rather run the UI the same way as the API (one platform,
container-based), build a Next.js **standalone** image and deploy it as a second
ECS Express Mode service instead of using Amplify:

1. In `next.config.ts`, set `output: 'standalone'`.
2. Add a UI `Dockerfile` (multi-stage: `npm ci` → `npm run build` → run
   `node .next/standalone/server.js`, listen on `8080`, pass
   `NEXT_PUBLIC_API_URL` as a **build arg** since it's inlined at build time).
3. Create a second Express Mode service from that image (same steps as
   [`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md)), then do the CORS handshake in
   Step 4.

Amplify is simpler for Next.js (native SSR support, no Dockerfile) and avoids a
second Application Load Balancer's monthly cost. Go container-based only if you
specifically want one platform for both apps.

> **Not S3 + CloudFront static hosting:** that only serves a static export
> (`next export`). This app relies on SSR / server components / `/api` route
> handlers, so a static-only bucket would break those routes.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| UI loads but every API call fails with **CORS** | Add the exact Amplify origin to the API's `CORS_ORIGINS` (Step 4). Scheme + host must match, no trailing slash. |
| API calls go to `localhost:8000` in production | `NEXT_PUBLIC_API_URL` wasn't set at **build** time. Set it, then **Redeploy** (it's inlined at build, not runtime). |
| Build fails on Amplify | Confirm app root = repo root (not `emma-ai-app/`), Node 18+, and that `npm ci` succeeds against the committed `package-lock.json`. |
| `401` after login redirect loop | Confirm the API is reachable and its `/auth/login` works (test with `curl` per the backend RUNBOOK). |
| Demo login present in prod | Remove `NEXT_PUBLIC_DEV_EMAIL` / `NEXT_PUBLIC_DEV_PASSWORD` from Amplify env and rebuild. |

---

## The full picture

```
Browser ──HTTPS──▶ Amplify (Next.js UI)  ──HTTPS──▶ ECS Express (FastAPI API) ──▶ Supabase Cloud (Postgres + Auth + RLS)
          Setup 3                          Setup 2                                Setup 1
```

- DB: [`SETUP_SUPABASE_DB.md`](SETUP_SUPABASE_DB.md)
- API: [`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md)
- UI: this file
