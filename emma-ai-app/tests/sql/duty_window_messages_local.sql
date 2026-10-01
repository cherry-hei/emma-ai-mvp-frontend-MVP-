-- Synthetic-only integration harness. Run on a FRESH, LOCAL, DISPOSABLE database.
-- Never run this fixture against Emma's AWS/Supabase/customer databases.
\set ON_ERROR_STOP on
create schema auth;
do $$begin
  if not exists (select 1 from pg_roles where rolname='authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname='anon') then
    create role anon nologin;
  end if;
end$$;
grant usage on schema public, auth to authenticated;

create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;
grant execute on function auth.uid() to authenticated;

create table public.facilities (id uuid primary key, org_id uuid);
create table public.users_profile (
  id uuid primary key, auth_user_id uuid unique, facility_id uuid references public.facilities(id),
  role text, staff_id uuid
);
create table public.facility_json_configs (
  id uuid primary key default gen_random_uuid(),
  facility_id uuid not null references public.facilities(id),
  config_key text not null, config_json jsonb not null default '{}'::jsonb,
  version int not null default 1, description text,
  effective_from date not null default current_date,
  active boolean not null default true,
  created_by uuid references public.users_profile(id),
  created_at timestamptz not null default now(),
  constraint facility_json_configs_json_check check (jsonb_typeof(config_json) = 'object')
);
create unique index uq_facility_json_configs_active
  on public.facility_json_configs(facility_id, config_key) where active;
grant select, update on public.facilities to authenticated;
grant select on public.users_profile to authenticated;
grant select, insert, update on public.facility_json_configs to authenticated;

create function public.current_facility_id() returns uuid language sql stable security definer
set search_path = public, auth as $$
  select facility_id from public.users_profile where auth_user_id = auth.uid() limit 1;
$$;
create function public.current_role_name() returns text language sql stable security definer
set search_path = public, auth as $$
  select role from public.users_profile where auth_user_id = auth.uid() limit 1;
$$;
grant execute on function public.current_facility_id(), public.current_role_name() to authenticated;

alter table public.facilities enable row level security;
create policy facilities_tenant on public.facilities for all to authenticated
  using (id = public.current_facility_id()) with check (id = public.current_facility_id());
alter table public.users_profile enable row level security;
create policy profile_own on public.users_profile for select to authenticated
  using (auth_user_id = auth.uid());
alter table public.facility_json_configs enable row level security;
create policy facility_json_configs_tenant on public.facility_json_configs
  for all to authenticated using (facility_id = public.current_facility_id())
  with check (facility_id = public.current_facility_id());

-- Two homes, two owners, one frontline per home. All identifiers are invented.
insert into public.facilities(id,org_id) values
 ('11111111-1111-1111-1111-111111111111','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),
 ('22222222-2222-2222-2222-222222222222','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
insert into public.users_profile(id,auth_user_id,facility_id,role) values
 ('a1111111-1111-1111-1111-111111111111','a0111111-1111-1111-1111-111111111111','11111111-1111-1111-1111-111111111111','owner'),
 ('a2222222-2222-2222-2222-222222222222','a0222222-2222-2222-2222-222222222222','11111111-1111-1111-1111-111111111111','frontline'),
 ('b1111111-1111-1111-1111-111111111111','b0111111-1111-1111-1111-111111111111','22222222-2222-2222-2222-222222222222','owner'),
 ('b2222222-2222-2222-2222-222222222222','b0222222-2222-2222-2222-222222222222','22222222-2222-2222-2222-222222222222','frontline');

\i /home/ubuntu/emma-ai-mvp-ui-oct1/emma-ai-app/supabase/migrations/20261001000025_direct_messages.sql

set role authenticated;
set request.jwt.claim.sub to 'a0111111-1111-1111-1111-111111111111';
select (public.publish_duty_request_window(
  '11111111-1111-1111-1111-111111111111',
  '{"enabled":true,"opens_at":"2026-10-02T08:00:00+08:00","closes_at":"2026-10-03T08:00:00+08:00","target_start":"2026-11-01","target_end":"2026-11-30"}'::jsonb
)).version = 1 as first_version_one;

-- Try malformed update; the previously active row must survive.
do $$ begin
  begin
    perform public.publish_duty_request_window(
      '11111111-1111-1111-1111-111111111111',
      '{"enabled":true,"opens_at":"2026-10-04T09:00:00+08:00"}'::jsonb
    );
    raise exception 'FAIL: malformed update was allowed';
  exception when sqlstate '22023' then null;
  end;
end $$;
select count(*)=1 as old_window_survived from public.facility_json_configs
  where facility_id='11111111-1111-1111-1111-111111111111' and active and version=1;

-- Force an insert error AFTER the retirement update; the transaction rolls back.
reset role;
create function public.local_fail_version_two() returns trigger language plpgsql as $$
begin
  if new.version=2 then raise exception using errcode='22023', message='synthetic forced insert failure'; end if;
  return new;
end $$;
create trigger trg_local_fail_version_two before insert on public.facility_json_configs
for each row execute function public.local_fail_version_two();
set role authenticated;
set request.jwt.claim.sub to 'a0111111-1111-1111-1111-111111111111';
do $$ begin
  begin
    perform public.publish_duty_request_window('11111111-1111-1111-1111-111111111111',
      '{"enabled":false,"opens_at":null,"closes_at":null,"target_start":null,"target_end":null}'::jsonb);
    raise exception 'FAIL: insert error did not occur';
  exception when sqlstate '22023' then null;
  end;
end $$;
select count(*)=1 as atomic_rollback_kept_old from public.facility_json_configs
  where facility_id='11111111-1111-1111-1111-111111111111' and active and version=1;
reset role;
drop trigger trg_local_fail_version_two on public.facility_json_configs;
drop function public.local_fail_version_two();
set role authenticated;
set request.jwt.claim.sub to 'a0111111-1111-1111-1111-111111111111';
select (public.publish_duty_request_window('11111111-1111-1111-1111-111111111111',
  '{"enabled":false,"opens_at":null,"closes_at":null,"target_start":null,"target_end":null}'::jsonb
)).version = 2 as new_version_two;
select count(*)=1 as only_one_active from public.facility_json_configs
  where facility_id='11111111-1111-1111-1111-111111111111' and active;

-- An owner from B and a frontline from A cannot write A's window.
set request.jwt.claim.sub to 'b0111111-1111-1111-1111-111111111111';
do $$ begin
  begin
    perform public.publish_duty_request_window('11111111-1111-1111-1111-111111111111', '{"enabled":false}'::jsonb);
    raise exception 'FAIL: cross-facility publish was allowed';
  exception when insufficient_privilege then null;
  end;
end $$;
set request.jwt.claim.sub to 'a0222222-2222-2222-2222-222222222222';
do $$ begin
  begin
    perform public.publish_duty_request_window('11111111-1111-1111-1111-111111111111', '{"enabled":false}'::jsonb);
    raise exception 'FAIL: frontline publish was allowed';
  exception when insufficient_privilege then null;
  end;
end $$;

-- Participant-only reads. The other home cannot read or create messages in A.
set request.jwt.claim.sub to 'a0111111-1111-1111-1111-111111111111';
insert into public.direct_messages(facility_id,sender_profile_id,recipient_profile_id,body)
values ('11111111-1111-1111-1111-111111111111',
 'a1111111-1111-1111-1111-111111111111', 'a2222222-2222-2222-2222-222222222222', 'synthetic hello');
set request.jwt.claim.sub to 'a0222222-2222-2222-2222-222222222222';
select count(*)=1 as a_recipient_reads_one from public.direct_messages;
set request.jwt.claim.sub to 'b0111111-1111-1111-1111-111111111111';
select count(*)=0 as b_cannot_read_a from public.direct_messages;
do $$ begin
  if exists (select 1 from public.direct_messages) then
    raise exception 'FAIL: B can read home A messages';
  end if;
end $$;
do $$ begin
  begin
    insert into public.direct_messages(facility_id,sender_profile_id,recipient_profile_id,body)
    values ('11111111-1111-1111-1111-111111111111',
      'b1111111-1111-1111-1111-111111111111', 'a2222222-2222-2222-2222-222222222222', 'denied');
    raise exception 'FAIL: cross-facility insert was allowed';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;
do $$ begin
  if (select count(*) from public.facility_json_configs
      where facility_id='11111111-1111-1111-1111-111111111111'
      and config_key='duty_request_window') <> 2
     or (select count(*) from public.facility_json_configs
      where facility_id='11111111-1111-1111-1111-111111111111'
      and config_key='duty_request_window' and active and version=2) <> 1 then
    raise exception 'FAIL: window atomic update/history invariant';
  end if;
  if (select count(*) from public.direct_messages) <> 1 then
    raise exception 'FAIL: cross-facility insert was not denied';
  end if;
end $$;
select 'local-only SQL checks completed' as status;
