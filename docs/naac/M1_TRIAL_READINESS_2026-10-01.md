# M1 / NAAC and SA-style synthetic trial — evidence & known limitations

**As of 1 October 2026 · commit `698b981` on remote `main` · not final M1 acceptance**

| M1 item | Evidence | Remaining check |
|---|---|---|
| A.1 organisation schema/RLS | Commit `698b981`; Sep 24 audit observed NAAC vs Home A unique organisation/facility IDs, cross-roster read empty | Review additional dictionary null-facility RLS case; this PR proposes a fix, not deployed or live-tested |
| A.3 organisation-scoped retrieval | Separate shift/task/escort dictionary IDs and scoped roster in Sep 24 audit | Re-run NAAC↔SA read and write RLS on the current deployed version and after reviewed migration |
| A.2 NAAC code import | 277 shift, 59 task and 18 escort definitions, six invented staff and five synthetic logins in Sep 24 audit | NAAC active/exception/rank/unit confirmation, import diff and final customer sign-off outstanding |
| NAAC roster | 42 days / six synthetic people / 252 cells in Sep 24 audit | Add following synthetic period; NAAC ESL test then returned five candidates, **none compliant** because of missing following period |
| Trial/UAT guide | A newly supplied engineering UAT guide exists | Remove embedded shared password; reconcile its five M1 tests with requested Emergency SL readiness and run against current deployment |
| Tests & CI | Deploy workflow `35721064048` succeeded for commit `698b981` | It did **not** run pytest. This PR adds *offline-only* PR checks, not database-backed RLS/ESL acceptance. Existing no-secret test errors from prior audit need targeted resolution |
| SA-style fixture | Home A carries 11 SA-style shift codes | `ORG_A` / `A` are generic fixture identifiers, not verified customer-configured SA tenant. SA final codes, units, roles, account counts and name require confirmation |

## Supported 5 October demonstration

- NAAC: synthetic login, scoped roster, simple create/edit/audit, request to manager, rule check and report download **if re-verified**; active codes and Emergency SL remain provisional until specifically closed.
- SA: only **SA-workflow-inspired synthetic fixture** until final codes, identity and roles are confirmed. Do not claim a real SA pilot or final SA tenant.
- M2 named special events and approved-leave auto-fill, M3 NAAC 18-sheet export, live AI and M4+M5 real-data gate are **separate** and not silently included.
- No real NGO staff, rosters, credentials or resident data in current overseas-stack or Codex. Only invented users and synthetic examples. Do not send raw account passwords in a shared guide.

## Required Kien return (with links/evidence, not just 'done')

1. Date and diff for confirmed NAAC codes/exceptions/ranks/units; mark external dependency if customer hasn't returned.
2. Following synthetic period and one NAAC Emergency SL fixture with at least one compliant candidate, or explicit note that this remains trial-blocking outside the contractual five UAT cases.
3. Safe UAT guide (no shared password), known limitations, actual CI no-secret pytest output, and an authenticated local/synthetic DB RLS test for NAAC↔SA in both directions after the reviewed migration.
4. Confirm whether Care Home A is intended to become SA's synthetic tenant; list actual `org_id`/`facility_id` in a private engineer-to-owner handoff, code dictionary counts/source, synthetic manager/staff roles/count, and latest read/write isolation run.

**Acceptance rule:** Cherry/Management records contract M1 acceptance separately from customer trial readiness. An AWS deploy success or an offline CI green check alone is neither of them.
