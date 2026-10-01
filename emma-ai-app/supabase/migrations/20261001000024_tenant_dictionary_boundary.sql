-- M1 tenant boundary follow-up. REVIEW ONLY until an accountable engineer
-- inspects a synthetic DB preflight, approves the migration and runs RLS UAT.
-- A facility_id NULL is a GLOBAL template only when org_id is ALSO NULL.
-- An organisation-owned dictionary row with facility_id NULL is never global.
-- This migration is additive to the tenant isolation model: no rows are moved,
-- renamed or deleted. Stop on inconsistent existing rows instead of guessing.

do $$
begin
    if exists (
        select 1 from shift_definitions d join facilities f on f.id = d.facility_id
         where d.org_id is distinct from f.org_id
    ) or exists (
        select 1 from task_definitions d join facilities f on f.id = d.facility_id
         where d.org_id is distinct from f.org_id
    ) or exists (
        select 1 from escort_locations d join facilities f on f.id = d.facility_id
         where d.org_id is distinct from f.org_id
    ) or exists (
        select 1 from users_profile u join facilities f on f.id = u.facility_id
         where u.org_id is distinct from f.org_id
    ) then
        raise exception 'org_id/facility_id mismatch: stop and reconcile synthetic rows before applying';
    end if;
end $$;

-- Old policies used "facility_id is null OR own org". That exposed an
-- org-owned row without a facility to *every* signed-in organisation.
drop policy if exists task_definitions_read on task_definitions;
create policy task_definitions_read on task_definitions
    for select to authenticated
    using (
        org_id = public.current_org_id()
        or (org_id is null and facility_id is null)
    );

drop policy if exists escort_locations_read on escort_locations;
create policy escort_locations_read on escort_locations
    for select to authenticated
    using (
        org_id = public.current_org_id()
        or (org_id is null and facility_id is null)
    );

-- A caller must never be able to tag another organisation's facility with
-- their own org_id, even if their old WITH CHECK only compared the org_id.
create or replace function public.set_org_from_facility()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $$
declare
    owning_org uuid;
begin
    if new.facility_id is not null then
        select f.org_id into owning_org
          from public.facilities f
         where f.id = new.facility_id;
        if owning_org is null then
            raise exception 'facility has no owning organisation';
        end if;
        if new.org_id is not null and new.org_id is distinct from owning_org then
            raise exception 'org_id must match facility owner';
        end if;
        new.org_id := owning_org;
    end if;
    return new;
end;
$$;

-- Human acceptance: run as both NAAC and Care Home A/SA *authenticated* JWTs.
-- Verify own rows visible, truly global rows visible, other-org rows with both
-- NULL and non-NULL facility_id invisible, and cross-org writes rejected.
-- This does not close all 70 policies / 55 tables in the separate M5 gate.
