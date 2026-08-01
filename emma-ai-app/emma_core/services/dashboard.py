"""The Dashboard's single read.

Everything on the page comes from one call so the KPI cards, the SL/DSL
distribution, today's shift mix and the recent-alert feed can never show
numbers from different moments.
"""
from __future__ import annotations

from datetime import date as Date

from . import incidents as incident_svc
from ._common import as_date, assignments_for_shifts, iso, operative_version, resolve_period
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

    shift_mix, shift_mix_date = _shift_mix(client, version, today)

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
        # The mix is not always today's — see _shift_mix. The UI labels the card
        # with this date so a fallback is never mistaken for live staffing.
        "shift_distribution_date": shift_mix_date,
        "recent_incidents": recent,
        "alerts": open_alerts[:6],
        "total_staff": staff_count,
        "compliance_days": ratio_days[-14:],
    }


def _mix_date(client, version_id: str, today: Date) -> str | None:
    """The date the shift mix should describe.

    Rosters are planned in closed cycles, so on the day after a period ends —
    and on any day before the next one is drafted — no shift exists for `today`
    and the card would blank out. Fall back to the nearest rostered day: the
    most recent one on or before today, or, if the whole roster is still ahead,
    its first day.
    """
    # SQL: select date from shifts
    #      where roster_version_id = :version_id and date <= :today
    #      order by date desc limit 1
    past = (client.table("shifts").select("date")
            .eq("roster_version_id", version_id).lte("date", today.isoformat())
            .order("date", desc=True).limit(1).execute().data)
    if past:
        return str(past[0]["date"])[:10]
    # SQL: same, for date > :today, ascending
    ahead = (client.table("shifts").select("date")
             .eq("roster_version_id", version_id).gt("date", today.isoformat())
             .order("date").limit(1).execute().data)
    return str(ahead[0]["date"])[:10] if ahead else None


def _shift_mix(client, version: dict | None,
               today: Date) -> tuple[list[dict], str | None]:
    """How many people are on each shift code, in the operative roster.

    Returns the mix and the date it describes, which is today whenever today is
    rostered and the nearest rostered day otherwise.
    """
    if not version:
        return [], None
    on = _mix_date(client, version["id"], today)
    if not on:
        return [], None
    # SQL: select id, shift_type, is_working from shifts
    #      where roster_version_id = :version_id and date = :on
    shifts = (client.table("shifts").select("id,shift_type,is_working")
              .eq("roster_version_id", version["id"]).eq("date", on)
              .execute().data)
    if not shifts:
        return [], on
    by_id = {s["id"]: s for s in shifts}
    # SQL: select shift_id, staff_id, status from shift_assignments
    #      where shift_id = any(:shift_ids)
    # (in SQL the tally below would be `group by shift_type` with `count(*)`)
    assigns = assignments_for_shifts(client, by_id,
                                     select="shift_id,staff_id,status")

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
    ), on
