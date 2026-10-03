-- B1 only: no global task/escort dictionary entries have Founder approval.
-- DRAFT / NOT EXECUTED. Requires migrations 23 and 24; compatible with 25.
-- Do not edit historical migration 24 or infer approval to run this file.
-- NULL scope is not permission. Preserve same-organisation dictionary sharing,
-- including organisation-owned rows with facility_id NULL.
-- Migration 23's remaining FOR ALL write policies also compare org_id with
-- current_org_id(), so they do not admit NULL-org rows through policy OR.
-- This does not repair configuration-admin entitlement (B2) or other tables.
-- RLS runtime verification remains NOT TESTED until separately authorised.
-- Rollback: before application, leave this draft unapplied. A later rollback
-- must not restore the broad global-read policies; review a forward repair.

begin;

drop policy if exists task_definitions_read on public.task_definitions;
create policy task_definitions_read on public.task_definitions
    for select to authenticated
    using (org_id is not null and org_id = public.current_org_id());

drop policy if exists escort_locations_read on public.escort_locations;
create policy escort_locations_read on public.escort_locations
    for select to authenticated
    using (org_id is not null and org_id = public.current_org_id());

commit;
