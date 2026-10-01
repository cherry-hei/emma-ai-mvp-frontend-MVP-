# Emma AI Engineering Operating Rules

## Current approved scope
- M1 is in Founder UAT / acceptance review only.
- Synthetic data only. Never use real NGO, staff, resident, roster, or personal data.
- M2, M3, M4, M5 and AI work require separate Founder written approval.
- Existing code does not equal accepted delivery.

## Forbidden actions
- No production deployment, migration execution, cloud/IAM/DNS/billing/secrets changes.
- No merge to main or direct push to main.
- No weakening RLS, auth, privacy controls, test thresholds, or build checks.
- Never use `any`, `ts-ignore`, `|| true` on build/test commands, or fake test evidence.

## Mandatory workflow
1. Inspect first; state exact scope and assumptions.
2. One atomic task per branch.
3. Minimise changes and preserve backward compatibility.
4. Add/update tests for changed behavior.
5. Run typecheck, unmasked production build, lint and relevant tests.
6. Report exact commands, PASS/FAIL, changed files, risks, rollback and Kien review requirements.
7. Stop if a task touches production, real data, paid scope, RLS, migrations, credentials, or unclear requirements.

## Roles
- Founder: scope, spend, customer, production and data approval.
- Kien: technical review, RLS/migrations/IAM/release approval.
- Codex Senior Engineer: implementation/testing only.
- Codex QA/Security Reviewer: read-only review and test evidence only.
- Codex Product/UX Agent: PRD/UI specification only; no code unless approved.

## Tenant safety
- Enforce organisation and facility isolation.
- Demonstrate synthetic cross-organisation read and write denial.
- `facility_id IS NULL` must never imply cross-tenant access.
- Service-role operations must have explicit server-side scope checks.

## Definition of done
A task is not done until tests/build evidence exists and required Kien review is identified.
