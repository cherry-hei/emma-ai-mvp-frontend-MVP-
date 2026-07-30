-- ============================================================================
-- Emma AI · Phase 2 - solver jobs, option scores, violation log (+ RLS)
-- Async job tracking + A/B/C option scores + hard-violation log for the CP-SAT
-- rostering engine. All three tables carry facility_id and use the standard
-- tenant RLS policy (see migration ...0002). Table-level grants are inherited
-- automatically via the `alter default privileges` in migration ...0003.
-- ============================================================================

-- ── optimization_jobs (async OR-Tools run tracking) ──────────────────────────
create table optimization_jobs (
    id                 uuid primary key default gen_random_uuid(),
    facility_id        uuid not null references facilities(id) on delete cascade,
    period_id          uuid references roster_periods(id) on delete cascade,
    rule_profile_id    uuid,                                  -- FK deferred (rule_profiles is a future table)
    status             text not null default 'pending',       -- pending|running|completed|failed
    plan_mode          text,                                   -- A|B|C, or null = all three
    solver_limits_json jsonb,
    input_payload_json jsonb,
    result_json        jsonb,
    error_json         jsonb,
    started_at         timestamptz,
    completed_at       timestamptz,
    created_at         timestamptz not null default now()
);
create index idx_optimization_jobs_facility on optimization_jobs(facility_id);
create index idx_optimization_jobs_period on optimization_jobs(period_id);

-- ── roster_option_scores (A/B/C solver scores + reasons per version) ─────────
create table roster_option_scores (
    id                      uuid primary key default gen_random_uuid(),
    facility_id             uuid not null references facilities(id) on delete cascade,
    roster_version_id       uuid not null references roster_versions(id) on delete cascade,
    plan_mode               text not null,                     -- A|B|C
    constraint_score        int  not null,
    hard_violation_count    int  not null default 0,
    soft_penalty_total      bigint not null default 0,
    objective_weights_json  jsonb,
    infeasible_reasons_json jsonb,
    created_at              timestamptz not null default now()
);
create index idx_option_scores_version on roster_option_scores(roster_version_id);

-- ── violation_log (hard-constraint breaches; feeds conflict-rate KPI later) ──
create table violation_log (
    id                uuid primary key default gen_random_uuid(),
    facility_id       uuid not null references facilities(id) on delete cascade,
    roster_version_id uuid references roster_versions(id) on delete cascade,
    rule_code         text not null,                           -- coverage|ratio|rest|overlap|max_hours|leave|eligibility
    shift_id          uuid references shifts(id) on delete cascade,
    severity          text not null default 'hard',
    message           text,
    resolved          boolean not null default false,
    created_at        timestamptz not null default now()
);
create index idx_violation_log_version on violation_log(roster_version_id);

-- ── RLS (own-facility only; service_role bypasses by design) ─────────────────
alter table optimization_jobs enable row level security;
create policy optimization_jobs_tenant on optimization_jobs for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table roster_option_scores enable row level security;
create policy roster_option_scores_tenant on roster_option_scores for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table violation_log enable row level security;
create policy violation_log_tenant on violation_log for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());
