# Staff PWA candidate integration — 1 November 2026

Recorded before edits: branch `agent/nov04-domain-staff-monorepo`, source HEAD `6bcb10e4a20206044fb73bef881a394b0f5f62c6` (PR9). Git metadata is read-only; no implementation commit created. Parent must publish and bind review to the resulting exact SHA.

Staff source provenance supplied in the approved brief: private `cherry-hei/emma-ai-staff-pwa`, main `689aea230b570b4bde915b8d377f6ac46048ddbc`, copied into `staff-pwa/`. No remote provenance verification performed. It was already untracked at task start, alongside the two task briefs. Preserve that distinction when reviewing the parent diff.

## Isolation and hosting instructions

The root Next app retains its dependencies and workspace configuration. Root `tsconfig.json` now excludes `staff-pwa`, including its nested app and test sources. Staff remains a standalone Vite package with its own unchanged package manifest, lockfile, aliases, assets and `dist` output. Root `Dockerfile` still copies only `emma-ai-app/`; no Docker or runtime configuration edits occurred.

For a future separately approved Vercel configuration: Root Directory `staff-pwa`, install `pnpm install --frozen-lockfile`, build `pnpm build`, output `dist`. The inherited `staff-pwa/vercel.json` was not edited. These are instructions only; no Vercel project, origin, environment file, secret or deployment was created or changed. Browser tokens remain origin-local; a shared backend does not share browser credentials between manager and staff domains.

## Candidate contract implementation

`client/src/lib/api.ts` implements typed contacts, message list (peer/before/limit), send and persisted read receipts against the candidate routers. It rejects malformed or missing durable rows. Outbound input contains only recipient profile ID, exact message body and UUID retry ID. Real IDs come from authenticated `/messages/contacts`; no synthetic contacts, replies, sender, role or tenant are injected. Backend JWT/RLS remains authoritative.

Each recipient's unresolved send retains the same UUID for exact-content retries, including an ambiguous network failure. Editing content or changing recipient creates a new attempt. Successful completion removes only its own attempt. Credential generation changes clear attempts; old responses cannot overwrite new-session state. Retry state is memory-only, not an automatic offline queue. The caller must retain draft text on failure; no automatic background replay occurs.

Canonical `/me/request-window?kind=duty` is unwrapped and its exclusive date is converted by UTC calendar subtraction to the legacy inclusive `DutyRequestWindow.target_end`. Backend status controls availability; no browser-clock deadline or notice is invented. Missing/closed/unavailable windows are inactive. `submitLeaveRequest` gates DO/duty/swap using that mapping, while SL/DSL remain ungated by the ordinary window; the backend repeats enforcement. Submission requires a durable pending request, never approval.

The inherited ReportPage previously declared success without any request. Its submit now awaits the actual API, retains failed drafts, blocks duplicate submits, disables gated ordinary types by default and honestly labels unavailable attachment upload. Presentation otherwise remains the supplied source. No HRMS or paper submission is implied.

Both feature flags stay literal `false` in `features.ts`; only isolated tests mock them true. No environment bypass added. MessagesPage still displays the unavailable notice; a chat composer is not introduced by this wrapper-scoped task. The client contract is implemented, not live operational chat.

## Verification and review boundary

Dependencies installed using `pnpm --dir staff-pwa install --offline --frozen-lockfile`: 274 reused, zero downloads; no lockfile update. Final commands/results are recorded in CODEX_DOMAIN_ANALYSIS.md. Builds use no configured live API origin. All API tests use synthetic in-process/mocked fixtures. No live API, DB, migrations, CORS, real identities, push delivery, browser interaction or multi-user acceptance was tested.

Existing copied PreferencesPage contains demo preference arrays and local-only controls. They were not consumed by this integration or promoted to backend facts. That inherited screen requires a separate approved review before live use. The scoped implementation does not certify all inherited routes as trial-ready.

Rollback before release: parent can restore root tsconfig exclusion and the changed PWA files to the copied source, or remove the unshipped copied package. Keep both candidate flags off. No database rollback is needed because no database action occurred. Once any future messages exist, retention and backend rollback need their own reviewed manifest; do not drop audit tables.
