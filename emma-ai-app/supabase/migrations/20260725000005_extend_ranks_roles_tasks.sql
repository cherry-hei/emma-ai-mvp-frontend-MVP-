-- ============================================================================
-- Emma AI · extend ranks + roles, add facility-configurable task codes
-- Client feedback (Phase 1.1 RBAC + task-code configurability):
--   • staff_rank enum was missing SW / PT / OT (therapists + social worker).
--   • users_profile.role CHECK admitted only superintendent/admin/staff - add
--     scheduler / hr / auditor.
--   • task codes must live in the DB per facility, not be hardcoded → task_definitions.
--
-- NOTE on ALTER TYPE ... ADD VALUE: on PG12+ this is allowed inside a migration
-- transaction; the only rule is the NEW value may not be *used* in the same
-- transaction. This migration only declares the values (and a column OF the type),
-- it never inserts a row using them, so it is safe.
-- ============================================================================

-- ── ranks: add SW / PT / OT ──────────────────────────────────────────────────
alter type staff_rank add value if not exists 'SW';
alter type staff_rank add value if not exists 'PT';
alter type staff_rank add value if not exists 'OT';

-- ── roles: scheduler / hr / auditor (Phase 1.1 RBAC) ─────────────────────────
alter table users_profile drop constraint if exists users_profile_role_check;
alter table users_profile add constraint users_profile_role_check
    check (role in ('superintendent','admin','staff','scheduler','hr','auditor'));

-- ── task_definitions: facility-scoped task-code dictionary ───────────────────
-- facility_id NULL = shared template row (readable by everyone signed in), same
-- pattern as staffing_ratio_rules / calendar_days. Feeds shift_assignments.tasks
-- and the shift-editor task dropdown so codes are configured, never hardcoded.
create table if not exists task_definitions (
    id             uuid primary key default gen_random_uuid(),
    facility_id    uuid references facilities(id) on delete cascade,
    task_code      text not null,                          -- A1-A8 / P1-P6 ...
    task_name      text,
    shift_type     text,                                   -- optional owning shift
    required_rank  staff_rank,
    requires_audit boolean not null default false,
    active         boolean not null default true,
    created_at     timestamptz not null default now(),
    unique (facility_id, task_code)
);
create index if not exists idx_task_definitions_facility on task_definitions(facility_id);

alter table task_definitions enable row level security;
create policy task_definitions_read on task_definitions for select to authenticated
    using (facility_id is null or facility_id = public.current_facility_id());
create policy task_definitions_write on task_definitions for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());
