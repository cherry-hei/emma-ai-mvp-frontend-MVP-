# Emma integration work log — 2026-10-31

## Shared state, not shared chat

Codex and Manus do not automatically share chat memory. Read this branch's AGENTS.md, SHARED_CONTRACT.md, API contract and task acceptance criteria before work. Record exact commit and tests on every handoff. There is no running cross-platform coordinator or independent Codex session in this task.

| Work package | Source / owner | Evidence / next gate |
|---|---|---|
| Manager shell + roster presentation | agent/nov04-manager-698b981 / Manus engineering | White header, latest sidebar caption, account role/facility, 100/125/150/200% reflow, week/month/staff views; actual baseline API. 10 helper tests + local 16-case shell QA before final security recovery patch. Final counts belong to PR evidence. |
| Staff PWA pure source | cherry-hei/emma-ai-staff-pwa / Manus engineering | Source-only export, no old QA/debug/secret history. Live-missing messages/duty-window features fail closed. Optional credential replacement fix under review. |
| NAAC validation/import/auth | agent/nov04-contract-698b981 / engineer + independent review | Hash-next-day-off validation is implemented offline; role guards and paid-minute propagation under review. No migration or API deployment. |
| Landing | cherry-hei/emma-ai-web | Separate static bilingual frontend and Vercel project, no API or client data. |
| Independent review | reports/independent-review.md in task artifacts | Four preview gates, final remediation evidence will supplement this review rather than erase findings. |

## 4 November target and hard dependencies

- 31 Oct: source branches/PRs, preview-only frontends, API/role/paid-minute/task-recovery fixes; no production main merge.
- 1 Nov: Kien reviews the exact backend delta; agree messages and duty-window schema, RLS direct-client policies, solver lock projection and hash-next-day-off generation. Queenie task-role/headcount/shift replies remain pending.
- 2 Nov: approved isolated staging integration: same staff user's request → authorized reviewer/OWNER decision → lock → generation → deterministic validation → publication → staff refresh; two organisations and cross-unit restrictions.
- 3 Nov: NAAC six-week/18-sheet XLSX and print acceptance, multi-user/load measurements, backup/restore and account matrix rehearsals; canonical domain confirmed.
- 4 Nov: readiness/UAT decision against exact tested commit and open defects. It is not automatic production acceptance, account provisioning or approval to move real data outside Hong Kong. Gary's proposed 1 Dec launch and Kien's M2/M3 two-working-week estimate must be reconciled explicitly.

## Phone progress and approvals

GitHub's authenticated Draft PR and Checks pages are the initial phone-visible progress record. Device push notifications depend on the user's GitHub/Manus app settings and are not configured here. No Lark/WhatsApp bot or public approval link is provided.

A review comment is not deployment authorisation. Release request must contain: exact full commit SHA, target project/environment, purpose, migration/data/Auth effects, region, estimated cost, expiry, backup/rollback and the CEO's authenticated explicit response. Any changed SHA invalidates prior release approval. Existing main deploy-api workflow runs migrations: do not merge until its impact is reviewed. PR6 remains Draft and unchanged.

## Production gates still open

No real accounts, SQL execution, production data, DNS, Supabase/Auth replacement, cloud AI provider, paid model or automatic deployment approval is authorised by this document. Backend is currently Singapore per Kien; DB Seoul per his discussion, not independently console-verified. Vercel moves frontends only, not CP-SAT/API/data processing. One approved backend/data project with user-bound permissions remains the integration target, not shared service secrets.

## Current preview-only safety switches

The separate Vercel manager project uses NEXT_PUBLIC_INTEGRATION_PREVIEW=1 in both Preview and Production environments. It prevents API login/refresh/requests in the build, not only button clicks. The Staff PWA Vercel project intentionally has no VITE_API_BASE in either environment until server authorization and RLS staging gates are accepted. These are presentation/source previews, not replacement live client portals.

## Verified source publication — 31 Oct

- Backend Draft PR7: https://github.com/cherry-hei/emma-ai-mvp-frontend-MVP-/pull/7 ; commit `7205a24` includes canonical API guards and authoritative paid-minute import. Latest bounded combined offline suite: 192 passed. RLS direct access and staging gates remain open.
- Staff PWA source: https://github.com/cherry-hei/emma-ai-staff-pwa ; commit `c3f484c` includes optional credential replacement plus disabled unconfigured login. 12 tests, TypeScript and Vite build passed; no live account test.
- Landing source: https://github.com/cherry-hei/emma-ai-web ; public standalone URL https://emma-ai-web.vercel.app . Five static source tests and live Chinese language-toggle check passed. Custom DNS remains untouched.

## Final local acceptance — 31 Oct

- Manager focused UI/API/task tests: 21 passed; TypeScript and strict Next.js build passed.
- Real local browser: 16 shell cases (Chinese/English, desktop/mobile, 100/125/150/200 percent), week/month range and failed cell-save draft retention passed. All API requests intercepted dummy fixtures.
- Timed-task modal fault injection passed: one cell write, task 2 failure retains modal/task 1; retry writes only task 2; reopening and editing task 1 clock persists without rewriting cell.
- Known safety limitation: persisted task identities/removal remain locked in this modal until safe backend deletion/replacement flow is reviewed; task clocks remain editable. Notes have no persistence contract and stay disabled.
- Staff exact-SHA preview READY at https://emma-ai-staff-47uzuw2cc-cherry-heis-projects.vercel.app . Vercel SSO protects preview; app login disabled due to no API configuration. No real account UAT was performed.
- No production merge, migration, provisioning, DNS change, paid-plan change or customer-data import was performed.

## GitHub authorization limit

The configured GitHub App refused a new Actions workflow because it lacks `workflows` permission. The read-only test/build workflow is delivered as `verify-nov04-ui.workflow-example` for an authorised maintainer to install. It is NOT active CI; no workflow permission, branch protection or paid plan was changed. Local 21-test/build/UI evidence above is separate from GitHub check results. The unpublished parent-created integration commit was amended to remove the blocked workflow path; no shared history was rewritten.
