# Emma AI

Intelligent nurse / care-worker **rostering** for HK residential care homes. This
repository is a monorepo containing two apps that run together:

| App | Path | Stack | Local URL |
|---|---|---|---|
| **Frontend** | repo root (`src/`) | Next.js 16 (Turbopack) · React 19 · Tailwind v4 · shadcn/radix | http://localhost:3001 |
| **Backend** | [`emma-ai-app/`](emma-ai-app) | FastAPI · Supabase (Postgres + GoTrue + RLS) · OR-Tools CP-SAT solver | http://localhost:8000 (docs at `/docs`) |

The frontend consumes the backend's REST API and codegens its typed client from
`http://localhost:8000/openapi.json`. See [`emma-ai-app/README.md`](emma-ai-app/README.md)
and [`emma-ai-app/RUNBOOK.md`](emma-ai-app/RUNBOOK.md) for backend details.

## Status — what's real vs. in progress

**Phases 1 and 2 are fully wired to the backend** — real data, RLS-scoped to the
signed-in facility, no mock:

| Screen | Phase | Backing endpoints |
|---|---|---|
| **Login / account switch** | 1 | `/auth/login` · `/auth/refresh` · `/auth/me` |
| **Roster** — grid, manual edit, publish | 1 | `/rosters`, `/shifts`, `/roster-versions` |
| **Roster → AI Suggest** — A/B/C solver | 2 | `/optimize-roster`, `/optimization-jobs`, `/validate-roster` |
| **Compliance** — ratio, residents, certs | 1 | `/compliance/ratio`, `/resident-counts`, `/units`, `/staff` |
| **Staff Portfolio** — directory + profile | 1 | `/staff`, `/staff/{id}` |

**Phase 3 / 4 screens still render the prototype UI on mock data** (no backend yet —
to be built next): **Dashboard** stats, **Approval**, **Alert**, **ROI**, **Reports**,
**staff-app**, and the Staff profile's **AI Analysis** tab.

## Getting started

### One command (Windows) — runs both apps

```bash
dev.cmd
```

`dev.cmd` installs frontend deps on first run, then launches the FastAPI backend
(`uvicorn`) and the Next.js dev server in separate terminals.

### Manual

Frontend (repo root):

```bash
npm install
npm run dev
```

Backend — see [`emma-ai-app/RUNBOOK.md`](emma-ai-app/RUNBOOK.md) for the full setup:

```bash
cd emma-ai-app
pip install -r requirements.txt
uvicorn api.main:app --reload
```

## Authentication

The app has a real **login screen** at `/login`. Any unauthenticated route redirects
there; the top-right account menu has **Switch account / Sign out**. Sign-in is
per-account and each account is bound to one facility (RLS), so switching Home A ↔ B
means signing out and back in as that home's user.

- **Session:** `login()` stores a short-lived access token + a refresh token
  (`localStorage`). `apiFetch` transparently calls `POST /auth/refresh` on a 401 and
  replays the request; if the refresh token is also dead it clears state and routes
  to `/login`. See [`src/lib/api.ts`](src/lib/api.ts) and
  [`src/components/layout/AuthContext.tsx`](src/components/layout/AuthContext.tsx).
- **Dev convenience:** in local `next dev`, the login form is prefilled and shows
  one-click **demo accounts** (Home A super/admin, Home B super). These are compiled
  **out of production builds** — see the dev-login gate below.

## Configuration

Frontend env lives in `.env.local` (gitignored):

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL of the backend API (default `http://localhost:8000`) |
| `NEXT_PUBLIC_DEV_EMAIL` / `NEXT_PUBLIC_DEV_PASSWORD` | **Dev only.** Seeded creds used to prefill the login form and power the demo-account buttons. Never real credentials. |
| `NEXT_PUBLIC_ENABLE_DEV_LOGIN` | Optional. Set `true` to keep the dev prefill + demo buttons on a **non-prod deployed demo**. Off by default; the dev UI is auto-enabled under `next dev` and auto-stripped from production builds regardless of this flag being unset. |

> **Production:** run a real `next build` (`NODE_ENV=production`) and leave
> `NEXT_PUBLIC_ENABLE_DEV_LOGIN` unset — the form ships bare, with no seed
> credentials in the bundle. For a stricter posture, move auth to a server-side BFF
> with httpOnly cookies (the token currently lives in `localStorage`).

Backend env lives in `emma-ai-app/.env` (see `emma-ai-app/.env.example`).

## Roster & AI solver (Phase 2)

The **Roster** page ([`src/components/roster/RealRosterBoard.tsx`](src/components/roster/RealRosterBoard.tsx))
is fully backend-driven and RLS-scoped to the signed-in facility:

- **Period + version** selectors (create a period, switch between the manual draft
  and solver-generated A/B/C options; option tabs show their constraint score).
- **Live grid** — real staff × day cells from `/rosters/{period}`; click a cell on
  the manual draft to assign/edit/clear a shift (`POST`/`PATCH`/`DELETE /shifts`).
- **AI Roster Suggest** runs the OR-Tools CP-SAT solver (`/optimize-roster`, polled
  via `/optimization-jobs/{id}`) and shows three scored options with KPIs and
  infeasibility reasons.
- **Validate** (`/validate-roster`) and **Publish** (`/rosters/{id}/publish`, guarded
  by the score/violation threshold) close the loop.

## Compliance (Phase 1)

The **Compliance** page ([`src/app/compliance/page.tsx`](src/app/compliance/page.tsx))
is backend-driven, with a period + date selector and three tabs:

- **Staffing Ratio** — per-window SWD checks from `/compliance/ratio` (residents,
  required vs. actual, pass/fail), scoped to the manual roster version.
- **Residents** — daily per-unit counts from `/resident-counts`, editable
  (`POST /resident-counts`); they are the denominator for the ratio checks.
- **Certifications** — real `staff_certificates` with expiry, sorted by urgency
  (days-left → expired / expiring / valid).

## Frontend layout

```
src/app/        routes: login, dashboard, roster, staff, staff-app, compliance,
                approval, alert, personnel, reports, roi, + /api route handlers
src/components/  ui/ (shadcn), layout/ (AuthContext, AppShell, Sidebar, TopNav), roster/
src/lib/         api.ts (typed client), apiTypes.ts, data.ts, types.ts, utils.ts
```

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Next.js dev server on port 3001 (Turbopack) |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run lint` | ESLint |

## Deployment

Three pieces, deployed in this order:

1. **Database** — Supabase Cloud → [`SETUP_SUPABASE_DB.md`](SETUP_SUPABASE_DB.md)
2. **API** — AWS ECS Express Mode, containerized via [`Dockerfile`](Dockerfile),
   auto-deployed by [`.github/workflows/deploy-api.yml`](.github/workflows/deploy-api.yml)
   → [`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md)
3. **UI** — AWS Amplify Hosting → [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md)

Push to `develop` redeploys the API; push to the Amplify-connected branch
redeploys the UI.
