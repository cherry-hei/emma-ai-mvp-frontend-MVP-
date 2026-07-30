-- ============================================================================
-- Emma AI · Phase 0 - Row Level Security (multi-tenancy)
-- Home A must never see Home B data. Every tenant table is scoped by facility_id
-- to the caller's facility, resolved from their auth.uid() via users_profile.
--
-- - service_role key bypasses RLS (used for migrations/seed/admin) - by design.
-- - anon role gets no policies => no access until signed in.
-- ============================================================================

-- Resolve the current user's facility. SECURITY DEFINER so it reads users_profile
-- WITHOUT triggering RLS (prevents infinite recursion when used in policies).
create or replace function public.current_facility_id()
returns uuid
language sql
stable
security definer
set search_path = public, auth
as $$
    select facility_id from public.users_profile where auth_user_id = auth.uid() limit 1;
$$;

-- ── Helper: apply the standard "own-facility only" policy to a table ─────────
-- (written out explicitly per-table below for clarity/auditability)

-- facilities: user sees only their own facility row
alter table facilities enable row level security;
create policy facilities_tenant on facilities for all to authenticated
    using (id = public.current_facility_id())
    with check (id = public.current_facility_id());

-- Standard tenant tables: facility_id must match the caller's facility
alter table facility_units enable row level security;
create policy facility_units_tenant on facility_units for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table staff enable row level security;
create policy staff_tenant on staff for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table staff_contracts enable row level security;
create policy staff_contracts_tenant on staff_contracts for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table shift_definitions enable row level security;
create policy shift_definitions_tenant on shift_definitions for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table roster_periods enable row level security;
create policy roster_periods_tenant on roster_periods for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table roster_versions enable row level security;
create policy roster_versions_tenant on roster_versions for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table shifts enable row level security;
create policy shifts_tenant on shifts for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table shift_assignments enable row level security;
create policy shift_assignments_tenant on shift_assignments for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table daily_resident_counts enable row level security;
create policy daily_resident_counts_tenant on daily_resident_counts for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table manual_override_log enable row level security;
create policy manual_override_log_tenant on manual_override_log for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table roster_publish_events enable row level security;
create policy roster_publish_events_tenant on roster_publish_events for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

-- Tables that also allow global/template rows (facility_id IS NULL):
-- readable by everyone signed in, but users may only write rows for their own facility.
alter table staffing_ratio_rules enable row level security;
create policy staffing_ratio_rules_read on staffing_ratio_rules for select to authenticated
    using (facility_id is null or facility_id = public.current_facility_id());
create policy staffing_ratio_rules_write on staffing_ratio_rules for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

alter table calendar_days enable row level security;
create policy calendar_days_read on calendar_days for select to authenticated
    using (facility_id is null or facility_id = public.current_facility_id());
create policy calendar_days_write on calendar_days for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

-- users_profile: see profiles in your facility, plus always your own row.
-- Writes happen via service_role (admin provisioning) - no authenticated write policy.
alter table users_profile enable row level security;
create policy users_profile_select on users_profile for select to authenticated
    using (facility_id = public.current_facility_id() or auth_user_id = auth.uid());
