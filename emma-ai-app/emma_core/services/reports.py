"""Report generation and the automated-report registry (spec 7.1 / 7.2 / 3.7).

`generate` builds a report from the roster that is actually in the database and
persists both the parameters and the resulting rows into `reports`, so a report
shown to SWD can be reproduced byte-for-byte later. Every generator returns the
same {columns, rows, meta} shape, which is what makes one CSV renderer enough.
"""
from __future__ import annotations

import csv
import io
from datetime import date as Date

from ._common import as_date, assignments_for_shifts, iso, month_bounds, operative_version, resolve_period, shift_minutes
from .compliance import minute_ratio_series, ratio_series, threshold_monitors

NIGHT_CODES = {"N", "AN", "7P"}
OFF_CODES = {"OFF", "DO"}


# ── registry reads ───────────────────────────────────────────────────────────
def list_schedules(client, facility_id: str) -> list[dict]:
    # SQL: select * from report_schedules
    #      where facility_id = :facility_id and active = true
    #      order by sort_order
    return (client.table("report_schedules").select("*")
            .eq("facility_id", facility_id).eq("active", True)
            .order("sort_order").execute().data)


def list_event_triggers(client, facility_id: str, on: Date | None = None) -> list[dict]:
    """Configured triggers, each carrying its real occurrence count this month."""
    start, end = month_bounds(on)
    # SQL: select * from event_trigger_rules
    #      where facility_id = :facility_id and active = true
    #      order by sort_order
    rules = (client.table("event_trigger_rules").select("*")
             .eq("facility_id", facility_id).eq("active", True)
             .order("sort_order").execute().data)
    # SQL: select event_type, date, title from facility_events
    #      where facility_id = :facility_id and date >= :start and date <= :end
    # (counted per event_type in Python and stitched onto the rules - in SQL this
    #  would be a `left join lateral (... group by event_type)` on the rule code)
    events = (client.table("facility_events").select("event_type,date,title")
              .eq("facility_id", facility_id)
              .gte("date", start).lte("date", end).execute().data)
    counts: dict[str, int] = {}
    for e in events:
        counts[e["event_type"]] = counts.get(e["event_type"], 0) + 1
    return [{**r, "recent_count": counts.get(r["trigger_code"], 0),
             "month_start": start, "month_end": end} for r in rules]


def list_regulatory_docs(client, facility_id: str) -> list[dict]:
    # SQL: select * from regulatory_documents
    #      where (facility_id = :facility_id or facility_id is null)  -- null = shared
    #      order by sort_order
    return (client.table("regulatory_documents").select("*")
            .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
            .order("sort_order").execute().data)


def list_reports(client, facility_id: str, *, limit: int = 20) -> list[dict]:
    # SQL: select id, report_type, title, period_start, period_end, format,
    #             row_count, created_at
    #      from reports
    #      where facility_id = :facility_id
    #      order by created_at desc
    #      limit :limit
    # (payload_json is deliberately not selected - the list view never renders it)
    return (client.table("reports")
            .select("id,report_type,title,period_start,period_end,format,row_count,created_at")
            .eq("facility_id", facility_id)
            .order("created_at", desc=True).limit(limit).execute().data)


def get_report(client, facility_id: str, report_id: str) -> dict | None:
    # SQL: select * from reports
    #      where facility_id = :facility_id and id = :report_id
    rows = (client.table("reports").select("*")
            .eq("facility_id", facility_id).eq("id", report_id).execute().data)
    return rows[0] if rows else None


# ── roster loading shared by the roster-derived reports ──────────────────────
def _roster_context(client, facility_id: str, period_id: str | None):
    period = resolve_period(client, facility_id, period_id)
    if not period:
        raise ValueError("no roster period to report on")
    version = operative_version(client, facility_id, period["id"])
    # The three reads every roster-derived report shares; each generator then pivots
    # them differently in Python.
    #
    # SQL: select * from shifts where roster_version_id = :version_id
    shifts = ({} if not version else
              {s["id"]: s for s in (client.table("shifts").select("*")
                                    .eq("roster_version_id", version["id"]).execute().data)})
    assigns = []
    if shifts:
        assigns = [a for a in assignments_for_shifts(client, shifts)
                   if a.get("status") != "cancelled" and a.get("staff_id")]
    # SQL: select id, name, name_en, rank, gender, employment_type from staff
    #      where facility_id = :facility_id
    staff = {s["id"]: s for s in (
        client.table("staff").select("id,name,name_en,rank,gender,employment_type")
        .eq("facility_id", facility_id).execute().data)}
    return period, version, shifts, assigns, staff


def _cells_by_staff(shifts: dict, assigns: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for a in assigns:
        sh = shifts[a["shift_id"]]
        out.setdefault(a["staff_id"], []).append(sh)
    for rows in out.values():
        rows.sort(key=lambda s: str(s["date"]))
    return out


def _staff_label(st: dict) -> str:
    return st.get("name_en") or st.get("name") or "-"


# ── generators ───────────────────────────────────────────────────────────────
def _roster_hours(client, facility_id: str, params: dict) -> dict:
    period, version, shifts, assigns, staff = _roster_context(
        client, facility_id, params.get("period_id"))
    cells = _cells_by_staff(shifts, assigns)
    rows = []
    for sid, st in staff.items():
        mine = cells.get(sid, [])
        working = [s for s in mine if s.get("is_working")]
        minutes = sum(shift_minutes(s) for s in working)
        rows.append({
            "staff": _staff_label(st), "rank": st["rank"],
            "employment_type": st["employment_type"],
            "working_shifts": len(working),
            "hours": round(minutes / 60, 1),
            "avg_hours_per_shift": round(minutes / 60 / len(working), 1) if working else 0,
        })
    rows.sort(key=lambda r: -r["hours"])
    return {
        "columns": [
            {"key": "staff", "label": "Staff"}, {"key": "rank", "label": "Rank"},
            {"key": "employment_type", "label": "Employment"},
            {"key": "working_shifts", "label": "Working shifts"},
            {"key": "hours", "label": "Total hours"},
            {"key": "avg_hours_per_shift", "label": "Avg hrs/shift"},
        ],
        "rows": rows,
        "meta": _meta(period, version, "Total rostered hours per staff member"),
    }


def _ph_dayoff(client, facility_id: str, params: dict) -> dict:
    period, version, shifts, assigns, staff = _roster_context(
        client, facility_id, params.get("period_id"))
    # SQL: select date, day_type from calendar_days
    #      where (facility_id = :facility_id or facility_id is null)
    #        and date >= :period_start and date <= :period_end
    # (the day_type filter is the comprehension's `if`, not a where clause)
    holidays = {iso(c["date"]) for c in (
        client.table("calendar_days").select("date,day_type")
        .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
        .gte("date", str(period["period_start"])).lte("date", str(period["period_end"]))
        .execute().data) if c["day_type"] in ("public_holiday", "statutory_holiday")}
    cells = _cells_by_staff(shifts, assigns)

    rows = []
    for sid, st in staff.items():
        mine = cells.get(sid, [])
        rows.append({
            "staff": _staff_label(st), "rank": st["rank"],
            "day_offs": len([s for s in mine if s["shift_type"] in OFF_CODES]),
            "annual_leave": len([s for s in mine if s["shift_type"] == "AL"]),
            "ph_worked": len([s for s in mine
                              if iso(s["date"]) in holidays and s.get("is_working")]),
            "ph_off": len([s for s in mine
                           if iso(s["date"]) in holidays and not s.get("is_working")]),
        })
    rows.sort(key=lambda r: (-r["ph_worked"], r["staff"]))
    return {
        "columns": [
            {"key": "staff", "label": "Staff"}, {"key": "rank", "label": "Rank"},
            {"key": "day_offs", "label": "Day offs"},
            {"key": "annual_leave", "label": "Annual leave"},
            {"key": "ph_worked", "label": "PH worked"}, {"key": "ph_off", "label": "PH off"},
        ],
        "rows": rows,
        "meta": {**_meta(period, version, "Public holiday and day-off distribution"),
                 "public_holidays": sorted(holidays)},
    }


def _do_count(client, facility_id: str, params: dict) -> dict:
    period, version, shifts, assigns, staff = _roster_context(
        client, facility_id, params.get("period_id"))
    cells = _cells_by_staff(shifts, assigns)
    rows = []
    for sid, st in staff.items():
        mine = cells.get(sid, [])
        offs = [s for s in mine if s["shift_type"] in OFF_CODES]
        working = [s for s in mine if s.get("is_working")]
        minutes = sum(shift_minutes(s) for s in working)
        longest, streak = 0, 0
        for s in mine:
            if s.get("is_working"):
                streak += 1
                longest = max(longest, streak)
            else:
                streak = 0
        rows.append({
            "staff": _staff_label(st), "rank": st["rank"],
            "day_offs": len(offs),
            "hours_per_day_off": round(minutes / 60 / len(offs), 1) if offs else 0,
            "longest_run_without_off": longest,
        })
    rows.sort(key=lambda r: -r["longest_run_without_off"])
    return {
        "columns": [
            {"key": "staff", "label": "Staff"}, {"key": "rank", "label": "Rank"},
            {"key": "day_offs", "label": "Day offs"},
            {"key": "hours_per_day_off", "label": "Hours per day off"},
            {"key": "longest_run_without_off", "label": "Longest run w/o off"},
        ],
        "rows": rows,
        "meta": _meta(period, version, "Day-off frequency and consecutive-work runs"),
    }


def _ap_shifts(client, facility_id: str, params: dict) -> dict:
    period, version, shifts, assigns, staff = _roster_context(
        client, facility_id, params.get("period_id"))
    cells = _cells_by_staff(shifts, assigns)
    rows = []
    for sid, st in staff.items():
        mine = [s for s in cells.get(sid, []) if s.get("is_working")]
        a = len([s for s in mine if s["shift_type"].startswith(("A", "B", "E", "7A", "9A"))
                 and s["shift_type"] != "AN"])
        p = len([s for s in mine if s["shift_type"].startswith("P")])
        n = len([s for s in mine if s["shift_type"] in NIGHT_CODES])
        total = a + p + n
        rows.append({
            "staff": _staff_label(st), "rank": st["rank"],
            "a_shifts": a, "p_shifts": p, "night_shifts": n,
            "p_share_pct": round(p / total * 100) if total else 0,
        })
    rows.sort(key=lambda r: -r["p_share_pct"])
    return {
        "columns": [
            {"key": "staff", "label": "Staff"}, {"key": "rank", "label": "Rank"},
            {"key": "a_shifts", "label": "A shifts"}, {"key": "p_shifts", "label": "P shifts"},
            {"key": "night_shifts", "label": "Night shifts"},
            {"key": "p_share_pct", "label": "P share %"},
        ],
        "rows": rows,
        "meta": _meta(period, version, "A vs P vs night shift distribution per staff"),
    }


def _night_gender(client, facility_id: str, params: dict) -> dict:
    period, version, shifts, assigns, staff = _roster_context(
        client, facility_id, params.get("period_id"))
    buckets: dict[str, dict] = {}
    for a in assigns:
        sh = shifts[a["shift_id"]]
        if sh["shift_type"] not in NIGHT_CODES or not sh.get("is_working"):
            continue
        st = staff.get(a["staff_id"]) or {}
        gender = st.get("gender") or "unknown"
        slot = buckets.setdefault(gender, {"gender": gender, "night_shifts": 0, "staff": set()})
        slot["night_shifts"] += 1
        slot["staff"].add(a["staff_id"])
    total = sum(b["night_shifts"] for b in buckets.values())
    rows = [{
        "gender": b["gender"], "staff_count": len(b["staff"]),
        "night_shifts": b["night_shifts"],
        "share_pct": round(b["night_shifts"] / total * 100) if total else 0,
        "avg_per_staff": round(b["night_shifts"] / len(b["staff"]), 1) if b["staff"] else 0,
    } for b in buckets.values()]
    rows.sort(key=lambda r: -r["night_shifts"])
    return {
        "columns": [
            {"key": "gender", "label": "Gender"},
            {"key": "staff_count", "label": "Staff"},
            {"key": "night_shifts", "label": "Night shifts"},
            {"key": "share_pct", "label": "Share %"},
            {"key": "avg_per_staff", "label": "Avg per staff"},
        ],
        "rows": rows,
        "meta": {**_meta(period, version, "Night shift distribution by gender"),
                 "night_codes": sorted(NIGHT_CODES)},
    }


def _staff_register(client, facility_id: str, params: dict) -> dict:
    """SWD staff register (Annex 3.2 shape): who is employed, at what rank, with
    which certificates and medication-audit status."""
    period, version, *_ = _roster_context(client, facility_id, params.get("period_id"))
    # SQL: select s.id, s.name, s.name_en, s.rank, s.employment_type, s.status,
    #             s.gender, s.is_audited_for_medication, s.is_mentor,
    #             jsonb_build_object('name', u.name) as unit
    #      from staff s
    #      left join facility_units u on u.id = s.primary_unit_id
    #      where s.facility_id = :facility_id
    #      order by s.rank
    staff = (client.table("staff")
             .select("id,name,name_en,rank,employment_type,status,gender,"
                     "is_audited_for_medication,is_mentor, unit:facility_units(name)")
             .eq("facility_id", facility_id).order("rank").execute().data)
    certs: dict[str, list[str]] = {}
    # SQL: select staff_id, cert_type, expiry_date from staff_certificates
    #      where facility_id = :facility_id
    #      order by expiry_date
    for c in (client.table("staff_certificates").select("staff_id,cert_type,expiry_date")
              .eq("facility_id", facility_id).order("expiry_date").execute().data):
        certs.setdefault(c["staff_id"], []).append(
            f'{c["cert_type"]} ({iso(c["expiry_date"])})' if c.get("expiry_date")
            else c["cert_type"])
    rows = [{
        "staff": _staff_label(st), "name_local": st.get("name"), "rank": st["rank"],
        "unit": (st.get("unit") or {}).get("name") or "-",
        "employment_type": st["employment_type"], "status": st["status"],
        "medication_audited": "Y" if st.get("is_audited_for_medication") else "N",
        "certificates": "; ".join(certs.get(st["id"], [])) or "-",
    } for st in staff]
    return {
        "columns": [
            {"key": "staff", "label": "Name (EN)"},
            {"key": "name_local", "label": "Name"}, {"key": "rank", "label": "Rank"},
            {"key": "unit", "label": "Unit"},
            {"key": "employment_type", "label": "Employment"},
            {"key": "status", "label": "Status"},
            {"key": "medication_audited", "label": "Med. audited"},
            {"key": "certificates", "label": "Certificates"},
        ],
        "rows": rows,
        "meta": _meta(period, version, "SWD staff register with certificate status"),
    }


def _staffing_ratio(client, facility_id: str, params: dict) -> dict:
    """Both statutory report methods (spec 3.7): per-shift and minute-level window."""
    period, version, *_ = _roster_context(client, facility_id, params.get("period_id"))
    start = as_date(params.get("date_from") or period["period_start"])
    end = as_date(params.get("date_to") or period["period_end"])
    version_id = version["id"] if version else None

    per_shift = ratio_series(client, facility_id, start, end, roster_version_id=version_id)
    windows = minute_ratio_series(client, facility_id, start, end,
                                  roster_version_id=version_id)
    rows = [{
        "date": w["date"], "window": f'{w["window_start"]}–{w["window_end"]}',
        "rule": w["label"], "residents": w["residents"], "required": w["required"],
        "min_on_duty": w["min_actual"], "breach_minutes": w["breach_minutes"],
        "result": "PASS" if w["passes"] else "FAIL",
    } for w in windows]
    return {
        "columns": [
            {"key": "date", "label": "Date"}, {"key": "window", "label": "Statutory window"},
            {"key": "rule", "label": "Rule"}, {"key": "residents", "label": "Residents"},
            {"key": "required", "label": "Required"},
            {"key": "min_on_duty", "label": "Min on duty"},
            {"key": "breach_minutes", "label": "Breach minutes"},
            {"key": "result", "label": "Result"},
        ],
        "rows": rows,
        "meta": {
            **_meta(period, version, "Per-shift and statutory-window staffing ratio"),
            "date_from": start.isoformat(), "date_to": end.isoformat(),
            "per_shift_days": per_shift,
            "total_breach_minutes": sum(w["breach_minutes"] for w in windows),
            "failing_windows": len([w for w in windows if not w["passes"]]),
        },
    }


def _compliance_summary(client, facility_id: str, params: dict) -> dict:
    """SWD-style summary: ratio result, open violations, certificate warnings."""
    from . import kpi as kpi_svc

    period, version, *_ = _roster_context(client, facility_id, params.get("period_id"))
    ratio = kpi_svc.staffing_ratio_compliance(client, facility_id, period["id"])
    conflicts = kpi_svc.conflict_rate(client, facility_id, period["id"])
    monitors = threshold_monitors(client, facility_id)

    rows = [
        {"section": "Staffing ratio", "metric": "Pass rate",
         "value": f'{ratio["pass_rate_pct"]}%',
         "status": "PASS" if ratio["publishable"] else "FAIL"},
        {"section": "Staffing ratio", "metric": "Breach minutes",
         "value": ratio["breach_minutes"],
         "status": "PASS" if ratio["breach_minutes"] == 0 else "FAIL"},
        {"section": "Hard constraints", "metric": "Unresolved violations",
         "value": conflicts["hard_violations"],
         "status": "PASS" if conflicts["hard_violations"] == 0 else "FAIL"},
        {"section": "Hard constraints", "metric": "Conflict rate",
         "value": f'{conflicts["conflict_rate_pct"]}%', "status": "INFO"},
    ]
    for m in monitors:
        rows.append({
            "section": "Threshold monitor", "metric": m["name_en"],
            "value": m["current_count"],
            "status": {"ok": "PASS", "warn": "WARN", "over": "FAIL"}[m["severity"]],
        })
    return {
        "columns": [
            {"key": "section", "label": "Section"}, {"key": "metric", "label": "Metric"},
            {"key": "value", "label": "Value"}, {"key": "status", "label": "Status"},
        ],
        "rows": rows,
        "meta": {**_meta(period, version, "SWD compliance summary"),
                 "by_rule": ratio["by_rule"]},
    }


def _monthly_staffing_compliance(client, facility_id: str, params: dict) -> dict:
    """The scheduled monthly report - the compliance summary plus workforce mix."""
    from . import kpi as kpi_svc

    base = _compliance_summary(client, facility_id, params)
    period, *_ = _roster_context(client, facility_id, params.get("period_id"))
    external = kpi_svc.external_workforce(client, facility_id, period["id"])
    fairness = kpi_svc.shift_fairness(client, facility_id, period["id"])

    base["rows"].append({
        "section": "Workforce", "metric": "External dependency",
        "value": f'{external["dependency_pct"]}%',
        "status": "WARN" if external["dependency_pct"] > 25 else "PASS",
    })
    base["rows"].append({
        "section": "Workforce", "metric": "Agency cost (period)",
        "value": f'HK${external["agency_cost"]:,}', "status": "INFO",
    })
    for f in fairness["by_shift_type"]:
        if f["difficult"]:
            base["rows"].append({
                "section": "Fairness", "metric": f'{f["shift_type"]} Gini',
                "value": f["gini"], "status": "WARN" if f["gini"] > 0.25 else "PASS",
            })
    base["meta"]["title_hint"] = "Monthly staffing compliance report"
    return base


def _event_overlays(client, facility_id: str, period: dict) -> dict[str, list[dict]]:
    """The special events on each day of the period, with the staffing they add.

    Cherry, 1 Aug 2026, on 7.2: "include events/overlays on the exported roster
    grid - a printed roster without special events is incomplete."

    The export used to carry the event's title alone, which is incomplete in two
    ways that matter on a printed sheet:

    * the title does not say what the event costs. '剪髮' on a Tuesday reads as a
      note; '剪髮 (+1 CW/HCA)' reads as the reason the ward is one body short if
      nobody was added. The additive requirements are the overlay - the rest is
      a diary entry.
    * an event booked for one floor was printed against every floor. Keying by
      date alone put 3/F's CGAT on the 1/F rows, so a manager checking cover for
      1/F saw a demand that was never theirs.

    Returned keyed by date; each entry carries `unit_id` so the caller can drop
    the ones that belong to another floor.
    """
    from .scheduling import EVENT_TYPE_LABELS, normalise_event_type

    # SQL: select id, date, title, event_type, unit_id from facility_events
    #      where facility_id = :facility_id
    #        and date >= :period_start and date <= :period_end
    rows = (client.table("facility_events")
            .select("id,date,title,event_type,unit_id")
            .eq("facility_id", facility_id)
            .gte("date", iso(period["period_start"]))
            .lte("date", iso(period["period_end"])).execute().data or [])
    if not rows:
        return {}

    # SQL: select event_id, rank, count, is_additive from event_staffing_requirements
    #      where facility_id = :facility_id and event_id = any(:event_ids)
    extra: dict[str, list[str]] = {}
    try:
        for req in (client.table("event_staffing_requirements")
                    .select("event_id,rank,count,is_additive")
                    .eq("facility_id", facility_id)
                    .in_("event_id", [r["id"] for r in rows]).execute().data or []):
            if req.get("is_additive"):
                extra.setdefault(req["event_id"], []).append(
                    f'+{int(req.get("count") or 1)} {req.get("rank") or ""}'.strip())
    except Exception:  # noqa: BLE001
        # A missing requirements table degrades the overlay to a plain title,
        # which is what this export printed before. It must not lose the roster.
        extra = {}

    out: dict[str, list[dict]] = {}
    for row in rows:
        code = normalise_event_type(row.get("event_type") or "")
        zh = EVENT_TYPE_LABELS.get(code, ("", ""))[0]
        label = row.get("title") or zh or code or "event"
        added = extra.get(row["id"]) or []
        out.setdefault(iso(row["date"]), []).append({
            "label": f'{label} ({", ".join(added)})' if added else label,
            "unit_id": row.get("unit_id"),
        })
    return out


def _roster_export(client, facility_id: str, params: dict) -> dict:
    """The published roster itself: one row per staff × day (spec 7.2).

    Long rather than wide - one row per cell, carrying the task codes, the unit
    and the event markers - because the export is consumed by both a spreadsheet
    and a diff, and a staff × day matrix breaks the moment a period is a different
    length.
    """
    period, version, shifts, assigns, staff = _roster_context(
        client, facility_id, params.get("period_id"))
    units = {}
    if shifts:
        # SQL: select id, name from facility_units where facility_id = :facility_id
        units = {u["id"]: u["name"] for u in (
            client.table("facility_units").select("id,name")
            .eq("facility_id", facility_id).execute().data)}
    events = _event_overlays(client, facility_id, period) if version else {}

    by_shift = {a["shift_id"]: a for a in assigns}
    rows = []
    for shift_id, shift in shifts.items():
        assignment = by_shift.get(shift_id)
        member = staff.get((assignment or {}).get("staff_id") or "")
        rows.append({
            "date": iso(shift["date"]),
            "staff": _staff_label(member) if member else "(unassigned)",
            "staff_zh": (member or {}).get("name") or "",
            "rank": (member or {}).get("rank") or shift.get("required_rank") or "",
            "employment_type": (member or {}).get("employment_type") or "",
            "shift_type": shift["shift_type"],
            "start_time": str(shift.get("start_time") or ""),
            "end_time": str(shift.get("end_time") or ""),
            "paid_hours": round(shift_minutes(shift) / 60, 2)
                          if shift.get("is_working") else 0,
            "unit": units.get(shift.get("unit_id") or "", ""),
            "tasks": ", ".join((assignment or {}).get("tasks") or []),
            "is_agency": bool((assignment or {}).get("is_agency")),
            # A facility-wide event prints on every row; a unit-scoped one only
            # on the rows for that unit.
            "events": "; ".join(
                overlay["label"]
                for overlay in events.get(iso(shift["date"]), [])
                if not overlay["unit_id"] or overlay["unit_id"] == shift.get("unit_id")
            ),
        })
    rows.sort(key=lambda r: (r["date"], r["staff"]))
    working = [r for r in rows if r["paid_hours"]]
    return {
        "columns": [
            {"key": "date", "label": "Date"}, {"key": "staff", "label": "Staff"},
            {"key": "staff_zh", "label": "姓名"}, {"key": "rank", "label": "Rank"},
            {"key": "employment_type", "label": "Employment"},
            {"key": "shift_type", "label": "Shift"},
            {"key": "start_time", "label": "Start"}, {"key": "end_time", "label": "End"},
            {"key": "paid_hours", "label": "Paid hours"},
            {"key": "unit", "label": "Unit"}, {"key": "tasks", "label": "Task codes"},
            {"key": "is_agency", "label": "External"},
            {"key": "events", "label": "Events"},
        ],
        "rows": rows,
        "meta": {**_meta(period, version, "Published roster with task codes and events"),
                 "cells": len(rows), "working_cells": len(working),
                 "paid_hours_total": round(sum(r["paid_hours"] for r in rows), 1)},
    }


def _evidence_pack(client, facility_id: str, params: dict) -> dict:
    """The security / compliance evidence checklist (spec 1.6 / 8.2).

    Every row carries its owner, test method, sample output and whether an
    external qualified reviewer is required. The caveats travel in `meta` so an
    exported pack cannot lose the wording the submission depends on.
    """
    from . import governance

    checklist = governance.evidence_checklist(client, facility_id)
    rows = [{
        "code": item["code"], "category": item["category"], "title": item["title"],
        "owner": item.get("owner") or "", "status": item["status"].upper(),
        "test_method": item.get("test_method") or "",
        "sample_output": item.get("sample_output") or "",
        "external_review": "yes" if item["external_review_required"] else "no",
        "checked_on": iso(item["checked_on"]) if item.get("checked_on") else "",
    } for item in checklist["items"]]
    return {
        "columns": [
            {"key": "code", "label": "Ref"}, {"key": "category", "label": "Category"},
            {"key": "title", "label": "Control"}, {"key": "owner", "label": "Owner"},
            {"key": "status", "label": "Status"},
            {"key": "test_method", "label": "Test method"},
            {"key": "sample_output", "label": "Sample output"},
            {"key": "external_review", "label": "External review"},
            {"key": "checked_on", "label": "Checked"},
        ],
        "rows": rows,
        "meta": {
            "description": "Client / government submission evidence checklist",
            "counts": checklist["counts"],
            "caveats": checklist["caveats"],
            "external_review_required": checklist["external_review_required"],
        },
    }


GENERATORS = {
    "roster_hours": _roster_hours,
    "ph_dayoff": _ph_dayoff,
    "do_count": _do_count,
    "ap_shifts": _ap_shifts,
    "night_gender": _night_gender,
    "staff_register": _staff_register,
    "staffing_ratio": _staffing_ratio,
    "compliance_summary": _compliance_summary,
    "monthly_staffing_compliance": _monthly_staffing_compliance,
    "roster_export": _roster_export,
    "evidence_pack": _evidence_pack,
}

TITLES = {
    "roster_hours": "Hours Report",
    "ph_dayoff": "PH & Day Off Report",
    "do_count": "DO Shift Count Report",
    "ap_shifts": "A/P Shift Distribution",
    "night_gender": "Night Shift Gender Report",
    "staff_register": "SWD Staff Register",
    "staffing_ratio": "Staffing Ratio Report",
    "compliance_summary": "SWD Compliance Summary",
    "monthly_staffing_compliance": "Monthly Staffing Compliance Report",
    "roster_export": "Roster Export",
    "evidence_pack": "Security & Compliance Evidence Pack",
}


def _meta(period: dict, version: dict | None, description: str) -> dict:
    return {
        "description": description,
        "period_id": period["id"],
        "period_start": iso(period["period_start"]),
        "period_end": iso(period["period_end"]),
        "roster_version_id": version["id"] if version else None,
        "roster_version_label": version.get("label") if version else None,
        "roster_version_status": version.get("status") if version else None,
    }


def generate(client, facility_id: str, report_type: str, *, params: dict | None = None,
             profile_id: str | None = None, persist: bool = True) -> dict:
    gen = GENERATORS.get(report_type)
    if not gen:
        raise ValueError(f"unknown report_type {report_type!r} "
                         f"(expected one of {', '.join(sorted(GENERATORS))})")
    params = params or {}
    result = gen(client, facility_id, params)
    title = TITLES.get(report_type, report_type)
    meta = result["meta"]

    row = {
        "facility_id": facility_id, "report_type": report_type, "title": title,
        "period_start": meta.get("date_from") or meta.get("period_start"),
        "period_end": meta.get("date_to") or meta.get("period_end"),
        "format": "json", "params_json": params,
        "payload_json": result, "row_count": len(result["rows"]),
        "generated_by": profile_id,
    }
    if persist:
        # SQL: insert into reports
        #        (facility_id, report_type, title, period_start, period_end, format,
        #         params_json, payload_json, row_count, generated_by)
        #      values (:facility_id, :report_type, :title, :period_start, :period_end,
        #              'json', :params::jsonb, :payload::jsonb, :row_count, :profile_id)
        #      returning *
        row = client.table("reports").insert(row).execute().data[0]
    return {**row, "payload": result}


def to_csv(payload: dict) -> str:
    buf = io.StringIO()
    keys = [c["key"] for c in payload["columns"]]
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([c["label"] for c in payload["columns"]])
    for r in payload["rows"]:
        writer.writerow([r.get(k, "") for k in keys])
    return buf.getvalue()


def run_schedule(client, facility_id: str, schedule_id: str,
                 profile_id: str | None = None) -> dict:
    """Manual 'Generate Now' on a scheduled report - same code path the cron uses."""
    # SQL: select * from report_schedules
    #      where facility_id = :facility_id and id = :schedule_id
    rows = (client.table("report_schedules").select("*")
            .eq("facility_id", facility_id).eq("id", schedule_id).execute().data)
    if not rows:
        raise ValueError("report schedule not found")
    schedule = rows[0]
    report = generate(client, facility_id, schedule["report_type"], profile_id=profile_id)
    # SQL: update report_schedules set last_run_at = :today
    #      where id = :schedule_id
    #      returning *
    (client.table("report_schedules").update({"last_run_at": Date.today().isoformat()})
     .eq("id", schedule_id).execute())
    return report
