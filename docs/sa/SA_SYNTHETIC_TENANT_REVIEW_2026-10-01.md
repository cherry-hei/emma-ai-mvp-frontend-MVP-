# SA synthetic tenant — rename/configuration review, not a migration approval

**Status:** review only · 1 October 2026 · **no deployment, no real data**

## Current evidence

| Check | Repository state at `698b981` | Decision |
|---|---|---|
| NAAC | `NAAC` organisation + `NAAC` facility, 277 duty / 59 task / 18 escort codes in shipped dictionaries, provisional units and active list | Synthetic M1 only; customer confirmation outstanding |
| SA-style home | `ORG_A` organisation, `A` facility, `Care Home A (救世軍式)` profile with 11 shift codes and two invented wings; existing synthetic superintendent account | **SA-style fixture**, not proven final SA account, final SA codes or client-approved facility structure |
| Isolation | Earlier live audit: NAAC and Home A distinct org/facility/dictionary IDs and cross-roster read empty; repository tests cover reads and NAAC→A write | Must rerun with authenticated NAAC and SA-style users after any name/config migration |
| Physical DB | Multi-organisation tables share one DB and RLS restricts access | Do not say there are two physical databases; contract/security owner decides if necessary |

## Required customer / engineer decisions

1. Confirm **which SA centre** will pilot and its legal/public display name; Home A is currently a generic synthetic fixture.
2. Confirm actual SA active duty/task codes, ranks, units, employment types and exceptions; do not silently re-label 11 synthetic codes as approved SA configuration.
3. Confirm whether `ORG_A` and facility `A` should be **retained as immutable internal IDs/codes** and only the user-facing names updated, or a new SA organisation/tenant created. Kien must document foreign-key, users_profile, audit, roster and rollback effects before choosing.
4. Confirm synthetic manager/staff counts and precise permissions using NAAC/SA Role Permission Matrix; never create real staff identities on the current stack.

## Recommended minimal migration after those confirmations

- Preserve current `org_id`, `facility_id`, roster history, audit trail and Home B fixture; change display names only if SA approves the wording. Keep a clearly visible **synthetic / provisional** badge on any trial UI. Do not change `code`/primary key just to make a nicer label.
- If SA's confirmed code list is materially different, import/diff it as a separate reviewed configuration PR using the reusable importer, not a rename of NAAC dictionaries.
- Preflight must compare the expected `ORG_A`/`A` rows and null counts; abort if IDs, expected names or tenant ownership differ. Migration and rollback must be reviewed by Kien; **no agent applies it**.
- Re-run: NAAC↔SA organisation/facility/staff/roster/dictionary read isolation **both directions**; cross-tenant writes rejected **both directions**; authenticating as a manager/staff resolves only one's own facility; dictionary display, CRUD/audit, Care Home B 34/31/3 regression unaffected.

**5 October no-go:** if SA has not confirmed the final codes/roles/name, use the existing Care Home A as a *SA-workflow-inspired synthetic demonstration*, not a customer-configured SA trial. Do not rename and imply validation that did not occur.
