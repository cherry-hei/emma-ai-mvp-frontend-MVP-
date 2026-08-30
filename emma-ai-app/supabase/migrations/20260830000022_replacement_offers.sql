-- Emergency cover offers: manager asks, staff answer, manager commits.
--
-- The swap table next door is staff to staff. This one starts with a manager,
-- because nobody volunteers for a shift that is vacant because a colleague is
-- ill. Several people can be asked at once and the first yes does not win; the
-- manager still picks, which is why acceptance and approval are separate states.
create table if not exists replacement_offers (
    id               uuid primary key default gen_random_uuid(),
    facility_id      uuid not null references facilities(id) on delete cascade,
    incident_id      uuid not null references sl_incidents(id) on delete cascade,
    shift_id         uuid not null references shifts(id) on delete cascade,
    offered_staff_id uuid not null references staff(id) on delete cascade,
    offered_by       uuid references users_profile(id) on delete set null,
    -- What the engine said when the offer went out. Kept because the ranking is
    -- recomputed on every read, and a manager who is asked to justify a choice
    -- needs the numbers they actually saw.
    score            numeric,
    rank_required    text,
    note             text,
    status           text not null default 'pending' check (status in (
                         'pending',      -- waiting on the staff member
                         'accepted',     -- they said yes, manager has not committed
                         'declined',     -- they said no
                         'approved',     -- manager committed this one
                         'withdrawn',    -- manager pulled it
                         'superseded')), -- someone else got the shift
    responded_at     timestamptz,
    response_note    text,
    approved_by      uuid references users_profile(id) on delete set null,
    approved_at      timestamptz,
    created_at       timestamptz not null default now(),
    -- Asking the same person twice for the same shift is a double notification,
    -- not a second chance.
    constraint replacement_offer_is_unique unique (incident_id, offered_staff_id)
);

create index if not exists idx_replacement_offers_incident
    on replacement_offers(facility_id, incident_id, status);
create index if not exists idx_replacement_offers_staff
    on replacement_offers(offered_staff_id, status);

comment on table replacement_offers is
    'Manager offers emergency cover to staff. Accepting is not being assigned; the manager approves.';

-- Only one offer per incident can be the one that was acted on.
create unique index if not exists uniq_replacement_offer_approved
    on replacement_offers(incident_id) where status = 'approved';

alter table replacement_offers enable row level security;

drop policy if exists replacement_offers_tenant on replacement_offers;
create policy replacement_offers_tenant on replacement_offers
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

grant select, insert, update on replacement_offers to authenticated;
