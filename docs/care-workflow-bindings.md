# Care Home A / B workflow binding

Implementation branch: `fix/care-home-workflows-20261111`, based on
`942a6e3126510d5ed3ddfff7db61da5480353a43`. This document describes source changes,
not an applied production configuration or a live-account acceptance result.

## What the binding means

Care Home A is the SA workflow and Care Home B is the NAAC workflow. These are
reviewed presentation assignments to immutable organisation, facility and account
IDs. They are never inferred from an email, display name, hostname, rank or title.

The existing source has three distinct profiles: A / `ORG_A` (SA-style, 28 days),
B / `ORG_B` (generic multi-floor, 31 days), and `NAAC` (42 days). Existing generic
B is not the NAAC tenant. This patch neither renames B nor moves its staff,
accounts, codes or rosters. To present the existing NAAC tenant as Care Home B,
Kien must bind its actual immutable IDs after confirming the target environment.
Moving generic B data into NAAC would be a separate reviewed migration.

## Server configuration

`CARE_WORKFLOW_BINDINGS_JSON` belongs only on the FastAPI server. Do not put it in
`NEXT_PUBLIC_*`, `VITE_*`, frontend source, shared chat, or an editable facility
configuration record. It contains deployment-controlled appointments, not passwords.

Empty, invalid, missing or mismatched bindings deny operational HTTP routes.
Login, refresh and `/auth/me` remain available to report `unbound` or `invalid`.
Both frontends use the resulting server metadata and fail closed on missing data.

Configuration shape (the UUIDs below are placeholders, never actual accounts):

```json
{
  "schema_version": 1,
  "bindings": [
    {
      "care_home": "A",
      "workflow": "SA",
      "org_id": "00000000-0000-4000-8000-000000000101",
      "facility_id": "00000000-0000-4000-8000-000000000102",
      "memberships": [
        {
          "profile_id": "00000000-0000-4000-8000-000000000103",
          "auth_user_id": "00000000-0000-4000-8000-000000000104",
          "expected_system_role": "OWNER",
          "workflow_role": "OWNER",
          "staff_id": null,
          "unit_ids": []
        }
      ]
    },
    {
      "care_home": "B",
      "workflow": "NAAC",
      "org_id": "00000000-0000-4000-8000-000000000201",
      "facility_id": "00000000-0000-4000-8000-000000000202",
      "memberships": [
        {
          "profile_id": "00000000-0000-4000-8000-000000000203",
          "auth_user_id": "00000000-0000-4000-8000-000000000204",
          "expected_system_role": "OWNER",
          "workflow_role": "director",
          "staff_id": null,
          "unit_ids": []
        }
      ]
    }
  ]
}
```

A and B must use distinct organisation IDs, facility IDs, profile IDs and login
identities. The current application has no reviewed multi-membership selector.
Authentication rejects more than one matching profile rather than choosing the
first. Profile, auth-user and expected canonical role must all match. A configured
staff ID must match the current profile. Duplicate appointments are invalid.

| Workflow appointment | Required canonical role | Operational scope |
| --- | --- | --- |
| SA | Same canonical role string in both role fields | Existing SA matrix |
| NAAC `director` / 主任 | `OWNER` | Bound facility; final decisions and publication |
| NAAC `deputy` / explicitly appointed 副主任 | `OWNER` | Bound facility; preparation/recommendation, no final decisions/publication |
| NAAC `nurse` / 護士 | `NURSE_MGR` | Exact staff record plus explicit units; create/edit manual draft cells and their task timings |
| NAAC `staff` / 員工 | `FRONTLINE` | Exact staff record; own requests/profile and published own/unit roster |

Legacy DB role spellings are normalized for comparison; a job title is never used
to grant deputy authority. Nurses require an exact staff ID and at least one unit
ID. Staff require an exact staff ID; unit roster stays unavailable without explicit
unit membership. Granting a unit does not grant other facilities in the same NGO.

## Operational profile checks

After immutable identity matching, A must still refer to the existing `A` facility
profile with 28-day cycles. B must refer to the actual `NAAC` facility profile with
42-day cycles. These are additional consistency checks, not identity inference.

For NAAC, the authenticated server read also checks:

- One active `scheduling_cycle` configuration equal to `{"cycle_type":"42day","days":42,"weeks":6}`.
- Active hard `shift_sequence` and `night_chain` definitions; the sequence limit
  is positive and at most eight working days, its before/after/consecutive clauses
  are present, and the night chain contains NAAC's `NO` sleeping and `O` off codes.
- The bound organisation's duty dictionary contains `A7`, `N10`, `NO` and `O`.

A failed or unavailable check returns `invalid` with all authority removed. This
is a bounded configuration presence/shape check. It does not certify every NAAC
rule, active-code correction, workbook mapping, quota, real roster or unresolved
staffing requirement. Those remain release acceptance items. No fingerprint of
all rules is taken and routine edits do not require a new hash.

New periods use the selected workflow's inclusive length and code: 28 / `28day`
for SA, 42 / `42day` for NAAC. Existing historical `6week` labels are not rewritten.

## API and UI behavior

`/auth/me`, login and refresh return `care_workflow`: status, A/B designation,
SA/NAAC workflow, explicit appointment label, org/facility/unit IDs, feature
permissions, roster scope and action booleans. Both frontends verify session scope
and consume this metadata rather than maintaining separate NAAC role rules.

The canonical SA role table remains intact. The registered roster API now checks
manual edit, delete, generation, batch and publication separately. The old literal
allowlist admitting `admin` and `scheduler` to publication is removed. The NAAC
deputy cannot inherit final authority merely because its legacy base role is OWNER.
Only draft manual versions can be edited; published, archived or unknown states
are refused. Explicit version reads must match both facility and period.

NAAC nurse manual-cell and task-timing operations resolve the target staff member
inside the bound home and appointed units. Task hydration requires an exact
shift assignment, not a facility-wide task list. Leave creation on behalf of
someone else requires final approver authority; other users can submit only their
own request. Recommendations and final decisions remain separate actions.

The new `/me/unit-roster` is read-only and published-only. With no arguments it
selects the latest published version in the bound home; optional `period_id` and
`version_id` are both enforced. It verifies unit ownership, filters output to own
and appointed-unit staff, and removes facility event overlays. The payload includes
its real period/version/dates so clients do not imply it covers another month.
Existing Staff own-roster/task helpers no longer fall back to an unpublished draft.

An explicit NAAC HTTP gate closes routes not implemented for this workflow, even
if an older route only required a login. ROI and other unapproved manager features
stay closed. Existing scoped `/me` task exceptions remain available. This patch
does not claim every legacy SA endpoint has been re-audited.

## Kien's rollout and rollback checks

1. Confirm actual backend environment/API URL and immutable A/SA and NAAC tenant
   IDs. Confirm each test login's profile, staff record, canonical role and units;
   provide reset/invitation links through the approved secure channel, not shared
   passwords in the group. Confirm who is the formally appointed NAAC deputy.
2. Review the exact source commit and configuration together. Verify the active
   NAAC rule dictionary, `#` next-day obligations, 42-day export and approved
   workbook/template mapping. The source audit does not prove live provisioning.
3. Rehearse with disposable fixture accounts and real RLS tokens: A cannot read or
   write B; staff cannot read other units/drafts; nurse cannot generate/delete/
   batch/publish/final-approve; deputy cannot final-approve/publish; director can
   publish only after current hard-constraint validation succeeds.
4. Verify database policy/RPC compatibility. This patch adds no SQL migration.
   Existing `publish_roster_version` is service-role-only and still validates
   legacy creator role strings. Canonical OWNER acceptance and direct database
   RLS parity with the new API appointments require explicit verification.
   API unit filtering is not claimed to be an added database RLS policy.
5. Bind both frontends to the same approved backend/identity project, with exact
   production CORS origins. Test login/refresh/logout, manager publication to staff
   readback, leave recommendation/final decision and task exception readback.
6. Only then approve the exact release and domain switch. None of these production
   changes were executed in this task. Rollback is the previous reviewed code and
   server setting. No database migration or data rollback is introduced here.

If a binding becomes invalid, the operator corrects the reviewed deployment
configuration or underlying profile/configuration; the UI must not offer an
"ignore" or role selector that restores authority.

## Offline verification

From `emma-ai-app`:

```bash
python -m pytest tests/test_care_workflows.py tests/test_mvp_rbac_parity.py tests/test_mvp_rbac.py tests/test_mvp_launch_api.py -q
```

Result: **126 passed**: 38 workflow/HTTP/configuration tests, 4 existing SA
frontend/backend matrix-parity tests, and 84 existing offline RBAC/launch
regressions. The old positive SA fixtures now use the real resolver with explicit
synthetic UUID bindings; new unbound-denial cases remain unchanged. These tests
use memory fixtures and mocked service effects. They do not log in to or mutate a
live database. Python compile verification also passed. One installed
Starlette/httpx test-client deprecation warning remains; it did not affect these
test results. The full live database suite was not run. The repository's existing
main-push deployment workflow is unchanged and was not invoked.
