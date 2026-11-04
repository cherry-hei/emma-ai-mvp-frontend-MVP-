-- An approval and its roster changes succeed or roll back together.
alter table public.task_assignments add column suspended_by_leave uuid
    references public.leave_requests(id);

create or replace function public.protect_suspended_task()
returns trigger language plpgsql set search_path = public, pg_temp as $$
begin
    if current_setting('emma.leave_guard', true) is distinct from 'allowed' then
        if tg_op <> 'INSERT' and old.suspended_by_leave is not null then
            raise exception using errcode = '23514', message = 'Task is suspended by approved leave';
        end if;
        if tg_op <> 'DELETE' and new.suspended_by_leave is not null then
            raise exception using errcode = '23514', message = 'Only leave approval may suspend a task';
        end if;
    end if;
    if tg_op = 'DELETE' then return old; end if;
    return new;
end;
$$;
create trigger trg_protect_suspended_task before insert or update or delete on public.task_assignments
    for each row execute function public.protect_suspended_task();

create table public.leave_roster_changes (
    id uuid primary key default gen_random_uuid(),
    facility_id uuid not null references public.facilities(id),
    request_id uuid not null references public.leave_requests(id),
    roster_version_id uuid not null references public.roster_versions(id),
    staff_id uuid not null references public.staff(id),
    date date not null,
    assignment_id uuid not null,
    applied_shift_id uuid not null,
    applied_shift jsonb not null,
    before_assignment jsonb,
    before_shift jsonb,
    before_tasks jsonb not null default '[]',
    restored_at timestamptz,
    unique(request_id, roster_version_id, date)
);
create unique index leave_roster_changes_live_cell
    on public.leave_roster_changes(facility_id, roster_version_id, staff_id, date)
    where restored_at is null;
alter table public.leave_roster_changes enable row level security;
create policy leave_roster_changes_tenant on public.leave_roster_changes
    for select to authenticated
    using (facility_id = public.current_facility_id());
grant select on public.leave_roster_changes to authenticated;
grant all on public.leave_roster_changes to service_role;

-- Approved leave is an audited amendment, like emergency cover.
create or replace function public.protect_published_roster_content()
returns trigger language plpgsql security definer set search_path = public as $$
declare
    old_version_id uuid;
    new_version_id uuid;
    version_status text;
begin
    if tg_table_name = 'shifts' then
        if tg_op in ('UPDATE', 'DELETE') then old_version_id := old.roster_version_id; end if;
        if tg_op in ('INSERT', 'UPDATE') then new_version_id := new.roster_version_id; end if;
    else
        if tg_op in ('UPDATE', 'DELETE') then
            select roster_version_id into old_version_id from shifts where id = old.shift_id;
        end if;
        if tg_op in ('INSERT', 'UPDATE') then
            select roster_version_id into new_version_id from shifts where id = new.shift_id;
        end if;
    end if;
    for version_status in select status from roster_versions
        where id = old_version_id or id = new_version_id order by id for update
    loop
        if version_status = 'published'
           and current_setting('emma.incident_guard', true) is distinct from 'allowed'
           and current_setting('emma.leave_guard', true) is distinct from 'allowed' then
            raise exception using errcode = '23514', message = 'the operative roster is immutable';
        end if;
    end loop;
    if tg_op = 'DELETE' then return old; end if;
    return new;
end;
$$;
revoke all on function public.protect_published_roster_content() from public;

create or replace function public.sync_approved_leave_roster()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
declare
    v record;
    day date;
    desired_code text;
    definition public.shift_definitions%rowtype;
    person public.staff%rowtype;
    prior public.shift_assignments%rowtype;
    applied public.shift_assignments%rowtype;
    snapshot public.leave_roster_changes%rowtype;
    new_shift_id uuid;
    cell_assignment_id uuid;
    saved_tasks jsonb;
    saved_assignment jsonb;
    saved_shift jsonb;
    affected integer;
    previous_guard text := coalesce(current_setting('emma.leave_guard', true), '');
begin
    if old.status = 'approved' and
       (new.staff_id, new.facility_id, new.date_start, new.date_end,
        new.leave_type, new.requested_shift_type) is distinct from
       (old.staff_id, old.facility_id, old.date_start, old.date_end,
        old.leave_type, old.requested_shift_type) then
        raise exception 'Revoke an approval before changing its dates, staff or code';
    end if;
    if old.status = 'approved' and new.status not in ('approved', 'revoked') then
        raise exception 'An approved request must be revoked before another decision';
    end if;
    if new.status = old.status then return new; end if;
    if new.status <> 'approved' and old.status <> 'approved' then return new; end if;

    -- Concurrent approvals for the same person cannot take the same day.
    perform pg_advisory_xact_lock(hashtextextended(new.staff_id::text, 0));
    perform set_config('emma.leave_guard', 'allowed', true);

    if old.status = 'approved' then
        for snapshot in select * from public.leave_roster_changes
            where request_id = new.id and facility_id = new.facility_id
              and restored_at is null order by roster_version_id, date for update
        loop
            select * into applied from public.shift_assignments
                where id = snapshot.assignment_id and facility_id = new.facility_id
                for update;
            if not found or applied.shift_id <> snapshot.applied_shift_id
               or applied.staff_id <> new.staff_id or applied.status = 'cancelled'
               or cardinality(applied.tasks) <> 0
               or exists (select 1 from public.task_assignments
                          where shift_assignment_id = snapshot.assignment_id
                            and suspended_by_leave is distinct from new.id) then
                raise exception 'Roster cell changed after approval; resolve it before revoking';
            end if;
            if (select to_jsonb(s) from public.shifts s where s.id = snapshot.applied_shift_id)
                is distinct from snapshot.applied_shift then
                raise exception 'Approved roster shift changed; resolve it before revoking';
            end if;
            if snapshot.before_assignment is null then
                delete from public.shift_assignments where id = snapshot.assignment_id;
            else
                if (select to_jsonb(s) from public.shifts s
                    where s.id = (snapshot.before_assignment->>'shift_id')::uuid)
                    is distinct from snapshot.before_shift then
                    raise exception 'Original shift changed after approval; resolve it before revoking';
                end if;
                select * into prior from jsonb_populate_record(
                    null::public.shift_assignments, snapshot.before_assignment);
                update public.shift_assignments set
                    shift_id = prior.shift_id, role = prior.role, status = prior.status,
                    is_agency = prior.is_agency, tasks = prior.tasks
                    where id = snapshot.assignment_id;
                update public.task_assignments set suspended_by_leave = null
                    where shift_assignment_id = snapshot.assignment_id and suspended_by_leave = new.id;
            end if;
            delete from public.shifts where id = snapshot.applied_shift_id
                and not exists (select 1 from public.shift_assignments
                                where shift_id = snapshot.applied_shift_id);
            update public.leave_roster_changes set restored_at = now()
                where id = snapshot.id;
            insert into public.audit_logs(facility_id, actor_profile_id, action,
                entity_table, entity_id, before_json, after_json, reason)
            values(new.facility_id, new.revoked_by, 'leave.roster.restore',
                'leave_requests', new.id, to_jsonb(snapshot),
                jsonb_build_object('assignment', snapshot.before_assignment,
                                   'tasks', snapshot.before_tasks), new.revoke_reason);
        end loop;
        update public.roster_cell_locks set released_at = now(),
            released_by = new.revoked_by, release_reason = new.revoke_reason
            where facility_id = new.facility_id and source_table = 'leave_requests'
              and source_id = new.id and released_at is null;
        perform set_config('emma.leave_guard', previous_guard, true);
        return new;
    end if;

    if exists (select 1 from public.leave_requests r where r.id <> new.id
        and r.facility_id = new.facility_id and r.staff_id = new.staff_id
        and r.status = 'approved' and r.date_start <= new.date_end
        and r.date_end >= new.date_start) then
        raise exception 'Another approved request already covers these dates';
    end if;
    if new.leave_type in ('DO', 'duty_request', 'shift_swap') then
        insert into public.roster_cell_locks(facility_id, staff_id, date,
            lock_type, shift_type, source_table, source_id, locked_by)
        select new.facility_id, new.staff_id, d::date,
            case when new.leave_type = 'DO' then 'forbid' else 'pin' end,
            case when new.leave_type = 'DO' then null else new.requested_shift_type end,
            'leave_requests', new.id, new.decided_by
        from generate_series(new.date_start, new.date_end, interval '1 day') d;
    end if;
    -- Lateness and appointments do not replace a whole duty.
    if new.leave_type in ('late', 'medical_fu') then
        perform set_config('emma.leave_guard', previous_guard, true);
        return new;
    end if;
    desired_code := case new.leave_type
        when 'duty_request' then new.requested_shift_type
        when 'shift_swap' then new.requested_shift_type
        when 'marriage' then 'MARL' when 'maternity' then 'ML'
        when 'unpaid' then 'NPL' when 'special' then 'SPL'
        when 'urgent' then 'SL' when 'DSL' then 'SL'
        else new.leave_type end;
    select d.* into definition from public.shift_definitions d
        join public.facilities f on f.org_id = d.org_id
        where f.id = new.facility_id and d.shift_type = desired_code limit 1;
    if not found and new.leave_type = 'DO' then
        select d.* into definition from public.shift_definitions d
            join public.facilities f on f.org_id = d.org_id
            where f.id = new.facility_id and d.shift_type = 'O' limit 1;
    end if;
    if definition.id is null then
        raise exception 'No organisation duty code is configured for leave type %', new.leave_type;
    end if;
    select * into strict person from public.staff
        where id = new.staff_id and facility_id = new.facility_id;
    for v in select rv.* from public.roster_versions rv
        join public.roster_periods p on p.id = rv.period_id
        where rv.facility_id = new.facility_id and p.facility_id = new.facility_id
          and p.period_start <= new.date_end and p.period_end >= new.date_start
          and rv.status <> 'archived'
          and (rv.version_type = 'manual' or rv.status = 'published')
        order by rv.id for update of rv
    loop
        for day in select generate_series(greatest(new.date_start,
            (select period_start from public.roster_periods where id = v.period_id)),
            least(new.date_end,
            (select period_end from public.roster_periods where id = v.period_id)),
            interval '1 day')::date
        loop
            select count(*) into affected from public.shift_assignments a
                join public.shifts s on s.id = a.shift_id
                where a.facility_id = new.facility_id and a.staff_id = new.staff_id
                  and a.status <> 'cancelled' and s.roster_version_id = v.id and s.date = day;
            if affected > 1 then raise exception 'Multiple assignments exist for this staff/day'; end if;
            select a.* into prior from public.shift_assignments a
                join public.shifts s on s.id = a.shift_id
                where a.facility_id = new.facility_id and a.staff_id = new.staff_id
                  and a.status <> 'cancelled' and s.roster_version_id = v.id and s.date = day
                for update of a;
            saved_assignment := case when prior.id is null then null else to_jsonb(prior) end;
            select to_jsonb(s) into saved_shift from public.shifts s where s.id = prior.shift_id;
            select coalesce(jsonb_agg(to_jsonb(t) order by t.id), '[]'::jsonb)
                into saved_tasks from public.task_assignments t
                where t.shift_assignment_id = prior.id;
            insert into public.shifts(facility_id, roster_version_id, date, shift_type,
                start_time, end_time, cross_midnight, unit_id, required_rank,
                is_working, segments, paid_minutes)
            values(new.facility_id, v.id, day, definition.shift_type,
                definition.start_time, definition.end_time, definition.cross_midnight,
                person.primary_unit_id, person.rank,
                case when new.leave_type in ('duty_request', 'shift_swap')
                     then definition.is_working else false end,
                definition.segments, definition.paid_minutes)
            returning id into new_shift_id;
            if prior.id is null then
                insert into public.shift_assignments(facility_id, shift_id, staff_id,
                    role, status, tasks) values(new.facility_id, new_shift_id, new.staff_id,
                    person.rank, 'assigned', '{}') returning id into cell_assignment_id;
            else
                cell_assignment_id := prior.id;
                update public.task_assignments set suspended_by_leave = new.id
                    where shift_assignment_id = prior.id;
                update public.shift_assignments set shift_id = new_shift_id,
                    tasks = '{}', is_agency = false where id = prior.id;
            end if;
            insert into public.leave_roster_changes(facility_id, request_id,
                roster_version_id, staff_id, date, assignment_id, applied_shift_id, applied_shift,
                before_assignment, before_shift, before_tasks)
            values(new.facility_id, new.id, v.id, new.staff_id, day,
                cell_assignment_id, new_shift_id,
                (select to_jsonb(s) from public.shifts s where s.id = new_shift_id),
                saved_assignment, saved_shift, saved_tasks);
            insert into public.audit_logs(facility_id, actor_profile_id, action,
                entity_table, entity_id, before_json, after_json, reason)
            values(new.facility_id, new.decided_by, 'leave.roster.apply',
                'leave_requests', new.id,
                jsonb_build_object('assignment', saved_assignment, 'shift', saved_shift, 'tasks', saved_tasks),
                jsonb_build_object('roster_version_id', v.id, 'date', day,
                    'assignment_id', cell_assignment_id, 'shift_id', new_shift_id,
                    'shift_type', definition.shift_type), new.decision_note);
        end loop;
    end loop;
    perform set_config('emma.leave_guard', previous_guard, true);
    return new;
exception when raise_exception then
    raise exception using errcode = '23514', message = sqlerrm;
end;
$$;
revoke all on function public.sync_approved_leave_roster() from public;
create trigger trg_leave_roster_sync after update on public.leave_requests
    for each row execute function public.sync_approved_leave_roster();
