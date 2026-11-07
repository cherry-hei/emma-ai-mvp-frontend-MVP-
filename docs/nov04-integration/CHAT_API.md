# Nov 04 Direct Messaging API Integration

## Scope and integration ownership

This change supplies, but deliberately does **not** register, `api/routers/messages.py`. The integration owner must add the module import and router to `emma-ai-app/api/main.py` with the existing router loop. No API main, shared models, permission matrix, frontend, migration execution, deployment, or data operation is included in this commit.

Migration to review before any environment application:

```text
emma-ai-app/supabase/migrations/20261031000100_direct_messages.sql
```

The migration is transactional when run through the repository migration runner. It creates `direct_messages`, `direct_message_audit`, RLS policies, immutability triggers, a contact RPC, and the two write RPCs. It does not seed contacts or messages.

## HTTP contract

All routes need the standard bearer JWT and return the ordinary JSON error envelope from `api.main` / `api.deps`.

| Method | Route | Request | Response |
|---|---|---|---|
| `GET` | `/messages/contacts` | — | `[{id, display_name, role, staff_id?}]` |
| `GET` | `/messages` | `before` optional RFC3339 exclusive `created_at` cursor; `limit` 1–100 (default 50); `peer` optional UUID | `[{id, sender_profile_id, recipient_profile_id, body, created_at, read_at}]`, newest first |
| `POST` | `/messages` | `{recipient_profile_id: UUID, body: nonblank string <= 4000 chars, client_message_id?: UUID}` | durable direct-message row, `201` |
| `PATCH` | `/messages/{id}/read` | — | durable direct-message row with persisted `read_at` |

`POST` supports retry idempotency only when `client_message_id` is supplied. Reusing that UUID for the same sender, recipient, and exact body returns the original durable row. Reusing it for different content is a `409 conflict`. A missing or malformed durable RPC result is a JSON `500 message_write_failed`, never `{ok:true}`.

The current `src/lib/messages-api.ts` sends the baseline POST payload without an idempotency key; the parent/frontend owner can add a UUID client key independently. Its existing response validator is compatible with all route responses above.

## Database-enforced safety boundary

This feature does **not** call `get_service_client()`. The service uses the caller's JWT-bound Supabase client.

The two write functions are intentionally `SECURITY DEFINER`, narrowly executable only by `authenticated`, and explicitly reject anything whose `auth.role()` is not `authenticated`. Each derives the caller from `auth.uid()`; neither accepts sender, facility, organisation, unit, role, or `read_at` input. The functions use fixed `search_path`s, no dynamic SQL, and are transactional.

The underlying table stores facility and organisation IDs and has participant-only RLS for reads. Browser `INSERT`, `UPDATE`, and `DELETE` privileges are revoked. `send_direct_message()` validates both profiles and writes the message plus a `sent` audit event atomically. Its transaction advisory-locks `(sender_profile_id, client_message_id)` before lookup/insert, with a partial unique index as the durable backstop. `mark_direct_message_read()` locks the row, verifies the caller is the recipient, persists `read_at` once, and appends one `read` audit event.

Message body, sender, recipient, tenant, idempotency key, and creation timestamp are immutable. Read state may only change `NULL -> timestamp` while the read RPC's transaction-local guard is set; the trigger rejects direct/forged updates and all message deletes. `direct_message_audit` is append-only, is not exposed to authenticated table readers, and stores event metadata rather than duplicating message content.

Participant visibility is evaluated against the **current** profile/staff/unit linkage. If either peer is deactivated or transferred to another primary unit, the former conversation is no longer returned and a pending recipient cannot mark it read. This is a conservative privacy default; retention/access policy should be confirmed during product and legal review.

## Scope assumptions and review questions

The existing source does not define a `Feature.DIRECT_MESSAGES` row in `emma_core.permissions`, nor an approved manager/staff messaging matrix. It also has no direct-message schema or the requested PR6 branch locally. This implementation therefore **does not invent a role allowlist**. It accepts only a known role stored in the database and otherwise fails closed.

Actual source relationships used for the conservative peer rule:

- `users_profile.auth_user_id` is the authenticated identity source.
- `users_profile.staff_id -> staff.id` is the profile/staff linkage.
- `staff.status = 'active'` means a contact is active.
- `staff.primary_unit_id -> facility_units.id` is the only current unit relationship on staff.
- `users_profile.facility_id` and `org_id` must equal the linked staff/facility organisation.

A sender and recipient must both be active, staff-linked, have a known role, and share **facility, organisation, and primary unit**. Profiles with a null/mismatched org, null/mismatched unit, inactive staff row, missing auth linkage, or unknown role get no contacts and cannot list/send/read messages. This is intentionally restrictive. Product/RBAC review must confirm whether same-unit-only is the intended rule, whether managers without a `staff_id` should participate, and whether a future direct-message `Feature` must grant/deny access by canonical role.

## Required disposable-db review before any apply

Offline tests assert source-level contracts only. They are not proof of deployed Postgres/RLS behavior. Before any reviewed migration application, use a **disposable local Supabase/Postgres fixture** (never customer data) to prove:

1. two same-unit authenticated users can list contacts, send, retry the same `client_message_id`, list only their participant rows, and mark only the recipient's row read;
2. different organisation, facility, unit, inactive staff, unlinked profile, and unknown role cannot contact, list, send, or read;
3. direct PostgREST DML is denied; forged `read_at`, content/participant edits, deletes, and audit edits fail;
4. concurrent retry submits produce one message and one `sent` audit event; and
5. a security review verifies function owner/search path/grants against the target Supabase PostgreSQL version.

No live Supabase instance was contacted or migrated for this change.

## Rollback

No automatic rollback SQL is included because dropping direct-message tables destroys durable communication/audit evidence. A reviewed rollback must first export or formally retain those records according to the applicable retention policy, revoke the three RPC execute grants, remove route registration, then drop policies/functions/tables only with explicit data-owner approval.
