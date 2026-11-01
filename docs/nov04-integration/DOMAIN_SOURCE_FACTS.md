# Latest CEO domain facts — 1 November 2026

Source: Cherry's 16:54 HKT message; requirements/proposal only, NOT deployed config or statutory ratio certification. Organisational code IDs must be scoped by org/facility/job family/version/date. Same A1/P1 labels can mean entirely different duties/hours across SA and NAAC. Do not merge demo dictionaries.

## SA monthly workflow facts

Monthly staffing budget: total allowance minus staff cost leaves possible agency amount. Example only: 5.5 vacancies x HKD20,000 = HKD110,000; '110 shifts' implies an unconfirmed unit rate, not an actual capacity limit. Night more costly, PH double in stated SA practice: confirm applicable rate components/multiplier contract. Do not treat annual salary pool/FTE vacancies as spendable cash without commitments/reserves.

N and AN assigned first by roster order. User states daily 3 AN staff and each staff 2 AN/month, also '6 days already assigned'; these statements require definition/eligible pool/month-specific reconciliation and do NOT authorise engine to hardcode six days. Define N vs AN time/duration, roster rotation order, eligible roles, rest rules and cross-period carryover.

From 25th, staff may request 4 preferred duty/DO entries. '4 days already assigned' is not approval; quota entries/groupings/consecutive-day rules need confirmation. Agency staff supply 2-3 preference OPTIONS for EACH offered shift; alternatives are not 2-3 confirmed bookings. Staff request close at 10th every month; opening/closing month must be tied to target roster month, local timezone, exclusive timestamp and publication lead time. Open/preclose/close notices required. Closed ordinary preference page inactive until next open; emergency illness cannot be blocked globally.

Priority stated: Annual Leave > Public Holiday > Requested Duty for Medical FU > Compensatory Leave > Requested Duty. Medical FU preference may or may not mean absent hours: do not infer/ask private clinical detail. Already approved leave/locks hard. New pending preferences soft until owner decision. DO priority is not explicitly stated. SL/BL classification/fast-report exceptions need approved policy, not automatic lower priority.

Key new semantics: system tries to match requests to operational staffing/rules in a COMPLETE monthly or 6-week candidate. When matched duties/off days appear in the candidate, authorised manager/owner reviews and approves in Approval Centre, then real notice and PWA request-state sync occur. Staff then submit paper leave forms to supervisor/HR or HRMS. Request matched != approved; roster publication != external HRMS completion. Audit exact candidate/rule/cost/request versions. Final owner authority remains existing approved RBAC; a nurse edit is not final approval.

Finish roster in third week, issue following month roster by third week or earlier. User also says 'next next month': target-month lead time needs clarification, do not shift scheduling year/month silently. Confirm AL/SL/BL forms and HR submission separately.

## SA cubicle operational coverage (not SWD table)

East: A = 1 RN + 1 HW + 4 CW; P = 1 RN + 1 HW + 3 CW; 2 AW 08:00-18:00.
West: A = 2 HW + 4 CW; P = 3 CW; 2 AW 08:00-18:00.
N/night/base minima and exact A/P time spans not supplied. Do not infer EN can replace RN in these operational minima or count nurse->2HW equivalence without approved mapping. Floor/unit staff cannot be double-counted. Residents by cubicle/time plus licence category need actual configuration.

## Events, specific tasks and routine

Visiting; hair cutting +1 CW; meeting; weekly staff training. Dates/durations/tasks for Visiting not supplied. Staff training/meeting can reduce effective base availability; on-site and simultaneously available are distinct.

CGAT +1 RN and +1 HW every 2 weeks Thursday AM (anchor/duration unknown); PGT approximately every 6 weeks with explicit date input; medication board checking +1 HW/EN (whether alternative vs additive is ambiguous); medication record checking on 25-26 monthly +1 EN and +1 HW; podiatry +1 HW and +1 CW (date/duration unknown); weighing on 20th +1 CW. Confirm additive vs drawn-from-base, simultaneity, substitution, location and overlap. Ordinary plus extra headcount must not be charged/counted twice.

RN/EN: no specific task code, 1h meeting every morning. HW A1-3/P1-3; agency without audit only assign code3. CW A1-8/P1-6. These labels identify org/job-scoped tasks/shifts only after confirmed dictionary; don't assume code3 means unqualified to all care.

Budget-shortage proposal: CW A1-7/P1-5 plus 1 CW B/D. This is a what-if alternative requiring times/eligibility/task/rule/total-cost review; it cannot lower statutory or approved hard minima automatically. Better forecast efficient deployment/agency usage, never automatic staff cut or employment action.

## NAAC divergence

42 calendar days/six-week periods; preserve 18-sheet real-time export. # shift requires Day Off on NEXT calendar day, including next-period boundary. Different night duty by job family must be confirmed from source-coded rule sheet and Queenie; history is candidate evidence only, not permission to invent requirements. Colour-confirmed active/changed/retired codes retain version lineage. Unknown task role/qualification/min simultaneous staff/eligible shift/substitution unresolved. Monthly money allocation must follow actual dates inside six weeks. Opening/cutoff/publication schedules must be anchored relative to cycle start and configured independently; do not inherit SA 25/10.

## Data, AI and operational guardrails

12 months of complete roster history is requested, not verified supplied. Preserve actual history periods/coverage and seasonal/PH/comparable events; do not invent attendance, exact costs, denied-request patterns or forecasts. Optimise even without 12 months using approved rules, clearly label low history confidence. Roster history shows assignments, not actual attendance/clinical competence or payroll truth. Never infer protected health data or staff performance from work pattern.

Trial Singapore coded-data authorisation remains from 31 October; December production hosting/legal controls remain separate. No region-gate silently added to this analysis. No real source rosters/staff/clinical request reasons sent to an external engineering LLM. Use anonymised schemas and synthetic fixtures only. SWD Q&A must cite current official category/effective-date source and flag uncertain licence mapping; AI does not determine law or authorise exceptions.
