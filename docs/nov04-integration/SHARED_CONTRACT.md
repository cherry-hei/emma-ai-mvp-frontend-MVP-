# Emma 4 November integration — shared contract v3

Updated 1 November 2026. This contract authorises bounded implementation and review, not blanket production deployment.

## Approved baseline and decisions

Frontend main is `caff1c86c44cf97231e84f24563c1bde6f414a07`; PR8 merged on 31 October and original Amplify public assets show the new UI. That release ran no API deployment, database migration or DNS change. Kien's previously confirmed API deployment/source baseline is `698b9810003ead2e1cc48e53c33626bb134a185e`; the actual runtime may only be established with operator evidence. PR6 remains Draft/reference. PR7 is open/review-ready, not merged or deployed. Do not merge either wholesale into this candidate.

CEO decisions are settled: invitation-only onboarding with assigned organisation/facility/unit/role; chat and duty/DO request windows required for 4 November internal UAT; authenticated Manus/GitHub approval channel first; owned GoDaddy domain inventory to be supplied. Coded real-data trial in Singapore is authorised and Hong Kong residency is not a trial blocker. NGO staff rollout target remains December. No numeric daily extra-spend cap has been received, so no additional paid unattended runner or automatic extra-credit purchase is activated.

## Work ownership

Integration branch: `agent/nov04-chat-windows-live`, based on caff1c8. Chat worktree owns new messages router/service/migration/tests. Window worktree owns request windows and bounded leave gating. Parent owns route registration, manager retry-idempotency UI, integration docs and GitHub branch/PR publication. Independent reviewer owns the external disposable-DB fixture and review report; do not modify implementation files concurrently.

Codex CLI 0.166.0 is installed, but engineering performed before verified authentication is Manus work, never described as Codex execution. Read `CODEX_NEXT_TASK.md` for a single scoped task after authentication. Lark is configured read-only but cannot be called without app credentials/user OAuth. Saved-agent profile management is unavailable in this task; finite task subagents are not persistent profiles. Platforms share these versioned files/PR evidence, not automatically copied private chat memory.

## API and safety boundaries

Manager/Staff PWA share the same approved FastAPI Bearer → user-bound DB/RLS contract. The candidate adds `/messages*`, manager `/request-windows*` and own `/me/request-window`. Messages preserve durable real-row responses and retry client IDs; no local fabricated chats or automatic replies. Request windows use DB server time, scoped durable rows, audit, idempotent create, versioned patch and duty/DO enforcement. Emergency sickness remains reportable when duty applications close. `CHAT_API.md` and `REQUEST_WINDOW_API.md` define exact contracts and remaining policy blockers.

Canonical requested-date ranges are half-open with `target_end_exclusive`; the current PWA legacy `/request-windows/duty` response maps to inclusive `target_end` by subtracting one calendar day. No PWA deployment or API enablement is implied. Hosted auth/CORS and real-user flows remain required.

No Pokoi/Haven Blob, passwords, names, staff, saved rosters or minute/coverage rules enter MVP. Preserve NAAC/SA tenant/unit separation, UTF-8 and exact minute accounting; unknown is not zero. Hard constraints block publication; individually acknowledged soft omissions need audit. Preserve NAAC #-next-calendar-day DO and 42-day/18-sheet export. Do not guess unresolved task eligibility/headcount or reclassify M1/M2 acceptance from offline checks.

No service-role/secret key in source, `NEXT_PUBLIC_*`, `VITE_*`, browser bundles, logs or reports. No customer identifiers/data in the public MVP repository or AI engineering prompts. No real provisioning or trial import until the precise authorised target and role matrix are verified.

## Release and phone approval

The existing main deploy workflow invokes `supabase db push --include-all` and ECS deployment. A future main merge can apply ALL pending migrations, not just these two candidate files. Require the actual target/migration ledger, full pending manifest, exact SHA, reviewed schema/RLS/RBAC/CORS evidence, backup/restore rehearsal and rollback approval before any backend release. A branch PR or code-review approval is not deploy/migration approval. Changed SHA invalidates an old release approval.

Existing GitHub event queue is enabled/ready/synced: bounded new-PR review and verified CEO `Emma:` comment dispatch. It does not automatically merge, deploy, migrate or send Lark/WhatsApp messages. Phone push depends on user app settings and has not been verified. No duplicate trigger or unattended loop is introduced.

Each package records its commit, files, exact test commands/counts and evidence boundaries. Local PostgreSQL fixtures do not prove live Supabase JWT/PostgREST policies, real multi-user acceptance or load performance. Obtain actual Supabase project reference/access, effective CORS, applied migrations/RLS, manager/staff/deputy role mappings and backup facts from Kien; do not ask the CEO to guess secrets or environments.
