# Emma — Source Capability and 12-Month History Gaps
## Read-only inventory: NAAC and SA workflow

**Inspection boundary.** Static source and local file metadata only. No live API, database, tenant, deployment, workbook-row, employee, health, or attendance data was accessed. The inspected repository commit is `6bcb10e4a20206044fb73bef881a394b0f5f62c6` (base PR9). This is not runtime evidence and is **not an M1 or M2 sign-off**.

## 1. History inventory: what is visible, and what it does not establish

Two visible NAAC roster-format workbooks were found in the shared project area. Both have the same **18-sheet** structure:

1. 更期代號註解
2. 代號及時數(old)
3. 代號及時數
4. 覆診地點代號
5. 第一週
6. 第二週
7. 第三週
8. 第四週
9. 第五週
10. 工作表2 *(hidden)*
11. 第六週
12. Hours
13. PH & Off
14. DO更次數
15. AP更
16. C更男女
17. N更男女
18. 用膳代號

| Visible workbook | Available span evidence | Interpretation |
|---|---|---|
| `NAAC TAHDuty(20260413-20260524).xlsx` | Filename states 2026-04-13 to 2026-05-24, **42 calendar days**. | One six-week sample workbook; it is not evidence of a complete 12-month history or an active runtime import. |
| `NAAC TAHDuty(255-0507).xlsx` | Filename has an abbreviated/ambiguous date token; no safe full date span is inferred. | A second visible sample workbook only; it must not be converted into a year/date claim without authoritative metadata. |

No typed or explicit ISO date cells were detected by a metadata-only scan; the stated first span is therefore filename evidence, not a reconstructed roster-date audit. A separate visible code-confirmation workbook was not counted as roster-history coverage.

**Conclusion:** the visible material is two samples, not twelve monthly or six-week cycles. The desired 12-month history remains **requested, not evidenced as supplied, imported, complete, contiguous, or active in a tenant**.

## 2. Confirmed requirement baseline

The prior handoff states that a hash-suffixed NAAC duty requires **Day Off on the next calendar day (D+1)**; neither a night code nor another substitute satisfies it. The rule must work at normal, month-end, year-end, and six-week/final-period boundaries; the latter needs successor-period context or a fail-closed result. That handoff also separates dictionary work from the full **18-sheet** live-format/export requirement.

The current source independently contains a NAAC profile declaring `cycle_type="42day"` and `scheduling_cycle_days=42` at:

- `emma-ai-app/emma_core/importers/naac.py`

This is profile/static source support, not proof that a 42-day tenant period was created, imported, optimized, exported, or published.

## 3. Source support actually present

### 3.1 Periods, history records, and general import plumbing

| Area | Static source support | Important boundary |
|---|---|---|
| Roster periods and versions | `api/routers/roster.py`; `emma_core/services/roster.py` list/create periods, list versions, and read a selected grid. | Period creation only rejects an end before its start. It does **not** enforce NAAC 42 days, SA monthly cycles, cutoff dates, or target-period workflow. |
| Audit history | `api/routers/governance.py`; `emma_core/services/audit.py` expose append-only `/audit-logs`, facility-scoped filters, and a maximum request limit of 500. | Current source has no `/roster-history` route and no dedicated 12-month history/import coverage API. Audit records are not a complete historical roster ingestion programme. |
| Workbook import job record | `api/routers/imports.py`; `emma_core/services/imports.py`; migration `20260730000014_mvp_foundation.sql`. Uploads create `import_jobs`, retain digest/status/summary and unresolved-cell `import_issues`; validate mode records a job without roster writes. | The HTTP import path awaits `run_import`; it is not queued as a background/resumable batch import worker. |
| Parsed import write path | `emma_core/importers/loader.py`. It creates reference data, staff, period/version, cells, leave, tasks, events, calendar/configuration records. `_insert_many` batches bulk inserts in groups of 500. | The loader comprises multiple PostgREST writes/deletes and has no visible all-workbook transaction/rollback wrapper. A failure can therefore require reconciliation of prior writes. |
| Import layout registry | `emma_core/importers/__init__.py` registers only `home_a` and `home_b` readers. | `naac.py` provides a NAAC dictionary/grammar/profile but is **not** a registered workbook layout reader. The visible NAAC 18-sheet format therefore has no demonstrated current API import path. |

### 3.2 CP-SAT optimizer: actual inputs and constraints

**Primary paths:**

- `emma-ai-app/api/routers/optimize.py`
- `emma-ai-app/emma_core/services/optimize.py`
- `emma-ai-app/emma_core/solver/inputs.py`
- `emma-ai-app/emma_core/solver/model.py`
- `emma-ai-app/emma_core/solver/objective.py`
- `emma-ai-app/emma_core/solver/solve.py`

The optimizer constructs demand from working shifts in a selected source/manual version. It loads active staff/contracts, ratio rules, resident counts, approved leave and pending/reviewed requests, calendar cost multipliers, agency policy, night history/debt, and **additive event** staffing requirements. It outputs A/B/C alternatives (or a Pareto set) as draft versions and option-score records.

Implemented hard or eligibility controls include:

- rank/contract shift eligibility and medication-audit eligibility;
- approved actual leave, including cross-midnight occupied dates;
- overlap and minimum rest;
- maximum period hours where configured;
- agency prohibitions/caps, selected part-time patterns, night cooldown/limits, and local full-time night recovery;
- direct request-supplied `LockedAssignment` pins/forbids.

Coverage and staffing-ratio gaps are **elastic model slack variables**, made dominant in the objective by `BIG_M`; they are not inherently infeasible model constraints. The solver may therefore return an explainable option with gaps, which is subsequently subject to deterministic validation and publication gating.

The A/B/C objective changes only the weights on five soft terms:

1. agency cost proxy;
2. overtime/workload;
3. future-debt proxy;
4. deviation from baseline plus request preferences;
5. fairness spread.

The cost term is a shift/agency estimate with calendar multipliers. There is **no total/salary budget cap or budget-feasibility constraint** in the optimizer inputs/model. ROI budget fields and vacancy-derived agency limits are not a complete staffing budget gate.

### 3.3 Approved leave, approval, locks, and publication

| Control | Actual source behavior | Gap/risk for end-to-end workflow |
|---|---|---|
| Approved actual leave | `services/optimize.py` converts approved non-duty requests to hard unavailability; `services/validation.py` raises `approved_leave_unavailable`; `services/leave.py` has an approved-date helper. | This is substantive source support, but no live test was performed. |
| Leave balance/anchors | Migration `20260729000010_phase5_compliance_engine.sql` prevents approved leave-anchor edits and serializes/validates balance consumption. | This is database-source design only; migration application is not verified. |
| Approved DO/duty lock | `services/roster_locks.py` writes a persistent forbid for approved DO, or a pin for approved duty/swap; revocation releases it. | `services/optimize.py` loads only request-body `locked_assignments`; no visible read of persisted `roster_cell_locks`. Thus approved DO/duty locks are **not visibly projected automatically into each optimization run**. |
| Approval atomicity | `services/leave.py::decide` changes approval status, then calls lock creation. | The source explicitly describes this as a post-approval lock step. It is not one visible database transaction; an approved-but-unlocked failure state is possible and needs reconciliation/transactional design. |
| Publish validation | `api/routers/roster.py` runs fresh deterministic validation before publish. The publication RPC in migration `20260729000010_phase5_compliance_engine.sql` locks the period, requires a passed validation run no older than `content_updated_at`, archives the previous operative version, and publishes in one DB transaction. | Stronger than a UI-only gate. However, the RPC visibly compares roster-content freshness, not a locked/versioned comparison of all external rule, leave, resident, budget, task, or request inputs that could change after validation. |

## 4. Missing or incomplete NAAC/SA workflow support

### NAAC gaps

1. **No current NAAC workbook-layout importer.** The NAAC duty grammar/profile is present, but API-recognised layouts are only the two non-NAAC readers. Source dictionary support is not end-to-end import support.
2. **No current `# → D+1 DO` validator or solver rule.** The NAAC parser treats `#` as a duty-supervisor marker. The pinned validator implements configurable generic night-chain recovery and sequence checks, but source search found no hash-duty successor-Day-Off enforcement, no explicit D+1 obligation record, and no final-42-day successor/fail-closed logic.
3. **No enforced 42-day period gate.** The profile says 42 days; generic period creation accepts any non-negative span. A period selector/cycle guard must enforce or explicitly validate NAAC cycle length.
4. **No demonstrated 18-sheet real-time export.** The two sample workbooks contain 18 sheets, but the current source report/export path is generic data/report output, not a verified 18-sheet NAAC round-trip/template exporter.
5. **Dictionary/version lineage is incomplete as an operational proof.** The source includes NAAC duty/task CSV-backed dictionary logic, but no verified live lifecycle handling for confirmed/changed/retired codes, exact-literal preservation, or full current source reconciliation.
6. **Task staffing is not solver demand.** Additive event staffing is modeled. Ordinary task assignments and floor-minimum rules are validated by `services/scheduling.py` / deterministic validation, but are not loaded by `services/optimize.py` into CP-SAT demand. Unconfirmed task eligibility, minimum simultaneous staffing, allowed shift, and substitution cannot safely be invented.

### SA and shared workflow gaps

1. **Period selection exists, workflow gating does not.** Generic period list/create/select endpoints exist; no source enforcement was found for SA’s monthly cadence, NAAC’s cycle-relative opening/cutoff/publication dates, or target-period deadline windows.
2. **Preferences are only partly modeled.** Pending/reviewed requests feed a weighted soft preference; approved actual leave is hard. There is no demonstrated candidate-to-approval workflow that persists request-to-option matching, exact candidate/rule/cost version, and owner decision as one controlled process.
3. **Budget is not a solver gate.** Cost is optimized as a proxy, but total allowance, committed staff cost, approved agency budget, and date-specific rate components are not modeled as a verified budget constraint.
4. **Task/floor/coverage integration is incomplete.** Events can create additive CP-SAT demand; task execution, floor minima, and several operational coverage requirements remain post-solve validation/configuration, not jointly optimized demand.
5. **History scale and operational import performance are unproven.** Import writes are synchronous and multi-step; the optimizer uses FastAPI `BackgroundTasks` plus a polled `optimization_jobs` row, not a durable broker/worker with retry, cancellation, or restart recovery. No 12-month batch import/backfill orchestration, timing benchmark, or tenant-scale evidence was inspected.
6. **Publication controls cannot substitute for complete domain rules.** Fresh deterministic validation and atomic version-state publishing are implemented, but they cannot validate missing NAAC D+1 logic, unconfigured staffing/task/budget gates, or unsupported source import mappings.

## 5. Required next evidence before any milestone decision

1. Provide a redacted, authoritative period inventory proving actual 12-month coverage (period start/end, source digest/version, import status, gap/overlap result) rather than relying on workbook count.
2. Implement and test a NAAC reader for the 18-sheet format, then validate exact source-to-persisted duty/task mappings in an isolated environment.
3. Add a literal-preserving NAAC `#` D+1 Day-Off rule with month/year and final-42-day successor-period or fail-closed tests; preserve its separation from task `#` markers.
4. Project approved DO/duty locks into optimizer inputs transactionally, and make approval plus lock/reconciliation auditable as one reliable outcome.
5. Define and version period-selection, preferences, staffing/task/floor gates, cost/budget inputs, and publication revalidation dependencies by facility and target period.
6. Exercise imports and solver jobs in an isolated environment at representative multi-period volume, including partial-failure recovery, job restart behavior, and publish revalidation after non-roster policy input changes.

## Final status

The pinned source contains meaningful generic CP-SAT, deterministic validation, leave, auditing, period/version, and import-job components. It does **not** establish a complete NAAC or SA requested-history workflow. In particular, the visible samples do not establish 12 months; NAAC layout import, hash-to-next-calendar-day DO enforcement, lock projection, period/cutoff workflow, budget/task staffing integration, and full 18-sheet export remain unsupported or unverified end-to-end.

**No M1, M2, runtime, deployment, tenant, or production sign-off is made.**
