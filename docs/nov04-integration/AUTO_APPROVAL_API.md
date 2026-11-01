# Automatic leave approval backend candidate

Status: review-only candidate implemented; automatic leave approval is NOT complete.
Date: 1 November 2026. Owner: Codex; independent reviewer: parent Manus (pending).
Branch: `agent/nov04-autoapproval-codex`.
Recorded source commit before editing: `caff1c86c44cf97231e84f24563c1bde6f414a07`.
Original API baseline: `698b9810003ead2e1cc48e53c33626bb134a185e`.
This document and the five new backend/test files are the entire owned change.
Parent task/source-pointer files are excluded.
Final delivery is an uncommitted working-tree candidate on the recorded source
commit: this environment grants read-only access to Git metadata. Parent must
create and independently review the exact candidate commit before release approval.

## Implemented contract

Parent must register `api.routers.auto_approval.router` on the existing FastAPI app.
No registration, deployment, real migration, PWA edit or shared-model change is included.
All routes use existing authenticated Bearer `get_ctx` and the caller's user-bound
Supabase client. OWNER (including existing superintendent alias) only; nurses,
staff, unknown roles and missing scope fail closed. Scope comes from the profile,
never URL/body tenant fields. SQL independently checks actor, facility and org.
The Staff source pointer/handoff and `client/src/lib/api.ts` at the supplied
`689aea230b570b4bde915b8d377f6ac46048ddbc` source were inspected read-only;
its Bearer request contract is preserved. No frontend adoption is implemented.

| Method / path | Contract |
| --- | --- |
| GET `/auto-approval/policy` | `{policy: object or null, mutation_available: false}`; null means no policy, never enabled by default |
| POST `/auto-approval/policy` | Create with expected_version=0, enabled=false; 201 after validated persistence response |
| PATCH `/auto-approval/policy` | Full replacement of policy settings with current expected_version >=1; 200 |
| POST `/auto-approval/evaluations/{request_uuid}` | Body `{expected_policy_version: positive integer}`; bounded single authoritative request read; always manual_review |

Create/patch body example (synthetic configuration, not an approved NGO policy):

```json
{"expected_version":0,"retry_key":"owner-action-unique-1","enabled":false,"allowed_types":[],"rule_version":"reviewed-source-version"}
```

Policy response fields: org_id, facility_id, version, enabled, allowed_types,
rule_version. Integers/booleans are strict; unknown input fields are rejected.
Activation requires a separate patch, explicit nonempty allowed_types and a rule
version. This enables policy intent only: it cannot enable automatic mutation.
Types are literal configured codes; membership does not establish eligibility.
No guessed AL/DO/SL quotas or real identities are seeded. No soft finding is omitted.

Policy RPC `auto_approval_write_policy` serializes on the facility row, checks
expected version, increments it, and appends actor/payload/before/after audit in
one database transaction. Retry identity is scoped to facility and actor: the
same key + exact payload + actor returns the original result, even after later
policy changes. Reusing a key with a different payload/actor, duplicate creation,
or stale expected version returns HTTP 409. Keep the same key/payload when a
save response is lost. A retry response is a receipt for that action; GET returns
the current policy. No direct authenticated policy/audit writes are granted.
Empty/malformed/unconfirmed write responses and DB errors return 503, never success.
GET absence is a valid empty row list; malformed/non-JSON reads return 503.

Evaluation response includes request_id, observed policy_version (or null),
outcome=`manual_review`, mutation_available=false, applied=false, and stable reason
codes. It flags missing/disabled/stale policy, types not explicitly allowed,
nonpending requests and past/invalid dates. Every result also identifies missing
fresh balance/publication-lock checks, unverified duty-window/staffing/qualification/
rule coverage and unavailable transactional apply. Results are ephemeral snapshots,
not durable approvals, evidence certificates, recommendations, or replayable grants.
Only policy mutations have durable retry/audit records. Missing request is 404;
malformed persistence evidence is 503. No client score, cached policy_result_json,
LLM output, or claimed client evidence can approve or reject anything.
Emergency reporting and existing leave endpoints are untouched.

## Automatic-apply blocker and feature gates

Existing `leave.decide` writes status before `roster_locks.apply_for_request`,
then performs additional audit/notification operations. It has no single RPC
covering state CAS, balances, publication/cell locks, fresh source-rule version,
request windows and complete staffing/qualification evidence. This task adds no
approval RPC, apply route, background job, paid model call or fallback to that path.
Unknown staffing/task eligibility is not inferred from leave_type.

A future automatic-apply implementation needs independently accepted source-rule
coverage (including boundary obligations), authoritative duty windows, balance
and publication checks in the same transaction as request CAS, approved-leave
accounting, locks, audit and retry identity. Hard conflicts must block application;
soft omissions require individual acknowledged audit. No approval capability may
be inferred from this evaluator, even when policy.enabled=true.

Integration remains gated on parent router registration, migration review on the
exact approved target and SHA, DB/RLS acceptance, independent diff review and
hosted authenticated multi-user acceptance. No live acceptance is claimed.

## Evidence and exact counts

Final offline command, from repository root:

```sh
APP_ENV=offline SUPABASE_URL=https://example.invalid SUPABASE_ANON_KEY=offline-fixture SUPABASE_SERVICE_ROLE_KEY=offline-fixture PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest emma-ai-app/tests/test_nov04_auto_approval.py emma-ai-app/tests/test_nov04_auto_approval_sql.py emma-ai-app/tests/test_phase5_leave_service.py -q
```

Result: **97 passed, 1 skipped in 2.57s**: 72 new API/service tests,
25 existing leave-policy tests; 1 optional PostgreSQL test skipped by default.
Fixtures are synthetic and process-only settings use example.invalid; no network
client is created by these tests. ASGI transport exercises routing, validation
and auth overrides. This sandbox stalls AnyIO thread wakeups; the test fixture
runs sync dependency/route dispatch inline. Standard TestClient and unmodified
thread dispatch attempts stalled and were interrupted/timed out; they are not
passes. Hosted worker/thread behavior is unverified.

The SQL test opt-in command is `AUTO_APPROVAL_SQL_TESTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest emma-ai-app/tests/test_nov04_auto_approval_sql.py -q`.
Explicit attempts produced **1 setup error, 0 passed**: PostgreSQL could not bind
a Unix socket (`Operation not permitted`). Migration execution was never reached.
The test initializes only a unique disposable cluster/DB, never connects to an
existing DB, and removes its temporary cluster on failure. On a permitted host
it tests the actual migration against minimal source-shaped auth/profile tables,
not the complete Supabase migration chain. SQL syntax/runtime, concurrent CAS,
full baseline integration and live Supabase/RLS acceptance remain unverified.

Python compileall passed for the two modules and two new test files.
No production secret was used or added; new files contain only synthetic UUIDs,
example.invalid settings and fixture placeholders. No external provider call,
purchase, push, deployment, live migration, provisioning or external message ran.

## Files, migration impact and rollback

Owned files:

- `emma-ai-app/api/routers/auto_approval.py`
- `emma-ai-app/emma_core/services/auto_approval.py`
- `emma-ai-app/supabase/migrations/20261101000300_auto_approval.sql`
- `emma-ai-app/tests/test_nov04_auto_approval.py`
- `emma-ai-app/tests/test_nov04_auto_approval_sql.py`
- `docs/nov04-integration/AUTO_APPROVAL_API.md`

Migration adds two empty policy/audit tables, owner-only SELECT RLS policies,
a scoped-owner helper and a narrowly granted policy-write RPC. No existing
leave, balance, roster, profile, workflow or chat/window schema/data is changed.
It has not run against any live target. Facility locking can contend with other
facility writes; this needs runtime review before release.

Before any future release: identify exact project, migration ledger, backup,
rollback and exact-SHA approval. Application rollback: remove parent router
registration/disable access; policy enabled flags do not control any leave mutation.
For schema rollback, first export and preserve policy/audit history, then in a
reviewed transaction drop auto_approval_write_policy, the two new tables (their
policies go with them), and finally auto_approval_is_owner. Do not delete audit
history without separate reviewed authorization. Parent must integrate this into
the full migration impact/rollback manifest. No rollback was executed here.

## Parent Manus review update — 1 November

Independent parent review reran the 97-pass/1-skip offline suite. Parent added an append-only audit UPDATE/DELETE trigger, PUBLIC table revocation and null-profile-org denial. Parent then ran AUTO_APPROVAL_SQL_TESTS=1 outside the Codex sandbox: **1 passed**, using the test's unique disposable local cluster/DB, with CAS/retry/RLS and additional privileged audit/null-org checks. The earlier sandbox socket setup error remains historical and is not a live-Supabase failure claim. No hosted Supabase, customer data or full baseline migration history was tested.

The policy/evaluation foundation remains review-only and automatic leave approval is NOT implemented. Parent will register the candidate router and publish source review evidence separately; no live deployment is implied. Schema rollback must also retire protect_auto_approval_policy_audit after retaining/exporting audit evidence under approval.
