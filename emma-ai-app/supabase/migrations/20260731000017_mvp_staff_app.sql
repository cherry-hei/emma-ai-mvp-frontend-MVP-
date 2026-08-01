-- Staff App PWA backend (spec SA.1, SA.3, SA.4, SA.5, SA.6).
--
-- Four concerns land together because they are one workflow seen from four
-- angles: a staff member asks for something (SA.1), works the day and reports
-- what actually happened (SA.3), the manager decides (SA.5), and both sides are
-- told (SA.4). Shift swap (SA.6) is the same loop with a third party in it.
--
-- What is deliberately NOT here: the certificate vault (SA.7). Its own ClickUp
-- description puts it in the Phase 5-8 backlog "to be quoted before Phase 5-8
-- starts", and building unquoted post-MVP work is the mistake this project has
-- already made once.

-- ── SA.3 · task exceptions ──────────────────────────────────────────────────
-- "Mark tasks as completed OR report exceptions with predefined reasons."
--
-- Why a table and not a `reason` column on task_assignments: a task can be
-- attempted, blocked, re-attempted and blocked again on the same shift. The
-- roster cell holds the current status; the exception log holds why, every
-- time, which is what a family complaint or an SWD query is actually asking.
--
-- Why the reason is a closed list: free text cannot be counted. "How often is
-- personal care refused on 2/F?" has to be answerable without reading prose.
alter table task_assignments drop constraint if exists task_assignments_task_status_check;
alter table task_assignments add constraint task_assignments_task_status_check
    check (task_status in ('pending', 'done', 'skipped', 'exception'));

create table if not exists task_exceptions (
    id                 uuid primary key default gen_random_uuid(),
    facility_id        uuid not null references facilities(id) on delete cascade,
    task_assignment_id uuid not null references task_assignments(id) on delete cascade,
    -- Who reported it, not who was assigned: a colleague covering the round is
    -- the one who saw it, and the audit needs the observer.
    reported_by        uuid references staff(id) on delete set null,
    reason_code        text not null check (reason_code in (
                           'resident_refused',
                           'resident_absent',
                           'clinical_hold',
                           'equipment_unavailable',
                           'insufficient_time',
                           'staff_reassigned',
                           'other')),
    -- 'other' defeats the point of a closed list unless it explains itself.
    note               text,
    reported_at        timestamptz not null default now(),
    constraint task_exception_other_needs_note
        check (reason_code <> 'other' or length(btrim(coalesce(note, ''))) > 0)
);

create index if not exists idx_task_exceptions_assignment
    on task_exceptions(task_assignment_id, reported_at desc);
create index if not exists idx_task_exceptions_facility
    on task_exceptions(facility_id, reported_at desc);

comment on table task_exceptions is
    'Every "could not do this task" event, with a countable reason. Append-only by policy.';

-- ── SA.5 · roster cell locks ────────────────────────────────────────────────
-- "On approval, the system automatically locks the corresponding roster cell to
--  the approved duty/day-off."
--
-- The solver already understands a lock (solver/inputs.py::LockedAssignment),
-- but only as a transient argument to one optimisation run. An approval is a
-- promise to a person and has to outlive the run that happens to be in flight,
-- so it is persisted here and read back on every solve.
--
-- date + shift_type rather than a shift_id FK, deliberately: an approved DO for
-- next month must constrain a roster that has not been drawn yet. Pointing at a
-- shift row would mean the lock could only exist after the thing it constrains.
create table if not exists roster_cell_locks (
    id               uuid primary key default gen_random_uuid(),
    facility_id      uuid not null references facilities(id) on delete cascade,
    staff_id         uuid not null references staff(id) on delete cascade,
    date             date not null,
    -- pin: this person works this shift_type. forbid: this person is not rostered
    -- at all that day (an approved day off).
    lock_type        text not null check (lock_type in ('pin', 'forbid')),
    shift_type       text,
    source_table     text not null check (source_table in ('leave_requests', 'swap_requests')),
    source_id        uuid not null,
    locked_by        uuid references users_profile(id) on delete set null,
    created_at       timestamptz not null default now(),
    -- Released, never deleted: "why was this person off on the 12th?" must stay
    -- answerable after the approval is revoked.
    released_at      timestamptz,
    released_by      uuid references users_profile(id) on delete set null,
    release_reason   text,
    constraint pin_needs_shift_type
        check (lock_type <> 'pin' or shift_type is not null),
    constraint forbid_has_no_shift_type
        check (lock_type <> 'forbid' or shift_type is null)
);

-- One live lock per person per day. Two approvals that both claim the same cell
-- is a contradiction the approver has to resolve, not something to store twice.
create unique index if not exists uq_live_roster_cell_lock
    on roster_cell_locks(facility_id, staff_id, date) where released_at is null;
create index if not exists idx_roster_cell_locks_source
    on roster_cell_locks(source_table, source_id);

comment on table roster_cell_locks is
    'Approved duty/day-off decisions the optimiser must honour. Survives re-solve.';

-- ── SA.6 · shift swap ───────────────────────────────────────────────────────
-- "Staff A initiates swap with Staff B; B accepts/declines; if accepted, manager
--  gives final approval. On approval both roster cells are swapped and locked."
--
-- Three parties means three separate consents, and the order matters: a manager
-- must never be asked to approve a swap the counterparty has not agreed to. The
-- status column is the state machine that enforces the order; `peer_response`
-- and `manager_*` are recorded separately so a decline by B and a rejection by
-- the manager are distinguishable months later.
create table if not exists swap_requests (
    id                     uuid primary key default gen_random_uuid(),
    facility_id            uuid not null references facilities(id) on delete cascade,
    requester_staff_id     uuid not null references staff(id) on delete cascade,
    requester_shift_id     uuid not null references shifts(id) on delete cascade,
    counterparty_staff_id  uuid not null references staff(id) on delete cascade,
    counterparty_shift_id  uuid not null references shifts(id) on delete cascade,
    reason                 text,
    status                 text not null default 'pending_peer' check (status in (
                               'pending_peer',      -- waiting on B
                               'pending_manager',   -- B agreed, waiting on the manager
                               'approved',
                               'declined',          -- B said no
                               'rejected',          -- the manager said no
                               'cancelled')),       -- A withdrew it
    peer_responded_at      timestamptz,
    peer_response_note     text,
    manager_decided_by     uuid references users_profile(id) on delete set null,
    manager_decided_at     timestamptz,
    manager_note           text,
    created_at             timestamptz not null default now(),
    -- Swapping with yourself is not a swap; it is an edit, and there is an
    -- endpoint for that.
    constraint swap_parties_differ check (requester_staff_id <> counterparty_staff_id),
    constraint swap_shifts_differ  check (requester_shift_id <> counterparty_shift_id)
);

create index if not exists idx_swap_requests_facility
    on swap_requests(facility_id, status, created_at desc);
create index if not exists idx_swap_requests_requester on swap_requests(requester_staff_id);
create index if not exists idx_swap_requests_counterparty on swap_requests(counterparty_staff_id);

comment on table swap_requests is
    'Three-party shift swap: requester -> counterparty -> manager. Order is enforced by status.';

-- ── SA.4 · push subscriptions ───────────────────────────────────────────────
-- Device registrations for Firebase Cloud Messaging. The row exists whether or
-- not FCM credentials have been provisioned: the PWA can register from day one,
-- and the delivery worker starts finding recipients the moment the project key
-- lands. The manager side of SA.4 is Server-Sent Events, which needs no table -
-- it reads `notifications`, which already exists.
create table if not exists push_subscriptions (
    id           uuid primary key default gen_random_uuid(),
    facility_id  uuid not null references facilities(id) on delete cascade,
    staff_id     uuid references staff(id) on delete cascade,
    profile_id   uuid references users_profile(id) on delete cascade,
    platform     text not null default 'web' check (platform in ('web', 'ios', 'android')),
    -- The FCM registration token. Unique because the same device re-registering
    -- must update its row, not accumulate duplicates that each get a push.
    token        text not null unique,
    user_agent   text,
    created_at   timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    revoked_at   timestamptz,
    -- A subscription with no recipient can never be delivered.
    constraint push_subscription_has_a_recipient
        check (staff_id is not null or profile_id is not null)
);

create index if not exists idx_push_subscriptions_recipient
    on push_subscriptions(facility_id, staff_id) where revoked_at is null;

comment on table push_subscriptions is
    'FCM device tokens. Rows are valid before FCM is provisioned; delivery is a worker concern.';

-- ── RLS ─────────────────────────────────────────────────────────────────────
-- Tenant boundary in the database, role rules in the API against the permission
-- matrix - the same split migration 16 explains. RLS is the part that must hold
-- even when the API is wrong.
alter table task_exceptions   enable row level security;
alter table roster_cell_locks enable row level security;
alter table swap_requests     enable row level security;
alter table push_subscriptions enable row level security;

drop policy if exists task_exceptions_tenant on task_exceptions;
create policy task_exceptions_tenant on task_exceptions
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

drop policy if exists roster_cell_locks_tenant on roster_cell_locks;
create policy roster_cell_locks_tenant on roster_cell_locks
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

drop policy if exists swap_requests_tenant on swap_requests;
create policy swap_requests_tenant on swap_requests
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

drop policy if exists push_subscriptions_tenant on push_subscriptions;
create policy push_subscriptions_tenant on push_subscriptions
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

grant select, insert         on task_exceptions    to authenticated;
grant select, insert, update on roster_cell_locks  to authenticated;
grant select, insert, update on swap_requests      to authenticated;
grant select, insert, update on push_subscriptions to authenticated;

-- ── an exception report is not editable history ─────────────────────────────
-- Same reasoning as audit_logs and request_recommendations: a reason rewritten
-- after the manager read it makes the record useless as evidence. A correction
-- is a second report.
create or replace function trg_task_exception_append_only()
returns trigger language plpgsql as $$
begin
    raise exception
        'task_exceptions is append-only; report a further exception instead';
end;
$$;

drop trigger if exists protect_task_exceptions on task_exceptions;
create trigger protect_task_exceptions
    before update or delete on task_exceptions
    for each row execute function trg_task_exception_append_only();
