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

## Status — what's real

**Phases 1, 2 and 3 are fully wired to the backend** — real data, RLS-scoped to the
signed-in facility. There is no mock data left in the app; `src/lib/data.ts` and the
fixture-backed `/api/*` route handlers were deleted.

| Screen | Phase | Backing endpoints |
|---|---|---|
| **Login / account switch** | 1 | `/auth/login` · `/auth/refresh` · `/auth/me` |
| **Roster** — grid, manual edit, publish | 1 | `/rosters`, `/shifts`, `/roster-versions` |
| **Roster → AI Suggest** — A/B/C solver | 2 | `/optimize-roster`, `/optimization-jobs`, `/validate-roster` |
| **Compliance** — ratio, residents, certs | 1 | `/compliance/ratio`, `/resident-counts`, `/units`, `/staff` |
| **Staff Portfolio** — directory + profile | 1 | `/staff`, `/staff/{id}` |
| **Dashboard** — KPIs, incident mix, shift mix, alerts | 3 | `/dashboard/summary` |
| **Approval Centre** — AL / duty / sick queues, approve & reject | 3 | `/leave-requests`, `/leave-requests/stats` |
| **Alert Centre** — live alerts, cover flow, resolution | 3 | `/alerts`, `/sl-incidents`, `/replacement-candidates`, `/sl-incidents/{id}/resolve` |
| **ROI** — A1 / A2 / agency, editable baseline | 3 | `/roi/summary`, `/roi/settings` |
| **Reports** — generation, schedules, thresholds, regulatory sync | 3 | `/reports/*`, `/compliance/thresholds` |
| **Staff App** — roster, tasks, clock in/out, profile | 3 | `/me/*` |
| **Staff profile → AI Analysis** | 3 | `/staff/{id}/ai-analysis` |
| **Roster → Pareto options** (spec 9.1) | 3 | `/optimize-pareto` |

**Phase 4 (NLP feedback analysis) is not started.**

## Phase 3 — operations layer

Phase 3 turns the console from a planning tool into an operational one. The
additions worth knowing about:

- **Emergency cover is compliance-checked before it is suggested** (spec 3.8).
  `/replacement-candidates` ranks every other active staff member and returns each
  one either clean or with the explicit reasons it is blocked — rest gap, max
  hours, approved leave, rank eligibility, medication audit. Resolving an incident
  re-rosters the shift, records the TOIL owed in `future_debt_ledger`, and stamps
  the response time that feeds the A2 ROI figure.
- **Two staffing-ratio methods** (spec 3.6 / 3.7). `/compliance/ratio` is the
  per-shift check; `/compliance/minute-ratio` walks each statutory window segment
  by segment and reports breach *minutes*, so a shift that covers half a window can
  no longer pass the whole window.
- **ROI is measured, not configured.** Headcount comes from `staff`, incidents from
  `sl_incidents`, agency spend from `agency_assignments`. Only the baseline
  assumptions (manager hourly rate, survey hours, agency-reduction %) are editable,
  and they persist per facility in `roi_settings`.
- **Threshold monitors are live.** Certificate expiry, PT cap, AN limit, RN-absent
  shifts, CL accrual and occupancy are computed from the current roster, the
  certificate register and the debt ledger on every page load.
- **Reports are reproducible.** `/reports/generate` stores both the parameters and
  the resulting rows in `reports`, so a report shown to SWD can be re-opened later
  byte-for-byte. Every generator also streams as CSV.
- **Pareto roster options** (spec 9.1). `/optimize-pareto` re-solves the same hard
  model across 15 weight vectors, discards dominated candidates and returns the
  cost extreme, the staff-satisfaction extreme and the knee — with the frontier in
  `result_json.pareto`.
- **The staff app is self-scoped.** Every `/me/*` route resolves the staff record
  from the caller's own profile, and RLS additionally restricts a `staff` login to
  its own rows, so a staff token cannot read a colleague's roster, leave or
  attendance.

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
                approval, alert, personnel, reports, roi
src/components/  ui/ (shadcn), layout/ (AuthContext, AppShell, Sidebar, TopNav), roster/
src/lib/         api.ts (typed client), apiTypes.ts, types.ts, utils.ts
```

Every page reads through `src/lib/api.ts`; there are no Next.js route handlers and
no local fixtures. The staff app at `/staff-app` needs an account whose
`users_profile.staff_id` is set — `staff_a@emma.local` in the seed.

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Next.js dev server on port 3001 (Turbopack) |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run lint` | ESLint |

## Deployment

Containerized via [`Dockerfile`](Dockerfile); see [`AWS_DEPLOY.md`](AWS_DEPLOY.md)
for the AWS deployment guide.
