-- DRAFT ONLY — NOT in supabase/migrations and not applied by this task.
--
-- Canonical-role transition hardening for public.can_see_staff_row().
--
-- The existing helper treats every role other than legacy `staff` as
-- facility-wide. That is unsafe during a canonical-role transition because a
-- profile holding canonical `FRONTLINE`, a null role, or an unrecognised role
-- would otherwise receive facility-wide visibility on every policy using this
-- helper.
--
-- Scope and non-goals:
-- * This changes only the helper's role interpretation. Existing RLS policies,
--   grants, direct-write rules, unit scope, and all other role RBAC remain
--   unchanged and must be reviewed/UAT-tested separately.
-- * It deliberately retains the current facility-wide helper semantics for the
--   known legacy non-staff role values and known canonical non-FRONTLINE role
--   values. It does not infer any NAAC deputy or ordinary-nurse semantics.
-- * `FRONTLINE` and legacy `staff` are self-only. An unlinked profile, null
--   role, null staff id, or unknown role returns false.
--
-- Apply only after review in a non-production environment with actual-token RLS
-- tests for legacy and canonical profiles. No SQL was executed for this draft.

create or replace function public.can_see_staff_row(row_staff_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, auth
as $$
    select case lower(coalesce(public.current_role_name(), ''))
        when 'staff' then coalesce(row_staff_id = public.current_staff_id(), false)
        when 'frontline' then coalesce(row_staff_id = public.current_staff_id(), false)

        -- Existing, intentionally facility-wide manager/helper values.
        when 'superintendent' then true
        when 'admin' then true
        when 'scheduler' then true
        when 'hr' then true
        when 'auditor' then true

        -- Canonical roles that retain the current helper's facility-wide branch.
        when 'owner' then true
        when 'nurse_mgr' then true
        when 'allied_health' then true
        when 'admin_clerk' then true
        when 'hr_auditor' then true

        -- Unknown/null role must never become a facility-wide permission.
        else false
    end;
$$;
