# Bounded 17:47 implementation result

Source read before editing: branch `agent/nov04-priorities-yearfairness`, commit `8f66dec910e1f31fad7d341868f9748983b44023`. No commit created, index write, checkout, push or merge. The task brief and decision file were already untracked and remain untouched. Only the following five new files are task-owned:

- `emma-ai-app/emma_core/domain_profiles/lexicographic.py`
- `emma-ai-app/emma_core/domain_profiles/fairness.py`
- `emma-ai-app/tests/test_lexicographic_candidate.py`
- `emma-ai-app/tests/test_annual_fairness_candidate.py`
- `docs/nov04-integration/CODEX_1747_RESULT.md`

## Implemented behaviour

`minimise_lexicographic` takes a caller-owned CP-SAT model and typed integer penalty layers AL, PH, medicalFU, CL, ordinaryduty. Missing request categories must be explicit zero expressions. External staffing and fairness may follow in the caller's declared order. All solving/objective replacement/optimum equality constraints occur on a clone; original model including original objective remains unchanged on success, nonoptimal status or later-stage exception. Expressions must belong to the supplied model; variable-index candidate values refer to that model. No constraints are removed or softened. Each stage records position/name/status/integer solution value/objective bound/wall time. Only OPTIMAL permits freezing and advancing. FEASIBLE stops as candidate-only; UNKNOWN, INFEASIBLE and MODEL_INVALID stop without claiming a complete optimum. A last solved candidate, if any, remains evidence only. A bound reported under UNKNOWN is the solver's raw bound, not proof of feasibility. Optional dependency import is lazy; absence raises ImportError, with no fallback or install.

Configuration evidence: installed OR-Tools `9.15.6755`, default 10 seconds per stage, seed 0, one worker. First-solution stopping is explicit and recorded. Wall-time limits are not a cross-machine reproducibility guarantee.

`rolling_window` and `fairness_evidence` provide immutable typed, dependency-free evidence for exactly 365 inclusive service dates. Scope is organisation/job-family/versioned code bucket. The caller evaluates N and AN separately. Identical event retries deduplicate; conflicting event IDs and double actual assignment credits reject. Original plans, cancelled plans, actual-work and actual-cover records remain separate. Only explicitly worked actual events receive credit; unknown attendance, eligibility or history produces unknown totals/spread. Employment intervals bound exposure; full-history attestation is required over the applicable interval. Empty/ineligible cohorts have unknown spread. Spread <=3 is a soft target only; no publication gate, makeup quota, medical explanation or punitive logic exists.

Documented actual credits remain visible even when totals are unknown. Opportunity normalisation and expected-minus-actual carryforward require exact supplied denominators and a documented exposure source; absent exposure never defaults to one. Expected shares must be supplied, not inferred. Positive debt/negative overallocation is advice only, subordinate to hard rules and owner review. The caller must provide approved FTE-adjusted opportunity denominators/expected shares where relevant; this helper does not derive FTE or eligibility from employment titles or health data.

## Actual local verification

Command, from `emma-ai-app/`:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider tests/test_lexicographic_candidate.py tests/test_annual_fairness_candidate.py
```

Final result: **48 passed, 0 failed, 0 skipped in 2.05s** (19 lexicographic, 29 fairness cases). Only synthetic fixtures were used. The first run exposed an OR-Tools 9.15 proto API mismatch (7 failed/28 passed); corrected to its actual `has_floating_point_objective()` API. Intermediate run: 35 passed; additional priority/transaction/exposure cases yielded the final 48.

Actual CP-SAT proof fixture produced `(stage, layer, status, value, bound)`:

```text
1 AL           OPTIMAL 0   0.0
2 PH           OPTIMAL 100 100.0
3 medicalFU    OPTIMAL 0   0.0
4 CL           OPTIMAL 0   0.0
5 ordinaryduty OPTIMAL 0   0.0
```

Same model with weighted sum `2*unfilled_AL + unfilled_PH` chooses unfilled AL=1; staged solving preserves AL=0. All adjacent request priorities are also tested. Tests actually obtain FEASIBLE using explicit first-solution stopping on a synthetic covering model, UNKNOWN with a zero-second limit, INFEASIBLE with contradictory hard locks, and MODEL_INVALID with an empty variable domain. Hard approved-leave pin remains fixed. Success/failure/float-objective rejection and later-stage exception leave the caller's model unchanged. Fairness cases cover leap/year/month boundaries, inclusive endpoints, cancelled plan/replacement actual cover, event retries/conflicts, employment intervals, tenant/family/N-vs-AN isolation, unknowns, exact exposures and soft spread violation.

No live runtime, API, DB/RLS, schema, source-data or multi-user acceptance was attempted. No dependency installation, paid API, purchase or external messaging occurred. New implementation/test files contain synthetic identifiers and no credentials; a bounded credential-pattern scan reports no matches. Existing tracked diff is empty; all implementation changes are the new files above.

## Integration gaps and caller requirements

Read-only assessment: `solver/model.py::apply_objective` remains BIG_M coverage/ratio slack plus weighted penalties; `services/optimize.py::_preference_weight` maps requests to weights. Existing `solver/solve.py::solve_plan` groups other non-solution statuses into its infeasible response. The new helper does not repair or wire those existing behaviours. Existing model permits staffing/ratio slack and contains agency caps; callers cannot treat it as a hard-valid complete plan merely by replacing its objective. Hard-coverage validation/constraints, source/rule/snapshot binding, approved locks and deterministic revalidation remain prerequisites. No public API contract changes.

`services/optimize.py::_prior_night_history` reads the latest prior published roster period, counts noncancelled assignments, and combines night types in its night counter; this is not a complete 365-day actual-attendance ledger. Existing model fairness is worked-minute spread, not this scoped annual evidence. No actual annual history or eligible cohort has been supplied/verified. Caller must provide authoritative scope/dictionary versions, immutable assignment/event identities, attendance completeness, eligibility over the relevant interval, employment dates, and documented exposure/share assumptions. Eligibility changes require caller cohort partitioning rather than one falsely constant eligibility assertion. Bucket equivalence must be explicitly approved outside this helper. Events are one assignment credit each; this utility does not infer hours or cross-bucket equivalence.

Resource-versus-request tradeoff policy remains unresolved; only explicitly lower external-staff/fairness objectives are supported here. No hard spend cap, rates or savings claims are invented. Complete candidate matching is not leave approval, durable decision, publication or HR receipt.

Feature gate: import/call opt-in only; no existing import, runtime entry point or feature flag was modified. Rollback: remove these five new task files; no deployed state or migration exists to reverse. Independent parent review remains outstanding; this result is local synthetic solver evidence only.
