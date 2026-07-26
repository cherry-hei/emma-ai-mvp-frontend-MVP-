"""Staff directory reads, enriched for the frontend Staff Portfolio.

Derived fields are scoped to the facility's CURRENT roster period (the one
covering today, else the most recent), so creating a future period's blank
roster never zeroes out the live directory:
  • scheduled_hours   — working minutes assigned to the staff in the current
                        period's manual roster (÷60).
  • contracted_period_hours — the effective weekly contract scaled to the period.
  • status            — 'on_leave' (a leave cell on the reference date),
                        'scheduled' (has working shifts this period) or
                        'available'.
  • certs             — from staff_certificates (empty only when that table isn't
                        migrated yet; other DB errors propagate).
"""
from __future__ import annotations

from datetime import date as Date

LEAVE_CODES = {"AL", "SL", "DSL"}   # non-working leave shift codes


def _mins(t: str | None) -> int | None:
    if not t:
        return None
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


def _duration(shift: dict) -> int:
    """Minutes for a shift. Trusts the explicit cross_midnight flag (no auto-flip
    on end<=start, which would double-count contradictory data)."""
    start, end = _mins(shift.get("start_time")), _mins(shift.get("end_time"))
    if start is None or end is None:
        return 0
    if shift.get("cross_midnight"):
        return (1440 - start) + end
    return max(0, end - start)


def _iso(v) -> str:
    return str(v)[:10]


def _current_period(client, facility_id: str) -> dict | None:
    """The period covering today, else the most recent by start date."""
    periods = (client.table("roster_periods").select("*")
               .eq("facility_id", facility_id)
               .order("period_start", desc=True).execute().data)
    if not periods:
        return None
    today = Date.today().isoformat()
    for p in periods:                       # newest-first
        if _iso(p["period_start"]) <= today <= _iso(p["period_end"]):
            return p
    return periods[0]


def _manual_version(client, facility_id: str, period_id: str) -> dict | None:
    rows = (client.table("roster_versions").select("*")
            .eq("facility_id", facility_id).eq("version_type", "manual")
            .eq("period_id", period_id)
            .order("created_at", desc=True).limit(1).execute().data)
    return rows[0] if rows else None


def _roster_stats(client, facility_id: str) -> dict:
    """Per-staff scheduled minutes + on-leave-today flag from the CURRENT period's
    manual roster, plus period length and the manual version id (for history)."""
    stats: dict = {"by_staff": {}, "period_days": 28, "version_id": None}
    period = _current_period(client, facility_id)
    if not period:
        return stats
    ps, pe = _iso(period["period_start"]), _iso(period["period_end"])
    stats["period_days"] = (Date.fromisoformat(pe) - Date.fromisoformat(ps)).days + 1
    today = Date.today().isoformat()
    ref = today if ps <= today <= pe else ps

    ver = _manual_version(client, facility_id, period["id"])
    if not ver:
        return stats
    stats["version_id"] = ver["id"]
    shifts = (client.table("shifts").select("*")
              .eq("roster_version_id", ver["id"]).execute().data)
    shift_by = {s["id"]: s for s in shifts}
    assigns = []
    if shift_by:
        assigns = (client.table("shift_assignments").select("shift_id,staff_id")
                   .in_("shift_id", list(shift_by)).execute().data)
    for a in assigns:
        sh, sid = shift_by.get(a["shift_id"]), a.get("staff_id")
        if not sh or not sid:
            continue
        d = stats["by_staff"].setdefault(sid, {"minutes": 0, "on_leave": False})
        if sh.get("is_working"):
            d["minutes"] += _duration(sh)
        elif sh.get("shift_type") in LEAVE_CODES and _iso(sh.get("date")) == ref:
            d["on_leave"] = True     # leave specifically on the reference date
    return stats


def _contracts_by_staff(client, facility_id: str) -> dict[str, dict]:
    """The currently-effective contract per staff (fallback: most recent)."""
    rows = (client.table("staff_contracts").select("*")
            .eq("facility_id", facility_id)
            .order("effective_from", desc=True).execute().data)
    today = Date.today().isoformat()
    out: dict[str, dict] = {}
    for c in rows:                                  # newest effective_from first
        ef, et = c.get("effective_from"), c.get("effective_to")
        if (ef is None or _iso(ef) <= today) and (et is None or _iso(et) >= today):
            out.setdefault(c["staff_id"], c)
    for c in rows:                                  # fallback for staff w/o an effective row
        out.setdefault(c["staff_id"], c)
    return out


def _certs_by_staff(client, facility_id: str) -> dict[str, list[str]]:
    """Certificate types per staff. Returns {} ONLY when staff_certificates isn't
    migrated yet; any other DB error propagates (never silently reports 'no certs')."""
    try:
        rows = (client.table("staff_certificates").select("staff_id,cert_type")
                .eq("facility_id", facility_id).execute().data)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "pgrst205" in msg or "could not find the table" in msg or "does not exist" in msg:
            return {}
        raise
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["staff_id"], []).append(r["cert_type"])
    return out


def _weekly_hours(st: dict, contract: dict) -> float:
    weekly = contract.get("weekly_hours")
    if weekly is None:
        weekly = st.get("contracted_hours")
    if weekly is None:
        weekly = 44
    return float(weekly)


def _enrich(st: dict, *, stats: dict, certs: dict, contracts: dict) -> dict:
    unit = st.get("unit") or {}
    s = stats["by_staff"].get(st["id"], {})
    weekly = _weekly_hours(st, contracts.get(st["id"], {}))
    weeks = max(stats["period_days"], 1) / 7
    minutes = s.get("minutes", 0)
    status = "on_leave" if s.get("on_leave") else ("scheduled" if minutes else "available")
    return {
        **st,
        "unit_name": unit.get("name"),
        "certs": certs.get(st["id"], []),
        "scheduled_hours": round(minutes / 60, 1),
        "contracted_period_hours": round(weekly * weeks, 1),
        "status": status,
    }


def list_staff(client, facility_id: str, *, search: str | None = None,
               rank: str | None = None) -> list[dict]:
    rows = (client.table("staff").select("*, unit:facility_units(name)")
            .eq("facility_id", facility_id).order("created_at").execute().data)
    stats = _roster_stats(client, facility_id)
    certs = _certs_by_staff(client, facility_id)
    contracts = _contracts_by_staff(client, facility_id)

    needle = search.lower() if search else None
    out: list[dict] = []
    for st in rows:
        if rank and st.get("rank") != rank:
            continue
        if needle:
            hay = f'{st.get("name") or ""} {st.get("name_en") or ""}'.lower()
            if needle not in hay:
                continue
        out.append(_enrich(st, stats=stats, certs=certs, contracts=contracts))
    return out


def get_staff_detail(client, facility_id: str, staff_id: str) -> dict | None:
    rows = (client.table("staff").select("*, unit:facility_units(name)")
            .eq("facility_id", facility_id).eq("id", staff_id).execute().data)
    if not rows:
        return None
    stats = _roster_stats(client, facility_id)
    certs = _certs_by_staff(client, facility_id)
    contracts = _contracts_by_staff(client, facility_id)
    detail = _enrich(rows[0], stats=stats, certs=certs, contracts=contracts)

    # recent WORKING shift history from the manual/published roster only (never
    # speculative A/B/C drafts — those live as archived/draft versions).
    assigns = (client.table("shift_assignments")
               .select("tasks, shift:shifts(date,shift_type,start_time,end_time,is_working,"
                       "version:roster_versions(version_type,status))")
               .eq("staff_id", staff_id).execute().data)
    history = []
    for a in assigns:
        sh = a.get("shift") or {}
        ver = sh.get("version") or {}
        if not sh or not sh.get("is_working"):
            continue
        if ver.get("version_type") != "manual" and ver.get("status") != "published":
            continue
        history.append({
            "date": sh.get("date"),
            "shift_type": sh.get("shift_type"),
            "start_time": (sh.get("start_time") or "")[:5] or None,
            "end_time": (sh.get("end_time") or "")[:5] or None,
            "tasks": a.get("tasks") or [],
        })
    history.sort(key=lambda h: h["date"] or "", reverse=True)
    detail["shift_history"] = history[:10]
    return detail
