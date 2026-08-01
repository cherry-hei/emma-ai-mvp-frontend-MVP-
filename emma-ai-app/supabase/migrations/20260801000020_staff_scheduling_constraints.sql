-- ─────────────────────────────────────────────────────────────────────────────
-- Per-person scheduling constraints and quotas
--
-- Cherry, 1 Aug 2026:
--
--   "the personal constraints (like 'STAFF_001 cannot do N shift') should be
--    stored as configurable rules in the DB (not hardcoded in any config file),
--    so that the OWNER can update them via the admin UI in future without a code
--    change."
--
-- This is the table that makes that true. Three things drove the shape:
--
-- 1. It is employee personal data. NAAC編更安排1.docx names five people - three
--    with a personal '#' quota (15/13/9 against the nurses' 12), one who may not
--    take N shifts, one who asks for fewer A shifts. Those names were redacted
--    from the committed copy; this table is where the real mapping lives, behind
--    the same RLS as every other tenant table.
--
-- 2. A preference and a prohibition are not the same thing and must not be
--    stored as if they were. "Su Hua requests fewer A shifts" is a wish the
--    optimiser should weigh; "Pan Jianmin must not be assigned N shifts" is a
--    line the roster may not cross. Collapsing both into "constraint" would
--    either turn a preference into a hard block, or - far worse - let a solver
--    trade away a prohibition because the objective function found it cheap.
--    `enforcement` keeps them apart.
--
-- 3. Someone has to be able to say why. A constraint with no reason and no
--    author becomes folklore: in a year nobody remembers whether the night-shift
--    exclusion was a medical restriction, a caring commitment or a favour, and
--    nobody dares remove it.
-- ─────────────────────────────────────────────────────────────────────────────

create table if not exists staff_scheduling_constraints (
    id              uuid primary key default gen_random_uuid(),
    facility_id     uuid not null references facilities(id) on delete cascade,
    staff_id        uuid not null references staff(id) on delete cascade,

    -- What kind of rule this is.
    --   forbid_shift    this person may not be assigned these shift codes
    --   require_quota   this person owes exactly N of something per cycle
    --                   (the NAAC '#' duty-supervisor allocation)
    --   prefer_less     weigh against assigning these codes, do not forbid
    --   prefer_more     weigh in favour
    constraint_type text not null check (constraint_type in
        ('forbid_shift', 'require_quota', 'prefer_less', 'prefer_more')),

    -- 'hard' may never be violated; 'soft' is an objective-function term.
    -- Derived from constraint_type on write, but stored, because the compliance
    -- engine filters on it and must not have to know the type taxonomy.
    enforcement     text not null default 'soft'
                    check (enforcement in ('hard', 'soft')),

    -- The shift or task codes this applies to. Empty means "all", which is only
    -- meaningful for a quota.
    codes           text[] not null default '{}',

    -- For require_quota: how many per cycle. NAAC's '#' numbers live here.
    target_count    integer check (target_count is null or target_count >= 0),
    weight          numeric not null default 1.0 check (weight >= 0),

    -- Effective-dated, like every other rule in this system: a constraint that
    -- ended in March must not silently invalidate March's roster when someone
    -- re-runs validation in June.
    effective_from  date,
    effective_to    date,
    active          boolean not null default true,

    -- Why, who, and when. See point 3 above.
    reason          text,
    created_by      uuid references users_profile(id) on delete set null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    check (effective_to is null or effective_from is null
           or effective_to >= effective_from),
    check (constraint_type <> 'require_quota' or target_count is not null),
    check (constraint_type = 'require_quota' or cardinality(codes) > 0)
);

create index if not exists idx_staff_constraints_staff
    on staff_scheduling_constraints(staff_id) where active;
create index if not exists idx_staff_constraints_facility
    on staff_scheduling_constraints(facility_id, constraint_type) where active;

alter table staff_scheduling_constraints enable row level security;

-- Read is open to anyone in the facility who can already see the roster: the
-- solver, the validator and the roster grid all need it, and the constraint is
-- visible on the grid anyway the moment it takes effect.
create policy staff_constraints_read on staff_scheduling_constraints
    for select to authenticated
    using (facility_id = public.current_facility_id());

-- Writes are not restricted at the RLS layer beyond tenancy; the API gates them
-- on Feature.FACILITY_SETTINGS, which is OWNER-only. Doing it there rather than
-- here keeps one answer to "who may change this" - the permission matrix - and
-- avoids a second, silently diverging copy of the rule in SQL.
create policy staff_constraints_write on staff_scheduling_constraints
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

grant select, insert, update, delete on staff_scheduling_constraints to authenticated;

comment on table staff_scheduling_constraints is
    'Per-person scheduling rules and quotas. Employee personal data - never committed to the repository as fixtures (Cherry, 1 Aug 2026). OWNER-editable so a change needs no deploy.';
comment on column staff_scheduling_constraints.enforcement is
    'hard = the roster may not violate it; soft = the optimiser weighs it. A preference stored as hard blocks a legal roster; a prohibition stored as soft gets traded away.';
