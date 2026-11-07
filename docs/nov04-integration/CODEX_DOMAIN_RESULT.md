Implemented locally on `agent/nov04-domain-staff-monorepo`, based on `6bcb10e4a20206044fb73bef881a394b0f5f62c6`.

- Added typed candidate chat/window clients, retry IDs, session isolation and date mapping.
- Fixed report submission to require a durable response and retain failed drafts.
- Kept candidate features default-off. Matched requests remain unapproved until authorised approval.
- Passed 36 client tests, 44 backend fixture tests, PWA typecheck/build and root typecheck.

Wrote [domain analysis](/home/ubuntu/emma-nov01-domain/repo/docs/nov04-integration/CODEX_DOMAIN_ANALYSIS.md) and [integration notes](/home/ubuntu/emma-nov01-domain/repo/docs/nov04-integration/MONOREPO_INTEGRATION.md), including HITL/system boundaries and live blockers.

No deployment, migration, paid fallback or real-data use. Git metadata untouched; parent publication and independent review remain required.