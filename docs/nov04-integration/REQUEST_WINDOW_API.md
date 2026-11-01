# Request-window API candidate

**Branch:** `agent/nov04-window-api-caff1c8`  
**Base:** `caff1c86c44cf97231e84f24563c1bde6f414a07`  
**Status:** local candidate only. The migration has not been applied, and the router is intentionally not yet registered in `api/main.py`.

## Purpose and security boundary

A request window controls when a staff member can submit a **DO**, **specific-duty** (`duty_request`), or **shift-swap** request. It is not an approval, roster lock, publication, or solver input. Existing approval, approved-lock, publication, and solver semantics remain unchanged.

The server performs two checks:

1. `emma_core.services.request_windows.assert_request_allowed()` calls a database RPC before the normal leave service writes, giving an honest unavailable result before any service-role insert.
2. `trg_enforce_request_window_on_leave_insert` repeats the decision in PostgreSQL using `clock_timestamp()` in the same insert transaction. Direct inserts and a window closed between the preflight and insert cannot bypass it.

The application-time interval is **`[opens_at, closes_at)`**. The requested-date interval is **`[target_start, target_end_exclusive)`**. Existing `leave_requests.date_end` remains inclusive, so a request is valid only when `date_end < target_end_exclusive`.

Missing, closed, scheduled, expired, or out-of-target-range duty windows fail closed. The endpoint and trigger intentionally **do not gate `SL`, `DSL`, `urgent`, or `late`**: those existing sick/emergency reporting paths must remain available. Ordinary leave (`AL`, `PH`, `CL`, `special`, etc.) has a `leave` window resource for display and future policy work but is not newly gated in this candidate; this avoids silently changing non-duty leave policy without a confirmed product rule.

## Authorization and scope

Every durable row carries an immutable derived organisation, facility, and optional unit scope:

- `organization_id` derives from the caller's facility; it is never accepted from the request body.
- `facility_id` derives from the authenticated profile; it is never accepted from the request body.
- `scope: "facility"` covers the facility. `scope: "unit"` requires a unit in that same facility and overrides the facility row for staff whose primary unit matches it.

Only canonical `OWNER` and legacy `superintendent` administer windows. This is the current verified mapping: `normalise_role("superintendent") == OWNER`. `deputy` is **not** a known canonical or legacy database role in the base branch, so it fails closed. A data/RBAC mapping for the named NAAC deputy is required before claiming the CEO's “superintendent + deputy” operating intent is fully covered. Frontline and all other roles cannot create or patch a window or choose their own scope.

The migration makes both window tables RLS tenant-scoped and direct-write read-only for `authenticated`. Owners/superintendents can read their facility's windows and audit; a non-owner can read the facility window plus only the row for their own primary unit, and cannot read audit. Management writes use security-definer RPCs that repeat the facility, role, unit, and organisation checks. Audit rows are append-only.

## Routes

The parent integration owner must add the following import and include to `emma-ai-app/api/main.py` after reviewing the migration:

```python
from api.routers import request_windows as _request_windows
# append _request_windows to the app.include_router(...) module tuple
```

### `GET /request-windows`

An owner/superintendent receives durable rows for their own facility/organisation. A non-owner receives the facility row plus only the window for their own primary unit; sibling-unit rows and audit are not enumerated.

```json
{
  "server_now": "2026-11-01T01:00:00.000000+00:00",
  "windows": [
    {
      "id": "uuid",
      "organization_id": "uuid",
      "facility_id": "uuid",
      "unit_id": null,
      "kind": "duty",
      "scope": "facility",
      "state": "open",
      "opens_at": "2026-11-01T00:00:00+00:00",
      "closes_at": "2026-11-03T00:00:00+00:00",
      "target_start": "2026-11-10",
      "target_end_exclusive": "2026-12-01",
      "version": 1,
      "status": "open",
      "server_now": "2026-11-01T01:00:00+00:00"
    }
  ]
}
```

`status` is calculated from DB time, not API-host time.

### `POST /request-windows`

OWNER/superintendent only. `idempotency_key` is required and unique per facility. Repeating the identical request returns the original row; reuse with changed content returns a conflict.

```json
{
  "kind": "duty",
  "scope": "unit",
  "unit_id": "uuid",
  "state": "open",
  "opens_at": "2026-11-01T09:00:00+08:00",
  "closes_at": "2026-11-03T17:00:00+08:00",
  "target_start": "2026-11-10",
  "target_end_exclusive": "2026-12-01",
  "idempotency_key": "manager-ui-request-uuid-or-random-key",
  "reason": "November collection cycle"
}
```

`target_end` is accepted as an input alias during migration, but its semantics are still exclusive and responses use `target_end_exclusive`.

### `PATCH /request-windows/{id}`

OWNER/superintendent only. Supply the last read `version` plus one or more changed fields. The RPC locks the row, compares the version, increments it, and writes an append-only audit record. A stale write returns `409` with `request_window_conflict`; the UI must refresh rather than overwrite.

```json
{
  "version": 1,
  "state": "closed",
  "reason": "Collection cycle closed"
}
```

Timestamp fields must include an offset. Partial updates are merged and revalidated as a complete window in the database.

### `GET /me/request-window?kind=duty|leave`

The Staff PWA route. It resolves the caller's own linked staff unit and returns the unit row if present, otherwise the facility row.

```json
{
  "kind": "duty",
  "available": true,
  "status": "open",
  "reason": null,
  "server_now": "2026-11-01T01:00:00+00:00",
  "window": { "id": "uuid", "target_end_exclusive": "2026-12-01" }
}
```

For `kind=leave`, the response is display-ready but does not imply the existing ordinary-leave create route is gated.

### Compatibility alias: `GET /request-windows/duty`

The currently inspected Staff PWA source (`client/src/lib/api.ts`) calls this older path and expects flat fields: `enabled`, `opens_at`, `closes_at`, `target_start`, `target_end`, and `status`. The candidate retains a **read-only** alias with that shape. Its `target_end` is now **exclusive**.

The PWA owner should move to `/me/request-window?kind=duty`, update `DutyRequestWindow` to use `target_end_exclusive`, and change the date check in `RecordsPage.tsx` from `end <= target_end` to `end < target_end_exclusive`. Until then, the server remains authoritative and rejects the otherwise enabled final exclusive date; the client must not report it as saved on failure.

## Migration, rollout, and rollback

Migration: `emma-ai-app/supabase/migrations/20261031000200_request_windows.sql`.

It creates `request_windows`, `request_window_audit`, RLS policies, durable idempotent/CAS RPCs, and the **BEFORE INSERT** leave trigger. It does not update or revalidate existing `leave_requests`, so historical and approved records are retained. It must be reviewed and executed only against the confirmed target database with a backup and real-token RLS test; no such execution happened in this work package.

Safe rollback is operational, not a blind table drop: first disable/remove `trg_enforce_request_window_on_leave_insert` only under a reviewed release decision, then remove the route registration, revoke RPC grants, and only later retire the tables/functions after retention requirements are satisfied. Do not drop `request_window_audit` as an application rollback action: it is evidence. A missing migration/RPC fails the service preflight closed for duty/DO, producing an unavailable response rather than a fake accepted request.

## Known runtime blockers

- No confirmed Supabase project/database credentials are available in this worktree, so SQL was not applied and DB/RLS/trigger concurrency tests have not run.
- `api/main.py` is parent-owned and still needs the one explicit router registration above.
- The current database has no verified deputy role mapping or organisation-level administrator policy. The candidate deliberately permits only the existing OWNER/superintendent mapping and only facility/unit administration.
- Staff PWA source uses the legacy inclusive `target_end` UI contract and needs the documented type/condition update before hosted UAT.
