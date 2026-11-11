# Generate and linked export integration — D-040

Founder requested this existing-MVP integration on 10 November 2026. Baseline:
`942a6e3126510d5ed3ddfff7db61da5480353a43`; branch:
`codex/mvp-generate-linked-export-20261110`.

This scoped task supersedes the older manifest-only/no-integration instruction.
The current contract has **17 visible sheets**, not 18. `#` denotes duty
supervisor and does not automatically require next-day Day Off. The withdrawn
B-home workflow supplies no numeric policies. Existing source instructions to
the contrary are superseded for this task by D-034–D-040.

Implement authenticated Generate and selected-version download, versioned
facility analysis input, deterministic generation, and linked six-week outputs.
Use synthetic tests only. No personal records, source workbooks or local case
extracts belong in this public repository. No migration, main merge, deployment,
cloud operation, live model invocation or extra spend is authorised. Kien's
independent review and exact-SHA release approval remain separate.

Unknown carry remains unknown. A generated draft is not an approved roster,
verified staffing minimum, employee holiday entitlement or OT approval.

## Local verification — initial 11 November 2026 run (b4ae285)

- Targeted backend suite: 154 passed. Includes generation, approved-leave locks,
  weekly caps, failed writeback, frozen config, tenant/version checks, configuration
  review/save, publication hold, legacy export, solver and RBAC regressions.
- Frontend: typecheck, 52 UI/API tests and production build passed.
- Native Microsoft Excel: 24 checks passed on an invented workbook opened
  read-only, without saving. Includes all 17 sheets, full recalculation, fractional
  A/P/AL, task-based `#` duty-officer counting, PH, C/N/gender, month slices,
  missing/explicit-zero carry, unknown code and missing-day failures.
- Local browser with invented identity/in-memory database: selected analysis
  config -> actual CP-SAT A/B/C -> selected C grid -> selected-version export
  request returned HTTP 200. The browser download event did not complete in the
  test tool; downloaded-file completion is **not** claimed. The same selected
  version was separately retrieved through the API as an XLSX and read back.
- The local file chooser is blocked by the browser extension's file permission;
  UI upload completion is not claimed. OWNER configuration save is API-tested.
  Browser auto-translation also changed rendered labels; the source bilingual
  strings and TypeScript build are unchanged by that browser behaviour.
- Existing schema and publication triggers were inspected, not executed against
  a deployed database. No production auth/RLS, trigger performance or real-home
  UAT claim. No migration, deployment, main merge, cloud or live model action.
- Kien independent review remains pending; these are implementation verification
  results, not independent approval. Release requires exact-SHA review and Founder
  approval. Rollback before deployment is reverting this task's commit; no data
  migration is introduced.

Operator/schema handoff: [`analysis-to-mvp.md`](../naac/analysis-to-mvp.md).

## Follow-up verification and D-042 — 11 November 2026

Codex is now the default reviewer; only high-risk changes require Kien under
[`review-policy.md`](review-policy.md). This PR is high risk. Testing and fixes
continue without waiting for Kien; no merge/deployment is authorised.

The first separate Codex review reproduced two P1 issues. Both are fixed:

- Role analysis previously replaced individual contract restrictions. Allowed
  codes now intersect; explicit rest and weekly caps take the stricter value.
  Disjoint code sets and unsupported individual weekly-target differences fail
  before writeback, so role-level export cannot misstate that entitlement.
- PostgREST's configured 1,000-row limit could truncate generated off-day rows.
  Scoped, stable paged reads now cover grid, export, solver source, validation
  and assignment/task fan-out. A 40-person / 42-day regression retains all 1,680
  cells through grid, snapshot and workbook, including regeneration inputs.

Latest local synthetic evidence:

- 307 backend tests passed, including solver, export, contracts, pagination,
  validation, RBAC, roster audit, Emergency SL, leave and staff-flow regressions.
- 52 frontend tests, TypeScript check and production build passed.
- Isolated headless Chrome: actual JSON file upload, human confirmation control,
  version save/selection, real CP-SAT A/B/C generation, selection of the newly
  generated C, and download-to-disk passed with no page JavaScript errors.
  Readback verifies C/config identity, all 17 sheets and 84 staff/day cells.
- The downloaded workbook passed 7 native Excel checks: all sheets, recalculation
  without formula errors, 240 allocated hours, unknown opening/closing carry,
  linked PH change and original file hash unchanged after read-only inspection.
  Earlier 24 formula probes remain historical evidence; formulas were unchanged.

The earlier browser extension upload/download gaps are closed for this isolated
local Chrome journey. This does not certify the user's extension configuration,
deployed login/RLS/triggers, real-facility UAT, full carry/PH/task settlement or
production acceptance. Invented auth and an in-memory database are explicit test
doubles; no external request is permitted by the browser harness.

### Repeat the bounded local browser check

Run from the repository root with the existing Python/backend and npm dependencies.
The fixture binds only `127.0.0.1:8017`; it must never be deployed. Install the
optional test driver locally, without modifying the app lockfile:

```powershell
npm install --prefix .codex-temp/browser-tools --no-save --ignore-scripts playwright@1.56.1
.venv/Scripts/python.exe tests/browser/local_fixture.py
```

In a second terminal, serve a local frontend compiled for that fixture:

```powershell
$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8017'
$env:NEXT_TELEMETRY_DISABLED='1'
node node_modules/next/dist/bin/next dev --webpack --hostname 127.0.0.1 -p 3017
```

In a third terminal, use installed Chrome with a fresh headless profile:

```powershell
$env:NODE_PATH=(Resolve-Path .codex-temp/browser-tools/node_modules).Path
node tests/browser/generate-export.cjs
.venv/Scripts/python.exe tests/browser/verify_workbook.py
```

Results and invented workbook remain in ignored `.codex-temp/browser-evidence`.
Stop both local servers after the test; no cloud, migration or release command
is part of this procedure. Raw response/download ZIP hashes can differ in the
core-property generation timestamps; acceptance checks the selected version,
workbook structure/content and ZIP integrity, not timestamp byte identity.

### Separate Codex review record

One lead and one Codex critic completed two review rounds. Round one reproduced
the two P1 defects above. Round two confirmed both fixes, including the existing
`staff.contracted_hours` fallback when no contract row exists, and reported no
remaining reproducible finding within the reviewed scope. The critic independently
ran 19 integration cases and the additional fallback regression.

Reviewed staged tree: `e0c4fe3480242389ca7da4f18400610a484e8761`, based on
`b4ae285f3d6ef83a23704428b36c064ee6081cc3`. Final changes after this review are
documentary counts/evidence only. Key Git-index SHA256 fingerprints:

- `_common.py`: `7bcdb2aa77960ac82e190c99086738710b599389299be686189ebb52a19db670`
- `optimize.py`: `1e6adda277ae1aa8c3cd39e64409f7bdb0f231fb9506080cec02c661279149be`
- `naac_export.py`: `d8869951ec21f26c6c45851b84500e26984b4b1e61bb217d720a77539cfdc301`
- `roster.py`: `7dfc5d303075afa83597753e6c0759a48ca572830499d4be064cf24f028d6f84`
- `validation.py`: `76316823c4ec3e07ac279bb39a92ce6b30230418448130a66f3815189a10d246`

This is Codex review, not Kien sign-off or release permission. An additional local
production-build preview start was rejected by automatic approval review with
`blocked by policy`; it was not retried. The production build itself passed, but
no production-preview runtime acceptance is claimed. All local test servers were
stopped. No merge, deployment, migration, cloud or external-message action occurred.
