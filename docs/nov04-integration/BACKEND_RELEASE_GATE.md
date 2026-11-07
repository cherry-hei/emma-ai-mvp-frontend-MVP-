# Backend candidate release gate

This file is not deployment approval. The candidate was built from frontend main caff1c86c44cf97231e84f24563c1bde6f414a07. Main, API, customer database, DNS and Pokoi storage remain unchanged by this package.

## Proposed schema changes

- `20261031000100_direct_messages.sql`: durable direct messages, metadata audit, participant/scoped RLS, guarded send/read/contact RPCs and idempotent sends.
- `20261031000200_request_windows.sql`: scoped durable application windows, audit, versioned/idempotent management RPCs, DB-time availability and duty/DO request enforcement.

Neither has been applied to the real Supabase target. Their content hashes and final source SHA must be attached to a release request after review. Do not approve a release against an earlier candidate hash.

## Kien/operator facts required

Confirm the actual Supabase project URL/reference and authorised operator, deployed API revision, effective CORS, migration ledger and current schema/RLS/function ownership/grants. Confirm expected manager/staff/deputy profiles and unit links without exposing personal records or keys in the public repository. Operator validates existing leave/profile update policies so new gates cannot be bypassed through an older direct-client surface.

The main deploy workflow uses `supabase db push --include-all`: inspect its ENTIRE pending migration list. It can apply older pending changes in addition to these two files. A repo source listing is not proof that a migration was already applied.

## Acceptance evidence required before release

Use a disposable staging Supabase project with actual JWT/PostgREST/RLS paths. Verify both organisations and sibling units, unknown/unlinked accounts, private message reads, sender/recipient identity, retry mismatch/concurrency, immutable audit and read receipts. Verify real owner/staff operations, CAS stale writes, duty/DO gate, application time/date boundaries, unit override, emergency sickness reporting and closing/concurrent request races. Confirm direct-client update paths cannot turn another leave type into a gated request or alter staff/scope to bypass enforcement.

Verify manager and Staff PWA CORS and login, same backend contract, independent per-domain auth tokens, send/reload/reply/read and legacy inclusive end date. Do not label missing manager window-control UI, invitation lifecycle, full-month solver/export or load tests as completed by backend route registration.

## Backup and rollback

Before migration, take an operator-controlled snapshot/backup and rehearse restoration, naming backup time and rollback owner in private release evidence. Record change effects on authenticated callers and existing approvals. Keep audit/messages as evidence; application rollback must not blindly drop durable communications or audit tables. Review any temporary gate disablement explicitly because it changes who may submit duty requests.

Deploy the exact reviewed application image/schema in a controlled sequence with CORS kept to exact origins. Verify live health, route schema, persistence and cross-tenant denial. Only then enable the PWA/API gate or canonical DNS after separate target-specific approvals. No service secrets in client bundles or Git.

## Approval payload

The CEO must receive exact full SHA, API/image target, database project, complete pending migration names/hashes, data/auth effects, tested backup/restore/rollback and final blockers. Generic code approval, prior frontend release approval, silence or another SHA is not approval to deploy or migrate.
