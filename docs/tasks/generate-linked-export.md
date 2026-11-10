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

## Local verification — 11 November 2026

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
