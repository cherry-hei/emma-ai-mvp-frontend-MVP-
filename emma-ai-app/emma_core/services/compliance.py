"""Staff-to-resident ratio checking.

Two methods, both required by the Code of Practice reporting (spec 3.6 / 3.7):

  compute_ratios   per-shift check — a staff member counts toward a window if
                   their shift overlaps it at all. Cheap, and what the
                   Compliance page's pass/fail cards show.
  minute_ratio     minute-level overlap — walks the window segment by segment and
                   counts only the minutes each person is actually on duty, so a
                   shift that covers half a statutory window can no longer pass
                   the whole window. This is the audit-grade number.

Rules come from staffing_ratio_rules; the denominator from daily_resident_counts.
"""
from __future__ import annotations

import math
from datetime import date as Date, timedelta

from ..models import RatioResult
from ..shifttime import covers_window, day_spans, duty_spans, to_minutes

CERT_WARN_DAYS = 90
AN_MONTHLY_LIMIT = 2          # facility policy: at most 2 AN shifts per staff per month
CL_ACCRUAL_LIMIT_HOURS = 20   # Employment Ordinance Cap.57 liability watch level
OCCUPANCY_FLOOR_PCT = 90      # below this, LSG subvention is affected
EXTERNAL_TYPES = {"local_pt", "agency", "outsource", "casual"}


def _mins(t: str | None) -> int | None:
    return to_minutes(t)


def _intervals(start: int, end: int) -> list[tuple[int, int]]:
    """Split a possibly cross-midnight window into same-day intervals."""
    return day_spans(start, end, end <= start)


def _requirement(rule: dict, residents: int) -> tuple[int, str]:
    w = f'{str(rule["time_window_start"])[:5]}–{str(rule["time_window_end"])[:5]}'
    if rule.get("ratio_residents_per_staff"):
        ratio = rule["ratio_residents_per_staff"]
        required = math.ceil(residents / ratio) if residents else 0
        return required, f'{rule.get("staff_rank") or "Any"} {w} (1:{ratio})'
    required = rule.get("min_staff_any_rank") or 0
    return required, f'Any rank {w} (min {required})'


def _load_rules(client, facility_id: str) -> list[dict]:
    # SQL: select * from staffing_ratio_rules
    #      where (facility_id = :facility_id or facility_id is null)  -- null = statutory
    #        and active = true
    return (client.table("staffing_ratio_rules").select("*")
            .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
            .eq("active", True).execute().data)


def _evaluate_day(rules: list[dict], residents: int, shift_by: dict[str, dict],
                  assigns: list[dict]) -> list[RatioResult]:
    results: list[RatioResult] = []
    for rule in rules:
        ws, we = _mins(rule["time_window_start"]), _mins(rule["time_window_end"])
        count = 0
        for a in assigns:
            sh = shift_by.get(a["shift_id"])
            # covers_window walks each duty segment, so a split A/N shift does not
            # count as present during its unpaid afternoon rest.
            if not sh or not covers_window(sh, ws, we):
                continue
            if rule.get("staff_rank") and a.get("role") != rule["staff_rank"]:
                continue
            count += 1
        required, label = _requirement(rule, residents)
        results.append(RatioResult(
            label=label, rank=rule.get("staff_rank"),
            window_start=str(rule["time_window_start"]), window_end=str(rule["time_window_end"]),
            residents=residents, required=required, actual=count, passes=count >= required,
        ))
    return results


def compute_ratios(client, facility_id: str, on_date, *,
                   roster_version_id: str | None = None) -> list[RatioResult]:
    """Ratio check for a single day. Pass ``roster_version_id`` to scope the count to one version — otherwise A/B/C drafts sharing the same dates double-count staff and falsely pass."""
    d = str(on_date)

    # SQL: select resident_count from daily_resident_counts
    #      where facility_id = :facility_id and date = :d
    # (summed in Python — one row per unit/care_level; `sum(resident_count)` in SQL
    #  would do the same)
    residents = sum(r["resident_count"] for r in (
        client.table("daily_resident_counts").select("resident_count")
        .eq("facility_id", facility_id).eq("date", d).execute().data))

    rules = _load_rules(client, facility_id)

    # SQL: select * from shifts
    #      where facility_id = :facility_id and date = :d and is_working = true
    #        [and roster_version_id = :roster_version_id]   -- when scoped to a version
    shifts_q = (client.table("shifts").select("*")
                .eq("facility_id", facility_id).eq("date", d).eq("is_working", True))
    if roster_version_id:
        shifts_q = shifts_q.eq("roster_version_id", roster_version_id)
    shifts = shifts_q.execute().data
    shift_by = {s["id"]: s for s in shifts}
    assigns = []
    if shift_by:
        # SQL: select shift_id, role, staff_id, status from shift_assignments
        #      where shift_id = any(:shift_ids)
        # (cancelled rows are dropped by the comprehension, not by the query)
        assigns = [a for a in (client.table("shift_assignments").select("shift_id,role,staff_id,status")
                               .in_("shift_id", list(shift_by)).execute().data)
                   if a.get("status") != "cancelled"]

    return _evaluate_day(rules, residents, shift_by, assigns)


# ── minute-level overlap (spec 3.6) ──────────────────────────────────────────
def _clip(interval: tuple[int, int], window: tuple[int, int]) -> tuple[int, int] | None:
    lo, hi = max(interval[0], window[0]), min(interval[1], window[1])
    return (lo, hi) if lo < hi else None


def _minute_eval(rules: list[dict], residents: int, shift_by: dict[str, dict],
                 assigns: list[dict], d: str) -> list[dict]:
    """Per-rule minute-level coverage for one day (pure — no DB access).

    Splits each statutory window into the segments where the on-duty headcount is
    constant, then reports how many minutes fall short of the requirement. A
    window only passes when *every* minute in it is covered.
    """
    out: list[dict] = []
    for rule in rules:
        required, label = _requirement(rule, residents)
        rank = rule.get("staff_rank")
        windows = _intervals(_mins(rule["time_window_start"]), _mins(rule["time_window_end"]))

        # on-duty intervals of every staff member the rule counts — duty_spans
        # expands a split shift into its separate windows
        duty: list[tuple[int, int]] = []
        for a in assigns:
            sh = shift_by.get(a["shift_id"])
            if not sh:
                continue
            if rank and a.get("role") != rank:
                continue
            duty.extend(duty_spans(sh))

        segments, breach_minutes, window_minutes = [], 0, 0
        min_actual = None
        for w in windows:
            window_minutes += w[1] - w[0]
            clipped = [c for c in (_clip(i, w) for i in duty) if c]
            points = sorted({w[0], w[1], *(p for c in clipped for p in c)})
            for lo, hi in zip(points, points[1:]):
                actual = sum(1 for c in clipped if c[0] <= lo and c[1] >= hi)
                ok = actual >= required
                if not ok:
                    breach_minutes += hi - lo
                min_actual = actual if min_actual is None else min(min_actual, actual)
                segments.append({
                    "start": f"{lo // 60:02d}:{lo % 60:02d}",
                    "end": f"{hi // 60:02d}:{hi % 60:02d}",
                    "minutes": hi - lo, "actual": actual, "required": required, "passes": ok,
                })

        out.append({
            "date": d, "label": label, "rank": rank,
            "window_start": str(rule["time_window_start"])[:5],
            "window_end": str(rule["time_window_end"])[:5],
            "residents": residents, "required": required,
            "min_actual": min_actual or 0,
            "window_minutes": window_minutes, "breach_minutes": breach_minutes,
            "passes": breach_minutes == 0,
            "segments": segments,
        })
    return out


def minute_ratio(client, facility_id: str, on_date, *,
                 roster_version_id: str | None = None) -> list[dict]:
    """Minute-level coverage for a single day."""
    d = str(on_date)
    # Same three reads as compute_ratios — only the evaluation differs (minute-level
    # rather than per-shift), so the SQL is identical.
    #
    # SQL: select resident_count from daily_resident_counts
    #      where facility_id = :facility_id and date = :d
    residents = sum(r["resident_count"] for r in (
        client.table("daily_resident_counts").select("resident_count")
        .eq("facility_id", facility_id).eq("date", d).execute().data))
    rules = _load_rules(client, facility_id)

    # SQL: select * from shifts
    #      where facility_id = :facility_id and date = :d and is_working = true
    #        [and roster_version_id = :roster_version_id]   -- when scoped to a version
    shifts_q = (client.table("shifts").select("*")
                .eq("facility_id", facility_id).eq("date", d).eq("is_working", True))
    if roster_version_id:
        shifts_q = shifts_q.eq("roster_version_id", roster_version_id)
    shift_by = {s["id"]: s for s in shifts_q.execute().data}
    assigns = []
    if shift_by:
        # SQL: select shift_id, role, staff_id, status from shift_assignments
        #      where shift_id = any(:shift_ids)
        assigns = [a for a in (client.table("shift_assignments")
                               .select("shift_id,role,staff_id,status")
                               .in_("shift_id", list(shift_by)).execute().data)
                   if a.get("status") != "cancelled"]
    return _minute_eval(rules, residents, shift_by, assigns, d)


def minute_ratio_series(client, facility_id: str, start: Date, end: Date, *,
                        roster_version_id: str | None = None) -> list[dict]:
    """Minute-level coverage across a range, in a fixed number of queries — the
    breach-minute source for the SWD compliance KPI and the statutory report."""
    rules = _load_rules(client, facility_id)
    if not rules:
        return []
    residents_by_date, shift_by, by_date = _load_range(
        client, facility_id, start, end, roster_version_id)

    out = []
    day = start
    while day <= end:
        key = day.isoformat()
        day_assigns = by_date.get(key, [])
        day_shifts = {a["shift_id"]: shift_by[a["shift_id"]] for a in day_assigns}
        out.extend(_minute_eval(rules, residents_by_date.get(key, 0),
                                day_shifts, day_assigns, key))
        day += timedelta(days=1)
    return out


# ── day-by-day series (dashboard compliance rate, reports, KPI) ──────────────
def _load_range(client, facility_id: str, start: Date, end: Date,
                roster_version_id: str | None):
    """(residents_by_date, shift_by_id, assignments_by_date) for a date range."""
    # Three queries for the whole range, then bucketed by date in Python — this is
    # what keeps ratio_series / minute_ratio_series off a per-day query loop.
    #
    # SQL: select date, resident_count from daily_resident_counts
    #      where facility_id = :facility_id and date >= :start and date <= :end
    # (in SQL the per-date rollup would be `group by date` with `sum(resident_count)`)
    residents_by_date: dict[str, int] = {}
    for r in (client.table("daily_resident_counts").select("date,resident_count")
              .eq("facility_id", facility_id)
              .gte("date", str(start)).lte("date", str(end)).execute().data):
        key = str(r["date"])[:10]
        residents_by_date[key] = residents_by_date.get(key, 0) + r["resident_count"]

    # SQL: select * from shifts
    #      where facility_id = :facility_id and is_working = true
    #        and date >= :start and date <= :end
    #        [and roster_version_id = :roster_version_id]   -- when scoped to a version
    shifts_q = (client.table("shifts").select("*")
                .eq("facility_id", facility_id).eq("is_working", True)
                .gte("date", str(start)).lte("date", str(end)))
    if roster_version_id:
        shifts_q = shifts_q.eq("roster_version_id", roster_version_id)
    shift_by = {s["id"]: s for s in shifts_q.execute().data}

    assigns = []
    if shift_by:
        # SQL: select shift_id, role, staff_id, status from shift_assignments
        #      where shift_id = any(:shift_ids)
        assigns = [a for a in (client.table("shift_assignments")
                               .select("shift_id,role,staff_id,status")
                               .in_("shift_id", list(shift_by)).execute().data)
                   if a.get("status") != "cancelled"]
    by_date: dict[str, list[dict]] = {}
    for a in assigns:
        sh = shift_by.get(a["shift_id"])
        if sh:
            by_date.setdefault(str(sh["date"])[:10], []).append(a)
    return residents_by_date, shift_by, by_date



def ratio_series(client, facility_id: str, start: Date, end: Date, *,
                 roster_version_id: str | None = None) -> list[dict]:
    """Pass/fail per day across a range, in a fixed number of queries."""
    rules = _load_rules(client, facility_id)
    if not rules:
        return []
    residents_by_date, shift_by, by_date = _load_range(
        client, facility_id, start, end, roster_version_id)

    out = []
    day = start
    while day <= end:
        key = day.isoformat()
        day_assigns = by_date.get(key, [])
        day_shifts = {a["shift_id"]: shift_by[a["shift_id"]] for a in day_assigns}
        checks = _evaluate_day(rules, residents_by_date.get(key, 0), day_shifts, day_assigns)
        failed = [c for c in checks if not c.passes]
        out.append({
            "date": key, "checks": len(checks), "passed": len(checks) - len(failed),
            "failed": len(failed), "failing_labels": [c.label for c in failed],
            "pass_rate": round((len(checks) - len(failed)) / len(checks) * 100) if checks else 0,
        })
        day += timedelta(days=1)
    return out


# ── live threshold monitors (Reports page) ───────────────────────────────────
# The escalation wording and legal references below are regulation, not facility
# data — they stay in code. Every *number* is measured from the database.
def threshold_monitors(client, facility_id: str) -> list[dict]:
    from ._common import as_date, month_bounds, operative_version, resolve_period

    today = Date.today()
    month_start, month_end = month_bounds(today)
    period = resolve_period(client, facility_id, None)
    version = operative_version(client, facility_id, period["id"]) if period else None

    monitors: list[dict] = []

    # 1 · certificate / licence expiry ---------------------------------------
    # SQL: select c.staff_id, c.cert_type, c.expiry_date,
    #             jsonb_build_object('name', s.name, 'name_en', s.name_en) as staff
    #      from staff_certificates c
    #      left join staff s on s.id = c.staff_id
    #      where c.facility_id = :facility_id and c.expiry_date is not null
    #      order by c.expiry_date
    certs = (client.table("staff_certificates")
             .select("staff_id,cert_type,expiry_date, staff:staff(name,name_en)")
             .eq("facility_id", facility_id).not_.is_("expiry_date", "null")
             .order("expiry_date").execute().data)
    soon = [(c, (as_date(c["expiry_date"]) - today).days) for c in certs
            if (as_date(c["expiry_date"]) - today).days <= CERT_WARN_DAYS]
    urgent = [c for c, days in soon if days <= 7]
    detail = ", ".join(
        f'{((c.get("staff") or {}).get("name_en") or (c.get("staff") or {}).get("name"))}: '
        f'{days}d' for c, days in soon[:3])
    monitors.append({
        "code": "CERT_EXPIRY", "icon": "📜",
        "name_en": "Licence Expiry Alert", "name_zh": "執照到期警示",
        "condition_en": f"Certificate expiry ≤ {CERT_WARN_DAYS} days",
        "condition_zh": f"執照到期 ≤ {CERT_WARN_DAYS}天",
        "severity": "over" if urgent else ("warn" if soon else "ok"),
        "current_count": len(soon),
        "note_en": (f"{len(soon)} staff require follow-up ({detail})" if soon
                    else "No certificate expiring in the next 90 days ✓"),
        "note_zh": (f"{len(soon)} 人需跟進（{detail}）" if soon else "未來 90 天無證書到期 ✓"),
        "levels": [
            {"days": 90, "label_en": "🟡 Reminder", "label_zh": "🟡 提醒",
             "action_en": "Send reminder to staff and Home Manager",
             "action_zh": "發送提醒至員工及院長"},
            {"days": 30, "label_en": "🟠 Warning", "label_zh": "🟠 警告",
             "action_en": "Send warning + escalate to Assistant Home Manager",
             "action_zh": "發送警告 + 上報助理院長"},
            {"days": 7, "label_en": "🔴 Urgent", "label_zh": "🔴 緊急",
             "action_en": "Emergency alert + suspend assignment to that shift",
             "action_zh": "緊急通知 + 暫緩排入該更"},
        ],
        "law_en": "SWD Registration", "law_zh": "社署註冊",
    })

    # roster-derived monitors need the operative version -----------------------
    day_rows: list[dict] = []
    if version:
        # SQL: select * from shifts
        #      where roster_version_id = :version_id and is_working = true
        #        and date >= :month_start and date <= :month_end
        shifts = (client.table("shifts").select("*")
                  .eq("roster_version_id", version["id"]).eq("is_working", True)
                  .gte("date", month_start).lte("date", month_end).execute().data)
        by_id = {s["id"]: s for s in shifts}
        if by_id:
            # SQL: select shift_id, staff_id, role, is_agency, status
            #      from shift_assignments
            #      where shift_id = any(:shift_ids)
            assigns = (client.table("shift_assignments")
                       .select("shift_id,staff_id,role,is_agency,status")
                       .in_("shift_id", list(by_id)).execute().data)
            # SQL: select id, employment_type, gender, name, name_en from staff
            #      where facility_id = :facility_id
            staff_rows = {s["id"]: s for s in (
                client.table("staff").select("id,employment_type,gender,name,name_en")
                .eq("facility_id", facility_id).execute().data)}
            for a in assigns:
                if a.get("status") == "cancelled" or not a.get("staff_id"):
                    continue
                sh = by_id[a["shift_id"]]
                day_rows.append({
                    "date": str(sh["date"])[:10], "shift_type": sh["shift_type"],
                    "staff_id": a["staff_id"], "role": a.get("role"),
                    "employment_type": (staff_rows.get(a["staff_id"]) or {}).get("employment_type"),
                    "is_agency": bool(a.get("is_agency")),
                })

    # 2 · part-time / external ratio -----------------------------------------
    per_slot: dict[tuple[str, str], list[dict]] = {}
    for r in day_rows:
        per_slot.setdefault((r["date"], r["shift_type"]), []).append(r)
    pt_breaches = []
    for (d, stype), rows in per_slot.items():
        if stype not in ("A", "P", "7A", "9A"):     # specific-hour day shifts only
            continue
        external = [r for r in rows if r["employment_type"] in EXTERNAL_TYPES or r["is_agency"]]
        if external and len(external) > len(rows) // 2:
            pt_breaches.append(f"{d} {stype}")
    monitors.append({
        "code": "PT_RATIO", "icon": "🛡️",
        "name_en": "PT Ratio Overage Block", "name_zh": "PT比例超標攔截",
        "condition_en": "Specific-hour PT headcount > floor(total × 50%)",
        "condition_zh": "特定鐘點PT人數 > floor(總數×50%)",
        "severity": "over" if pt_breaches else "ok",
        "current_count": len(pt_breaches),
        "note_en": (f"{len(pt_breaches)} A/P shifts over the PT cap: "
                    + ", ".join(pt_breaches[:3]) if pt_breaches
                    else "No triggers this month — A/P shifts within limit ✓"),
        "note_zh": (f"{len(pt_breaches)} 個 A/P 更超出 PT 上限" if pt_breaches
                    else "本月未觸發 — A/P更均在上限內 ✓"),
        "levels": [{"label_en": "🔴 Immediate Block", "label_zh": "🔴 即時阻截",
                    "action_en": "Block roster confirmation + show Cap.459A s.11(3)",
                    "action_zh": "阻止排班確認 + 顯示 Cap.459A s.11(3)"}],
        "law_en": "Cap.459A s.11(3)", "law_zh": "Cap.459A s.11(3)",
    })

    # 3 · AN shifts per staff per month ---------------------------------------
    an_counts: dict[str, int] = {}
    for r in day_rows:
        if r["shift_type"] == "AN":
            an_counts[r["staff_id"]] = an_counts.get(r["staff_id"], 0) + 1
    over_an = {k: v for k, v in an_counts.items() if v > AN_MONTHLY_LIMIT}
    monitors.append({
        "code": "AN_LIMIT", "icon": "🌙",
        "name_en": "AN Shift Over-limit Block", "name_zh": "AN更超限阻截",
        "condition_en": f"AN shifts per staff per month > {AN_MONTHLY_LIMIT}",
        "condition_zh": f"每人每月AN更數 > {AN_MONTHLY_LIMIT}次",
        "severity": "over" if over_an else "ok",
        "current_count": len(over_an),
        "note_en": (f"{len(over_an)} staff exceeded {AN_MONTHLY_LIMIT} AN shifts this month"
                    if over_an else f"No staff over {AN_MONTHLY_LIMIT} AN shifts ✓"),
        "note_zh": (f"{len(over_an)} 名員工超出 {AN_MONTHLY_LIMIT} 次AN更"
                    if over_an else f"無員工超出 {AN_MONTHLY_LIMIT} 次AN更 ✓"),
        "levels": [{"label_en": "🔴 Block 3rd AN", "label_zh": "🔴 阻截第3次",
                    "action_en": "Block adding a 3rd AN shift + log to compliance journal",
                    "action_zh": "阻止加入第3次AN更 + 記錄至合規日誌"}],
        "law_en": "Internal Home Policy", "law_zh": "院舍內部規定",
    })

    # 4 · shifts with no RN on duty -------------------------------------------
    rn_gap: dict[str, int] = {}
    for (d, stype), rows in per_slot.items():
        if not any(r["role"] == "RN" for r in rows):
            rn_gap[stype] = rn_gap.get(stype, 0) + 1
    total_rn_gap = sum(rn_gap.values())
    breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(rn_gap.items()))
    monitors.append({
        "code": "RN_ABSENT", "icon": "🏥",
        "name_en": "RN-Absent Shift Emergency Alert", "name_zh": "RN空更緊急通知",
        "condition_en": "FT RN = 0 in any working shift",
        "condition_zh": "任何更次 FT RN = 0",
        "severity": "over" if total_rn_gap else "ok",
        "current_count": total_rn_gap,
        "note_en": (f"{total_rn_gap} shifts this month without an RN ({breakdown})"
                    if total_rn_gap else "Every shift has RN cover this month ✓"),
        "note_zh": (f"本月 {total_rn_gap} 個更次無RN（{breakdown}）"
                    if total_rn_gap else "本月每更均有RN當值 ✓"),
        "levels": [{"label_en": "🔴 Immediate Alert", "label_zh": "🔴 即時警告",
                    "action_en": "Notify Home Manager + start standby RN contact process",
                    "action_zh": "即時警告院長 + 自動啟動後備RN聯絡流程"}],
        "law_en": "Cap.459A s.11(1)", "law_zh": "Cap.459A s.11(1)",
    })

    # 5 · CL / TOIL accrual ----------------------------------------------------
    # SQL: select staff_id, debt_type, quantity from future_debt_ledger
    #      where facility_id = :facility_id and status = 'open'
    # (the CL/CO/TOIL/OT filter and per-staff sum happen in Python below)
    debts = (client.table("future_debt_ledger").select("staff_id,debt_type,quantity")
             .eq("facility_id", facility_id).eq("status", "open").execute().data)
    per_staff: dict[str, float] = {}
    for d in debts:
        if d["debt_type"] in ("CL", "CO", "TOIL", "OT"):
            per_staff[d["staff_id"]] = per_staff.get(d["staff_id"], 0.0) + float(d["quantity"])
    total_cl = round(sum(per_staff.values()), 1)
    over_cl = [k for k, v in per_staff.items() if v > CL_ACCRUAL_LIMIT_HOURS]
    monitors.append({
        "code": "CL_ACCRUAL", "icon": "⏰",
        "name_en": "CL Accrual Over-limit Reminder", "name_zh": "CL積壓超限提醒",
        "condition_en": f"CL accrual per staff > {CL_ACCRUAL_LIMIT_HOURS}h",
        "condition_zh": f"每人CL積壓 > {CL_ACCRUAL_LIMIT_HOURS}h",
        "severity": "warn" if over_cl else ("warn" if total_cl else "ok"),
        "current_count": len(over_cl),
        "note_en": f"{total_cl}h open across the home · {len(over_cl)} staff over limit",
        "note_zh": f"全院積壓 {total_cl}h · {len(over_cl)} 人超出上限",
        "levels": [{"label_en": "🟠 Warning", "label_zh": "🟠 警告",
                    "action_en": "Prioritise compensatory rest next cycle + update liability report",
                    "action_zh": "列入下月更表優先補休 + 財務負債月報更新"}],
        "law_en": "Employment Ordinance Cap.57", "law_zh": "僱傭條例 Cap.57",
    })

    # 6 · occupancy ------------------------------------------------------------
    # SQL: select capacity from facilities where id = :facility_id
    facility = (client.table("facilities").select("capacity")
                .eq("id", facility_id).execute().data)
    capacity = (facility[0].get("capacity") if facility else None) or 0
    # SQL: select date, resident_count from daily_resident_counts
    #      where facility_id = :facility_id and date <= :today
    #      order by date desc
    #      limit 50
    # 50 rows, not 1: the newest date can have several unit/care_level rows and they
    # all have to be summed. The limit assumes < 50 rows per day.
    latest = (client.table("daily_resident_counts").select("date,resident_count")
              .eq("facility_id", facility_id).lte("date", today.isoformat())
              .order("date", desc=True).limit(50).execute().data)
    latest_date = str(latest[0]["date"])[:10] if latest else None
    occupied = sum(r["resident_count"] for r in latest if str(r["date"])[:10] == latest_date)
    pct = round(occupied / capacity * 100) if capacity else 0
    monitors.append({
        "code": "OCCUPANCY", "icon": "🏠",
        "name_en": "Occupancy Below 90% Reminder", "name_zh": "入住率低於90%提醒",
        "condition_en": f"Occupancy rate < {OCCUPANCY_FLOOR_PCT}%",
        "condition_zh": f"入住率 < {OCCUPANCY_FLOOR_PCT}%",
        "severity": "warn" if capacity and pct < OCCUPANCY_FLOOR_PCT else "ok",
        "current_count": 1 if capacity and pct < OCCUPANCY_FLOOR_PCT else 0,
        "note_en": (f"Current occupancy {pct}% ({occupied}/{capacity})" if capacity
                    else "Facility capacity not configured"),
        "note_zh": (f"現時入住率 {pct}% ({occupied}/{capacity})" if capacity
                    else "未設定院舍宿位總數"),
        "levels": [{"label_en": "🟡 Reminder", "label_zh": "🟡 提醒",
                    "action_en": "Occupancy affects government subvention calculation",
                    "action_zh": "提示入住率影響政府撥款計算"}],
        "law_en": "LSG Subvention Rules", "law_zh": "LSG撥款規定",
    })

    return monitors
