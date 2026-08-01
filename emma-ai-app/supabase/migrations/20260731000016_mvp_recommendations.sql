-- Recommend-vs-approve for the Approval Centre (spec 1.1).
--
-- From the RBAC definition of 30 Jul 2026:
--
--   "Admin / Nursing Officer / PT / OT can recommend (mark suggest-approve /
--    suggest-reject with reason = first-pass review), but final approval is
--    exclusively Superintendent/Deputy Superintendent (SA) or 主任/副主任 (NAAC).
--    Data model: approval record needs recommendation (who/what/reason/timestamp,
--    writable by R roles) + final_decision (writable only by OWNER). Approver UI
--    must show pending items together with all recommendations attached."
--
-- Why a table and not three columns on leave_requests: "all recommendations"
-- is plural. A nursing officer and an admin clerk can both review the same
-- request, and they can disagree - that disagreement is exactly what the
-- superintendent needs to see, so it cannot be flattened into one column.
--
-- The final decision stays on leave_requests (decided_by / decided_at /
-- decision_note, already present). This migration only adds the recommendation
-- side plus the two states the spec needs that the status check was missing.

-- ── request_recommendations ─────────────────────────────────────────────────
create table if not exists request_recommendations (
    id               uuid primary key default gen_random_uuid(),
    facility_id      uuid not null references facilities(id) on delete cascade,
    leave_request_id uuid not null references leave_requests(id) on delete cascade,
    -- The reviewer, and the role they held when they reviewed. The role is
    -- copied rather than joined: a nursing officer who later becomes a
    -- superintendent must not retroactively turn their recommendation into an
    -- approval, and an audit reader needs to know the authority at the time.
    recommended_by   uuid not null references users_profile(id) on delete restrict,
    recommended_role text not null,
    recommendation   text not null check (recommendation in ('approve', 'reject')),
    -- Required. A first-pass review with no reason is not a review; the doc
    -- specifies "suggest-approve/suggest-reject with reason".
    reason           text not null check (length(btrim(reason)) > 0),
    created_at       timestamptz not null default now(),
    withdrawn_at     timestamptz,
    -- One live recommendation per person per request. Re-reviewing means
    -- withdrawing the first, which keeps both on the record.
    constraint uq_recommendation_per_reviewer
        unique (leave_request_id, recommended_by, created_at)
);

create index if not exists idx_recommendations_request
    on request_recommendations(leave_request_id) where withdrawn_at is null;
create index if not exists idx_recommendations_facility
    on request_recommendations(facility_id, created_at desc);

comment on table request_recommendations is
    'First-pass reviews by R-grade roles. Never a decision - see leave_requests.decided_by.';
comment on column request_recommendations.recommended_role is
    'Role held at the time of review, copied deliberately so later promotions cannot rewrite authority.';

-- ── statuses the spec needs ─────────────────────────────────────────────────
-- The state machine is PENDING -> (recommendations) -> APPROVE / REJECT / CANCEL,
-- and an APPROVE may later be REVOKED. 'revoked' was missing, so a withdrawn
-- approval had nowhere to go but back to a state that loses the history.
alter table leave_requests drop constraint if exists leave_requests_status_check;
alter table leave_requests add constraint leave_requests_status_check
    check (status in ('pending','reviewed','approved','rejected','cancelled','revoked'));

-- Who revoked, when and why. Separate from decided_* so the original approval
-- stays legible after it is withdrawn.
alter table leave_requests add column if not exists revoked_by
    uuid references users_profile(id) on delete set null;
alter table leave_requests add column if not exists revoked_at   timestamptz;
alter table leave_requests add column if not exists revoke_reason text;

-- ── RLS ─────────────────────────────────────────────────────────────────────
-- Tenant-scoped like every other table. The role rules (who may recommend, who
-- may decide) are enforced in the API against the permission matrix rather than
-- here: the matrix is the single source of truth and duplicating it in SQL is how
-- the two drift. RLS guarantees the facility boundary, which is the part that
-- must hold even if the API is wrong.
alter table request_recommendations enable row level security;
drop policy if exists request_recommendations_tenant on request_recommendations;
create policy request_recommendations_tenant on request_recommendations
    for all to authenticated
    using (facility_id = public.current_facility_id())
    with check (facility_id = public.current_facility_id());

grant select, insert, update on request_recommendations to authenticated;

-- ── a recommendation is not editable history ────────────────────────────────
-- Withdrawing is the only permitted update. Rewriting the reason after the
-- superintendent has read it would make the approval trail unusable as evidence,
-- which is the same reason audit_logs is append-only.
create or replace function trg_recommendation_append_only()
returns trigger language plpgsql as $$
begin
    if old.withdrawn_at is null and new.withdrawn_at is not null
       and new.leave_request_id = old.leave_request_id
       and new.recommended_by   = old.recommended_by
       and new.recommendation   = old.recommendation
       and new.reason           = old.reason
       and new.created_at       = old.created_at then
        return new;
    end if;
    raise exception
        'request_recommendations is append-only; withdraw and add a new one instead';
end;
$$;

drop trigger if exists protect_recommendations on request_recommendations;
create trigger protect_recommendations
    before update on request_recommendations
    for each row execute function trg_recommendation_append_only();
