-- ============================================================================
-- Emma AI · durable request windows for duty/day-off applications
--
-- This migration intentionally gates only the confirmed existing duty request
-- types (DO, duty_request, shift_swap).  SL/DSL/urgent/late remain emergency
-- reporting paths and are never blocked by a request window. Existing rows are
-- not rewritten: enforcement applies only to creates and policy-input changes,
-- not to status-only or audit-only updates of historical decisions.
--
-- Application timestamps use [opens_at, closes_at).  Requested leave dates use
-- [target_start, target_end_exclusive), because leave_requests.date_end is an
-- inclusive day in the existing API/schema.
-- ============================================================================

create table if not exists public.request_windows (
    id                       uuid primary key default gen_random_uuid(),
    org_id                   uuid not null references public.organisations(id) on delete cascade,
    facility_id              uuid not null references public.facilities(id) on delete cascade,
    unit_id                  uuid references public.facility_units(id) on delete cascade,
    kind                     text not null check (kind in ('duty', 'leave')),
    scope_level              text not null check (scope_level in ('facility', 'unit')),
    is_open                  boolean not null default true,
    opens_at                 timestamptz not null,
    closes_at                timestamptz not null,
    target_start             date not null,
    target_end_exclusive     date not null,
    version                  integer not null default 1 check (version >= 1),
    idempotency_key          text not null,
    created_by               uuid references public.users_profile(id) on delete set null,
    updated_by               uuid references public.users_profile(id) on delete set null,
    created_at               timestamptz not null default clock_timestamp(),
    updated_at               timestamptz not null default clock_timestamp(),
    constraint request_windows_application_range_check check (closes_at > opens_at),
    constraint request_windows_target_range_check check (target_end_exclusive > target_start),
    constraint request_windows_scope_shape_check check (
        (scope_level = 'facility' and unit_id is null)
        or (scope_level = 'unit' and unit_id is not null)
    )
);

-- One current durable row per scope/kind.  A manager uses PATCH + version rather
-- than silently superseding it, while the audit table below preserves every edit.
create unique index if not exists uq_request_windows_facility_kind
    on public.request_windows(facility_id, kind)
    where scope_level = 'facility';
create unique index if not exists uq_request_windows_unit_kind
    on public.request_windows(facility_id, unit_id, kind)
    where scope_level = 'unit';
create unique index if not exists uq_request_windows_idempotency
    on public.request_windows(facility_id, idempotency_key);
create index if not exists idx_request_windows_effective
    on public.request_windows(facility_id, kind, scope_level, unit_id);

create table if not exists public.request_window_audit (
    id                       uuid primary key default gen_random_uuid(),
    request_window_id        uuid not null references public.request_windows(id) on delete restrict,
    org_id                   uuid not null references public.organisations(id) on delete cascade,
    facility_id              uuid not null references public.facilities(id) on delete cascade,
    actor_profile_id         uuid references public.users_profile(id) on delete set null,
    action                   text not null check (action in ('create', 'update')),
    version                  integer not null,
    before_json              jsonb,
    after_json               jsonb not null,
    reason                   text,
    created_at               timestamptz not null default clock_timestamp()
);
create index if not exists idx_request_window_audit_window
    on public.request_window_audit(request_window_id, version);
create index if not exists idx_request_window_audit_facility
    on public.request_window_audit(facility_id, created_at desc);

-- A row can name only a unit in the same facility and an organisation matching
-- the facility.  The API never accepts org/facility IDs from a manager body;
-- this trigger protects direct writes and future server callers as well.
create or replace function public.validate_request_window_scope()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    v_org_id uuid;
begin
    select f.org_id into v_org_id from public.facilities f where f.id = new.facility_id;
    if v_org_id is null or new.org_id is distinct from v_org_id then
        raise exception using errcode = '23503', message = 'request window organisation does not match facility';
    end if;
    if new.scope_level = 'unit' and not exists (
        select 1 from public.facility_units u
         where u.id = new.unit_id and u.facility_id = new.facility_id
    ) then
        raise exception using errcode = '23503', message = 'request window unit does not belong to facility';
    end if;
    return new;
end;
$$;
drop trigger if exists trg_request_windows_scope on public.request_windows;
create trigger trg_request_windows_scope
before insert or update of org_id, facility_id, unit_id, scope_level on public.request_windows
for each row execute function public.validate_request_window_scope();

create or replace function public.protect_request_window_audit()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    raise exception using errcode = '42501', message = 'request_window_audit is append-only';
end;
$$;
drop trigger if exists trg_protect_request_window_audit on public.request_window_audit;
create trigger trg_protect_request_window_audit
before update or delete on public.request_window_audit
for each row execute function public.protect_request_window_audit();

create or replace function public.request_window_kind_for_leave(p_leave_type text)
returns text
language sql
immutable
set search_path = public
as $$
    select case lower(trim(coalesce(p_leave_type, '')))
        when 'do' then 'duty'
        when 'duty_request' then 'duty'
        when 'shift_swap' then 'duty'
        else null
    end;
$$;

create or replace function public.request_window_status(
    p_window public.request_windows,
    p_now timestamptz
)
returns text
language plpgsql
immutable
set search_path = public
as $$
begin
    if not p_window.is_open then
        return 'closed';
    elsif p_now < p_window.opens_at then
        return 'scheduled';
    elsif p_now >= p_window.closes_at then
        return 'expired';
    end if;
    return 'open';
end;
$$;

create or replace function public.request_window_public(
    p_window public.request_windows,
    p_now timestamptz default clock_timestamp()
)
returns jsonb
language sql
stable
set search_path = public
as $$
    select jsonb_build_object(
        'id', p_window.id,
        'organization_id', p_window.org_id,
        'facility_id', p_window.facility_id,
        'unit_id', p_window.unit_id,
        'kind', p_window.kind,
        'scope', p_window.scope_level,
        'state', case when p_window.is_open then 'open' else 'closed' end,
        'opens_at', p_window.opens_at,
        'closes_at', p_window.closes_at,
        'target_start', p_window.target_start,
        'target_end_exclusive', p_window.target_end_exclusive,
        'version', p_window.version,
        'status', public.request_window_status(p_window, p_now),
        'server_now', p_now,
        'created_at', p_window.created_at,
        'updated_at', p_window.updated_at
    );
$$;

-- Security-definer only exposes a row inside the caller's facility.  Service
-- role uses the same function for server preflight; its result is still repeated
-- by the INSERT trigger below, which is the authoritative race-safe gate.
create or replace function public.request_window_availability(
    p_facility_id uuid,
    p_staff_id uuid,
    p_leave_type text,
    p_date_start date default null,
    p_date_end date default null
)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_kind text := public.request_window_kind_for_leave(p_leave_type);
    v_org_id uuid;
    v_unit_id uuid;
    v_window public.request_windows%rowtype;
    v_status text;
    v_service boolean := coalesce(auth.role(), current_setting('request.jwt.claim.role', true)) = 'service_role';
    v_role text := lower(coalesce(public.current_role_name(), ''));
    v_known_role boolean;
begin
    -- This is the exact direct-message legacy plus canonical role vocabulary,
    -- case-normalized here so unknown/stale values fail closed at this RPC.
    v_known_role := v_role in (
        'superintendent', 'admin', 'staff', 'scheduler', 'hr', 'auditor',
        'owner', 'nurse_mgr', 'allied_health', 'admin_clerk', 'frontline', 'hr_auditor'
    );
    if not v_service and (
        auth.uid() is null
        or p_facility_id is distinct from public.current_facility_id()
        or not v_known_role
    ) then
        raise exception using errcode = '42501', message = 'request-window facility is not available';
    end if;
    -- The Staff PWA may inspect only its own effective unit window. Existing
    -- non-frontline manager-assisted leave submission still needs to preflight
    -- the subject staff member, so it is deliberately not collapsed to self.
    if not v_service
       and v_role in ('staff', 'frontline')
       and p_staff_id is distinct from public.current_staff_id() then
        raise exception using errcode = '42501', message = 'request-window staff is not available';
    end if;

    if v_kind is null then
        return jsonb_build_object(
            'kind', null,
            'available', true,
            'status', 'not_gated',
            'reason', null,
            'server_now', v_now,
            'window', null
        );
    end if;

    -- Retain a shared facility lock through the calling transaction.  It blocks
    -- RPC creation of a new effective unit override (which locks this facility
    -- FOR UPDATE) after this availability decision and before a leave write.
    select f.org_id, s.primary_unit_id
      into v_org_id, v_unit_id
      from public.facilities f
      join public.staff s on s.id = p_staff_id and s.facility_id = f.id
     where f.id = p_facility_id
     for share of f;
    if not found then
        return jsonb_build_object(
            'kind', v_kind,
            'available', false,
            'status', 'unavailable',
            'reason', 'No staff record is available in this facility.',
            'server_now', v_now,
            'window', null
        );
    end if;

    select w.* into v_window
      from public.request_windows w
     where w.org_id = v_org_id
       and w.facility_id = p_facility_id
       and w.kind = v_kind
       and (
            (w.scope_level = 'unit' and w.unit_id = v_unit_id)
            or w.scope_level = 'facility'
       )
     order by case when w.scope_level = 'unit' then 0 else 1 end
     limit 1
     for share;

    if not found then
        return jsonb_build_object(
            'kind', v_kind,
            'available', false,
            'status', 'unavailable',
            'reason', 'No request window is configured for this scope.',
            'server_now', v_now,
            'window', null
        );
    end if;

    v_status := public.request_window_status(v_window, v_now);
    if v_status <> 'open' then
        return jsonb_build_object(
            'kind', v_kind,
            'available', false,
            'status', v_status,
            'reason', 'The request window is not open.',
            'server_now', v_now,
            'window', public.request_window_public(v_window, v_now)
        );
    end if;

    if (p_date_start is null) <> (p_date_end is null) then
        return jsonb_build_object(
            'kind', v_kind,
            'available', false,
            'status', 'invalid_range',
            'reason', 'Both requested dates are required to check the target range.',
            'server_now', v_now,
            'window', public.request_window_public(v_window, v_now)
        );
    end if;

    if p_date_start is not null and (
        p_date_start < v_window.target_start
        or p_date_end < p_date_start
        or p_date_end >= v_window.target_end_exclusive
    ) then
        return jsonb_build_object(
            'kind', v_kind,
            'available', false,
            'status', 'out_of_range',
            'reason', 'Requested dates are outside the published target range.',
            'server_now', v_now,
            'window', public.request_window_public(v_window, v_now)
        );
    end if;

    return jsonb_build_object(
        'kind', v_kind,
        'available', true,
        'status', 'open',
        'reason', null,
        'server_now', v_now,
        'window', public.request_window_public(v_window, v_now)
    );
end;
$$;

-- This trigger is intentionally the final authority. It applies to service-role
-- writes too. The availability function retains shared locks on the governing
-- facility and window through the leave transaction, so a close or a newly
-- created override cannot commit after the final gate but before the leave write.
-- Status-only and other non-policy updates are deliberately not revalidated.
create or replace function public.enforce_request_window_on_leave_insert()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
declare
    v_availability jsonb;
begin
    if tg_op = 'UPDATE'
       and new.facility_id is not distinct from old.facility_id
       and new.staff_id is not distinct from old.staff_id
       and new.leave_type is not distinct from old.leave_type
       and new.date_start is not distinct from old.date_start
       and new.date_end is not distinct from old.date_end then
        return new;
    end if;
    if public.request_window_kind_for_leave(new.leave_type) is null then
        return new;
    end if;
    v_availability := public.request_window_availability(
        new.facility_id,
        new.staff_id,
        new.leave_type,
        new.date_start,
        new.date_end
    );
    if coalesce((v_availability ->> 'available')::boolean, false) is false then
        raise exception using
            errcode = '23514',
            message = 'request window unavailable: ' || coalesce(v_availability ->> 'status', 'unavailable');
    end if;
    return new;
end;
$$;
drop trigger if exists trg_enforce_request_window_on_leave_insert on public.leave_requests;
create trigger trg_enforce_request_window_on_leave_insert
before insert or update of facility_id, staff_id, leave_type, date_start, date_end on public.leave_requests
for each row execute function public.enforce_request_window_on_leave_insert();

create or replace function public.assert_request_window_admin(p_facility_id uuid)
returns uuid
language plpgsql
security definer
set search_path = public, auth
as $$
declare
    v_profile_id uuid;
begin
    if auth.uid() is null
       or p_facility_id is distinct from public.current_facility_id()
       or lower(coalesce(public.current_role_name(), '')) not in ('owner', 'superintendent') then
        raise exception using errcode = '42501', message = 'not authorized to administer request windows';
    end if;
    select id into v_profile_id
      from public.users_profile
     where auth_user_id = auth.uid()
     limit 1;
    if v_profile_id is null then
        raise exception using errcode = '42501', message = 'request-window profile is not available';
    end if;
    return v_profile_id;
end;
$$;

create or replace function public.create_request_window(
    p_facility_id uuid,
    p_kind text,
    p_scope_level text,
    p_unit_id uuid,
    p_state text,
    p_opens_at timestamptz,
    p_closes_at timestamptz,
    p_target_start date,
    p_target_end_exclusive date,
    p_idempotency_key text,
    p_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_profile_id uuid;
    v_org_id uuid;
    v_row public.request_windows%rowtype;
    v_existing public.request_windows%rowtype;
    v_create_reason text;
begin
    v_profile_id := public.assert_request_window_admin(p_facility_id);
    if p_kind not in ('duty', 'leave')
       or p_scope_level not in ('facility', 'unit')
       or p_state not in ('open', 'closed')
       or p_opens_at is null or p_closes_at is null
       or p_target_start is null or p_target_end_exclusive is null
       or btrim(coalesce(p_idempotency_key, '')) = '' then
        raise exception using errcode = '22023', message = 'invalid request-window create payload';
    end if;
    if p_closes_at <= p_opens_at or p_target_end_exclusive <= p_target_start then
        raise exception using errcode = '22023', message = 'invalid request-window range';
    end if;
    if (p_scope_level = 'facility' and p_unit_id is not null)
       or (p_scope_level = 'unit' and p_unit_id is null) then
        raise exception using errcode = '22023', message = 'invalid request-window scope';
    end if;

    -- Serialize matching retries before the idempotency lookup so concurrent
    -- retry traffic returns the original durable row rather than a unique error.
    perform pg_advisory_xact_lock(hashtextextended(p_facility_id::text || ':' || p_idempotency_key, 0));
    select * into v_existing
      from public.request_windows
     where facility_id = p_facility_id and idempotency_key = p_idempotency_key;
    if found then
        if v_existing.kind = p_kind
           and v_existing.scope_level = p_scope_level
           and v_existing.unit_id is not distinct from p_unit_id
           and v_existing.is_open = (p_state = 'open')
           and v_existing.opens_at = p_opens_at
           and v_existing.closes_at = p_closes_at
           and v_existing.target_start = p_target_start
           and v_existing.target_end_exclusive = p_target_end_exclusive then
            -- The reason is immutable create evidence, so it is part of exact
            -- replay identity even though it lives only in the append-only audit.
            select a.reason into v_create_reason
              from public.request_window_audit a
             where a.request_window_id = v_existing.id
               and a.action = 'create'
               and a.version = 1
             order by a.created_at, a.id
             limit 1;
            if found and v_create_reason is not distinct from p_reason then
                return public.request_window_public(v_existing, v_now);
            end if;
        end if;
        raise exception using errcode = '23505', message = 'idempotency key already belongs to a different request window';
    end if;

    select org_id into v_org_id from public.facilities where id = p_facility_id for update;
    if v_org_id is null then
        raise exception using errcode = '42501', message = 'facility is not available';
    end if;

    insert into public.request_windows (
        org_id, facility_id, unit_id, kind, scope_level, is_open,
        opens_at, closes_at, target_start, target_end_exclusive,
        idempotency_key, created_by, updated_by, created_at, updated_at
    ) values (
        v_org_id, p_facility_id, p_unit_id, p_kind, p_scope_level, p_state = 'open',
        p_opens_at, p_closes_at, p_target_start, p_target_end_exclusive,
        p_idempotency_key, v_profile_id, v_profile_id, v_now, v_now
    ) returning * into v_row;

    insert into public.request_window_audit (
        request_window_id, org_id, facility_id, actor_profile_id,
        action, version, before_json, after_json, reason
    ) values (
        v_row.id, v_row.org_id, v_row.facility_id, v_profile_id,
        'create', v_row.version, null, to_jsonb(v_row), p_reason
    );
    return public.request_window_public(v_row, v_now);
end;
$$;

create or replace function public.patch_request_window(
    p_facility_id uuid,
    p_window_id uuid,
    p_expected_version integer,
    p_patch jsonb,
    p_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_profile_id uuid;
    v_before public.request_windows%rowtype;
    v_row public.request_windows%rowtype;
    v_is_open boolean;
    v_opens_at timestamptz;
    v_closes_at timestamptz;
    v_target_start date;
    v_target_end_exclusive date;
begin
    v_profile_id := public.assert_request_window_admin(p_facility_id);
    if p_expected_version is null or p_expected_version < 1
       or p_patch is null or jsonb_typeof(p_patch) <> 'object'
       or not (p_patch ?| array['state', 'opens_at', 'closes_at', 'target_start', 'target_end_exclusive'])
       or exists (
            select 1 from jsonb_object_keys(p_patch) as key
             where key not in ('state', 'opens_at', 'closes_at', 'target_start', 'target_end_exclusive')
       ) then
        raise exception using errcode = '22023', message = 'invalid request-window patch payload';
    end if;

    select * into v_before
      from public.request_windows
     where id = p_window_id and facility_id = p_facility_id
     for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'request window not found';
    end if;
    if v_before.version <> p_expected_version then
        raise exception using errcode = 'P0001', message = 'stale request-window version';
    end if;
    if p_patch ? 'state' and p_patch ->> 'state' not in ('open', 'closed') then
        raise exception using errcode = '22023', message = 'invalid request-window state';
    end if;
    if (p_patch ? 'opens_at' and (p_patch ->> 'opens_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$')
       or (p_patch ? 'closes_at' and (p_patch ->> 'closes_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$') then
        raise exception using errcode = '22023', message = 'request-window timestamps require timezone offsets';
    end if;

    v_is_open := case when p_patch ? 'state' then p_patch ->> 'state' = 'open' else v_before.is_open end;
    v_opens_at := case when p_patch ? 'opens_at' then (p_patch ->> 'opens_at')::timestamptz else v_before.opens_at end;
    v_closes_at := case when p_patch ? 'closes_at' then (p_patch ->> 'closes_at')::timestamptz else v_before.closes_at end;
    v_target_start := case when p_patch ? 'target_start' then (p_patch ->> 'target_start')::date else v_before.target_start end;
    v_target_end_exclusive := case when p_patch ? 'target_end_exclusive' then (p_patch ->> 'target_end_exclusive')::date else v_before.target_end_exclusive end;
    if v_closes_at <= v_opens_at or v_target_end_exclusive <= v_target_start then
        raise exception using errcode = '22023', message = 'invalid request-window range';
    end if;

    update public.request_windows
       set is_open = v_is_open,
           opens_at = v_opens_at,
           closes_at = v_closes_at,
           target_start = v_target_start,
           target_end_exclusive = v_target_end_exclusive,
           version = v_before.version + 1,
           updated_by = v_profile_id,
           updated_at = v_now
     where id = v_before.id
     returning * into v_row;

    insert into public.request_window_audit (
        request_window_id, org_id, facility_id, actor_profile_id,
        action, version, before_json, after_json, reason
    ) values (
        v_row.id, v_row.org_id, v_row.facility_id, v_profile_id,
        'update', v_row.version, to_jsonb(v_before), to_jsonb(v_row), p_reason
    );
    return public.request_window_public(v_row, v_now);
end;
$$;

create or replace function public.request_window_catalog(p_facility_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_service boolean := coalesce(auth.role(), current_setting('request.jwt.claim.role', true)) = 'service_role';
    v_role text := lower(coalesce(public.current_role_name(), ''));
    v_known_role boolean;
    v_owner boolean;
    v_staff_id uuid := public.current_staff_id();
    v_unit_id uuid;
    v_windows jsonb;
begin
    -- Keep this in lockstep with the direct-message migration's known legacy
    -- and canonical role vocabulary. Unknown nonempty values must not read.
    v_known_role := v_role in (
        'superintendent', 'admin', 'staff', 'scheduler', 'hr', 'auditor',
        'owner', 'nurse_mgr', 'allied_health', 'admin_clerk', 'frontline', 'hr_auditor'
    );
    v_owner := v_role in ('owner', 'superintendent');
    if not v_service and (
        auth.uid() is null
        or p_facility_id is distinct from public.current_facility_id()
        or not v_known_role
    ) then
        raise exception using errcode = '42501', message = 'request-window facility is not available';
    end if;
    if not v_service and not v_owner then
        select primary_unit_id into v_unit_id
          from public.staff
         where id = v_staff_id and facility_id = p_facility_id;
    end if;
    select coalesce(
        jsonb_agg(public.request_window_public(w, v_now) order by w.kind, w.scope_level, w.created_at),
        '[]'::jsonb
    ) into v_windows
      from public.request_windows w
      join public.facilities f on f.id = w.facility_id and f.org_id = w.org_id
     where w.facility_id = p_facility_id
       and (
            v_service
            or v_owner
            or w.scope_level = 'facility'
            or w.unit_id = v_unit_id
       );
    return jsonb_build_object('server_now', v_now, 'windows', v_windows);
end;
$$;

-- Tenant-scoped read-only direct access.  Mutations go through the authorization
-- checking RPCs; the audited RPC path is the only supported write surface.
alter table public.request_windows enable row level security;
alter table public.request_window_audit enable row level security;
drop policy if exists request_windows_tenant_read on public.request_windows;
create policy request_windows_tenant_read on public.request_windows
    for select to authenticated
    using (
        facility_id = public.current_facility_id()
        and lower(coalesce(public.current_role_name(), '')) in (
            'superintendent', 'admin', 'staff', 'scheduler', 'hr', 'auditor',
            'owner', 'nurse_mgr', 'allied_health', 'admin_clerk', 'frontline', 'hr_auditor'
        )
        and exists (
            select 1 from public.facilities f
             where f.id = request_windows.facility_id
               and f.org_id = request_windows.org_id
        )
        and (
            lower(coalesce(public.current_role_name(), '')) in ('owner', 'superintendent')
            or scope_level = 'facility'
            or unit_id = (
                select s.primary_unit_id
                  from public.staff s
                 where s.id = public.current_staff_id()
                   and s.facility_id = request_windows.facility_id
            )
        )
    );
drop policy if exists request_window_audit_tenant_read on public.request_window_audit;
create policy request_window_audit_tenant_read on public.request_window_audit
    for select to authenticated
    using (
        facility_id = public.current_facility_id()
        and lower(coalesce(public.current_role_name(), '')) in (
            'superintendent', 'admin', 'staff', 'scheduler', 'hr', 'auditor',
            'owner', 'nurse_mgr', 'allied_health', 'admin_clerk', 'frontline', 'hr_auditor'
        )
        and exists (
            select 1 from public.facilities f
             where f.id = request_window_audit.facility_id
               and f.org_id = request_window_audit.org_id
        )
        and lower(coalesce(public.current_role_name(), '')) in ('owner', 'superintendent')
    );

revoke all on public.request_windows, public.request_window_audit from public, anon, authenticated;
grant select on public.request_windows, public.request_window_audit to authenticated;
revoke all on function public.request_window_availability(uuid, uuid, text, date, date) from public, anon;
revoke all on function public.request_window_catalog(uuid) from public, anon;
revoke all on function public.create_request_window(uuid, text, text, uuid, text, timestamptz, timestamptz, date, date, text, text) from public, anon;
revoke all on function public.patch_request_window(uuid, uuid, integer, jsonb, text) from public, anon;
grant execute on function public.request_window_availability(uuid, uuid, text, date, date) to authenticated, service_role;
grant execute on function public.request_window_catalog(uuid) to authenticated, service_role;
grant execute on function public.create_request_window(uuid, text, text, uuid, text, timestamptz, timestamptz, date, date, text, text) to authenticated;
grant execute on function public.patch_request_window(uuid, uuid, integer, jsonb, text) to authenticated;
