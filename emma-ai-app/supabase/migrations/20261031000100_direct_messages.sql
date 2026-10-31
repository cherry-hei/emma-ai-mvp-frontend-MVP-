-- ============================================================================
-- Emma AI · bounded direct messages
--
-- Direct messaging is deliberately a narrow, facility-local feature:
--   * every participant has an active, staff-linked profile from auth.uid();
--   * both profiles must share facility, organisation, and primary unit;
--   * browser clients may SELECT their own messages only; writes happen through
--     authenticated SECURITY DEFINER RPCs that verify auth.uid(), never a
--     service-role API client;
--   * message content/participants/scope are immutable and receipt writes are
--     possible only through mark_direct_message_read().
-- ============================================================================

-- This helper is intentionally narrow: it derives a profile only from the
-- authenticated JWT. It does not grant profile-directory access.
create or replace function public.current_profile_id()
returns uuid
language sql
stable
security definer
set search_path = public, auth
as $$
    select up.id
      from public.users_profile up
     where up.auth_user_id = auth.uid()
     limit 1;
$$;

revoke all on function public.current_profile_id() from public;
grant execute on function public.current_profile_id() to authenticated;

-- A profile is eligible for this feature only when its DB role is known, its
-- login and staff link are current, its staff record is active, and the linked
-- unit belongs to the same facility. This is intentionally stricter than the
-- pre-existing facility-wide users_profile SELECT policy.
create or replace function public.direct_message_profile_scope(p_profile_id uuid)
returns table (
    profile_id uuid,
    facility_id uuid,
    org_id uuid,
    unit_id uuid
)
language sql
stable
security definer
set search_path = public, auth
as $$
    select up.id, up.facility_id, up.org_id, st.primary_unit_id
      from public.users_profile up
      join public.staff st
        on st.id = up.staff_id
       and st.facility_id = up.facility_id
       and st.status = 'active'
      join public.facilities f
        on f.id = up.facility_id
       and f.org_id = up.org_id
      join public.facility_units u
        on u.id = st.primary_unit_id
       and u.facility_id = up.facility_id
     where up.id = p_profile_id
       and up.auth_user_id is not null
       and up.facility_id is not null
       and up.org_id is not null
       and up.role in (
           'superintendent', 'admin', 'staff', 'scheduler', 'hr', 'auditor',
           'OWNER', 'NURSE_MGR', 'ALLIED_HEALTH', 'ADMIN_CLERK', 'SCHEDULER',
           'FRONTLINE', 'HR_AUDITOR'
       );
$$;

revoke all on function public.direct_message_profile_scope(uuid)
from public, anon, authenticated;

-- Participant-only reads must respect *current* scope, not merely the scope at
-- send time. A unit transfer or inactivation hides a former peer's history.
-- The caller must be one of the two profiles, so this is not a directory lookup.
create or replace function public.current_user_can_read_direct_message(
    p_sender_profile_id uuid,
    p_recipient_profile_id uuid,
    p_facility_id uuid,
    p_org_id uuid
)
returns boolean
language plpgsql
stable
security definer
set search_path = pg_catalog, public, auth
as $$
declare
    caller_scope record;
    sender_scope record;
    recipient_scope record;
begin
    if auth.uid() is null or auth.role() is distinct from 'authenticated' then
        return false;
    end if;
    select * into caller_scope
      from public.direct_message_profile_scope(public.current_profile_id());
    if caller_scope.profile_id is null
       or caller_scope.profile_id not in (p_sender_profile_id, p_recipient_profile_id) then
        return false;
    end if;
    select * into sender_scope
      from public.direct_message_profile_scope(p_sender_profile_id);
    select * into recipient_scope
      from public.direct_message_profile_scope(p_recipient_profile_id);
    return sender_scope.profile_id is not null
       and recipient_scope.profile_id is not null
       and sender_scope.facility_id = recipient_scope.facility_id
       and sender_scope.org_id = recipient_scope.org_id
       and sender_scope.unit_id = recipient_scope.unit_id
       and p_facility_id = sender_scope.facility_id
       and p_org_id = sender_scope.org_id;
end;
$$;

revoke all on function public.current_user_can_read_direct_message(uuid, uuid, uuid, uuid)
from public, anon;
grant execute on function public.current_user_can_read_direct_message(uuid, uuid, uuid, uuid)
to authenticated;

create table if not exists direct_messages (
    id                   uuid primary key default gen_random_uuid(),
    facility_id          uuid not null references facilities(id) on delete cascade,
    org_id               uuid not null references organisations(id) on delete restrict,
    sender_profile_id    uuid not null references users_profile(id) on delete restrict,
    recipient_profile_id uuid not null references users_profile(id) on delete restrict,
    body                 text not null,
    client_message_id    uuid,
    created_at           timestamptz not null default now(),
    read_at              timestamptz,
    constraint direct_messages_distinct_participants
        check (sender_profile_id <> recipient_profile_id),
    constraint direct_messages_body_not_blank
        check (length(btrim(body)) > 0),
    constraint direct_messages_body_max_length
        check (char_length(body) <= 4000),
    constraint direct_messages_read_after_send
        check (read_at is null or read_at >= created_at)
);

-- Replayed POSTs from one sender resolve to the one durable row. NULL means the
-- legacy/current client did not send an idempotency key and is deliberately not
-- collapsed with another NULL request.
create unique index if not exists uq_direct_messages_sender_client_message
    on direct_messages(sender_profile_id, client_message_id)
    where client_message_id is not null;
create index if not exists idx_direct_messages_participant_created
    on direct_messages(facility_id, sender_profile_id, created_at desc);
create index if not exists idx_direct_messages_recipient_created
    on direct_messages(facility_id, recipient_profile_id, created_at desc);

comment on table direct_messages is
    'Facility/org/unit-scoped direct messages. Content and identity are immutable; recipient read_at is set only by a secured RPC.';

-- The audit intentionally stores event metadata rather than a second copy of
-- message body. It is protected evidence, not an activity-feed API.
create table if not exists direct_message_audit (
    id               uuid primary key default gen_random_uuid(),
    message_id       uuid not null references direct_messages(id) on delete restrict,
    facility_id      uuid not null references facilities(id) on delete cascade,
    org_id           uuid not null references organisations(id) on delete restrict,
    actor_profile_id uuid not null references users_profile(id) on delete restrict,
    action           text not null check (action in ('sent', 'read')),
    created_at       timestamptz not null default now()
);
create index if not exists idx_direct_message_audit_message_created
    on direct_message_audit(message_id, created_at);

comment on table direct_message_audit is
    'Append-only direct-message event evidence. Message bodies are not duplicated into audit records.';

-- DB-level defence in depth: even a future caller granted INSERT cannot create a
-- cross-facility/org/unit pair or write a scope inconsistent with participants.
create or replace function public.validate_direct_message_participants()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, auth
as $$
declare
    sender_scope record;
    recipient_scope record;
begin
    select * into sender_scope
      from public.direct_message_profile_scope(new.sender_profile_id);
    select * into recipient_scope
      from public.direct_message_profile_scope(new.recipient_profile_id);

    if sender_scope.profile_id is null
       or recipient_scope.profile_id is null
       or sender_scope.facility_id <> recipient_scope.facility_id
       or sender_scope.org_id <> recipient_scope.org_id
       or sender_scope.unit_id <> recipient_scope.unit_id
       or new.facility_id <> sender_scope.facility_id
       or new.org_id <> sender_scope.org_id then
        raise exception using
            errcode = '42501',
            message = 'direct-message participants are not eligible peers';
    end if;
    return new;
end;
$$;

revoke all on function public.validate_direct_message_participants() from public;

drop trigger if exists trg_validate_direct_message_participants on direct_messages;
create trigger trg_validate_direct_message_participants
before insert on direct_messages
for each row execute function public.validate_direct_message_participants();

-- Read receipts can only transition NULL -> timestamp while a secured RPC has
-- installed its transaction-local guard. Nothing else on the message may change,
-- and messages cannot be deleted. The table's authenticated UPDATE privilege is
-- revoked below; this guard additionally protects against a future broad grant.
create or replace function public.protect_direct_message()
returns trigger
language plpgsql
set search_path = pg_catalog, public, auth
as $$
begin
    if tg_op = 'DELETE' then
        raise exception using
            errcode = '42501',
            message = 'direct messages cannot be deleted';
    end if;

    if current_setting('emma.direct_message_read_guard', true) is distinct from 'allowed'
       or old.read_at is not null
       or new.read_at is null
       or new.read_at < old.created_at
       or (old.id, old.facility_id, old.org_id, old.sender_profile_id,
           old.recipient_profile_id, old.body, old.client_message_id,
           old.created_at) is distinct from
          (new.id, new.facility_id, new.org_id, new.sender_profile_id,
           new.recipient_profile_id, new.body, new.client_message_id,
           new.created_at) then
        raise exception using
            errcode = '42501',
            message = 'direct message content and identity are immutable';
    end if;
    return new;
end;
$$;

revoke all on function public.protect_direct_message() from public;

drop trigger if exists trg_protect_direct_message on direct_messages;
create trigger trg_protect_direct_message
before update or delete on direct_messages
for each row execute function public.protect_direct_message();

create or replace function public.protect_direct_message_audit()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    raise exception using
        errcode = '42501',
        message = 'direct_message_audit is append-only';
end;
$$;

revoke all on function public.protect_direct_message_audit() from public;

drop trigger if exists trg_protect_direct_message_audit on direct_message_audit;
create trigger trg_protect_direct_message_audit
before update or delete on direct_message_audit
for each row execute function public.protect_direct_message_audit();

-- Participant-only reads. The nested scope proof ensures invalid, unlinked,
-- inactive, unknown-role, or unitless callers fail closed even if they retain a
-- profile row and a JWT after an administrative change.
alter table direct_messages enable row level security;
alter table direct_message_audit enable row level security;

drop policy if exists direct_messages_select_participant on direct_messages;
create policy direct_messages_select_participant on direct_messages
    for select to authenticated
    using (
        facility_id = public.current_facility_id()
        and (sender_profile_id = public.current_profile_id()
             or recipient_profile_id = public.current_profile_id())
        and public.current_user_can_read_direct_message(
            sender_profile_id, recipient_profile_id, facility_id, org_id
        )
    );

-- These policies document the least privilege shape even though table DML is
-- revoked from authenticated below and real writes use the secured RPCs. The
-- insert trigger validates the peer relationship; the update trigger permits
-- only the RPC's guarded NULL -> read_at transition.
drop policy if exists direct_messages_insert_sender on direct_messages;
create policy direct_messages_insert_sender on direct_messages
    for insert to authenticated
    with check (
        sender_profile_id = public.current_profile_id()
        and facility_id = public.current_facility_id()
        and public.current_user_can_read_direct_message(
            sender_profile_id, recipient_profile_id, facility_id, org_id
        )
    );

drop policy if exists direct_messages_update_recipient on direct_messages;
create policy direct_messages_update_recipient on direct_messages
    for update to authenticated
    using (
        recipient_profile_id = public.current_profile_id()
        and facility_id = public.current_facility_id()
        and public.current_user_can_read_direct_message(
            sender_profile_id, recipient_profile_id, facility_id, org_id
        )
    )
    with check (
        recipient_profile_id = public.current_profile_id()
        and facility_id = public.current_facility_id()
        and public.current_user_can_read_direct_message(
            sender_profile_id, recipient_profile_id, facility_id, org_id
        )
    );

-- No audit policy or authenticated audit grant: only the secured transactional
-- RPCs write it, and service-role review can read it under Supabase's own role.

-- Contacts are emitted by this DB function so application code never reads a
-- broad profile directory. It returns exactly the frontend contact contract.
create or replace function public.list_direct_message_contacts()
returns table (
    id uuid,
    display_name text,
    role text,
    staff_id uuid
)
language plpgsql
security definer
set search_path = pg_catalog, public, auth
as $$
declare
    caller_scope record;
begin
    if auth.uid() is null or auth.role() is distinct from 'authenticated' then
        raise exception using errcode = '42501', message = 'authentication required';
    end if;

    select * into caller_scope
      from public.direct_message_profile_scope(public.current_profile_id());
    if caller_scope.profile_id is null then
        raise exception using
            errcode = '42501',
            message = 'direct-message profile is not eligible';
    end if;

    return query
    select up.id,
           coalesce(nullif(btrim(st.name), ''), nullif(btrim(st.name_en), '')),
           up.role,
           up.staff_id
      from public.users_profile up
      join public.staff st
        on st.id = up.staff_id
       and st.facility_id = up.facility_id
       and st.status = 'active'
      join public.facilities f
        on f.id = up.facility_id
       and f.org_id = up.org_id
      join public.facility_units u
        on u.id = st.primary_unit_id
       and u.facility_id = up.facility_id
     where up.id <> caller_scope.profile_id
       and up.facility_id = caller_scope.facility_id
       and up.org_id = caller_scope.org_id
       and st.primary_unit_id = caller_scope.unit_id
       and up.auth_user_id is not null
       and up.role in (
           'superintendent', 'admin', 'staff', 'scheduler', 'hr', 'auditor',
           'OWNER', 'NURSE_MGR', 'ALLIED_HEALTH', 'ADMIN_CLERK', 'SCHEDULER',
           'FRONTLINE', 'HR_AUDITOR'
       )
       and coalesce(nullif(btrim(st.name), ''), nullif(btrim(st.name_en), '')) is not null
     order by lower(coalesce(nullif(btrim(st.name), ''), nullif(btrim(st.name_en), ''))),
              up.id;
end;
$$;

-- A retry-safe, all-or-nothing write: advisory serialization makes the
-- select/return-or-insert sequence safe for concurrent retries sharing a
-- sender/client UUID, while the unique index remains the durable backstop.
create or replace function public.send_direct_message(
    p_recipient_profile_id uuid,
    p_body text,
    p_client_message_id uuid default null
)
returns setof direct_messages
language plpgsql
security definer
set search_path = pg_catalog, public, auth
as $$
declare
    caller_scope record;
    recipient_scope record;
    existing direct_messages%rowtype;
    created direct_messages%rowtype;
begin
    if auth.uid() is null or auth.role() is distinct from 'authenticated' then
        raise exception using errcode = '42501', message = 'authentication required';
    end if;
    if p_recipient_profile_id is null
       or p_body is null
       or length(btrim(p_body)) = 0
       or char_length(p_body) > 4000 then
        raise exception using errcode = '22023', message = 'invalid direct-message payload';
    end if;

    select * into caller_scope
      from public.direct_message_profile_scope(public.current_profile_id());
    select * into recipient_scope
      from public.direct_message_profile_scope(p_recipient_profile_id);
    if caller_scope.profile_id is null
       or recipient_scope.profile_id is null
       or caller_scope.profile_id = recipient_scope.profile_id
       or caller_scope.facility_id <> recipient_scope.facility_id
       or caller_scope.org_id <> recipient_scope.org_id
       or caller_scope.unit_id <> recipient_scope.unit_id then
        -- One refusal avoids turning POST into a profile/facility/unit oracle.
        raise exception using
            errcode = '42501',
            message = 'recipient is not an eligible direct-message contact';
    end if;

    if p_client_message_id is not null then
        perform pg_advisory_xact_lock(
            hashtext(caller_scope.profile_id::text || ':' || p_client_message_id::text)
        );
        select * into existing
          from public.direct_messages
         where sender_profile_id = caller_scope.profile_id
           and client_message_id = p_client_message_id
         for update;
        if found then
            if existing.recipient_profile_id <> p_recipient_profile_id
               or existing.body <> p_body then
                raise exception using
                    errcode = '23505',
                    message = 'client_message_id was already used for different content';
            end if;
            return next existing;
            return;
        end if;
    end if;

    insert into public.direct_messages (
        facility_id, org_id, sender_profile_id, recipient_profile_id, body,
        client_message_id
    ) values (
        caller_scope.facility_id, caller_scope.org_id, caller_scope.profile_id,
        recipient_scope.profile_id, p_body, p_client_message_id
    ) returning * into created;

    insert into public.direct_message_audit (
        message_id, facility_id, org_id, actor_profile_id, action
    ) values (
        created.id, created.facility_id, created.org_id, caller_scope.profile_id, 'sent'
    );

    return next created;
end;
$$;

create or replace function public.mark_direct_message_read(p_message_id uuid)
returns setof direct_messages
language plpgsql
security definer
set search_path = pg_catalog, public, auth
as $$
declare
    caller_scope record;
    target direct_messages%rowtype;
begin
    if auth.uid() is null or auth.role() is distinct from 'authenticated' then
        raise exception using errcode = '42501', message = 'authentication required';
    end if;

    select * into caller_scope
      from public.direct_message_profile_scope(public.current_profile_id());
    if caller_scope.profile_id is null then
        raise exception using
            errcode = '42501',
            message = 'direct-message profile is not eligible';
    end if;

    select * into target
      from public.direct_messages
     where id = p_message_id
       and facility_id = caller_scope.facility_id
       and org_id = caller_scope.org_id
       and recipient_profile_id = caller_scope.profile_id
       and public.current_user_can_read_direct_message(
           sender_profile_id, recipient_profile_id, facility_id, org_id
       )
     for update;
    if not found then
        -- Deliberately no distinction between missing, sent-by-caller, or foreign.
        return;
    end if;

    if target.read_at is null then
        perform set_config('emma.direct_message_read_guard', 'allowed', true);
        update public.direct_messages
           set read_at = now()
         where id = target.id
        returning * into target;

        insert into public.direct_message_audit (
            message_id, facility_id, org_id, actor_profile_id, action
        ) values (
            target.id, target.facility_id, target.org_id, caller_scope.profile_id, 'read'
        );
    end if;

    return next target;
end;
$$;

-- Direct table DML is not available to browser users. The RLS policies stay as
-- defence-in-depth documentation and protect any future narrowly-granted path.
revoke all privileges on direct_messages, direct_message_audit
from anon, authenticated;
grant select on direct_messages to authenticated;

revoke all on function public.list_direct_message_contacts() from public, anon;
grant execute on function public.list_direct_message_contacts() to authenticated;
revoke all on function public.send_direct_message(uuid, text, uuid)
from public, anon;
grant execute on function public.send_direct_message(uuid, text, uuid)
to authenticated;
revoke all on function public.mark_direct_message_read(uuid)
from public, anon;
grant execute on function public.mark_direct_message_read(uuid)
to authenticated;
