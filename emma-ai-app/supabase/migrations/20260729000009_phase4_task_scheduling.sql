-- ============================================================================
-- Emma AI · Phase 4 — task-based scheduling
--
-- 4.1 Task codes and eligibility
-- 4.2 Event staffing overlays
-- 4.3 Floor/unit operational coverage
--
-- Existing Phase 3 tables are extended in place so staff-app task completion
-- and report event registries remain compatible. Every new tenant row carries
-- facility_id and is protected by the same database boundary as the rest of the
-- application.
-- ============================================================================

-- ── 4.1 staff qualifications + richer task definitions ─────────────────────
create table if not exists staff_qualifications (
    id                 uuid primary key default gen_random_uuid(),
    facility_id        uuid not null references facilities(id) on delete cascade,
    staff_id           uuid not null references staff(id) on delete cascade,
    qualification_type text not null,
    is_active          boolean not null default true,
    effective_from     date,
    expiry_date        date,
    notes              text,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    unique (staff_id, qualification_type, effective_from)
);
create index if not exists idx_staff_qualifications_staff
    on staff_qualifications(staff_id, is_active);
create index if not exists idx_staff_qualifications_facility
    on staff_qualifications(facility_id, qualification_type);

alter table task_definitions
    add column if not exists unit_id uuid references facility_units(id) on delete set null,
    add column if not exists description text,
    add column if not exists required_qualification_json jsonb not null default '{}'::jsonb,
    add column if not exists is_restricted boolean not null default false;

-- A1/P1 codes are rank-specific in the care-home source material, so the same
-- code may legitimately exist once for HW and once for CW/HCA.
alter table task_definitions
    drop constraint if exists task_definitions_facility_id_task_code_key;
create unique index if not exists uq_task_definitions_facility_code_rank
    on task_definitions (facility_id, task_code, required_rank)
    where facility_id is not null;

alter table task_assignments
    add column if not exists roster_version_id uuid references roster_versions(id) on delete cascade,
    add column if not exists start_at timestamptz,
    add column if not exists end_at timestamptz,
    add column if not exists source_type text not null default 'legacy_cell';

alter table task_assignments
    drop constraint if exists task_assignments_source_type_check;
alter table task_assignments
    add constraint task_assignments_source_type_check
    check (source_type in ('manual','event','solver','legacy_cell'));

update task_assignments ta
set roster_version_id = s.roster_version_id
from shift_assignments sa
join shifts s on s.id = sa.shift_id
where ta.shift_assignment_id = sa.id
  and ta.roster_version_id is null;

create index if not exists idx_task_assignments_version
    on task_assignments(roster_version_id);

-- ── 4.2 event demand overlays ────────────────────────────────────────────────
alter table facility_events
    add column if not exists unit_id uuid references facility_units(id) on delete set null,
    add column if not exists required_staffing_json jsonb not null default '[]'::jsonb,
    add column if not exists notes text,
    add column if not exists updated_at timestamptz not null default now();

create table if not exists event_staffing_requirements (
    id          uuid primary key default gen_random_uuid(),
    facility_id uuid not null references facilities(id) on delete cascade,
    event_id    uuid not null references facility_events(id) on delete cascade,
    -- Text intentionally supports alternatives such as "HW|EN" and "CW|HCA".
    rank        text not null,
    count       int not null check (count > 0),
    is_additive boolean not null default true,
    notes       text,
    created_at  timestamptz not null default now()
);
create index if not exists idx_event_staffing_requirements_event
    on event_staffing_requirements(event_id);
create index if not exists idx_facility_events_unit_date
    on facility_events(facility_id, unit_id, date);

-- ── 4.3 floor/unit coverage rules ────────────────────────────────────────────
create table if not exists floor_min_staffing_rules (
    id                uuid primary key default gen_random_uuid(),
    facility_id       uuid not null references facilities(id) on delete cascade,
    unit_id           uuid references facility_units(id) on delete cascade,
    floor             text,
    time_window_start time not null,
    time_window_end   time not null,
    rank              text not null,
    min_count         int not null check (min_count >= 0),
    condition_json    jsonb not null default '{}'::jsonb,
    active            boolean not null default true,
    effective_from    date,
    effective_to      date,
    created_at        timestamptz not null default now(),
    check (unit_id is not null or floor is not null)
);
create index if not exists idx_floor_min_staffing_rules_facility
    on floor_min_staffing_rules(facility_id, active);
create index if not exists idx_floor_min_staffing_rules_unit
    on floor_min_staffing_rules(unit_id);

-- Store structured evidence for deterministic Phase 4 validation. The original
-- columns stay intact for Phase 2/3 consumers.
alter table violation_log
    add column if not exists date date,
    add column if not exists unit_id uuid references facility_units(id) on delete set null,
    add column if not exists task_assignment_id uuid references task_assignments(id) on delete set null,
    add column if not exists event_id uuid references facility_events(id) on delete set null,
    add column if not exists details_json jsonb not null default '{}'::jsonb;

-- ── RLS ──────────────────────────────────────────────────────────────────────
alter table staff_qualifications enable row level security;
drop policy if exists staff_qualifications_tenant on staff_qualifications;
create policy staff_qualifications_tenant on staff_qualifications
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (
        facility_id = public.current_facility_id()
        and exists (
            select 1 from staff s
            where s.id = staff_qualifications.staff_id
              and s.facility_id = staff_qualifications.facility_id
        )
    );

alter table event_staffing_requirements enable row level security;
drop policy if exists event_staffing_requirements_tenant on event_staffing_requirements;
create policy event_staffing_requirements_tenant on event_staffing_requirements
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (
        facility_id = public.current_facility_id()
        and exists (
            select 1 from facility_events e
            where e.id = event_staffing_requirements.event_id
              and e.facility_id = event_staffing_requirements.facility_id
        )
    );

alter table floor_min_staffing_rules enable row level security;
drop policy if exists floor_min_staffing_rules_tenant on floor_min_staffing_rules;
create policy floor_min_staffing_rules_tenant on floor_min_staffing_rules
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (
        facility_id = public.current_facility_id()
        and (
            unit_id is null
            or exists (
                select 1 from facility_units u
                where u.id = floor_min_staffing_rules.unit_id
                  and u.facility_id = floor_min_staffing_rules.facility_id
            )
        )
    );

grant select, insert, update, delete on
    staff_qualifications,
    event_staffing_requirements,
    floor_min_staffing_rules
to authenticated;
