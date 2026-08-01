-- ─────────────────────────────────────────────────────────────────────────────
-- MVP 4.1 · escort locations, and 2.2/2.3 · NAAC sequencing config
--
-- Cherry settled the open design question on ClickUp 4.1 (31 Jul 2026):
--
--   "The location code is per-assignment (attached to a specific staff member's
--    shift cell on a specific date), not per-task-definition. The same location
--    code can appear on different staff on different days."
--
-- So the column belongs on task_assignments, not task_definitions. The
-- dictionary of valid codes is facility-scoped reference data, in the same
-- shape as task_definitions: facility_id NULL means a shared template row.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── the code set ────────────────────────────────────────────────────────────
create table if not exists escort_locations (
    id           uuid primary key default gen_random_uuid(),
    facility_id  uuid references facilities(id) on delete cascade,
    code         text not null,                 -- TMH, CPH, POH, 深盲輔 …
    name_en      text,
    name_zh      text,
    -- Two NAAC places share TMH and two share CPH. The roster only ever writes
    -- the code, so `aliases` keeps every place that resolves to it without
    -- forcing the home to invent codes it does not use on paper.
    aliases      text[] not null default '{}',
    active       boolean not null default true,
    created_at   timestamptz not null default now(),
    unique (facility_id, code)
);
create index if not exists idx_escort_locations_facility on escort_locations(facility_id);

alter table escort_locations enable row level security;
create policy escort_locations_read on escort_locations for select to authenticated
    using (facility_id is null or facility_id = public.current_facility_id());
create policy escort_locations_write on escort_locations for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

-- ── the per-assignment location ─────────────────────────────────────────────
-- Text rather than a foreign key to escort_locations. A roster cell is imported
-- before the dictionary is necessarily complete, and refusing the import because
-- a home wrote a clinic we have not catalogued would lose real roster data to a
-- reference-data gap. `escort_location_id` resolves it when the code is known;
-- `escort_location` always keeps what the home actually wrote.
alter table task_assignments
    add column if not exists escort_location text,
    add column if not exists escort_location_id uuid
        references escort_locations(id) on delete set null;

create index if not exists idx_task_assignments_escort
    on task_assignments(escort_location) where escort_location is not null;

comment on column task_assignments.escort_location is
    'Medical-escort destination for THIS assignment on THIS date (Cherry, ClickUp 4.1, 31 Jul 2026). Roster cell format: shift_code + location_code, e.g. "A7 TMH".';

-- `needs_location` marks the task codes that are incomplete without one - the
-- escort and follow-up markers (f, 陪, 家). Validation reads it rather than
-- hardcoding a code list, so a home can add its own escort task.
alter table task_definitions
    add column if not exists needs_location boolean not null default false,
    add column if not exists task_category text,
    add column if not exists task_name_zh text;

-- ── NAAC's consecutive-day rules ────────────────────────────────────────────
-- Seeded as a rule_definition rather than written into the engine, because they
-- are this home's working practices and not statute. Homes A and B get no row
-- and the evaluator returns immediately for them.
--
-- AN → NO → O is deliberately absent: that is the existing `night_chain` rule,
-- which already requires a sleeping day then a day off after a night duty. NAAC
-- only differs in spelling the codes NO and O, so it is configured below and not
-- re-implemented.
insert into rule_definitions (facility_id, rule_code, severity, config_json, description)
select f.id, 'shift_sequence', 'hard', jsonb_build_object(
    'max_consecutive_working_days', 8,
    'forbidden_before', jsonb_build_array(
        jsonb_build_object(
            'shift', jsonb_build_array('AN', 'A7N*', 'G7SN*'),
            'forbidden', jsonb_build_array('P*'),
            'reason', 'A P shift the day before an AN double shift leaves too little rest; the home rosters A7, A1030 or A9 instead.')
    ),
    'forbidden_after', jsonb_build_array(
        jsonb_build_object(
            'shift', jsonb_build_array('A230*', '*E'),
            'forbidden', jsonb_build_array('A7', 'A7X', 'A7S', 'A7#'),
            'reason', 'A7 the morning after A230 or an E-position shift is too short a turnaround.')
    ),
    'no_consecutive', jsonb_build_array(
        jsonb_build_object(
            'codes', jsonb_build_array('A130', 'A230E'),
            'reason', 'Kitchen duty and the A230 E-position cannot fall on consecutive days.')
    )
), 'NAAC TAH rostering arrangement, section 3. Source: NAAC編更安排1.docx via ClickUp 2.2, 31 Jul 2026.'
from facilities f
where f.code = 'NAAC'
  and not exists (
      select 1 from rule_definitions r
      where r.facility_id = f.id and r.rule_code = 'shift_sequence'
  );

-- NAAC spells the post-night rest NO and the statutory rest day O, where the
-- other two homes write SLEEP/SD and DO/OFF. Same rule, different vocabulary.
insert into rule_definitions (facility_id, rule_code, severity, config_json, description)
select f.id, 'night_chain', 'hard', jsonb_build_object(
    'night_shift_types', jsonb_build_array('AN', 'N', 'N10', 'N1015', 'N1030', 'K10'),
    'sleep_codes', jsonb_build_array('NO'),
    'day_off_codes', jsonb_build_array('O', 'OFF', 'DO'),
    'chain_employment_types', jsonb_build_array('local_ft'),
    'an_monthly_limit', 0,
    'nurse_night_monthly_limit', 0,
    'cooldown_ranks', jsonb_build_array('RN', 'EN')
), 'NAAC AN → NO → O sequencing. Monthly limits set to 0 (off): NAAC caps night duty through the per-person # quota and the even-distribution rule, not a monthly count.'
from facilities f
where f.code = 'NAAC'
  and not exists (
      select 1 from rule_definitions r
      where r.facility_id = f.id and r.rule_code = 'night_chain'
  );
