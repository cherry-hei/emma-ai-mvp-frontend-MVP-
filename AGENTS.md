# Emma AI shared engineering instructions

Use this file in both Codex and Manus. Chat history is not automatically shared. Read the approved versioned task brief, API contract and acceptance criteria; record your exact branch and source commit before editing.

## Current baseline and release boundary

Frontend main is caff1c86c44cf97231e84f24563c1bde6f414a07, released on 31 October 2026 (PR8 merged). It changed UI only; zero Actions runs and no API/DB/DNS action. Kien's previously confirmed API source/deployment baseline is 698b9810003ead2e1cc48e53c33626bb134a185e. Amplify public assets show the new UI; its build-history SHA was not independently read. The current API hostname is ap-southeast-1 Singapore. The CEO authorised non-HK hosting and coded real-data internal trial for 4 November; NGO staff launch remains December. Residency is not a trial blocker. Developer tests use disposable fixtures; only the selected live project with reviewed tenant/RBAC and backup controls may hold authorised trial data.

IMPORTANT: .github/workflows/deploy-api.yml currently deploys on pushes to main and applies database migrations. A frontend-only merge can therefore affect API and database deployment. Do not push or merge main, invoke that workflow, or assume a UI release is harmless. Require reviewed exact-SHA release approval and a migration impact/rollback manifest first. Keep PR6 Draft until independently accepted.

## Responsibilities

PM maintains approved scope, dependencies and evidence. UI designer/QA owns presentation and interaction acceptance. Engineer implements against actual API/schema contracts. Independent reviewer checks the diff and test evidence without trusting the implementer's claims. Business-development work drafts communications only; external sends need separate approval.

1 November integration work is agent/nov04-domain-staff-monorepo, based on PR9 6bcb10e. Chat/window candidate PR9 is by Manus. Codex CLI authentication via the existing ChatGPT subscription succeeded at 16:15 HKT; real finite tasks produced separate PR10 policy/evaluation foundation and this Staff PWA client/domain candidate. Staff source was copied from private emma-ai-staff-pwa main 689aea2 into staff-pwa/ in THIS repo, with separate builds and unchanged API Docker/workflows. Candidate source is not live acceptance. Saved-agent profile management is unavailable; task subagents are not persistent profiles. Invitation-only onboarding and chat/window internal-UAT priority are approved. Use existing subscriptions/credits only; ask before extra purchases, API-key billing, paid hosts/runners or upgrades. No automatic additional spending is authorised.

One task branch/worktree and one owner per editable file. No simultaneous backend edits by different workers. Resolve integration conflicts explicitly. Each task records commit, changed files, tests, runtime versus fixture evidence and remaining blockers.

## Product and data separation

Adopt Pokoi presentation and using-flow only. Never import Pokoi/Haven Blob, shared password, demo roster, staff, staffing/minute rules or chat state into MVP. Preserve NAAC/SA organisation/facility/unit isolation, authentic user identities and backend/RLS feature guards.

Keep manager and Staff PWA on the same approved FastAPI contract. A common data project does not share tokens across domains or waive user-bound permissions. Never put service-role/secret keys in source, NEXT_PUBLIC_*, VITE_*, browser bundles, logs or reports. Real-data internal trial, provisioning and domain setup are within the CEO's current requested scope, but do not guess the database, accounts or owned domain. Record the exact target, reviewed migration/data/auth effects and rollback before high-impact execution. Do not require Hong Kong residency for this trial. Real NGO data must never enter the public source repository or AI engineering prompts.

## Required correctness

Preserve literal UTF-8 names/codes and exact hours/minutes. Unknown is not zero. Empty/non-JSON/error response is failure; retain drafts and never show a failed save as successful. Old organisation/session/period responses cannot replace the current view. Respect publication locks and version conflicts.

Use true CP-SAT candidates and deterministic revalidation with the current rule/source version. Hard violations block publication. Only specifically acknowledged soft findings may be omitted, with audit. NAAC # shifts require Day Off on the next calendar day, including boundary obligations; preserve the 42-day/six-week, 18-sheet export contract. Do not guess unresolved Queenie task eligibility or minimum staffing.

The latest CEO workflow is roster-first: pending request matched in a COMPLETE candidate is NOT approval. Owner reviews the complete plan and final requests; only durable authorised decision+lock+audit/outbox receipts change approved status/notices. HR forms/HRMS are separate. AI explains/asks bounded version-bound questions; it does not waive hard rules or approve. A valid human answer creates new authorised input/version and system resumes automatically. Read DECISION_UPDATE_2026-11-01.md and DOMAIN_WORKFLOW_BLUEPRINT.md. Do not assume 12 months history exists, SA codes/windows apply to NAAC, vacancy allowance is actual spendable budget, or unknown task qualifications are zero. No automatic staffing/employment cuts or health/performance inference.

## Verification and phone review

Build/typecheck commands must fail on errors; never use `next build || true`. PR checks may run without production secrets. Do not interpret a screenshot, route, offline test or successful build as live DB/RLS or multi-user acceptance.

For decisions from a phone, use the authenticated Manus task or GitHub PR identity and bind approval to the exact action/commit/target. A notification, unauthenticated callback, stale approval, silence, ambiguous chat message or generic code-review approval does not authorise migration/deployment. Changed commit invalidates prior release approval. No automated merge/deployment is provided by this file.

For a task to be ready, supply its commit, exact test counts, preview/runtime evidence where available, no-secret check, feature gates, rollback and open blockers. Dates are targets; never claim zero bugs, no lag or complete production readiness without evidence.

## Active event-based engineering queue — 31 October 2026

The Manus GitHub event workflow is enabled for this repository: new PRs receive bounded review; only verified CEO GitHub comments by cherry-hei beginning `Emma:` dispatch one scoped code task. Every task has one file owner, exact SHA, offline/live distinction, reviewer and next action. No automatic main merges, production deploys, migrations or external messaging. Full private chats are not copied between platforms; versioned decisions and work summaries are shared instead. Codex execution requires separately authenticated runner; never claim it ran when Manus performed the task.
