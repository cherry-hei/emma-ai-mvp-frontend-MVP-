# Codex Staff PWA Monorepo — Independent QA

**Verification date:** 2026-11-01 09:04–09:07 UTC  
**Candidate path:** `/home/ubuntu/emma-nov01-domain/repo`  
**Requested branch:** `agent/nov04-domain-staff-monorepo`  
**Stated base:** `6bcb10e`  
**Method:** Read-only source inspection and requested local-command attempts only. No browser, API, database, authentication, records, migrations, deployment, DNS, account, or network-service activity was performed.

## Result summary

| Area | Independent result | Notes |
|---|---|---|
| PWA `pnpm check` | **BLOCKED — not started** | Execution wrapper rejected the supplied nested-app working directory before shell startup. |
| PWA `pnpm test` | **BLOCKED — not started** | Same wrapper blocker; no Vitest process or result. |
| PWA `pnpm build` | **BLOCKED — not started** | Same wrapper blocker; no Vite build process or result. |
| Root `npm run test:ui` | **BLOCKED — not started** | Execution wrapper rejected the supplied repository-root directory before shell startup. |
| Root `npm run build` | **BLOCKED — not started** | Same wrapper blocker; no root typecheck or Next build process or result. |
| Static PWA/backend contract review | **PASS, bounded static evidence** | Message and request-window field names/routes inspected against local backend source; details below. |
| Dockerfile unchanged | **PASS** | SHA-256 of base and current Dockerfile match: `b9cd21ddf2373c4b99e8e2fa1c206c735bcb0cf456c6eab0b13e51062e7c45cf`. |
| Root exclusion of nested app | **PASS** | Current root `tsconfig.json` adds only `"staff-pwa"` to the existing `exclude` array. |
| Exact source provenance `689aea2` | **NOT INDEPENDENTLY VERIFIABLE** | Commit `689aea2` is unavailable in this repository object database; the PWA is an untracked directory, not a nested Git worktree. |

**Overall QA disposition:** **Not a runnable acceptance pass.** No critical static field-name/gating contradiction was found in this focused review, but the five required check/test/build commands did not start and the claimed exact-source provenance cannot be independently compared in this worktree.

## Candidate/worktree identity

`HEAD` and the merge base with `6bcb10e` both resolve to `6bcb10e4a20206044fb73bef881a394b0f5f62c6`. The candidate is therefore present as uncommitted worktree content: `staff-pwa/` is untracked and root `tsconfig.json` is modified (along with integration documentation). This report evaluates that current worktree content only; it does not represent a committed branch-to-base diff.

The source worktree changed concurrently during this read-only QA pass: the final status also showed a modified `AGENTS.md` and additional untracked integration documentation. Those later concurrent changes were not evaluated as part of this focused PWA review. QA wrote only the artifacts under `/home/ubuntu/emma-nov01-domain/reports`; it did not modify candidate source, dependencies, lockfiles, migrations, configuration, workflows, or runtime assets.

The root Dockerfile has no content diff from `6bcb10e`; the identical SHA-256 above confirms this. The root `tsconfig.json` change is exactly:

```diff
-  "exclude": ["node_modules"]
+  "exclude": ["node_modules", "staff-pwa"]
```

That isolates the nested Vite PWA from the root Next/TypeScript project while the nested `staff-pwa/tsconfig.json` independently includes `client/src/**/*` and uses `strict: true`.

## Required command attempts

Each command was issued with the correct candidate directory supplied as its working directory. Every attempt was rejected by the execution wrapper **before shell startup**, so no command emitted an exit code and none may be counted as a pass or failure of project code.

| Requested command | Supplied directory | Outcome |
|---|---|---|
| `pnpm check` | `repo/staff-pwa` | Not started |
| `pnpm test` | `repo/staff-pwa` | Not started |
| `pnpm build` | `repo/staff-pwa` | Not started |
| `npm run test:ui` | `repo` | Not started |
| `npm run build` | `repo` | Not started |

Exact wrapper blocker in every case:

```text
terminal:the current working directory may not be the webdev project directory, please cd into the webdev directory to run the command
```

I did not bypass that restriction or run equivalent commands from an alternate directory. Per-command records are retained beside this report:

- `Monorepo_Independent_QA_pwa_check.log`
- `Monorepo_Independent_QA_pwa_test.log`
- `Monorepo_Independent_QA_pwa_build.log`
- `Monorepo_Independent_QA_root_test-ui.log`
- `Monorepo_Independent_QA_root_build.log`

Source-level inventory only (not execution results): the PWA has **5** `*.test.ts` files and **32** lexical `it`/`test` declarations (one is parameterized with `it.each`); root `test:ui` invokes **10** test files containing **50** lexical test declarations.

## Focused static contract findings

### 1. Message API names and durable retry behavior — consistent

The PWA implementation uses the local backend’s concrete routes and field names:

- Contacts: `GET /messages/contacts` with `id`, `display_name`, `role`, optional `staff_id`.
- List: `GET /messages` with matching `peer`, `before`, and `limit` query names.
- Send: `POST /messages` with `recipient_profile_id`, `body`, and `client_message_id`.
- Read receipt: `PATCH /messages/{id}/read`.
- Durable response fields: `id`, `sender_profile_id`, `recipient_profile_id`, `body`, `created_at`, and nullable `read_at`.

These names match `api/routers/messages.py` and `emma_core/services/messages.py`. The backend explicitly expects `recipient_profile_id`, `body`, and optional `client_message_id`; it returns the same durable row fields. The PWA rejects malformed/non-durable send responses and checks that the returned recipient and body match the attempted send.

Static retry/session safeguards are present:

- A failed direct-message send retains the exact per-recipient `{ body, key }` attempt; a retry with unchanged content reuses `client_message_id`.
- Edits, another recipient, or a credential-generation change create a new key; `advanceCredentialGeneration()` clears retained attempts.
- Requests carry a credential-generation snapshot. Late responses after logout/new login are rejected; refresh coalescing is keyed to the complete credential snapshot.
- On `401`, a request refreshes at most once and retries under the **original** credential generation; it cannot replay a stale mutation into a newly logged-in account.
- Login removes prior stored access/refresh/expiry/user data before starting a replacement login and verifies `/auth/me` before persisting the new session.

The static PWA tests specifically cover per-recipient retry-key/content preservation, key rotation on edits/session changes, stale-response rejection, failed/new-login isolation, and delayed refresh behavior. They were **not run** due to the blocker above.

### 2. Request-window field names and default release gate — consistent and closed by default

`getDutyRequestWindow()` calls `GET /me/request-window?kind=duty` and validates the backend response shape `available`, `status`, and `window`, with `target_start`, `target_end_exclusive`, `opens_at`, and `closes_at`. The PWA converts the backend’s exclusive end date to its inclusive date-control end. This aligns with `api/routers/request_windows.py` and `emma_core/services/request_windows.py`, whose `my_window(..., kind="duty")` returns the availability response from the request-window service.

Both candidate feature gates are literal `false` defaults in `client/src/lib/features.ts`:

- `directMessages.available: false`
- `dutyRequestWindow.available: false`

No environment or role toggle was found that enables either gate. The affected API helpers fail before their candidate network calls when a gate is false. The Report/Records UI disables the duty/day-off/duty-request/shift-swap choices, and Roster displays the related capability as unavailable.

### 3. Draft preservation and confirmation semantics — static evidence supports expected behavior

For `ReportPage`, `submitted` is set only after `await submitLeaveRequest(...)` resolves. In the error path, the form state is not cleared; it shows an error and leaves entered values intact. The form is disabled only while the submission is in progress.

For `RecordsPage`, it closes the form and clears the reason only after the submission resolves, then reloads server data. Its failure path reports the error and does not clear or close the form. The PWA submission helper itself accepts success only when the returned row includes an `id`, exact submitted dates, and `status === "pending"`; otherwise it throws rather than displaying success.

### 4. No fake approval / no automatic approval found in the bounded PWA pass

The PWA does not include a client call to the backend’s final leave-decision endpoint (`PATCH /leave-requests/{request_id}`) or recommendation endpoints. Its visible language distinguishes submission/pending review from approval (for example, “提交不等於批准”). Records call out that only an approved request becomes a hard constraint.

The replacement-offer UI sends a response to an offer but states that an accepted offer has been sent for manager approval and is not automatically added to the roster. The backend route comment and implementation likewise distinguish offer response from manager commitment.

### 5. No direct-message composer is implemented in the current UI

The direct-message API helpers exist behind the false `directMessages` gate, but no `sendDirectMessage`, `listDirectMessages`, `listMessageContacts`, or `markDirectMessageRead` consumer was found outside `client/src/lib/api.ts`. `MessagesPage` shows an unavailable notice rather than contacts, thread, or composer controls.

## Limits and follow-up required

1. Re-run the five requested commands in an authorized execution context that recognizes this existing repository and nested PWA directory. Record actual process exit codes and runner/build totals before promotion.
2. Make the candidate changes committed or otherwise provide the source object containing `689aea2` if exact-source provenance must be independently verified.
3. This was deliberately not a live acceptance test. Backend registration/deployment state, CORS, authentication/RLS, migrations/RPC availability, and real-record behavior remain unverified.

## Independent versus self-reports

This report does **not** adopt Codex’s reported client/backend/PWA/root test or type-check results. The static observations and the command-attempt blockers above are independent; all runnable test/build outcomes remain unverified in this environment.

## Parent provenance supplement — 17:09 HKT

After this reviewer report, the parent used the original separate authorised Staff source repository at /home/ubuntu/emma-oct31-chat-window/staff-source to access exact commit689aea230b570b4bde915b8d377f6ac46048ddbc. SHA-256 comparison of every105 original tracked file against staff-pwa/ found102 unchanged, zero missing, and exactly3 intentional differences: api.ts, features.ts and ReportPage.tsx. Two candidate contract tests are added. Staff_Source_Provenance.json holds this separate check. This resolves source-copy lineage for the parent; it does not alter the reviewer's historical inability to resolve that cross-repository object, and does NOT supply any runnable test/build result.
