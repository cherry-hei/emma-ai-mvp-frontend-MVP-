"""The Dashboard's single read.

Everything on the page comes from one call so the KPI cards, the SL/DSL
distribution, today's shift mix and the recent-alert feed can never show
numbers from different moments.
"""
from __future__ import annotations

from datetime import date as Date

from . import incidents as incident_svc
from ._common import as_date, iso, operative_version, resolve_period
from .compliance import ratio_series


def summary(client, facility_id: str) -> dict:
    today = Date.today()
    # SQL: select id, code, name, capacity from facilities where id = :facility_id
    facility = (client.table("facilities").select("id,code,name,capacity")
                .eq("id", facility_id).execute().data)
    facility = facility[0] if facility else {}

    period = resolve_period(client, facility_id, None)
    version = operative_version(client, facility_id, period["id"]) if period else None

    stats = incident_svc.stats(client, facility_id, today)

    # compliance rate over the current period, from the ratio engine
    compliance_rate = 0.0
    ratio_days: list[dict] = []
    if period:
        ratio_days = ratio_series(
            client, facility_id, as_date(period["period_start"]),
            min(as_date(period["period_end"]), today),
            roster_version_id=version["id"] if version else None)
        checks = sum(d["checks"] for d in ratio_days)
        passed = sum(d["passed"] for d in ratio_days)
        compliance_rate = round(passed / checks * 100, 1) if checks else 0.0

    shift_mix = _today_shift_mix(client, version, today)

    # SQL: select count(*) from staff
    #      where facility_id = :facility_id and status = 'active'
    # (count="exact" returns the count in the Content-Range header; the id rows
    #  themselves are discarded)
    staff_count = (client.table("staff").select("id", count="exact")
                   .eq("facility_id", facility_id).eq("status", "active").execute().count or 0)

    recent = incident_svc.list_incidents(client, facility_id, limit=5)
    open_alerts = incident_svc.active_alerts(client, facility_id)

    return {
        "facility": {"id": facility.get("id"), "code": facility.get("code"),
                     "name": facility.get("name"), "capacity": facility.get("capacity")},
        "period": ({"id": period["id"], "start": iso(period["period_start"]),
                    "end": iso(period["period_end"]), "status": period.get("status")}
                   if period else None),
        "roster_version": ({"id": version["id"], "label": version.get("label"),
                            "status": version.get("status"),
                            "version_type": version.get("version_type")}
                           if version else None),
        "date": today.isoformat(),
        "kpis": {
            "incidents_month": stats["total"],
            "auto_resolved": stats["auto_resolved"],
            "auto_resolved_pct": stats["auto_resolved_pct"],
            "avg_response_minutes": stats["avg_response_minutes"],
            "compliance_rate_pct": compliance_rate,
            "open_alerts": len(open_alerts),
        },
        "incident_distribution": stats["distribution"],
        "shift_distribution": shift_mix,
        "recent_incidents": recent,
        "alerts": open_alerts[:6],
        "total_staff": staff_count,
        "compliance_days": ratio_days[-14:],
    }


def _today_shift_mix(client, version: dict | None, today: Date) -> list[dict]:
    """How many people are on each shift code today, in the operative roster."""
    if not version:
        return []
    # SQL: select id, shift_type, is_working from shifts
    #      where roster_version_id = :version_id and date = :today
    shifts = (client.table("shifts").select("id,shift_type,is_working")
              .eq("roster_version_id", version["id"]).eq("date", today.isoformat())
              .execute().data)
    if not shifts:
        return []
    by_id = {s["id"]: s for s in shifts}
    # SQL: select shift_id, staff_id, status from shift_assignments
    #      where shift_id = any(:shift_ids)
    # (in SQL the tally below would be `group by shift_type` with `count(*)`)
    assigns = (client.table("shift_assignments").select("shift_id,staff_id,status")
               .in_("shift_id", list(by_id)).execute().data)

    counts: dict[str, int] = {}
    for a in assigns:
        if not a.get("staff_id") or a.get("status") == "cancelled":
            continue
        code = by_id[a["shift_id"]]["shift_type"]
        counts[code] = counts.get(code, 0) + 1
    total = sum(counts.values())
    working = {s["shift_type"]: bool(s.get("is_working")) for s in shifts}
    return sorted(
        [{"shift_type": k, "count": v, "is_working": working.get(k, True),
          "pct": round(v / total * 100) if total else 0} for k, v in counts.items()],
        key=lambda r: (-r["count"], r["shift_type"]),
    )
