"""Period / time helpers shared by the Phase 3 services.

Phase 1 services grew their own private copies of these; new code shares one
implementation so "which roster version am I looking at?" answers the same way
on every screen.
"""
from __future__ import annotations

import calendar
from datetime import date as Date, datetime, timezone

LEAVE_CODES = {"AL", "SL", "DSL"}        # non-working codes that mean "away"
OFF_CODES = {"OFF", "DO", "SLEEP"}       # non-working codes that mean "free"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso(v) -> str:
    """Date-ish value -> 'YYYY-MM-DD'."""
    return str(v)[:10]


def as_date(v) -> Date:
    return v if isinstance(v, Date) else Date.fromisoformat(iso(v))


def to_min(t: str | None) -> int | None:
    """'HH:MM[:SS]' -> minutes past midnight."""
    if not t:
        return None
    h, m = str(t).split(":")[:2]
    return int(h) * 60 + int(m)


def shift_minutes(shift: dict) -> int:
    """Paid minutes for a shift row. Trusts the explicit cross_midnight flag."""
    start, end = to_min(shift.get("start_time")), to_min(shift.get("end_time"))
    if start is None or end is None:
        return 0
    if shift.get("cross_midnight") or end <= start:
        return (1440 - start) + end
    return end - start


def day_intervals(start: int, end: int) -> list[tuple[int, int]]:
    """Split a possibly cross-midnight window into same-day [start, end) intervals."""
    if end <= start:
        return [(start, 1440), (0, end)]
    return [(start, end)]


def overlaps(a_start: int | None, a_end: int | None, b_start: int, b_end: int) -> bool:
    if a_start is None or a_end is None:
        return False
    for x0, x1 in day_intervals(a_start, a_end):
        for y0, y1 in day_intervals(b_start, b_end):
            if x0 < y1 and y0 < x1:
                return True
    return False


def month_bounds(on: Date | None = None) -> tuple[str, str]:
    on = on or Date.today()
    last = calendar.monthrange(on.year, on.month)[1]
    return f"{on.year:04d}-{on.month:02d}-01", f"{on.year:04d}-{on.month:02d}-{last:02d}"


# ── roster period / version resolution ───────────────────────────────────────
def current_period(client, facility_id: str) -> dict | None:
    """The period covering today, else the most recent by start date."""
    rows = (client.table("roster_periods").select("*")
            .eq("facility_id", facility_id)
            .order("period_start", desc=True).execute().data)
    if not rows:
        return None
    today = Date.today().isoformat()
    for p in rows:                                   # newest first
        if iso(p["period_start"]) <= today <= iso(p["period_end"]):
            return p
    return rows[0]


def resolve_period(client, facility_id: str, period_id: str | None) -> dict | None:
    if not period_id:
        return current_period(client, facility_id)
    rows = (client.table("roster_periods").select("*")
            .eq("facility_id", facility_id).eq("id", period_id).execute().data)
    return rows[0] if rows else None


def operative_version(client, facility_id: str, period_id: str) -> dict | None:
    """The version that represents reality for a period: the published one if there
    is one, else the manual draft. Never an A/B/C candidate — those are proposals."""
    rows = (client.table("roster_versions").select("*")
            .eq("facility_id", facility_id).eq("period_id", period_id)
            .order("created_at", desc=True).execute().data)
    published = [v for v in rows if v.get("status") == "published"]
    if published:
        return published[0]
    manual = [v for v in rows if v.get("version_type") == "manual"]
    return manual[0] if manual else None


def load_roster(client, facility_id: str, version_id: str) -> tuple[list[dict], list[dict]]:
    """(shifts, assignments) for one roster version, in two queries."""
    shifts = (client.table("shifts").select("*")
              .eq("roster_version_id", version_id).execute().data)
    if not shifts:
        return [], []
    assigns = (client.table("shift_assignments").select("*")
               .in_("shift_id", [s["id"] for s in shifts]).execute().data)
    return shifts, assigns


def staff_by_id(client, facility_id: str) -> dict[str, dict]:
    rows = (client.table("staff").select("*, unit:facility_units(name)")
            .eq("facility_id", facility_id).execute().data)
    return {r["id"]: r for r in rows}


def staff_brief(st: dict | None) -> dict:
    """The staff fields every Phase 3 list row shows."""
    if not st:
        return {"staff_id": None, "name": "—", "name_en": None, "rank": None, "unit_name": None}
    unit = st.get("unit") or {}
    return {
        "staff_id": st["id"], "name": st.get("name") or "—",
        "name_en": st.get("name_en"), "rank": st.get("rank"),
        "unit_name": unit.get("name"),
    }
