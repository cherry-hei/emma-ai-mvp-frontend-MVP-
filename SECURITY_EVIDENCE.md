# Security & compliance evidence checklist

Spec 1.6. The register lives in `evidence_items` (`GET /evidence-items`,
exported by `POST /reports/evidence`), which returns the caveats below alongside
the items so an exported pack cannot lose them.

## Wording that must travel with the claims

These are not disclaimers added at the end; they are the limits of what the
engineering evidence supports.

- Deletion requests are handled per PDPO, **subject to legal, HR, SWD-audit and
  statutory record-keeping obligations**. Deletion is not unconditional.
- A **7-year** audit retention period is **proposed** and requires client/legal
  confirmation.
- AI features run through an approved provider behind a controlled API gateway.
  **No vendor is fixed** at this stage.
- Transport security is **TLS 1.2 minimum, TLS 1.3 where supported**.
- SRAA or third-party security review is available **if required**. Emma AI is
  **not asserted to be critical infrastructure**.
- These are the engineering team's **technical** test results. Formal legal or
  security certification requires an **external qualified reviewer**.

## Platform controls

| Ref | Category | Control | Test method | Evidence | Status |
|---|---|---|---|---|---|
| EV-01 | RBAC | Role permission matrix enforced on read *and* write paths, final approval reserved to OWNER | pytest: the matrix is asserted cell-by-cell against the signed definition; guarded endpoints reject non-permitted roles over HTTP | `tests/test_mvp_rbac.py`, `tests/test_phase5_api_security.py` | pass |
| EV-02 | Isolation | Facility isolation (row-level security) | pytest: a Home A token cannot read or write Home B rows | `tests/test_rls_isolation.py` | pass |
| EV-03 | Audit | Append-only audit log with before/after and actor | pytest: UPDATE/DELETE on `audit_logs` rejected; `GET /audit-logs` returns the trail | `tests/test_mvp_foundation.py` | pass |
| EV-04 | Rules | SWD staffing-ratio and hard-constraint fixtures | pytest: minute-level ratio and every hard constraint against fixtures | `tests/test_phase5_compliance.py`, `tests/test_phase5_validation.py` | pass |
| EV-05 | API | API test report | pytest over the documented OpenAPI surface | `tests/test_api.py` | pass |
| EV-06 | Rules | Roster import validation summary | pytest: both homes' real layouts parse; unresolved cells reported against their source cell | `tests/test_mvp_import.py`, `import_issues` | pass |
| EV-07 | Security | OWASP ZAP baseline scan | ZAP baseline against the deployed API | — | **pending** |
| EV-08 | Backup | Backup and restore drill | Restore a PITR snapshot into a scratch project and run the suite against it | — | **pending** |
| EV-09 | AI | AI prompt masking sample | Prompt log review: no names, HKIDs or phone numbers leave the boundary | — | not applicable (no AI layer ships in the MVP) |
| EV-10 | Security | Transport security configuration | TLS configuration review of the deployed endpoints | — | **pending** |
| EV-11 | Audit | PDPO retention and deletion boundary | Written retention policy reviewed against HR, SWD-audit and statutory duties | — | **pending**, external review required |

## Per-facility sign-off

Seeded for each home and writable by its superintendent
(`PATCH /evidence-items/{code}`):

| Ref | Control | Owner |
|---|---|---|
| EV-F1 | Facility rule profile reviewed by the RN advisor | Superintendent |
| EV-F2 | User permission matrix signed off for this home | Superintendent |
| EV-F3 | Resident-count source of truth confirmed | Superintendent |

EV-F3 matters more than its position suggests: the resident count is the
denominator of every statutory ratio, and a wrong count invalidates every ratio
result computed from it.

## Role permission matrix

Authority: *Emma AI — RBAC Definition for Implementation (Salvation Army × NAAC)*,
30 Jul 2026. The definition is transcribed into `emma_core/permissions.py` and
re-transcribed independently into `tests/test_mvp_rbac.py`, so this table, the
enforcement code and the tests cannot drift apart silently.

Each NGO's real job titles map onto these seven roles in facility config —
院長/副院長 and 主任/副主任 are both OWNER — so admitting a third home adds a
mapping, not a code path.

| Role | Roster read | Roster draft | Publish | Import | Leave **recommend** | Leave **decide** | Reports | ROI | Audit log | Config |
|---|---|---|---|---|---|---|---|---|---|---|
| OWNER | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| NURSE_MGR | ✓ | ✓ | — | — | ✓ | — | read | — | — | — |
| ALLIED_HEALTH | ✓ | — | — | — | — | — | — | — | — | — |
| ADMIN_CLERK | ✓ | — | ✓ | — | ✓ | — | read + download | — | — | — |
| SCHEDULER † | ✓ | ✓ | — | ✓ | — | — | read | — | — | — |
| FRONTLINE | own rows only | — | — | — | — | — | — | — | — | — |
| HR_AUDITOR † | ✓ | — | — | — | — | — | read | — | read | — |

**Recommend is not approve.** NURSE_MGR, ADMIN_CLERK and ALLIED_HEALTH may attach
a suggest-approve/suggest-reject with a reason as a first-pass review; the final
decision is OWNER-only and the approve endpoint returns 403 to every other role
(`tests/test_mvp_rbac.py::test_owner_is_the_only_role_that_can_decide`). An
approval record therefore carries a recommendation part, writable by the review
roles, and a final-decision part writable only by OWNER.

† SCHEDULER and HR_AUDITOR are defined in the source document's role table but
have no feature-matrix columns in it. Their rows above are **derived from the role
definitions and await client confirmation**; both were resolved towards *less*
access than more.

Every row is additionally scoped to one facility by row-level security, so the
table above describes what a role may do *within its own home*.
