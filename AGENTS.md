# Emma AI shared engineering instructions

Use this file in both Codex and Manus. Chat history is not automatically shared. Read the approved versioned task brief, API contract and acceptance criteria; record your exact branch and source commit before editing.

## Current baseline and release boundary

Current source/API baseline reported by Kien: main 698b9810003ead2e1cc48e53c33626bb134a185e. Amplify manager build SHA is not yet verified. The current API hostname is ap-southeast-1 Singapore; use synthetic fixtures only until Hong Kong production gates are evidenced.

IMPORTANT: .github/workflows/deploy-api.yml currently deploys on pushes to main and applies database migrations. A frontend-only merge can therefore affect API and database deployment. Do not push or merge main, invoke that workflow, or assume a UI release is harmless. Require reviewed exact-SHA release approval and a migration impact/rollback manifest first. Keep PR6 Draft until independently accepted.

## Responsibilities

PM maintains approved scope, dependencies and evidence. UI designer/QA owns presentation and interaction acceptance. Engineer implements against actual API/schema contracts. Independent reviewer checks the diff and test evidence without trusting the implementer's claims. Business-development work drafts communications only; external sends need separate approval.

One task branch/worktree and one owner per editable file. No simultaneous backend edits by different workers. Resolve integration conflicts explicitly. Each task records commit, changed files, tests, runtime versus fixture evidence and remaining blockers.

## Product and data separation

Adopt Pokoi presentation and using-flow only. Never import Pokoi/Haven Blob, shared password, demo roster, staff, staffing/minute rules or chat state into MVP. Preserve NAAC/SA organisation/facility/unit isolation, authentic user identities and backend/RLS feature guards.

Keep manager and Staff PWA on the same approved FastAPI contract. A common data project does not share tokens across domains or waive user-bound permissions. Never put service-role/secret keys in source, NEXT_PUBLIC_*, VITE_*, browser bundles, logs or reports. No production database, real-user provisioning, real NGO data import, authentication replacement or DNS switch without separate approval and Hong Kong residency evidence.

## Required correctness

Preserve literal UTF-8 names/codes and exact hours/minutes. Unknown is not zero. Empty/non-JSON/error response is failure; retain drafts and never show a failed save as successful. Old organisation/session/period responses cannot replace the current view. Respect publication locks and version conflicts.

Use true CP-SAT candidates and deterministic revalidation with the current rule/source version. Hard violations block publication. Only specifically acknowledged soft findings may be omitted, with audit. NAAC # shifts require Day Off on the next calendar day, including boundary obligations; preserve the 42-day/six-week, 18-sheet export contract. Do not guess unresolved Queenie task eligibility or minimum staffing.

## Verification and phone review

Build/typecheck commands must fail on errors; never use `next build || true`. PR checks may run without production secrets. Do not interpret a screenshot, route, offline test or successful build as live DB/RLS or multi-user acceptance.

For decisions from a phone, use the authenticated Manus task or GitHub PR identity and bind approval to the exact action/commit/target. A notification, unauthenticated callback, stale approval, silence, ambiguous chat message or generic code-review approval does not authorise migration/deployment. Changed commit invalidates prior release approval. No automated merge/deployment is provided by this file.

For a task to be ready, supply its commit, exact test counts, preview/runtime evidence where available, no-secret check, feature gates, rollback and open blockers. Dates are targets; never claim zero bugs, no lag or complete production readiness without evidence.
