-- The charity sits above the home. One charity runs many homes and they all
-- work from the same duty code dictionary, so the dictionaries hang off the
-- charity while the roster stays with the home that works it.

create table if not exists organisations (
    id uuid primary key default gen_random_uuid(),
    code text not null unique,
    name text not null,
    created_at timestamptz not null default now()
);

comment on table organisations is
    'The charity. A facility is one of its homes; duty codes live here so sister homes share one dictionary.';

alter table facilities        add column if not exists org_id uuid references organisations(id);
alter table shift_definitions add column if not exists org_id uuid references organisations(id);
alter table task_definitions  add column if not exists org_id uuid references organisations(id);
alter table escort_locations  add column if not exists org_id uuid references organisations(id);
alter table users_profile     add column if not exists org_id uuid references organisations(id);

-- Homes that predate this table each get their own charity. They belong to
-- different ones in reality, and folding them into a single charity would erase
-- the very boundary the isolation tests exist to prove.
insert into organisations (code, name)
select 'ORG_' || f.code, f.name
  from facilities f
 where f.org_id is null
on conflict (code) do nothing;

update facilities f
   set org_id = o.id
  from organisations o
 where f.org_id is null
   and o.code = 'ORG_' || f.code;

alter table facilities alter column org_id set not null;

update shift_definitions s set org_id = f.org_id
  from facilities f where s.facility_id = f.id and s.org_id is null;
update task_definitions t set org_id = f.org_id
  from facilities f where t.facility_id = f.id and t.org_id is null;
update escort_locations e set org_id = f.org_id
  from facilities f where e.facility_id = f.id and e.org_id is null;
update users_profile u set org_id = f.org_id
  from facilities f where u.facility_id = f.id and u.org_id is null;

create index if not exists idx_facilities_org         on facilities(org_id);
create index if not exists idx_shift_definitions_org  on shift_definitions(org_id, shift_type);
create index if not exists idx_task_definitions_org   on task_definitions(org_id, task_code);
create index if not exists idx_escort_locations_org   on escort_locations(org_id, code);
create index if not exists idx_users_profile_org      on users_profile(org_id);

-- Which charity the signed-in user belongs to. It reads the profile first so a
-- charity-level account can exist later without being tied to one home.
create or replace function public.current_org_id()
returns uuid
language sql
stable
security definer
set search_path to 'public', 'auth'
as $$
    select coalesce(up.org_id, f.org_id)
      from public.users_profile up
      left join public.facilities f on f.id = up.facility_id
     where up.auth_user_id = auth.uid()
     limit 1;
$$;

grant execute on function public.current_org_id() to authenticated;

alter table organisations enable row level security;

drop policy if exists organisations_tenant on organisations;
create policy organisations_tenant on organisations
    for all to authenticated
    using (id = public.current_org_id())
    with check (id = public.current_org_id());

grant select on organisations to authenticated;

-- A home is now visible to its own charity, which is what lets one charity run
-- twenty homes without twenty logins.
drop policy if exists facilities_tenant on facilities;
create policy facilities_tenant on facilities
    for all to authenticated
    using (org_id = public.current_org_id())
    with check (org_id = public.current_org_id());

-- The three dictionaries move to the charity. Everything else keeps the home
-- boundary it already had.
drop policy if exists shift_definitions_tenant on shift_definitions;
create policy shift_definitions_tenant on shift_definitions
    for all to authenticated
    using (org_id = public.current_org_id())
    with check (org_id = public.current_org_id());

drop policy if exists task_definitions_read on task_definitions;
create policy task_definitions_read on task_definitions
    for select to authenticated
    using (facility_id is null or org_id = public.current_org_id());

drop policy if exists task_definitions_write on task_definitions;
create policy task_definitions_write on task_definitions
    for all to authenticated
    using (org_id = public.current_org_id())
    with check (org_id = public.current_org_id());

drop policy if exists escort_locations_read on escort_locations;
create policy escort_locations_read on escort_locations
    for select to authenticated
    using (facility_id is null or org_id = public.current_org_id());

drop policy if exists escort_locations_write on escort_locations;
create policy escort_locations_write on escort_locations
    for all to authenticated
    using (org_id = public.current_org_id())
    with check (org_id = public.current_org_id());

-- A row that names a home but no charity inherits the home's. Every insert that
-- already exists keeps working, and a dictionary row orphaned from its charity
-- becomes impossible rather than merely unlikely.
create or replace function public.set_org_from_facility()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $$
begin
    if new.org_id is null and new.facility_id is not null then
        select f.org_id into new.org_id
          from public.facilities f
         where f.id = new.facility_id;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_shift_definitions_org on shift_definitions;
create trigger trg_shift_definitions_org
    before insert or update of facility_id, org_id on shift_definitions
    for each row execute function public.set_org_from_facility();

drop trigger if exists trg_task_definitions_org on task_definitions;
create trigger trg_task_definitions_org
    before insert or update of facility_id, org_id on task_definitions
    for each row execute function public.set_org_from_facility();

drop trigger if exists trg_escort_locations_org on escort_locations;
create trigger trg_escort_locations_org
    before insert or update of facility_id, org_id on escort_locations
    for each row execute function public.set_org_from_facility();

drop trigger if exists trg_users_profile_org on users_profile;
create trigger trg_users_profile_org
    before insert or update of facility_id, org_id on users_profile
    for each row execute function public.set_org_from_facility();
