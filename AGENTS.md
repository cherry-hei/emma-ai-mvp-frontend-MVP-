# AGENTS.md — Emma AI MVP Repository

These instructions apply to every Codex or AI-assisted task in this repository.

## Mission and current authority

Emma AI is a Hong Kong care-home compliance-first scheduling system. The immediate engineering priority is the accepted **M1 synthetic trial scope**:

- A.1 Organisation Architecture
- A.2 NAAC Code Import
- A.3 Organisation-Scoped Retrieval

M2, M3, M4, M5, defect reserve and deferred AI completion are not authorised merely because they appear in planning documents. Do not start them unless the task explicitly states that Cherry approved that milestone.

When repository documents conflict, use this order:

1. The current task and explicit approval from Cherry
2. This `AGENTS.md`
3. `MVP_SCOPE.md`
4. The relevant dated implementation specification
5. `README.md` and older planning notes

Identify conflicts instead of silently choosing the larger scope.

## Non-negotiable product rules

- The deterministic rule and scheduling engine is authoritative for eligibility, compliance, exclusion and ranking evidence.
- AI may parse a question or explain validated structured evidence. It must not decide compliance, override a hard rule, invent policy or silently choose an ambiguous scope.
- A manager remains the final approver.
- Preserve the Care Home B regression fixture: 34 candidates, 31 compliant and 3 expected exclusions for the 2026-09-01 `SLEEP` HCA shift.
- Preserve Care Home A and Care Home B while adding organisation scoping.
- Avoid duplicate screens, duplicate business logic and one-off facility branches. New facilities should be configuration, not separate products.

## Data boundary

The repository and all Codex tasks are **synthetic-data only** until the complete Hong Kong production gate is approved and accepted.

Do not:

- import or inspect real NGO roster workbooks, staff names, leave reasons, certificates, attachments or resident information;
- use the `import_real_rosters.py --commit` or `--replace-demo-data` paths;
- copy data from current overseas databases into a task environment;
- place real data, credentials, tokens, cookies or secrets in prompts, commits, fixtures, logs, screenshots or pull requests.

Some older repository text describes historical real-workbook imports. It is not permission to use those records. Build and test with generated synthetic fixtures only.

All real NGO Auth, API, compute, database, storage, logs, backups, keys and production AI processing must remain in Hong Kong. `ap-east-1` resources alone do not prove that the production gate has passed.

## Repository and deployment safety

- Work from `agent/draft-work` or a task branch based on it.
- Never push directly to `main`.
- Never merge a pull request.
- Never run `workflow_dispatch`, `gh workflow run` or any production deployment command.
- A push to `main` triggers `.github/workflows/deploy-api.yml`, applies database migrations and deploys to AWS. Treat this as a protected production action.
- Do not change AWS, IAM, GitHub Actions variables/secrets, DNS, Firebase production settings or external service permissions unless the task explicitly authorises the exact change.
- Never use an AWS root login or long-lived production access key.
- Do not modify the deployment workflow as part of an unrelated feature.

Open a draft pull request for review. Kien or another accountable human engineer must review production-facing changes before Cherry separately approves any promotion to `main`.

## Stack and design boundaries

- Frontend: Next.js 16, React 19, TypeScript, Tailwind and shadcn/radix at the repository root.
- Backend: Python FastAPI under `emma-ai-app/`.
- Scheduling: OR-Tools CP-SAT plus the deterministic validation engine.
- Data: Postgres with RLS/RBAC and audit evidence. Supabase is a current tool, not a mandatory permanent architecture.
- Docker Desktop should remain running for local Supabase and database-backed tests.
- Keep domain and validation logic in `emma_core`; routers and UI should consume it rather than reimplement it.
- Reuse existing API contracts and components. Make the smallest change that satisfies the acceptance criteria.

## Work protocol

For every task:

1. Inspect the relevant files, tests, migrations and recent commits.
2. Return a short plan with scope, files, tests, risks and human-review points.
3. Implement only the approved scope.
4. Add or update tests before claiming completion.
5. Run the strongest safe local checks available.
6. Review the diff for secrets, real data, destructive SQL and unrelated changes.
7. Return a concise summary, test evidence, known limitations and required human actions.
8. Open a draft pull request; do not merge or deploy.

Use one implementation agent and one review pass. Do not simulate a long multi-role debate.

## Validation commands

Frontend:

```bash
npm ci
npx tsc --noEmit
npx next build
```

Run `npx next build` directly because the current `npm run build` script contains `|| true` and may hide a failed build.

Backend:

```bash
cd emma-ai-app
python -m pip install -r requirements.txt
python -m pytest -q
```

Database-backed tests require Docker Desktop and local Supabase. If the database is unavailable, run the relevant offline tests, report exactly what was skipped and do not claim the full suite passed.

For M1 or tenancy work, include authenticated cross-organisation read and write tests using at least two synthetic organisations.

## Migration rules

- Use additive, ordered and reviewable migrations.
- Do not delete, truncate or reseed an existing environment.
- Backfill `org_id` deterministically and reconcile row counts.
- Add constraints only after proving existing synthetic rows satisfy them.
- Include forward checks, checksums or reconciled counts, and a rollback or safe-disable plan.
- Re-run affected RLS/RBAC tests and the Care Home B regression fixture.
- Never apply a migration to a live database from Codex.

## Pull-request evidence

Every draft PR must state:

- approved milestone and task ID;
- problem and scope;
- files and schema changed;
- data classification (`synthetic only` unless a later written gate says otherwise);
- tests run and their results;
- migration and rollback approach;
- organisation-isolation evidence;
- known limitations;
- actions requiring Kien/engineer review;
- explicit statement that no deployment or production data action was performed.

## Mandatory human review

Codex may prepare Infrastructure as Code, migration/checksum scripts, PostgREST and Auth adapters, RLS matrices, automated tests, restore scripts and cutover checklists.

An authorised human engineer must execute or sign off:

- production IAM and credentials;
- live-database preflight and migration;
- Auth signing keys;
- every production RLS policy;
- backup and restore drill;
- DNS cutover;
- production go/no-go and rollback decision.
