-- ============================================================================
-- Emma AI · MVP foundation - the Phase 0-2 records the compliance work assumed
--
-- 0.1 Architecture decision register
-- 0.2 MVP scope lock
-- 1.3 Append-only audit trail (before/after, actor, reason)
-- 1.4 Excel roster import jobs + per-row validation issues
-- 1.6 Security / compliance evidence checklist
-- 2.2 Facility-scoped JSON rule configuration
-- 2.3 Shift-definition weighting factor
--
-- Phases 3-5 already model the roster, tasks and compliance rules. What was
-- missing is the paperwork around them: how the architecture was chosen, what
-- the pilot promised, who changed what, where the data came from, and which
-- evidence the client/SWD submission rests on. Those are rows, not prose, so
-- the API can serve them and a report can cite them.
-- ============================================================================

-- ── 0.1 architecture decisions ───────────────────────────────────────────────
-- Cross-facility by design: the platform's database/hosting choice is one
-- decision for the product, not a per-tenant setting. Readable by any signed-in
-- user, writable only by the service role (a decision record is authored during
-- a migration or a governance review, never from the app).
create table if not exists architecture_decisions (
    id             uuid primary key default gen_random_uuid(),
    code           text not null unique,                      -- 'ADR-0001'
    title          text not null,
    status         text not null default 'accepted',          -- proposed|accepted|superseded
    context        text,
    decision       text not null,
    consequences   text,
    alternatives_json   jsonb not null default '[]'::jsonb,   -- [{option, why_not}]
    non_negotiables_json jsonb not null default '[]'::jsonb,  -- product outcomes it must satisfy
    decided_on     date,
    decided_by     text,
    superseded_by  text references architecture_decisions(code),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    constraint architecture_decisions_status_check
        check (status in ('proposed', 'accepted', 'superseded'))
);

-- ── 0.2 MVP scope lock ───────────────────────────────────────────────────────
-- One row per feature area, stating whether the 7-week MVP includes it. The
-- `phase` column matches the delivery plan's phase names so a scope question is
-- answered from the same source the roadmap uses.
create table if not exists project_scope (
    id           uuid primary key default gen_random_uuid(),
    item_code    text not null unique,                        -- '1.4', '6.3'
    phase        text not null,                               -- 'Phase 1 - Foundation, Security & Data Import'
    title        text not null,
    scope        text not null,                               -- mvp|deferred
    priority     text,                                        -- P0|P1|P2|P3
    rationale    text,
    agreed_on    date,
    created_at   timestamptz not null default now(),
    constraint project_scope_scope_check check (scope in ('mvp', 'deferred'))
);
create index if not exists idx_project_scope_scope on project_scope(scope, item_code);

-- ── 1.3 audit trail ──────────────────────────────────────────────────────────
-- Append-only, facility-scoped, before/after. `manual_override_log` remains the
-- roster-edit KPI feed (AI acceptance rate); this table is the general record
-- every module writes to, including the ones that have no roster cell to point
-- at (rule edits, imports, publishes, configuration changes).
--
-- Retention: the pilot proposes 7 years, subject to client/legal/SWD
-- confirmation. A PDPO deletion request is honoured where lawful, but statutory
-- HR/audit retention can override it - which is why rows cannot be deleted
-- through the API and a redaction is expressed as a further append.
create table if not exists audit_logs (
    id               uuid primary key default gen_random_uuid(),
    facility_id      uuid references facilities(id) on delete cascade,  -- null = platform-wide
    actor_profile_id uuid references users_profile(id) on delete set null,
    actor_email      text,                                    -- denormalised: survives profile deletion
    action           text not null,                           -- create|update|delete|publish|import|login
    entity_table     text not null,
    entity_id        uuid,
    before_json      jsonb,
    after_json       jsonb,
    reason           text,
    request_id       text,
    created_at       timestamptz not null default now()
);
create index if not exists idx_audit_logs_facility_created
    on audit_logs(facility_id, created_at desc);
create index if not exists idx_audit_logs_entity
    on audit_logs(entity_table, entity_id);

-- An audit row is evidence: once written it is immutable, and a correction is a
-- new row rather than a rewrite. Mirrors trg_protect_violation_evidence.
create or replace function public.protect_audit_log()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    raise exception using
        errcode = '42501',
        message = 'audit_logs is append-only';
end;
$$;

drop trigger if exists trg_protect_audit_log on audit_logs;
create trigger trg_protect_audit_log
before update or delete on audit_logs
for each row execute function public.protect_audit_log();

-- ── 1.4 Excel roster import ──────────────────────────────────────────────────
-- One job per uploaded workbook. `summary_json` holds the counts the acceptance
-- criteria asks for (staff matched/created, cells parsed, leave rows, events),
-- and every cell the parser could not resolve becomes an import_issues row so a
-- manager can see exactly which source cell needs a human.
create table if not exists import_jobs (
    id            uuid primary key default gen_random_uuid(),
    facility_id   uuid not null references facilities(id) on delete cascade,
    source_name   text not null,                              -- original file name
    source_layout text not null,                              -- home_a_duty_roster|home_b_floor_roster
    source_sha256 text,                                       -- same file twice is visible
    mode          text not null default 'validate',           -- validate|commit
    status        text not null default 'pending',            -- pending|running|completed|failed
    period_id     uuid references roster_periods(id) on delete set null,
    roster_version_id uuid references roster_versions(id) on delete set null,
    summary_json  jsonb not null default '{}'::jsonb,
    error_json    jsonb,
    created_by    uuid references users_profile(id) on delete set null,
    started_at    timestamptz,
    completed_at  timestamptz,
    created_at    timestamptz not null default now(),
    constraint import_jobs_mode_check check (mode in ('validate', 'commit')),
    constraint import_jobs_status_check
        check (status in ('pending', 'running', 'completed', 'failed'))
);
create index if not exists idx_import_jobs_facility_created
    on import_jobs(facility_id, created_at desc);

create table if not exists import_issues (
    id           uuid primary key default gen_random_uuid(),
    facility_id  uuid not null references facilities(id) on delete cascade,
    job_id       uuid not null references import_jobs(id) on delete cascade,
    severity     text not null default 'warning',             -- info|warning|error
    code         text not null,                               -- unparsed_cell|unknown_rank|...
    sheet        text,
    cell_ref     text,                                        -- 'RCW 院舍護理員 after!M14'
    raw_value    text,
    message      text not null,
    created_at   timestamptz not null default now(),
    constraint import_issues_severity_check
        check (severity in ('info', 'warning', 'error'))
);
create index if not exists idx_import_issues_job on import_issues(job_id, severity);

-- ── 1.6 security / compliance evidence checklist ─────────────────────────────
-- Each row is one item in the client/government submission pack, carrying its
-- owner, test method, sample output and whether an external qualified reviewer
-- is required. facility_id is nullable because most controls (RBAC model, TLS,
-- backup/restore) are platform-wide.
create table if not exists evidence_items (
    id            uuid primary key default gen_random_uuid(),
    facility_id   uuid references facilities(id) on delete cascade,
    code          text not null,                              -- 'EV-01'
    category      text not null,                              -- rbac|isolation|audit|security|ai|rules|api|backup
    title         text not null,
    owner         text,
    test_method   text,
    sample_output text,                                       -- path, endpoint or test id
    status        text not null default 'pending',            -- pending|pass|fail|not_applicable
    external_review_required boolean not null default false,
    notes         text,
    sort_order    int not null default 0,
    checked_on    date,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    constraint evidence_items_status_check
        check (status in ('pending', 'pass', 'fail', 'not_applicable'))
);
create unique index if not exists uq_evidence_items_facility_code
    on evidence_items (coalesce(facility_id, '00000000-0000-0000-0000-000000000000'::uuid), code);
create index if not exists idx_evidence_items_category
    on evidence_items(category, sort_order);

-- ── 2.2 facility JSON configuration ──────────────────────────────────────────
-- Facility-specific scheduling knobs that are data, not rules: the scheduling
-- cycle, agency vacancy formula, floor minimums, holiday priorities, request
-- quotas. `rule_definitions` stays the home of anything the compliance engine
-- evaluates; this table holds the shape the engine and importer read to know
-- what a facility looks like. Effective-dated and versioned so a config change
-- is auditable rather than destructive.
create table if not exists facility_json_configs (
    id             uuid primary key default gen_random_uuid(),
    facility_id    uuid not null references facilities(id) on delete cascade,
    config_key     text not null,                             -- scheduling_cycle|agency_formula|...
    config_json    jsonb not null default '{}'::jsonb,
    version        int not null default 1,
    description    text,
    effective_from date not null default current_date,
    active         boolean not null default true,
    created_by     uuid references users_profile(id) on delete set null,
    created_at     timestamptz not null default now(),
    constraint facility_json_configs_json_check
        check (jsonb_typeof(config_json) = 'object')
);
-- One active row per key per facility; superseding a config deactivates the old
-- version instead of overwriting it.
create unique index if not exists uq_facility_json_configs_active
    on facility_json_configs (facility_id, config_key)
    where active;
create index if not exists idx_facility_json_configs_facility
    on facility_json_configs(facility_id, config_key, version desc);

-- ── 2.3 shift-definition weighting ───────────────────────────────────────────
-- The source rosters weight some shifts differently from their clock hours
-- (imported-labour night weighting, 12-hour 7A/7P equivalence). paid_minutes
-- already carries the pay truth; this is the fairness/cost weight.
alter table shift_definitions
    add column if not exists weighting_factor numeric not null default 1.0,
    add column if not exists source_note text;

-- ============================================================================
-- Row Level Security
-- ============================================================================

-- Governance registers are readable by any signed-in user and written by the
-- service role during migrations/governance reviews. Read-only for the app is
-- deliberate: an architecture decision is not an in-app setting.
alter table architecture_decisions enable row level security;
drop policy if exists architecture_decisions_read on architecture_decisions;
create policy architecture_decisions_read on architecture_decisions
    for select to authenticated using (true);

alter table project_scope enable row level security;
drop policy if exists project_scope_read on project_scope;
create policy project_scope_read on project_scope
    for select to authenticated using (true);

-- Audit rows are readable inside the tenant and insertable by the acting
-- session. Update/delete are additionally blocked by trg_protect_audit_log, so
-- even a policy mistake cannot rewrite history.
alter table audit_logs enable row level security;
drop policy if exists audit_logs_tenant_read on audit_logs;
create policy audit_logs_tenant_read on audit_logs
    for select to authenticated
    using (facility_id = public.current_facility_id() or facility_id is null);

drop policy if exists audit_logs_tenant_insert on audit_logs;
create policy audit_logs_tenant_insert on audit_logs
    for insert to authenticated
    with check (facility_id = public.current_facility_id());

alter table import_jobs enable row level security;
drop policy if exists import_jobs_tenant on import_jobs;
create policy import_jobs_tenant on import_jobs
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table import_issues enable row level security;
drop policy if exists import_issues_tenant on import_issues;
create policy import_issues_tenant on import_issues
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (
        facility_id = public.current_facility_id()
        and exists (
            select 1 from import_jobs j
            where j.id = import_issues.job_id
              and j.facility_id = import_issues.facility_id
        )
    );

-- Evidence rows carry a nullable facility_id: shared platform controls are
-- visible to every tenant, facility rows only to their own.
alter table evidence_items enable row level security;
drop policy if exists evidence_items_read on evidence_items;
create policy evidence_items_read on evidence_items
    for select to authenticated
    using (facility_id = public.current_facility_id() or facility_id is null);

drop policy if exists evidence_items_write on evidence_items;
create policy evidence_items_write on evidence_items
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table facility_json_configs enable row level security;
drop policy if exists facility_json_configs_tenant on facility_json_configs;
create policy facility_json_configs_tenant on facility_json_configs
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

-- ============================================================================
-- Grants
-- ============================================================================
grant select on architecture_decisions, project_scope to authenticated;
grant select, insert on audit_logs to authenticated;
grant select, insert, update, delete on
    import_jobs,
    import_issues,
    evidence_items,
    facility_json_configs
to authenticated;
