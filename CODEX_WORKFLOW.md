# Codex Workflow for Emma AI

## 1. Connect the repository

In Codex, connect GitHub and authorise only `cherry-hei/emma-ai-mvp-frontend-MVP-`. Create a repository environment and select `agent/draft-work` as the base branch where the interface permits it.

Do not add AWS production credentials. The first environment needs only the repository, Node/npm, Python and synthetic local-test configuration. Database-backed tests may use local Supabase with Docker Desktop.

## 2. First Codex task: audit only

Paste this before asking Codex to implement M1:

```text
Read AGENTS.md, MVP_SCOPE.md, README.md, SECURITY_EVIDENCE.md and the relevant tests.
Audit the current repository against M1 A.1, A.2 and A.3.
Do not change code.
Return only:
1. existing implementation;
2. missing work;
3. affected tables, APIs and tests;
4. migration and rollback risks;
5. a proposed three-PR sequence;
6. items that require Kien's human review.
Use synthetic data only and do not access AWS or run a deployment.
```

## 3. Recommended M1 pull-request sequence

### PR 1 — A.1 Organisation Architecture

Add the organisation model and `org_id` relationships through an additive migration. Backfill only synthetic fixtures. Preserve existing facility and role behaviour. Include row-count reconciliation and rollback guidance.

### PR 2 — A.3 Organisation-Scoped Retrieval

Apply authenticated organisation scoping to affected reads and writes. Add two-organisation leakage tests covering both allowed and denied operations. Preserve existing facility self-scoping.

### PR 3 — A.2 NAAC Code Import

Build a repeatable, idempotent CSV/XLSX importer with Big5 support, validation, time/hour derivation and reconciled counts. Use the pre-filled code sheet only as provisional configuration. Do not finalise disputed mappings until NAAC returns its confirmation.

Each PR should be based on the accepted previous PR. All remain draft until reviewed.

## 4. Task-card template

```text
Task ID: M1-___
Approved milestone: M1 only, 28h / USD364 fixed
Goal:
Acceptance criteria:
Repository: cherry-hei/emma-ai-mvp-frontend-MVP-
Base branch: agent/draft-work
Likely files:
Required tests:
Data: generated synthetic fixtures only
Out of scope: M2, M3, M4, M5, AI completion, production deployment
Human review: Kien or assigned accountable engineer

Inspect first. Give a short plan, implement the minimum change, run tests, review the diff and open a draft PR. Do not merge, deploy, use production credentials or touch real NGO data.
```

## 5. Review flow

1. Codex implements and tests one task.
2. Codex opens a draft PR targeting `agent/draft-work`.
3. Request `@codex review` for a focused automated review.
4. Kien or another accountable engineer reviews schema, RLS, migration, rollback and test evidence.
5. Cherry decides whether the change is accepted and whether it may be promoted.
6. Promotion to `main` and production deployment require a separate explicit decision.

## 6. Completion standard

M1 is not complete because three PRs exist. It is complete only when the six agreed deliverables are accepted: a usable NAAC synthetic tenant, test accounts, invented six-week roster, organisation-isolation evidence, core-workflow smoke test and short UAT guide.
