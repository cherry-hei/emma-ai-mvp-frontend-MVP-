-- ============================================================================
-- Emma AI · Phase 5 follow-up - atomic emergency-cover resolution
--
-- Emergency cover is the only supported amendment to an operative roster.  It
-- must therefore be narrower than a general service-role write: this RPC locks
-- the incident, re-validates the tenant/actor/candidate, writes the cover,
-- recovery cells, debt and audit evidence in one transaction, and is safe to
-- retry with the same replacement.
-- ============================================================================

-- Provenance makes the transaction result reconstructable on an idempotent
-- retry and prevents a reopened/duplicated request from creating a second cover.
alter table shift_assignments
    add column if not exists source_incident_id uuid
        references sl_incidents(id) on delete set null,
    add column if not exists incident_assignment_kind text;

alter table shift_assignments
    drop constraint if exists shift_assignments_incident_kind_check;
alter table shift_assignments
    add constraint shift_assignments_incident_kind_check
    check (
        (source_incident_id is null and incident_assignment_kind is null)
        or incident_assignment_kind in ('cover', 'recovery')
    );

create unique index if not exists uq_shift_assignments_incident_result
    on shift_assignments(source_incident_id, incident_assignment_kind, shift_id)
    where source_incident_id is not null;

alter table future_debt_ledger
    add column if not exists resolution_key text;
create unique index if not exists uq_future_debt_resolution_key
    on future_debt_ledger(resolution_key)
    where resolution_key is not null;

alter table notifications
    add column if not exists resolution_key text;
create unique index if not exists uq_notification_resolution_key
    on notifications(resolution_key)
    where resolution_key is not null;

-- Tighten the Phase 5 immutability rule: holding the service key no longer
-- permits arbitrary edits to published roster content.  Only the local guard
-- set inside resolve_roster_incident() opens the amendment window.
create or replace function public.protect_published_roster_content()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    old_version_id uuid;
    new_version_id uuid;
    version_status text;
    incident_guard text := current_setting('emma.incident_guard', true);
begin
    if tg_table_name = 'shifts' then
        if tg_op in ('UPDATE', 'DELETE') then
            old_version_id := old.roster_version_id;
        end if;
        if tg_op in ('INSERT', 'UPDATE') then
            new_version_id := new.roster_version_id;
        end if;
    else
        if tg_op in ('UPDATE', 'DELETE') then
            select roster_version_id
            into old_version_id
            from shifts
            where id = old.shift_id;
        end if;
        if tg_op in ('INSERT', 'UPDATE') then
            select roster_version_id
            into new_version_id
            from shifts
            where id = new.shift_id;
        end if;
    end if;

    for version_status in
        select status
        from roster_versions
        where id = old_version_id or id = new_version_id
        order by id
        for update
    loop
        if version_status = 'published'
           and incident_guard is distinct from 'allowed' then
            raise exception using
                errcode = '23514',
                message = 'the operative roster is immutable';
        end if;
    end loop;

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

revoke all on function public.protect_published_roster_content() from public;

create or replace function public.resolve_roster_incident(
    p_facility_id uuid,
    p_incident_id uuid,
    p_replacement_staff_id uuid,
    p_actor_profile_id uuid,
    p_recovery_targets jsonb default '[]'::jsonb,
    p_auto boolean default true,
    p_note text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
    incident_row sl_incidents%rowtype;
    incident_shift shifts%rowtype;
    incident_version roster_versions%rowtype;
    incident_period roster_periods%rowtype;
    due_period roster_periods%rowtype;
    replacement staff%rowtype;
    target jsonb;
    target_day date;
    target_code text;
    target_version_id uuid;
    target_version roster_versions%rowtype;
    target_definition shift_definitions%rowtype;
    recovery_shift shifts%rowtype;
    cover_assignment shift_assignments%rowtype;
    policy jsonb;
    allowed_codes jsonb;
    recovery_required boolean := false;
    is_night boolean := false;
    offset_days integer;
    paid_minutes_total numeric := 0;
    debt_hours numeric := 0;
    resolution_minutes integer := 0;
    debts_json jsonb := '[]'::jsonb;
    recovery_json jsonb := '[]'::jsonb;
begin
    if coalesce(
        auth.role(),
        current_setting('request.jwt.claim.role', true)
    ) is distinct from 'service_role' then
        raise exception using
            errcode = '42501',
            message = 'incident resolution is available only through the API service';
    end if;

    if not exists (
        select 1
        from users_profile profile
        where profile.id = p_actor_profile_id
          and profile.facility_id = p_facility_id
          and profile.role in ('superintendent', 'admin', 'scheduler')
    ) then
        raise exception using
            errcode = '42501',
            message = 'resolving profile is not authorized for this facility';
    end if;

    select *
    into incident_row
    from sl_incidents
    where id = p_incident_id
      and facility_id = p_facility_id
    for update;
    if not found then
        raise exception using
            errcode = 'P0002',
            message = 'incident not found';
    end if;

    -- Same-candidate retries return the committed transaction result.  A retry
    -- cannot silently switch the person who accepted the cover.
    if incident_row.replacement_status = 'resolved' then
        if incident_row.replacement_staff_id is distinct from p_replacement_staff_id then
            raise exception using
                errcode = '23514',
                message = 'incident was resolved with a different replacement';
        end if;

        select coalesce(
            jsonb_agg(to_jsonb(debt) order by debt.created_at, debt.id),
            '[]'::jsonb
        )
        into debts_json
        from future_debt_ledger debt
        where debt.source_incident_id = p_incident_id;

        select coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'date', roster_shift.date,
                    'shift_type', roster_shift.shift_type,
                    'shift_id', roster_shift.id,
                    'shift_assignment_id', assignment.id
                )
                order by roster_shift.date, assignment.id
            ),
            '[]'::jsonb
        )
        into recovery_json
        from shift_assignments assignment
        join shifts roster_shift on roster_shift.id = assignment.shift_id
        where assignment.source_incident_id = p_incident_id
          and assignment.incident_assignment_kind = 'recovery';

        return jsonb_build_object(
            'incident', to_jsonb(incident_row),
            'future_debt', debts_json -> 0,
            'future_debts', debts_json,
            'night_recovery', recovery_json,
            'resolution_minutes', incident_row.resolution_minutes,
            'idempotent_replay', true
        );
    end if;
    if incident_row.replacement_status not in ('open', 'notified') then
        raise exception using
            errcode = '23514',
            message = 'incident is not open for resolution';
    end if;
    if incident_row.shift_id is null then
        raise exception using
            errcode = '23514',
            message = 'incident has no roster shift to cover';
    end if;

    select *
    into incident_shift
    from shifts
    where id = incident_row.shift_id
      and facility_id = p_facility_id
    for update;
    if not found or incident_shift.roster_version_id is null then
        raise exception using
            errcode = '23514',
            message = 'incident shift is not attached to this facility roster';
    end if;

    select *
    into incident_version
    from roster_versions
    where id = incident_shift.roster_version_id
      and facility_id = p_facility_id
    for update;
    if not found or incident_version.status <> 'published' then
        raise exception using
            errcode = '23514',
            message = 'incident shift is not on the operative roster';
    end if;

    select *
    into incident_period
    from roster_periods
    where id = incident_version.period_id
      and facility_id = p_facility_id
      and incident_shift.date between period_start and period_end
    for update;
    if not found then
        raise exception using
            errcode = '23514',
            message = 'incident shift is outside its roster period';
    end if;

    select *
    into due_period
    from roster_periods
    where facility_id = p_facility_id
      and period_start > incident_period.period_end
    order by period_start, id
    limit 1
    for update;
    if not found then
        raise exception using
            errcode = '23514',
            message = 'next roster period is required for bounded compensation debt';
    end if;

    select *
    into replacement
    from staff
    where id = p_replacement_staff_id
      and facility_id = p_facility_id
      and status = 'active'
    for update;
    if not found or replacement.id = incident_row.staff_id then
        raise exception using
            errcode = '23514',
            message = 'replacement is not an active candidate in this facility';
    end if;

    -- The API refreshes this explainable candidate snapshot immediately before
    -- calling the RPC.  The database still requires the exact candidate to have
    -- passed that current compliance evaluation.
    if not exists (
        select 1
        from replacement_candidates candidate
        where candidate.facility_id = p_facility_id
          and candidate.incident_id = p_incident_id
          and candidate.candidate_staff_id = p_replacement_staff_id
          and candidate.compliance_ok
          and candidate.created_at >= incident_row.reported_at
    ) then
        raise exception using
            errcode = '23514',
            message = 'replacement is not a current compliant candidate';
    end if;

    if not exists (
        select 1
        from shift_assignments assignment
        where assignment.facility_id = p_facility_id
          and assignment.shift_id = incident_shift.id
          and assignment.staff_id = incident_row.staff_id
          and assignment.status <> 'cancelled'
        for update
    ) then
        raise exception using
            errcode = '23514',
            message = 'absent staff no longer owns the incident shift';
    end if;
    if exists (
        select 1
        from shift_assignments assignment
        where assignment.facility_id = p_facility_id
          and assignment.shift_id = incident_shift.id
          and assignment.staff_id = p_replacement_staff_id
          and assignment.status <> 'cancelled'
    ) then
        raise exception using
            errcode = '23514',
            message = 'replacement is already assigned to the incident shift';
    end if;
    if exists (
        select 1
        from leave_requests request
        where request.facility_id = p_facility_id
          and request.staff_id = p_replacement_staff_id
          and request.status = 'approved'
          and request.leave_type not in ('duty_request', 'shift_swap')
          and incident_shift.date between request.date_start and request.date_end
    ) then
        raise exception using
            errcode = '23514',
            message = 'replacement is on approved leave for the incident shift';
    end if;

    -- Mirror the care-rank substitution ladder used by the Python candidate
    -- evaluator; therapy/social roles remain exact-match only.
    if incident_shift.required_rank is not null
       and replacement.rank <> incident_shift.required_rank
       and not (
            replacement.rank::text in ('RN', 'EN', 'HW', 'HCA', 'CW', 'PCW', 'AW')
            and incident_shift.required_rank::text in (
                'RN', 'EN', 'HW', 'HCA', 'CW', 'PCW', 'AW'
            )
            and case replacement.rank::text
                    when 'RN' then 7
                    when 'EN' then 6
                    when 'HW' then 5
                    when 'HCA' then 4
                    when 'CW' then 4
                    when 'PCW' then 3
                    when 'AW' then 2
                    else 0
                end
                >=
                case incident_shift.required_rank::text
                    when 'RN' then 7
                    when 'EN' then 6
                    when 'HW' then 5
                    when 'HCA' then 4
                    when 'CW' then 4
                    when 'PCW' then 3
                    when 'AW' then 2
                    else 0
                end
       ) then
        raise exception using
            errcode = '23514',
            message = 'replacement rank cannot cover the incident shift';
    end if;
    if incident_shift.required_rank::text in ('RN', 'EN', 'HW')
       and not replacement.is_audited_for_medication then
        raise exception using
            errcode = '23514',
            message = 'replacement is not audited for medication duty';
    end if;

    select definition.config_json
    into policy
    from rule_definitions definition
    where definition.rule_code = 'night_chain'
      and definition.active
      and definition.facility_id in (p_facility_id, null)
      and (
          definition.effective_from is null
          or definition.effective_from <= incident_period.period_start
      )
      and (
          definition.effective_to is null
          or definition.effective_to >= incident_period.period_start
      )
    order by
        (definition.facility_id = p_facility_id) desc,
        definition.config_version desc,
        definition.effective_from desc nulls last,
        definition.id desc
    limit 1;
    policy := jsonb_build_object(
        'night_shift_types', jsonb_build_array('AN', 'N'),
        'chain_employment_types', jsonb_build_array('local_ft'),
        'sleep_codes', jsonb_build_array('SLEEP', 'SD'),
        'day_off_codes', jsonb_build_array('DO', 'OFF'),
        'cooldown_ranks', jsonb_build_array('RN', 'EN')
    ) || coalesce(policy, '{}'::jsonb);

    is_night := exists (
        select 1
        from jsonb_array_elements_text(policy -> 'night_shift_types') value
        where upper(value) = upper(incident_shift.shift_type)
    );
    recovery_required := is_night and exists (
        select 1
        from jsonb_array_elements_text(
            policy -> 'chain_employment_types'
        ) value
        where value = replacement.employment_type::text
    );

    if is_night and exists (
        select 1
        from jsonb_array_elements_text(policy -> 'cooldown_ranks') value
        where upper(value) = upper(replacement.rank::text)
    ) and exists (
        select 1
        from future_debt_ledger debt
        where debt.facility_id = p_facility_id
          and debt.staff_id = p_replacement_staff_id
          and debt.debt_type = 'NIGHT_COOLDOWN'
          and debt.status = 'open'
          and (
              debt.due_period_id is null
              or debt.due_period_id = incident_period.id
          )
    ) then
        raise exception using
            errcode = '23514',
            message = 'replacement is in the mandatory night cooldown';
    end if;

    if p_recovery_targets is null
       or jsonb_typeof(p_recovery_targets) <> 'array' then
        raise exception using
            errcode = '22023',
            message = 'recovery targets must be a JSON array';
    end if;
    if recovery_required and jsonb_array_length(p_recovery_targets) <> 2 then
        raise exception using
            errcode = '23514',
            message = 'two mandatory night-recovery cells are required';
    end if;
    if not recovery_required and jsonb_array_length(p_recovery_targets) <> 0 then
        raise exception using
            errcode = '23514',
            message = 'recovery cells are not allowed for this cover';
    end if;

    perform set_config('emma.incident_guard', 'allowed', true);

    insert into shift_assignments (
        facility_id,
        shift_id,
        staff_id,
        role,
        status,
        is_agency,
        source_incident_id,
        incident_assignment_kind
    ) values (
        p_facility_id,
        incident_shift.id,
        p_replacement_staff_id,
        coalesce(incident_shift.required_rank, replacement.rank),
        'assigned',
        false,
        p_incident_id,
        'cover'
    )
    returning * into cover_assignment;

    insert into manual_override_log (
        facility_id,
        roster_version_id,
        shift_assignment_id,
        action,
        before_json,
        after_json,
        changed_by,
        reason
    ) values (
        p_facility_id,
        incident_version.id,
        cover_assignment.id,
        'assign',
        jsonb_build_object('staff_id', incident_row.staff_id),
        jsonb_build_object('staff_id', p_replacement_staff_id),
        p_actor_profile_id,
        'emergency cover for ' || incident_row.incident_type || ' incident'
    );

    if recovery_required then
        for offset_days in 1..2 loop
            target_day := incident_shift.date + offset_days;
            allowed_codes := case
                when offset_days = 1 then policy -> 'sleep_codes'
                else policy -> 'day_off_codes'
            end;

            select item
            into target
            from jsonb_array_elements(p_recovery_targets) item
            where (item ->> 'date')::date = target_day
            limit 1;
            if not found then
                raise exception using
                    errcode = '23514',
                    message = 'mandatory recovery date is missing';
            end if;

            target_code := upper(target ->> 'shift_type');
            if not exists (
                select 1
                from jsonb_array_elements_text(allowed_codes) value
                where upper(value) = target_code
            ) then
                raise exception using
                    errcode = '23514',
                    message = 'recovery shift type does not match the effective policy';
            end if;

            target_version_id := (target ->> 'roster_version_id')::uuid;
            select *
            into target_version
            from roster_versions
            where id = target_version_id
              and facility_id = p_facility_id
              and status = 'published'
            for update;
            if not found then
                raise exception using
                    errcode = '23514',
                    message = 'recovery target has no operative roster';
            end if;
            if (
                target_day between incident_period.period_start and incident_period.period_end
                and target_version.id <> incident_version.id
            ) or not exists (
                select 1
                from roster_periods target_period
                where target_period.id = target_version.period_id
                  and target_period.facility_id = p_facility_id
                  and target_day between target_period.period_start and target_period.period_end
            ) then
                raise exception using
                    errcode = '23514',
                    message = 'recovery target does not match its operative period';
            end if;

            select *
            into target_definition
            from shift_definitions definition
            where definition.facility_id = p_facility_id
              and upper(definition.shift_type) = target_code
              and not definition.is_working
            order by definition.id
            limit 1;
            if not found then
                raise exception using
                    errcode = '23514',
                    message = 'recovery shift definition is not configured';
            end if;

            if exists (
                select 1
                from leave_requests request
                where request.facility_id = p_facility_id
                  and request.staff_id = p_replacement_staff_id
                  and request.status = 'approved'
                  and request.leave_type not in ('duty_request', 'shift_swap')
                  and target_day between request.date_start and request.date_end
            ) then
                raise exception using
                    errcode = '23514',
                    message = 'approved leave conflicts with mandatory recovery';
            end if;
            if exists (
                select 1
                from shift_assignments assignment
                join shifts roster_shift on roster_shift.id = assignment.shift_id
                where assignment.facility_id = p_facility_id
                  and assignment.staff_id = p_replacement_staff_id
                  and assignment.status <> 'cancelled'
                  and roster_shift.roster_version_id = target_version.id
                  and roster_shift.date = target_day
                  and upper(roster_shift.shift_type) <> target_code
            ) then
                raise exception using
                    errcode = '23514',
                    message = 'mandatory recovery date became unavailable';
            end if;

            if not exists (
                select 1
                from shift_assignments assignment
                join shifts roster_shift on roster_shift.id = assignment.shift_id
                where assignment.facility_id = p_facility_id
                  and assignment.staff_id = p_replacement_staff_id
                  and assignment.status <> 'cancelled'
                  and roster_shift.roster_version_id = target_version.id
                  and roster_shift.date = target_day
                  and upper(roster_shift.shift_type) = target_code
            ) then
                insert into shifts (
                    facility_id,
                    roster_version_id,
                    date,
                    shift_type,
                    start_time,
                    end_time,
                    cross_midnight,
                    unit_id,
                    required_rank,
                    required_count,
                    is_working,
                    segments,
                    paid_minutes
                ) values (
                    p_facility_id,
                    target_version.id,
                    target_day,
                    target_code,
                    target_definition.start_time,
                    target_definition.end_time,
                    target_definition.cross_midnight,
                    incident_shift.unit_id,
                    null,
                    1,
                    false,
                    target_definition.segments,
                    coalesce(target_definition.paid_minutes, 0)
                )
                returning * into recovery_shift;

                insert into shift_assignments (
                    facility_id,
                    shift_id,
                    staff_id,
                    role,
                    status,
                    is_agency,
                    source_incident_id,
                    incident_assignment_kind
                ) values (
                    p_facility_id,
                    recovery_shift.id,
                    p_replacement_staff_id,
                    replacement.rank,
                    'assigned',
                    false,
                    p_incident_id,
                    'recovery'
                );
            end if;
        end loop;
    end if;

    if incident_shift.paid_minutes is not null then
        paid_minutes_total := incident_shift.paid_minutes;
    elsif incident_shift.segments is not null
          and jsonb_typeof(incident_shift.segments) = 'array'
          and jsonb_array_length(incident_shift.segments) > 0 then
        select coalesce(sum(
            case
                when (segment ->> 'end')::time <= (segment ->> 'start')::time
                then 1440
                else 0
            end
            + extract(
                epoch from (
                    (segment ->> 'end')::time
                    - (segment ->> 'start')::time
                )
            ) / 60
        ), 0)
        into paid_minutes_total
        from jsonb_array_elements(incident_shift.segments) segment;
    elsif incident_shift.start_time is not null
          and incident_shift.end_time is not null then
        paid_minutes_total := (
            case
                when incident_shift.cross_midnight
                     or incident_shift.end_time <= incident_shift.start_time
                then 1440
                else 0
            end
            + extract(
                epoch from (
                    incident_shift.end_time - incident_shift.start_time
                )
            ) / 60
        );
    end if;
    debt_hours := round(greatest(0, paid_minutes_total) / 60, 2);

    insert into future_debt_ledger (
        facility_id,
        staff_id,
        debt_type,
        quantity,
        unit,
        due_period_id,
        source_incident_id,
        source_shift_id,
        status,
        note,
        details_json,
        resolution_key
    ) values (
        p_facility_id,
        p_replacement_staff_id,
        'TOIL',
        debt_hours,
        'hours',
        due_period.id,
        p_incident_id,
        incident_shift.id,
        'open',
        'emergency cover - compensate next cycle',
        jsonb_build_object(
            'due_period_start', due_period.period_start,
            'due_period_end', due_period.period_end,
            'shift_type', upper(incident_shift.shift_type),
            'policy', 'emergency_cover_toil'
        ),
        p_incident_id::text || ':TOIL'
    )
    on conflict (resolution_key) where resolution_key is not null do nothing;

    if is_night then
        insert into future_debt_ledger (
            facility_id,
            staff_id,
            debt_type,
            quantity,
            unit,
            due_period_id,
            source_incident_id,
            source_shift_id,
            status,
            note,
            details_json,
            resolution_key
        ) values (
            p_facility_id,
            p_replacement_staff_id,
            'OT',
            1,
            'hours',
            due_period.id,
            p_incident_id,
            incident_shift.id,
            'open',
            'standalone ' || upper(incident_shift.shift_type)
                || ' cover - mandatory +1 hour overtime',
            jsonb_build_object(
                'due_period_start', due_period.period_start,
                'due_period_end', due_period.period_end,
                'shift_type', upper(incident_shift.shift_type),
                'policy', 'phase5_long_night'
            ),
            p_incident_id::text || ':OT'
        )
        on conflict (resolution_key) where resolution_key is not null do nothing;

        if exists (
            select 1
            from jsonb_array_elements_text(policy -> 'cooldown_ranks') value
            where upper(value) = upper(replacement.rank::text)
        ) then
            insert into future_debt_ledger (
                facility_id,
                staff_id,
                debt_type,
                quantity,
                unit,
                due_period_id,
                source_incident_id,
                source_shift_id,
                status,
                note,
                details_json,
                resolution_key
            ) values (
                p_facility_id,
                p_replacement_staff_id,
                'NIGHT_COOLDOWN',
                1,
                'period',
                due_period.id,
                p_incident_id,
                incident_shift.id,
                'open',
                'nurse night cover - block night duty next period',
                jsonb_build_object(
                    'due_period_start', due_period.period_start,
                    'due_period_end', due_period.period_end,
                    'shift_type', upper(incident_shift.shift_type),
                    'rank', upper(replacement.rank::text),
                    'policy', 'phase5_nurse_cooldown'
                ),
                p_incident_id::text || ':NIGHT_COOLDOWN'
            )
            on conflict (resolution_key) where resolution_key is not null do nothing;
        end if;
    end if;

    update shift_assignments
    set status = 'cancelled'
    where facility_id = p_facility_id
      and shift_id = incident_shift.id
      and staff_id = incident_row.staff_id
      and status <> 'cancelled';

    resolution_minutes := greatest(
        0,
        round(
            extract(epoch from (clock_timestamp() - incident_row.reported_at)) / 60
        )::integer
    );
    update sl_incidents
    set replacement_status = 'resolved',
        replacement_staff_id = p_replacement_staff_id,
        resolved_at = clock_timestamp(),
        resolved_by = p_actor_profile_id,
        resolution_minutes = resolution_minutes,
        auto_resolved = coalesce(p_auto, true),
        notes = p_note
    where id = p_incident_id
      and facility_id = p_facility_id
    returning * into incident_row;

    insert into notifications (
        facility_id,
        staff_id,
        channel,
        event_type,
        title,
        body,
        related_type,
        related_id,
        status,
        sent_at,
        resolution_key
    ) values (
        p_facility_id,
        p_replacement_staff_id,
        'in_app',
        'cover_assigned',
        'You have been assigned emergency cover',
        case
            when debt_hours > 0 then '+' || debt_hours || 'h TOIL recorded'
            else null
        end,
        'sl_incident',
        p_incident_id,
        'sent',
        clock_timestamp(),
        p_incident_id::text || ':cover_assigned'
    )
    on conflict (resolution_key) where resolution_key is not null do nothing;

    perform set_config('emma.incident_guard', 'denied', true);

    select coalesce(
        jsonb_agg(to_jsonb(debt) order by debt.created_at, debt.id),
        '[]'::jsonb
    )
    into debts_json
    from future_debt_ledger debt
    where debt.source_incident_id = p_incident_id;

    select coalesce(
        jsonb_agg(
            jsonb_build_object(
                'date', roster_shift.date,
                'shift_type', roster_shift.shift_type,
                'shift_id', roster_shift.id,
                'shift_assignment_id', assignment.id
            )
            order by roster_shift.date, assignment.id
        ),
        '[]'::jsonb
    )
    into recovery_json
    from shift_assignments assignment
    join shifts roster_shift on roster_shift.id = assignment.shift_id
    where assignment.source_incident_id = p_incident_id
      and assignment.incident_assignment_kind = 'recovery';

    return jsonb_build_object(
        'incident', to_jsonb(incident_row),
        'future_debt', debts_json -> 0,
        'future_debts', debts_json,
        'night_recovery', recovery_json,
        'resolution_minutes', incident_row.resolution_minutes,
        'idempotent_replay', false
    );
end;
$$;

revoke all on function public.resolve_roster_incident(
    uuid, uuid, uuid, uuid, jsonb, boolean, text
) from public, anon, authenticated;
grant execute on function public.resolve_roster_incident(
    uuid, uuid, uuid, uuid, jsonb, boolean, text
) to service_role;

commit;
