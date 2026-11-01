# SA profile primitive engineering result — 1 November 2026

**NOT LIVE. NOT FULL CP-SAT INTEGRATION.** These are opt-in pure evidence
primitives, not complete roster capability. The current live solver does not
consume this module. No live solver/runtime verification was performed.

## Provenance and ownership

Branch recorded before editing: `agent/nov04-domain-staff-monorepo`.
Source commit: `657462433ca30e4945e04d29c4df0d6e8c44845f`.
No new commit: git metadata writes, commits, pushes and deployment were not
performed. Task authority: `CODEX_SA_CONFIRMATION_TASK.md` and
`SA_CONFIRMED_RULES_2026-11-01.md`, CEO confirmations at 17:26 HKT.
Read the shared instructions, decision update, blueprint, solver inputs/model,
request-window service and API contract for integration assessment only.

Only these four new files were authored by this task:

- `emma-ai-app/emma_core/domain_profiles/__init__.py`: no runtime registration.
- `emma-ai-app/emma_core/domain_profiles/sa.py`: dependency-free typed evidence.
- `emma-ai-app/tests/test_sa_confirmed_profile.py`: synthetic tests only.
- `docs/nov04-integration/SA_PROFILE_ENGINEERING_RESULT.md`: this report.

The two supplied task/rule documents were already untracked at start.
Concurrent modifications to existing shared documents appeared during execution;
they belong to the parent/doc-sync work and were not edited by this task.

## Functions and evidence

- `monthly_anchors`: target-month opening/closing calendar dates, publication
  month/week 3 and Asia/Hong_Kong display. Exclusive cutoff remains `None`;
  an adapter must require actual configured instants. No opening hour or day
  within publication week is invented. This does not gate emergency reporting.
- `Duty.segments`: scoped organisation/facility/dictionary version and exact
  family/code; N is 21:15–07:15, AN and literal A/N are one assignment with
  07:00–14:30 and 21:30–07:15 segments. N is 600 elapsed minutes; AN is
  450 + 585 elapsed minutes. The split gap is excluded. No paid minutes,
  meal deduction, rate or continuous AN envelope is inferred.
- `overlaps`, `interval_available`, `validate_duties`: half-open local intervals,
  minute precision, date bounds, staff/day uniqueness, family consistency,
  scope matching and cross-period staff overlaps. Occupancy availability is
  not leave/rest/maximum-hours approval or labour compliance certification.
- `nightly_evidence`: hard assignment-count evidence for at least three
  distinct RCW, N/AN together, no HW/CW substitution or maximum of three.
  Ordered night clock slices include the 21:15–21:30 gap for AN-only nights.
  Slice counts are evidence, without an invented hard minute-coverage floor.
- `monthly_fairness`: caller-selected explicitly applicable pool, AN counted
  once by anchor month, N separately. Outside 2–3 produces a soft integer
  distance penalty/finding, never a publication block. Incomplete-month stats
  are `None`, not zero. Caller must establish eligibility, leave/opportunities
  and history completeness; no employees or eligibility are fabricated.
- `evaluate_task`: additional staffing by default; distinct staff/cost IDs,
  task role/qualification, interval and extra-staff location checks. Baseline
  draw requires explicit minima and a supplied authorisation receipt bound to
  exact decision/candidate/task/staff set, reason and integer budget impact.
  All supplied hard minima are swept over simultaneous intervals, including
  portions outside the task. Any hard shortfall blocks despite authorisation.
  Unknown compatibility removes the worker from base during the task; only an
  explicit true flag with compatibility evidence permits simultaneous credit.
  Result retains task, minima, baseline/extra resources, allocations, remaining
  counts, authorisation and required future audit/outbox receipt fields.

## Actual local verification

Exact test command, run from repository root, with no special environment:

```sh
python -m pytest -q emma-ai-app/tests/test_sa_confirmed_profile.py
```

First run: **43 passed in 0.16s**, exit 0. After adding retained task evidence
and an explicit empty-minima draw guard, final run: **45 passed in 0.15s**,
exit 0. No failing or blocked test command occurred. These counts include
parameterised synthetic cases. No network, credentials, DB, LLM API or paid
fallback was used. No full existing suite, live CP-SAT solve, API, DB/RLS,
phone preview or multi-user test was run.

Coverage includes January 2027 anchors; leap/year/date boundaries; exact N/AN
elapsed clocks; alias/invalid codes and family/scope checks; split gap;
15-minute next-day A overlap; duplicates; mixed-code distinct RCW count versus
2 RCW + HW/CW; early AN night gap; no maximum-three assumption; monthly soft
AN counts with N separate and incomplete stats unknown; additive tasks;
stale/missing draw authorisation; surplus draw; mandatory floor rejection;
unknown/explicit compatibility; missing qualification/minima; duplicate
resources/cost/allocations; interval sweeps; another unit's hard shortfall.

Additional executed inline Python check: parsed all three new Python files
with `ast.parse`, scanned them for common OpenAI/AWS/private-key/JWT credential
patterns (no matches), asserted profile imports are only `__future__`,
`dataclasses`, `datetime`, `typing`, and checked all other app Python files
for `domain_profiles` references (none). This is a bounded no-secret source
check, not a general credential-security certification. No environment secrets
were read. Report contains synthetic identifiers and no real roster data.

## Integration gap and safe next step

Existing `DemandSlot` already has work segments but `duration_min` denotes
paid minutes, while overlap/rest uses the outer envelope. Current model uses
coverage/ratio slack, exact AN hard monthly limits (default two), and existing
night recovery policies. These primitives do not change those behaviours or
replace current policy. Existing request-window API requires aware configured
opening/closing timestamps and durable DB-authoritative windows; calendar
anchors here do not create or update windows.

A separately scoped integration must map an explicitly selected SA dictionary
and versions, preserve work-versus-paid-versus-rest semantics, integrate
confirmed hard nightly and all effective hard coverage/leave/rest/hour rules,
implement soft applicable AN fairness, and deterministically revalidate complete
candidates. Exact cutoff instants, paid-minute policies, task dates/rates,
qualification/location compatibility and all operational/statutory minima
remain caller/configuration responsibilities. A true `hard_minima_complete`
flag and qualification/compatibility facts must come from reviewed versioned
inputs; this pure helper cannot establish their truth. Other simultaneous task
bookings must already be excluded from the caller's availability snapshot.

Authorisation strings are supplied evidence, not authenticated by this module.
A future transaction adapter must verify identity/authority/current versions,
validate complete resource/cost bookings and budgets, and durably write decision,
audit and outbox receipts. This module writes none of those receipts and does
not approve, lock or publish a roster. Independent review and end-to-end
integration acceptance remain open.

Feature gate: explicit import/call only; no existing consumer, router, config
or solver registration. Rollback: remove these four new files; no migration,
data, auth, workflow or runtime rollback is needed for this unwired source.
No API/DB/UI/solver/dependency/Docker/workflow/DNS changes or deployments.

## Parent independent check and proposal/acceptance supplement

At17:32 HKT the parent ran `python3 -m pytest -q emma-ai-app/tests/test_sa_confirmed_profile.py` in the actual candidate checkout:45 passed in0.08s. This is independent executable offline evidence, not a live solver/RLS/DB result.

Parent then added `TaskEvidence.safe_to_propose` and two tests to keep the CEO's workflow acyclic: a physically safe baseline draw may be proposed under the approved fallback policy BEFORE normal owner acceptance; absence/staleness of acceptance remains a final-acceptance finding, not a reason to prevent otherwise lawful candidate generation. Physical/qualification/incomplete-minima shortfalls still prevent proposal. `passes` retains its final local-evidence gate, and neither property authenticates receipts, commits decisions nor waives hard rules. Final rerun count is recorded by the parent handoff/PR.
