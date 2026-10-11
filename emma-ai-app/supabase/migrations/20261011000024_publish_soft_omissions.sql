-- ============================================================================
-- Emma AI · publish soft omissions (REVIEW ONLY — NOT APPLIED BY THIS CHANGE)
--
-- Replaces the legacy three-argument publication RPC.  The prior RPC accepted
-- an implicit latest validation, allowed a null actor, used a solver quality
-- score as a hard gate, and wrote evidence outside the transaction in Python.
-- This migration deliberately has no compatibility overload: keeping the old
-- service_role callable would leave a publish bypass.
--
-- Apply only after review in an isolated non-production Supabase project.
-- ============================================================================

-- The existing event row is the publication timeline.  Store the immutable
-- evidence references there rather than accepting browser-authored free text.
alter table public.roster_publish_events
    add column if not exists evidence_json jsonb not null default '{}'::jsonb
    check (jsonb_typeof(evidence_json) = 'object');

-- Set only by the service while persisting a run. This is not a browser input:
-- it binds a reviewed stable fingerprint to one exact soft evidence row.
alter table public.violation_log
    add column if not exists omission_id text;
create unique index if not exists uq_violation_log_soft_omission_per_run
    on public.violation_log(validation_run_id, omission_id)
    where omission_id is not null;

comment on column public.roster_publish_events.evidence_json is
    'Atomic publish evidence: validation run/digest and server-mapped omitted violation row IDs.';

-- Remove the service-role callable legacy signature before creating the exact
-- contract.  RESTRICT is intentional: an unexpected dependency stops review/
-- deployment rather than leaving a bypass beside the replacement RPC.
revoke execute on function public.publish_roster_version(uuid, uuid, uuid)
    from public, authenticated, service_role;
drop function if exists public.publish_roster_version(uuid, uuid, uuid);

create function public.publish_roster_version(
    p_facility_id uuid,
    p_roster_version_id uuid,
    p_created_by uuid,
    p_validation_run_id uuid,
    p_input_digest text,
    p_omitted_soft_violation_row_ids uuid[]
)
returns setof public.roster_versions
language plpgsql
security definer
set search_path = public, auth, pg_catalog
as $$
declare
    target public.roster_versions%rowtype;
    validation_run public.roster_validation_runs%rowtype;
    actual_hard_count integer := 0;
    actual_soft_count integer := 0;
    actual_unknown_count integer := 0;
    requested_omission_count integer := 0;
    matched_omission_count integer := 0;
    published_at_value timestamptz;
    locked_period_id uuid;
begin
    -- This SECURITY DEFINER RPC is an internal service boundary, never a
    -- browser capability.  Authentication/OWNER checks still happen in FastAPI;
    -- the profile test below binds the audited actor to this facility.
    if coalesce(auth.role(), current_setting('request.jwt.claim.role', true))
       is distinct from 'service_role' then
        raise exception using
            errcode = '42501',
            message = 'not permitted to publish this roster';
    end if;

    -- An anonymous audit actor is not acceptable.  During the canonical-role
    -- migration OWNER is allowed alongside the only legacy publisher spelling,
    -- superintendent.  Admin/scheduler remain deliberately excluded.
    if p_created_by is null or not exists (
        select 1
        from public.users_profile up
        where up.id = p_created_by
          and up.facility_id = p_facility_id
          and up.role in ('OWNER', 'superintendent')
    ) then
        raise exception using
            errcode = '42501',
            message = 'a facility OWNER publishing actor is required';
    end if;

    if p_validation_run_id is null
       or p_input_digest is null
       or p_input_digest !~ '^[0-9a-f]{64}$'
       or p_omitted_soft_violation_row_ids is null
       or array_position(p_omitted_soft_violation_row_ids, null) is not null then
        raise exception using
            errcode = '23514',
            message = 'fresh validation evidence and soft omission IDs are required';
    end if;

    -- Lock the period first to retain the legacy deadlock-safe serialization
    -- order, then lock the target version and the exact submitted validation
    -- run.  A content/rule check cannot race a completed publication.
    select *
    into target
    from public.roster_versions
    where id = p_roster_version_id
      and facility_id = p_facility_id;
    if not found then
        raise exception using errcode = 'P0002', message = 'roster version not found';
    end if;
    if target.period_id is null then
        raise exception using
            errcode = '23514', message = 'a roster period is required for publication';
    end if;

    locked_period_id := target.period_id;
    perform id
    from public.roster_periods
    where id = target.period_id
      and facility_id = p_facility_id
    for update;
    if not found then
        raise exception using
            errcode = '23514', message = 'roster period does not belong to this facility';
    end if;

    select *
    into target
    from public.roster_versions
    where id = p_roster_version_id
      and facility_id = p_facility_id
    for update;

    if not found or target.period_id is distinct from locked_period_id then
        raise exception using errcode = '23514', message = 'roster period changed after locking';
    end if;

    select *
    into validation_run
    from public.roster_validation_runs
    where id = p_validation_run_id
      and facility_id = p_facility_id
      and roster_version_id = p_roster_version_id
    for update;
    if not found
       or validation_run.status <> 'passed'
       or validation_run.completed_at is null
       or validation_run.roster_digest <> p_input_digest
       or validation_run.source_content_updated_at is distinct from target.content_updated_at
       or validation_run.completed_at < target.content_updated_at
       or validation_run.validated_by is distinct from p_created_by then
        raise exception using
            errcode = '23514',
            message = 'the submitted validation is not a fresh passed roster snapshot';
    end if;

    -- Lock every row of the exact run before deriving counts or checking the
    -- supplied database IDs.  Any unknown severity is hard-fail: legal/
    -- eligibility configuration that has not been defined must never default to
    -- pass or be silently classed as a soft warning.
    perform id
    from public.violation_log
    where facility_id = p_facility_id
      and roster_version_id = p_roster_version_id
      and validation_run_id = p_validation_run_id
    order by id
    for update;

    select
        count(*) filter (where severity = 'hard' and not resolved),
        count(*) filter (where severity = 'soft' and not resolved),
        count(*) filter (where severity not in ('hard', 'soft') or severity is null)
    into actual_hard_count, actual_soft_count, actual_unknown_count
    from public.violation_log
    where facility_id = p_facility_id
      and roster_version_id = p_roster_version_id
      and validation_run_id = p_validation_run_id;

    if actual_unknown_count <> 0
       or validation_run.hard_violation_count <> actual_hard_count
       or validation_run.soft_violation_count <> actual_soft_count
       or actual_hard_count <> 0 then
        raise exception using
            errcode = '23514',
            message = 'hard, unknown, or mismatched validation evidence blocks publication';
    end if;

    requested_omission_count := coalesce(cardinality(p_omitted_soft_violation_row_ids), 0);
    if requested_omission_count <> (
        select count(distinct omitted_id)
        from unnest(p_omitted_soft_violation_row_ids) as supplied(omitted_id)
    ) then
        raise exception using
            errcode = '23514',
            message = 'soft omission IDs must be unique';
    end if;

    select count(*)
    into matched_omission_count
    from public.violation_log violation
    where violation.id = any(p_omitted_soft_violation_row_ids)
      and violation.facility_id = p_facility_id
      and violation.roster_version_id = p_roster_version_id
      and violation.validation_run_id = p_validation_run_id
      and violation.severity = 'soft'
      and not violation.resolved;

    -- Exact equality means a client cannot omit a hard/historical/cross-tenant
    -- row, acknowledge one row twice, or skip one current soft checkbox.
    if requested_omission_count <> actual_soft_count
       or matched_omission_count <> actual_soft_count then
        raise exception using
            errcode = '23514',
            message = 'every current soft validation finding must be individually acknowledged';
    end if;

    -- Solver scores remain evidence but are not a legal hard gate: low score may
    -- express acknowledged agency/OT/fairness soft trade-offs.  A deterministic
    -- validation hard/unknown state above is the only publication blocker.

    -- A generated option's non-zero hard solver evidence still blocks, even if
    -- a later detector failed to rediscover it. Low soft quality alone does not.
    if exists (
        select 1 from public.roster_option_scores score
        where score.facility_id = p_facility_id
          and score.roster_version_id = p_roster_version_id
          and (score.hard_violation_count is null or score.hard_violation_count <> 0)
    ) then
        raise exception using errcode = '23514', message = 'hard solver evidence blocks publication';
    end if;

    -- Stable sibling locking retains one operative version per period.
    perform id
    from public.roster_versions
    where facility_id = p_facility_id
      and period_id = target.period_id
    order by id
    for update;

    perform set_config('emma.publish_guard', 'allowed', true);
    update public.roster_versions
    set status = 'archived'
    where facility_id = p_facility_id
      and period_id = target.period_id
      and status = 'published'
      and id <> p_roster_version_id;

    published_at_value := clock_timestamp();
    update public.roster_versions
    set status = 'published',
        published_at = published_at_value
    where id = p_roster_version_id
      and facility_id = p_facility_id;

    insert into public.roster_publish_events (
        facility_id,
        roster_version_id,
        event_type,
        created_by,
        evidence_json
    ) values (
        p_facility_id,
        p_roster_version_id,
        'publish',
        p_created_by,
        jsonb_build_object(
            'validation_run_id', p_validation_run_id,
            'input_digest', p_input_digest,
            'omitted_soft_violation_row_ids', to_jsonb(p_omitted_soft_violation_row_ids),
            'soft_violation_count', actual_soft_count,
            'hard_violation_count', actual_hard_count
        )
    );

    -- This append-only audit evidence is inside the same transaction as the
    -- state change and event.  Any error rolls all three back; there is no
    -- post-RPC best-effort audit gap.
    insert into public.audit_logs (
        facility_id,
        actor_profile_id,
        action,
        entity_table,
        entity_id,
        after_json
    ) values (
        p_facility_id,
        p_created_by,
        'publish',
        'roster_versions',
        p_roster_version_id,
        jsonb_build_object(
            'status', 'published',
            'published_at', published_at_value,
            'period_id', target.period_id,
            'validation_run_id', p_validation_run_id,
            'input_digest', p_input_digest,
            'omitted_soft_violation_row_ids', to_jsonb(p_omitted_soft_violation_row_ids),
            'soft_violation_count', actual_soft_count,
            'hard_violation_count', actual_hard_count
        )
    );
    perform set_config('emma.publish_guard', 'denied', true);

    return query
    select *
    from public.roster_versions
    where id = p_roster_version_id
      and facility_id = p_facility_id;
exception
    when others then
        -- The setting is transaction-local; reset it before surfacing the
        -- failure for callers that catch a statement error inside a transaction.
        perform set_config('emma.publish_guard', 'denied', true);
        raise;
end;
$$;

revoke all on function public.publish_roster_version(uuid, uuid, uuid, uuid, text, uuid[])
    from public, authenticated;
grant execute on function public.publish_roster_version(uuid, uuid, uuid, uuid, text, uuid[])
    to service_role;

comment on function public.publish_roster_version(uuid, uuid, uuid, uuid, text, uuid[]) is
    'Service-role-only atomic roster publication: exact fresh validation run/digest, OWNER actor, all current soft evidence IDs, event and audit evidence.';
