-- ============================================================================
-- Direct messages and duty-request-window RLS hardening
--
-- Chat is deliberately accessed only through an authenticated user's client.
-- There is no SECURITY DEFINER message write RPC and the application must not
-- substitute a service-role client, because RLS is the message confidentiality
-- boundary.
-- ============================================================================

-- The existing current_facility_id() is SECURITY DEFINER.  The matching profile
-- helper is likewise SECURITY DEFINER so policies never query users_profile
-- through its own RLS policy (and therefore cannot recurse).
create or replace function public.current_profile_id()
returns uuid
language sql
stable
security definer
set search_path = public, auth
as $$
    select id
      from public.users_profile
     where auth_user_id = auth.uid()
     limit 1;
$$;

grant execute on function public.current_profile_id() to authenticated;

-- Resolve the allowed manager/frontline relationship inside a SECURITY DEFINER
-- helper.  This avoids making direct_messages RLS depend on users_profile RLS.
-- Both canonical roles and the still-provisioned legacy spellings are accepted.
create or replace function public.is_direct_message_recipient(
    target_facility_id uuid,
    target_profile_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public, auth
as $$
    select exists (
        select 1
          from public.users_profile sender
          join public.users_profile recipient on recipient.id = target_profile_id
         where sender.id = public.current_profile_id()
           and sender.facility_id = target_facility_id
           and recipient.facility_id = target_facility_id
           and (
               (
                   lower(sender.role) in ('owner', 'nurse_mgr', 'superintendent')
                   and lower(recipient.role) in ('frontline', 'staff')
               )
               or
               (
                   lower(sender.role) in ('frontline', 'staff')
                   and lower(recipient.role) in ('owner', 'nurse_mgr', 'superintendent')
               )
           )
    );
$$;

grant execute on function public.is_direct_message_recipient(uuid, uuid) to authenticated;

create table if not exists direct_messages (
    id                   uuid primary key default gen_random_uuid(),
    facility_id          uuid not null references facilities(id) on delete cascade,
    sender_profile_id    uuid not null references users_profile(id) on delete restrict,
    recipient_profile_id uuid not null references users_profile(id) on delete restrict,
    body                 text not null check (char_length(body) between 1 and 1000 and btrim(body) <> ''),
    created_at           timestamptz not null default now(),
    read_at              timestamptz,
    constraint direct_messages_distinct_profiles
        check (sender_profile_id <> recipient_profile_id)
);

create index if not exists idx_direct_messages_sender_created
    on direct_messages (facility_id, sender_profile_id, created_at);
create index if not exists idx_direct_messages_recipient_created
    on direct_messages (facility_id, recipient_profile_id, created_at);

-- Clients may not backdate messages or create them already read.  The server
-- sets the creation timestamp, and the UPDATE trigger below sets read_at.
create or replace function public.prepare_direct_message_insert()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.read_at is not null then
        raise exception using
            errcode = '42501',
            message = 'direct_messages may not be inserted as read';
    end if;
    new.created_at := now();
    return new;
end;
$$;

drop trigger if exists trg_prepare_direct_message_insert on direct_messages;
create trigger trg_prepare_direct_message_insert
before insert on direct_messages
for each row execute function public.prepare_direct_message_insert();

-- `UPDATE(read_at)` is also granted below, but a table owner, SQL console, or
-- future grant must not be able to change message contents accidentally.  First
-- read wins and the database supplies the timestamp rather than accepting a
-- client-selected one.
create or replace function public.guard_direct_message_read_update()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.id is distinct from old.id
       or new.facility_id is distinct from old.facility_id
       or new.sender_profile_id is distinct from old.sender_profile_id
       or new.recipient_profile_id is distinct from old.recipient_profile_id
       or new.body is distinct from old.body
       or new.created_at is distinct from old.created_at then
        raise exception using
            errcode = '42501',
            message = 'only direct_messages.read_at may be updated';
    end if;
    if old.read_at is not null then
        raise exception using
            errcode = '42501',
            message = 'direct_messages.read_at is immutable once set';
    end if;
    if new.read_at is null then
        raise exception using
            errcode = '42501',
            message = 'direct_messages.read_at may not be cleared';
    end if;
    new.read_at := now();
    return new;
end;
$$;

drop trigger if exists trg_guard_direct_message_read_update on direct_messages;
create trigger trg_guard_direct_message_read_update
before update on direct_messages
for each row execute function public.guard_direct_message_read_update();

alter table direct_messages enable row level security;

drop policy if exists direct_messages_select_participant on direct_messages;
create policy direct_messages_select_participant on direct_messages
    for select to authenticated
    using (
        facility_id = public.current_facility_id()
        and public.current_profile_id() in (sender_profile_id, recipient_profile_id)
    );

drop policy if exists direct_messages_insert_sender on direct_messages;
create policy direct_messages_insert_sender on direct_messages
    for insert to authenticated
    with check (
        facility_id = public.current_facility_id()
        and sender_profile_id = public.current_profile_id()
        and sender_profile_id <> recipient_profile_id
        and public.is_direct_message_recipient(facility_id, recipient_profile_id)
    );

drop policy if exists direct_messages_update_recipient_read on direct_messages;
create policy direct_messages_update_recipient_read on direct_messages
    for update to authenticated
    using (
        facility_id = public.current_facility_id()
        and recipient_profile_id = public.current_profile_id()
    )
    with check (
        facility_id = public.current_facility_id()
        and recipient_profile_id = public.current_profile_id()
    );

-- The default privileges from the early schema migration are broader than chat
-- needs.  Pair the RLS policy with column-level grants: no DELETE, no body edit,
-- and no sender read receipt update even if a future policy regresses.
revoke all on table direct_messages from public, anon, authenticated;
grant select, insert on table direct_messages to authenticated;
grant update (read_at) on table direct_messages to authenticated;

-- facility_json_configs originally had one facility-only FOR ALL policy.  RLS
-- policies are ORed, so leaving it in place would silently defeat an owner-only
-- policy for duty_request_window.  Keep the former facility-wide behavior for
-- all other keys, but split this sensitive key into its own OWNER policy.  Read
-- access remains facility-wide so a FRONTLINE profile can see the published
-- window before submitting a DO/duty request.
drop policy if exists facility_json_configs_tenant on facility_json_configs;
drop policy if exists facility_json_configs_read on facility_json_configs;
drop policy if exists facility_json_configs_other_write on facility_json_configs;
drop policy if exists duty_request_window_owner_write on facility_json_configs;

create policy facility_json_configs_read on facility_json_configs
    for select to authenticated
    using (facility_id = public.current_facility_id());

create policy facility_json_configs_other_write on facility_json_configs
    for all to authenticated
    using (
        facility_id = public.current_facility_id()
        and config_key <> 'duty_request_window'
    )
    with check (
        facility_id = public.current_facility_id()
        and config_key <> 'duty_request_window'
    );

create policy duty_request_window_owner_write on facility_json_configs
    for all to authenticated
    using (
        facility_id = public.current_facility_id()
        and config_key = 'duty_request_window'
        and lower(public.current_role_name()) in ('owner', 'superintendent')
    )
    with check (
        facility_id = public.current_facility_id()
        and config_key = 'duty_request_window'
        and lower(public.current_role_name()) in ('owner', 'superintendent')
    );

-- A pair of PostgREST UPDATE/INSERT calls is not atomic: a failed second call
-- would retire the only active window. One SECURITY INVOKER RPC performs both
-- writes in its own transaction, under the caller's RLS and privilege grants.
-- Locking the parent facility row serializes two simultaneous owner publishes.
create or replace function public.publish_duty_request_window(
    p_facility_id uuid,
    p_config_json jsonb
)
returns public.facility_json_configs
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
    v_version integer;
    v_row public.facility_json_configs%rowtype;
    v_opens timestamptz;
    v_closes timestamptz;
    v_target_start date;
    v_target_end date;
begin
    if auth.uid() is null
       or p_facility_id is distinct from public.current_facility_id()
       or coalesce(lower(public.current_role_name()) in ('owner', 'superintendent'), false) is false then
        raise exception using errcode = '42501', message = 'not authorized to publish request window';
    end if;
    if p_config_json is null
       or jsonb_typeof(p_config_json) <> 'object'
       or jsonb_typeof(p_config_json -> 'enabled') is distinct from 'boolean' then
        raise exception using errcode = '22023', message = 'enabled must be a boolean';
    end if;
    if (p_config_json ->> 'opens_at') is not null
       or (p_config_json ->> 'closes_at') is not null
       or (p_config_json ->> 'target_start') is not null
       or (p_config_json ->> 'target_end') is not null
       or (p_config_json ->> 'enabled')::boolean then
        if (p_config_json ->> 'opens_at') is null
           or (p_config_json ->> 'closes_at') is null
           or (p_config_json ->> 'target_start') is null
           or (p_config_json ->> 'target_end') is null
           or (p_config_json ->> 'opens_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
           or (p_config_json ->> 'closes_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' then
            raise exception using errcode = '22023', message = 'window requires timezones and all target fields';
        end if;
        v_opens := (p_config_json ->> 'opens_at')::timestamptz;
        v_closes := (p_config_json ->> 'closes_at')::timestamptz;
        v_target_start := (p_config_json ->> 'target_start')::date;
        v_target_end := (p_config_json ->> 'target_end')::date;
        if v_closes <= v_opens or v_target_end < v_target_start then
            raise exception using errcode = '22023', message = 'invalid request window range';
        end if;
    end if;

    perform 1 from public.facilities where id = p_facility_id for update;
    if not found then
        raise exception using errcode = '42501', message = 'facility not available';
    end if;
    select coalesce(max(version), 0) + 1 into v_version
      from public.facility_json_configs
     where facility_id = p_facility_id and config_key = 'duty_request_window';
    update public.facility_json_configs set active = false
     where facility_id = p_facility_id and config_key = 'duty_request_window' and active;
    insert into public.facility_json_configs (
        facility_id, config_key, config_json, version, description, active, created_by
    ) values (
        p_facility_id, 'duty_request_window', p_config_json, v_version,
        'Owner-controlled frontline duty/day-off request window', true,
        public.current_profile_id()
    ) returning * into v_row;
    return v_row;
end;
$$;

revoke all on function public.publish_duty_request_window(uuid, jsonb) from public, anon;
grant execute on function public.publish_duty_request_window(uuid, jsonb) to authenticated;
