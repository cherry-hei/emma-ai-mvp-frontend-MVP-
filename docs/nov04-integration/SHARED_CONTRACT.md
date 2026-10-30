# Emma 4 November integration — shared contract v2

Date: 30 October 2026. Authorised implementation and previews, not blanket production release.

Confirmed source/API baseline: `cherry-hei/emma-ai-mvp-frontend-MVP-` main `698b9810003ead2e1cc48e53c33626bb134a185e`. Manager Amplify build SHA remains unverified. OpenAPI snapshot `private/live-openapi.json`, 125 paths, version 0.6.0. API endpoint is Singapore ap-southeast-1. CEO authorised non-HK hosting and real-data internal trial on 31 October 2026. This supersedes the prior HK-only trial gate. It does not waive tenant isolation, least privilege, server-only secrets, or backups.

PR6 `c1c2573` is historical mixed work, not a prerequisite of PR7/PR8. Use the two existing successor PRs for a bounded reviewed release; do not merge PR6 wholesale. User goal: 4 November internal functional UAT with authorised real data. Gary launch: 1 December 2026. Explain both; do not silently agree to a different date or treat preparation as real production acceptance.

Manager UI target: `/home/ubuntu/emma-pokoi-lamtei-release`, presentation and flow ONLY. Never copy its state/API/Blob/shared-password/staff/rules. PWA UI source: `/home/ubuntu/emma-staff-pwa`; preserve original Emma pink identity and current authenticated API safeguards. Records need date-range filtering.

Frontends proposed on Vercel, same approved data project. Preserve browser → FastAPI Bearer → user-bound DB/RLS. Do not bypass API or replace authentication. No secret/service-role key in client, NEXT_PUBLIC_, VITE_, Git, reports. Identify the actual Supabase project used by Kien first; the connected account currently returns zero visible projects. Non-HK trial is allowed. No guessing/replacement empty database; inspect migration effects and backup/rollback before target-specific execution. Never put provider service secrets in clients.

One owner per worktree/file: manager owns shell/CSS, roster owns roster-specific pages/components/helpers (not shared shell/CSS/Auth/API), PWA owns pwa copy, backend owns only emma-ai-app in backend copy, document owner owns reports, deployment owner owns landing copy and read-only inventory. Parent handles integration, GitHub external writes and Vercel operations. Subagents must not push, merge, deploy, change DNS, provision accounts or invoke paid models. Local code commits are allowed with repository attribution rules and no private data.

Branches: agent/nov04-manager-698b981, agent/nov04-roster-698b981, agent/nov04-contract-698b981, agent/nov04-pwa-vercel. Preserve old worktrees and PR6.

Preserve zh/en, UTF-8 literal names/codes, exact minutes, unknown ≠ zero. Empty/nonJSON/error response is failure. No false saved. Hard rules block publishing; individual soft omissions need audit. Preserve tenant scoping and stale session/version guards. Build scripts must not swallow errors with || true.

NAAC # shift requires next calendar day Day Off including boundaries. NAAC six-week 42-day/18-sheet export remains institution-specific. Purple codes inactive for new assignment without destroying history; green corrected shifts prevail. Task rank/demand remains unresolved until Queenie confirms; no guessing. Relevant audited files under /home/ubuntu/naac-oct28-audit and /home/ubuntu/emma-oct29-delivery.

Phone approvals first use authenticated Manus task/GitHub PR controls. Do not claim a custom cross-platform approval service or automatic phone notifications already works. Exact payload, SHA, target, expiry, audit and rollback required for high-impact release/DB/Auth/import/DNS/provider/cost actions. Changed SHA invalidates approval. No actual Codex CLI/session was found; Manus engineering is not execution by the user's Codex account. Shared memory is these versioned files, never automatic chat synchronisation.

Each work package returns branch/commit, changed files, real test counts, offline/mock/live distinction and blockers. Do not claim zero bugs or load acceptance without measurements. No messages sent to Queenie/Kien/Gary; drafts only.

## Latest execution evidence and activation conditions

31 October: current API rejects CORS preflight for both https://emma-ai-staff-pwa.vercel.app and https://emma-ai-manager-mvp.vercel.app (HTTP 400, no Allow-Origin). Backend operator must add these exact origins to the effective CORS_ORIGINS while preserving approved origins; do not open wildcard Vercel/Amplify trust. PWA must use VITE_API_BASE set to the confirmed FastAPI origin, never a DB service key. Chat/request-window routes are absent from the public OpenAPI. New PWA auth/me hydration and CP-SAT persisted locks/hash-next-day-off patches remain subject to source review and hosted UAT.

GitHub event queue enabled/synced: new PR review and CEO Emma: comment dispatch. A configured trigger is not evidence that an engineering event has already executed. Lark/WhatsApp notification and phone release-approval service are not running. Public repo requires non-sensitive status only.
