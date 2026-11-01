# NAAC UI candidate design

Source branch: `agent/nov04-naac-rbac-ui`. Source commit before edits: `d0ff7b9aa9d17fea003a39bff0b326ef288108d8`. Authority: CODEX_NAAC_UI_TASK.md and its confirmed 12-action matrix. This is a review-only candidate, not live NAAC role binding.

| Action | Superintendent | Appointed deputy (SW1) | Nurse | Staff |
| --- | --- | --- | --- | --- |
| Personal view | Yes | Yes | Yes | Yes |
| Unit view | Yes | Yes | Yes | Yes |
| Organisation view | Yes | Yes | No | No |
| Batch generation | Yes | Yes | No | No |
| Rules dictionary | Yes | Yes | No | No |
| Preliminary review | Yes | Yes | No | No |
| Reports / Excel | Yes | Yes | No | No |
| Audit | Yes | Yes | No | No |
| Staff role / qualification management | Yes | Yes | No | No |
| Draft shift edit | Yes | Yes | Own unit | No |
| Final decision | Yes | No | No | No |
| Publish | Yes | No | No | No |

Policy accepts exact future identity identifiers only: superintendent, appointed_deputy, nurse, staff. Unknown identifiers and actions deny. No job-title inference, canonical-role mapping, facility-to-NAAC assumption or changes to global permissions. Organisation scope applies only to superintendent/deputy; nurse/staff remain personal/unit scoped. The helper describes policy, not row-level authorisation; future integration must enforce assigned organisation/facility/unit and effective appointment server-side.

Direct preview URL: `/naac-access-preview`. Existing AppShell and facility.settings permission guard entry, currently global OWNER only through existing normalisation. Preview identity selection never reads or changes the signed-in identity. No sidebar change. All operation buttons are disabled even when the selected future policy allows the action. Denied modules appear as labelled review inventory; intended operational interfaces hide them. Staff requests/chat remain in Staff PWA with no links or fake calls here.

Uses existing language context, rounded white cards, pink accent, minimum base 16px text, wrapping single-column layout at narrow widths and native labelled selector. EN/zh controls and explicit bilingual preview warning. 200% zoom and visual acceptance still require browser review.

No salary, cost, history, ROI, financial compliance, invitation or additional administration grant. No customer data, requests, persistence or writes. Existing backend/auth/PWA/cloud remain untouched. Rollout needs explicit deployment identity binding, backend RBAC/RLS and scope validation, independent review and exact-SHA release approval. Rollback removes this candidate's new files, two route-registration lines and added test script; no data rollback is needed.
