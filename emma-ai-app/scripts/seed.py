"""Seed local Supabase with Home A + Home B demo data.

Run AFTER `supabase db reset` (schema+RLS applied) and after .env holds the
service-role key:

    .venv/Scripts/python scripts/seed.py

Uses the service-role client (bypasses RLS) to create reference data, a demo
roster (ported from the prototype UI pattern), resident counts, and dev auth
users. Idempotent: wipes the two demo facilities + dev users first.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from emma_core.db import get_service_client  # noqa: E402

DEV_PASSWORD = "EmmaDev123!"

sb = get_service_client()


# ── helpers ──────────────────────────────────────────────────────────────────
def ins(table: str, row: dict) -> str:
    res = sb.table(table).insert(row).execute()
    return res.data[0]["id"]


def ins_many(table: str, rows: list[dict]) -> list[str]:
    if not rows:
        return []
    res = sb.table(table).insert(rows).execute()
    return [r["id"] for r in res.data]


def wipe() -> None:
    for code in ("A", "B"):
        sb.table("facilities").delete().eq("code", code).execute()
    # dev auth users
    try:
        users = sb.auth.admin.list_users()
        for u in users:
            if u.email and u.email.endswith("@emma.local"):
                sb.auth.admin.delete_user(u.id)
    except Exception as e:  # noqa: BLE001
        print("  (auth wipe skipped:", e, ")")


def seed_shift_defs(facility_id: str, defs: list[tuple]) -> None:
    rows = []
    for code, label, start, end, cross, working in defs:
        rows.append({
            "facility_id": facility_id, "shift_type": code, "label": label,
            "start_time": start, "end_time": end, "cross_midnight": cross,
            "is_working": working,
        })
    ins_many("shift_definitions", rows)


def seed_ratio_rules(facility_id: str, cw_rank: str) -> None:
    rules = [
        ("RN", "07:00", "20:00", 60, None),
        ("HW", "07:00", "20:00", 30, None),
        (cw_rank, "07:00", "17:00", 20, None),
        (cw_rank, "17:00", "07:00", 40, None),
        ("AW", "07:00", "18:00", 40, None),
        (None, "18:00", "07:00", None, 2),  # night: >=2 staff any rank
    ]
    rows = [{
        "facility_id": facility_id, "staff_rank": r, "time_window_start": s,
        "time_window_end": e, "ratio_residents_per_staff": ratio,
        "min_staff_any_rank": mn, "effective_from": "2026-01-01", "active": True,
    } for (r, s, e, ratio, mn) in rules]
    ins_many("staffing_ratio_rules", rows)


# time maps per shift code -> (start, end, cross_midnight, is_working)
SHIFT_TIMES_A = {
    "A": ("07:00", "15:00", False, True), "B": ("08:00", "16:00", False, True),
    "E": ("09:00", "17:00", False, True), "P": ("13:30", "21:30", False, True),
    "N": ("21:30", "07:00", True, True),  "AN": ("07:00", "13:30", True, True),
    "OFF": (None, None, False, False), "AL": (None, None, False, False),
    "SLEEP": (None, None, False, False), "DO": (None, None, False, False),
}
SHIFT_TIMES_B = {
    "7A": ("07:00", "19:00", False, True), "9A": ("09:00", "21:00", False, True),
    "7P": ("19:00", "07:00", True, True),  "A": ("07:00", "16:00", False, True),
    "P": ("12:30", "21:30", False, True),  "AN": ("07:00", "14:30", True, True),
    "OFF": (None, None, False, False), "DO": (None, None, False, False),
    "AL": (None, None, False, False), "SLEEP": (None, None, False, False),
}

WEEK = [f"2026-07-0{d}" for d in range(1, 8)]  # 2026-07-01 .. 07


def seed_roster(facility_id, version_id, staff_ids, ranks, units, pattern,
                times, day0_tasks) -> None:
    """One shift + assignment per staff per day, following `pattern`."""
    for i, staff_id in enumerate(staff_ids):
        for d, code in enumerate(pattern[i]):
            start, end, cross, working = times[code]
            shift_id = ins("shifts", {
                "facility_id": facility_id, "roster_version_id": version_id,
                "date": WEEK[d], "shift_type": code, "start_time": start,
                "end_time": end, "cross_midnight": cross, "unit_id": units[i],
                "required_rank": ranks[i], "required_count": 1,
                "is_working": working,
            })
            ins("shift_assignments", {
                "facility_id": facility_id, "shift_id": shift_id,
                "staff_id": staff_id, "role": ranks[i], "status": "assigned",
                "is_agency": False,
                "tasks": day0_tasks.get(i, []) if d == 0 else [],
            })


def seed_resident_counts(facility_id, unit_counts, entered_by) -> None:
    rows = []
    for date in WEEK:
        for unit_id, count in unit_counts:
            rows.append({
                "facility_id": facility_id, "date": date, "unit_id": unit_id,
                "care_level": "general", "resident_count": count,
                "entered_by": entered_by,
            })
    ins_many("daily_resident_counts", rows)


def make_user(email, role, facility_id, staff_id=None) -> str:
    res = sb.auth.admin.create_user({
        "email": email, "password": DEV_PASSWORD, "email_confirm": True,
    })
    auth_id = res.user.id
    ins("users_profile", {
        "auth_user_id": auth_id, "facility_id": facility_id, "email": email,
        "role": role, "staff_id": staff_id,
    })
    return auth_id


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print("Wiping demo facilities + dev users ...")
    wipe()

    # ---- calendar (global HK public holiday) ----
    sb.table("calendar_days").delete().eq("date", "2026-07-01").is_("facility_id", "null").execute()
    ins("calendar_days", {
        "facility_id": None, "date": "2026-07-01", "day_type": "public_holiday",
        "holiday_name": "HKSAR Establishment Day", "is_agency_allowed": True,
        "staff_cost_multiplier": 2.0,
    })

    # ================= HOME A (28-day cycle) =================
    print("Seeding Home A ...")
    fa = ins("facilities", {
        "code": "A", "name": "Care Home A (救世軍式)", "type": "RCHE",
        "scheduling_cycle_days": 28,
    })
    east = ins("facility_units", {"facility_id": fa, "unit_type": "wing", "name": "East Wing", "code": "EW"})
    west = ins("facility_units", {"facility_id": fa, "unit_type": "wing", "name": "West Wing", "code": "WW"})

    a_staff = [
        ("余逸詩", "Yu Yat Sze", "RN", "local_ft", east),
        ("梁嘉琪", "Leung Ka Kei", "EN", "local_ft", west),
        ("王雅琛", "Wong Yat Sum", "HW", "local_ft", east),
        ("何啟晴", "Ho Kai Ching", "CW", "local_ft", west),
        ("黃司琦", "Wong Sze Kai", "PTA", "local_ft", east),
        ("黃靜賢", "Wong Jing Yin", "PCW", "imported_labor", west),
        ("李紹洪", "Li Shao Hung", "AW", "local_ft", east),
    ]
    a_ids, a_ranks, a_units = [], [], []
    for name, en, rank, emp, unit in a_staff:
        sid = ins("staff", {
            "facility_id": fa, "name": name, "name_en": en, "rank": rank,
            "employment_type": emp, "primary_unit_id": unit,
            "contracted_hours": 44, "is_audited_for_medication": rank in ("RN", "EN", "HW"),
            "status": "active",
        })
        ins("staff_contracts", {
            "facility_id": fa, "staff_id": sid, "weekly_hours": 44,
            "max_weekly_hours": 54, "min_rest_minutes": 720 if emp == "imported_labor" else 660,
            "allowed_shift_types": ["A", "B", "E", "P", "N", "AN"],
            "effective_from": "2026-01-01",
        })
        a_ids.append(sid); a_ranks.append(rank); a_units.append(unit)

    # per-staff certificates with expiry (feeds Staff Portfolio credentials +
    # Compliance "Certifications" expiry tracking). Dates around 2026-07 give a mix
    # of expiring-soon and far-off for a realistic compliance view.
    a_certs = [
        [("ACLS", "2026-08-10"), ("Triage", "2027-01-15"), ("BLS", "2026-08-01")],  # RN
        [("First Aid", "2026-08-20"), ("Manual Handling", "2027-03-01")],           # EN
        [("Elder Care", "2026-09-30"), ("Vitals", "2026-08-15")],                   # HW
        [("Personal Care", "2027-06-30")],                                          # CW
        [("Rehab Tech", "2026-11-05")],                                             # PTA
        [("Bathing", "2026-08-28"), ("Transfer", "2027-02-01")],                    # PCW
        [("Infection Control", "2027-01-20")],                                      # AW
    ]
    ins_many("staff_certificates", [
        {"facility_id": fa, "staff_id": a_ids[i], "cert_type": c, "expiry_date": exp}
        for i, certs in enumerate(a_certs) for (c, exp) in certs
    ])

    seed_shift_defs(fa, [
        ("A", "Morning", "07:00", "15:00", False, True),
        ("B", "Morning B", "08:00", "16:00", False, True),
        ("E", "Morning E", "09:00", "17:00", False, True),
        ("P", "Afternoon", "13:30", "21:30", False, True),
        ("N", "Night", "21:30", "07:00", True, True),
        ("AN", "A/N split", "07:00", "13:30", True, True),
        ("OFF", "Day Off", None, None, False, False),
        ("AL", "Annual Leave", None, None, False, False),
        ("SLEEP", "Sleeping Day", None, None, False, False),
        ("DO", "Rest Day", None, None, False, False),
    ])
    seed_ratio_rules(fa, "CW")

    period_a = ins("roster_periods", {
        "facility_id": fa, "period_start": "2026-07-01", "period_end": "2026-07-28",
        "cycle_type": "28day", "status": "planning",
    })
    ver_a = ins("roster_versions", {
        "facility_id": fa, "period_id": period_a, "version_type": "manual",
        "label": "July 2026 draft", "status": "draft",
    })
    pattern_a = [
        ["P", "A", "P", "AN", "SLEEP", "OFF", "AL"],
        ["OFF", "P", "P", "A", "P", "AN", "SLEEP"],
        ["A", "AN", "SLEEP", "OFF", "A", "A", "OFF"],
        ["P", "P", "OFF", "P", "P", "A", "A"],
        ["A", "A", "A", "A", "A", "OFF", "OFF"],
        ["N", "N", "N", "OFF", "N", "N", "N"],
        ["P", "P", "P", "P", "P", "A", "A"],
    ]
    tasks_a = {
        0: ["Med Checking", "ICP Review", "FU Chat"],
        2: ["Vital Signs", "AOM (Oral)"],
        3: ["Oral Feeding", "Diaper Change"],
        4: ["Rehab Session"],
        6: ["Infection Control"],
    }
    seed_roster(fa, ver_a, a_ids, a_ranks, a_units, pattern_a, SHIFT_TIMES_A, tasks_a)

    # ================= HOME B (natural month) =================
    print("Seeding Home B ...")
    fb = ins("facilities", {
        "code": "B", "name": "Care Home B (多層院舍)", "type": "RCHE",
        "scheduling_cycle_days": 31,
    })
    f2 = ins("facility_units", {"facility_id": fb, "unit_type": "floor", "name": "2/F", "code": "2F"})
    f6 = ins("facility_units", {"facility_id": fb, "unit_type": "floor", "name": "6/F", "code": "6F"})
    b_staff = [
        ("陳大文", "Chan Tai Man", "HCA", "imported_labor", f2),
        ("李美娟", "Li Mei Kuen", "HW", "local_ft", f6),
        ("王志強", "Wong Chi Keung", "EN", "local_ft", f6),
    ]
    b_ids, b_ranks, b_units = [], [], []
    for name, en, rank, emp, unit in b_staff:
        sid = ins("staff", {
            "facility_id": fb, "name": name, "name_en": en, "rank": rank,
            "employment_type": emp, "primary_unit_id": unit,
            "contracted_hours": 49.5 if emp == "local_ft" else 72, "status": "active",
        })
        b_ids.append(sid); b_ranks.append(rank); b_units.append(unit)

    seed_shift_defs(fb, [
        ("7A", "7A 12h", "07:00", "19:00", False, True),
        ("9A", "9A 12h", "09:00", "21:00", False, True),
        ("7P", "7P night", "19:00", "07:00", True, True),
        ("A", "Morning", "07:00", "16:00", False, True),
        ("P", "Afternoon", "12:30", "21:30", False, True),
        ("AN", "A/N split", "07:00", "14:30", True, True),
        ("OFF", "Day Off", None, None, False, False),
        ("DO", "Rest Day", None, None, False, False),
        ("AL", "Annual Leave", None, None, False, False),
        ("SLEEP", "Sleeping Day", None, None, False, False),
    ])
    seed_ratio_rules(fb, "HCA")

    period_b = ins("roster_periods", {
        "facility_id": fb, "period_start": "2026-07-01", "period_end": "2026-07-31",
        "cycle_type": "natural_month", "status": "planning",
    })
    ver_b = ins("roster_versions", {
        "facility_id": fb, "period_id": period_b, "version_type": "manual",
        "label": "July 2026 draft", "status": "draft",
    })
    pattern_b = [
        ["7A", "7A", "7P", "OFF", "7A", "7A", "7A"],
        ["A", "A", "P", "P", "OFF", "A", "A"],
        ["P", "P", "A", "A", "P", "OFF", "DO"],
    ]
    seed_roster(fb, ver_b, b_ids, b_ranks, b_units, pattern_b, SHIFT_TIMES_B, {})

    # ---- auth users + profiles ----
    print("Creating dev auth users ...")
    super_a = make_user("super_a@emma.local", "superintendent", fa)
    make_user("admin_a@emma.local", "admin", fa)
    make_user("super_b@emma.local", "superintendent", fb)

    # resident counts (need an entered_by profile id for Home A)
    prof_a = sb.table("users_profile").select("id").eq("auth_user_id", super_a).execute().data[0]["id"]
    seed_resident_counts(fa, [(east, 42), (west, 38)], prof_a)

    print("\nSeed complete.")
    print("  Dev logins (password: %s):" % DEV_PASSWORD)
    print("    super_a@emma.local  (Superintendent, Home A)")
    print("    admin_a@emma.local  (Admin, Home A)")
    print("    super_b@emma.local  (Superintendent, Home B)")


if __name__ == "__main__":
    main()
