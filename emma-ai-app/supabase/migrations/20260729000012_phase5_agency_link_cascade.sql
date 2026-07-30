-- ============================================================================
-- Emma AI · Phase 5 follow-up - agency link validation vs. FK cascade cleanup
--
-- validate_agency_assignment_links() policed every UPDATE, but both anchors are
-- ON DELETE SET NULL.  Tearing down a roster version therefore fired the trigger
-- from inside the cascade: Postgres nulls agency_assignments.shift_id while the
-- shift and its assignments are already being deleted, so re-checking the still
-- populated shift_assignment_id joined against a vanishing shift row and raised
-- 'agency assignment belongs to another facility, date or shift' — a delete that
-- should have succeeded.
--
-- The guard exists to stop a *bad link being set*, not to police cascade
-- cleanup, so each anchor is now validated only when that anchor actually
-- changes to a new non-null value.  Clearing a link stays unchecked: there is
-- nothing left to point at, and the cross-anchor check below is vacuous once
-- shift_id is null.
-- ============================================================================

create or replace function public.validate_agency_assignment_links()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.shift_id is not null
       and (
           tg_op = 'INSERT'
           or new.shift_id is distinct from old.shift_id
       )
       and not exists (
        select 1
        from shifts sh
        where sh.id = new.shift_id
          and sh.facility_id = new.facility_id
          and sh.date = new.date
    ) then
        raise exception using
            errcode = '23503',
            message = 'agency shift belongs to another facility or date';
    end if;
    -- Re-checked when the assignment anchor is (re)pointed, and when shift_id
    -- gains a new non-null value the pair must still agree on.
    if new.shift_assignment_id is not null
       and (
           tg_op = 'INSERT'
           or new.shift_assignment_id is distinct from old.shift_assignment_id
           or (
               new.shift_id is not null
               and new.shift_id is distinct from old.shift_id
           )
       )
       and not exists (
        select 1
        from shift_assignments assignment
        join shifts sh on sh.id = assignment.shift_id
        where assignment.id = new.shift_assignment_id
          and assignment.facility_id = new.facility_id
          and sh.facility_id = new.facility_id
          and sh.date = new.date
          and (
              new.shift_id is null
              or assignment.shift_id = new.shift_id
          )
    ) then
        raise exception using
            errcode = '23503',
            message = 'agency assignment belongs to another facility, date or shift';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_validate_agency_assignment_links on agency_assignments;
create trigger trg_validate_agency_assignment_links
before insert or update on agency_assignments
for each row execute function public.validate_agency_assignment_links();
