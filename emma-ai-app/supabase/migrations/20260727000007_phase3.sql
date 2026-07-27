-- ============================================================================
-- Emma AI · Phase 3 — operations layer
--
-- Everything the Phase 3 screens (Dashboard, Approval, Alert, ROI, Reports,
-- Staff App) read is a real table here; nothing is computed from fixtures.
--
--   leave_requests        4.2  AL / day-off / duty requests + approval workflow
--   sl_incidents          4.3  urgent SL/DSL + emergency-cover close-loop
--   replacement_candidates 3.8 ranked, ratio-checked cover suggestions
--   future_debt_ledger    4.5  AN/CL/CO/OT debt created by emergency cover
--   notifications         4.4  in-app / email / WhatsApp fan-out
--   attendance_events          staff-app clock in / out
--   task_assignments      3.10 task-code assignment + completion status
--   agency_assignments    5.3  real agency cost — the Part B ROI denominator
--   roi_settings          5.1  per-facility configurable ROI baseline
--   reports / report_schedules  7.1 generated artefacts + the schedule registry
--   facility_events            event-trigger occurrences (admissions, incidents)
--   regulatory_documents       SWD regulatory-sync registry
--
-- Row-level security: standard own-facility scoping, except the staff-personal
-- tables, which additionally restrict a 'staff' role login to its own rows —
-- a staff app token must never be able to read a colleague's leave or roster.
-- ============================================================================

-- ── occupancy denominator for the <90% threshold monitor ─────────────────────
alter table facilities add column if not exists capacity int;

-- ── gender: required by the SWD night-shift gender distribution report ───────
alter table staff add column if not exists gender text
    check (gender is null or gender in ('M','F','other'));

-- ── RLS helpers (SECURITY DEFINER so policies don't recurse on users_profile) ─
create or replace function public.current_role_name()
returns text
language sql
stable
security definer
set search_path = public, auth
as $$
    select role from public.users_profile where auth_user_id = auth.uid() limit 1;
$$;

create or replace function public.current_staff_id()
returns uuid
language sql
stable
security definer
set search_path = public, auth
as $$
    select staff_id from public.users_profile where auth_user_id = auth.uid() limit 1;
$$;

-- True when the caller may see a row belonging to `row_staff_id`: managers see
-- the whole facility, a 'staff' login only itself.
create or replace function public.can_see_staff_row(row_staff_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, auth
as $$
    select public.current_role_name() is distinct from 'staff'
        or row_staff_id = public.current_staff_id();
$$;


-- ── leave_requests ───────────────────────────────────────────────────────────
create table if not exists leave_requests (
    id                   uuid primary key default gen_random_uuid(),
    facility_id          uuid not null references facilities(id) on delete cascade,
    staff_id             uuid not null references staff(id) on delete cascade,
    -- category drives the Approval page's three sub-tabs; leave_type is the detail
    category             text not null check (category in ('al','duty','sick')),
    leave_type           text not null,          -- AL|special|marriage|DO|duty_request|SL|DSL|urgent|late
    date_start           date not null,
    date_end             date not null,
    requested_shift_type text,                   -- duty requests: the shift asked for
    reason               text,
    remark               text,
    document_url         text,                   -- sick-leave certificate
    status               text not null default 'pending'
                         check (status in ('pending','reviewed','approved','rejected','cancelled')),
    reviewed_at          timestamptz,            -- set => UI shows "… & Reviewed"
    decided_by           uuid references users_profile(id) on delete set null,
    decided_at           timestamptz,
    decision_note        text,
    created_at           timestamptz not null default now()
);
create index if not exists idx_leave_requests_facility on leave_requests(facility_id, status);
create index if not exists idx_leave_requests_staff on leave_requests(staff_id);

-- ── sl_incidents (urgent SL/DSL — ROI A2 + Alert centre) ─────────────────────
create table if not exists sl_incidents (
    id                    uuid primary key default gen_random_uuid(),
    facility_id           uuid not null references facilities(id) on delete cascade,
    staff_id              uuid not null references staff(id) on delete cascade,
    shift_id              uuid references shifts(id) on delete set null,
    leave_request_id      uuid references leave_requests(id) on delete set null,
    incident_type         text not null default 'SL'
                          check (incident_type in ('SL','DSL','urgent','late')),
    reason                text,
    reported_at           timestamptz not null default now(),
    replacement_status    text not null default 'open'
                          check (replacement_status in ('open','notified','resolved','cancelled')),
    replacement_staff_id  uuid references staff(id) on delete set null,
    resolved_at           timestamptz,
    resolved_by           uuid references users_profile(id) on delete set null,
    resolution_minutes    int,                   -- reported_at -> resolved_at, for the avg-response KPI
    auto_resolved         boolean not null default false,  -- cover accepted from an Emma suggestion
    notes                 text,
    created_at            timestamptz not null default now()
);
create index if not exists idx_sl_incidents_facility on sl_incidents(facility_id, reported_at);
create index if not exists idx_sl_incidents_staff on sl_incidents(staff_id);

-- ── replacement_candidates (snapshot of the ranking shown to the manager) ────
create table if not exists replacement_candidates (
    id                 uuid primary key default gen_random_uuid(),
    facility_id        uuid not null references facilities(id) on delete cascade,
    incident_id        uuid not null references sl_incidents(id) on delete cascade,
    candidate_staff_id uuid not null references staff(id) on delete cascade,
    score              int not null default 0,
    rank_order         int not null default 0,
    compliance_ok      boolean not null default true,   -- passes the ratio/rest check
    blocked_reasons    jsonb not null default '[]'::jsonb,
    reasons            jsonb not null default '[]'::jsonb,  -- why it scored well
    future_debt_json   jsonb not null default '{}'::jsonb,
    created_at         timestamptz not null default now()
);
create index if not exists idx_replacement_candidates_incident on replacement_candidates(incident_id);

-- ── future_debt_ledger (AN / CL / CO / OT owed after emergency cover) ────────
create table if not exists future_debt_ledger (
    id                uuid primary key default gen_random_uuid(),
    facility_id       uuid not null references facilities(id) on delete cascade,
    staff_id          uuid not null references staff(id) on delete cascade,
    debt_type         text not null check (debt_type in ('AN','CL','CO','OT','TOIL')),
    quantity          numeric not null default 0,      -- hours (CL/CO/OT/TOIL) or count (AN)
    unit              text not null default 'hours',
    due_period_id     uuid references roster_periods(id) on delete set null,
    source_incident_id uuid references sl_incidents(id) on delete set null,
    status            text not null default 'open' check (status in ('open','settled','cancelled')),
    note              text,
    created_at        timestamptz not null default now(),
    settled_at        timestamptz
);
create index if not exists idx_future_debt_facility on future_debt_ledger(facility_id, status);
create index if not exists idx_future_debt_staff on future_debt_ledger(staff_id);

-- ── notifications ────────────────────────────────────────────────────────────
create table if not exists notifications (
    id            uuid primary key default gen_random_uuid(),
    facility_id   uuid not null references facilities(id) on delete cascade,
    staff_id      uuid references staff(id) on delete cascade,       -- recipient (staff app)
    profile_id    uuid references users_profile(id) on delete cascade, -- recipient (console)
    channel       text not null default 'in_app'
                  check (channel in ('in_app','email','whatsapp')),
    event_type    text not null,                 -- roster_published|leave_decided|cover_request|...
    title         text not null,
    body          text,
    related_type  text,
    related_id    uuid,
    status        text not null default 'queued'
                  check (status in ('queued','sent','read','failed')),
    sent_at       timestamptz,
    read_at       timestamptz,
    created_at    timestamptz not null default now()
);
create index if not exists idx_notifications_recipient on notifications(facility_id, staff_id, status);

-- ── attendance_events (staff-app clock in / out) ─────────────────────────────
create table if not exists attendance_events (
    id          uuid primary key default gen_random_uuid(),
    facility_id uuid not null references facilities(id) on delete cascade,
    staff_id    uuid not null references staff(id) on delete cascade,
    shift_id    uuid references shifts(id) on delete set null,
    event_type  text not null check (event_type in ('clock_in','clock_out')),
    event_at    timestamptz not null default now(),
    source      text not null default 'staff_app',
    note        text,
    created_at  timestamptz not null default now()
);
create index if not exists idx_attendance_staff_time on attendance_events(staff_id, event_at);

-- ── task_assignments (task codes per rostered shift + completion) ────────────
-- staff_id is denormalised from the shift assignment so RLS and the staff app
-- can filter without a join.
create table if not exists task_assignments (
    id                  uuid primary key default gen_random_uuid(),
    facility_id         uuid not null references facilities(id) on delete cascade,
    shift_assignment_id uuid not null references shift_assignments(id) on delete cascade,
    staff_id            uuid references staff(id) on delete set null,
    task_id             uuid references task_definitions(id) on delete set null,
    task_label          text not null,
    scheduled_time      time,
    priority            text not null default 'normal' check (priority in ('high','normal')),
    task_status         text not null default 'pending'
                        check (task_status in ('pending','done','skipped')),
    completed_at        timestamptz,
    completed_by        uuid references staff(id) on delete set null,
    created_at          timestamptz not null default now(),
    unique (shift_assignment_id, task_label)
);
create index if not exists idx_task_assignments_staff on task_assignments(staff_id);

-- ── agency_assignments (real agency spend — ROI Part B) ──────────────────────
create table if not exists agency_assignments (
    id                  uuid primary key default gen_random_uuid(),
    facility_id         uuid not null references facilities(id) on delete cascade,
    shift_id            uuid references shifts(id) on delete set null,
    shift_assignment_id uuid references shift_assignments(id) on delete set null,
    date                date not null,
    role                staff_rank,
    vendor              text,
    hours               numeric not null default 8,
    cost                numeric not null default 0,
    reason              text,
    created_at          timestamptz not null default now()
);
create index if not exists idx_agency_assignments_facility_date on agency_assignments(facility_id, date);

-- ── roi_settings (one configurable baseline per facility) ────────────────────
create table if not exists roi_settings (
    facility_id               uuid primary key references facilities(id) on delete cascade,
    manager_hourly_rate       numeric not null default 409,     -- HK$70,720 / 173h
    roster_hours_before       numeric not null default 26,      -- survey n=2 homes
    roster_hours_after        numeric not null default 7,
    hours_saved_per_incident  numeric not null default 0.75,
    agency_reduction_pct      numeric not null default 5,       -- conservative, SWD floor
    total_budget              numeric not null default 0,       -- monthly operating budget
    salary_budget             numeric not null default 0,
    contract_years            text not null default '5yr' check (contract_years in ('3yr','5yr','10yr')),
    -- {"RN": 1, "HCA": 2, …} — open posts per rank. Headcount itself is counted
    -- from the staff table; only the vacancies are an operator input.
    vacancies_json            jsonb not null default '{}'::jsonb,
    updated_by                uuid references users_profile(id) on delete set null,
    updated_at                timestamptz not null default now()
);

-- ── reports (generated artefacts) ────────────────────────────────────────────
create table if not exists reports (
    id           uuid primary key default gen_random_uuid(),
    facility_id  uuid not null references facilities(id) on delete cascade,
    report_type  text not null,                  -- staffing_ratio|compliance|roster_hours|...
    title        text not null,
    period_start date,
    period_end   date,
    format       text not null default 'json' check (format in ('json','csv','pdf','xlsx')),
    params_json  jsonb not null default '{}'::jsonb,
    payload_json jsonb,                          -- the report rows, so it stays reproducible
    row_count    int not null default 0,
    file_url     text,
    generated_by uuid references users_profile(id) on delete set null,
    created_at   timestamptz not null default now()
);
create index if not exists idx_reports_facility on reports(facility_id, created_at);

-- ── report_schedules (the Reports page "Scheduled" registry) ─────────────────
create table if not exists report_schedules (
    id             uuid primary key default gen_random_uuid(),
    facility_id    uuid not null references facilities(id) on delete cascade,
    report_type    text not null,
    icon           text,
    name_en        text not null,
    name_zh        text,
    cron_label_en  text,
    cron_label_zh  text,
    recipients_en  text[] not null default '{}',
    recipients_zh  text[] not null default '{}',
    content_en     text[] not null default '{}',
    content_zh     text[] not null default '{}',
    law_reference  text,
    last_run_at    date,
    next_run_at    date,
    active         boolean not null default true,
    sort_order     int not null default 0,
    created_at     timestamptz not null default now()
);
create index if not exists idx_report_schedules_facility on report_schedules(facility_id, sort_order);

-- ── event_trigger_rules + facility_events (Reports "Event Triggers" tab) ─────
create table if not exists event_trigger_rules (
    id            uuid primary key default gen_random_uuid(),
    facility_id   uuid not null references facilities(id) on delete cascade,
    trigger_code  text not null,                 -- matches facility_events.event_type
    icon          text,
    label_en      text not null,
    label_zh      text,
    action_en     text,
    action_zh     text,
    sla_en        text,
    sla_zh        text,
    law_reference text,
    active        boolean not null default true,
    sort_order    int not null default 0,
    created_at    timestamptz not null default now(),
    unique (facility_id, trigger_code)
);

create table if not exists facility_events (
    id          uuid primary key default gen_random_uuid(),
    facility_id uuid not null references facilities(id) on delete cascade,
    event_type  text not null,                   -- STAFF_JOIN_LEAVE|INCIDENT_REPORTED|...
    date        date not null,
    start_at    timestamptz,
    end_at      timestamptz,
    title       text,
    demand_json jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);
create index if not exists idx_facility_events_facility_date on facility_events(facility_id, date);

-- ── regulatory_documents (SWD regulatory sync registry) ──────────────────────
create table if not exists regulatory_documents (
    id             uuid primary key default gen_random_uuid(),
    facility_id    uuid references facilities(id) on delete cascade,   -- null = applies to all
    doc_code       text not null,
    name_en        text not null,
    name_zh        text,
    key_clause_en  text,
    key_clause_zh  text,
    source_url     text,
    version_label  text,
    last_synced_at date,
    sync_status    text not null default 'synced'
                   check (sync_status in ('synced','changed','error')),
    sort_order     int not null default 0,
    created_at     timestamptz not null default now()
);


-- ============================================================================
-- Row Level Security
-- ============================================================================

-- Staff-personal tables: own facility, and a 'staff' login only sees itself.
alter table leave_requests enable row level security;
drop policy if exists leave_requests_tenant on leave_requests;
create policy leave_requests_tenant on leave_requests for all to authenticated
    using (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id))
    with check (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id));

alter table sl_incidents enable row level security;
drop policy if exists sl_incidents_tenant on sl_incidents;
create policy sl_incidents_tenant on sl_incidents for all to authenticated
    using (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id))
    with check (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id));

alter table future_debt_ledger enable row level security;
drop policy if exists future_debt_ledger_tenant on future_debt_ledger;
create policy future_debt_ledger_tenant on future_debt_ledger for all to authenticated
    using (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id))
    with check (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id));

alter table notifications enable row level security;
drop policy if exists notifications_tenant on notifications;
create policy notifications_tenant on notifications for all to authenticated
    using (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id))
    with check (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id));

alter table attendance_events enable row level security;
drop policy if exists attendance_events_tenant on attendance_events;
create policy attendance_events_tenant on attendance_events for all to authenticated
    using (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id))
    with check (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id));

alter table task_assignments enable row level security;
drop policy if exists task_assignments_tenant on task_assignments;
create policy task_assignments_tenant on task_assignments for all to authenticated
    using (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id))
    with check (facility_id = public.current_facility_id() and public.can_see_staff_row(staff_id));

-- Facility-wide operational tables: standard own-facility scoping.
alter table replacement_candidates enable row level security;
drop policy if exists replacement_candidates_tenant on replacement_candidates;
create policy replacement_candidates_tenant on replacement_candidates for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table agency_assignments enable row level security;
drop policy if exists agency_assignments_tenant on agency_assignments;
create policy agency_assignments_tenant on agency_assignments for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table roi_settings enable row level security;
drop policy if exists roi_settings_tenant on roi_settings;
create policy roi_settings_tenant on roi_settings for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table reports enable row level security;
drop policy if exists reports_tenant on reports;
create policy reports_tenant on reports for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table report_schedules enable row level security;
drop policy if exists report_schedules_tenant on report_schedules;
create policy report_schedules_tenant on report_schedules for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table event_trigger_rules enable row level security;
drop policy if exists event_trigger_rules_tenant on event_trigger_rules;
create policy event_trigger_rules_tenant on event_trigger_rules for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table facility_events enable row level security;
drop policy if exists facility_events_tenant on facility_events;
create policy facility_events_tenant on facility_events for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

-- regulatory_documents also carries global rows (facility_id is null).
alter table regulatory_documents enable row level security;
drop policy if exists regulatory_documents_read on regulatory_documents;
create policy regulatory_documents_read on regulatory_documents for select to authenticated
    using (facility_id is null or facility_id = public.current_facility_id());
drop policy if exists regulatory_documents_write on regulatory_documents;
create policy regulatory_documents_write on regulatory_documents for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

-- Grants (RLS still filters rows; these are the table-level privileges).
grant select, insert, update, delete on
    leave_requests, sl_incidents, replacement_candidates, future_debt_ledger,
    notifications, attendance_events, task_assignments, agency_assignments,
    roi_settings, reports, report_schedules, event_trigger_rules,
    facility_events, regulatory_documents
to authenticated;
