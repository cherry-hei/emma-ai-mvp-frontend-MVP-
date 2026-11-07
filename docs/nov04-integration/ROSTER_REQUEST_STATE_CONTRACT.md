# Roster-first request and workflow state contract

Status: proposed implementation contract, not deployed persistence. Source: CEO message 1 November 16:54. This supersedes any assumption that fitting a pending request into a solver output automatically approves it. Preserve existing backend literal status codes via an explicit compatibility adapter; do not silently rename live DB enums or PATCH from UI to undocumented states.

## Planning-period state

`CONFIGURING -> INPUT_READY -> REQUESTS_OPEN -> REQUESTS_CLOSED -> SNAPSHOT_READY -> SOLVING -> CANDIDATES_READY -> HUMAN_REVIEW -> DECISIONS_COMMITTED -> PUBLISH_READY -> PUBLISHED`.

`NEEDS_INPUT`, `INFEASIBLE`, `SOLVE_UNKNOWN`, `STALE_SNAPSHOT` and `DECISION_CONFLICT` are explicit nonpublication states. A validated human clarification updates a versioned rule/budget/input; the backend automatically resumes from a NEW snapshot, not by editing an already signed plan. Unknown required rule is blocked input, not a zero/default pass. Requests may change until their server deadline; approved emergency reports or true HR adjustments are separate controlled workflows after cutoff.

## Request workflow vs solver evidence

Submission workflow: `SUBMITTED -> UNDER_REVIEW -> APPROVED | REJECTED | WITHDRAWN`. Recommendation and read/review status are not approval. An unmatched request remains pending for a human reasoned decision; the optimiser may not silently reject it.

Candidate evidence, separate from status: `MATCHED_IN_CANDIDATE | PARTIALLY_MATCHED | UNMATCHED | NOT_EVALUATED`, each bound to candidate_hash, period_id, request_id/version, ruleset_version, budget_version, dictionary_version and snapshot_id. Before owner decision these are provisional, not staff promises. No success notification or changed approved badge until durable decision receipt exists.

Final approvals are owner/superintendent-authorised according to the existing tenant RBAC. Deputy recommendation and nurse roster editing do not confer final decision/publish rights. Agency availability acceptance and booking are not staff leave approval. Never count preference alternatives as confirmed shifts.

## Decision bundle and hard promises

After owner selects/reviews a complete candidate, one approval bundle transaction revalidates complete hard-rule coverage, versions, active unit/staff links, applicable leave balance/window and budget authority. It CAS-updates request decisions, records all approved unavailability/pin/DO promises and immutable audit, and creates outbox event intents. Either all promised writes commit or none; a retry key returns the same receipt. The current multi-call leave.decide cannot be claimed to provide this. Notifications are a post-commit outbox delivery/retry concern, not a reason to roll back committed approval.

Approved leave/existing published locks are hard input to every subsequent solve. A new candidate that would break a committed promise must explicitly be rejected or re-enter a separately authorised revoke/amend process. If only part of a candidate's requests is approved, freeze those promises and rerun the remaining uncommitted portion; invalidate prior candidate score/evidence.

## Publish vs HR record

Owner publish action must revalidate exact decision bundle and roster snapshot, hard rules, cost and qualified staffing. Soft deviations require specific reasoned acknowledgements and audit; a generic soft omit cannot waive law or approved promises. Batch approval and publish may be offered as two explicit UX steps or one confirmed payload, but backend events remain distinct and atomic guarantees are documented.

After committed decision/publish, staff PWA fetches authoritative status and personal published roster. It may explain approved-but-not-yet-published state if two steps are separate. Outbox pushes notifications and recalculates UI counts; offline clients retry reads, not approvals. Paper/HRMS submission is a separate `HR_DOCUMENT_REQUIRED -> HR_SUBMITTED -> HR_ACKNOWLEDGED` channel with exact HR authority and receipt; do not declare HR leave final merely from roster acceptance. No external HRMS write or paper certification is currently implemented or authorised by this contract.

## Notifications and window gating

Backend period/window UTC instants plus Asia/Hong_Kong display. Canonical end is exclusive. A close notice explains no new ordinary duty/DO preferences, but emergency SL reporting remains active. AL/SL/BL and urgent medical exceptions need explicit policy; do not disable all leave submissions because duty requests are closed. Server gate prevents direct API bypass and concurrent close races; frontend inactivity is only UX.

Durable opened/reminder/closed/decision/published events use tenant-period-event idempotency keys; scheduled jobs and outbox delivery stay in the application, not LLM loops or browser timers. Provider/device delivery remains unverified until target/runtime setup. Do not promise WhatsApp/push currently works.
