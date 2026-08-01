# MVP scope lock

**MVP = Phase 0-4 + Phase 7 reporting (data only) + the Staff App PWA backend.
Seven weeks.**

The register lives in `project_scope` (`GET /project-scope`,
`GET /project-scope/summary`) so a scope question is answered from the same
source the roadmap uses. This file is the readable copy. Phase numbering follows
the delivery plan, not the repository's older internal numbering.

## In scope

| # | Phase | Item | Priority |
|---|---|---|---|
| 0.1 | Phase 0 · Decision & MVP Scope Lock | Architecture decision boundary | P0 |
| 0.2 | Phase 0 · Decision & MVP Scope Lock | 7-week MVP scope lock | P0 |
| 1.1 | Phase 1 · Foundation, Security & Data Import | Role-based login and permissions | P0 |
| 1.2 | Phase 1 | Facility-level data isolation | P0 |
| 1.3 | Phase 1 | Append-only audit log | P0 |
| 1.4 | Phase 1 | Import real roster Excel into the database | P0 |
| 1.5 | Phase 1 | Calendar / public holiday & special-pay schema | P0 |
| 1.6 | Phase 1 | Compliance / security evidence checklist | P1 |
| 2.1 | Phase 2 · Core Data Model | Staff profile and contract model | P0 |
| 2.2 | Phase 2 | Facility-specific JSON rule config | P0 |
| 2.3 | Phase 2 | Shift definition dictionary | P0 |
| 3.1 | Phase 3 · Roster Operations | Database-backed roster calendar | P0 |
| 3.2 | Phase 3 | Manual roster edit flow | P0 |
| 3.3 | Phase 3 | Roster save, publish and export | P0 |
| 3.4 | Phase 3 | Limited A/B/C option comparison | P1 |
| 4.1 | Phase 4 · Task-Based Scheduling | Task-code definitions and assignment | P0 |
| 4.2 | Phase 4 | Special event staffing overlays | P0 |
| 4.3 | Phase 4 | Floor / unit operational staffing | P0 |
| 7.1 | Phase 7 · Reporting | Export basic compliance report — **data only** | P0 |
| 7.2 | Phase 7 | Export roster report — **data only** | P1 |
| SA.1 | MVP addendum | Staff App PWA backend (`/me/*`, self-scoped) | P0 |

"Data only" for Phase 7 means JSON and CSV, reproducible from a stored payload.
PDF/Excel rendering and object storage for `file_url` are deferred.

## Deferred

| # | Phase | Item | Note |
|---|---|---|---|
| 5.1-5.5 | Phase 5 · Compliance Engine | SWD ratios, hard constraints, night chain, agency caps, leave rules | Outside the seven weeks; **delivered early** with the compliance-engine work and now in use |
| 6.1 | Phase 6 · AI Suggestion Layer | AI conflict explanation | Deterministic rules stay the source of truth; explanations wait for an approved gateway |
| 6.2 | Phase 6 | AI-assisted replacement candidates | The rule-based candidate ranking exists; the AI explanation layer does not |
| 8.1 | Phase 8 · QA, Evidence & Pilot Readiness | Full QA scope (ZAP, load, backup drill) | Rule fixtures exist; the rest is post-MVP |
| 8.2 | Phase 8 | Client / government evidence pack | The checklist and its export exist; assembling and reviewing the pack is post-MVP |

Also explicitly out: forecasting and the pressure signal (6.x in the older
workbook), ML/XGBoost, full ROI automation, PDF/Excel rendering, notification
delivery (email/WhatsApp), and scheduled report execution — `report_schedules`
carries `next_run_at` but nothing fires it.

## Success criteria

1. A manager signs in and sees their own home's roster, drawn from the database.
2. A real roster spreadsheet imports with a validation summary naming every cell
   the parser could not resolve.
3. Manual edits persist and are audited.
4. Hard compliance violations are listed, and block publication.
5. A compliance report and a roster export can be produced for a date range and
   re-opened later unchanged.
6. A staff member sees only their own roster, tasks and leave.

## Known gaps carried into the pilot

- **Resident counts are not in the source rosters.** They are the denominator of
  every statutory ratio, so an imported period reports how many days lack a count
  rather than inventing one. Enter them via `POST /resident-counts`.
- **Certificates, incidents, agency invoices and clock-ins are not in a roster
  spreadsheet.** The screens that read them are empty for an imported facility
  until the data is entered.
- **Rule calibration.** Validating the homes' real rosters against the seeded
  rule profiles produces violations that are partly real findings and partly
  configuration drift — see the note in [`README.md`](README.md#what-the-real-data-shows).
