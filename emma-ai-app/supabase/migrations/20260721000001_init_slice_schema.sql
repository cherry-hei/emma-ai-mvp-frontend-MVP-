-- ============================================================================
-- Emma AI · Phase 0 foundation — slice schema
-- Every core table carries facility_id (multi-tenancy; RLS added in next migration).
-- Scope: only the tables the Phase 1 thin slice needs. More tables (leave, agency,
-- rule builder, task codes, KPI, solver jobs) land in later phases.
-- ============================================================================

create extension if not exists pgcrypto;  -- gen_random_uuid()

-- ── Enums ───────────────────────────────────────────────────────────────────
create type staff_rank as enum ('RN','EN','HW','HCA','CW','PCW','AW','PTA','OTA');
create type employment_type as enum
    ('local_ft','local_pt','imported_labor','agency','outsource','casual');

-- ── facilities ──────────────────────────────────────────────────────────────
create table facilities (
    id                     uuid primary key default gen_random_uuid(),
    code                   text not null unique,              -- 'A', 'B'
    name                   text not null,
    type                   text,                              -- care-home type
    timezone               text not null default 'Asia/Hong_Kong',
    scheduling_cycle_days  int  not null default 28,          -- 28 (home A) or 30/31 (home B)
    created_at             timestamptz not null default now()
);

-- ── facility_units (wing / floor / ward / cubicle hierarchy) ─────────────────
create table facility_units (
    id             uuid primary key default gen_random_uuid(),
    facility_id    uuid not null references facilities(id) on delete cascade,
    parent_unit_id uuid references facility_units(id) on delete cascade,
    unit_type      text not null,                             -- wing|floor|ward|cubicle
    name           text not null,
    code           text,
    created_at     timestamptz not null default now()
);
create index idx_facility_units_facility on facility_units(facility_id);

-- ── staff ────────────────────────────────────────────────────────────────────
create table staff (
    id                        uuid primary key default gen_random_uuid(),
    facility_id               uuid not null references facilities(id) on delete cascade,
    name                      text not null,                  -- 中文
    name_en                   text,
    rank                      staff_rank not null,
    employment_type           employment_type not null,
    primary_unit_id           uuid references facility_units(id) on delete set null,
    contracted_hours          numeric,                        -- per week
    is_audited_for_medication boolean not null default false,
    is_mentor                 boolean not null default false,
    status                    text not null default 'active', -- active|inactive
    created_at                timestamptz not null default now()
);
create index idx_staff_facility on staff(facility_id);

-- ── staff_contracts (rest / hour rules — solver + compliance input) ──────────
create table staff_contracts (
    id                 uuid primary key default gen_random_uuid(),
    facility_id        uuid not null references facilities(id) on delete cascade,
    staff_id           uuid not null references staff(id) on delete cascade,
    weekly_hours       numeric,
    max_weekly_hours   numeric,
    min_rest_minutes   int not null default 720,              -- imported labour = 12h
    allowed_shift_types text[] not null default '{}',
    effective_from     date,
    effective_to       date,
    created_at         timestamptz not null default now()
);
create index idx_staff_contracts_staff on staff_contracts(staff_id);

-- ── users_profile (links Supabase auth.users -> facility + role) ─────────────
create table users_profile (
    id            uuid primary key default gen_random_uuid(),
    auth_user_id  uuid unique references auth.users(id) on delete cascade,
    facility_id   uuid references facilities(id) on delete cascade,
    email         text,
    role          text not null check (role in ('superintendent','admin','staff')),
    staff_id      uuid references staff(id) on delete set null,
    created_at    timestamptz not null default now()
);
create index idx_users_profile_facility on users_profile(facility_id);
create index idx_users_profile_auth on users_profile(auth_user_id);

-- ── shift_definitions (facility shift dictionary) ────────────────────────────
create table shift_definitions (
    id             uuid primary key default gen_random_uuid(),
    facility_id    uuid not null references facilities(id) on delete cascade,
    shift_type     text not null,                             -- A/B/E/P/N/AN/7A/9A/7P/OFF/AL/SLEEP/DO...
    label          text,
    start_time     time,
    end_time       time,
    cross_midnight boolean not null default false,
    paid_minutes   int,
    is_working     boolean not null default true,             -- OFF/AL/SLEEP/DO = false
    created_at     timestamptz not null default now(),
    unique (facility_id, shift_type)
);

-- ── roster_periods ────────────────────────────────────────────────────────────
create table roster_periods (
    id           uuid primary key default gen_random_uuid(),
    facility_id  uuid not null references facilities(id) on delete cascade,
    period_start date not null,
    period_end   date not null,
    cycle_type   text not null default '28day',               -- 28day|natural_month
    status       text not null default 'planning',            -- planning|locked
    created_at   timestamptz not null default now()
);
create index idx_roster_periods_facility on roster_periods(facility_id);

-- ── roster_versions (A/B/C + publish control) ────────────────────────────────
create table roster_versions (
    id           uuid primary key default gen_random_uuid(),
    facility_id  uuid not null references facilities(id) on delete cascade,
    period_id    uuid references roster_periods(id) on delete cascade,
    version_type text not null default 'manual',              -- manual|A|B|C
    label        text,
    status       text not null default 'draft' check (status in ('draft','published','archived')),
    created_by   uuid references users_profile(id) on delete set null,
    published_at timestamptz,
    created_at   timestamptz not null default now()
);
create index idx_roster_versions_period on roster_versions(period_id);

-- ── shifts (a scheduled slot: date + type + unit + requirement) ──────────────
create table shifts (
    id                uuid primary key default gen_random_uuid(),
    facility_id       uuid not null references facilities(id) on delete cascade,
    roster_version_id uuid references roster_versions(id) on delete cascade,
    date              date not null,
    shift_type        text not null,
    start_time        time,
    end_time          time,
    cross_midnight    boolean not null default false,
    unit_id           uuid references facility_units(id) on delete set null,
    required_rank     staff_rank,
    required_count    int not null default 1,
    is_working        boolean not null default true,
    created_at        timestamptz not null default now()
);
create index idx_shifts_version on shifts(roster_version_id);
create index idx_shifts_facility_date on shifts(facility_id, date);

-- ── shift_assignments (staff <-> shift slot) ─────────────────────────────────
create table shift_assignments (
    id          uuid primary key default gen_random_uuid(),
    facility_id uuid not null references facilities(id) on delete cascade,
    shift_id    uuid not null references shifts(id) on delete cascade,
    staff_id    uuid references staff(id) on delete set null,
    role        staff_rank,
    status      text not null default 'assigned',             -- assigned|confirmed|cancelled
    is_agency   boolean not null default false,
    tasks       text[] not null default '{}',                 -- task-code labels (A1-A8/P1-P6)
    created_at  timestamptz not null default now()
);
create index idx_assignments_shift on shift_assignments(shift_id);
create index idx_assignments_staff on shift_assignments(staff_id);

-- ── daily_resident_counts (denominator for staffing ratios) ──────────────────
create table daily_resident_counts (
    id             uuid primary key default gen_random_uuid(),
    facility_id    uuid not null references facilities(id) on delete cascade,
    date           date not null,
    unit_id        uuid references facility_units(id) on delete cascade,
    care_level     text,
    resident_count int not null,
    entered_by     uuid references users_profile(id) on delete set null,
    updated_at     timestamptz not null default now(),
    created_at     timestamptz not null default now(),
    unique (facility_id, date, unit_id, care_level)
);
create index idx_resident_counts_facility_date on daily_resident_counts(facility_id, date);

-- ── staffing_ratio_rules (configurable Code of Practice ratios) ──────────────
create table staffing_ratio_rules (
    id                      uuid primary key default gen_random_uuid(),
    facility_id             uuid references facilities(id) on delete cascade,  -- null = template
    facility_type           text,
    care_level              text,
    staff_rank              staff_rank,
    time_window_start       time not null,
    time_window_end         time not null,
    ratio_residents_per_staff int,                            -- e.g. 60 => 1:60
    min_staff_any_rank      int,                              -- e.g. night >= 2 any rank
    effective_from          date,
    active                  boolean not null default true,
    created_at              timestamptz not null default now()
);
create index idx_ratio_rules_facility on staffing_ratio_rules(facility_id);

-- ── calendar_days (PH / statutory / special-pay days) ────────────────────────
create table calendar_days (
    id                     uuid primary key default gen_random_uuid(),
    facility_id            uuid references facilities(id) on delete cascade,  -- null = all facilities
    date                   date not null,
    day_type               text not null default 'normal',    -- public_holiday|statutory_holiday|special_pay|normal
    holiday_name           text,
    is_agency_allowed      boolean not null default true,
    agency_cost_multiplier numeric not null default 1.0,
    staff_cost_multiplier  numeric not null default 1.0,
    notes                  text,
    created_at             timestamptz not null default now()
);
create index idx_calendar_days_facility_date on calendar_days(facility_id, date);

-- ── manual_override_log (feeds future AI-acceptance KPI) ─────────────────────
create table manual_override_log (
    id                 uuid primary key default gen_random_uuid(),
    facility_id        uuid not null references facilities(id) on delete cascade,
    roster_version_id  uuid references roster_versions(id) on delete cascade,
    shift_assignment_id uuid references shift_assignments(id) on delete set null,
    action             text not null,                         -- create|update|delete|assign|unassign
    before_json        jsonb,
    after_json         jsonb,
    changed_by         uuid references users_profile(id) on delete set null,
    reason             text,
    created_at         timestamptz not null default now()
);
create index idx_override_version on manual_override_log(roster_version_id);

-- ── roster_publish_events (publish / rollback audit) ─────────────────────────
create table roster_publish_events (
    id                uuid primary key default gen_random_uuid(),
    facility_id       uuid not null references facilities(id) on delete cascade,
    roster_version_id uuid not null references roster_versions(id) on delete cascade,
    event_type        text not null,                          -- save_draft|publish|rollback
    created_by        uuid references users_profile(id) on delete set null,
    created_at        timestamptz not null default now()
);
create index idx_publish_events_version on roster_publish_events(roster_version_id);
