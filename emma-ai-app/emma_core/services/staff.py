"""Staff directory reads enriched for the Staff Portfolio. Derived fields (scheduled_hours, contracted_period_hours, status, certs) are scoped to the current roster period - the one covering today, else the most recent - so a future period's blank roster never zeroes out the live directory."""
from __future__ import annotations

from datetime import date as Date

from ..shifttime import paid_minutes

LEAVE_CODES = {"AL", "SL", "DSL"}   # non-working leave shift codes


def _duration(shift: dict) -> int:
    """Paid shift minutes - segment-aware (see emma_core.shifttime), so a split
    A/N shift counts its two duty windows, not the elapsed span between them."""
    return paid_minutes(shift)


def _iso(v) -> str:
    return str(v)[:10]


def _current_period(client, facility_id: str) -> dict | None:
    """The rostered period covering today - see ``_common.current_period``."""
    from ._common import current_period

    return current_period(client, facility_id)


def _manual_version(client, facility_id: str, period_id: str) -> dict | None:
    # SQL: select * from roster_versions
    #      where facility_id = :facility_id
    #        and version_type = 'manual'
    #        and period_id = :period_id
    #      order by created_at desc
    #      limit 1
    rows = (client.table("roster_versions").select("*")
            .eq("facility_id", facility_id).eq("version_type", "manual")
            .eq("period_id", period_id)
            .order("created_at", desc=True).limit(1).execute().data)
    return rows[0] if rows else None


def _roster_stats(client, facility_id: str) -> dict:
    """Per-staff scheduled minutes and on-leave flag from the current period's manual roster, plus period length and version id."""
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
    # SQL: select * from shifts where roster_version_id = :version_id
    shifts = (client.table("shifts").select("*")
              .eq("roster_version_id", ver["id"]).execute().data)
    shift_by = {s["id"]: s for s in shifts}
    assigns = []
    if shift_by:
        # SQL: select shift_id, staff_id from shift_assignments
        #      where shift_id = any(:shift_ids)
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
    # SQL: select * from staff_contracts
    #      where facility_id = :facility_id
    #      order by effective_from desc
    # (the "effective today" window test runs in Python below so the fallback pass
    #  can reuse the same rows instead of issuing a second query)
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


def _certs_by_staff(client, facility_id: str) -> dict[str, list[dict]]:
    """Certificates per staff as {cert_type, expiry_date} records. Returns {} only when
    staff_certificates isn't migrated yet; other DB errors propagate."""
    try:
        # SQL: select staff_id, cert_type, expiry_date from staff_certificates
        #      where facility_id = :facility_id
        #      order by expiry_date
        rows = (client.table("staff_certificates").select("staff_id,cert_type,expiry_date")
                .eq("facility_id", facility_id).order("expiry_date").execute().data)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "pgrst205" in msg or "could not find the table" in msg or "does not exist" in msg:
            return {}
        raise
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["staff_id"], []).append(
            {"cert_type": r["cert_type"], "expiry_date": r.get("expiry_date")})
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
    cert_records = certs.get(st["id"], [])
    return {
        **st,
        "unit_name": unit.get("name"),
        "certs": [c["cert_type"] for c in cert_records],
        "certificates": cert_records,
        "scheduled_hours": round(minutes / 60, 1),
        "contracted_period_hours": round(weekly * weeks, 1),
        "status": status,
    }


def list_staff(client, facility_id: str, *, search: str | None = None,
               rank: str | None = None) -> list[dict]:
    # SQL: select s.*, jsonb_build_object('name', u.name) as unit
    #      from staff s
    #      left join facility_units u on u.id = s.primary_unit_id
    #      where s.facility_id = :facility_id
    #      order by s.created_at
    # `search` and `rank` are NOT pushed down - they are applied in the Python loop
    # below (a rank filter would be `and s.rank = :rank`, search an ilike on
    # s.name / s.name_en).
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
    # SQL: select s.*, jsonb_build_object('name', u.name) as unit
    #      from staff s
    #      left join facility_units u on u.id = s.primary_unit_id
    #      where s.facility_id = :facility_id and s.id = :staff_id
    rows = (client.table("staff").select("*, unit:facility_units(name)")
            .eq("facility_id", facility_id).eq("id", staff_id).execute().data)
    if not rows:
        return None
    stats = _roster_stats(client, facility_id)
    certs = _certs_by_staff(client, facility_id)
    contracts = _contracts_by_staff(client, facility_id)
    detail = _enrich(rows[0], stats=stats, certs=certs, contracts=contracts)

    # recent working history from the manual/published roster only, never A/B/C drafts.
    #
    # SQL: select a.tasks,
    #             jsonb_build_object(
    #               'date', sh.date, 'shift_type', sh.shift_type,
    #               'start_time', sh.start_time, 'end_time', sh.end_time,
    #               'is_working', sh.is_working,
    #               'version', jsonb_build_object('version_type', v.version_type,
    #                                             'status', v.status)) as shift
    #      from shift_assignments a
    #      left join shifts sh on sh.id = a.shift_id
    #      left join roster_versions v on v.id = sh.roster_version_id
    #      where a.staff_id = :staff_id
    # The is_working / manual-or-published filter and the "10 most recent" cut are
    # applied in Python below, not in the query.
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
