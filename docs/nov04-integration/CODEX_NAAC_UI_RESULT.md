# Codex NAAC UI result — candidate only

Branch before editing: `agent/nov04-naac-rbac-ui`.
Source commit: `d0ff7b9aa9d17fea003a39bff0b326ef288108d8`.
No commit or push performed. Existing untracked CODEX_NAAC_UI_TASK.md preserved unchanged.

Changed files owned by this task:

- src/lib/naac-ui-policy.ts — isolated exact four-role/12-action policy; unknown denied; no aliases.
- src/lib/naac-ui-policy.test.mjs — full matrix, unknown identities/actions, scopes and existing route-guard assertions.
- src/app/naac-access-preview/page.tsx — static EN/zh owner review with role selector and disabled operations.
- src/components/layout/navRoutes.ts — only preview route and facility.settings mapping added.
- package.json — only test:naac-ui script added.
- docs/nov04-integration/NAAC_UI_DESIGN.md — matrix, intended UI, boundaries and rollout/rollback.
- docs/nov04-integration/CODEX_NAAC_UI_RESULT.md — this evidence record.

Verification:

- `npm run test:naac-ui`: passed, runner reports 1 test-file unit, zero failures.
- `node --experimental-strip-types src/lib/naac-ui-policy.test.mjs`: 7 individual tests passed, zero failures (including all 48 role/action cells). Node emits its existing typeless-package module warning; package module mode was not changed.
- `npm run test:ui`: 10 test-file units passed, zero failures. This environment's runner reports files rather than individual nested cases.
- `npm run typecheck`: failed to start compiler, exit 127, `tsc: not found`; no node_modules installed. No dependency installation performed.
- `git diff --check`: passed. Reviewed tracked diff: two route lines and one package script only.
- Inspected newly authored source and searched it for network/storage/env/secret-key patterns: no matches. No uploads, raw rosters, credentials or secrets accessed. No external assets/providers, purchases or API-key billing used.

Evidence is offline pure policy and source assertions only. Build not run because compiler/dependencies are unavailable. No browser runtime, 200% zoom, screenshot, live auth, DB/RLS or multi-user acceptance claimed. Preview is not wired to current NAAC identities or operational modules. Existing auth/AppShell/permissions, API/backend, PWA and cloud unchanged. Staff PWA requests/chat merely described, never called.

Feature boundary: current facility.settings guard controls entry; preview role selection is local component state and changes no signed-in permission. All operation controls remain disabled. Candidate policy requires explicit future identity binding and server-side organisation/facility/unit RBAC/RLS before rollout. Independent presentation/interaction review and installed-dependency typecheck/build remain open blockers. No live release authorised.

Rollback: remove the new task files and revert only this task's two navRoutes entries and one package script. Preserve pre-existing task brief and unrelated work. No migration/data rollback required.
