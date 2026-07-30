"""ROI v2.2 - admin-time (A1), emergency-cover (A2) and agency (Part B) savings.

The formulas are fixed by the ROI paper; what varies per home is the baseline
(manager hourly rate, survey hours, agency reduction assumption), which lives in
roi_settings and is editable from the ROI page. Everything else is counted from
the database: headcount from `staff`, incidents from `sl_incidents`, agency spend
from `agency_assignments`. Nothing here falls back to a demo constant.
"""
from __future__ import annotations

from datetime import date as Date

from ..constants import EMMA_TIERS, tier_for
from ._common import month_bounds, now_iso

EXTERNAL_TYPES = {"local_pt", "agency", "outsource", "casual"}
SCENARIOS = (
    (5, "conservative", "SWD minimum staffing floor", True),
    (8, "mid", "Paper 1 pilot reference", False),
    (15, "upside", "Original - removed as overly optimistic", False),
)

DEFAULTS = {
    "manager_hourly_rate": 409,
    "roster_hours_before": 26,
    "roster_hours_after": 7,
    "hours_saved_per_incident": 0.75,
    "agency_reduction_pct": 5,
    "total_budget": 0,
    "salary_budget": 0,
    "contract_years": "5yr",
    "vacancies_json": {},
}

EDITABLE = tuple(DEFAULTS)


def get_settings(client, facility_id: str) -> dict:
    # SQL: select * from roi_settings where facility_id = :facility_id
    rows = (client.table("roi_settings").select("*")
            .eq("facility_id", facility_id).execute().data)
    if rows:
        return rows[0]
    # SQL: insert into roi_settings (facility_id, <every key of DEFAULTS>)
    #      values (:facility_id, ...)
    #      returning *
    return (client.table("roi_settings")
            .insert({"facility_id": facility_id, **DEFAULTS}).execute().data[0])


def update_settings(client, facility_id: str, patch: dict,
                    profile_id: str | None = None) -> dict:
    get_settings(client, facility_id)              # ensure the row exists
    clean = {k: v for k, v in patch.items() if k in EDITABLE and v is not None}
    if not clean:
        return get_settings(client, facility_id)
    clean.update({"updated_by": profile_id, "updated_at": now_iso()})
    # SQL: update roi_settings
    #      set <the whitelisted keys of `clean`>, updated_by = :profile_id,
    #          updated_at = now()
    #      where facility_id = :facility_id
    #      returning *
    return (client.table("roi_settings").update(clean)
            .eq("facility_id", facility_id).execute().data[0])


def _staff_breakdown(client, facility_id: str, vacancies: dict) -> dict:
    # SQL: select rank, employment_type, status from staff
    #      where facility_id = :facility_id and status = 'active'
    # (in SQL the per-rank headcount would be `group by rank` with `count(*)`)
    rows = (client.table("staff").select("rank,employment_type,status")
            .eq("facility_id", facility_id).eq("status", "active").execute().data)
    by_rank: dict[str, int] = {}
    full_time = part_time = 0
    for r in rows:
        by_rank[r["rank"]] = by_rank.get(r["rank"], 0) + 1
        if r["employment_type"] in EXTERNAL_TYPES:
            part_time += 1
        else:
            full_time += 1
    ranks = sorted(set(by_rank) | set(vacancies or {}))
    return {
        "total": len(rows), "full_time": full_time, "part_time": part_time,
        "by_rank": [{
            "rank": rank,
            "headcount": by_rank.get(rank, 0),
            "vacancies": int((vacancies or {}).get(rank, 0) or 0),
        } for rank in ranks],
    }


def _agency_spend(client, facility_id: str, start: str, end: str) -> dict:
    # SQL: select role, cost, hours, vendor, date, shift_id from agency_assignments
    #      where facility_id = :facility_id and date >= :start and date <= :end
    # (per-role cost rollup is done in Python; in SQL it would be
    #  `group by role` with `count(*)` and `sum(cost)`)
    rows = (client.table("agency_assignments")
            .select("role,cost,hours,vendor,date,shift_id")
            .eq("facility_id", facility_id)
            .gte("date", start).lte("date", end).execute().data)
    linked_shift_ids = {
        row["shift_id"] for row in rows if row.get("shift_id")
    }
    published_shift_ids: set[str] = set()
    if linked_shift_ids:
        shifts = (
            client.table("shifts")
            .select("id,roster_version_id")
            .eq("facility_id", facility_id)
            .in_("id", list(linked_shift_ids))
            .execute()
            .data
        )
        version_ids = {
            row.get("roster_version_id") for row in shifts
            if row.get("roster_version_id")
        }
        published_versions: set[str] = set()
        if version_ids:
            published_versions = {
                row["id"] for row in (
                    client.table("roster_versions")
                    .select("id,status")
                    .eq("facility_id", facility_id)
                    .in_("id", list(version_ids))
                    .eq("status", "published")
                    .execute()
                    .data
                )
            }
        published_shift_ids = {
            row["id"] for row in shifts
            if row.get("roster_version_id") in published_versions
        }
    rows = [
        row for row in rows
        if not row.get("shift_id") or row["shift_id"] in published_shift_ids
    ]
    by_role: dict[str, dict] = {}
    total = 0.0
    for r in rows:
        cost = float(r.get("cost") or 0)
        total += cost
        slot = by_role.setdefault(r.get("role") or "-", {"role": r.get("role") or "-",
                                                         "shifts": 0, "cost": 0.0})
        slot["shifts"] += 1
        slot["cost"] += cost
    breakdown = sorted(by_role.values(), key=lambda b: -b["cost"])
    for b in breakdown:
        b["cost"] = round(b["cost"])
    return {"monthly_cost": round(total), "shifts": len(rows), "breakdown": breakdown}


def summary(client, facility_id: str, on: Date | None = None) -> dict:
    start, end = month_bounds(on)
    s = get_settings(client, facility_id)
    rate = float(s["manager_hourly_rate"])

    staff = _staff_breakdown(client, facility_id, s.get("vacancies_json") or {})
    agency = _agency_spend(client, facility_id, start, end)

    # SQL: select count(*) from sl_incidents
    #      where facility_id = :facility_id
    #        and reported_at >= :month_start::date
    #        and reported_at <= (:month_end::date + time '23:59:59')
    incidents = (client.table("sl_incidents").select("id", count="exact")
                 .eq("facility_id", facility_id)
                 .gte("reported_at", f"{start}T00:00:00Z")
                 .lte("reported_at", f"{end}T23:59:59Z").execute())
    incident_count = incidents.count or 0

    # Part A1 - roster scheduling time
    before = float(s["roster_hours_before"])
    after = float(s["roster_hours_after"])
    a1_hours = round(before - after, 2)
    a1_saving = round(a1_hours * rate)

    # Part A2 - emergency cover
    per_incident = float(s["hours_saved_per_incident"])
    a2_hours = round(incident_count * per_incident, 2)
    a2_saving = round(a2_hours * rate)
    admin_saving = a1_saving + a2_saving

    # Part B - agency
    reduction = float(s["agency_reduction_pct"])
    agency_saving = round(agency["monthly_cost"] * reduction / 100)
    scenarios = [{
        "pct": pct, "key": key, "rationale": why, "adopted": adopted,
        "saving": round(agency["monthly_cost"] * pct / 100),
    } for pct, key, why, adopted in SCENARIOS]

    monthly_saving = admin_saving + agency_saving
    annual_saving = monthly_saving * 12

    # Emma fee (tiered, per active staff member)
    tier = tier_for(staff["total"])
    contract = s["contract_years"]
    tier_rate = tier["rates"][contract]
    annual_fee = staff["total"] * tier_rate * 12
    monthly_fee = round(annual_fee / 12)
    net_annual = annual_saving - annual_fee

    total_budget = float(s["total_budget"] or 0)
    return {
        "month_start": start, "month_end": end,
        "settings": {k: (float(s[k]) if isinstance(s[k], (int, float)) else s[k])
                     for k in EDITABLE if k in s},
        "staff": staff,
        "a1": {
            "hours_before": before, "hours_after": after,
            "hours_saved": a1_hours, "hourly_rate": rate, "saving": a1_saving,
            "formula": f"({before}h − {after}h) × HK${rate:g}/hr",
        },
        "a2": {
            "incidents": incident_count, "hours_per_incident": per_incident,
            "hours_saved": a2_hours, "hourly_rate": rate, "saving": a2_saving,
            "formula": f"{incident_count} × {per_incident}h × HK${rate:g}/hr",
        },
        "agency": {
            **agency, "reduction_pct": reduction, "saving": agency_saving,
            "scenarios": scenarios,
            "formula": f"HK${agency['monthly_cost']:,} × {reduction:g}%",
        },
        "totals": {
            "admin_saving": admin_saving,
            "monthly_saving": monthly_saving,
            "annual_saving": annual_saving,
            "pct_of_annual_budget": (round(annual_saving / (total_budget * 12) * 100, 1)
                                     if total_budget else None),
        },
        "emma": {
            "tier": tier["tier"], "tier_label": tier["label"], "contract_years": contract,
            "rate_per_user": tier_rate, "monthly_fee": monthly_fee,
            "annual_fee": annual_fee, "annual_fee_prepaid": round(annual_fee * 0.85),
            "net_annual_benefit": net_annual,
            "payback_months": (round(annual_fee / monthly_saving, 1)
                               if monthly_saving > 0 else None),
            "roi_multiple": (round(annual_saving / annual_fee, 1)
                             if annual_fee > 0 else None),
        },
        "tiers": [{
            "tier": t["tier"], "label": t["label"], "max_staff": t["max_staff"],
            "rates": t["rates"],
        } for t in EMMA_TIERS],
    }
