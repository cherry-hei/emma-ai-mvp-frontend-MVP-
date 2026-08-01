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

## Status - what's real

**The MVP scope is complete** - Phase 0-4 plus Phase 7 reporting (data only) and
the Staff App backend. See [`MVP_SCOPE.md`](MVP_SCOPE.md) for the item-by-item
lock and [`ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md) for ADR-0001.
Phase 5 compliance landed ahead of that scope and is in use.

**The database holds the homes' own rosters, not generated demo data.** Home A's
March 2026 cycle (48 staff, before *and* after) and Home B's June and July 2026
sheets were imported from the workbooks the homes actually plan on - see
[Real data](#real-data-import).

Everything is RLS-scoped to the signed-in facility. There is no mock data left in
the app; `src/lib/data.ts` and the fixture-backed `/api/*` route handlers were
deleted.

| Screen | Phase | Backing endpoints |
|---|---|---|
| **Login / account switch** | 1 | `/auth/login` · `/auth/refresh` · `/auth/me` |
| **Roster** - grid, manual edit, publish | 1 | `/rosters`, `/shifts`, `/roster-versions` |
| **Roster → AI Suggest** - A/B/C solver | 2 + 5 | `/optimize-roster`, `/optimization-jobs`, `/validate-roster` |
| **Task scheduling** - events, qualifications, floor rules | 4 | `/facility-events`, `/staff-qualifications`, `/floor-rules` |
| **Roster → task eligibility** | 4 | `/task-assignments`, `/validate-roster` |
| **Medical escort** - destinations per assignment | 4 | `/escort-locations`, `/escorts`, `/task-assignments/{id}/escort-location` |
| **Compliance** - ratio, residents, certs | 1 + 5 | `/compliance/ratio`, `/compliance/minute-ratio`, `/compliance/rule-definitions`, `/resident-counts`, `/units`, `/staff` |
| **Staff Portfolio** - directory + profile | 1 | `/staff`, `/staff/{id}` |
| **Certificate vault** - store + expiry warnings | SA.7 | `/staff/{id}/certificates`, `/certificates/expiring`, `/certificates/notify-expiring` |
| **Dashboard** - KPIs, incident mix, shift mix, alerts | 3 | `/dashboard/summary` |
| **Approval Centre** - AL / duty / sick queues, recommend & decide | 3 + 5 | `/leave-requests`, `/leave-requests/stats`, `/leave-requests/{id}/recommendation` |
| **Alert Centre** - live alerts, cover flow, resolution | 3 | `/alerts`, `/sl-incidents`, `/replacement-candidates`, `/sl-incidents/{id}/resolve` |
| **ROI** - A1 / A2 / agency, editable baseline | 3 | `/roi/summary`, `/roi/settings` |
| **Reports** - generation, schedules, thresholds, regulatory sync | 3 | `/reports/*`, `/reports/download/{type}.{csv\|xlsx\|pdf}`, `/compliance/thresholds` |
| **Staff App** - roster, tasks, requests, swaps, profile | 3 + SA | `/me/*`, `/swaps`, `/notifications` |
| **Staff profile → AI Analysis** | 3 | `/staff/{id}/ai-analysis` |

Phase 5 makes deterministic compliance the source of truth for validation and
publishing. Natural-language explanations remain a later phase.

Endpoints added for the MVP foundation, with no UI yet:

| Endpoint | Spec | What it does |
|---|---|---|
| `POST /imports/roster-excel` | 1.4 | Upload a roster workbook; validate or commit |
| `GET /imports`, `/imports/{id}` | 1.4 | Import history with per-cell findings |
| `GET/POST /calendar-days` | 1.5 | Public / statutory / special-pay day flags |
| `GET/POST /facility-configs` | 2.2 | Versioned facility configuration |
| `POST /shift-definitions` | 2.3 | Duty dictionary writes, split shifts included |
| `GET /audit-logs` | 1.3 | Append-only before/after history |
| `GET /architecture-decisions`, `/project-scope` | 0.1 / 0.2 | The Phase 0 records |
| `GET /evidence-items`, `PATCH /evidence-items/{code}` | 1.6 | Submission checklist |
| `POST /reports/compliance` · `/roster` · `/staffing-ratio` · `/evidence` | 7.1 / 7.2 | The named exports |

## Real data import

`emma_core/importers` reads the homes' own spreadsheets. Two dialects, because the
two homes plan differently:

| Home | Layout | Cycle | What the sheet carries |
|---|---|---|---|
| **A** | `員工工作時間表`, two rank sheets, `Before`/`after` pair | 28 days | Task codes written into the duty (`A2N` = A/N split whose morning half is task A2), staff-request markers, OT/CL adjustments, an events row |
| **B** | `更期表`, one sheet, three floors | natural month | 12-hour `7A`/`7P` duties, a floor/standing-duty row under each staff member, a daily request quota, relief and outsourced pools |

A cell is not a single code. `▲SR A5 + OT x 3 hrs` says five things at once, and
`cells.py` documents the grammar that takes it apart. Anything it cannot resolve
becomes an `import_issues` row naming the exact source cell - the validation
summary spec 1.4 asks for - rather than being silently dropped.

```bash
python scripts/import_real_rosters.py --validate      # parse and report only
```

Home A's before/after pair maps onto roster versions: the plan is a draft, the
as-worked sheet is the record for the period.

### What the real data shows

Importing the real rosters and validating them against the seeded rule profiles
produces findings worth reading before the pilot. Neither as-worked roster passes,
so both stayed drafts - the publish gate is not negotiable for historical data.

| Rule | Home A | Home B | Reading |
|---|---|---|---|
| `min_rest` | 113 | 84 | **Genuine.** A P shift (ends 21:30) followed by an A shift (starts 07:00) is a 9.5-hour turnaround against an 11-hour contract minimum |
| `night_chain` | 63 | 109 | **Calibration.** After A/N the homes give a sleeping day then `補休`/`法` (CL / statutory holiday); the seeded rule expects `DO`/`OFF` |
| `part_time_restriction` | 181 | 16 | **Calibration.** The seeded fixed-PT pattern expects 5-6 work days a week; the real part-timers work 2-4 and are effectively relief staff |
| `night_monthly_limit` | 22 | — | **Genuine.** Staff exceed 2 A/N per month |
| `floor_coverage` | — | 42 | **Genuine.** Home B floor minimums |
| `max_hours` | — | 15 | **Genuine.** Over contracted maximum |

Two importer defects the real data caught and that are now fixed: task
assignments were linking to *inactive* task definitions (reported as "Unknown
task 'A7'" for a code the home writes daily), and `長A7` parsed as a plain `A`
shift. A third finding is scoping rather than a defect - a roster records the
leave that was taken but never the day it was requested, so imported leave is
flagged `submitted_on_unknown` and the request-cutoff rule skips it instead of
failing every historical row against a deadline that had already passed.

**Not in a roster spreadsheet, and therefore absent for an imported facility:**
resident counts (the denominator of every statutory ratio - the import reports how
many days lack one instead of inventing it), certificates, SL incidents, agency
invoices and clock-ins. The screens that read them are empty until the data is
entered.

## Phase 5 - deterministic compliance

- **SWD ratios (5.1):** effective-dated, facility-over-global rules support
  unit denominators, combined ranks, equivalent-head weights, duplicate-person
  protection, and audit-grade minute coverage.
- **Hard constraints (5.2):** one validation engine checks coverage, overlap,
  rest, hours, eligibility, approved leave, Phase 4 tasks/events/floors, and
  persists a digest of every consumed input plus structured evidence for every
  run. Read-only validation does not mutate roster tasks. Publish always performs
  a fresh run and atomically replaces the period's previous operative version.
- **Night chain (5.3):** monthly night limits, `N/AN → SLEEP/SD → DO`, standalone
  N overtime, and next-period nurse cooldown are enforced and recorded.
- **External workforce (5.4):** employment-type-aware bans, calendar/peak-day
  restrictions, rank/day caps, the 50% capacity cap, and Home B's vacancy
  formula are validated. Imported-labour rest/weighting and Home A/B fixed PT
  work patterns are enforced by both the validator and solver. Solver agency
  fills are ledgered without double-counting KPI or ROI spend.
- **Leave rules (5.5):** cutoffs, Home A/B request quotas, priority, locked-night
  exclusions, high-demand same-rank conflicts, and period-scoped balances are
  rechecked at approval time. Duty requests remain positive work preferences;
  pending requests cannot make an unchanged roster unpublishable.

## Phase 4 - task-based scheduling

- **Task codes and eligibility (4.1):** rank/shift/unit rules, qualifications,
  medication-audit restrictions, mentor/new-staff controls, and the A3/P3-only
  rule for unaudited agency staff are enforced before an edit is saved.
  Rejected attempts are recorded in `violation_log`, and the API returns the
  reasons as a list (`detail.issues`) so the roster editor can show *wrong rank*
  and *not medication-audited* as two separate, fixable things.
- **Event overlays (4.2):** events carry normalized staffing requirements. Hair
  cutting, CGAT, medication checks, podiatry and monthly weighing use reusable
  defaults; visiting, PGT and training accept manager-entered requirements.
  Event markers are included in roster date headers.
- **Floor coverage (4.3):** data-driven, minute-level rules support Home B's
  1/F, 2/F and 6/F HCA minimums, 6/F weekend relaxation, and the 2/F
  16:00–21:30 local-P-shift composition rule.
- `/validate-roster` runs the same operational checks for manual and solver
  versions, and those checks also guard publishing.

All three data sets are managed from **Task Scheduling** (`/scheduling`) —
events with their staffing requirements, staff qualifications, and floor
minimums. Before that screen existed the rules were real but unreachable: the
tables were seed-only, so a manager could not record that someone is
medication-audited, book an event with its extra cover, or state a floor
minimum at all.

**A task code follows the duty, not the shift label.** A/N is two duty windows,
so a morning code belongs on an A/N cell even though the codes differ. The
check (`shift_type_matches`) matches on the code when the codes are equal, and
otherwise only for a split shift whose segment starts inside the required
code's own window — so an A code is still refused on a B or E shift.

### Built on the backend, no UI yet

- **Pareto roster options** (spec 9.1) - `POST /optimize-pareto` works and is
  tested, but the Roster page's *AI Roster Suggest* button still calls
  `/optimize-roster` (the fixed A/B/C presets). Pointing it at the Pareto
  endpoint is a one-line change; the response contract is identical.

### Registries, not yet automation

These tables and screens are real and read live, but nothing executes them on a
schedule - they are the data model and the manual trigger, not the daemon:

- `report_schedules` carries `next_run_at`, but no cron fires it. **Generate Now**
  works today.
- `event_trigger_rules` + `facility_events` produce genuine month-to-date counts;
  nothing auto-creates an event or performs the described action (pre-filling an
  Annex 8.3 draft, etc.).
- `regulatory_documents` is a version register. Emma does not yet fetch upstream
  documents to detect a change.
- Notifications deliver **in-app only**. Email and WhatsApp rows are persisted
  with status `queued` for a delivery worker that does not exist yet.
- Reports render as JSON and CSV - **"data only"**, which is the MVP scope for
  Phase 7. PDF/Excel rendering and `file_url` object storage are deferred.

## Phase 3 - operations layer

Phase 3 turns the console from a planning tool into an operational one. The
additions worth knowing about:

- **Emergency cover is compliance-checked before it is suggested** (spec 3.8).
  `/replacement-candidates` ranks every other active staff member and returns each
  one either clean or with the explicit reasons it is blocked - rest gap, max
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
  cost extreme, the staff-satisfaction extreme and the knee - with the frontier in
  `result_json.pareto`.
- **The staff app is self-scoped.** Every `/me/*` route resolves the staff record
  from the caller's own profile, and RLS additionally restricts a `staff` login to
  its own rows, so a staff token cannot read a colleague's roster, leave or
  attendance.

## Split shifts (A/N)

The Code of Practice A/N shift is **two disjoint duty windows**, not one long one -
per the scheduling spec, Home A works 07:00–13:30 *and* 21:30–07:00 the next day
(6.5h + 9.5h = **16h paid**); Home B works 07:00–14:30 *and* 21:15–07:15
(**17.5h**). The unpaid rest gap between them is real.

Three consumers need three different answers, so all shift-time maths lives in one
place - [`emma_core/shifttime.py`](emma-ai-app/emma_core/shifttime.py):

| Question | Function | A/N answer |
|---|---|---|
| How many hours is this worth? | `paid_minutes()` | 16h - the sum of the segments |
| When is this person unavailable? | `envelope()` | 07:00 → 07:00 next day (24h), for rest + overlap checks |
| When are they on the floor? | `duty_spans()` | the two windows separately, so they are *not* counted present during the afternoon gap |

`shift_definitions.segments` / `shifts.segments` (jsonb) hold the duty windows;
a row without them is an ordinary contiguous shift and behaves exactly as before.
`paid_minutes` can override the clock where a facility pays a handover or sleep-in
differently. Segments survive manual cell edits and solver writeback, so an A/N
shift cannot silently revert to its elapsed span.

## Getting started

### One command (Windows) - runs both apps

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

Backend - see [`emma-ai-app/RUNBOOK.md`](emma-ai-app/RUNBOOK.md) for the full setup:

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
  **out of production builds** - see the dev-login gate below.

## Configuration

Frontend env lives in `.env.local` (gitignored):

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL of the backend API (default `http://localhost:8000`) |
| `NEXT_PUBLIC_DEV_EMAIL` / `NEXT_PUBLIC_DEV_PASSWORD` | **Dev only.** Seeded creds used to prefill the login form and power the demo-account buttons. Never real credentials. |
| `NEXT_PUBLIC_ENABLE_DEV_LOGIN` | Optional. Set `true` to keep the dev prefill + demo buttons on a **non-prod deployed demo**. Off by default; the dev UI is auto-enabled under `next dev` and auto-stripped from production builds regardless of this flag being unset. |

> **Production:** run a real `next build` (`NODE_ENV=production`) and leave
> `NEXT_PUBLIC_ENABLE_DEV_LOGIN` unset - the form ships bare, with no seed
> credentials in the bundle. For a stricter posture, move auth to a server-side BFF
> with httpOnly cookies (the token currently lives in `localStorage`).

Backend env lives in `emma-ai-app/.env` (see `emma-ai-app/.env.example`).

## Roster & AI solver (Phase 2)

The **Roster** page ([`src/components/roster/RealRosterBoard.tsx`](src/components/roster/RealRosterBoard.tsx))
is fully backend-driven and RLS-scoped to the signed-in facility:

- **Period + version** selectors (create a period, switch between the manual draft
  and solver-generated A/B/C options; option tabs show their constraint score).
- **Live grid** - real staff × day cells from `/rosters/{period}`; click a cell on
  the manual draft to assign/edit/clear a shift (`POST`/`PATCH`/`DELETE /shifts`).
- **AI Roster Suggest** runs the OR-Tools CP-SAT solver (`/optimize-roster`, polled
  via `/optimization-jobs/{id}`) and shows three scored options with KPIs and
  infeasibility reasons.
- **Validate** (`/validate-roster`) and **Publish** (`/rosters/{id}/publish`, guarded
  by the score/violation threshold) close the loop.

## Compliance (Phase 1)

The **Compliance** page ([`src/app/compliance/page.tsx`](src/app/compliance/page.tsx))
is backend-driven, with a period + date selector and three tabs:

- **Staffing Ratio** - per-window SWD checks from `/compliance/ratio` (residents,
  required vs. actual, pass/fail), scoped to the manual roster version.
- **Residents** - daily per-unit counts from `/resident-counts`, editable
  (`POST /resident-counts`); they are the denominator for the ratio checks.
- **Certifications** - real `staff_certificates` with expiry, sorted by urgency
  (days-left → expired / expiring / valid).

## Frontend layout

```
src/app/        routes: login, dashboard, roster, scheduling, staff, staff-app,
                compliance, approval, alert, personnel, reports, roi
src/components/  ui/ (shadcn), layout/ (AuthContext, AppShell, Sidebar, TopNav), roster/
src/lib/         api.ts (typed client), apiTypes.ts, types.ts, utils.ts
```

Every page reads through `src/lib/api.ts`; there are no Next.js route handlers and
no local fixtures. The staff app at `/staff-app` needs an account whose
`users_profile.staff_id` is set - `staff_a@emma.local` in the seed.

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Next.js dev server on port 3001 (Turbopack) |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run lint` | ESLint |

## Deployment

Three pieces, deployed in this order:

1. **Database** - Supabase Cloud → [`SETUP_SUPABASE_DB.md`](SETUP_SUPABASE_DB.md)
2. **API** - AWS ECS Express Mode, containerized via [`Dockerfile`](Dockerfile),
   auto-deployed by [`.github/workflows/deploy-api.yml`](.github/workflows/deploy-api.yml)
   → [`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md)
3. **UI** - AWS Amplify Hosting → [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md)

Push to `develop` redeploys the API; push to the Amplify-connected branch
redeploys the UI.
