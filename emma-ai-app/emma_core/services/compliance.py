"""Per-shift staff-to-resident ratio check. A staff member counts toward a window if their working shift overlaps it at all (minute-level accounting is a later phase). Rules come from staffing_ratio_rules."""
from __future__ import annotations

import math

from ..models import RatioResult


def _mins(t: str | None) -> int | None:
    if not t:
        return None
    h, m = t.split(":")[0], t.split(":")[1]
    return int(h) * 60 + int(m)


def _intervals(start: int, end: int) -> list[tuple[int, int]]:
    """Split a possibly cross-midnight window into same-day intervals."""
    if end <= start:
        return [(start, 1440), (0, end)]
    return [(start, end)]


def _overlaps(s_start: int | None, s_end: int | None, w_start: int, w_end: int) -> bool:
    if s_start is None or s_end is None:
        return False
    for a, b in _intervals(s_start, s_end):
        for c, d in _intervals(w_start, w_end):
            if a < d and c < b:
                return True
    return False


def compute_ratios(client, facility_id: str, on_date, *,
                   roster_version_id: str | None = None) -> list[RatioResult]:
    """Ratio check for a single day. Pass ``roster_version_id`` to scope the count to one version — otherwise A/B/C drafts sharing the same dates double-count staff and falsely pass."""
    d = str(on_date)

    residents = sum(r["resident_count"] for r in (
        client.table("daily_resident_counts").select("resident_count")
        .eq("facility_id", facility_id).eq("date", d).execute().data))

    rules = (client.table("staffing_ratio_rules").select("*")
             .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
             .eq("active", True).execute().data)

    shifts_q = (client.table("shifts").select("*")
                .eq("facility_id", facility_id).eq("date", d).eq("is_working", True))
    if roster_version_id:
        shifts_q = shifts_q.eq("roster_version_id", roster_version_id)
    shifts = shifts_q.execute().data
    shift_by = {s["id"]: s for s in shifts}
    assigns = []
    if shift_by:
        assigns = (client.table("shift_assignments").select("shift_id,role,staff_id")
                   .in_("shift_id", list(shift_by)).execute().data)

    results: list[RatioResult] = []
    for rule in rules:
        ws, we = _mins(rule["time_window_start"]), _mins(rule["time_window_end"])
        count = 0
        for a in assigns:
            sh = shift_by.get(a["shift_id"])
            if not sh or not _overlaps(_mins(sh["start_time"]), _mins(sh["end_time"]), ws, we):
                continue
            if rule.get("staff_rank") and a.get("role") != rule["staff_rank"]:
                continue
            count += 1

        w = f'{rule["time_window_start"][:5]}–{rule["time_window_end"][:5]}'
        if rule.get("ratio_residents_per_staff"):
            ratio = rule["ratio_residents_per_staff"]
            required = math.ceil(residents / ratio) if residents else 0
            label = f'{rule.get("staff_rank") or "Any"} {w} (1:{ratio})'
        else:
            required = rule.get("min_staff_any_rank") or 0
            label = f'Any rank {w} (min {required})'

        results.append(RatioResult(
            label=label, rank=rule.get("staff_rank"),
            window_start=rule["time_window_start"], window_end=rule["time_window_end"],
            residents=residents, required=required, actual=count, passes=count >= required,
        ))
    return results
