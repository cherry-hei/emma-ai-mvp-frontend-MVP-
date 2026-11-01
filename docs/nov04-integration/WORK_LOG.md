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

## 31 October CEO scope update — supersedes earlier trial residency notes

- Non-HK real-data internal trial is now authorised for 4 November. December is NGO staff rollout. Old HK-only and no-trial-data wording above is historical, not the current acceptance rule.
- Connected Supabase account returns no visible projects; actual Kien project ID/access remains unresolved. Do not create a substitute database.
- New Manager/Staff Vercel origins both fail live public CORS preflight (400). Effective backend CORS configuration, not frontend styling, blocks connection. No hosted login was attempted.
- Existing PR7/PR8 are the successor candidates; PR6 is reference only. A main push still deploys API and runs migrations.
- Manager successor: escort_location contract support, 22 offline UI/API tests, tsc and Next build passed.
- PWA successor: auth/me identity hydration, strict HTTPS API origin, 14 offline tests and type/build passed.
- Solver successor: persistent live pin/forbid locks and literal NAAC # next-calendar-day no-work/DO, 16 solver/service and 149 related offline tests passed; full rule completeness and real month writeback remain unverified.
- Accounts audit: existing provision scripts are not safe real-staff invite workflows; canonical role/RLS mismatch and missing unit/deputy/nurse scopes require implementation and hosted acceptance.
- GitHub event workflow configured enabled/synced for new PR review and verified CEO Emma: commands; first executed event not yet evidenced. No automatic merge/deploy/migration, Lark/WhatsApp bot, paid always-on host or shared-chat service running.

## 1 November — chat/window candidate integration

This section supersedes stale baseline/PR state above. PR8 frontend main is caff1c86c44cf97231e84f24563c1bde6f414a07 and was released without API/DB/DNS actions. PR7 is open/review-ready at 72dcbb8; PR6 remains Draft. The new branch agent/nov04-chat-windows-live is a separate bounded backend candidate; no main write/deployment is authorised here.

Manus chat package b66289342c683952c2c2799aa28109cd932a0917 and window package 1c38f15 were integrated as 1fb6d59 / 5d2228f. Parent registered both routers, added stable retry client_message_id intents to the manager composer, and retained inclusive legacy PWA target_end while canonical API uses target_end_exclusive. Candidate integration initially passed 129 offline backend tests, 50 UI regression tests and strict TypeScript; final rerun/DB review evidence belongs in the PR/handoff after corrections. Initial Next/Turbopack build failed solely on an external node_modules symlink; isolated dependencies and a strict rerun are being used, not ignoring errors or changing app release config.

Invitation-only login lifecycle is still not implemented: existing admin seed/provision code is not invite/expiry/accept/revoke/audit acceptance. Manager profiles lacking staff/unit links and deputy system-role mapping remain explicit runtime/policy blockers. PWA/API activation, full CP-SAT/month/export, live RLS/JWT multi-user UAT and load/backup evidence remain outstanding. This work does not accept Kien's M1/M2 milestones.

Codex CLI 0.166.0 installed via OpenAI's official standalone installer. Device login requested; until login status verifies authentication, all candidate implementation/review is Manus work. Lark read-only connector was created/enabled but real connection failed due to missing app credentials; no engineering conversation read and no external message sent. Persistent Manus profile management is unavailable in this task. Existing bounded GitHub event queue remains ready/synced; no duplicate trigger, paid host, extra credit purchase or constant loop was enabled. CEO numeric extra-spend cap is pending.

### CEO spending update — 1 November 16:05 HKT

Cherry confirmed existing subscriptions/credits only. Ask before any necessary additional spending; no automatic extra-credit purchase, API-key billing fallback, new paid runner/hosting or upgrade. This supersedes the earlier pending-numeric-cap note. Codex remains installed but not authenticated as of the check; the current device code is supplied by the CLI, not found in ChatGPT settings. The user provided the specific Lark workspace messenger URL for connection; unrelated chats and external sends remain out of scope.

### 1 November SQL correction and Codex activation

The independent local PostgreSQL review reproduced 3 high window defects (close/write race, semantic update bypass, unknown-role reads) and 1 reason-idempotency defect. One correction round fixed all four; the reviewer-owned fresh disposable PostgreSQL harness passed 47/47 checks and dropped its DB. This is local fixture evidence, not hosted Supabase/JWT/PostgREST acceptance. Parent integrated rerun count is recorded in final PR/handoff.

Codex device login succeeded at 16:15 HKT via existing ChatGPT subscription. A real finite Codex workspace-write engineering task is now executing on agent/nov04-autoapproval-codex, separate from chat/window edits. No paid API key, upgrade, extra credit purchase, dangerous sandbox bypass or unattended loop was enabled. Staff GitHub main 689aea230b570b4bde915b8d377f6ac46048ddbc was delivered as exact source ZIP and manifest. Its chat/window wrappers still intentionally throw unavailable; a later PWA client implementation is required, not a claim that they currently call new routes.

Deployment discovery: Supabase connector enabled and rechecked, projects=[]; GitHub deploy-variable reads return 403 Resource not accessible by integration. Existing deployment workflow is active/readable; last successful run 35721064048 is 698b981. Exact database/ledger/backup/CORS target facts remain unavailable. Do not dispatch deploy-api.yml and unknowingly apply all pending migrations.

## 1 November 16:54 domain workflow and same-repo Staff update

Latest CEO requirements supersede premature automatic approvals: match requests in complete month/NAAC 42-day candidate; owner reviews/decides; system then records decision/locks/audit/outbox, syncs PWA, and HR paperwork/HRMS remains separate. Bounded questions on target month, N/AN quotas/times and task additive/base-drawn semantics are pending; no silence-as-approval or guessed constraints.

Actual authenticated Codex task consolidated Staff source689aea2 into staff-pwa/, added typed genuine candidate messages/window APIs, UUID retries/session guards/date mapping and durable report submission. Chat/window features remain off; no inherited MessagesPage composer or live approval operation was fabricated. Root tsconfig isolates the nested app; Docker/workflows/manifests/lockfiles remain unchanged. Codex reported36 client tests,44 backend fixtures, PWA check/build and root typecheck; parent independent QA is separate evidence and final PR notes include its actual results.

Parent wrote domain blueprint, roster-first state contract, decision update, manifest/backlog and Chinese workflow map. Official SWD appendix differentiates RCHE/RCHD licence categories; 2024 Code ratio examples are not exhaustive current 2026 nursing-care-practitioner alternatives. User's operational minima are not statutory ratios. Source inventory shows no verified full12-month history and basePR9 gaps in NAAC reader/D+1DO/export, persisted-lock projection, hard-budget/task-demand and correct solver status.

Supabase recheck after user's verification still shows projects=[]; no actual target/ledger/backup facts inferred. No main merge, API deploy, live DB migration/import, DNS, accounts, HRMS record or extra spending. Existing subscription only. Sandbox inode pressure resolved by removing only2 verified inactive duplicated dependency directories; all source/worktrees/deliverables and current dependencies preserved.

## 1 November 17:26 — CEO resolves three SA workflow questions

Target January2027 intake is25November2026->10December2026; issue roster in third weekDecember. General targetM opening25M-2,closecalendarDay10M-1,publishweek3M-1; exact exclusive clock instant and weekday remain config, not invented.

StandaloneN21:15D->07:15D+1; AN/A-N consistsA07:00-14:30D plusN21:30D->07:15D+1, split gap excluded. EligibleHW/RCW/CW; dailyatleast3distinctRCW N-or-AN is hard operational need;2-3AN perapplicableeligibleperson/calendar-month is softfairness, not exactquota or silently N+AN. Remove active six-days note. Elapsed clock time is not paid minutes.

Task +1 defaultadditionalaboveEast/Westbase; authorised fallback proposal may drawbaseline ifextraunavailable, but remaininghardminima/qualification/time/location/budget must revalidate and no duplicateperson/cost. Owner's normalcomplete-candidatereview is decisiongate; not permissiontow aiv e law or new unrecorded per-task overrides.

Real finiteCodex task dispatched17:28 foropt-inSA profileprimitives/newtests only; separateManusagent synchronisesexistingdocs/manifest. No existingsolver/API/DB/UI changes or liveactivation authorised bythis step. FinalsourceSHA/testresults belonginthefollow-uphandoff. No additionalspend.

### SA confirmation final offline evidence

Codex authored4 scopednewfiles and reported45 tests. Parent independently ran45/45, then added safe_to_propose planning evidence plus2tests separating safeproposal fromowneracceptance. Finalparent command `python3 -m pytest -q emma-ai-app/tests/test_sa_confirmed_profile.py` returned47passed in0.15s; py_compile anddiff--check passed. Missing/staleacceptance alone mayleavea safeproposal readyfornormalownerreview; hardcoverage/qualification/incomplete-minima failuresblockbothproposal andfinal localacceptance. No adapterauth/decision/auditwriteismade.

Source remainsopt-in/unwired; noexistingroutes/solver/migrations/UI/deploychanges. Calendaranchors do notcreateDBwindows; nightcountandfairnessevidence are notcompleteCP-SATconstraintintegration. Parent willpushsamePR11asnewSHA,notmain; earlierSHA6574624isnotapprovalforthisnewhead.
