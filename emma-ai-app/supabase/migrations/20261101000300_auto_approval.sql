-- Review-only policy storage. No leave/roster/balance writes and no seeded policy.
create table public.auto_approval_policies (
    facility_id uuid primary key references public.facilities(id),
    org_id uuid not null references public.organisations(id),
    version bigint not null check (version > 0),
    enabled boolean not null default false,
    allowed_types text[] not null default '{}',
    rule_version text not null check (length(rule_version) between 1 and 128),
    check (not enabled or cardinality(allowed_types) > 0)
);
create table public.auto_approval_policy_audit (
    facility_id uuid not null references public.facilities(id),
    org_id uuid not null references public.organisations(id),
    retry_key text not null check (length(retry_key) between 1 and 128),
    actor_id uuid not null references public.users_profile(id),
    payload jsonb not null,
    previous_policy jsonb,
    result jsonb not null,
    created_at timestamptz not null default now(),
    primary key (facility_id, retry_key)
);

create function public.protect_auto_approval_policy_audit()
returns trigger language plpgsql set search_path = '' as $$
begin
    raise exception using errcode = '42501', message = 'auto-approval policy audit is append-only';
end;
$$;
create trigger protect_auto_approval_policy_audit
before update or delete on public.auto_approval_policy_audit
for each row execute function public.protect_auto_approval_policy_audit();

-- The same owner + org + facility test protects direct table reads and the RPC.
create function public.auto_approval_is_owner(p_org uuid, p_facility uuid)
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.users_profile u
        join public.facilities f on f.id = u.facility_id
        where u.auth_user_id = auth.uid()
          and upper(trim(u.role::text)) in ('OWNER', 'SUPERINTENDENT')
          and u.facility_id = p_facility and f.org_id = p_org
          and u.org_id = p_org
    );
$$;
revoke all on function public.auto_approval_is_owner(uuid, uuid) from public, anon;
grant execute on function public.auto_approval_is_owner(uuid, uuid) to authenticated;

alter table public.auto_approval_policies enable row level security;
alter table public.auto_approval_policy_audit enable row level security;
create policy auto_approval_policy_read on public.auto_approval_policies
    for select to authenticated
    using (public.auto_approval_is_owner(org_id, facility_id));
create policy auto_approval_audit_read on public.auto_approval_policy_audit
    for select to authenticated
    using (public.auto_approval_is_owner(org_id, facility_id));
revoke all on public.auto_approval_policies, public.auto_approval_policy_audit from public, anon, authenticated;
grant select on public.auto_approval_policies, public.auto_approval_policy_audit to authenticated;

-- Serialized policy CAS + retry identity + append-only audit in one transaction.
-- Identity comes from auth.uid(), never from an API argument or service client.
create function public.auto_approval_write_policy(
    p_org uuid, p_facility uuid, p_expected bigint, p_retry text,
    p_enabled boolean, p_types text[], p_rule text
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    old_row public.auto_approval_policies%rowtype;
    prior public.auto_approval_policy_audit%rowtype;
    actor uuid;
    body jsonb;
    result_row jsonb;
begin
    if not public.auto_approval_is_owner(p_org, p_facility) then
        raise insufficient_privilege using message = 'Scoped owner required';
    end if;
    if p_expected is null or p_expected < 0 or p_retry is null
       or length(p_retry) not between 1 and 128 or p_enabled is null
       or p_rule is null or length(p_rule) not between 1 and 128
       or p_types is null or cardinality(p_types) > 32
       or (p_enabled and cardinality(p_types) = 0)
       or (p_expected = 0 and p_enabled)
       or exists (select 1 from unnest(p_types) t where t is null or length(trim(t)) = 0 or length(t) > 64)
       or cardinality(p_types) <> (select count(distinct t) from unnest(p_types) t)
    then raise exception 'Invalid policy'; end if;
    -- Lock the existing facility, including the first-create race.
    perform 1 from public.facilities where id = p_facility and org_id = p_org for update;
    -- Recheck authorization after acquiring the serialization lock.
    if not public.auto_approval_is_owner(p_org, p_facility) then
        raise insufficient_privilege;
    end if;
    select id into strict actor from public.users_profile
        where auth_user_id = auth.uid() and facility_id = p_facility;
    body := jsonb_build_object('org_id', p_org, 'expected_version', p_expected,
        'enabled', p_enabled, 'allowed_types', p_types, 'rule_version', p_rule);
    select * into prior from public.auto_approval_policy_audit
        where facility_id = p_facility and retry_key = p_retry;
    if found then
        if prior.payload = body and prior.actor_id = actor then return prior.result; end if;
        return '{"error":"conflict"}'::jsonb;
    end if;
    select * into old_row from public.auto_approval_policies where facility_id = p_facility;
    if (found and (old_row.version <> p_expected or old_row.org_id <> p_org))
       or (not found and p_expected <> 0) then
        return '{"error":"conflict"}'::jsonb;
    end if;
    insert into public.auto_approval_policies as policies
        (facility_id, org_id, version, enabled, allowed_types, rule_version)
        values (p_facility, p_org, p_expected + 1, p_enabled, p_types, p_rule)
        on conflict (facility_id) do update set version = excluded.version,
            enabled = excluded.enabled, allowed_types = excluded.allowed_types,
            rule_version = excluded.rule_version
        returning to_jsonb(policies.*) into result_row;
    insert into public.auto_approval_policy_audit
        (facility_id, org_id, retry_key, actor_id, payload, previous_policy, result)
        values (p_facility, p_org, p_retry, actor, body,
            case when old_row.facility_id is null then null else to_jsonb(old_row) end, result_row);
    return result_row;
end;
$$;
revoke all on function public.auto_approval_write_policy(uuid, uuid, bigint, text, boolean, text[], text) from public, anon;
grant execute on function public.auto_approval_write_policy(uuid, uuid, bigint, text, boolean, text[], text) to authenticated;
