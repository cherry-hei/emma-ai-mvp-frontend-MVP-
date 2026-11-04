alter table public.facility_events
    add column assigned_staff_ids uuid[] not null default '{}';

create or replace function public.validate_event_staff_selection()
returns trigger language plpgsql set search_path = public, pg_temp as $$
begin
    if cardinality(new.assigned_staff_ids) > 100
       or cardinality(new.assigned_staff_ids) <>
          (select count(distinct id) from unnest(new.assigned_staff_ids) id) then
        raise exception using errcode = '23514', message = 'Event staff must be unique and limited to 100';
    end if;
    if exists (select 1 from unnest(new.assigned_staff_ids) as selected(staff_id)
        where not exists (select 1 from public.staff s
            where s.id = selected.staff_id and s.facility_id = new.facility_id and s.status = 'active')) then
        raise exception using errcode = '23514', message = 'Event staff must be active members of this facility';
    end if;
    if new.start_at is not null and new.end_at is not null and new.end_at <= new.start_at then
        raise exception using errcode = '23514', message = 'Event end must be after its start';
    end if;
    return new;
end;
$$;
create trigger trg_event_staff_selection before insert or update on public.facility_events
    for each row execute function public.validate_event_staff_selection();
