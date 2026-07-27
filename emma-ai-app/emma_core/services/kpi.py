"""KPI framework (spec 5.4 – 5.9).

All six KPIs are computed from committed rows — violation_log, shift_assignments,
manual_override_log, agency_assignments and the ratio engine — for the operative
version of a roster period. Nothing is stored pre-aggregated, so a KPI can never
disagree with the roster it claims to describe.
"""
from __future__ import annotations

from ..constants import PlanMode
from ._common import as_date, operative_version, resolve_period
from .compliance import EXTERNAL_TYPES, minute_ratio_series, ratio_series

DIFFICULT_SHIFTS = ("AN", "N", "7P", "P")   # fairness is reported for every type anyway


def _context(client, facility_id: str, period_id: str | None):
    period = resolve_period(client, facility_id, period_id)
    if not period:
        return None, None
    return period, operative_version(client, facility_id, period["id"])


def _roster_rows(client, version_id: str) -> tuple[dict[str, dict], list[dict]]:
    shifts = (client.table("shifts").select("*")
              .eq("roster_version_id", version_id).execute().data)
    if not shifts:
        return {}, []
    by_id = {s["id"]: s for s in shifts}
    assigns = [a for a in (client.table("shift_assignments").select("*")
                           .in_("shift_id", list(by_id)).execute().data)
               if a.get("status") != "cancelled" and a.get("staff_id")]
    return by_id, assigns


def gini(values: list[float]) -> float:
    """SUM_i SUM_j |xi - xj| / (2 n² x̄) — 0 = perfectly even, 1 = one person has all."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    if mean == 0:
        return 0.0
    spread = sum(abs(a - b) for a in values for b in values)
    return round(spread / (2 * n * n * mean), 4)


# ── 5.4 conflict rate ────────────────────────────────────────────────────────
def conflict_rate(client, facility_id: str, period_id: str | None = None) -> dict:
    period, version = _context(client, facility_id, period_id)
    if not version:
        return {"period_id": None, "assignments": 0, "hard_violations": 0,
                "conflict_rate_pct": 0.0, "by_rule": []}
    _, assigns = _roster_rows(client, version["id"])
    violations = (client.table("violation_log").select("rule_code,severity,resolved")
                  .eq("facility_id", facility_id)
                  .eq("roster_version_id", version["id"]).execute().data)
    hard = [v for v in violations if v.get("severity") == "hard" and not v.get("resolved")]
    by_rule: dict[str, int] = {}
    for v in hard:
        by_rule[v["rule_code"]] = by_rule.get(v["rule_code"], 0) + 1
    return {
        "period_id": period["id"], "roster_version_id": version["id"],
        "assignments": len(assigns), "hard_violations": len(hard),
        "conflict_rate_pct": round(len(hard) / len(assigns) * 100, 2) if assigns else 0.0,
        "by_rule": [{"rule_code": k, "count": v} for k, v in sorted(by_rule.items())],
    }


# ── 5.5 AN Gini + 5.8 all-shift fairness ─────────────────────────────────────
def shift_fairness(client, facility_id: str, period_id: str | None = None) -> dict:
    """Distribution fairness per shift type over staff eligible for the whole period."""
    period, version = _context(client, facility_id, period_id)
    if not version:
        return {"period_id": None, "eligible_staff": 0, "by_shift_type": []}

    by_id, assigns = _roster_rows(client, version["id"])
    staff_rows = (client.table("staff").select("id,rank,employment_type,status,created_at")
                  .eq("facility_id", facility_id).eq("status", "active").execute().data)
    period_start = as_date(period["period_start"])
    # "full-month eligible": on the books before the period opened, not external.
    eligible = [s["id"] for s in staff_rows
                if s["employment_type"] not in EXTERNAL_TYPES
                and as_date(s["created_at"]) <= period_start]
    if not eligible:
        eligible = [s["id"] for s in staff_rows]

    counts: dict[str, dict[str, int]] = {}
    for a in assigns:
        sh = by_id[a["shift_id"]]
        if not sh.get("is_working"):
            continue
        counts.setdefault(sh["shift_type"], {})[a["staff_id"]] = (
            counts.setdefault(sh["shift_type"], {}).get(a["staff_id"], 0) + 1)

    out = []
    for shift_type in sorted(counts):
        per_staff = [counts[shift_type].get(sid, 0) for sid in eligible]
        total = sum(per_staff)
        out.append({
            "shift_type": shift_type, "total": total,
            "gini": gini([float(v) for v in per_staff]),
            "max": max(per_staff), "min": min(per_staff),
            "mean": round(total / len(per_staff), 2) if per_staff else 0,
            "difficult": shift_type in DIFFICULT_SHIFTS,
        })
    return {
        "period_id": period["id"], "roster_version_id": version["id"],
        "eligible_staff": len(eligible), "by_shift_type": out,
    }


def an_gini(client, facility_id: str, period_id: str | None = None) -> dict:
    fairness = shift_fairness(client, facility_id, period_id)
    row = next((r for r in fairness["by_shift_type"] if r["shift_type"] == "AN"), None)
    return {
        "period_id": fairness["period_id"],
        "eligible_staff": fairness["eligible_staff"],
        "an_total": row["total"] if row else 0,
        "gini": row["gini"] if row else 0.0,
        "max": row["max"] if row else 0,
        "min": row["min"] if row else 0,
        "target_baseline": 0.25, "target_long_term": 0.10,
    }


# ── 5.6 AI acceptance / manual override ──────────────────────────────────────
def ai_acceptance(client, facility_id: str, period_id: str | None = None) -> dict:
    period, version = _context(client, facility_id, period_id)
    if not period:
        return {"period_id": None, "ai_assignments": 0, "overrides": 0,
                "acceptance_rate_pct": None, "override_rate_pct": 0.0}

    versions = (client.table("roster_versions").select("id,version_type,created_at")
                .eq("facility_id", facility_id).eq("period_id", period["id"])
                .execute().data)
    ai_versions = [v for v in versions
                   if v["version_type"] in (PlanMode.A, PlanMode.B, PlanMode.C)]
    version_ids = [v["id"] for v in versions]

    overrides = 0
    if version_ids:
        overrides = (client.table("manual_override_log").select("id", count="exact")
                     .eq("facility_id", facility_id)
                     .in_("roster_version_id", version_ids).execute().count or 0)

    ai_assignments = 0
    if ai_versions:
        newest = max(ai_versions, key=lambda v: v["created_at"])
        _, ai_assigns = _roster_rows(client, newest["id"])
        ai_assignments = len(ai_assigns)

    total_assignments = 0
    if version:
        _, assigns = _roster_rows(client, version["id"])
        total_assignments = len(assigns)

    return {
        "period_id": period["id"],
        "ai_versions": len(ai_versions),
        "ai_assignments": ai_assignments,
        "total_assignments": total_assignments,
        "overrides": overrides,
        "acceptance_rate_pct": (round(max(0, ai_assignments - overrides) / ai_assignments * 100, 1)
                                if ai_assignments else None),
        "override_rate_pct": (round(overrides / total_assignments * 100, 1)
                              if total_assignments else 0.0),
    }


# ── 5.9 external workforce dependency ────────────────────────────────────────
def external_workforce(client, facility_id: str, period_id: str | None = None) -> dict:
    """External dependency counts two sources: internal roster cells worked by
    part-time/agency/outsourced staff, and bought-in agency shifts, which are
    extra bodies that never appear in the roster. Counting only the first reports
    0% dependency for a home whose gaps are all covered by an outside vendor."""
    period, version = _context(client, facility_id, period_id)
    if not period:
        return {"period_id": None, "total_shifts": 0, "external_shifts": 0,
                "agency_shifts": 0, "dependency_pct": 0.0, "agency_cost": 0,
                "by_role": []}

    by_id, assigns = _roster_rows(client, version["id"]) if version else ({}, [])
    staff = {s["id"]: s for s in (
        client.table("staff").select("id,rank,employment_type")
        .eq("facility_id", facility_id).execute().data)}

    total = external = 0
    by_role: dict[str, dict] = {}
    for a in assigns:
        if not by_id[a["shift_id"]].get("is_working"):
            continue
        total += 1
        st = staff.get(a["staff_id"]) or {}
        is_external = bool(a.get("is_agency")) or st.get("employment_type") in EXTERNAL_TYPES
        role = a.get("role") or st.get("rank") or "—"
        slot = by_role.setdefault(role, {"role": role, "shifts": 0, "external": 0})
        slot["shifts"] += 1
        if is_external:
            external += 1
            slot["external"] += 1

    agency_rows = (client.table("agency_assignments").select("cost,date,role")
                   .eq("facility_id", facility_id)
                   .gte("date", str(period["period_start"]))
                   .lte("date", str(period["period_end"])).execute().data)
    cost = sum(float(r.get("cost") or 0) for r in agency_rows)
    for r in agency_rows:
        role = r.get("role") or "—"
        slot = by_role.setdefault(role, {"role": role, "shifts": 0, "external": 0})
        slot["shifts"] += 1
        slot["external"] += 1
    total += len(agency_rows)
    external += len(agency_rows)

    for slot in by_role.values():
        slot["dependency_pct"] = (round(slot["external"] / slot["shifts"] * 100, 1)
                                  if slot["shifts"] else 0.0)
    return {
        "period_id": period["id"],
        "roster_version_id": version["id"] if version else None,
        "total_shifts": total, "external_shifts": external,
        "agency_shifts": len(agency_rows),
        "dependency_pct": round(external / total * 100, 1) if total else 0.0,
        "agency_cost": round(cost),
        "by_role": sorted(by_role.values(), key=lambda r: -r["external"]),
    }


# ── 5.7 SWD staffing-ratio compliance ────────────────────────────────────────
def staffing_ratio_compliance(client, facility_id: str,
                              period_id: str | None = None) -> dict:
    period, version = _context(client, facility_id, period_id)
    if not period:
        return {"period_id": None, "pass_rate_pct": 0.0, "breach_days": 0,
                "breach_minutes": 0, "days": [], "by_rule": []}

    start, end = as_date(period["period_start"]), as_date(period["period_end"])
    version_id = version["id"] if version else None
    days = ratio_series(client, facility_id, start, end, roster_version_id=version_id)
    minutes = minute_ratio_series(client, facility_id, start, end,
                                  roster_version_id=version_id)

    checks = sum(d["checks"] for d in days)
    passed = sum(d["passed"] for d in days)
    breach_minutes = sum(m["breach_minutes"] for m in minutes)

    by_rule: dict[str, dict] = {}
    for m in minutes:
        slot = by_rule.setdefault(m["label"], {
            "label": m["label"], "rank": m["rank"], "breach_minutes": 0, "breach_days": 0})
        slot["breach_minutes"] += m["breach_minutes"]
        slot["breach_days"] += 0 if m["passes"] else 1

    return {
        "period_id": period["id"], "roster_version_id": version_id,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "checks": checks, "passed": passed,
        "pass_rate_pct": round(passed / checks * 100, 1) if checks else 0.0,
        "breach_days": len([d for d in days if d["failed"]]),
        "breach_minutes": breach_minutes,
        "publishable": passed == checks,
        "days": days,
        "by_rule": sorted(by_rule.values(), key=lambda r: -r["breach_minutes"]),
    }


def overview(client, facility_id: str, period_id: str | None = None) -> dict:
    """Every KPI in one call — what the ROI/KPI dashboard strip renders."""
    return {
        "conflict_rate": conflict_rate(client, facility_id, period_id),
        "an_gini": an_gini(client, facility_id, period_id),
        "shift_fairness": shift_fairness(client, facility_id, period_id),
        "ai_acceptance": ai_acceptance(client, facility_id, period_id),
        "external_workforce": external_workforce(client, facility_id, period_id),
        "staffing_ratio_compliance": staffing_ratio_compliance(client, facility_id, period_id),
    }


__all__ = [
    "ai_acceptance", "an_gini", "conflict_rate", "external_workforce", "gini",
    "overview", "shift_fairness", "staffing_ratio_compliance",
]
