# Codex engineering assignment — automatic leave approval candidate

CEO explicitly requested building automatic leave approval and API deployment on 1 November. Existing subscriptions/credits only; no API-key fallback, paid upgrade or unattended loop. Codex login is now verified using ChatGPT subscription. One finite task in this worktree, base caff1c86c44cf97231e84f24563c1bde6f414a07. Frontend PR8 is merged, original API baseline remains 698b981. No release approval for this new exact backend SHA yet.

## Scope and isolation

Read AGENTS.md, existing api/routers/leave.py, emma_core/services/leave.py, permissions, request policy/roster locks and migration conventions. The Staff PWA repo is cherry-hei/emma-ai-staff-pwa, main 689aea230b570b4bde915b8d377f6ac46048ddbc; it uses the same FastAPI Bearer contract. The parent supplies a source ZIP/manifest separately. Do not copy PWA/manager UI or customer records into backend. Do not edit chat/window SQL owned by another Manus worker.

Own only NEW api/routers/auto_approval.py, emma_core/services/auto_approval.py, migration 20261101000300_auto_approval.sql, tests/test_nov04_auto_approval*.py and docs/nov04-integration/AUTO_APPROVAL_API.md. Parent registers the router. Do not edit existing leave decision, auth, permissions, shared models, main, workflows, PWA or demo files. Do not commit parent files, push/merge/deploy/migrate live/provision users/change DNS/send messages.

## Required candidate

Implement persistent facility/org scoped, owner-authorised auto-approval POLICY with disabled-by-default state, no seeded real identities or guessed AL/DO/SL limits. Policy must explicitly allow types and define version/CAS and audit. Unknown facts or missing policy/evidence must yield manual-review/unavailable, never approve/reject from an LLM score, cached client result or optimistic write. Unrecognised roles and cross-tenant requests fail closed. Recommend is not final approval; staff/nurses cannot enable policies or execute approval.

Provide a real API evaluation resource for a bounded single request and policy-management contract. Owner policy activation is distinct from code deployment; default automatic mutation OFF. Decide whether a safe fully transactional approval RPC can be added with existing source schema. Approval must atomically include state CAS, fresh authoritative policy checks, approved-leave balance/locks/audit and retry identity. Existing leave.decide currently updates status then applies roster lock in separate calls; do NOT call it and claim atomic automatic approval. If that invariant cannot be safely established in this finite task, implement durable policy + deterministic evaluation/review-only gate, explicitly return mutation unavailable and document automatic-apply blocker. Do NOT pretend evaluate == approve or add a route that silently falls back to partial writes. This restriction is a security requirement, not permission to claim the requested feature complete.

Automatic policies must not approve past/published conflicting cells, unknown minimum staffing/qualifications, overdrawn leave, invalid/closed duty windows, hard rule conflicts, stale policy versions or missing rule coverage. Emergency reporting remains allowed independent of automatic approval. Soft omission requires a separately acknowledged audited rule, not implicit omission. Do not infer rule eligibility from leave_type alone.

## Evidence

Implement real fixtures and security tests, malformed/empty persistence response rejection, authorised/unauthorised policy create/patch/read, stale CAS/idempotency conflict and deterministic manual-review fallback. Use process-only example.invalid Supabase settings for offline tests, no secrets. Save exact tests/counts and explain optional SQL DB coverage; no claim of live Supabase/RLS acceptance. Return changed files, final status, actual feature implemented vs blockers in AUTO_APPROVAL_API.md. If using local PostgreSQL, create only uniquely named disposable DB and drop it; no existing DB. One bounded engineering pass; parent Manus independently reviews it.
