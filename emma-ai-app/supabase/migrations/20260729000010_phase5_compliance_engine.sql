-- ============================================================================
-- Emma AI · Phase 5 — deterministic compliance engine
--
-- 5.1 Versioned SWD staffing-ratio configuration
-- 5.2 Reproducible roster-validation runs and violation evidence
-- 5.3 Night / overtime debt evidence
-- 5.5 Leave policy outcomes and period balances
--
-- The migration is additive: existing Phase 1-4 consumers keep their original
-- columns and semantics. Global rule templates carry a null facility_id and are
-- readable by every authenticated tenant, but only service_role may mutate them.
-- ============================================================================

-- ── 5.1 richer, versioned SWD ratio rules ───────────────────────────────────
alter table staffing_ratio_rules
    add column if not exists rule_code text not null default 'swd_staffing_ratio',
    add column if not exists unit_id uuid references facility_units(id) on delete set null,
    -- Empty counted_ranks_json means "fall back to staff_rank / any rank".
    add column if not exists counted_ranks_json jsonb not null default '[]'::jsonb
        check (jsonb_typeof(counted_ranks_json) = 'array'),
    -- Optional fractional/equivalent-head weights keyed by rank.
    add column if not exists rank_weights_json jsonb not null default '{}'::jsonb
        check (jsonb_typeof(rank_weights_json) = 'object'),
    add column if not exists effective_to date
        check (
            effective_to is null
            or effective_from is null
            or effective_to >= effective_from
        ),
    add column if not exists config_version int not null default 1
        check (config_version > 0);

create index if not exists idx_ratio_rules_facility_code_version
    on staffing_ratio_rules(facility_id, rule_code, config_version);
create index if not exists idx_ratio_rules_unit
    on staffing_ratio_rules(unit_id)
    where unit_id is not null;

-- Legacy rows predate numeric validation, so scalar constraints are installed
-- NOT VALID: every new row is protected without making this additive migration
-- fail on historical data that administrators still need to clean up.
alter table staffing_ratio_rules
    drop constraint if exists staffing_ratio_rules_ratio_positive_check,
    add constraint staffing_ratio_rules_ratio_positive_check
        check (
            ratio_residents_per_staff is null
            or ratio_residents_per_staff > 0
        ) not valid,
    drop constraint if exists staffing_ratio_rules_min_staff_nonnegative_check,
    add constraint staffing_ratio_rules_min_staff_nonnegative_check
        check (min_staff_any_rank is null or min_staff_any_rank >= 0) not valid,
    drop constraint if exists staffing_ratio_rules_requirement_present_check,
    add constraint staffing_ratio_rules_requirement_present_check
        check (
            ratio_residents_per_staff is not null
            or min_staff_any_rank is not null
        ) not valid;

create or replace function public.is_nonnegative_numeric_json_object(value jsonb)
returns boolean
language sql
immutable
strict
set search_path = pg_catalog
as $$
    select jsonb_typeof(value) = 'object'
       and not exists (
            select 1
            from jsonb_each(value) item
            where case
                when jsonb_typeof(item.value) = 'number'
                    then (item.value #>> '{}')::numeric < 0
                else true
            end
       );
$$;

alter table staffing_ratio_rules
    drop constraint if exists staffing_ratio_rules_rank_weights_valid_check,
    add constraint staffing_ratio_rules_rank_weights_valid_check
        check (
            public.is_nonnegative_numeric_json_object(rank_weights_json)
        );

-- ── 5.2 versioned hard/soft rule definitions ────────────────────────────────
create table if not exists rule_definitions (
    id             uuid primary key default gen_random_uuid(),
    facility_id    uuid references facilities(id) on delete cascade,
    rule_code      text not null check (length(btrim(rule_code)) > 0),
    name           text,
    description    text,
    severity       text not null default 'hard'
                   check (severity in ('hard', 'soft')),
    config_json    jsonb not null default '{}'::jsonb
                   check (jsonb_typeof(config_json) = 'object'),
    config_version int not null default 1 check (config_version > 0),
    effective_from date,
    effective_to   date,
    active         boolean not null default true,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    check (
        effective_to is null
        or effective_from is null
        or effective_to >= effective_from
    )
);

-- PostgreSQL treats nulls as distinct in a regular unique constraint, so
-- facility rules and global templates need separate version-identity indexes.
create unique index if not exists uq_rule_definitions_facility_version
    on rule_definitions(facility_id, rule_code, config_version)
    where facility_id is not null;
create unique index if not exists uq_rule_definitions_global_version
    on rule_definitions(rule_code, config_version)
    where facility_id is null;
create index if not exists idx_rule_definitions_active
    on rule_definitions(facility_id, active, rule_code);

-- ── 5.2 reproducible validation audit ───────────────────────────────────────
create table if not exists roster_validation_runs (
    id                   uuid primary key default gen_random_uuid(),
    facility_id          uuid not null references facilities(id) on delete cascade,
    roster_version_id    uuid not null references roster_versions(id) on delete cascade,
    -- Digest of the roster snapshot and effective rule configuration.
    roster_digest        text not null
                         check (roster_digest ~ '^[0-9a-f]{64}$'),
    -- Exact roster content revision that was loaded for this run. Publication
    -- requires equality, closing the edit-during-validation race.
    source_content_updated_at timestamptz,
    status               text not null default 'running'
                         check (status in ('running', 'passed', 'failed', 'error')),
    hard_violation_count int not null default 0 check (hard_violation_count >= 0),
    soft_violation_count int not null default 0 check (soft_violation_count >= 0),
    summary_json         jsonb not null default '{}'::jsonb
                         check (jsonb_typeof(summary_json) = 'object'),
    validated_by         uuid references users_profile(id) on delete set null,
    started_at           timestamptz not null default now(),
    completed_at         timestamptz,
    created_at           timestamptz not null default now(),
    check (completed_at is null or completed_at >= started_at)
);

create index if not exists idx_validation_runs_version
    on roster_validation_runs(roster_version_id, created_at desc);
create index if not exists idx_validation_runs_facility_status
    on roster_validation_runs(facility_id, status, created_at desc);
create index if not exists idx_validation_runs_digest
    on roster_validation_runs(roster_version_id, roster_digest);

alter table roster_validation_runs
    add column if not exists source_content_updated_at timestamptz;

-- Structured violation evidence remains backward-compatible with Phase 2/4
-- rows, which legitimately have no validation run or rule-definition foreign key.
alter table violation_log
    add column if not exists validation_run_id uuid
        references roster_validation_runs(id) on delete set null,
    add column if not exists staff_id uuid
        references staff(id) on delete set null,
    add column if not exists rule_definition_id uuid
        references rule_definitions(id) on delete set null;

create index if not exists idx_violation_log_validation_run
    on violation_log(validation_run_id)
    where validation_run_id is not null;
create index if not exists idx_violation_log_staff
    on violation_log(staff_id)
    where staff_id is not null;
create index if not exists idx_violation_log_rule_definition
    on violation_log(rule_definition_id)
    where rule_definition_id is not null;

-- ── 5.3 debt provenance for night-chain / overtime cooldown ─────────────────
alter table future_debt_ledger
    drop constraint if exists future_debt_ledger_debt_type_check;
alter table future_debt_ledger
    add constraint future_debt_ledger_debt_type_check
    check (debt_type in ('AN', 'CL', 'CO', 'OT', 'TOIL', 'NIGHT_COOLDOWN'));

alter table future_debt_ledger
    add column if not exists source_shift_id uuid
        references shifts(id) on delete set null,
    add column if not exists details_json jsonb not null default '{}'::jsonb
        check (jsonb_typeof(details_json) = 'object');

create index if not exists idx_future_debt_source_shift
    on future_debt_ledger(source_shift_id)
    where source_shift_id is not null;

-- ── 5.5 leave priority, policy result and period balances ───────────────────
alter table leave_requests
    add column if not exists priority text not null default 'normal'
        check (priority in ('low', 'normal', 'high', 'urgent')),
    add column if not exists priority_reason text,
    add column if not exists policy_result_json jsonb not null default '{}'::jsonb
        check (jsonb_typeof(policy_result_json) = 'object');

create index if not exists idx_leave_requests_priority
    on leave_requests(facility_id, status, priority, date_start);

create table if not exists leave_balances (
    id              uuid primary key default gen_random_uuid(),
    facility_id     uuid not null references facilities(id) on delete cascade,
    staff_id        uuid not null references staff(id) on delete cascade,
    period_id       uuid not null references roster_periods(id) on delete cascade,
    leave_type      text not null check (length(btrim(leave_type)) > 0),
    opening_balance numeric(10, 2) not null default 0 check (opening_balance >= 0),
    accrued         numeric(10, 2) not null default 0 check (accrued >= 0),
    used            numeric(10, 2) not null default 0 check (used >= 0),
    carried         numeric(10, 2) not null default 0 check (carried >= 0),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    check (used <= opening_balance + accrued + carried),
    unique (facility_id, staff_id, period_id, leave_type)
);

create index if not exists idx_leave_balances_staff_period
    on leave_balances(staff_id, period_id);
create index if not exists idx_leave_balances_facility_period
    on leave_balances(facility_id, period_id, leave_type);

-- Reserve/release configured balances in the same transaction as a leave
-- approval-state change. Row locks prevent two simultaneous approvals from
-- spending the same remaining day.
create or replace function public.sync_leave_balance_usage()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    direction int := 0;
    anchor_facility_id uuid;
    anchor_staff_id uuid;
    anchor_leave_type text;
    anchor_date_start date;
    anchor_date_end date;
    balance_row record;
    overlap_days numeric;
    next_used numeric;
begin
    if tg_op = 'DELETE' then
        if old.status is distinct from 'approved' then
            return old;
        end if;
        direction := -1;
        anchor_facility_id := old.facility_id;
        anchor_staff_id := old.staff_id;
        anchor_leave_type := old.leave_type;
        anchor_date_start := old.date_start;
        anchor_date_end := old.date_end;
    elsif tg_op = 'INSERT' then
        if new.status = 'approved' then
            direction := 1;
        else
            return new;
        end if;
        anchor_facility_id := new.facility_id;
        anchor_staff_id := new.staff_id;
        anchor_leave_type := new.leave_type;
        anchor_date_start := new.date_start;
        anchor_date_end := new.date_end;
    else
        -- Once leave has consumed a balance, its ownership/type/date anchors are
        -- immutable. Cancellation releases the exact rows originally charged.
        if old.status = 'approved' and (
            old.facility_id,
            old.staff_id,
            old.leave_type,
            old.date_start,
            old.date_end
        ) is distinct from (
            new.facility_id,
            new.staff_id,
            new.leave_type,
            new.date_start,
            new.date_end
        ) then
            raise exception using
                errcode = '23514',
                message = 'approved leave anchors cannot be edited';
        end if;

        if new.status = 'approved' and old.status is distinct from 'approved' then
            direction := 1;
            anchor_facility_id := new.facility_id;
            anchor_staff_id := new.staff_id;
            anchor_leave_type := new.leave_type;
            anchor_date_start := new.date_start;
            anchor_date_end := new.date_end;
        elsif old.status = 'approved'
              and new.status is distinct from 'approved' then
            direction := -1;
            anchor_facility_id := old.facility_id;
            anchor_staff_id := old.staff_id;
            anchor_leave_type := old.leave_type;
            anchor_date_start := old.date_start;
            anchor_date_end := old.date_end;
        else
            return new;
        end if;
    end if;

    -- Lock every affected balance in a stable order before checking coverage.
    -- This serializes approvals that compete for the same entitlement.
    perform lb.id
    from leave_balances lb
    join roster_periods rp on rp.id = lb.period_id
    where lb.facility_id = anchor_facility_id
      and lb.staff_id = anchor_staff_id
      and lb.leave_type = anchor_leave_type
      and rp.period_start <= anchor_date_end
      and rp.period_end >= anchor_date_start
    order by rp.period_start, lb.id
    for update of lb;

    -- Every requested calendar day must resolve to exactly one configured
    -- balance. Missing rows must not turn approval into an unlimited allowance,
    -- and overlapping roster periods must not double-charge an entitlement.
    if exists (
        select 1
        from generate_series(
            anchor_date_start::timestamp,
            anchor_date_end::timestamp,
            interval '1 day'
        ) as requested_day(day_value)
        where (
            select count(*)
            from leave_balances lb
            join roster_periods rp on rp.id = lb.period_id
            where lb.facility_id = anchor_facility_id
              and lb.staff_id = anchor_staff_id
              and lb.leave_type = anchor_leave_type
              and requested_day.day_value::date
                  between rp.period_start and rp.period_end
        ) <> 1
    ) then
        raise exception using
            errcode = '23514',
            message = 'leave dates require exactly one configured balance';
    end if;

    for balance_row in
        select
            lb.id,
            lb.opening_balance,
            lb.accrued,
            lb.used,
            lb.carried,
            rp.period_start,
            rp.period_end
        from leave_balances lb
        join roster_periods rp on rp.id = lb.period_id
        where lb.facility_id = anchor_facility_id
          and lb.staff_id = anchor_staff_id
          and lb.leave_type = anchor_leave_type
          and rp.period_start <= anchor_date_end
          and rp.period_end >= anchor_date_start
        order by rp.period_start, lb.id
        for update of lb
    loop
        overlap_days := (
            least(anchor_date_end, balance_row.period_end)
            - greatest(anchor_date_start, balance_row.period_start)
            + 1
        );
        next_used := balance_row.used + direction * overlap_days;
        if next_used < 0 then
            raise exception using
                errcode = '23514',
                message = 'leave balance usage would become negative';
        end if;
        if next_used > (
            balance_row.opening_balance
            + balance_row.accrued
            + balance_row.carried
        ) then
            raise exception using
                errcode = '23514',
                message = 'insufficient configured leave balance';
        end if;
        update leave_balances
        set used = next_used, updated_at = now()
        where id = balance_row.id;
    end loop;
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_sync_leave_balance_usage on leave_requests;
create trigger trg_sync_leave_balance_usage
after insert or update or delete on leave_requests
for each row execute function public.sync_leave_balance_usage();

-- ============================================================================
-- Row Level Security
-- ============================================================================

-- The original ratio-rule write policy predates unit_id. Tighten it so a
-- facility-scoped rule cannot reference another tenant's unit.
drop policy if exists staffing_ratio_rules_write on staffing_ratio_rules;
create policy staffing_ratio_rules_write on staffing_ratio_rules
    for insert to authenticated
    with check (
        facility_id = public.current_facility_id()
        and public.current_role_name() in ('superintendent', 'admin', 'scheduler')
        and (
            unit_id is null
            or exists (
                select 1
                from facility_units u
                where u.id = staffing_ratio_rules.unit_id
                  and u.facility_id = staffing_ratio_rules.facility_id
            )
        )
    );

-- Global templates are read-only to authenticated clients. Tenant policy
-- definitions are append-only so historical validation remains reproducible.
alter table rule_definitions enable row level security;
drop policy if exists rule_definitions_read on rule_definitions;
create policy rule_definitions_read on rule_definitions for select to authenticated
    using (facility_id is null or facility_id = public.current_facility_id());
drop policy if exists rule_definitions_write on rule_definitions;
create policy rule_definitions_write on rule_definitions
    for insert to authenticated
    with check (
        facility_id = public.current_facility_id()
        and public.current_role_name() in ('superintendent', 'admin', 'scheduler')
    );

alter table roster_validation_runs enable row level security;
drop policy if exists roster_validation_runs_tenant on roster_validation_runs;
drop policy if exists roster_validation_runs_read on roster_validation_runs;
create policy roster_validation_runs_read on roster_validation_runs
    for select to authenticated
    using (facility_id = public.current_facility_id());
drop policy if exists roster_validation_runs_insert on roster_validation_runs;
drop policy if exists roster_validation_runs_update on roster_validation_runs;

-- New violation foreign keys must not become a path for cross-facility
-- references. Global rule templates remain valid evidence sources.
drop policy if exists violation_log_tenant on violation_log;
drop policy if exists violation_log_read on violation_log;
create policy violation_log_read on violation_log
    for select to authenticated
    using (facility_id = public.current_facility_id());
drop policy if exists violation_log_insert on violation_log;
drop policy if exists violation_log_update on violation_log;

-- Violation evidence is append-only. The sole permitted update resolves a
-- previously open row; evidence, ownership and timestamps cannot be rewritten.
create or replace function public.protect_violation_evidence()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if old.resolved
       or not new.resolved
       or (
            old.id,
            old.facility_id,
            old.roster_version_id,
            old.validation_run_id,
            old.rule_code,
            old.shift_id,
            old.staff_id,
            old.date,
            old.unit_id,
            old.task_assignment_id,
            old.event_id,
            old.rule_definition_id,
            old.severity,
            old.message,
            old.details_json,
            old.created_at
       ) is distinct from (
            new.id,
            new.facility_id,
            new.roster_version_id,
            new.validation_run_id,
            new.rule_code,
            new.shift_id,
            new.staff_id,
            new.date,
            new.unit_id,
            new.task_assignment_id,
            new.event_id,
            new.rule_definition_id,
            new.severity,
            new.message,
            new.details_json,
            new.created_at
       ) then
        raise exception using
            errcode = '23514',
            message = 'violation evidence is append-only';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_protect_violation_evidence on violation_log;
create trigger trg_protect_violation_evidence
before update on violation_log
for each row execute function public.protect_violation_evidence();

-- Preserve the personal-row boundary while validating the new source shift.
drop policy if exists future_debt_ledger_tenant on future_debt_ledger;
drop policy if exists future_debt_ledger_read on future_debt_ledger;
create policy future_debt_ledger_read on future_debt_ledger
    for select to authenticated
    using (
        facility_id = public.current_facility_id()
        and public.can_see_staff_row(staff_id)
    );
drop policy if exists future_debt_ledger_write on future_debt_ledger;

-- Leave balances follow the existing personal-row boundary: managers can see
-- the facility, while a staff login can only see its own balance.
drop policy if exists leave_requests_tenant on leave_requests;
drop policy if exists leave_requests_read on leave_requests;
create policy leave_requests_read on leave_requests
    for select to authenticated
    using (
        facility_id = public.current_facility_id()
        and public.can_see_staff_row(staff_id)
    );
drop policy if exists leave_requests_insert on leave_requests;
drop policy if exists leave_requests_update on leave_requests;

alter table leave_balances enable row level security;
drop policy if exists leave_balances_tenant on leave_balances;
drop policy if exists leave_balances_read on leave_balances;
create policy leave_balances_read on leave_balances
    for select to authenticated
    using (
        facility_id = public.current_facility_id()
        and public.can_see_staff_row(staff_id)
    );
drop policy if exists leave_balances_write on leave_balances;

-- ============================================================================
-- Roster publication and solver-ledger integrity
-- ============================================================================

alter table roster_versions
    add column if not exists content_updated_at timestamptz not null default now();

-- Normalise any legacy duplicate operative rows deterministically before
-- enforcing the invariant. The most recently published/created UUID wins.
with ranked_published as (
    select
        id,
        row_number() over (
            partition by facility_id, period_id
            order by published_at desc nulls last, created_at desc, id desc
        ) as operative_rank
    from roster_versions
    where status = 'published'
      and period_id is not null
)
update roster_versions rv
set status = 'archived'
from ranked_published ranked
where rv.id = ranked.id
  and ranked.operative_rank > 1;

create unique index if not exists uq_roster_versions_one_published_period
    on roster_versions(facility_id, period_id)
    where status = 'published' and period_id is not null;

-- Client writes are manager-only, facility/period-linked and begin as drafts.
-- Publishing is deliberately absent from these policies and is allowed only
-- through publish_roster_version(), whose transaction also archives the prior
-- operative version and records the audit event.
drop policy if exists roster_versions_tenant on roster_versions;
drop policy if exists roster_versions_read on roster_versions;
create policy roster_versions_read on roster_versions
    for select to authenticated
    using (facility_id = public.current_facility_id());
drop policy if exists roster_versions_insert on roster_versions;
create policy roster_versions_insert on roster_versions
    for insert to authenticated
    with check (
        public.current_role_name() in ('superintendent', 'admin', 'scheduler')
        and facility_id = public.current_facility_id()
        and status = 'draft'
        and (
            period_id is null
            or exists (
                select 1
                from roster_periods rp
                where rp.id = roster_versions.period_id
                  and rp.facility_id = roster_versions.facility_id
            )
        )
        and (
            created_by is null
            or exists (
                select 1
                from users_profile up
                where up.id = roster_versions.created_by
                  and up.facility_id = roster_versions.facility_id
            )
        )
    );
drop policy if exists roster_versions_update on roster_versions;
create policy roster_versions_update on roster_versions
    for update to authenticated
    using (
        public.current_role_name() in ('superintendent', 'admin', 'scheduler')
        and facility_id = public.current_facility_id()
    )
    with check (
        public.current_role_name() in ('superintendent', 'admin', 'scheduler')
        and facility_id = public.current_facility_id()
        and (
            period_id is null
            or exists (
                select 1
                from roster_periods rp
                where rp.id = roster_versions.period_id
                  and rp.facility_id = roster_versions.facility_id
            )
        )
        and (
            created_by is null
            or exists (
                select 1
                from users_profile up
                where up.id = roster_versions.created_by
                  and up.facility_id = roster_versions.facility_id
            )
        )
    );
drop policy if exists roster_versions_delete on roster_versions;
create policy roster_versions_delete on roster_versions
    for delete to authenticated
    using (
        public.current_role_name() in ('superintendent', 'admin', 'scheduler')
        and facility_id = public.current_facility_id()
        and status <> 'published'
    );

-- Publication events are evidence, not a client-editable activity feed.
drop policy if exists roster_publish_events_tenant on roster_publish_events;
drop policy if exists roster_publish_events_read on roster_publish_events;
create policy roster_publish_events_read on roster_publish_events
    for select to authenticated
    using (facility_id = public.current_facility_id());

create or replace function public.protect_roster_version_state()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    jwt_role text := coalesce(
        auth.role(),
        current_setting('request.jwt.claim.role', true)
    );
    publish_guard text := current_setting('emma.publish_guard', true);
    content_guard text := current_setting('emma.roster_content_guard', true);
begin
    if tg_op = 'DELETE' then
        if old.status = 'published' and jwt_role is distinct from 'service_role' then
            raise exception using
                errcode = '23514',
                message = 'the operative roster cannot be deleted';
        end if;
        return old;
    end if;

    if tg_op = 'INSERT' then
        if new.status = 'published'
           and publish_guard is distinct from 'allowed'
           and jwt_role is distinct from 'service_role' then
            raise exception using
                errcode = '23514',
                message = 'publish through publish_roster_version()';
        end if;
        return new;
    end if;

    if jwt_role is distinct from 'service_role'
       and (
            old.facility_id,
            old.period_id,
            old.version_type,
            old.created_by,
            old.created_at
       ) is distinct from (
            new.facility_id,
            new.period_id,
            new.version_type,
            new.created_by,
            new.created_at
       ) then
        raise exception using
            errcode = '23514',
            message = 'roster version identity is immutable';
    end if;
    if old.status = 'archived'
       and new.status is distinct from 'archived'
       and publish_guard is distinct from 'allowed'
       and jwt_role is distinct from 'service_role' then
        raise exception using
            errcode = '23514',
            message = 'an archived roster can only be restored by publication';
    end if;
    if old.status = 'published'
       and new.status is distinct from 'published'
       and publish_guard is distinct from 'allowed'
       and jwt_role is distinct from 'service_role' then
        raise exception using
            errcode = '23514',
            message = 'operative status is managed by publication';
    end if;
    if old.content_updated_at is distinct from new.content_updated_at
       and content_guard is distinct from 'allowed'
       and jwt_role is distinct from 'service_role' then
        raise exception using
            errcode = '23514',
            message = 'content_updated_at is managed by roster content';
    end if;
    if new.status = 'published'
       and old.status is distinct from 'published'
       and publish_guard is distinct from 'allowed'
       and jwt_role is distinct from 'service_role' then
        raise exception using
            errcode = '23514',
            message = 'publish through publish_roster_version()';
    end if;
    if tg_op = 'UPDATE'
       and old.published_at is distinct from new.published_at
       and publish_guard is distinct from 'allowed'
       and jwt_role is distinct from 'service_role' then
        raise exception using
            errcode = '23514',
            message = 'published_at is managed by publication';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_protect_roster_version_state on roster_versions;
create trigger trg_protect_roster_version_state
before insert or update or delete on roster_versions
for each row execute function public.protect_roster_version_state();

-- Serialize roster content edits on their parent version and reject edits to
-- the operative roster. This closes the race where validation passes, a
-- concurrent shift edit lands, and publication otherwise sees the old digest.
create or replace function public.protect_published_roster_content()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    old_version_id uuid;
    new_version_id uuid;
    version_status text;
    jwt_role text := coalesce(
        auth.role(),
        current_setting('request.jwt.claim.role', true)
    );
begin
    if tg_table_name = 'shifts' then
        if tg_op in ('UPDATE', 'DELETE') then
            old_version_id := old.roster_version_id;
        end if;
        if tg_op in ('INSERT', 'UPDATE') then
            new_version_id := new.roster_version_id;
        end if;
    else
        if tg_op in ('UPDATE', 'DELETE') then
            select roster_version_id
            into old_version_id
            from shifts
            where id = old.shift_id;
        end if;
        if tg_op in ('INSERT', 'UPDATE') then
            select roster_version_id
            into new_version_id
            from shifts
            where id = new.shift_id;
        end if;
    end if;

    for version_status in
        select status
        from roster_versions
        where id = old_version_id or id = new_version_id
        order by id
        for update
    loop
        if version_status = 'published'
           and jwt_role is distinct from 'service_role' then
            raise exception using
                errcode = '23514',
                message = 'the operative roster is immutable';
        end if;
    end loop;
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

revoke all on function public.protect_published_roster_content() from public;

drop trigger if exists trg_protect_published_roster_shifts on shifts;
create trigger trg_protect_published_roster_shifts
before insert or update or delete on shifts
for each row execute function public.protect_published_roster_content();

drop trigger if exists trg_protect_published_roster_assignments
    on shift_assignments;
create trigger trg_protect_published_roster_assignments
before insert or update or delete on shift_assignments
for each row execute function public.protect_published_roster_content();

-- Every shift/assignment mutation makes prior deterministic validations stale.
-- The trigger is SECURITY DEFINER so even a future narrower child-table policy
-- cannot suppress the version timestamp update.
create or replace function public.touch_roster_version_content()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    old_version_id uuid;
    new_version_id uuid;
begin
    if tg_table_name = 'shifts' then
        if tg_op in ('UPDATE', 'DELETE') then
            old_version_id := old.roster_version_id;
        end if;
        if tg_op in ('INSERT', 'UPDATE') then
            new_version_id := new.roster_version_id;
        end if;
    else
        if tg_op in ('UPDATE', 'DELETE') then
            select roster_version_id
            into old_version_id
            from shifts
            where id = old.shift_id;
        end if;
        if tg_op in ('INSERT', 'UPDATE') then
            select roster_version_id
            into new_version_id
            from shifts
            where id = new.shift_id;
        end if;
    end if;

    perform set_config('emma.roster_content_guard', 'allowed', true);
    update roster_versions
    set content_updated_at = clock_timestamp()
    where id = old_version_id or id = new_version_id;
    perform set_config('emma.roster_content_guard', 'denied', true);
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

revoke all on function public.touch_roster_version_content() from public;

drop trigger if exists trg_touch_roster_content_from_shifts on shifts;
create trigger trg_touch_roster_content_from_shifts
after insert or update or delete on shifts
for each row execute function public.touch_roster_version_content();

drop trigger if exists trg_touch_roster_content_from_assignments
    on shift_assignments;
create trigger trg_touch_roster_content_from_assignments
after insert or update or delete on shift_assignments
for each row execute function public.touch_roster_version_content();

create or replace function public.publish_roster_version(
    p_facility_id uuid,
    p_roster_version_id uuid,
    p_created_by uuid
)
returns setof roster_versions
language plpgsql
security definer
set search_path = public, auth
as $$
declare
    target roster_versions%rowtype;
    validation_run roster_validation_runs%rowtype;
    caller_profile_id uuid;
    jwt_role text := coalesce(
        auth.role(),
        current_setting('request.jwt.claim.role', true)
    );
begin
    -- Only the API's service client may execute the state transition. The API
    -- has already authenticated the manager and completed a fresh validation;
    -- browser clients cannot reuse an old run after external policy inputs move.
    if jwt_role is distinct from 'service_role' then
        raise exception using
            errcode = '42501',
            message = 'not permitted to publish this roster';
    end if;
    if p_created_by is not null and not exists (
        select 1
        from users_profile up
        where up.id = p_created_by
          and up.facility_id = p_facility_id
          and up.role in ('superintendent', 'admin', 'scheduler')
    ) then
        raise exception using
            errcode = '42501',
            message = 'publishing profile does not belong to this facility';
    end if;

    select *
    into target
    from roster_versions
    where id = p_roster_version_id
      and facility_id = p_facility_id;
    if not found then
        raise exception using
            errcode = 'P0002',
            message = 'roster version not found';
    end if;
    if target.period_id is null then
        raise exception using
            errcode = '23514',
            message = 'a roster period is required for publication';
    end if;

    -- A period-row lock is the transaction-wide serialization point. Taking
    -- it before any version-row locks avoids two concurrent publishers each
    -- holding a different target while waiting for the other.
    perform id
    from roster_periods
    where id = target.period_id
      and facility_id = p_facility_id
    for update;

    -- Refresh and lock the target after acquiring the period serialization
    -- lock; a content edit completed just before us may have advanced its
    -- content_updated_at timestamp.
    select *
    into target
    from roster_versions
    where id = p_roster_version_id
      and facility_id = p_facility_id
    for update;

    select *
    into validation_run
    from roster_validation_runs
    where facility_id = p_facility_id
      and roster_version_id = p_roster_version_id
      and status = 'passed'
      and hard_violation_count = 0
      and completed_at is not null
      and completed_at >= target.content_updated_at
      and source_content_updated_at = target.content_updated_at
    order by completed_at desc nulls last, created_at desc, id desc
    limit 1;
    if not found or exists (
        select 1
        from violation_log violation
        where violation.validation_run_id = validation_run.id
          and violation.severity = 'hard'
          and not violation.resolved
    ) then
        raise exception using
            errcode = '23514',
            message = 'a passed deterministic validation is required';
    end if;
    if exists (
        select 1
        from roster_option_scores score
        where score.roster_version_id = p_roster_version_id
          and score.facility_id = p_facility_id
          and (
              score.constraint_score < 60
              or score.hard_violation_count > 0
          )
    ) then
        raise exception using
            errcode = '23514',
            message = 'the generated roster does not meet the publish score';
    end if;

    -- Lock every sibling in stable UUID order. Concurrent publishers for the
    -- same period therefore serialize before touching the partial unique index.
    perform id
    from roster_versions
    where facility_id = p_facility_id
      and period_id = target.period_id
    order by id
    for update;

    perform set_config('emma.publish_guard', 'allowed', true);
    update roster_versions
    set status = 'archived'
    where facility_id = p_facility_id
      and period_id = target.period_id
      and status = 'published'
      and id <> p_roster_version_id;

    update roster_versions
    set status = 'published',
        published_at = clock_timestamp()
    where id = p_roster_version_id
      and facility_id = p_facility_id;

    caller_profile_id := p_created_by;

    insert into roster_publish_events (
        facility_id,
        roster_version_id,
        event_type,
        created_by
    ) values (
        p_facility_id,
        p_roster_version_id,
        'publish',
        caller_profile_id
    );
    perform set_config('emma.publish_guard', 'denied', true);

    return query
    select *
    from roster_versions
    where id = p_roster_version_id;
end;
$$;

revoke all on function public.publish_roster_version(uuid, uuid, uuid)
from public, authenticated;
grant execute on function public.publish_roster_version(uuid, uuid, uuid)
to service_role;

-- Solver scores are authoritative append-only output: clients may compare
-- their tenant's rows, while only the service role may insert or delete them.
drop policy if exists roster_option_scores_tenant on roster_option_scores;
drop policy if exists roster_option_scores_read on roster_option_scores;
create policy roster_option_scores_read on roster_option_scores
    for select to authenticated
    using (facility_id = public.current_facility_id());

create or replace function public.protect_roster_option_score()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if tg_op = 'UPDATE' then
        raise exception using
            errcode = '23514',
            message = 'roster option scores are immutable';
    end if;
    if not exists (
        select 1
        from roster_versions rv
        where rv.id = new.roster_version_id
          and rv.facility_id = new.facility_id
    ) then
        raise exception using
            errcode = '23503',
            message = 'option score roster belongs to another facility';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_protect_roster_option_score on roster_option_scores;
create trigger trg_protect_roster_option_score
before insert or update on roster_option_scores
for each row execute function public.protect_roster_option_score();

-- Agency purchases may remain deliberately unlinked, but every supplied shift
-- or assignment anchor must resolve to the same tenant, date and shift.
create or replace function public.validate_agency_assignment_links()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.shift_id is not null and not exists (
        select 1
        from shifts sh
        where sh.id = new.shift_id
          and sh.facility_id = new.facility_id
          and sh.date = new.date
    ) then
        raise exception using
            errcode = '23503',
            message = 'agency shift belongs to another facility or date';
    end if;
    if new.shift_assignment_id is not null and not exists (
        select 1
        from shift_assignments assignment
        join shifts sh on sh.id = assignment.shift_id
        where assignment.id = new.shift_assignment_id
          and assignment.facility_id = new.facility_id
          and sh.facility_id = new.facility_id
          and sh.date = new.date
          and (
              new.shift_id is null
              or assignment.shift_id = new.shift_id
          )
    ) then
        raise exception using
            errcode = '23503',
            message = 'agency assignment belongs to another facility, date or shift';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_validate_agency_assignment_links on agency_assignments;
create trigger trg_validate_agency_assignment_links
before insert or update on agency_assignments
for each row execute function public.validate_agency_assignment_links();

drop policy if exists agency_assignments_tenant on agency_assignments;
drop policy if exists agency_assignments_read on agency_assignments;
create policy agency_assignments_read on agency_assignments
    for select to authenticated
    using (facility_id = public.current_facility_id());
drop policy if exists agency_assignments_insert on agency_assignments;
create policy agency_assignments_insert on agency_assignments
    for insert to authenticated
    with check (
        public.current_role_name() in ('superintendent', 'admin', 'scheduler')
        and facility_id = public.current_facility_id()
        and (
            shift_id is null
            or exists (
                select 1
                from shifts sh
                where sh.id = agency_assignments.shift_id
                  and sh.facility_id = agency_assignments.facility_id
                  and sh.date = agency_assignments.date
            )
        )
        and (
            shift_assignment_id is null
            or exists (
                select 1
                from shift_assignments assignment
                join shifts sh on sh.id = assignment.shift_id
                where assignment.id = agency_assignments.shift_assignment_id
                  and assignment.facility_id = agency_assignments.facility_id
                  and sh.facility_id = agency_assignments.facility_id
                  and sh.date = agency_assignments.date
                  and (
                      agency_assignments.shift_id is null
                      or assignment.shift_id = agency_assignments.shift_id
                  )
            )
        )
    );
drop policy if exists agency_assignments_update on agency_assignments;
create policy agency_assignments_update on agency_assignments
    for update to authenticated
    using (
        public.current_role_name() in ('superintendent', 'admin', 'scheduler')
        and facility_id = public.current_facility_id()
    )
    with check (
        public.current_role_name() in ('superintendent', 'admin', 'scheduler')
        and facility_id = public.current_facility_id()
        and (
            shift_id is null
            or exists (
                select 1
                from shifts sh
                where sh.id = agency_assignments.shift_id
                  and sh.facility_id = agency_assignments.facility_id
                  and sh.date = agency_assignments.date
            )
        )
        and (
            shift_assignment_id is null
            or exists (
                select 1
                from shift_assignments assignment
                join shifts sh on sh.id = assignment.shift_id
                where assignment.id = agency_assignments.shift_assignment_id
                  and assignment.facility_id = agency_assignments.facility_id
                  and sh.facility_id = agency_assignments.facility_id
                  and sh.date = agency_assignments.date
                  and (
                      agency_assignments.shift_id is null
                      or assignment.shift_id = agency_assignments.shift_id
                  )
            )
        )
    );
drop policy if exists agency_assignments_delete on agency_assignments;
create policy agency_assignments_delete on agency_assignments
    for delete to authenticated
    using (
        public.current_role_name() in ('superintendent', 'admin', 'scheduler')
        and facility_id = public.current_facility_id()
    );

-- Default privileges from Phase 0 deliberately granted broad table access.
-- Phase 5 evidence/workflow tables are now explicitly narrowed: authenticated
-- clients can read tenant-scoped rows, while the authorized API service owns
-- every state transition and all trigger-maintained balances.
revoke all privileges on
    rule_definitions,
    roster_validation_runs,
    leave_balances
from authenticated;

grant select, insert on rule_definitions to authenticated;
grant select on roster_validation_runs, leave_balances to authenticated;

revoke insert, update, delete on
    violation_log,
    future_debt_ledger,
    leave_requests,
    roster_publish_events,
    roster_option_scores
from authenticated;

grant select on
    violation_log,
    future_debt_ledger,
    leave_requests,
    roster_publish_events,
    roster_option_scores
to authenticated;
