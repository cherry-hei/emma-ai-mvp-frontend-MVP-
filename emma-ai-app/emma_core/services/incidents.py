"""Urgent SL/DSL incidents, ratio-checked replacement suggestions and the
emergency-cover close-loop (spec 4.3 / 4.5 / 3.8).

Candidate ranking is deliberately rule-based, not a model: every candidate is
either compliance-clean or carries the explicit reasons it is blocked, so a
suggestion can never quietly break a statutory rule. Resolving an incident
re-rosters the shift, records the TOIL/OT owed in the future-debt ledger, and
stamps the response time that feeds the A2 ROI figure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date, datetime, timedelta, timezone

from ..constants import can_cover_rank
from . import notifications as notify, validation
from ._common import (
    LEAVE_CODES, as_date, iso, month_bounds, now_iso, operative_version,
    assignments_for_shifts,
    resolve_period, shift_minutes, staff_brief, staff_by_id, to_min,
)
from .compliance import compute_ratios

CERT_WARN_DAYS = 90
AUDIT_RANKS = {"RN", "EN", "HW"}       # slots whose duties include medication


@dataclass(frozen=True, slots=True)
class _NightPolicy:
    night_types: frozenset[str]
    chain_employment_types: frozenset[str]
    sleep_codes: tuple[str, ...]
    day_off_codes: tuple[str, ...]
    cooldown_ranks: frozenset[str]
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class _RecoveryTarget:
    day: Date
    code: str
    version_id: str
    definition: dict


def _periods(client, facility_id: str) -> list[dict]:
    rows = (
        client.table("roster_periods")
        .select("*")
        .eq("facility_id", facility_id)
        .order("period_start")
        .execute()
        .data
    )
    return sorted(rows, key=lambda row: iso(row["period_start"]))


def _period_containing(periods: list[dict], day: Date) -> dict | None:
    key = day.isoformat()
    return next(
        (
            row for row in periods
            if iso(row["period_start"]) <= key <= iso(row["period_end"])
        ),
        None,
    )


def _shift_roster_context(
    client,
    facility_id: str,
    shift: dict,
) -> tuple[dict, str]:
    """Resolve and tenant-check the roster version/period that owns a shift."""
    version_id = shift.get("roster_version_id")
    if version_id:
        versions = (
            client.table("roster_versions")
            .select("*")
            .eq("facility_id", facility_id)
            .eq("id", version_id)
            .execute()
            .data
        )
        if not versions:
            raise ValueError("incident shift does not belong to this facility roster")
        period_id = versions[0].get("period_id")
        if not period_id:
            raise ValueError("incident shift roster has no period")
        period = resolve_period(client, facility_id, period_id)
        if not period:
            raise ValueError("incident shift roster period was not found")
        day = as_date(shift["date"])
        if not (
            as_date(period["period_start"]) <= day <= as_date(period["period_end"])
        ):
            raise ValueError("incident shift date is outside its roster period")
        return period, version_id

    periods = _periods(client, facility_id)
    period = _period_containing(periods, as_date(shift["date"]))
    if not period:
        raise ValueError("no roster period covers the incident shift")
    version = operative_version(client, facility_id, period["id"])
    if not version:
        raise ValueError("incident shift has no operative roster version")
    return period, version["id"]


def _night_policy(
    client,
    facility_id: str,
    period: dict,
) -> _NightPolicy:
    """Load the same period-frozen night policy used by validation/optimization."""
    on_date = as_date(period["period_start"])
    rows = (
        client.table("rule_definitions")
        .select("*")
        .eq("rule_code", "night_chain")
        .execute()
        .data
    )
    eligible = [
        row for row in rows
        if row.get("active", True)
        and row.get("facility_id") in (None, facility_id)
        and (
            not row.get("effective_from")
            or as_date(row["effective_from"]) <= on_date
        )
        and (
            not row.get("effective_to")
            or as_date(row["effective_to"]) >= on_date
        )
    ]
    eligible.sort(
        key=lambda row: (
            row.get("facility_id") == facility_id,
            int(row.get("config_version") or 1),
            str(row.get("effective_from") or ""),
        ),
        reverse=True,
    )
    config = dict(validation.DEFAULT_NIGHT_POLICY)
    if eligible:
        config.update(eligible[0].get("config_json") or {})
    return _NightPolicy(
        night_types=frozenset(
            str(value).upper() for value in config.get("night_shift_types", ())
        ),
        chain_employment_types=frozenset(
            str(value) for value in config.get("chain_employment_types", ())
        ),
        sleep_codes=tuple(
            str(value).upper() for value in config.get("sleep_codes", ())
        ),
        day_off_codes=tuple(
            str(value).upper() for value in config.get("day_off_codes", ())
        ),
        cooldown_ranks=frozenset(
            str(value).upper() for value in config.get("cooldown_ranks", ())
        ),
        rule_id=eligible[0].get("id") if eligible else None,
    )


def _next_period(periods: list[dict], period: dict) -> dict | None:
    boundary = as_date(period["period_end"])
    return next(
        (
            row for row in periods
            if as_date(row["period_start"]) > boundary
        ),
        None,
    )


def _recovery_targets(
    client,
    facility_id: str,
    shift: dict,
    period: dict,
    version_id: str,
    policy: _NightPolicy,
    periods: list[dict],
) -> tuple[list[_RecoveryTarget], list[str]]:
    """Plan the exact SLEEP/DO cells needed after a configured night shift."""
    if str(shift.get("shift_type") or "").upper() not in policy.night_types:
        return [], []

    definitions = (
        client.table("shift_definitions")
        .select("*")
        .eq("facility_id", facility_id)
        .execute()
        .data
    )
    definition_by_code = {
        str(row.get("shift_type") or "").upper(): row
        for row in definitions
        if not row.get("is_working", False)
    }

    required = (
        (1, policy.sleep_codes, "sleeping-day"),
        (2, policy.day_off_codes, "day-off"),
    )
    targets: list[_RecoveryTarget] = []
    issues: list[str] = []
    shift_day = as_date(shift["date"])
    for offset, alternatives, label in required:
        code = next((value for value in alternatives if value in definition_by_code), None)
        if not code:
            issues.append(
                f"no non-working {label} shift definition is configured "
                f"({', '.join(alternatives)})"
            )
            continue

        day = shift_day + timedelta(days=offset)
        target_period = _period_containing(periods, day)
        if not target_period:
            issues.append(f"no roster period covers mandatory recovery on {day}")
            continue
        if target_period["id"] == period["id"]:
            target_version_id = version_id
        else:
            target_version = operative_version(
                client,
                facility_id,
                target_period["id"],
            )
            if not target_version:
                issues.append(
                    f"no operative roster exists for mandatory recovery on {day}"
                )
                continue
            target_version_id = target_version["id"]
        targets.append(_RecoveryTarget(
            day=day,
            code=code,
            version_id=target_version_id,
            definition=definition_by_code[code],
        ))
    return targets, issues


def _target_assignments(
    client,
    facility_id: str,
    targets: list[_RecoveryTarget],
) -> dict[tuple[str, Date], list[dict]]:
    if not targets:
        return {}
    version_ids = sorted({target.version_id for target in targets})
    wanted = {
        (target.version_id, target.day.isoformat()) for target in targets
    }
    shifts = (
        client.table("shifts")
        .select("*")
        .eq("facility_id", facility_id)
        .in_("roster_version_id", version_ids)
        .execute()
        .data
    )
    shifts = [
        row for row in shifts
        if (row.get("roster_version_id"), iso(row.get("date"))) in wanted
    ]
    if not shifts:
        return {}
    by_id = {row["id"]: row for row in shifts}
    assignments = assignments_for_shifts(
        client, by_id, select="shift_id,staff_id,status", facility_id=facility_id)
    out: dict[tuple[str, Date], list[dict]] = {}
    for assignment in assignments:
        if assignment.get("status") == "cancelled":
            continue
        shift = by_id.get(assignment.get("shift_id"))
        staff_id = assignment.get("staff_id")
        if not shift or not staff_id:
            continue
        out.setdefault((staff_id, as_date(shift["date"])), []).append(shift)
    return out


def _recovery_issues(
    staff: dict,
    targets: list[_RecoveryTarget],
    setup_issues: list[str],
    assigned: dict[tuple[str, Date], list[dict]],
    on_leave: set[tuple[str, str]],
) -> list[str]:
    issues = list(setup_issues)
    staff_id = staff["id"]
    for target in targets:
        if (staff_id, target.day.isoformat()) in on_leave:
            issues.append(
                f"approved leave conflicts with mandatory {target.code} "
                f"recovery on {target.day}"
            )
        existing = assigned.get((staff_id, target.day), [])
        wrong = [
            str(row.get("shift_type") or "")
            for row in existing
            if str(row.get("shift_type") or "").upper() != target.code
        ]
        if wrong:
            issues.append(
                f"mandatory {target.code} recovery on {target.day} conflicts "
                f"with {', '.join(sorted(set(wrong)))}"
            )
    return issues


# ── reads ────────────────────────────────────────────────────────────────────
def _incident_out(row: dict, staff: dict[str, dict], shifts: dict[str, dict]) -> dict:
    sh = shifts.get(row.get("shift_id") or "") or {}
    replacement = staff.get(row.get("replacement_staff_id") or "")
    return {
        **staff_brief(staff.get(row["staff_id"])),
        "id": row["id"],
        "incident_type": row["incident_type"],
        "reason": row.get("reason"),
        "reported_at": row["reported_at"],
        "date": iso(sh.get("date")) if sh.get("date") else iso(row["reported_at"]),
        "shift_id": row.get("shift_id"),
        "shift_type": sh.get("shift_type"),
        "shift_window": (f'{(sh.get("start_time") or "")[:5]}–{(sh.get("end_time") or "")[:5]}'
                         if sh.get("start_time") else None),
        "status": row["replacement_status"],
        "resolved": row["replacement_status"] == "resolved",
        "resolved_at": row.get("resolved_at"),
        "resolution_minutes": row.get("resolution_minutes"),
        "auto_resolved": bool(row.get("auto_resolved")),
        "replacement_staff_id": row.get("replacement_staff_id"),
        "replacement_name": (replacement or {}).get("name_en") or (replacement or {}).get("name"),
        "notes": row.get("notes"),
    }


def _shifts_by_id(client, ids: list[str]) -> dict[str, dict]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    # SQL: select * from shifts where id = any(:ids)
    rows = client.table("shifts").select("*").in_("id", ids).execute().data
    return {r["id"]: r for r in rows}


def list_incidents(client, facility_id: str, *, status: str | None = None,
                   since: Date | None = None, staff_id: str | None = None,
                   limit: int = 50) -> list[dict]:
    # SQL: select * from sl_incidents
    #      where facility_id = :facility_id
    #        [and replacement_status = :status]   -- when status is given
    #        [and staff_id = :staff_id]           -- when staff_id is given
    #        [and reported_at >= :since::date]    -- when since is given
    #      order by reported_at desc
    #      limit :limit
    q = client.table("sl_incidents").select("*").eq("facility_id", facility_id)
    if status:
        q = q.eq("replacement_status", status)
    if staff_id:
        q = q.eq("staff_id", staff_id)
    if since:
        q = q.gte("reported_at", f"{since}T00:00:00Z")
    rows = q.order("reported_at", desc=True).limit(limit).execute().data
    staff = staff_by_id(client, facility_id)
    shifts = _shifts_by_id(client, [r.get("shift_id") for r in rows])
    return [_incident_out(r, staff, shifts) for r in rows]


def get_incident(client, facility_id: str, incident_id: str) -> dict | None:
    # SQL: select * from sl_incidents
    #      where facility_id = :facility_id and id = :incident_id
    rows = (client.table("sl_incidents").select("*")
            .eq("facility_id", facility_id).eq("id", incident_id).execute().data)
    if not rows:
        return None
    staff = staff_by_id(client, facility_id)
    shifts = _shifts_by_id(client, [rows[0].get("shift_id")])
    return _incident_out(rows[0], staff, shifts)


def stats(client, facility_id: str, on: Date | None = None) -> dict:
    """Month-to-date incident KPIs - the four cards on Dashboard and Alert."""
    start, end = month_bounds(on)
    # SQL: select * from sl_incidents
    #      where facility_id = :facility_id
    #        and reported_at >= :month_start::date
    #        and reported_at <= (:month_end::date + time '23:59:59')
    # Every counter below (open / resolved / auto / avg response / per-type
    # distribution) is tallied in Python from this one fetch.
    rows = (client.table("sl_incidents").select("*")
            .eq("facility_id", facility_id)
            .gte("reported_at", f"{start}T00:00:00Z")
            .lte("reported_at", f"{end}T23:59:59Z").execute().data)

    resolved = [r for r in rows if r["replacement_status"] == "resolved"]
    auto = [r for r in resolved if r.get("auto_resolved")]
    durations = [r["resolution_minutes"] for r in resolved if r.get("resolution_minutes")]

    order = ["SL", "DSL", "urgent", "late"]
    counts = {k: 0 for k in order}
    for r in rows:
        counts[r["incident_type"]] = counts.get(r["incident_type"], 0) + 1
    total = len(rows)
    distribution = [{
        "incident_type": k, "count": counts[k],
        "pct": round(counts[k] / total * 100) if total else 0,
    } for k in order]

    return {
        "month_start": start, "month_end": end,
        "total": total,
        "open": len([r for r in rows if r["replacement_status"] in ("open", "notified")]),
        "resolved": len(resolved),
        "auto_resolved": len(auto),
        "auto_resolved_pct": round(len(auto) / total * 100, 1) if total else 0.0,
        "avg_response_minutes": round(sum(durations) / len(durations)) if durations else 0,
        "distribution": distribution,
    }


# ── create ───────────────────────────────────────────────────────────────────
def _find_shift_for(client, facility_id: str, staff_id: str, on_date: Date) -> dict | None:
    """The working shift this staff member was rostered on for `on_date`, in the
    operative (published, else manual) version - the slot that now needs cover."""
    period = resolve_period(client, facility_id, None)
    if not period:
        return None
    version = operative_version(client, facility_id, period["id"])
    if not version:
        return None
    # SQL: select * from shifts
    #      where roster_version_id = :version_id
    #        and date = :on_date
    #        and is_working = true
    shifts = (client.table("shifts").select("*")
              .eq("facility_id", facility_id)
              .eq("roster_version_id", version["id"]).eq("date", str(on_date))
              .eq("is_working", True).execute().data)
    if not shifts:
        return None
    by_id = {s["id"]: s for s in shifts}
    # SQL: select * from shift_assignments
    #      where shift_id = any(:shift_ids) and staff_id = :staff_id
    assigns = assignments_for_shifts(client, by_id, facility_id=facility_id,
                                     staff_id=staff_id)
    for a in assigns:
        if a.get("status") != "cancelled":
            return by_id.get(a["shift_id"])
    return None


def open_incident(client, facility_id: str, *, staff_id: str, incident_type: str = "SL",
                  on_date: Date | None = None, reason: str | None = None,
                  shift_id: str | None = None, leave_request_id: str | None = None) -> dict:
    """Log an incident and immediately snapshot the ranked cover candidates."""
    _require_active_staff(client, facility_id, staff_id)
    on_date = on_date or Date.today()
    if not shift_id:
        shift = _find_shift_for(client, facility_id, staff_id, on_date)
        shift_id = shift["id"] if shift else None
    if shift_id:
        shifts = (
            client.table("shifts")
            .select("id,date")
            .eq("facility_id", facility_id)
            .eq("id", shift_id)
            .execute()
            .data
        )
        if not shifts:
            raise ValueError("incident shift does not belong to this facility")
        assignments = (
            client.table("shift_assignments")
            .select("id,status")
            .eq("facility_id", facility_id)
            .eq("shift_id", shift_id)
            .eq("staff_id", staff_id)
            .execute()
            .data
        )
        if not any(row.get("status") != "cancelled" for row in assignments):
            raise ValueError("staff member is not assigned to the incident shift")
        on_date = as_date(shifts[0]["date"])
    if leave_request_id:
        leave = (
            client.table("leave_requests")
            .select("id")
            .eq("facility_id", facility_id)
            .eq("id", leave_request_id)
            .eq("staff_id", staff_id)
            .execute()
            .data
        )
        if not leave:
            raise ValueError("leave request does not belong to this staff member")

    # SQL: insert into sl_incidents
    #        (facility_id, staff_id, shift_id, leave_request_id, incident_type,
    #         reason, replacement_status)
    #      values (:facility_id, :staff_id, :shift_id, :leave_request_id,
    #              :incident_type, :reason, 'open')
    #      returning *
    row = client.table("sl_incidents").insert({
        "facility_id": facility_id, "staff_id": staff_id, "shift_id": shift_id,
        "leave_request_id": leave_request_id, "incident_type": incident_type,
        "reason": reason, "replacement_status": "open",
    }).execute().data[0]

    refresh_candidates(client, facility_id, row["id"])
    notify.push(
        client, facility_id, event_type="cover_request",
        title=f"{incident_type} reported - cover required",
        body=f'{iso(on_date)}' + (f' · {reason}' if reason else ""),
        related_type="sl_incident", related_id=row["id"],
    )
    return row


# ── replacement candidates ───────────────────────────────────────────────────
def _rest_conflict(candidate_shifts: list[dict], vacancy: dict, min_rest_min: int) -> str | None:
    """Nearest-neighbour rest check against the candidate's other rostered shifts."""
    v_date = as_date(vacancy["date"])
    v_start = to_min(vacancy.get("start_time")) or 0
    v_dur = shift_minutes(vacancy)
    v_from = v_date.toordinal() * 1440 + v_start
    v_to = v_from + v_dur

    for sh in candidate_shifts:
        if not sh.get("is_working"):
            continue
        d = as_date(sh["date"])
        if abs((d - v_date).days) > 1:
            continue
        s_from = d.toordinal() * 1440 + (to_min(sh.get("start_time")) or 0)
        s_to = s_from + shift_minutes(sh)
        if s_from < v_to and v_from < s_to:
            return f'already rostered {sh["shift_type"]} on {iso(sh["date"])}'
        gap = s_from - v_to if s_from >= v_to else v_from - s_to
        if gap < min_rest_min:
            return (f'only {gap // 60}h rest around {sh["shift_type"]} on '
                    f'{iso(sh["date"])} (needs {min_rest_min // 60}h)')
    return None


def build_candidates(client, facility_id: str, incident: dict) -> list[dict]:
    """Rank every other active staff member for the vacant shift. Never filters a
    person out silently - blocked candidates come back with `blocked_reasons`."""
    shift_id = incident.get("shift_id")
    vacancy = None
    if shift_id:
        # SQL: select * from shifts where id = :shift_id
        rows = (
            client.table("shifts")
            .select("*")
            .eq("facility_id", facility_id)
            .eq("id", shift_id)
            .execute()
            .data
        )
        vacancy = rows[0] if rows else None
    if not vacancy:
        return []

    v_date = as_date(vacancy["date"])
    period, version_id = _shift_roster_context(
        client,
        facility_id,
        vacancy,
    )
    periods = _periods(client, facility_id)
    policy = _night_policy(client, facility_id, period)
    night_type = str(vacancy.get("shift_type") or "").upper()
    is_night = night_type in policy.night_types
    recovery_targets, recovery_setup_issues = _recovery_targets(
        client,
        facility_id,
        vacancy,
        period,
        version_id,
        policy,
        periods,
    )
    recovery_assignments = _target_assignments(
        client,
        facility_id,
        recovery_targets,
    )
    due_period = _next_period(periods, period)

    # SQL: select s.*, jsonb_build_object('name', u.name) as unit
    #      from staff s
    #      left join facility_units u on u.id = s.primary_unit_id
    #      where s.facility_id = :facility_id and s.status = 'active'
    staff_rows = (client.table("staff").select("*, unit:facility_units(name)")
                  .eq("facility_id", facility_id).eq("status", "active").execute().data)
    # SQL: select * from staff_contracts where facility_id = :facility_id
    # (keyed by staff_id in Python - last row per staff wins, no effective-date filter)
    contracts = {c["staff_id"]: c for c in (
        client.table("staff_contracts").select("*").eq("facility_id", facility_id).execute().data)}

    # everything rostered in the operative version, so we can test conflicts + load
    shifts_by_staff: dict[str, list[dict]] = {}
    scheduled_min: dict[str, int] = {}
    worked_types: dict[str, set[str]] = {}
    if version_id:
        # SQL: select * from shifts where roster_version_id = :version_id
        shifts = (client.table("shifts").select("*")
                  .eq("facility_id", facility_id)
                  .eq("roster_version_id", version_id).execute().data)
        by_id = {s["id"]: s for s in shifts}
        assigns = []
        if by_id:
            # SQL: select shift_id, staff_id, status from shift_assignments
            #      where shift_id = any(:shift_ids)
            assigns = assignments_for_shifts(
                client, by_id, select="shift_id,staff_id,status",
                facility_id=facility_id)
        for a in assigns:
            sid, sh = a.get("staff_id"), by_id.get(a["shift_id"])
            if not sid or not sh or a.get("status") == "cancelled":
                continue
            shifts_by_staff.setdefault(sid, []).append(sh)
            if sh.get("is_working"):
                scheduled_min[sid] = scheduled_min.get(sid, 0) + shift_minutes(sh)
                worked_types.setdefault(sid, set()).add(sh["shift_type"])

    from .leave import approved_leave_dates
    on_leave = approved_leave_dates(
        client,
        facility_id,
        v_date,
        v_date + timedelta(days=2),
    )

    # SQL: select staff_id, debt_type, due_period_id from future_debt_ledger
    #      where facility_id = :facility_id and status = 'open'
    # (counted per staff in Python; in SQL this would be a
    #  `group by staff_id` with `count(*)`)
    open_debt: dict[str, int] = {}
    cooldown_staff: set[str] = set()
    for d in (client.table("future_debt_ledger")
              .select("staff_id,debt_type,due_period_id")
              .eq("facility_id", facility_id).eq("status", "open").execute().data):
        open_debt[d["staff_id"]] = open_debt.get(d["staff_id"], 0) + 1
        if (
            d.get("debt_type") == "NIGHT_COOLDOWN"
            and (not d.get("due_period_id") or d.get("due_period_id") == (period or {}).get("id"))
        ):
            cooldown_staff.add(d["staff_id"])

    period_days = 28
    if period:
        period_days = (as_date(period["period_end"]) - as_date(period["period_start"])).days + 1
    v_minutes = shift_minutes(vacancy)
    required_rank = vacancy.get("required_rank")

    out: list[dict] = []
    for st in staff_rows:
        if st["id"] == incident["staff_id"]:
            continue
        blocked: list[str] = []
        reasons: list[str] = []
        contract = contracts.get(st["id"]) or {}
        mine = shifts_by_staff.get(st["id"], [])

        if required_rank and not can_cover_rank(st["rank"], required_rank):
            blocked.append(f'{st["rank"]} cannot cover a {required_rank} slot')
        if required_rank in AUDIT_RANKS and not st.get("is_audited_for_medication"):
            blocked.append("not audited for medication duty")
        if (
            is_night
            and str(st.get("rank") or "").upper() in policy.cooldown_ranks
            and st["id"] in cooldown_staff
        ):
            blocked.append("mandatory next-period nurse night cooldown")
        if (st["id"], v_date.isoformat()) in on_leave:
            blocked.append("on approved leave that day")
        if due_period is None:
            blocked.append(
                "next roster period is required for bounded compensation debt"
            )
        if (
            is_night
            and st.get("employment_type") in policy.chain_employment_types
        ):
            blocked.extend(_recovery_issues(
                st,
                recovery_targets,
                recovery_setup_issues,
                recovery_assignments,
                on_leave,
            ))

        same_day = [s for s in mine if iso(s["date"]) == v_date.isoformat()]
        if any(s["shift_type"] in LEAVE_CODES for s in same_day):
            blocked.append("already on leave in the roster")
        conflict = _rest_conflict(mine, vacancy, int(contract.get("min_rest_minutes") or 720))
        if conflict:
            blocked.append(conflict)

        weekly = float(contract.get("max_weekly_hours") or contract.get("weekly_hours")
                       or st.get("contracted_hours") or 44)
        cap_min = round(weekly * (period_days / 7) * 60)
        booked = scheduled_min.get(st["id"], 0)
        if cap_min and booked + v_minutes > cap_min:
            blocked.append(f'would exceed max hours ({round((booked + v_minutes) / 60)}h '
                           f'> {round(cap_min / 60)}h)')

        score = 50
        free_today = not any(s.get("is_working") for s in same_day)
        if free_today:
            score += 25
            reasons.append("free on the day")
        if st.get("primary_unit_id") and st["primary_unit_id"] == vacancy.get("unit_id"):
            score += 10
            reasons.append("familiar with the unit")
        headroom = 1 - (booked / cap_min) if cap_min else 0
        score += round(max(0.0, min(1.0, headroom)) * 10)
        if headroom > 0.15:
            reasons.append(f'{round(headroom * 100)}% hours headroom')
        debts = open_debt.get(st["id"], 0)
        score += max(0, 10 - debts * 3)
        if debts == 0:
            reasons.append("no outstanding TOIL/CL debt")
        if vacancy["shift_type"] in worked_types.get(st["id"], set()):
            score += 5
            reasons.append(f'has worked {vacancy["shift_type"]} this period')
        if st["rank"] == required_rank:
            score += 5
            reasons.append("exact rank match")

        out.append({
            **staff_brief(st),
            "candidate_staff_id": st["id"],
            "score": min(100, score) if not blocked else max(0, min(100, score) - 40),
            "compliance_ok": not blocked,
            "blocked_reasons": blocked,
            "reasons": reasons,
            "future_debt": {"open_entries": debts},
            "employment_type": st.get("employment_type"),
        })

    out.sort(key=lambda c: (c["compliance_ok"], c["score"]), reverse=True)
    for i, c in enumerate(out):
        c["rank_order"] = i + 1
    return out


def _persist_candidate_snapshot(
    client,
    facility_id: str,
    incident_id: str,
    ranked: list[dict],
) -> None:
    """Replace one incident's explainable candidate snapshot as a unit."""
    # Delete-then-insert rather than upsert: the ranking is a whole snapshot, and a
    # candidate who dropped out must not survive as a stale row.
    #
    # SQL: delete from replacement_candidates
    #      where facility_id = :facility_id and incident_id = :incident_id
    (client.table("replacement_candidates").delete()
     .eq("facility_id", facility_id).eq("incident_id", incident_id).execute())
    if ranked:
        # SQL: insert into replacement_candidates
        #        (facility_id, incident_id, candidate_staff_id, score, rank_order,
        #         compliance_ok, blocked_reasons, reasons, future_debt_json)
        #      values (...), (...), ...      -- one tuple per ranked candidate
        #      returning *
        client.table("replacement_candidates").insert([{
            "facility_id": facility_id, "incident_id": incident_id,
            "candidate_staff_id": c["candidate_staff_id"], "score": c["score"],
            "rank_order": c["rank_order"], "compliance_ok": c["compliance_ok"],
            "blocked_reasons": c["blocked_reasons"], "reasons": c["reasons"],
            "future_debt_json": c["future_debt"],
        } for c in ranked]).execute()


def refresh_candidates(client, facility_id: str, incident_id: str) -> list[dict]:
    """Recompute and persist the candidate snapshot (spec: the ranking the manager saw)."""
    # SQL: select * from sl_incidents
    #      where facility_id = :facility_id and id = :incident_id
    rows = (client.table("sl_incidents").select("*")
            .eq("facility_id", facility_id).eq("id", incident_id).execute().data)
    if not rows:
        raise ValueError("incident not found")
    ranked = build_candidates(client, facility_id, rows[0])
    _persist_candidate_snapshot(client, facility_id, incident_id, ranked)
    return ranked


def list_candidates(client, facility_id: str, incident_id: str, *,
                    compliance_checked: bool = True, limit: int = 5) -> list[dict]:
    # SQL: select * from replacement_candidates
    #      where facility_id = :facility_id and incident_id = :incident_id
    #      order by rank_order
    # `compliance_checked` and `limit` are applied in Python below, after the staff
    # names are joined on, so the caller always sees a contiguous ranking.
    rows = (client.table("replacement_candidates").select("*")
            .eq("facility_id", facility_id).eq("incident_id", incident_id)
            .order("rank_order").execute().data)
    if not rows:
        rows = []
        for c in refresh_candidates(client, facility_id, incident_id):
            rows.append({
                "candidate_staff_id": c["candidate_staff_id"], "score": c["score"],
                "rank_order": c["rank_order"], "compliance_ok": c["compliance_ok"],
                "blocked_reasons": c["blocked_reasons"], "reasons": c["reasons"],
                "future_debt_json": c["future_debt"],
            })
    staff = staff_by_id(client, facility_id)
    out = []
    for r in rows:
        if compliance_checked and not r.get("compliance_ok"):
            continue
        out.append({
            **staff_brief(staff.get(r["candidate_staff_id"])),
            "candidate_staff_id": r["candidate_staff_id"],
            "score": r["score"], "rank_order": r["rank_order"],
            "compliance_ok": bool(r.get("compliance_ok")),
            "blocked_reasons": r.get("blocked_reasons") or [],
            "reasons": r.get("reasons") or [],
            "future_debt": r.get("future_debt_json") or {},
        })
    return out[:limit]


# ── resolve (close the loop) ─────────────────────────────────────────────────
def _require_profile(client, facility_id: str, profile_id: str | None) -> None:
    if not profile_id:
        return
    rows = (
        client.table("users_profile")
        .select("id")
        .eq("facility_id", facility_id)
        .eq("id", profile_id)
        .execute()
        .data
    )
    if not rows:
        raise ValueError("resolving profile does not belong to this facility")


def _require_active_staff(
    client,
    facility_id: str,
    staff_id: str,
) -> dict:
    rows = (
        client.table("staff")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("id", staff_id)
        .eq("status", "active")
        .execute()
        .data
    )
    if not rows:
        raise ValueError("staff member does not belong to this facility")
    return rows[0]


def _resolve_recovery_plan(
    client,
    facility_id: str,
    shift: dict,
    staff: dict,
) -> tuple[dict, dict, _NightPolicy, list[_RecoveryTarget]]:
    period, version_id = _shift_roster_context(
        client,
        facility_id,
        shift,
    )
    periods = _periods(client, facility_id)
    due_period = _next_period(periods, period)
    if not due_period:
        raise ValueError(
            "create the next roster period before resolving cover; "
            "compensation debt must have a bounded due period"
        )

    policy = _night_policy(client, facility_id, period)
    is_night = (
        str(shift.get("shift_type") or "").upper() in policy.night_types
    )
    if (
        is_night
        and str(staff.get("rank") or "").upper() in policy.cooldown_ranks
    ):
        cooldown = (
            client.table("future_debt_ledger")
            .select("*")
            .eq("facility_id", facility_id)
            .eq("staff_id", staff["id"])
            .eq("debt_type", "NIGHT_COOLDOWN")
            .eq("status", "open")
            .execute()
            .data
        )
        active = [
            row for row in cooldown
            if (
                not row.get("due_period_id")
                or row.get("due_period_id") == period["id"]
            )
        ]
        if active:
            raise ValueError(
                "replacement is in the mandatory next-period nurse night cooldown"
            )

    targets: list[_RecoveryTarget] = []
    if (
        is_night
        and staff.get("employment_type") in policy.chain_employment_types
    ):
        targets, setup_issues = _recovery_targets(
            client,
            facility_id,
            shift,
            period,
            version_id,
            policy,
            periods,
        )
        assigned = _target_assignments(client, facility_id, targets)
        from .leave import approved_leave_dates
        shift_day = as_date(shift["date"])
        on_leave = approved_leave_dates(
            client,
            facility_id,
            shift_day + timedelta(days=1),
            shift_day + timedelta(days=2),
        )
        issues = _recovery_issues(
            staff,
            targets,
            setup_issues,
            assigned,
            on_leave,
        )
        if issues:
            raise ValueError(
                "replacement cannot satisfy mandatory night recovery: "
                + "; ".join(issues)
            )
    return period, due_period, policy, targets


def _materialize_night_recovery(
    client,
    facility_id: str,
    shift: dict,
    staff: dict,
    targets: list[_RecoveryTarget],
    *,
    incident_id: str | None = None,
) -> list[dict]:
    """Persist configured sleeping-day/day-off cells after emergency night cover."""
    assigned = _target_assignments(client, facility_id, targets)
    created: list[dict] = []
    for target in targets:
        existing = assigned.get((staff["id"], target.day), [])
        conflicting = [
            row for row in existing
            if str(row.get("shift_type") or "").upper() != target.code
        ]
        if conflicting:
            raise ValueError(
                f"mandatory {target.code} recovery on {target.day} "
                "became unavailable"
            )
        if existing:
            continue
        definition = target.definition
        recovery_shift = (
            client.table("shifts")
            .insert({
                "facility_id": facility_id,
                "roster_version_id": target.version_id,
                "date": target.day.isoformat(),
                "shift_type": target.code,
                "start_time": definition.get("start_time"),
                "end_time": definition.get("end_time"),
                "cross_midnight": bool(definition.get("cross_midnight")),
                "unit_id": shift.get("unit_id"),
                "required_rank": None,
                "required_count": 1,
                "is_working": False,
                "segments": definition.get("segments"),
                "paid_minutes": int(definition.get("paid_minutes") or 0),
            })
            .execute()
            .data[0]
        )
        assignment_payload = {
            "facility_id": facility_id,
            "shift_id": recovery_shift["id"],
            "staff_id": staff["id"],
            "role": staff.get("rank"),
            "status": "assigned",
            "is_agency": False,
        }
        if incident_id:
            assignment_payload.update({
                "source_incident_id": incident_id,
                "incident_assignment_kind": "recovery",
            })
        assignment = (
            client.table("shift_assignments")
            .insert(assignment_payload)
            .execute()
            .data[0]
        )
        created.append({
            "date": target.day.isoformat(),
            "shift_type": target.code,
            "shift_id": recovery_shift["id"],
            "shift_assignment_id": assignment["id"],
        })
    return created


def _record_cover_debts(
    client,
    facility_id: str,
    incident_id: str,
    shift: dict,
    staff: dict,
    due_period: dict,
    policy: _NightPolicy,
    debt_hours: float,
) -> list[dict]:
    shift_type = str(shift.get("shift_type") or "").upper()
    due_details = {
        "due_period_start": iso(due_period["period_start"]),
        "due_period_end": iso(due_period["period_end"]),
        "shift_type": shift_type,
    }

    def insert(
        debt_type: str,
        quantity: float,
        unit: str,
        note: str,
        details: dict,
    ) -> dict:
        return (
            client.table("future_debt_ledger")
            .insert({
                "facility_id": facility_id,
                "staff_id": staff["id"],
                "debt_type": debt_type,
                "quantity": quantity,
                "unit": unit,
                "due_period_id": due_period["id"],
                "source_incident_id": incident_id,
                "source_shift_id": shift["id"],
                "status": "open",
                "note": note,
                "details_json": {**due_details, **details},
                "resolution_key": f"{incident_id}:{debt_type}",
            })
            .execute()
            .data[0]
        )

    debts = [insert(
        "TOIL",
        debt_hours,
        "hours",
        "emergency cover - compensate next cycle",
        {"policy": "emergency_cover_toil"},
    )]
    if shift_type not in policy.night_types:
        return debts

    debts.append(insert(
        "OT",
        1,
        "hours",
        f"standalone {shift_type} cover - mandatory +1 hour overtime",
        {"policy": "phase5_long_night"},
    ))
    if str(staff.get("rank") or "").upper() in policy.cooldown_ranks:
        debts.append(insert(
            "NIGHT_COOLDOWN",
            1,
            "period",
            "nurse night cover - block night duty next period",
            {
                "rank": str(staff.get("rank") or "").upper(),
                "policy": "phase5_nurse_cooldown",
            },
        ))
    return debts


def resolve_incident(client, facility_id: str, incident_id: str, *,
                     replacement_staff_id: str, profile_id: str | None = None,
                     auto: bool = True, note: str | None = None) -> dict:
    """Re-roster the vacant shift onto the replacement, record the debt it creates,
    and stamp the response time."""
    # SQL: select * from sl_incidents
    #      where facility_id = :facility_id and id = :incident_id
    rows = (client.table("sl_incidents").select("*")
            .eq("facility_id", facility_id).eq("id", incident_id).execute().data)
    if not rows:
        raise ValueError("incident not found")
    incident = rows[0]
    if incident["replacement_status"] == "resolved":
        raise ValueError("incident is already resolved")

    _require_profile(client, facility_id, profile_id)
    candidates = {
        candidate["candidate_staff_id"]: candidate
        for candidate in build_candidates(client, facility_id, incident)
    }
    chosen = candidates.get(replacement_staff_id)
    if not chosen:
        raise ValueError("replacement must be one of the current candidate IDs")
    if not chosen["compliance_ok"]:
        raise ValueError(
            "replacement fails the compliance check: "
            + "; ".join(chosen["blocked_reasons"])
        )
    replacement = _require_active_staff(
        client,
        facility_id,
        replacement_staff_id,
    )

    if incident.get("facility_id") not in (None, facility_id):
        raise ValueError("incident does not belong to this facility")
    shift_id = incident.get("shift_id")
    if not shift_id:
        raise ValueError("incident has no roster shift to cover")
    shift_rows = (
        client.table("shifts")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("id", shift_id)
        .execute()
        .data
    )
    if not shift_rows:
        raise ValueError("incident shift does not belong to this facility")
    shift = shift_rows[0]
    _, due_period, policy, recovery_targets = _resolve_recovery_plan(
        client,
        facility_id,
        shift,
        replacement,
    )
    debt_hours = round(shift_minutes(shift) / 60, 2)
    absent_assignments = (
        client.table("shift_assignments")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("shift_id", shift_id)
        .eq("staff_id", incident["staff_id"])
        .execute()
        .data
    )
    if not any(
        row.get("status") != "cancelled" for row in absent_assignments
    ):
        raise ValueError("absent staff no longer owns the incident shift")

    if shift_id:
        # Keep the absent person's row for audit and add cover before cancelling
        # it, so a failed intermediate write cannot create an uncovered shift.
        # SQL: insert into shift_assignments
        #        (facility_id, shift_id, staff_id, role, status, is_agency)
        #      values (:facility_id, :shift_id, :replacement_staff_id,
        #              :required_rank, 'assigned', false)
        #      returning *
        new_assignment = client.table("shift_assignments").insert({
            "facility_id": facility_id, "shift_id": shift_id,
            "staff_id": replacement_staff_id, "role": shift.get("required_rank"),
            "status": "assigned", "is_agency": False,
        }).execute().data[0]
        # PostgREST exposes these as separate statements. All reads and policy
        # checks have completed before this deliberately coverage-safe sequence.
        #
        # SQL: insert into manual_override_log
        #        (facility_id, roster_version_id, shift_assignment_id, action,
        #         before_json, after_json, changed_by, reason)
        #      values (:facility_id, :roster_version_id, :new_assignment_id, 'assign',
        #              :before_json::jsonb, :after_json::jsonb, :profile_id, :reason)
        #      returning *
        client.table("manual_override_log").insert({
            "facility_id": facility_id,
            "roster_version_id": shift.get("roster_version_id"),
            "shift_assignment_id": new_assignment["id"], "action": "assign",
            "before_json": {"staff_id": incident["staff_id"]},
            "after_json": {"staff_id": replacement_staff_id},
            "changed_by": profile_id,
            "reason": f'emergency cover for {incident["incident_type"]} incident',
        }).execute()
        recovery = _materialize_night_recovery(
            client,
            facility_id,
            shift,
            replacement,
            recovery_targets,
        )
        debts = _record_cover_debts(
            client,
            facility_id,
            incident_id,
            shift,
            replacement,
            due_period,
            policy,
            debt_hours,
        )
        # Cancel last: if a preceding PostgREST write fails, the original staff
        # member remains assigned and the roster never acquires an uncovered gap.
        (
            client.table("shift_assignments")
            .update({"status": "cancelled"})
            .eq("facility_id", facility_id)
            .eq("shift_id", shift_id)
            .eq("staff_id", incident["staff_id"])
            .execute()
        )

    reported = datetime.fromisoformat(str(incident["reported_at"]).replace("Z", "+00:00"))
    minutes = max(0, round((datetime.now(timezone.utc) - reported).total_seconds() / 60))

    # SQL: update sl_incidents
    #      set replacement_status = 'resolved', replacement_staff_id = :replacement_staff_id,
    #          resolved_at = now(), resolved_by = :profile_id,
    #          resolution_minutes = :minutes, auto_resolved = :auto, notes = :note
    #      where facility_id = :facility_id and id = :incident_id
    #      returning *
    updated = (client.table("sl_incidents").update({
        "replacement_status": "resolved",
        "replacement_staff_id": replacement_staff_id,
        "resolved_at": now_iso(), "resolved_by": profile_id,
        "resolution_minutes": minutes, "auto_resolved": auto, "notes": note,
    }).eq("facility_id", facility_id).eq("id", incident_id).execute().data[0])

    notify.push(client, facility_id, staff_id=replacement_staff_id,
                event_type="cover_assigned", title="You have been assigned emergency cover",
                body=f'+{debt_hours}h TOIL recorded' if debt_hours else None,
                related_type="sl_incident", related_id=incident_id)

    return {
        "incident": updated,
        "future_debt": debts[0] if debts else None,
        "future_debts": debts,
        "night_recovery": recovery,
        "resolution_minutes": minutes,
    }


def list_future_debt(client, facility_id: str, *, staff_id: str | None = None,
                     status: str = "open") -> list[dict]:
    # SQL: select * from future_debt_ledger
    #      where facility_id = :facility_id
    #        [and status = :status]        -- unless status is passed as ""
    #        [and staff_id = :staff_id]    -- when staff_id is given
    #      order by created_at desc
    q = client.table("future_debt_ledger").select("*").eq("facility_id", facility_id)
    if status:
        q = q.eq("status", status)
    if staff_id:
        q = q.eq("staff_id", staff_id)
    rows = q.order("created_at", desc=True).execute().data
    staff = staff_by_id(client, facility_id)
    return [{
        **staff_brief(staff.get(r["staff_id"])),
        "id": r["id"], "debt_type": r["debt_type"], "quantity": float(r["quantity"]),
        "unit": r["unit"], "status": r["status"], "note": r.get("note"),
        "created_at": r.get("created_at"),
    } for r in rows]


# ── derived alert feed ───────────────────────────────────────────────────────
def active_alerts(client, facility_id: str) -> list[dict]:
    """The Alert centre's live list. Every entry is derived from real rows:
    open incidents, expiring certificates, hour overruns and today's ratio gaps."""
    today = Date.today()
    alerts: list[dict] = []
    staff = staff_by_id(client, facility_id)

    for inc in list_incidents(client, facility_id, status="open", limit=20):
        alerts.append({
            "id": f'incident:{inc["id"]}',
            "kind": "cover", "urgent": True,
            "title": f'{inc["incident_type"]} - cover required',
            "detail": (f'{inc["name_en"] or inc["name"]} ({inc["rank"]}) · '
                       f'{inc["shift_type"] or "shift"} {inc["shift_window"] or ""}').strip(),
            "unit_name": inc["unit_name"], "date": inc["date"],
            "incident_id": inc["id"],
        })

    # SQL: select staff_id, cert_type, expiry_date from staff_certificates
    #      where facility_id = :facility_id
    #        and expiry_date is not null
    #      order by expiry_date
    # The CERT_WARN_DAYS cutoff is applied in the Python loop, not as
    # `and expiry_date <= current_date + 90`.
    certs = (client.table("staff_certificates").select("staff_id,cert_type,expiry_date")
             .eq("facility_id", facility_id).not_.is_("expiry_date", "null")
             .order("expiry_date").execute().data)
    for c in certs:
        days = (as_date(c["expiry_date"]) - today).days
        if days > CERT_WARN_DAYS:
            continue
        st = staff.get(c["staff_id"]) or {}
        alerts.append({
            "id": f'cert:{c["staff_id"]}:{c["cert_type"]}',
            "kind": "certificate", "urgent": days <= 7,
            "title": f'{c["cert_type"]} {"expired" if days < 0 else "expiring"}',
            "detail": (f'{st.get("name_en") or st.get("name")} · '
                       f'{"expired " + str(-days) + "d ago" if days < 0 else str(days) + " days left"}'),
            "unit_name": (st.get("unit") or {}).get("name"),
            "date": iso(c["expiry_date"]),
        })

    period = resolve_period(client, facility_id, None)
    if period:
        version = operative_version(client, facility_id, period["id"])
        if version:
            for r in compute_ratios(client, facility_id, today,
                                    roster_version_id=version["id"]):
                if r.passes:
                    continue
                alerts.append({
                    "id": f'ratio:{r.label}',
                    "kind": "ratio", "urgent": True,
                    "title": f'Staffing ratio below minimum - {r.label}',
                    "detail": f'{r.actual} on duty, {r.required} required '
                              f'for {r.residents} residents',
                    "unit_name": None, "date": today.isoformat(),
                })

    for over in _hour_overruns(client, facility_id, period):
        alerts.append(over)

    alerts.sort(key=lambda a: (not a["urgent"], a.get("date") or ""))
    return alerts


def _hour_overruns(client, facility_id: str, period: dict | None) -> list[dict]:
    """Staff rostered beyond their contracted maximum for the period (OT alert)."""
    if not period:
        return []
    version = operative_version(client, facility_id, period["id"])
    if not version:
        return []
    # SQL: select * from shifts
    #      where roster_version_id = :version_id and is_working = true
    shifts = (client.table("shifts").select("*")
              .eq("roster_version_id", version["id"]).eq("is_working", True).execute().data)
    if not shifts:
        return []
    by_id = {s["id"]: s for s in shifts}
    # SQL: select shift_id, staff_id, status from shift_assignments
    #      where shift_id = any(:shift_ids)
    assigns = assignments_for_shifts(client, by_id,
                                     select="shift_id,staff_id,status")
    booked: dict[str, int] = {}
    for a in assigns:
        if not a.get("staff_id") or a.get("status") == "cancelled":
            continue
        booked[a["staff_id"]] = booked.get(a["staff_id"], 0) + shift_minutes(by_id[a["shift_id"]])

    # SQL: select * from staff_contracts where facility_id = :facility_id
    contracts = {c["staff_id"]: c for c in (
        client.table("staff_contracts").select("*").eq("facility_id", facility_id).execute().data)}
    staff = staff_by_id(client, facility_id)
    days = (as_date(period["period_end"]) - as_date(period["period_start"])).days + 1

    out = []
    for sid, minutes in booked.items():
        st = staff.get(sid) or {}
        c = contracts.get(sid) or {}
        weekly = c.get("max_weekly_hours") or c.get("weekly_hours") or st.get("contracted_hours")
        if not weekly:
            continue
        cap = round(float(weekly) * (days / 7) * 60)
        if minutes <= cap:
            continue
        out.append({
            "id": f"hours:{sid}",
            "kind": "hours", "urgent": True,
            "title": f'Hours over contract - {st.get("name_en") or st.get("name")}',
            "detail": f'{round(minutes / 60)}h rostered vs {round(cap / 60)}h maximum '
                      f'this period',
            "unit_name": (st.get("unit") or {}).get("name"),
            "date": iso(period["period_end"]),
        })
    return out


__all__ = [
    "active_alerts", "build_candidates", "get_incident", "list_candidates",
    "list_future_debt", "list_incidents", "open_incident", "refresh_candidates",
    "resolve_incident", "stats",
]
