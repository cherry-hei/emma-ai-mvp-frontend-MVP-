## Approved scope

- Task ID:
- Milestone:
- Base branch: `agent/draft-work`
- [ ] This PR is limited to the explicitly approved task.
- [ ] M2, M3, M4, M5 and deferred AI were not added unless named above.

## Change summary

Describe the user-visible and technical result.

## Data and safety

- Data classification: `synthetic only`
- [ ] No real NGO data, credentials, tokens, cookies or secrets were used or committed.
- [ ] Deterministic rules remain authoritative.
- [ ] Care Home A/B behaviour is preserved.
- [ ] Care Home B 34/31/3 regression is preserved or its test evidence is attached.
- [ ] No AWS, IAM, DNS, Firebase-production or GitHub secret/variable change was made.
- [ ] No deployment or production workflow was run.

## Schema and migration

- Migration files:
- Backfill/reconciliation evidence:
- Rollback or safe-disable plan:
- RLS/RBAC impact:

## Validation

| Check | Command | Result |
|---|---|---|
| TypeScript | `npx tsc --noEmit` | |
| Frontend build | `npx next build` | |
| Backend tests | `python -m pytest -q` | |
| Organisation isolation | Relevant authenticated tests | |
| Other | | |

List skipped tests and why. Do not report the full suite as passing if database-backed tests were unavailable.

## Known limitations

State what this PR does not complete.

## Human review gates

- [ ] Kien or assigned engineer reviewed architecture/schema.
- [ ] RLS and cross-organisation behaviour reviewed.
- [ ] Migration and rollback reviewed.
- [ ] Cherry approved any move beyond the draft branch.
- [ ] Production go/no-go remains a separate decision.
