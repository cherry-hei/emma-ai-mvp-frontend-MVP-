"""Staff-to-resident ratio checking.

Two methods, both required by the Code of Practice reporting (spec 3.6 / 3.7):

  compute_ratios   per-shift check - a staff member counts toward a window if
                   their shift overlaps it at all. Cheap, and what the
                   Compliance page's pass/fail cards show.
  minute_ratio     minute-level overlap - walks the window segment by segment and
                   counts only the minutes each person is actually on duty, so a
                   shift that covers half a statutory window can no longer pass
                   the whole window. This is the audit-grade number.

Rules come from staffing_ratio_rules; the denominator from daily_resident_counts.
"""
from __future__ import annotations

import json
import math
from datetime import date as Date, timedelta

from ..models import RatioResult
from ..shifttime import covers_window, day_spans, duty_spans, to_minutes
from ._common import assignments_for_shifts

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


def _as_date(value) -> Date | None:
    if value is None or value == "":
        return None
    if isinstance(value, Date):
        return value
    return Date.fromisoformat(str(value)[:10])


def _json_value(value, expected_type, default):
    if isinstance(value, expected_type):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return default
        return parsed if isinstance(parsed, expected_type) else default
    return default


def _same_id(left, right) -> bool:
    return str(left) == str(right)


def _resident_total(residents: int | list[dict], rule: dict) -> int:
    """Resolve one rule's denominator from an aggregate or per-unit rows."""
    if isinstance(residents, (int, float)):
        return max(0, int(residents))

    unit_id = rule.get("unit_id")
    care_level = rule.get("care_level")
    total = 0
    for row in residents or []:
        if unit_id is not None and not _same_id(row.get("unit_id"), unit_id):
            continue
        if care_level and row.get("care_level") != care_level:
            continue
        try:
            total += int(row.get("resident_count") or 0)
        except (TypeError, ValueError):
            continue
    return max(0, total)


def _rank_config(rule: dict) -> tuple[set[str] | None, dict[str, float]]:
    """Return counted ranks and their equivalent-head weights.

    Phase 5 JSON configuration takes precedence. Empty JSON retains the legacy
    exact ``staff_rank`` behaviour; a rule with no rank remains any-rank.
    """
    counted_raw = _json_value(rule.get("counted_ranks_json"), list, [])
    weights_raw = _json_value(rule.get("rank_weights_json"), dict, {})
    counted = {str(rank) for rank in counted_raw if rank not in (None, "")}

    weights: dict[str, float] = {}
    for rank, value in weights_raw.items():
        if isinstance(value, bool):
            raise ValueError(
                f"invalid staffing ratio weight for {rank}: expected a number"
            )
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"invalid staffing ratio weight for {rank}: expected a number"
            ) from None
        if not math.isfinite(parsed) or parsed < 0:
            raise ValueError(
                f"invalid staffing ratio weight for {rank}: "
                "expected a finite non-negative number"
            )
        weights[str(rank)] = parsed

    if not counted and weights:
        counted = set(weights)
    if not counted and rule.get("staff_rank"):
        counted = {str(rule["staff_rank"])}
    return (counted or None), weights


def _rank_label(rule: dict) -> str:
    counted, _weights = _rank_config(rule)
    return "/".join(sorted(counted)) if counted else "Any"


def _requirement(rule: dict, residents: int | list[dict]) -> tuple[int | float, str]:
    resident_total = _resident_total(residents, rule)
    w = f'{str(rule["time_window_start"])[:5]}–{str(rule["time_window_end"])[:5]}'
    ratio_value = rule.get("ratio_residents_per_staff")
    if ratio_value is not None:
        try:
            ratio = int(ratio_value)
            is_integral = float(ratio_value) == ratio
        except (TypeError, ValueError):
            raise ValueError(
                "ratio_residents_per_staff must be a positive integer"
            ) from None
        if isinstance(ratio_value, bool) or not is_integral or ratio <= 0:
            raise ValueError(
                "ratio_residents_per_staff must be a positive integer"
            )
        # Compare equivalent-head capacity before rounding. Integer headcounts
        # still behave exactly like ceil(residents / ratio), while fractional
        # substitutions remain correct (for example Home B: one HW carries
        # 40/60 of the RN/EN 1:60 capacity).
        required = resident_total / ratio if resident_total else 0
        return required, f'{_rank_label(rule)} {w} (1:{ratio})'
    try:
        required = int(rule.get("min_staff_any_rank") or 0)
        is_integral = float(rule.get("min_staff_any_rank") or 0) == required
    except (TypeError, ValueError):
        raise ValueError(
            "min_staff_any_rank must be a non-negative integer"
        ) from None
    if (
        isinstance(rule.get("min_staff_any_rank"), bool)
        or not is_integral
        or required < 0
    ):
        raise ValueError("min_staff_any_rank must be a non-negative integer")
    return required, f'{_rank_label(rule)} {w} (min {required})'


def _rule_identity(rule: dict) -> tuple:
    """Identity shared by versions and facility overrides of one rule."""
    code = str(rule.get("rule_code") or "").strip()
    if code and code != "swd_staffing_ratio":
        return ("code", code)
    # Existing rows receive one generic migration default. Keep their original
    # dimensions in the identity so separate statutory windows are not collapsed.
    return (
        "legacy",
        rule.get("facility_type"),
        rule.get("care_level"),
        str(rule.get("unit_id") or ""),
        str(rule.get("staff_rank") or ""),
        str(rule.get("time_window_start") or "")[:5],
        str(rule.get("time_window_end") or "")[:5],
    )


def _version_key(item: tuple[int, dict]) -> tuple:
    index, rule = item
    try:
        version = int(rule.get("config_version") or 1)
    except (TypeError, ValueError):
        version = 1
    effective = _as_date(rule.get("effective_from")) or Date.min
    return version, effective, str(rule.get("created_at") or ""), -index


def _infer_facility_id(rules: list[dict]) -> str | None:
    values = {str(rule["facility_id"]) for rule in rules if rule.get("facility_id")}
    return next(iter(values)) if len(values) == 1 else None


def _effective_rules(
    rules: list[dict],
    facility_id: str | None,
    on_date,
) -> list[dict]:
    """Select active/effective versions with facility-over-global precedence."""
    day = _as_date(on_date) or Date.today()
    facility_id = str(facility_id) if facility_id else _infer_facility_id(rules)
    grouped: dict[tuple, list[tuple[int, dict]]] = {}

    for index, rule in enumerate(rules):
        if not rule.get("active", True):
            continue
        row_facility = str(rule["facility_id"]) if rule.get("facility_id") else None
        if facility_id and row_facility not in (None, facility_id):
            continue
        effective_from = _as_date(rule.get("effective_from"))
        effective_to = _as_date(rule.get("effective_to"))
        if effective_from and day < effective_from:
            continue
        if effective_to and day > effective_to:
            continue
        grouped.setdefault(_rule_identity(rule), []).append((index, rule))

    selected: list[tuple[int, dict]] = []
    for candidates in grouped.values():
        facility_rows = [
            item for item in candidates
            if facility_id and _same_id(item[1].get("facility_id"), facility_id)
        ]
        pool = facility_rows or [
            item for item in candidates if item[1].get("facility_id") is None
        ]
        if not pool:
            # Pure callers may not provide a target facility. Preserve their
            # deterministic version choice instead of mixing several versions.
            pool = candidates
        winner = max(pool, key=_version_key)
        selected.append((min(item[0] for item in candidates), winner[1]))

    return [rule for _index, rule in sorted(selected, key=lambda item: item[0])]


def _load_rule_rows(client, facility_id: str) -> list[dict]:
    # SQL: select * from staffing_ratio_rules
    #      where (facility_id = :facility_id or facility_id is null)  -- null = statutory
    #        and active = true
    return (client.table("staffing_ratio_rules").select("*")
            .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
            .eq("active", True).execute().data)


def _load_rules(client, facility_id: str, on_date=None) -> list[dict]:
    return _effective_rules(
        _load_rule_rows(client, facility_id), facility_id, on_date or Date.today())


def _assignment_weight(rule: dict, assignment: dict, shift: dict) -> float | None:
    if assignment.get("status") == "cancelled":
        return None
    unit_id = rule.get("unit_id")
    if unit_id is not None and not _same_id(shift.get("unit_id"), unit_id):
        return None

    counted, weights = _rank_config(rule)
    role = str(assignment.get("role") or "")
    if counted is not None and role not in counted:
        return None
    weight = weights.get(role, 1.0)
    return weight if weight > 0 else None


def _assignment_identity(assignment: dict, fallback: int) -> str:
    if assignment.get("staff_id"):
        return f'staff:{assignment["staff_id"]}'
    # Synthetic agency rows have no staff_id; assignment id is their stable
    # person-equivalent. The final fallback keeps old pure fixtures usable.
    marker = assignment.get("id") or f'{assignment.get("shift_id")}:{fallback}'
    return f"agency:{marker}"


def _weighted_window_count(
    rule: dict,
    shift_by: dict[str, dict],
    assigns: list[dict],
    window_start: int,
    window_end: int,
) -> float:
    weights_by_person: dict[str, float] = {}
    for index, assignment in enumerate(assigns):
        shift = shift_by.get(assignment.get("shift_id"))
        if not shift or not covers_window(shift, window_start, window_end):
            continue
        weight = _assignment_weight(rule, assignment, shift)
        if weight is None:
            continue
        identity = _assignment_identity(assignment, index)
        weights_by_person[identity] = max(weights_by_person.get(identity, 0.0), weight)
    return sum(weights_by_person.values())


def _display_number(value: float) -> int | float:
    if math.isclose(value, round(value), abs_tol=1e-9):
        return int(round(value))
    return round(value, 3)


def _evaluate_day(
    rules: list[dict],
    residents: int | list[dict],
    shift_by: dict[str, dict],
    assigns: list[dict],
    *,
    facility_id: str | None = None,
    on_date=None,
) -> list[RatioResult]:
    if on_date is not None:
        rules = _effective_rules(rules, facility_id, on_date)
    results: list[RatioResult] = []
    for rule in rules:
        ws, we = _mins(rule["time_window_start"]), _mins(rule["time_window_end"])
        weighted_count = _weighted_window_count(rule, shift_by, assigns, ws, we)
        resident_total = _resident_total(residents, rule)
        required, label = _requirement(rule, residents)
        results.append(RatioResult(
            label=label, rank=rule.get("staff_rank"),
            window_start=str(rule["time_window_start"]), window_end=str(rule["time_window_end"]),
            residents=resident_total, required=_display_number(required),
            actual=_display_number(weighted_count),
            passes=weighted_count + 1e-9 >= required,
        ))
    return results


def compute_ratios(client, facility_id: str, on_date, *,
                   roster_version_id: str | None = None) -> list[RatioResult]:
    """Ratio check for a single day. Pass ``roster_version_id`` to scope the count to one version - otherwise A/B/C drafts sharing the same dates double-count staff and falsely pass."""
    d = str(on_date)

    # SQL: select unit_id, care_level, resident_count from daily_resident_counts
    #      where facility_id = :facility_id and date = :d
    # Rows stay disaggregated so a unit/care-level rule gets its own denominator.
    residents = (
        client.table("daily_resident_counts")
        .select("unit_id,care_level,resident_count")
        .eq("facility_id", facility_id).eq("date", d).execute().data
    )

    rules = _load_rules(client, facility_id, d)

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
        # SQL: select id, shift_id, role, staff_id, is_agency, status
        #      from shift_assignments
        #      where shift_id = any(:shift_ids)
        # (cancelled rows are dropped by the comprehension, not by the query)
        assigns = [a for a in assignments_for_shifts(
            client, shift_by, select="id,shift_id,role,staff_id,is_agency,status")
            if a.get("status") != "cancelled"]

    return _evaluate_day(
        rules, residents, shift_by, assigns, facility_id=facility_id, on_date=d)


# ── minute-level overlap (spec 3.6) ──────────────────────────────────────────
def _clip(interval: tuple[int, int], window: tuple[int, int]) -> tuple[int, int] | None:
    lo, hi = max(interval[0], window[0]), min(interval[1], window[1])
    return (lo, hi) if lo < hi else None


def _minute_eval(
    rules: list[dict],
    residents: int | list[dict],
    shift_by: dict[str, dict],
    assigns: list[dict],
    d: str,
    *,
    facility_id: str | None = None,
) -> list[dict]:
    """Per-rule minute-level coverage for one day (pure - no DB access).

    Splits each statutory window where the weighted on-duty headcount is
    constant. The same person is counted once even if duplicate/overlapping
    assignments exist; distinct synthetic agency assignments count separately.
    """
    rules = _effective_rules(rules, facility_id, d)
    out: list[dict] = []
    for rule in rules:
        required, label = _requirement(rule, residents)
        resident_total = _resident_total(residents, rule)
        rank = rule.get("staff_rank")
        windows = _intervals(_mins(rule["time_window_start"]), _mins(rule["time_window_end"]))

        # duty_spans expands a split shift into its separate windows. Identity
        # remains attached so duplicate assignments cannot inflate coverage.
        duty: list[tuple[str, float, int, int]] = []
        for index, assignment in enumerate(assigns):
            shift = shift_by.get(assignment.get("shift_id"))
            if not shift:
                continue
            weight = _assignment_weight(rule, assignment, shift)
            if weight is None:
                continue
            identity = _assignment_identity(assignment, index)
            duty.extend(
                (identity, weight, start, end)
                for start, end in duty_spans(shift)
            )

        segments, breach_minutes, window_minutes = [], 0, 0
        min_actual: float | None = None
        for w in windows:
            window_minutes += w[1] - w[0]
            clipped: list[tuple[str, float, int, int]] = []
            for identity, weight, start, end in duty:
                interval = _clip((start, end), w)
                if interval:
                    clipped.append((identity, weight, interval[0], interval[1]))
            points = sorted({
                w[0], w[1],
                *(point for _identity, _weight, start, end in clipped
                  for point in (start, end)),
            })
            for lo, hi in zip(points, points[1:]):
                active: dict[str, float] = {}
                for identity, weight, start, end in clipped:
                    if start <= lo and end >= hi:
                        active[identity] = max(active.get(identity, 0.0), weight)
                actual = sum(active.values())
                ok = actual + 1e-9 >= required
                if not ok:
                    breach_minutes += hi - lo
                min_actual = actual if min_actual is None else min(min_actual, actual)
                segments.append({
                    "start": f"{lo // 60:02d}:{lo % 60:02d}",
                    "end": f"{hi // 60:02d}:{hi % 60:02d}",
                    "minutes": hi - lo,
                    "actual": _display_number(actual),
                    "required": _display_number(required),
                    "passes": ok,
                })

        out.append({
            "date": d,
            "rule_id": rule.get("id"),
            "rule_code": rule.get("rule_code"),
            "config_version": int(rule.get("config_version") or 1),
            "label": label,
            "rank": rank,
            "unit_id": rule.get("unit_id"),
            "window_start": str(rule["time_window_start"])[:5],
            "window_end": str(rule["time_window_end"])[:5],
            "residents": resident_total,
            "required": _display_number(required),
            "min_actual": _display_number(min_actual or 0),
            "window_minutes": window_minutes,
            "breach_minutes": breach_minutes,
            "passes": breach_minutes == 0,
            "segments": segments,
        })
    return out


def minute_ratio(client, facility_id: str, on_date, *,
                 roster_version_id: str | None = None) -> list[dict]:
    """Minute-level coverage for a single day."""
    d = str(on_date)
    # Same three reads as compute_ratios - only the evaluation differs (minute-level
    # rather than per-shift), so the SQL is identical.
    #
    # SQL: select unit_id, care_level, resident_count from daily_resident_counts
    #      where facility_id = :facility_id and date = :d
    residents = (
        client.table("daily_resident_counts")
        .select("unit_id,care_level,resident_count")
        .eq("facility_id", facility_id).eq("date", d).execute().data
    )
    rules = _load_rules(client, facility_id, d)

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
        # SQL: select id, shift_id, role, staff_id, is_agency, status
        #      from shift_assignments
        #      where shift_id = any(:shift_ids)
        assigns = [a for a in assignments_for_shifts(
            client, shift_by, select="id,shift_id,role,staff_id,is_agency,status")
            if a.get("status") != "cancelled"]
    return _minute_eval(
        rules, residents, shift_by, assigns, d, facility_id=facility_id)


def minute_ratio_series(client, facility_id: str, start: Date, end: Date, *,
                        roster_version_id: str | None = None) -> list[dict]:
    """Minute-level coverage across a range, in a fixed number of queries - the
    breach-minute source for the SWD compliance KPI and the statutory report."""
    rule_rows = _load_rule_rows(client, facility_id)
    if not rule_rows:
        return []
    residents_by_date, shift_by, by_date = _load_range(
        client, facility_id, start, end, roster_version_id)

    out = []
    day = start
    while day <= end:
        key = day.isoformat()
        day_assigns = by_date.get(key, [])
        day_shifts = {a["shift_id"]: shift_by[a["shift_id"]] for a in day_assigns}
        out.extend(_minute_eval(
            rule_rows,
            residents_by_date.get(key, []),
            day_shifts,
            day_assigns,
            key,
            facility_id=facility_id,
        ))
        day += timedelta(days=1)
    return out


# ── day-by-day series (dashboard compliance rate, reports, KPI) ──────────────
def _load_range(client, facility_id: str, start: Date, end: Date,
                roster_version_id: str | None):
    """(residents_by_date, shift_by_id, assignments_by_date) for a date range."""
    # Three queries for the whole range, then bucketed by date in Python - this is
    # what keeps ratio_series / minute_ratio_series off a per-day query loop.
    #
    # SQL: select date, unit_id, care_level, resident_count
    #      from daily_resident_counts
    #      where facility_id = :facility_id and date >= :start and date <= :end
    # Keep rows per date rather than rolling up across units.
    residents_by_date: dict[str, list[dict]] = {}
    for r in (client.table("daily_resident_counts")
              .select("date,unit_id,care_level,resident_count")
              .eq("facility_id", facility_id)
              .gte("date", str(start)).lte("date", str(end)).execute().data):
        key = str(r["date"])[:10]
        residents_by_date.setdefault(key, []).append(r)

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
        # SQL: select id, shift_id, role, staff_id, is_agency, status
        #      from shift_assignments
        #      where shift_id = any(:shift_ids)
        assigns = [a for a in assignments_for_shifts(
            client, shift_by, select="id,shift_id,role,staff_id,is_agency,status")
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
    rule_rows = _load_rule_rows(client, facility_id)
    if not rule_rows:
        return []
    residents_by_date, shift_by, by_date = _load_range(
        client, facility_id, start, end, roster_version_id)

    out = []
    day = start
    while day <= end:
        key = day.isoformat()
        day_assigns = by_date.get(key, [])
        day_shifts = {a["shift_id"]: shift_by[a["shift_id"]] for a in day_assigns}
        checks = _evaluate_day(
            rule_rows,
            residents_by_date.get(key, []),
            day_shifts,
            day_assigns,
            facility_id=facility_id,
            on_date=key,
        )
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
# data - they stay in code. Every *number* is measured from the database.
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
            assigns = assignments_for_shifts(
                client, by_id, select="shift_id,staff_id,role,is_agency,status")
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
                    else "No triggers this month - A/P shifts within limit ✓"),
        "note_zh": (f"{len(pt_breaches)} 個 A/P 更超出 PT 上限" if pt_breaches
                    else "本月未觸發 - A/P更均在上限內 ✓"),
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
