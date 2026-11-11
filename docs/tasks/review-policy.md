# D-042: Codex default review, Kien for high-risk changes

Confirmed by Founder on 11 November 2026. Supersedes only the blanket Kien-review
clauses of D-028/D-040. Historical decisions remain in the local Company OS;
no private business records or customer data are copied into this repository.

| Change | Review |
|---|---|
| Routine low-risk wording, layout, documentation and bounded bug fixes | Separate Codex review plus relevant checks |
| Eligibility, minimum coverage, rest, hours, AL/PH, carry or OT accounting | Codex review; focused Kien independent review required |
| Tenant isolation, authentication/permissions, personal data, database/migrations, deployment/infrastructure or material reliability/performance | Codex review; focused Kien independent review required |
| Facility policy and operational roster/leave decisions | Founder/facility confirmation; technical review cannot supply missing policy |

Record the risk rationale, exact reviewed commit (or explicitly identified working
tree), findings, fixes, tests and remaining limitations. Mixed changes take the
highest risk. A routine label cannot override unresolved material impact. The
implementer cannot report their own self-check as independent review. Preserve
one lead/one critic and at most two review rounds; do not simulate Kien approval.

PR #15 is high risk because generation/accounting and tenant/version export
boundaries change. Continue approved synthetic tests and fixes before requesting
any release decision. Browser file-transfer acceptance is engineering work, not
a separate permission step. Deployed auth/RLS and real-facility acceptance are
not established by in-memory fixtures.

Founder alone authorises merge, deployment, migrations and other restricted
actions. Current instruction expressly forbids merge/deployment. Main-branch
automation applies migrations and deploys. No branch protections, workflow
triggers, cloud resources or review requests are changed by this policy update.
