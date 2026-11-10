# Care Home A / SA, Care Home B / NAAC integration

## Decision and authority

Cherry confirmed on 11 November 2026 (HKT) that Kien's manager MVP is the existing
`emma-ai-manager-mvp` project and that Kien has already built the Staff App backend.
The separate `emma-ai-staff-pwa` frontend needs an explicit, verified connection to
that backend. She requested A = Salvation Army (SA), B = NAAC, immediate repairs
where the human approval workflow is missing, and a Lark message to Kien asking
for the two homes' account mappings.

Keep the two frontend repositories/deployments and one approved FastAPI, auth and
data contract. This allows independent manager and phone releases while giving
one authoritative place to enforce organisation, facility, unit, staff identity,
appointment, publication state and audit. A shared backend does not share browser
tokens across domains. The staff browser receives only its own authenticated API
responses; service credentials remain on the backend.

| Surface | Existing Vercel project | Intended domain | Responsibility |
| --- | --- | --- | --- |
| Manager | `emma-ai-manager-mvp` | `app.hiemmaai.com` | Rules, draft review, authorised decisions and publication |
| Staff | `emma-ai-staff-pwa` | `staff.hiemmaai.com` | Personal/published unit roster, own requests, work status and exceptions |
| API / authentication | Kien's approved FastAPI deployment | Confirm the exact existing origin | All data access, membership, validation and audit |

## What the source actually contained

Manager source was inspected at main `942a6e3126510d5ed3ddfff7db61da5480353a43`.
The deployed production record points to `b0cdb0ece3606162468656e65a23e8ff1bc69136`;
Kien's deployment remains the runtime baseline. This feature branch does not
assert that main is already deployed or approve replacing the production release.

- `emma_core/vocab.py`, seed data and facility configuration model A as an SA-style
  28-day home, generic B as a different 31-day home, and NAAC as a third profile.
  Renaming B would leave the wrong rules/data under the label.
- `/auth/me` previously exposed a broad role and facility without an explicit
  A/SA or B/NAAC workflow appointment. UI role labels used SA terminology globally.
- The registered roster router used a legacy `WRITE_ROLES` check for publication;
  it did not express a NAAC deputy's lack of final authority.
- Staff source at `689aea230b570b4bde915b8d377f6ac46048ddbc` contains real `/auth`
  and `/me` clients, but `/report` declared success without making an API request,
  and the certificate page displayed synthetic records and local-only uploads.
- Staff project environment metadata returned no entries, including zero hidden
  production entries. Its latest production attempt is `BLOCKED`; a prior READY
  preview is not runtime/backend acceptance. The blocking reason was not returned
  by the bounded build-events request.

## Implemented authority boundary

The backend resolves a server-only `CARE_WORKFLOW_BINDINGS_JSON` against exact
organisation, facility, profile and authentication-user IDs. It checks the actual
base role, staff link, explicit units and facility operational profile. A display
name, email, URL, job title or browser selection cannot select another tenant or
appoint a deputy. Missing or inconsistent configuration is denied.

The desired Care Home B presentation must bind to the reviewed NAAC facility,
whose operational code/configuration uses NAAC's 42-day cycle. The existing generic
B/31-day facility is not automatically changed, merged or transferred. If Kien
needs to move that tenant's data, prepare a separate exact migration and rollback.

| Workflow appointment | Read scope | Manual roster changes | Generate/batch | Final decision / publish |
| --- | --- | --- | --- | --- |
| NAAC 主任 | Bound facility; reviewed management features | Yes | Yes | Yes |
| NAAC explicitly appointed deputy | Bound facility; reviewed management features | Yes | Yes | No; recommendations only |
| NAAC nurse | Own/explicitly assigned units | Create/edit within scope | No | No |
| NAAC staff | Own data and assigned units' published roster | Own requests/work records only | No | No |
| SA | Existing seven-role matrix under explicit A/SA binding | Existing canonical grants | Existing canonical grants | Existing canonical final-decision grants |

The current backend profile is facility-scoped. This implementation does not
claim organisation-wide multi-facility administration or silently expand queries
across a customer's homes. Invitation-based provisioning and unit membership
remain administrative operations tied to actual accounts.

The manager consumes the verified workflow in login/refresh and `/auth/me`, uses
it for menus, direct-route checks, role labels and action controls, and blocks
unbound accounts with an account-setup message. NAAC periods have all 42 calendar
days with the existing `42day` API value; SA retains 28 days. Nurse edits do not
request facility-wide validation data; server-side write validation still applies.
The shared-device roster log is scoped to user, organisation, facility, appointment,
units and period. The proposed manager `/messages` contract has no registered
backend routes, so its menu/direct route stays unavailable.

The separate Staff App branch replaces simulated request success with confirmed
backend operations, removes synthetic certificate records, verifies workflow and
identity on restore/refresh, and prevents an older membership's data from remaining
visible after a context change. Its task exception and published-unit-roster
screens use the real typed backend contracts. Failed requests retain user input;
an HTTP success without a valid scoped response is not shown as a saved result.

## Validation and evidence limits

Development uses synthetic fixtures and a loopback API origin for builds. It does
not log in to either live care home, read operational records, apply migrations or
prove live RLS, account provisioning, notification delivery, SSL or phone acceptance.

Final development checks: manager UI **61/61**, backend targeted workflow/SA/RBAC/
launch tests **126/126**, Staff App **59/59**. Both frontend type checks and builds
pass; the manager build used a loopback API placeholder and generated 20 static
pages. An independent reviewer ran the 126 backend tests and the 12 manager API
regressions, and cleared the source for draft PR review. No live database suite ran.
The manager UI suite includes tenant mismatch, missing
binding, deputy final-denial, nurse action restrictions, self-only visibility and
28/42-day boundary tests. Backend tests must also exercise the registered endpoint
guards and cross-unit denials. A code-only parity test is insufficient.

## Required rollout order

1. Kien verifies the exact production manager/backend source SHAs and confirms the
   approved FastAPI origin, schema/migration state and API version. Review this
   change against the deployed baseline, not just the current main label.
2. Obtain the immutable A/SA and B/NAAC org/facility/unit IDs and the invitation or
   reset flow for separate synthetic test users. Verify explicit NAAC director,
   deputy, nurse and staff appointments; preserve SA's actual seven-role matrix.
   Do not request passwords, tokens or shared credentials in Lark.
3. Confirm NAAC's actual shift dictionary, rule configuration and 42-day workflow;
   supply the reviewed binding setting. An empty binding deliberately closes all
   operational routes, so do not deploy this backend without the reviewed setting.
   The existing deployment workflow was not changed; Kien must confirm that the
   selected runtime receives and preserves this server setting before release.
   Verify legacy database role/RPC compatibility and direct authenticated RLS
   denials independently; source API checks do not change database policies.
4. Kien reviews the exact manager/backend and Staff App commits. Install the
   compatible backend contract first in the selected non-production test target,
   then point both frontends to its approved origin. The Staff build needs
   `VITE_API_BASE`; manager needs `NEXT_PUBLIC_API_URL`. These are public API origins,
   never service keys. Limit CORS to the actual tested frontend origins.
5. Test A and B separately with each role: login, own/unit roster, request and
   durable readback, recommendation versus final approval, task completion/exception,
   cross-tenant denial, cross-unit denial, locked publication, revoked appointments,
   and stale responses after sign-out/context changes. Confirm mobile installation
   and any required push provisioning independently.
6. Resolve the Staff production `BLOCKED` reason. Prepare the exact release SHA,
   migration/auth effects and rollback. The main-push workflow deploys the API and
   runs migrations; do not treat a frontend merge as harmless.
7. For the custom domains, attach only to the intended projects after runtime
   acceptance and review the authoritative DNS zone/TTL/rollback first. Vercel SSO
   is configured to exclude custom domains, so app authentication is essential.
   Current CNAME suggestions are `app` → `0d1430cdd98c0cb2.vercel-dns-017.com.` and
   `staff` → `ebd29e0a79486c1d.vercel-dns-017.com.`; they have not been applied.

Rollback: restore the prior reviewed backend/frontend commits and previous
server-only binding/API-origin settings together. This feature change adds no
database migration and performs no tenant reassignment. Keep production and DNS
unchanged until the exact release and rollback are approved.

## Kien communication — authorised, awaiting Lark sign-in and recipient verification

The user authorised this specific engineering message. Lark currently shows the
login page, so no delivery or reply is claimed. Send it only after verifying the
existing Emma group/Kien identity; do not silently substitute email or another channel.

> Hi Kien — Cherry confirmed that your manager MVP is already deployed in
> `emma-ai-manager-mvp`, and that you have built the Staff App backend. We are
> keeping `emma-ai-manager-mvp` and `emma-ai-staff-pwa` as separate frontend
> deployments, both using one approved FastAPI/auth/data contract. The intended
> domains remain `app.hiemmaai.com` and `staff.hiemmaai.com`.
>
> Cherry wants Care Home A to use the SA workflow and Care Home B to use NAAC.
> Source currently has A/SA, a separate generic B/31-day fixture, and a third NAAC
> profile. We are adding explicit immutable tenant/account bindings and separate
> NAAC appointments rather than relabelling or moving the old B data. For NAAC,
> the appointed deputy may prepare/recommend but only 主任 may finally approve or
> publish; nurses may create/edit within assigned units but cannot generate,
> batch or publish. Staff see their own data and authorised units' published roster.
>
> Please confirm (1) the actual A/SA and B/NAAC org/facility/unit IDs; (2) separate
> test login identifiers, roles and invitation/reset links for each home, including
> NAAC director/deputy/nurse/staff and the SA roles in use; (3) the approved API
> origin and backend/deployed manager commit, current schema state and allowed
> frontend CORS origins; (4) NAAC rule/dictionary readiness and the Staff Vercel
> production BLOCKED reason. Please do not post passwords, tokens or service keys.
>
> The frontend fixes replace the request page's simulated submission with the
> real API and restore the employee exception → human review path. We will share
> the exact draft PRs and test evidence for your engineering review before any
> production merge, migration or domain cutover.
