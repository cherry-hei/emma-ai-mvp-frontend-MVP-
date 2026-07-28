"""Derived analytics: the Staff Portfolio "AI Analysis" tab and the facility
highlight strip.

There is no model here and no fabricated score. A staff member's *explicit*
competence is what their certificates attest; their *implicit* competence is what
their rostered task history and shift mix demonstrate. Gaps are the delta between
the two plus the task codes their rank is expected to cover but never has.
"""
from __future__ import annotations

from datetime import date as Date

from ._common import as_date, iso, operative_version, resolve_period, shift_minutes

CERT_WARN_DAYS = 90
NIGHT_CODES = {"N", "AN", "7P"}


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == " ").strip()


def _cert_status(expiry: str | None, today: Date) -> tuple[str, int | None]:
    if not expiry:
        return "valid", None
    days = (as_date(expiry) - today).days
    if days < 0:
        return "expired", days
    if days <= CERT_WARN_DAYS:
        return "expiring", days
    return "valid", days


def _shift_history(client, facility_id: str, staff_id: str) -> list[dict]:
    """Working cells from the manual/published rosters only — never A/B/C proposals."""
    # SQL: select a.id, a.tasks, a.status,
    #             jsonb_build_object(
    #               'date', sh.date, 'shift_type', sh.shift_type,
    #               'start_time', sh.start_time, 'end_time', sh.end_time,
    #               'is_working', sh.is_working, 'unit_id', sh.unit_id,
    #               'version', jsonb_build_object('version_type', v.version_type,
    #                                             'status', v.status)) as shift
    #      from shift_assignments a
    #      left join shifts sh on sh.id = a.shift_id
    #      left join roster_versions v on v.id = sh.roster_version_id
    #      where a.facility_id = :facility_id and a.staff_id = :staff_id
    # The cancelled / non-working / non-operative-version filters run in Python below.
    rows = (client.table("shift_assignments")
            .select("id,tasks,status, shift:shifts(date,shift_type,start_time,end_time,"
                    "is_working,unit_id, version:roster_versions(version_type,status))")
            .eq("facility_id", facility_id).eq("staff_id", staff_id).execute().data)
    out = []
    for a in rows:
        sh = a.get("shift") or {}
        ver = sh.get("version") or {}
        if a.get("status") == "cancelled" or not sh.get("is_working"):
            continue
        if ver.get("version_type") != "manual" and ver.get("status") != "published":
            continue
        out.append({
            "date": iso(sh.get("date")), "shift_type": sh.get("shift_type"),
            "unit_id": sh.get("unit_id"), "tasks": list(a.get("tasks") or []),
            "minutes": shift_minutes(sh),
        })
    out.sort(key=lambda h: h["date"], reverse=True)
    return out


def staff_analysis(client, facility_id: str, staff_id: str) -> dict:
    today = Date.today()
    # SQL: select s.*, jsonb_build_object('name', u.name) as unit
    #      from staff s
    #      left join facility_units u on u.id = s.primary_unit_id
    #      where s.facility_id = :facility_id and s.id = :staff_id
    staff_rows = (client.table("staff").select("*, unit:facility_units(name)")
                  .eq("facility_id", facility_id).eq("id", staff_id).execute().data)
    if not staff_rows:
        raise ValueError("staff member not found")
    st = staff_rows[0]

    # SQL: select cert_type, expiry_date from staff_certificates
    #      where facility_id = :facility_id and staff_id = :staff_id
    #      order by expiry_date
    certs = (client.table("staff_certificates").select("cert_type,expiry_date")
             .eq("facility_id", facility_id).eq("staff_id", staff_id)
             .order("expiry_date").execute().data)
    history = _shift_history(client, facility_id, staff_id)

    # ── implicit signal: what the roster shows them actually doing ──
    task_counts: dict[str, int] = {}
    for h in history:
        for label in h["tasks"]:
            task_counts[label] = task_counts.get(label, 0) + 1
    peak = max(task_counts.values(), default=0)

    explicit = []
    for c in certs:
        status, days = _cert_status(c.get("expiry_date"), today)
        explicit.append({
            "skill": c["cert_type"], "expiry_date": c.get("expiry_date"),
            "days_left": days, "status": status,
            "score": {"valid": 100, "expiring": 70, "expired": 30}[status],
        })
    cert_index = {_norm(e["skill"]): e for e in explicit}

    implicit = [{
        "skill": label, "occurrences": n,
        "score": round(n / peak * 100) if peak else 0,
    } for label, n in sorted(task_counts.items(), key=lambda kv: -kv[1])]

    # ── combined bars: every dimension either side of the evidence line ──
    dimensions = {*(e["skill"] for e in explicit), *task_counts}
    bars = []
    for skill in dimensions:
        cert = cert_index.get(_norm(skill))
        occurrences = task_counts.get(skill, 0)
        bars.append({
            "skill": skill,
            "explicit": cert["score"] if cert else 0,
            "implicit": round(occurrences / peak * 100) if peak else 0,
            "occurrences": occurrences,
            "certified": bool(cert),
        })
    bars.sort(key=lambda b: -(b["explicit"] + b["implicit"]))

    # ── gaps: rank-expected task codes never performed + certificate decay ──
    # SQL: select task_code, task_name, required_rank, requires_audit
    #      from task_definitions
    #      where (facility_id = :facility_id or facility_id is null)  -- null = template
    #        and active = true
    # (the rank match runs in Python so `required_rank is null` rows stay in scope)
    expected = (client.table("task_definitions").select("task_code,task_name,required_rank,requires_audit")
                .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
                .eq("active", True).execute().data)
    performed = {_norm(k) for k in task_counts}
    gaps = []
    for t in expected:
        if t.get("required_rank") and t["required_rank"] != st["rank"]:
            continue
        name = t.get("task_name") or t["task_code"]
        if _norm(name) in performed:
            continue
        if t.get("requires_audit") and not st.get("is_audited_for_medication"):
            gaps.append({"skill": name, "kind": "eligibility",
                         "detail": "requires medication audit, not yet certified"})
        else:
            gaps.append({"skill": name, "kind": "experience",
                         "detail": "expected for this rank but never rostered"})
    for e in explicit:
        if e["status"] == "expired":
            gaps.append({"skill": e["skill"], "kind": "certificate",
                         "detail": f'expired {abs(e["days_left"])} days ago'})
        elif e["status"] == "expiring":
            gaps.append({"skill": e["skill"], "kind": "certificate",
                         "detail": f'expires in {e["days_left"]} days'})

    training = [
        {"title": f'Renew {g["skill"]}', "reason": g["detail"], "priority": "high"}
        if g["kind"] == "certificate" else
        {"title": f'Shadow {g["skill"]}', "reason": g["detail"], "priority": "normal"}
        for g in gaps[:6]
    ]

    # ── notable events, all from committed rows ──
    # SQL: select i.id, i.incident_type, i.resolved_at, i.resolution_minutes,
    #             jsonb_build_object('date', sh.date, 'shift_type', sh.shift_type) as shift
    #      from sl_incidents i
    #      left join shifts sh on sh.id = i.shift_id
    #      where i.facility_id = :facility_id
    #        and i.replacement_staff_id = :staff_id
    #        and i.replacement_status = 'resolved'
    #      order by i.resolved_at desc
    #      limit 5
    covers = (client.table("sl_incidents")
              .select("id,incident_type,resolved_at,resolution_minutes, shift:shifts(date,shift_type)")
              .eq("facility_id", facility_id).eq("replacement_staff_id", staff_id)
              .eq("replacement_status", "resolved")
              .order("resolved_at", desc=True).limit(5).execute().data)
    events = [{
        "date": iso((c.get("shift") or {}).get("date") or c.get("resolved_at")),
        "title": f'Emergency cover — {(c.get("shift") or {}).get("shift_type") or "shift"}',
        "detail": f'{c["incident_type"]} resolved in {c.get("resolution_minutes") or "?"} min',
        "skill": "Crisis response",
    } for c in covers]

    nights = len([h for h in history if h["shift_type"] in NIGHT_CODES])
    if nights:
        events.append({
            "date": history[0]["date"] if history else today.isoformat(),
            "title": f"{nights} night shifts rostered",
            "detail": "sustained night-duty coverage",
            "skill": "Night-duty resilience",
        })
    units = {h["unit_id"] for h in history if h["unit_id"]}
    if len(units) > 1:
        events.append({
            "date": history[0]["date"] if history else today.isoformat(),
            "title": f"Worked across {len(units)} units",
            "detail": "cross-unit versatility",
            "skill": "Unit versatility",
        })

    minutes = sum(h["minutes"] for h in history)
    return {
        "staff": {
            "id": st["id"], "name": st.get("name"), "name_en": st.get("name_en"),
            "rank": st.get("rank"), "unit_name": (st.get("unit") or {}).get("name"),
            "is_mentor": bool(st.get("is_mentor")),
            "is_audited_for_medication": bool(st.get("is_audited_for_medication")),
        },
        "explicit_skills": explicit,
        "implicit_skills": implicit[:10],
        "skill_bars": bars[:6],
        "gaps": gaps[:6],
        "recommended_training": training,
        "events": events[:5],
        "activity": {
            "working_shifts": len(history),
            "hours": round(minutes / 60, 1),
            "night_shifts": nights,
            "distinct_units": len(units),
            "tasks_performed": sum(task_counts.values()),
            "emergency_covers": len(covers),
        },
        "evidence_note": ("Explicit = certificate-backed. Implicit = derived from "
                          "rostered task history and shift mix in this facility."),
    }


def facility_highlights(client, facility_id: str) -> list[dict]:
    """Three real, sourced statements for the Dashboard's Emma AI summary strip."""
    from . import incidents as incident_svc
    from . import kpi as kpi_svc
    from . import roi as roi_svc

    settings = roi_svc.get_settings(client, facility_id)
    stats = incident_svc.stats(client, facility_id)
    hours_saved = round(stats["total"] * float(settings["hours_saved_per_incident"]), 1)

    period = resolve_period(client, facility_id, None)
    ratio = kpi_svc.staffing_ratio_compliance(client, facility_id,
                                              period["id"] if period else None)
    fairness = kpi_svc.shift_fairness(client, facility_id, period["id"] if period else None)
    worst = max(fairness["by_shift_type"], key=lambda f: f["gini"], default=None) \
        if fairness["by_shift_type"] else None

    manual_baseline = 45   # ROI paper: manual cover handling takes ~45 min
    return [
        {
            "key": "cover",
            "value": stats["resolved"],
            "text_en": (f'{stats["resolved"]} of {stats["total"]} cover cases closed this '
                        f'month — about {hours_saved}h of manual coordination avoided'),
            "text_zh": (f'本月處理 {stats["resolved"]}/{stats["total"]} 宗補更，'
                        f'節省約 {hours_saved} 小時人手協調時間'),
        },
        {
            "key": "compliance",
            "value": ratio["pass_rate_pct"],
            "text_en": (f'SWD staffing ratio passing {ratio["pass_rate_pct"]}% of checks · '
                        f'{ratio["breach_minutes"]} breach minutes this period'),
            "text_zh": (f'SWD 人手比率合規率 {ratio["pass_rate_pct"]}%，'
                        f'本期違規 {ratio["breach_minutes"]} 分鐘'),
        },
        {
            "key": "response",
            "value": stats["avg_response_minutes"],
            "text_en": (f'Average cover response {stats["avg_response_minutes"]} min '
                        f'(manual baseline {manual_baseline} min)'
                        + (f' · highest shift-type Gini {worst["gini"]} on {worst["shift_type"]}'
                           if worst else "")),
            "text_zh": (f'平均補更響應時間 {stats["avg_response_minutes"]} 分鐘'
                        f'（人手需 {manual_baseline} 分鐘）'),
        },
    ]
