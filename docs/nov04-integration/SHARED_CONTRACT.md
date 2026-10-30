# Emma 4 November integration — shared contract v1

Date: 30 October 2026. Authorised implementation and previews, not blanket production release.

Confirmed source/API baseline: `cherry-hei/emma-ai-mvp-frontend-MVP-` main `698b9810003ead2e1cc48e53c33626bb134a185e`. Manager Amplify build SHA remains unverified. OpenAPI snapshot `private/live-openapi.json`, 125 paths, version 0.6.0. API endpoint is Singapore ap-southeast-1. No real NGO data/Auth/production AI processing there under the HK gate.

Existing PR6 `c1c2573` must stay Draft. User goal: 4 November readiness. Gary launch: 1 December 2026. Explain both; do not silently agree to a different date or treat preparation as real production acceptance.

Manager UI target: `/home/ubuntu/emma-pokoi-lamtei-release`, presentation and flow ONLY. Never copy its state/API/Blob/shared-password/staff/rules. PWA UI source: `/home/ubuntu/emma-staff-pwa`; preserve original Emma pink identity and current authenticated API safeguards. Records need date-range filtering.

Frontends proposed on Vercel, same approved data project. Preserve browser → FastAPI Bearer → user-bound DB/RLS. Do not bypass API or replace authentication. No secret/service-role key in client, NEXT_PUBLIC_, VITE_, Git, reports. Supabase actual region and HK Auth/storage/logs/backups must be established before real data. No new database, migration, real account or production data write.

One owner per worktree/file: manager owns shell/CSS, roster owns roster-specific pages/components/helpers (not shared shell/CSS/Auth/API), PWA owns pwa copy, backend owns only emma-ai-app in backend copy, document owner owns reports, deployment owner owns landing copy and read-only inventory. Parent handles integration, GitHub external writes and Vercel operations. Subagents must not push, merge, deploy, change DNS, provision accounts or invoke paid models. Local code commits are allowed with repository attribution rules and no private data.

Branches: agent/nov04-manager-698b981, agent/nov04-roster-698b981, agent/nov04-contract-698b981, agent/nov04-pwa-vercel. Preserve old worktrees and PR6.

Preserve zh/en, UTF-8 literal names/codes, exact minutes, unknown ≠ zero. Empty/nonJSON/error response is failure. No false saved. Hard rules block publishing; individual soft omissions need audit. Preserve tenant scoping and stale session/version guards. Build scripts must not swallow errors with || true.

NAAC # shift requires next calendar day Day Off including boundaries. NAAC six-week 42-day/18-sheet export remains institution-specific. Purple codes inactive for new assignment without destroying history; green corrected shifts prevail. Task rank/demand remains unresolved until Queenie confirms; no guessing. Relevant audited files under /home/ubuntu/naac-oct28-audit and /home/ubuntu/emma-oct29-delivery.

Phone approvals first use authenticated Manus task/GitHub PR controls. Do not claim a custom cross-platform approval service or automatic phone notifications already works. Exact payload, SHA, target, expiry, audit and rollback required for high-impact release/DB/Auth/import/DNS/provider/cost actions. Changed SHA invalidates approval. No actual Codex CLI/session was found; Manus engineering is not execution by the user's Codex account. Shared memory is these versioned files, never automatic chat synchronisation.

Each work package returns branch/commit, changed files, real test counts, offline/mock/live distinction and blockers. Do not claim zero bugs or load acceptance without measurements. No messages sent to Queenie/Kien/Gary; drafts only.
