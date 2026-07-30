"""Period / time helpers shared by the Phase 3 services.

Phase 1 services grew their own private copies of these; new code shares one
implementation so "which roster version am I looking at?" answers the same way
on every screen.
"""
from __future__ import annotations

import calendar
from datetime import date as Date, datetime, timezone

from ..shifttime import covers_window, day_spans, envelope, paid_minutes, to_minutes

LEAVE_CODES = {"AL", "SL", "DSL"}        # non-working codes that mean "away"
OFF_CODES = {"OFF", "DO", "SLEEP"}       # non-working codes that mean "free"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso(v) -> str:
    """Date-ish value -> 'YYYY-MM-DD'."""
    return str(v)[:10]


def as_date(v) -> Date:
    return v if isinstance(v, Date) else Date.fromisoformat(iso(v))


to_min = to_minutes


def shift_minutes(shift: dict) -> int:
    """Paid minutes for a shift row - segment-aware, so a split A/N shift counts
    its two duty windows, not the elapsed span between them."""
    return paid_minutes(shift)


def shift_envelope(shift: dict) -> tuple[int, int, bool] | None:
    """Outer span of a shift, for overlap and minimum-rest checks."""
    return envelope(shift)


def day_intervals(start: int, end: int) -> list[tuple[int, int]]:
    """Split a possibly cross-midnight window into same-day [start, end) intervals."""
    return day_spans(start, end, end <= start)


def overlaps(a_start: int | None, a_end: int | None, b_start: int, b_end: int) -> bool:
    if a_start is None or a_end is None:
        return False
    for x0, x1 in day_intervals(a_start, a_end):
        for y0, y1 in day_intervals(b_start, b_end):
            if x0 < y1 and y0 < x1:
                return True
    return False


def shift_covers(shift: dict, win_start: int, win_end: int) -> bool:
    """Is the staff member on duty at any point inside the window?"""
    return covers_window(shift, win_start, win_end)


def month_bounds(on: Date | None = None) -> tuple[str, str]:
    on = on or Date.today()
    last = calendar.monthrange(on.year, on.month)[1]
    return f"{on.year:04d}-{on.month:02d}-01", f"{on.year:04d}-{on.month:02d}-{last:02d}"


# ── roster period / version resolution ───────────────────────────────────────
def current_period(client, facility_id: str) -> dict | None:
    """The rostered period covering today, else the most recent rostered one.

    Every caller pairs this with ``operative_version`` and reports on the roster it
    finds, so a period that only exists to carry leave entitlements - open for
    planning, no shifts on it yet - is not the operative period. Preferring a
    rostered one keeps the dashboards and KPIs on the last real roster instead of
    blanking out the moment a future cycle is opened.
    """
    # SQL: select * from roster_periods
    #      where facility_id = :facility_id
    #      order by period_start desc
    # (the "covers today" and "has a roster" tests are done in Python below)
    rows = (client.table("roster_periods").select("*")
            .eq("facility_id", facility_id)
            .order("period_start", desc=True).execute().data)
    if not rows:
        return None
    # SQL: select period_id, version_type, status from roster_versions
    #      where facility_id = :facility_id
    versions = (client.table("roster_versions")
                .select("period_id,version_type,status")
                .eq("facility_id", facility_id).execute().data)
    rostered = {
        v["period_id"] for v in versions
        if v.get("status") == "published" or v.get("version_type") == "manual"
    }
    today = Date.today().isoformat()
    covers_today = [
        p for p in rows                              # newest first
        if iso(p["period_start"]) <= today <= iso(p["period_end"])
    ]
    for group in (covers_today, rows):
        for p in group:
            if p["id"] in rostered:
                return p
    return covers_today[0] if covers_today else rows[0]


def resolve_period(client, facility_id: str, period_id: str | None) -> dict | None:
    if not period_id:
        return current_period(client, facility_id)
    # SQL: select * from roster_periods
    #      where facility_id = :facility_id and id = :period_id
    rows = (client.table("roster_periods").select("*")
            .eq("facility_id", facility_id).eq("id", period_id).execute().data)
    return rows[0] if rows else None


def operative_version(client, facility_id: str, period_id: str) -> dict | None:
    """The version that represents reality for a period: the published one if there
    is one, else the manual draft. Never an A/B/C candidate - those are proposals."""
    # SQL: select * from roster_versions
    #      where facility_id = :facility_id and period_id = :period_id
    #      order by created_at desc
    # (published-then-manual preference is applied in Python, not in the query)
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
    # Two round trips instead of one join - PostgREST cannot return the parent and
    # child sets as separate arrays, and the callers want them separately anyway.
    #
    # SQL (1): select * from shifts where roster_version_id = :version_id
    shifts = (client.table("shifts").select("*")
              .eq("roster_version_id", version_id).execute().data)
    if not shifts:
        return [], []
    # SQL (2): select * from shift_assignments where shift_id = any(:shift_ids)
    assigns = (client.table("shift_assignments").select("*")
               .in_("shift_id", [s["id"] for s in shifts]).execute().data)
    return shifts, assigns


def staff_by_id(client, facility_id: str) -> dict[str, dict]:
    # SQL: select s.*, jsonb_build_object('name', u.name) as unit
    #      from staff s
    #      left join facility_units u on u.id = s.primary_unit_id
    #      where s.facility_id = :facility_id
    rows = (client.table("staff").select("*, unit:facility_units(name)")
            .eq("facility_id", facility_id).execute().data)
    return {r["id"]: r for r in rows}


def staff_brief(st: dict | None) -> dict:
    """The staff fields every Phase 3 list row shows."""
    if not st:
        return {"staff_id": None, "name": "-", "name_en": None, "rank": None, "unit_name": None}
    unit = st.get("unit") or {}
    return {
        "staff_id": st["id"], "name": st.get("name") or "-",
        "name_en": st.get("name_en"), "rank": st.get("rank"),
        "unit_name": unit.get("name"),
    }
