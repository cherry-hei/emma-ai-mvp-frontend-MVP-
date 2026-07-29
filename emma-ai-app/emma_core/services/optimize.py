"""DB boundary for the CP-SAT solver: loads a period into solver inputs, runs the
requested plan modes, and writes each option back as a roster version. Pass a
service-role client so the bulk writeback bypasses RLS.

Schema reconciliations (no leave_requests / rule_profiles yet): demand = working
shifts of the latest ``manual`` version; hard leave = source assignments on an
``AL`` shift; baseline = every source assignment cell.
"""
from __future__ import annotations

from datetime import date as Date, datetime, timezone

from ..constants import JobStatus, PlanMode, RosterStatus, SolveStatus
from ..models import KpiSummary, OptimizeRequest, OptimizeResponse, RosterOption
from ..solver import (
    BaselineCell,
    DemandSlot,
    LockedAssignment,
    RatioRuleInput,
    ResidentCountInput,
    SolverInputs,
    SolverLimits,
    StaffInput,
    build_and_solve,
    solve_pareto,
)
from ..shifttime import duty_segments, envelope, paid_minutes
from ..solver.timeutils import to_minutes

_AUDIT_RANKS = {"RN", "EN", "HW"}      # slots of these ranks involve medication duty
_LEAVE_TYPES = {"AL"}                  # source cells meaning hard unavailability


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_date(v) -> Date:
    return v if isinstance(v, Date) else Date.fromisoformat(str(v)[:10])


def _min_to_time(m: int | None) -> str | None:
    return None if m is None else f"{m // 60:02d}:{m % 60:02d}:00"


def _segments_json(segments) -> list[dict] | None:
    """Solver segments back to the jsonb shape stored on shifts."""
    if len(segments) <= 1:
        return None                                # ordinary contiguous shift
    return [{"start": _min_to_time(s)[:5], "end": _min_to_time(e)[:5]}
            for s, e, _ in segments]


def _clock_minutes(value, fallback: str) -> int:
    if not value:
        return int(to_minutes(fallback))
    text = str(value)
    if "T" in text:
        text = text.split("T", 1)[1]
    return int(to_minutes(text[:5]))


# ── load: DB rows -> pure SolverInputs ───────────────────────────────────────
def _source_version(client, facility_id, period_id, source_version_id):
    if source_version_id:
        # facility_id filter matters: with the RLS-bypassing service-role client, a
        # source_version_id from another facility would otherwise leak its roster.
        # SQL: select * from roster_versions
        #      where id = :source_version_id and facility_id = :facility_id
        rows = (client.table("roster_versions").select("*")
                .eq("id", source_version_id).eq("facility_id", facility_id).execute().data)
        return rows[0] if rows else None
    # SQL: select * from roster_versions
    #      where facility_id = :facility_id
    #        and period_id = :period_id
    #        and version_type = 'manual'
    #      order by created_at desc
    #      limit 1
    rows = (client.table("roster_versions").select("*")
            .eq("facility_id", facility_id).eq("period_id", period_id)
            .eq("version_type", "manual").order("created_at", desc=True).limit(1).execute().data)
    return rows[0] if rows else None


def load_inputs(client, facility_id: str, period_id: str, *, source_version_id=None,
                include_staff_ids=None, exclude_staff_ids=None,
                locked_assignments=None) -> SolverInputs:
    # SQL: select * from roster_periods
    #      where id = :period_id and facility_id = :facility_id
    periods = (client.table("roster_periods").select("*")
               .eq("id", period_id).eq("facility_id", facility_id).execute().data)
    if not periods:
        raise ValueError(f"roster_period {period_id} not found")
    period = periods[0]
    period_start = _as_date(period["period_start"])
    period_end = _as_date(period["period_end"])

    src = _source_version(client, facility_id, period_id, source_version_id)
    if not src:
        raise ValueError("no source 'manual' roster version to derive demand from")

    # Flat facility-scoped reads together become SolverInputs. They are
    # deliberately unjoined: the solver wants whole tables in memory, not a
    # denormalised row set.
    #
    # SQL: select * from shifts where roster_version_id = :source_version_id
    shifts = client.table("shifts").select("*").eq("roster_version_id", src["id"]).execute().data
    shift_ids = [s["id"] for s in shifts]
    assigns = []
    if shift_ids:
        # SQL: select * from shift_assignments where shift_id = any(:shift_ids)
        assigns = (client.table("shift_assignments").select("*")
                   .in_("shift_id", shift_ids).execute().data)

    # SQL: select * from staff where facility_id = :facility_id and status = 'active'
    staff_rows = (client.table("staff").select("*")
                  .eq("facility_id", facility_id).eq("status", "active").execute().data)
    # SQL: select * from staff_contracts where facility_id = :facility_id
    contracts = client.table("staff_contracts").select("*").eq("facility_id", facility_id).execute().data
    contract_by_staff = {c["staff_id"]: c for c in contracts}
    # SQL: select * from staffing_ratio_rules
    #      where (facility_id = :facility_id or facility_id is null)   -- null = statutory
    #        and active = true
    rules = (client.table("staffing_ratio_rules").select("*")
             .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
             .eq("active", True).execute().data)
    # SQL: select * from daily_resident_counts
    #      where facility_id = :facility_id
    #        and date >= :period_start and date <= :period_end
    counts = (client.table("daily_resident_counts").select("*")
              .eq("facility_id", facility_id)
              .gte("date", str(period_start)).lte("date", str(period_end)).execute().data)
    # Phase 4 additive event requirements become independent demand slots. A
    # concurrent requirement (podiatry/weighing) stays a validation-only overlay.
    events = (client.table("facility_events").select("*")
              .eq("facility_id", facility_id)
              .gte("date", str(period_start)).lte("date", str(period_end))
              .execute().data)
    event_requirements = []
    if events:
        event_requirements = (
            client.table("event_staffing_requirements").select("*")
            .eq("facility_id", facility_id)
            .in_("event_id", [event["id"] for event in events])
            .execute().data
        )
    # SQL: select * from calendar_days
    #      where (facility_id = :facility_id or facility_id is null)
    # (unbounded by date — the whole calendar is pulled, then indexed by date below)
    calendar = (client.table("calendar_days").select("*")
                .or_(f"facility_id.eq.{facility_id},facility_id.is.null").execute().data)
    cal_by_date = {_as_date(c["date"]): c for c in calendar}

    period_days = (period_end - period_start).days + 1
    weeks = period_days / 7
    max_work_days = max(1, period_days - period_days // 7)   # ~1 rest day / week

    # ── staff (with Home-B defaults where no contract row exists) ──
    staff: list[StaffInput] = []
    for st in staff_rows:
        c = contract_by_staff.get(st["id"]) or {}
        weekly = c.get("weekly_hours") or st.get("contracted_hours") or 0
        max_weekly = c.get("max_weekly_hours")
        staff.append(StaffInput(
            id=st["id"], rank=st["rank"], employment_type=st["employment_type"],
            primary_unit_id=st.get("primary_unit_id"),
            is_audited_for_medication=bool(st.get("is_audited_for_medication")),
            min_rest_minutes=int(c.get("min_rest_minutes") or 720),
            allowed_shift_types=frozenset(c.get("allowed_shift_types") or []),
            contracted_period_minutes=round(float(weekly) * weeks * 60),
            max_period_minutes=round(float(max_weekly) * weeks * 60) if max_weekly else 0,
            max_work_days=max_work_days,
        ))

    # ── demand + baseline + leave (all from the source version) ──
    assign_by_shift: dict[str, list] = {}
    for a in assigns:
        assign_by_shift.setdefault(a["shift_id"], []).append(a)

    demand: list[DemandSlot] = []
    baseline: list[BaselineCell] = []
    leave: set[tuple[str, Date]] = set()
    for s in shifts:
        d = _as_date(s["date"])
        working = bool(s.get("is_working"))
        for a in assign_by_shift.get(s["id"], []):
            if a.get("staff_id"):
                baseline.append(BaselineCell(staff_id=a["staff_id"], date=d,
                                             shift_type=s["shift_type"], is_working=working))
                if s["shift_type"] in _LEAVE_TYPES:
                    leave.add((a["staff_id"], d))
        if not working:
            continue
        segments = duty_segments(s)
        span = envelope(s)
        if not span:
            continue
        start, end, cross = span
        rank = s.get("required_rank")
        cal = cal_by_date.get(d)
        demand.append(DemandSlot(
            id=s["id"], date=d, day_index=(d - period_start).days, shift_type=s["shift_type"],
            start_min=start, end_min=end, cross_midnight=cross,
            duration_min=paid_minutes(s), segments=segments,
            unit_id=s.get("unit_id"), required_rank=rank,
            required_count=int(s.get("required_count") or 1),
            requires_medication=rank in _AUDIT_RANKS,
            agency_allowed=bool(cal["is_agency_allowed"]) if cal else True,
            agency_cost_scaled=round(float(cal["agency_cost_multiplier"]) * 10) if cal else 10,
        ))

    event_by_id = {event["id"]: event for event in events}
    for requirement in event_requirements:
        if not requirement.get("is_additive", True):
            continue
        event = event_by_id.get(requirement.get("event_id"))
        if not event:
            continue
        d = _as_date(event["date"])
        start = _clock_minutes(event.get("start_at"), "00:00")
        end = _clock_minutes(event.get("end_at"), "24:00")
        cross = end <= start
        duration = ((1440 - start) + end) if cross else end - start
        cal = cal_by_date.get(d)
        event_type = str(event.get("event_type") or "event")
        demand.append(DemandSlot(
            id=f"event:{event['id']}:{requirement['id']}",
            date=d,
            day_index=(d - period_start).days,
            shift_type=f"EVENT:{event_type}",
            start_min=start,
            end_min=end,
            cross_midnight=cross,
            duration_min=duration,
            segments=((start, end, cross),),
            unit_id=event.get("unit_id"),
            required_rank=requirement.get("rank"),
            required_count=int(requirement.get("count") or 1),
            requires_medication=event_type.lower().startswith("medication"),
            agency_allowed=bool(cal["is_agency_allowed"]) if cal else True,
            agency_cost_scaled=(
                round(float(cal["agency_cost_multiplier"]) * 10) if cal else 10
            ),
            is_event_overlay=True,
        ))

    ratio_rules = [RatioRuleInput(
        window_start_min=to_minutes(r["time_window_start"]),
        window_end_min=to_minutes(r["time_window_end"]),
        staff_rank=r.get("staff_rank"),
        ratio_residents_per_staff=r.get("ratio_residents_per_staff"),
        min_staff_any_rank=r.get("min_staff_any_rank"),
    ) for r in rules]

    resident_counts = [ResidentCountInput(
        date=_as_date(rc["date"]), resident_count=int(rc["resident_count"]),
        unit_id=rc.get("unit_id"),
    ) for rc in counts]

    locks = tuple(LockedAssignment(staff_id=lk["staff_id"], slot_id=lk["slot_id"],
                                   pin=bool(lk.get("pin", True)))
                  for lk in (locked_assignments or []))

    return SolverInputs(
        facility_id=facility_id, period_id=period_id,
        period_start=period_start, period_end=period_end,
        staff=tuple(staff), demand=tuple(demand), ratio_rules=tuple(ratio_rules),
        resident_counts=tuple(resident_counts), baseline=tuple(baseline),
        leave_unavailable=frozenset(leave), locks=locks,
        include_staff_ids=frozenset(include_staff_ids or []),
        exclude_staff_ids=frozenset(exclude_staff_ids or []),
    )


# ── run + writeback ──────────────────────────────────────────────────────────
def run_optimization(client, request: OptimizeRequest, *, persist: bool = True,
                     job_id: str | None = None, pareto: bool = False) -> OptimizeResponse:
    """Run the solver for the requested plan mode(s), optionally persisting each option
    as a roster version. Pass ``job_id`` for an already-enqueued PENDING job (async
    path); otherwise a RUNNING job is created inline. With ``pareto`` the three
    options come off a non-dominated frontier instead of the fixed A/B/C presets."""
    persist = persist and request.writeback.persist
    created_here = job_id is None
    if created_here:
        job_id = _create_job(client, request)
    try:
        if not created_here:
            # inside the try so a failure here is captured by _fail_job, not orphaned.
            _start_job(client, job_id)
        inputs = load_inputs(
            client, request.facility_id, request.period_id,
            source_version_id=request.source_version_id,
            include_staff_ids=request.include_staff_ids,
            exclude_staff_ids=request.exclude_staff_ids,
            locked_assignments=request.locked_assignments,
        )
        limits = SolverLimits(max_seconds=request.solver_limits.max_seconds,
                              workers=request.solver_limits.workers,
                              seed=request.solver_limits.seed)
        if persist and request.writeback.archive_previous_auto:
            _archive_previous(client, request.facility_id, request.period_id)

        meta: dict | None = None
        if pareto:
            solved, meta = solve_pareto(inputs, limits)
        else:
            modes = ([request.plan_mode] if request.plan_mode
                     else [PlanMode.A, PlanMode.B, PlanMode.C])
            solved = build_and_solve(inputs, modes, limits)

        options: list[RosterOption] = []
        for res in solved:
            version_id = None
            if persist and res.status != SolveStatus.INFEASIBLE:
                version_id = _writeback_version(client, request, inputs, res)
            options.append(_to_option(res, version_id))

        _complete_job(client, job_id, options, meta=meta)
        return OptimizeResponse(job_id=job_id, status=JobStatus.COMPLETED,
                                roster_options=options)
    except Exception as exc:  # noqa: BLE001
        _fail_job(client, job_id, exc)
        raise


def _to_option(res, version_id) -> RosterOption:
    return RosterOption(
        plan_mode=res.plan_mode, version_label=res.label, status=res.status,
        roster_version_id=version_id,
        constraint_score=res.constraint_score,
        hard_violation_count=res.hard_violation_count,
        soft_penalty_total=res.soft_penalty_total,
        kpi=KpiSummary(
            headcount_assigned=res.kpi.headcount_assigned,
            agency_count=res.kpi.agency_count,
            ot_hours=round(res.kpi.ot_minutes / 60, 1),
            coverage_gap=res.kpi.coverage_gap,
            ratio_breaches=res.kpi.ratio_breaches,
            deviation_from_baseline=res.kpi.deviation_from_baseline,
            fairness_spread_minutes=res.kpi.fairness_spread_minutes,
        ),
        infeasible_reasons=list(res.infeasible_reasons),
    )


def _archive_previous(client, facility_id, period_id) -> None:
    # SQL: update roster_versions set status = 'archived'
    #      where facility_id = :facility_id and period_id = :period_id
    #        and version_type = any('{A,B,C}')
    #        and status = 'draft'
    #      returning *
    (client.table("roster_versions").update({"status": RosterStatus.ARCHIVED})
     .eq("facility_id", facility_id).eq("period_id", period_id)
     .in_("version_type", [PlanMode.A, PlanMode.B, PlanMode.C])
     .eq("status", RosterStatus.DRAFT).execute())


def _writeback_version(client, request, inputs, res) -> str:
    # SQL: insert into roster_versions
    #        (facility_id, period_id, version_type, label, status, created_by)
    #      values (:facility_id, :period_id, :plan_mode, :label, 'draft', :created_by)
    #      returning id
    version_id = (client.table("roster_versions").insert({
        "facility_id": request.facility_id, "period_id": request.period_id,
        "version_type": str(res.plan_mode), "label": f"{res.label} · auto",
        "status": RosterStatus.DRAFT, "created_by": request.created_by,
    }).execute().data[0]["id"])

    # one fresh shift per demand slot; keep source-slot -> new-shift id map
    #
    # SQL (once per demand slot — an N-statement loop, not a single multi-row insert,
    #      because each returned shift id has to be mapped back to its solver slot):
    #      insert into shifts
    #        (facility_id, roster_version_id, date, shift_type, start_time, end_time,
    #         cross_midnight, unit_id, required_rank, required_count, is_working,
    #         segments, paid_minutes)
    #      values (:facility_id, :version_id, :date, :shift_type, :start_time,
    #              :end_time, :cross_midnight, :unit_id, :required_rank,
    #              :required_count, true, :segments::jsonb, :paid_minutes)
    #      returning id
    slot_to_shift: dict[str, str] = {}
    for sl in inputs.demand:
        new_id = (client.table("shifts").insert({
            "facility_id": request.facility_id, "roster_version_id": version_id,
            "date": str(sl.date), "shift_type": sl.shift_type,
            "start_time": _min_to_time(sl.start_min), "end_time": _min_to_time(sl.end_min),
            "cross_midnight": sl.cross_midnight, "unit_id": sl.unit_id,
            "required_rank": (
                sl.required_rank if "|" not in (sl.required_rank or "") else None
            ),
            "required_count": sl.required_count,
            "is_working": True,
            # carry the split-shift shape through, else a solver option would
            # silently re-inflate an A/N shift back to its elapsed span
            "segments": _segments_json(sl.segments), "paid_minutes": sl.duration_min,
        }).execute().data[0]["id"])
        slot_to_shift[sl.id] = new_id

    rows = [{
        "facility_id": request.facility_id, "shift_id": slot_to_shift[a.slot_id],
        "staff_id": a.staff_id, "role": a.role, "status": "assigned", "is_agency": a.is_agency,
    } for a in res.assignments if a.slot_id in slot_to_shift]
    if rows:
        # SQL: insert into shift_assignments
        #        (facility_id, shift_id, staff_id, role, status, is_agency)
        #      values (...), (...), ...      -- one tuple per solver assignment
        #      returning *
        client.table("shift_assignments").insert(rows).execute()

    # SQL: insert into roster_option_scores
    #        (facility_id, roster_version_id, plan_mode, constraint_score,
    #         hard_violation_count, soft_penalty_total, objective_weights_json,
    #         infeasible_reasons_json)
    #      values (:facility_id, :version_id, :plan_mode, :constraint_score,
    #              :hard_violation_count, :soft_penalty_total,
    #              :weights::jsonb, :infeasible_reasons::jsonb)
    #      returning *
    client.table("roster_option_scores").insert({
        "facility_id": request.facility_id, "roster_version_id": version_id,
        "plan_mode": str(res.plan_mode), "constraint_score": res.constraint_score,
        "hard_violation_count": res.hard_violation_count,
        "soft_penalty_total": res.soft_penalty_total,
        "objective_weights_json": res.weights,
        "infeasible_reasons_json": list(res.infeasible_reasons),
    }).execute()

    vrows = [{
        "facility_id": request.facility_id, "roster_version_id": version_id,
        "rule_code": str(v.rule_code),
        "shift_id": slot_to_shift.get(v.slot_id) if v.slot_id else None,
        "severity": v.severity, "message": v.message, "resolved": False,
    } for v in res.violations]
    if vrows:
        # SQL: insert into violation_log
        #        (facility_id, roster_version_id, rule_code, shift_id, severity,
        #         message, resolved)
        #      values (...), (...), ...      -- one tuple per solver violation
        #      returning *
        client.table("violation_log").insert(vrows).execute()

    return version_id


# ── optimization_jobs lifecycle ──────────────────────────────────────────────
def enqueue_optimization(client, request: OptimizeRequest) -> str:
    """Insert a PENDING job and return its id immediately; the HTTP layer runs
    ``run_optimization(..., job_id=job_id)`` in the background so the request doesn't
    block on the CP-SAT solves."""
    # SQL: insert into optimization_jobs
    #        (facility_id, period_id, rule_profile_id, status, plan_mode,
    #         solver_limits_json, input_payload_json)
    #      values (:facility_id, :period_id, :rule_profile_id, 'pending', :plan_mode,
    #              :solver_limits::jsonb, :input_payload::jsonb)
    #      returning id
    return (client.table("optimization_jobs").insert({
        "facility_id": request.facility_id, "period_id": request.period_id,
        "rule_profile_id": request.rule_profile_id, "status": JobStatus.PENDING,
        "plan_mode": str(request.plan_mode) if request.plan_mode else None,
        "solver_limits_json": request.solver_limits.model_dump(),
        "input_payload_json": request.model_dump(mode="json"),
    }).execute().data[0]["id"])


def _create_job(client, request: OptimizeRequest) -> str:
    # SQL: insert into optimization_jobs
    #        (facility_id, period_id, rule_profile_id, status, plan_mode,
    #         solver_limits_json, input_payload_json, started_at)
    #      values (:facility_id, :period_id, :rule_profile_id, 'running', :plan_mode,
    #              :solver_limits::jsonb, :input_payload::jsonb, now())
    #      returning id
    return (client.table("optimization_jobs").insert({
        "facility_id": request.facility_id, "period_id": request.period_id,
        "rule_profile_id": request.rule_profile_id, "status": JobStatus.RUNNING,
        "plan_mode": str(request.plan_mode) if request.plan_mode else None,
        "solver_limits_json": request.solver_limits.model_dump(),
        "input_payload_json": request.model_dump(mode="json"),
        "started_at": _now(),
    }).execute().data[0]["id"])


def _start_job(client, job_id: str) -> None:
    # SQL: update optimization_jobs set status = 'running', started_at = now()
    #      where id = :job_id
    #      returning *
    (client.table("optimization_jobs").update({
        "status": JobStatus.RUNNING, "started_at": _now(),
    }).eq("id", job_id).execute())


def _complete_job(client, job_id: str, options, *, meta: dict | None = None) -> None:
    result = {"roster_options": [o.model_dump(mode="json") for o in options]}
    if meta:
        result["pareto"] = meta
    # SQL: update optimization_jobs
    #      set status = 'completed', result_json = :result::jsonb, completed_at = now()
    #      where id = :job_id
    #      returning *
    (client.table("optimization_jobs").update({
        "status": JobStatus.COMPLETED, "result_json": result, "completed_at": _now(),
    }).eq("id", job_id).execute())


def _fail_job(client, job_id: str, exc: Exception) -> None:
    try:
        # SQL: update optimization_jobs
        #      set status = 'failed', error_json = :error::jsonb, completed_at = now()
        #      where id = :job_id
        #      returning *
        (client.table("optimization_jobs").update({
            "status": JobStatus.FAILED,
            "error_json": {"type": type(exc).__name__, "message": str(exc)},
            "completed_at": _now(),
        }).eq("id", job_id).execute())
    except Exception:  # noqa: BLE001 — never mask the original error
        pass


def get_job(client, job_id: str) -> dict | None:
    # SQL: select * from optimization_jobs where id = :job_id
    rows = client.table("optimization_jobs").select("*").eq("id", job_id).execute().data
    return rows[0] if rows else None


# ── option-score reads (compare / publish-guard UI) ──────────────────────────
def get_option_scores(client, roster_version_id: str) -> dict | None:
    """Score row + hard-violation detail for one roster version."""
    # SQL: select * from roster_option_scores
    #      where roster_version_id = :roster_version_id
    #      limit 1
    rows = (client.table("roster_option_scores").select("*")
            .eq("roster_version_id", roster_version_id).limit(1).execute().data)
    if not rows:
        return None
    score = rows[0]
    # SQL: select * from violation_log
    #      where roster_version_id = :roster_version_id
    #      order by created_at
    score["violations"] = (client.table("violation_log").select("*")
                           .eq("roster_version_id", roster_version_id)
                           .order("created_at").execute().data)
    return score


def list_period_option_scores(client, period_id: str) -> list[dict]:
    """All A/B/C option scores for a period, for the side-by-side compare table."""
    # SQL: select id, version_type, label, status from roster_versions
    #      where period_id = :period_id
    #        and version_type = any('{A,B,C}')
    versions = (client.table("roster_versions").select("id,version_type,label,status")
                .eq("period_id", period_id)
                .in_("version_type", [PlanMode.A, PlanMode.B, PlanMode.C])
                .execute().data)
    by_version = {v["id"]: v for v in versions}
    if not by_version:
        return []
    # SQL: select * from roster_option_scores
    #      where roster_version_id = any(:version_ids)
    # (the label/status columns are grafted on in Python rather than joined)
    scores = (client.table("roster_option_scores").select("*")
              .in_("roster_version_id", list(by_version)).execute().data)
    for s in scores:
        v = by_version.get(s["roster_version_id"], {})
        s["version_label"] = v.get("label")
        s["version_status"] = v.get("status")
    return scores
