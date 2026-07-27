"""Staff-app self-service reads (spec 4.1).

Every function takes the caller's own staff_id — resolved from users_profile, not
from a request parameter — so a staff token can only ever reach its own roster,
tasks, leave and attendance. RLS enforces the same rule at the database.
"""
from __future__ import annotations

from datetime import date as Date, timedelta

from . import attendance as att
from . import tasks as task_svc
from ._common import (
    as_date, iso, operative_version, resolve_period, shift_minutes, staff_by_id,
)
from .compliance import compute_ratios


def resolve_staff_id(profile) -> str:
    staff_id = getattr(profile, "staff_id", None) or (
        profile.get("staff_id") if isinstance(profile, dict) else None)
    if not staff_id:
        raise ValueError("this account is not linked to a staff record")
    return staff_id


def _staff_row(client, facility_id: str, staff_id: str) -> dict:
    rows = (client.table("staff").select("*, unit:facility_units(name)")
            .eq("facility_id", facility_id).eq("id", staff_id).execute().data)
    if not rows:
        raise ValueError("staff record not found")
    return rows[0]


def _my_shifts(client, facility_id: str, staff_id: str,
               start: Date, end: Date) -> list[dict]:
    """Rostered cells for [start, end] from the operative version, newest first."""
    period = resolve_period(client, facility_id, None)
    if not period:
        return []
    version = operative_version(client, facility_id, period["id"])
    if not version:
        return []
    shifts = (client.table("shifts").select("*")
              .eq("roster_version_id", version["id"])
              .gte("date", str(start)).lte("date", str(end)).execute().data)
    if not shifts:
        return []
    by_id = {s["id"]: s for s in shifts}
    assigns = (client.table("shift_assignments").select("*")
               .in_("shift_id", list(by_id)).eq("staff_id", staff_id).execute().data)

    out = []
    for a in assigns:
        if a.get("status") == "cancelled":
            continue
        sh = by_id[a["shift_id"]]
        out.append({
            "assignment_id": a["id"], "shift_id": sh["id"], "date": iso(sh["date"]),
            "shift_type": sh["shift_type"], "is_working": bool(sh.get("is_working")),
            "start_time": (sh.get("start_time") or "")[:5] or None,
            "end_time": (sh.get("end_time") or "")[:5] or None,
            "minutes": shift_minutes(sh) if sh.get("is_working") else 0,
            "unit_id": sh.get("unit_id"),
            "tasks": list(a.get("tasks") or []),
        })
    out.sort(key=lambda c: c["date"])
    return out


def my_roster(client, facility_id: str, staff_id: str, *, days: int = 7,
              start: Date | None = None) -> dict:
    """A `days`-long window anchored on today, slid to stay inside the current
    roster period — near the end of a cycle, showing 28 days forward from today
    would return one rostered day and 27 blanks."""
    if start is None:
        start = Date.today()
        period = resolve_period(client, facility_id, None)
        if period:
            ps, pe = as_date(period["period_start"]), as_date(period["period_end"])
            latest_start = pe - timedelta(days=days - 1)
            start = min(max(start, ps), max(ps, latest_start))
    end = start + timedelta(days=days - 1)
    cells = _my_shifts(client, facility_id, staff_id, start, end)
    by_date = {c["date"]: c for c in cells}
    unit_names = {u["id"]: u["name"] for u in (
        client.table("facility_units").select("id,name")
        .eq("facility_id", facility_id).execute().data)}
    st = _staff_row(client, facility_id, staff_id)

    series = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        cell = by_date.get(d)
        series.append({
            "date": d,
            "shift_type": cell["shift_type"] if cell else None,
            "is_working": bool(cell and cell["is_working"]),
            "start_time": cell["start_time"] if cell else None,
            "end_time": cell["end_time"] if cell else None,
            "unit_name": unit_names.get(cell["unit_id"]) if cell else None,
            "tasks": cell["tasks"] if cell else [],
        })
    return {
        "staff_id": staff_id,
        "name": st.get("name"), "name_en": st.get("name_en"), "rank": st.get("rank"),
        "unit_name": (st.get("unit") or {}).get("name"),
        "start": start.isoformat(), "end": end.isoformat(),
        "days": series,
    }


def hours_progress(client, facility_id: str, staff_id: str) -> dict:
    """Rostered vs contracted hours for the current period (the staff-app ring)."""
    period = resolve_period(client, facility_id, None)
    if not period:
        return {"scheduled_hours": 0.0, "contracted_hours": 0.0, "pct": 0}
    ps, pe = as_date(period["period_start"]), as_date(period["period_end"])
    cells = _my_shifts(client, facility_id, staff_id, ps, pe)
    minutes = sum(c["minutes"] for c in cells)

    st = _staff_row(client, facility_id, staff_id)
    contracts = (client.table("staff_contracts").select("*")
                 .eq("facility_id", facility_id).eq("staff_id", staff_id)
                 .order("effective_from", desc=True).limit(1).execute().data)
    weekly = float((contracts[0] if contracts else {}).get("weekly_hours")
                   or st.get("contracted_hours") or 44)
    total = round(weekly * (((pe - ps).days + 1) / 7), 1)
    return {
        "period_start": ps.isoformat(), "period_end": pe.isoformat(),
        "scheduled_hours": round(minutes / 60, 1),
        "contracted_hours": total,
        "pct": round(minutes / 60 / total * 100) if total else 0,
    }


def summary(client, facility_id: str, staff_id: str) -> dict:
    """Everything the staff-app home screen renders, in one round trip."""
    today = Date.today()
    st = _staff_row(client, facility_id, staff_id)
    cells = _my_shifts(client, facility_id, staff_id, today, today)
    today_cell = cells[0] if cells else None
    my_tasks = task_svc.for_staff_date(client, facility_id, staff_id, today)

    ratio_headline = None
    period = resolve_period(client, facility_id, None)
    if period:
        version = operative_version(client, facility_id, period["id"])
        if version:
            checks = compute_ratios(client, facility_id, today,
                                    roster_version_id=version["id"])
            if checks:
                passing = sum(1 for c in checks if c.passes)
                worst = min(checks, key=lambda c: (c.passes, c.actual - c.required))
                ratio_headline = {
                    "passing": passing, "total": len(checks),
                    "pct": round(passing / len(checks) * 100),
                    "worst_label": worst.label,
                }

    unread = (client.table("notifications").select("id", count="exact")
              .eq("facility_id", facility_id).eq("staff_id", staff_id)
              .neq("status", "read").execute())

    return {
        "staff": {
            "id": st["id"], "name": st.get("name"), "name_en": st.get("name_en"),
            "rank": st.get("rank"), "unit_name": (st.get("unit") or {}).get("name"),
            "employment_type": st.get("employment_type"),
        },
        "date": today.isoformat(),
        "today_shift": today_cell,
        "tasks_total": len(my_tasks),
        "tasks_pending": len([t for t in my_tasks if t["status"] == "pending"]),
        "tasks": my_tasks,
        "hours": hours_progress(client, facility_id, staff_id),
        "attendance": att.today_status(client, facility_id, staff_id),
        "facility_ratio": ratio_headline,
        "unread_notifications": unread.count or 0,
    }


def profile(client, facility_id: str, staff_id: str) -> dict:
    st = _staff_row(client, facility_id, staff_id)
    certs = (client.table("staff_certificates").select("cert_type,expiry_date")
             .eq("facility_id", facility_id).eq("staff_id", staff_id)
             .order("expiry_date").execute().data)
    today = Date.today()
    return {
        "id": st["id"], "name": st.get("name"), "name_en": st.get("name_en"),
        "rank": st.get("rank"), "employment_type": st.get("employment_type"),
        "unit_name": (st.get("unit") or {}).get("name"),
        "gender": st.get("gender"),
        "is_mentor": bool(st.get("is_mentor")),
        "is_audited_for_medication": bool(st.get("is_audited_for_medication")),
        "certificates": [{
            "cert_type": c["cert_type"], "expiry_date": c.get("expiry_date"),
            "days_left": ((as_date(c["expiry_date"]) - today).days
                          if c.get("expiry_date") else None),
        } for c in certs],
        "hours": hours_progress(client, facility_id, staff_id),
        "attendance_month": att.month_summary(client, facility_id, staff_id),
    }


def my_leave(client, facility_id: str, staff_id: str) -> list[dict]:
    from .leave import list_requests
    return list_requests(client, facility_id, staff_id=staff_id)


def colleagues_on(client, facility_id: str, on: Date) -> list[dict]:
    """Who else is on duty today — shown on the staff app's shift screen."""
    period = resolve_period(client, facility_id, None)
    if not period:
        return []
    version = operative_version(client, facility_id, period["id"])
    if not version:
        return []
    shifts = (client.table("shifts").select("*")
              .eq("roster_version_id", version["id"]).eq("date", str(on))
              .eq("is_working", True).execute().data)
    if not shifts:
        return []
    by_id = {s["id"]: s for s in shifts}
    assigns = (client.table("shift_assignments").select("shift_id,staff_id,status")
               .in_("shift_id", list(by_id)).execute().data)
    staff = staff_by_id(client, facility_id)
    out = []
    for a in assigns:
        if not a.get("staff_id") or a.get("status") == "cancelled":
            continue
        st = staff.get(a["staff_id"]) or {}
        sh = by_id[a["shift_id"]]
        out.append({
            "staff_id": a["staff_id"],
            "name": st.get("name"), "name_en": st.get("name_en"), "rank": st.get("rank"),
            "shift_type": sh["shift_type"],
            "start_time": (sh.get("start_time") or "")[:5] or None,
            "end_time": (sh.get("end_time") or "")[:5] or None,
        })
    out.sort(key=lambda c: (c["shift_type"], c["name_en"] or ""))
    return out
