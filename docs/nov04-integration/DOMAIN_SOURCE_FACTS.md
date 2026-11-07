# Latest CEO domain facts — 1 November 2026

**Latest source authority:** `SA_CONFIRMED_RULES_2026-11-01.md`, CEO confirmation, 1 November 2026 17:26 HKT. It supersedes Cherry's 16:54 HKT message only for the resolved SA target-month timeline, N/AN rules and event/task staffing semantics below. Requirements/proposal only: this is NOT deployed config or statutory ratio certification. Organisational code IDs must be scoped by org/facility/job family/version/date. Same A1/P1 labels can mean entirely different duties/hours across SA and NAAC. Do not merge demo dictionaries.

## SA monthly workflow facts

Monthly staffing budget: total allowance minus staff cost leaves possible agency amount. Example only: 5.5 vacancies x HKD20,000 = HKD110,000; '110 shifts' implies an unconfirmed unit rate, not an actual capacity limit. Night-more-costly/PH-double practice does not establish rate components, premium stacking, paid or credited minutes, or contracts. Do not treat annual salary pool/FTE vacancies as spendable cash without commitments/reserves.

N and AN are scheduled first as a planning hierarchy, but remain in the joint feasibility model. Only HW, RCW and CW are eligible for these rules. Standalone **N** is 21:15 on roster day D to 07:15 D+1. Composite **AN/A-N** is one assignment with two work segments: A 07:00–14:30 D and N 21:30 D–07:15 D+1; the 14:30–21:30 off-duty gap is neither continuous work nor credited presence. Every roster-night date requires at least **three distinct RCW** assigned a qualifying N or AN night segment (HARD); HW/CW do not fill this RCW-specific minimum without separately approved substitution. Each applicable/eligible HW, RCW or CW should receive **2–3 composite AN assignments per calendar month** (SOFT fairness only). Count AN once; do not turn it into an N+AN target or count a cross-midnight end again. Standalone-N load remains separately recorded. The obsolete six-day assertion is not an active requirement.

For target month M, ordinary duty/DO preference intake opens on calendar day 25 of M-2, closes on calendar day 10 of M-1, and the roster is issued in week 3 of M-1 (for January 2027: 25 November / 10 December / December week 3). Store the close calendar day separately from its configured exclusive UTC instant; UI is Asia/Hong_Kong. Exact opening/closing hours and the particular publication day in week 3 remain policy configuration, not inferred facts. From the configured opening, staff may request 4 preferred duty/DO entries; quota units/groupings/consecutive-day rules remain configuration. Agency staff supply 2–3 preference OPTIONS for EACH offered shift; alternatives are not 2–3 confirmed bookings. Open/preclose/close notices are required. Closed ordinary preference page is inactive until next open; emergency illness cannot be blocked globally.

Priority stated: Annual Leave > Public Holiday > Requested Duty for Medical FU > Compensatory Leave > Requested Duty. Medical FU preference may or may not mean absent hours: do not infer/ask private clinical detail. Already approved leave/locks hard. New pending preferences soft until owner decision. DO priority is not explicitly stated. SL/BL classification/fast-report exceptions need approved policy, not automatic lower priority.

Key new semantics: system tries to match requests to operational staffing/rules in a COMPLETE monthly or 6-week candidate. When matched duties/off days appear in the candidate, authorised manager/owner reviews and approves in Approval Centre, then real notice and PWA request-state sync occur. Staff then submit paper leave forms to supervisor/HR or HRMS. Request matched != approved; roster publication != external HRMS completion. Audit exact candidate/rule/cost/request versions. Final owner authority remains existing approved RBAC; a nurse edit is not final approval.

Finish and issue the target-month roster in week 3 of M-1. The exact publication day within that week remains configured; do not shift the mapped year/month silently. Confirm AL/SL/BL forms and HR submission separately.

## SA cubicle operational coverage (not SWD table)

East: A = 1 RN + 1 HW + 4 CW; P = 1 RN + 1 HW + 3 CW; 2 AW 08:00-18:00.
West: A = 2 HW + 4 CW; P = 3 CW; 2 AW 08:00-18:00.
N/night/base minima and exact A/P time spans not supplied. Do not infer EN can replace RN in these operational minima or count nurse->2HW equivalence without approved mapping. Floor/unit staff cannot be double-counted. Residents by cubicle/time plus licence category need actual configuration.

## Events, specific tasks and routine

Visiting; hair cutting +1 CW; meeting; weekly staff training. Dates/durations/tasks for Visiting remain unconfigured. Staff training/meeting can reduce effective base availability; on-site and simultaneously available are distinct.

CGAT +1 RN and +1 HW every 2 weeks Thursday AM (anchor/duration unknown); PGT approximately every 6 weeks with explicit date input; medication board checking +1 HW/EN (alternative-role meaning remains unconfigured); medication record checking on 25-26 monthly +1 EN and +1 HW; podiatry +1 HW and +1 CW (date/duration unknown); weighing on 20th +1 CW. Default `+1 RN/HW/CW` is **additional staff above the East/West baseline for the actual overlapping task duration**. If extra staff are unavailable, the system may automatically propose a safe controlled draw from base under the authorised fallback policy. Final acceptance occurs in the normal complete-candidate owner review, not a new ad-hoc approval for each task; version-bound owner acceptance must cover the particular draw and its evidence before commitments/publication. Preserve role/task/location/interval, affected unit counts, capacity source, budget impact and audit, then recheck remaining baseline, task, statutory and other hard minima. Unknown worker compatibility defaults to non-simultaneous: never double-count person/time or staff cost, or override law/committed promises. Dates/durations, actual ratecards/paid minutes, 21:15–21:30 operational minimum and substitution/compatibility policy remain configuration; no generic task ambiguity authorises a waiver.

RN/EN: no specific task code, 1h meeting every morning. HW A1-3/P1-3; agency without audit only assign code3. CW A1-8/P1-6. These labels identify org/job-scoped tasks/shifts only after confirmed dictionary; don't assume code3 means unqualified to all care.

Budget-shortage proposal: CW A1-7/P1-5 plus 1 CW B/D. This is a what-if alternative requiring times/eligibility/task/rule/total-cost review; it cannot lower statutory or approved hard minima automatically. Better forecast efficient deployment/agency usage, never automatic staff cut or employment action.

## NAAC divergence

42 calendar days/six-week periods; preserve 18-sheet real-time export. # shift requires Day Off on NEXT calendar day, including next-period boundary. Different night duty by job family must be confirmed from source-coded rule sheet and Queenie; history is candidate evidence only, not permission to invent requirements. Colour-confirmed active/changed/retired codes retain version lineage. Unknown task role/qualification/min simultaneous staff/eligible shift/substitution unresolved. Monthly money allocation must follow actual dates inside six weeks. Opening/cutoff/publication schedules must be anchored relative to cycle start and configured independently; do not inherit SA 25/10.

## Data, AI and operational guardrails

12 months of complete roster history is requested, not verified supplied. Preserve actual history periods/coverage and seasonal/PH/comparable events; do not invent attendance, exact costs, denied-request patterns or forecasts. Optimise even without 12 months using approved rules, clearly label low history confidence. Roster history shows assignments, not actual attendance/clinical competence or payroll truth. Never infer protected health data or staff performance from work pattern.

Trial Singapore coded-data authorisation remains from 31 October; December production hosting/legal controls remain separate. No region-gate silently added to this analysis. No real source rosters/staff/clinical request reasons sent to an external engineering LLM. Use anonymised schemas and synthetic fixtures only. SWD Q&A must cite current official category/effective-date source and flag uncertain licence mapping; AI does not determine law or authorise exceptions.
