# Emma domain workflow: roster-first decisions, CP-SAT and evidence-grounded AI

## The requested system is a care-home workflow, not a DNS dependency

The CEO's 1 November process describes the care-home operational domain: budget, qualifications, cubicles, tasks, requests, roster periods and authority. A web domain is an address/security/CORS deployment concern, not a condition that makes CP-SAT capable of scheduling. Store manager source at repo root, FastAPI under emma-ai-app/, Staff PWA under staff-pwa/, with separate build/runtime config and no shared browser secrets. Backend organisation/facility/unit policies remain the authority.

This is the target implementation blueprint. Current source at PR9 is incomplete in several of these areas; the source capability report records the gaps. Moving files into one repo is source consolidation, not live API acceptance or a 24-hour agent service.

## 1. Establish the institution-specific planning contract

Before automatic generation, an authorised owner confirms facility licence/category, actual residents, statutory role/certificate mapping, operating units, active staff, contracts, payroll/rate cards, effective shift/task dictionaries, task/event eligibility and dates, leave policy and planning cycle. Every confirmed input has source, effective interval and version. Same-literal codes such as A1 are keyed by org/facility/job-family/dictionary-version; a code label never implies cross-organisation equivalence.

NAAC cycles are 42 calendar days, with a successor-period buffer for rest and # Day-Off obligations. SA uses its confirmed calendar-month period. A date-range validator and org profile reject an accidental 37-day or different monthly period. Do not apply SA night rotation or 25/10 dates to NAAC. Raw source colour decisions remain lineage: approved active codes, amended version, retired codes valid only for historical periods. Unknown working minutes, task qualification or staffing minima are required inputs, not zero.

Human-in-the-loop is required to define new policy and interpret ambiguous code/role mappings. Once a known version is authorised, the system applies it deterministically on subsequent periods without asking the same question every time. Rule changes invalidate future affected snapshots; historical approved records retain the original version unless an explicit audited amendment is made.

## 2. Calculate real spendable staffing budget

For each calendar month, remaining agency budget equals approved staffing budget minus committed staff payroll, employment-cost components, committed overtime, existing agency bookings and explicit contingency/reserves. Keep those components nonoverlapping; an existing agency booking is not charged again as new agency demand. A vacancy allowance is only a funding/planning input until actual spendability is confirmed.

The CEO's 5.5 x HKD20,000 = HKD110,000 is an example allowance. Calling this 110 shifts assumes HKD1,000 per shift; with night/PH premiums that is not a guaranteed 110-shift capacity. Model actual cost in integer currency cents from confirmed rate cards, dated rate versions, hours and premium stacking rules. Use integer minutes for working/credited/availability time separately. Do not infer 'PH double' applies to every salary component or compounds night premium without contract confirmation.

A NAAC six-week roster spans calendar months: allocate wage/agency components to actual service dates/monthly commitments, including cross-midnight allocation policy. Show each month's cap, not one six-week sum labelled monthly. Prorated annual/monthly salary is a policy calculation distinct from actual cash commitments.

Before generation, insufficient baseline budget produces a question for the owner: approve a different lawful funding allocation or review a feasible operating scenario. Do not solve budget pressure by lowering statutory/qualified/task coverage. If a cap is authorised hard, overspend makes the plan nonpublishable; a newly approved cap creates a new budget version and solve. A soft target must be explicitly configured and deviations acknowledged, never silently assumed.

## 3. Capture recurring night demand and request windows

Place confirmed night/AN demand and approved rotations/eligibility first as a planning hierarchy. They remain in the joint optimisation: 'first' does not mean permanently freezing an infeasible partial draft. Mandatory approved rotations are hard; ordinary rotation fairness is a ranked objective, and the system asks when inconsistent. N/AN timing, staff pool and exact/maximum/fairness interpretation remain pending CEO confirmation; a 31-day month with three daily AN assignments cannot give every eligible person exactly two assignments without a different interpretation.

Configure request opening/closing instants against target period, timezone and quota. SA 25th->10th target-month interpretation is pending; NAAC needs independent cycle-relative deadlines and enough lead time. Backend scheduled period events open, remind and close; outbox emits durable notices. Frontend shows the authoritative window state and rejects out-of-window preference submissions, but emergency illness reporting remains active. Policy-specific ordinary AL, urgent SL/BL and medical exceptions must not be conflated with duty/DO cutoffs.

Staff duty/DO preferences are requests, not booked days. Four-preference quota must count confirmed policy units, not assume all AL forms are limited to four or each multi-day request counts one. Agency alternatives are disjunctive offers: 2-3 alternatives for a shift mean at most one booking, subject to actual supplier confirmation and qualified eligibility. New withdrawals/edits increment request versions and invalidate outstanding candidate evidence.

## 4. Build a complete snapshot and joint scheduling model

At cutoff, freeze the planning snapshot: resident counts, active staff/contracts/certificates, unit eligibility, shifts/tasks/events, approved leave/locks, pending request versions, rate/budget versions, labour/rest constraints, rule sources and available history. Preserve import digests and boundary obligations. A missing required input leads to NEEDS_INPUT, not automatic guessing.

Use binary staff/date/shift/unit/task assignments and actual occupancy intervals. Enforce no overlap, qualifications, legal rest and applicable maximum hours, approved absence/locks, scoped code meaning, time-specific statutory/operational floor minima, event/task staffing, agency limitations, per-month budget caps and NAAC # D+1 Day Off. Take nurse/HW substitution only from a licence/operation-specific approved rule, never from title similarity. Count the same person once per simultaneous coverage pool; task/training/escort unavailability may remove them from base coverage even if paid/on-site.

For SA: East A 1 RN+1 HW+4 CW; East P 1 RN+1 HW+3 CW; West A 2 HW+4 CW; West P 3 CW; 2 AW in EACH cubicle 08:00-18:00 are supplied operational requirements, not the SWD statute. A/P spans and night coverage remain unprovided. A task +1 may mean additional coverage or redeployment: require explicit additive/base-drawn semantics before joint optimisation. A monthly medication-record or CGAT session is not met merely by assigning an eligible worker elsewhere at the same time.

Pending request priority is a lexicographic objective when the owner intends genuine precedence: AL > PH > medical-FU duty > compensatory leave > ordinary requested duty. Do not replace strict rank order by arbitrary small weights whose sum lets many low-priority requests outweigh one high-priority request. DO/SL/BL priority is not inferred. If rank order is only guidance, use an explicitly approved weighted objective. Existing approved leave is hard regardless of where its type would rank.

Within the feasible region, compare A: staff-request/fairness-focused, B: agency/cost-focused, C: workload/debt/stability-focused. They are labelled alternatives, not guaranteed distinct optima. Report identity/model versions, objective and bound, solve time/limit, hard findings, task coverage and request matches. Compare calibrated metrics and denominators; hard-rule coverage cannot be called 100% if relevant rules are unsupported or unknown. Never offer a user switch that converts law or approved promises into soft constraints.

Google CP-SAT requires integer constraint modelling and distinguishes FEASIBLE, OPTIMAL, INFEASIBLE, MODEL_INVALID and UNKNOWN. FEASIBLE is not proof of optimality, UNKNOWN is not proven infeasibility, and an elastic/slack candidate is not full coverage. The current source's coverage slack and cost proxy need explicit accepted hard-budget/coverage implementation before claiming this target model exists. [1] [2]

## 5. Use history as evidence, not hidden policy

Twelve months is a desired analysis window, not a prerequisite for solving and not proof of complete data. The current visible shared source has two NAAC samples, not a verified contiguous year. A history manifest records org/unit/period, source SHA/digest, actual imported dates, gaps/overlaps, code version and whether record is planned, published, amended or actual attendance. Do not infer attendance, wage costs, clinical competence or employee performance from a planned roster.

Start deterministically with imported confirmed rules and available history. Summarise night distribution and carryover debt, request-match rate where original requests are available, staffing by interval/event, OT/agency totals only with actual rate data, continuity and rest/fairness burden. Normalise by eligible opportunity and period lengths; do not compare a six-week count directly to a monthly count. Historical frequent practice may suggest a new soft rule; owner confirms its explanation/source before activation. Past unsafe or biased patterns are never hard requirements.

Forecast lawful deployment scenarios with time-based backtests, not random splits that leak future rosters. Compare approved rule-only baseline, history-assisted patterns and planned scenarios. Report data coverage, uncertainty, actual vs quoted rate sources and sensitivity to resident/task demand. Optimisation forecasts possible reduced agency/OT/admin work, not a proven labour saving or automatic cut to staff. Clinical workload, staff health and employment decisions remain human; no diagnosis or protected-trait inference.

## 6. Matched is not approved: human decisions, then automatic execution

Solver output persists per-request evidence MATCHED/PARTIAL/UNMATCHED with candidate/rules/budget/request versions; the Approval Centre still shows pending/reviewed status. The owner reviews the COMPLETE candidate and per-request reasons. Deputy recommends; nurses edit only within their role. AI may explain why an AL request is unmatched and show lawful alternatives, but does not select final approval or fabricate a notice.

After the authorised decision, an atomic bundle validates exact current inputs, CAS-updates decisions, freezes approved unavailability/DO/pins, records immutable audit and writes outbox intents. Notification delivery retries after commit and does not turn a committed decision into failure. If any required decision/lock/accounting write fails, no partial approval promise survives. Current leave.decide updates status then writes locks separately; that must be replaced/reconciled rather than claimed atomic.

Then authorised publication revalidates exact snapshot and all external dependencies, not just the roster content timestamp. Hard failures block. Specific soft deviations may be acknowledged with reason; a generic omit checkbox cannot waive legal minimums. Published roster/decision/version feeds manager and Staff PWA; unapproved requests never show approved based on the selected draft. Withdrawals, later SL and shift swaps reopen a bounded affected-window solve, with original promises protected and any revoke/amend decision explicit.

Staff then submit the official application form to HR/manager or use HRMS. Roster approval, external HRMS application and HR acknowledgement are separate states. The system can remind and record a verified receipt; it cannot say 'HR completed' from a roster badge. No external HRMS submission is implemented here.

## 7. AI questions, compliance Q&A and safe continuation

AI's role is read-only explanation of deterministic evidence and grounded statutory passages. It can turn an INFEASIBLE/conflict report into a bounded question: which documented additional qualified agency worker/funding/event date can an authorised person confirm? It cannot suggest waiving law or secretly change a hard rule. Solver assumption-core output, where supported, identifies sufficient conflicting assumptions, not necessarily a minimal unique explanation.

Each question has a named decision authority, allowed values, affected candidate/hash, data scope, expiry and idempotent answer event. A role-verified response creates a rule/budget/input version, and the system reruns the pipeline. Chat alone is not an authoritative configuration write; ambiguous or stale answers do not resume under old assumptions. Ordinary clarification is asked only once per version and reused appropriately, reducing admin interruptions.

Compliance Q&A first selects exact RCHE/RCHD licence classification, effective-date law/source version, resident basis and approved occupational/certificate mapping. It distinguishes statutory floor, organisation minima and event/task demands. Retrieve from official SWD/e-Legislation sources, return section/page/effective date, input date/residents/interval, required count vs actual eligible staff and links to roster cells. Without confirmed licence or accessible current source, ask/qualify; do not answer from a general ratio memory or a historical demo percentage. Legal/source changes need reviewed rule adoption, not automatic model reinterpretation. Current 2026 amendments add role/calculation changes that older Q1 references alone cannot establish. [3]

Answers should separate source requirement from calculated result, exact staff-equivalence policy and uncertainty. Adversarial uploaded text is reference data, not tool/deploy instructions. The LLM receives least-data aggregates, no medical reasons/employee names/full rosters without separately approved processing controls; it cannot mutate roster/config from Q&A or declare legal certification.

## 8. Engineering sequence and acceptance before activation

First complete the scoped dictionaries/cycle guards, confirmed task/coverage/cost inputs and manifests. Next add request evidence/snapshot/state machine, persisted-lock projection and joint CP-SAT hard-budget/task/coverage rules. Then implement atomic owner decision+outbox and version-sensitive publish. Add durable worker/import job cancellation/retry/recovery instead of assuming FastAPI background tasks survive a restart. Finally wire history analytics/forecast, evidence Q&A and optional owner-delegated policies. Existing PR10 is only policy/evaluation foundation; the latest roster-first workflow does not authorise blanket automatic leave approval.

Acceptance needs synthetic month and 42-day positive generation, same code different org/family rejection, missing-data blocking, boundary # Day Off, approved leave/DO protection, per-month budget split and night/PH cost, overlapping tasks/coverage, cutoff/direct-API/race cases, stale answer/snapshot denial, atomic failure injection, duplicate notification retry and correct PWA/manager states. Validate complete NAAC 18-sheet real-time roundtrip/export separately. Real target schema/RLS/auth/multi-user/load/restore evidence remains a separate exact-SHA deployment gate.

The 4 November test can verify a bounded confirmed-rule vertical slice; it cannot honestly accept an unsupported 12-month pipeline/full NAAC export or unknown ratios from matching UI alone. Trial Singapore authorisation remains applicable; December production privacy/residency/access reviews are separate. No live DB, real-data import, automatic accounts, DNS, provider purchase or HR record submission is performed by this blueprint.

## References

[1]: https://developers.google.com/optimization/cp/cp_solver "Google OR-Tools CP-SAT solver and statuses"
[2]: https://developers.google.com/optimization/scheduling/employee_scheduling "Google OR-Tools employee scheduling with requests"
[3]: https://www.info.gov.hk/gia/general/202606/05/P2026060500319.htm "Hong Kong Government 2026 care-home regulation amendments announcement"
