# Domain implementation backlog — source-aware and not milestone sign-off

**Latest SA source authority:** `SA_CONFIRMED_RULES_2026-11-01.md`, CEO confirmation, 1 November 2026 17:26 HKT. The items below are source-only candidate implementation work, not a runtime/deployment commitment.

## P0: confirmed-rule vertical slice for 4 November

1. Finish exact runtime Supabase/API/CORS/migration/backup facts and permissions; source consolidation is not deployment. Recheck same-org/unit roles and provisioned staff links.
2. Implement and test confirmed SA mapping M → open day25 of M-2 / close day10 of M-1 / publication week3 of M-1; store close calendar day separately from configured exclusive UTC instant and keep UI Asia/Hong_Kong. Implement distinct HW/RCW/CW N clocks (N 21:15–07:15; composite AN A07:00–14:30 plus N21:30–07:15) with preserved split gap, and hard nightly ≥3 distinct RCW N-or-AN assignment validation. Implement 2–3 composite AN/calendar-month as SOFT applicable-eligibility fairness only, separately tracking N load. Make `+1 RN/HW/CW` additional above base by default; when extras are unavailable, permit the system to propose a safe audited base draw after capacity and remaining-hard-minimum recheck, with no duplicate person/time/cost. Bind final acceptance of each proposed draw and its evidence to the normal complete-candidate owner review and version before commitments/publication, not a new ad-hoc task permission. Retain residual configuration for exact deadline/publication hours, paid/credited minutes/rates, 21:15–21:30 minimum and substitution/compatibility. Confirm NAAC active code/next-day DO meanings/qualifications independently. No unknown-as-zero rule activation.
3. Add scoped calendar-month/42-day validators and successor-boundary inputs. Generic create-period currently accepts arbitrary spans. A task code # is not the same as duty hash.
4. Project persisted roster_cell_locks into EACH optimise snapshot with conflict detection; current base reads request-body locks only. Already approved leave/DO/duty promises cannot depend on the caller remembering pins.
5. Implement NAAC # D+1 Day-Off constraint and deterministic validator, including month/year/42nd-day boundary, not generic night recovery. Register actual NAAC workbook reader; profile/CSV alone is not 18-sheet import/export.
6. Preserve real CP-SAT status/best bound/time. Current source maps non-feasible statuses to INFEASIBLE; do not ask humans to relax rules from a timeout report.
7. Add actual complete-candidate request match evidence and owner decision binding. Current leave.decide status/locks/audit are separate calls; build atomic decision bundle plus outbox before reliable automatic continuation.

## P1: complete domain optimisation

Versioned statutory and organisation time-segment staffing/eligibility layers; task additional coverage with controlled authorised base reallocation; no simultaneous double counting. Build true joint hard coverage/task/budget model, not only validation after elastic slack candidates. A/B/C options preserve hard constraints and ranked pending priorities. Introduce confirmed cents ratecards, calendar-month budget ledger, night/PH component stacking, existing commitments and six-week cost allocation; current cost proxy is not a budget cap. Do not infer rates or paid/credited minutes from the confirmed N/AN clocks.

Add immutable planning snapshots that include external rules/residents/budget/request/task/leave versions. Existing publish freshness is roster-content-focused; broader policy changes must invalidate validation/approval. Specific soft omission only, no toggle for legal/approved promises.

## P2: evidence-grounded history and efficient operation

Manifest the actual 12-month coverage/lineage/gaps; available shared samples do not prove a full year. Make bulk import durable/resumable/tenant-scoped, with reconciled partial-write failure and retries. Build rule-only vs history-assisted temporal backtests, calibrated workload/agency/OT/task metrics and uncertainty; never infer attendance/payroll/competence from planned shifts.

Use durable application jobs with versioned cancellation and restart recovery rather than unverified in-process BackgroundTasks. Open/close/reminder/decision/publish outbox events need idempotent delivery and status, not browser timers or repeated paid LLM polling.

## P3: Q&A, forecast and less human interruption

Ground official source retrieval by licence/regime/class/effective date; review 2026 nursing-care-practitioner/legal calculation deltas. Q&A answers cite clause/page/current count/time and unknowns, cannot mutate/approve. Implement decision questions bound to role/current hash/allowed options and expiry, with audited answer -> new snapshot -> automatic resume.

Optional owner-delegated approvals are future policy and require positive/negative transactional acceptance; latest CEO flow retains complete-plan owner approval. Do not call existing PR10 review-only evaluator automatic approval. Compare lawful budget patterns and resource deployments with uncertainty; no automatic staffing cuts/employment or HRMS actions.

## Acceptance dimensions

Complete month and NAAC 42 days; SA year/month/leap boundary mapping; standalone-N versus composite-AN clocks and split gap; nightly distinct-RCW3 hard failure/qualification; AN fairness soft reporting without N+AN conversion; additional-task default and audited base-draw hard-minimum/capacity recheck; same code different org/family; cycle/time/budget boundaries; qualification/coverage/task overlap; approved promises; input completeness; deadline/direct API/race; stale answer/approval; atomic failure injection; double notification prevention; manager/staff committed state; actual 18-sheet live-content export; representative scale/restart/restore. Offline fixtures, build, and API docs do not count as hosted multi-user/RLS or contract milestone sign-off.
