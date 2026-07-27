"""Seed local Supabase with Home A + Home B demo data.

Run AFTER `supabase db reset` (schema+RLS applied) and after .env holds the
service-role key:

    python scripts/seed.py

Uses the service-role client (bypasses RLS) to create reference data, a full
period roster, resident counts, and the Phase 3 operations layer (leave
requests, SL/DSL incidents, agency spend, attendance, debt ledger, report
schedules, regulatory registry). Idempotent: wipes the two demo facilities +
dev users first.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date as Date, datetime, timedelta, timezone

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


def ts(day: Date, hour: int, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute,
                    tzinfo=timezone.utc).isoformat()


def dates_for(start: str, days: int) -> list[str]:
    d0 = Date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(days)]


def wipe() -> None:
    for code in ("A", "B"):
        sb.table("facilities").delete().eq("code", code).execute()
    # global (facility-less) reference rows this script owns
    sb.table("regulatory_documents").delete().is_("facility_id", "null").execute()
    try:
        users = sb.auth.admin.list_users()
        for u in users:
            if u.email and u.email.endswith("@emma.local"):
                sb.auth.admin.delete_user(u.id)
    except Exception as e:  # noqa: BLE001
        print("  (auth wipe skipped:", e, ")")


def seed_shift_defs(facility_id: str, defs: list[tuple]) -> None:
    ins_many("shift_definitions", [{
        "facility_id": facility_id, "shift_type": code, "label": label,
        "start_time": start, "end_time": end, "cross_midnight": cross,
        "is_working": working,
    } for code, label, start, end, cross, working in defs])


def seed_ratio_rules(facility_id: str, cw_rank: str) -> None:
    rules = [
        ("RN", "07:00", "20:00", 60, None),
        ("HW", "07:00", "20:00", 30, None),
        (cw_rank, "07:00", "17:00", 20, None),
        (cw_rank, "17:00", "07:00", 40, None),
        ("AW", "07:00", "18:00", 40, None),
        (None, "18:00", "07:00", None, 2),  # night: >=2 staff any rank
    ]
    ins_many("staffing_ratio_rules", [{
        "facility_id": facility_id, "staff_rank": r, "time_window_start": s,
        "time_window_end": e, "ratio_residents_per_staff": ratio,
        "min_staff_any_rank": mn, "effective_from": "2026-01-01", "active": True,
    } for (r, s, e, ratio, mn) in rules])


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

PERIOD_A_START, PERIOD_A_DAYS = "2026-07-01", 28
PERIOD_B_START, PERIOD_B_DAYS = "2026-07-01", 31


def seed_roster(facility_id, version_id, staff_ids, ranks, units, pattern,
                times, task_map, dates) -> dict[str, list[str]]:
    """One shift + assignment per staff per day. The 7-day pattern repeats across
    the whole period so a 28-day cycle really has 28 days of roster — the KPI,
    fairness and report screens all read a full period.

    Returns {staff_id: [assignment_id, ...]} in date order.
    """
    shift_rows, meta = [], []
    for i, staff_id in enumerate(staff_ids):
        for d, day in enumerate(dates):
            code = pattern[i][d % 7]
            start, end, cross, working = times[code]
            shift_rows.append({
                "facility_id": facility_id, "roster_version_id": version_id,
                "date": day, "shift_type": code, "start_time": start,
                "end_time": end, "cross_midnight": cross, "unit_id": units[i],
                "required_rank": ranks[i], "required_count": 1, "is_working": working,
            })
            meta.append((i, staff_id, d, code))

    shift_ids = ins_many("shifts", shift_rows)
    assign_rows = []
    for shift_id, (i, staff_id, d, code) in zip(shift_ids, meta):
        # A staff member's standing duties recur on every working day, which is
        # what gives the AI-analysis tab real task-frequency evidence.
        tasks = task_map.get(i, []) if times[code][3] else []
        assign_rows.append({
            "facility_id": facility_id, "shift_id": shift_id, "staff_id": staff_id,
            "role": ranks[i], "status": "assigned", "is_agency": False, "tasks": tasks,
        })
    assignment_ids = ins_many("shift_assignments", assign_rows)

    by_staff: dict[str, list[str]] = {}
    for aid, (_, staff_id, _, _) in zip(assignment_ids, meta):
        by_staff.setdefault(staff_id, []).append(aid)
    return {"shift_ids": shift_ids, "meta": meta, "by_staff": by_staff}


def seed_resident_counts(facility_id, unit_counts, entered_by, dates) -> None:
    ins_many("daily_resident_counts", [{
        "facility_id": facility_id, "date": day, "unit_id": unit_id,
        "care_level": "general", "resident_count": count, "entered_by": entered_by,
    } for day in dates for unit_id, count in unit_counts])


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


# ── Phase 3 operations layer ─────────────────────────────────────────────────
def seed_task_definitions(facility_id: str) -> None:
    ins_many("task_definitions", [{
        "facility_id": facility_id, "task_code": code, "task_name": name,
        "shift_type": shift, "required_rank": rank, "requires_audit": audit,
    } for code, name, shift, rank, audit in [
        ("A1", "Med Checking", "A", "RN", True),
        ("A2", "Medication Mgmt", "A", "RN", True),
        ("A3", "Vital Signs", "A", None, False),
        ("A4", "Wound Care", "P", "RN", False),
        ("A5", "ICP Review", "P", "RN", False),
        ("A6", "Oral Feeding", None, None, False),
        ("A7", "Diaper Change", None, None, False),
        ("A8", "Infection Control", None, "AW", False),
        ("P1", "Rehab Session", "A", "PTA", False),
        ("P2", "FU Chat", "P", None, False),
        ("P3", "AOM (Oral)", "A", "HW", True),
        ("P4", "Escort Duty", None, None, False),
    ]])


def seed_roi_settings(facility_id: str, profile_id: str, *, total_budget: int,
                      salary_budget: int, vacancies: dict) -> None:
    # roi_settings is keyed by facility_id — it has no surrogate `id`, so this
    # can't go through ins().
    sb.table("roi_settings").insert({
        "facility_id": facility_id, "manager_hourly_rate": 409,
        "roster_hours_before": 26, "roster_hours_after": 7,
        "hours_saved_per_incident": 0.75, "agency_reduction_pct": 5,
        "total_budget": total_budget, "salary_budget": salary_budget,
        "contract_years": "5yr", "vacancies_json": vacancies,
        "updated_by": profile_id,
    }).execute()


def seed_leave_requests(facility_id: str, staff_ids: list[str], profile_id: str,
                        ref: Date) -> list[str]:
    """A realistic approval queue: some decided, some awaiting the superintendent."""
    rows = [
        # (staff idx, category, type, start offset, end offset, reason, remark, status, reviewed)
        (3, "al", "AL", -60, -54, "Marriage", "Wedding leave", "approved", True),
        (0, "al", "AL", 12, 16, "Annual leave", None, "reviewed", True),
        (2, "al", "special", 20, 20, "Compassionate leave", None, "pending", False),
        (5, "duty", "duty_request", 5, 5, "Requesting A shift", "Childcare", "pending", False),
        (1, "duty", "DO", 9, 9, "Day off request", None, "approved", True),
        (4, "duty", "duty_request", -3, -3, "Requesting P shift", None, "rejected", True),
        (4, "sick", "SL", -1, -1, "Fever", None, "approved", True),
        (6, "sick", "SL", -8, -8, "Gastric flu", None, "approved", True),
        (1, "sick", "DSL", -14, -11, "Influenza, 4 days", "Medical cert attached",
         "approved", True),
        (5, "sick", "late", 0, 0, "MTR disruption", None, "pending", False),
    ]
    payload = []
    for idx, category, ltype, d0, d1, reason, remark, status, reviewed in rows:
        created = ref + timedelta(days=min(d0, 0) - 1)
        payload.append({
            "facility_id": facility_id, "staff_id": staff_ids[idx],
            "category": category, "leave_type": ltype,
            "date_start": (ref + timedelta(days=d0)).isoformat(),
            "date_end": (ref + timedelta(days=d1)).isoformat(),
            "requested_shift_type": "A" if ltype == "duty_request" and idx == 5 else (
                "P" if ltype == "duty_request" else None),
            "reason": reason, "remark": remark,
            "document_url": "sick-leave-cert.pdf" if category == "sick" and ltype != "late" else None,
            "status": status,
            "reviewed_at": ts(created, 9) if reviewed else None,
            "decided_by": profile_id if status in ("approved", "rejected") else None,
            "decided_at": ts(created, 10) if status in ("approved", "rejected") else None,
            "created_at": ts(created, 8),
        })
    return ins_many("leave_requests", payload)


def seed_incidents(facility_id: str, staff_ids: list[str], profile_id: str,
                   ref: Date, shift_lookup) -> None:
    """A month of SL/DSL activity: mostly closed with a real response time, two
    still open so the Alert centre has live work and candidates to rank."""
    closed = [
        # (staff idx, type, days ago, response minutes, replacement idx, auto)
        (4, "SL", 1, 12, 3, True),
        (6, "SL", 3, 8, 0, True),
        (1, "DSL", 13, 27, 2, False),
        (5, "SL", 5, 19, 3, True),
        (2, "SL", 7, 14, 6, True),
        (3, "urgent", 9, 22, 1, True),
        (0, "SL", 11, 9, 2, True),
        (4, "SL", 15, 31, 6, False),
        (6, "late", 17, 5, 6, True),
        (1, "SL", 19, 16, 4, True),
        (5, "DSL", 22, 34, 0, False),
        (2, "SL", 24, 11, 3, True),
    ]
    rows = []
    for idx, itype, ago, minutes, rep_idx, auto in closed:
        day = ref - timedelta(days=ago)
        reported = ts(day, 7, 15)
        rows.append({
            "facility_id": facility_id, "staff_id": staff_ids[idx],
            "shift_id": shift_lookup(staff_ids[idx], day),
            "incident_type": itype, "reason": "Reported unfit for duty",
            "reported_at": reported, "replacement_status": "resolved",
            "replacement_staff_id": staff_ids[rep_idx],
            "resolved_at": ts(day, 7, 15 + minutes % 45),
            "resolved_by": profile_id, "resolution_minutes": minutes,
            "auto_resolved": auto, "created_at": reported,
        })

    # PostgREST unions the column set across a bulk insert and writes NULL where a
    # key is missing, so every row must carry the same keys — column defaults do
    # not fill the gaps here.
    open_cases = [(5, "SL", 0), (2, "urgent", 0)]
    for idx, itype, ago in open_cases:
        day = ref - timedelta(days=ago)
        rows.append({
            "facility_id": facility_id, "staff_id": staff_ids[idx],
            "shift_id": shift_lookup(staff_ids[idx], day),
            "incident_type": itype, "reason": "Called in unfit for duty",
            "reported_at": ts(day, 6, 40), "replacement_status": "open",
            "replacement_staff_id": None, "resolved_at": None, "resolved_by": None,
            "resolution_minutes": None, "auto_resolved": False,
            "created_at": ts(day, 6, 40),
        })
    ins_many("sl_incidents", rows)


def seed_agency(facility_id: str, ref: Date) -> None:
    """Real per-shift agency rates (HK$118,520 / 124 PT RCW shifts = HK$956;
    HK$29,550 / 24 PT HW-EN shifts = HK$1,231), at this home's scale."""
    rows = []
    for i in range(18):
        day = ref - timedelta(days=(i * 3) % 26)
        rows.append({
            "facility_id": facility_id, "date": day.isoformat(), "role": "PCW",
            "vendor": "HK Care Staffing Ltd", "hours": 8, "cost": 957,
            "reason": "SL cover — no internal candidate within rest rules",
        })
    for i in range(3):
        day = ref - timedelta(days=4 + i * 7)
        rows.append({
            "facility_id": facility_id, "date": day.isoformat(), "role": "HW",
            "vendor": "Prime Nursing Agency", "hours": 8, "cost": 1231,
            "reason": "Vacancy cover pending recruitment",
        })
    ins_many("agency_assignments", rows)


def seed_attendance(facility_id: str, staff_id: str, ref: Date) -> None:
    rows = []
    for ago in range(1, 11):
        day = ref - timedelta(days=ago)
        rows.append({"facility_id": facility_id, "staff_id": staff_id,
                     "event_type": "clock_in", "event_at": ts(day, 13, 22),
                     "source": "staff_app"})
        rows.append({"facility_id": facility_id, "staff_id": staff_id,
                     "event_type": "clock_out", "event_at": ts(day, 21, 34),
                     "source": "staff_app"})
    # on shift right now, so the app shows a live "clocked in" state
    rows.append({"facility_id": facility_id, "staff_id": staff_id,
                 "event_type": "clock_in", "event_at": ts(ref, 13, 18),
                 "source": "staff_app"})
    ins_many("attendance_events", rows)


def seed_debt(facility_id: str, staff_ids: list[str], period_id: str) -> None:
    ins_many("future_debt_ledger", [{
        "facility_id": facility_id, "staff_id": staff_ids[idx], "debt_type": kind,
        "quantity": qty, "unit": "hours" if kind != "AN" else "count",
        "due_period_id": period_id, "status": "open", "note": note,
    } for idx, kind, qty, note in [
        (3, "TOIL", 8, "emergency cover — compensate next cycle"),
        (0, "CL", 12.5, "public holiday worked"),
        (2, "TOIL", 8, "emergency cover — compensate next cycle"),
        (6, "CL", 4, "shift extension"),
        (1, "AN", 1, "AN make-up owed"),
    ]])


def seed_notifications(facility_id: str, staff_id: str, profile_id: str) -> None:
    ins_many("notifications", [{
        "facility_id": facility_id, "staff_id": staff_id, "profile_id": None,
        "channel": "in_app", "event_type": event, "title": title, "body": body,
        "status": status, "sent_at": None if status == "queued" else datetime.now(
            timezone.utc).isoformat(),
    } for event, title, body, status in [
        ("roster_published", "July roster published",
         "Your shifts for 1–28 July are confirmed.", "read"),
        ("leave_decided", "Annual leave reviewed",
         "Your 12–16 July request is with the superintendent.", "sent"),
        ("cover_request", "Cover needed — P shift",
         "A P shift needs cover today. Tap to accept.", "sent"),
    ]])


def seed_report_registry(facility_id: str) -> None:
    ins_many("report_schedules", [{
        "facility_id": facility_id, "report_type": rtype, "icon": icon,
        "name_en": name_en, "name_zh": name_zh,
        "cron_label_en": cron_en, "cron_label_zh": cron_zh,
        "recipients_en": rec_en, "recipients_zh": rec_zh,
        "content_en": content_en, "content_zh": content_zh,
        "law_reference": law, "last_run_at": last, "next_run_at": nxt,
        "sort_order": i,
    } for i, (rtype, icon, name_en, name_zh, cron_en, cron_zh, rec_en, rec_zh,
              content_en, content_zh, law, last, nxt) in enumerate([
        ("monthly_staffing_compliance", "📊",
         "Monthly Staffing Compliance Report", "月度人手合規報告",
         "1st of every month, 08:00", "每月1日 08:00",
         ["Home Manager", "Assistant Home Manager"], ["院長", "助理院長"],
         ["Actual FT/PT headcount per shift vs Cap.459A minimum",
          "PT ratio statistics for specific-hour A/P shifts",
          "Staff over the monthly AN limit",
          "CL accrual hours and estimated liability",
          "SL/DSL days and agency replacement cost",
          "External workforce dependency and fairness Gini"],
         ["各更次 FT/PT 實際人數 vs Cap.459A 最低要求",
          "特定鐘點 A/P 更 PT 比例統計",
          "AN 超限員工名單",
          "CL 積壓時數及財務負債估算",
          "SL/DSL 日數及外購替更成本",
          "外購人手依賴度及公平度 Gini"],
         "Cap.459A s.11(1)(3)", "2026-07-01", "2026-08-01"),
        ("compliance_summary", "📋",
         "Quarterly Service Quality Report (SQS)", "季度服務質素報告（SQS）",
         "First day of every quarter, 08:00", "每季首日 08:00",
         ["Home Manager", "Assistant Home Manager", "SWD"], ["院長", "助理院長", "社署"],
         ["Staffing ratio pass rate and breach minutes",
          "Unresolved hard-constraint violations",
          "Threshold monitor status across all six checks"],
         ["人手比率達標率及違規分鐘", "未解決硬約束違規", "六項閾值監控狀態"],
         "SQS 3.2", "2026-07-01", "2026-10-01"),
        ("staff_register", "🏛️",
         "Annual Licence Declaration", "年度牌照申報",
         "1 January every year, 08:00", "每年1月1日 08:00",
         ["Home Manager", "Licensing Office"], ["院長", "牌照處"],
         ["RCH staff list (Annex 3.2 format)",
          "Rank, employment type and unit for every staff member",
          "Certificate register with expiry dates",
          "Medication-audit status per staff"],
         ["安老院員工名單（附件3.2格式）", "每名員工職級、僱用類別及所屬單位",
          "證書登記及到期日", "各員工藥物審核資格"],
         "Cap.459A s.9.6", "2026-01-01", "2027-01-01"),
    ])])

    ins_many("event_trigger_rules", [{
        "facility_id": facility_id, "trigger_code": code, "icon": icon,
        "label_en": label_en, "label_zh": label_zh, "action_en": action_en,
        "action_zh": action_zh, "sla_en": sla_en, "sla_zh": sla_zh,
        "law_reference": law, "sort_order": i,
    } for i, (code, icon, label_en, label_zh, action_en, action_zh,
              sla_en, sla_zh, law) in enumerate([
        ("STAFF_JOIN_LEAVE", "👤", "Staff Joining / Leaving", "員工入職/離職",
         "Auto-update SWD staff list + notify Licensing Office",
         "自動更新社署員工名單 + 通知牌照處",
         "Within 1 working day", "1個工作天內", "Cap.459A s.9.6"),
        ("INCIDENT_REPORTED", "🚨", "Notifiable Incident", "特別事故登記",
         "Generate pre-filled Annex 8.3 draft + remind 24h reporting deadline",
         "生成附件8.3預填草稿 + 提醒24小時通報時限",
         "Immediate", "即時", "Cap.459A s.8.3"),
        ("INFECTION_OUTBREAK", "🦠", "Infection Control Event", "感染控制事件",
         "Activate infection control protocol + generate Annex 13.2 + alert staff",
         "啟動感染控制流程 + 生成附件13.2呈報表 + 通知相關員工",
         "Immediate", "即時", "Cap.459A s.13 / Cap.599"),
        ("RESIDENT_ADMISSION", "🛏️", "Resident Admission", "住客入住",
         "Create individual care plan reminder + auto-prompt review after 6 months",
         "建立個人照顧計劃提醒 + 6個月後自動提示更新",
         "Day of admission", "入住當日", "Cap.459A s.12"),
    ])])


def seed_facility_events(facility_id: str, ref: Date) -> None:
    ins_many("facility_events", [{
        "facility_id": facility_id, "event_type": etype,
        "date": (ref - timedelta(days=ago)).isoformat(), "title": title,
    } for etype, ago, title in [
        ("STAFF_JOIN_LEAVE", 21, "PCW joined — imported labour contract"),
        ("STAFF_JOIN_LEAVE", 6, "PTA resigned — 1 month notice"),
        ("RESIDENT_ADMISSION", 18, "New resident — East Wing"),
        ("RESIDENT_ADMISSION", 12, "New resident — West Wing"),
        ("RESIDENT_ADMISSION", 4, "New resident — East Wing"),
    ]])


def seed_regulatory_docs() -> None:
    ins_many("regulatory_documents", [{
        "facility_id": None, "doc_code": code, "name_en": name_en, "name_zh": name_zh,
        "key_clause_en": clause_en, "key_clause_zh": clause_zh,
        "version_label": version, "last_synced_at": synced, "sync_status": "synced",
        "sort_order": i,
    } for i, (code, name_en, name_zh, clause_en, clause_zh, version, synced) in enumerate([
        ("CAP459A", "Residential Care Homes (Elderly Persons) Regulation Cap.459A",
         "《安老院規例》Cap.459A", "s.11(3) PT headcount cap", "s.11(3) PT人數上限",
         "2024-06-16", "2024-06-16"),
        ("COP_2024", "Code of Practice for RCH(E) — June 2024 Revision",
         "《安老院實務守則》2024年6月修訂版", "Chapter 9: Agency Services",
         "第9章 外購服務", "2024-06", "2026-04-01"),
        ("SQS_16", "SWD 16 Service Quality Standards", "社署16項服務質素標準",
         "SQS 8: Legal Compliance", "SQS 8 法律合規", "2026", "2026-04-01"),
        ("LSG_TIPS", "LSG SmartTips April 2026 Edition", "LSG SmartTips 2026年4月版",
         "Recognised / Non-recognised Items", "認可/不認可項目", "2026-04", "2026-04-01"),
    ])])


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print("Wiping demo facilities + dev users ...")
    wipe()

    dates_a = dates_for(PERIOD_A_START, PERIOD_A_DAYS)
    dates_b = dates_for(PERIOD_B_START, PERIOD_B_DAYS)
    period_a_start, period_a_end = Date.fromisoformat(dates_a[0]), Date.fromisoformat(dates_a[-1])
    today = Date.today()
    # Anchor the Phase 3 activity inside the period so "today" always has data.
    ref = today if period_a_start <= today <= period_a_end else period_a_end

    # ---- calendar (global HK public holiday) ----
    sb.table("calendar_days").delete().eq("date", "2026-07-01").is_("facility_id", "null").execute()
    ins("calendar_days", {
        "facility_id": None, "date": "2026-07-01", "day_type": "public_holiday",
        "holiday_name": "HKSAR Establishment Day", "is_agency_allowed": True,
        "staff_cost_multiplier": 2.0,
    })
    seed_regulatory_docs()

    # ================= HOME A (28-day cycle) =================
    print("Seeding Home A ...")
    fa = ins("facilities", {
        "code": "A", "name": "Care Home A (救世軍式)", "type": "RCHE",
        "scheduling_cycle_days": 28, "capacity": 85,
    })
    east = ins("facility_units", {"facility_id": fa, "unit_type": "wing", "name": "East Wing", "code": "EW"})
    west = ins("facility_units", {"facility_id": fa, "unit_type": "wing", "name": "West Wing", "code": "WW"})

    a_staff = [
        ("余逸詩", "Yu Yat Sze", "RN", "local_ft", east, "F"),
        ("梁嘉琪", "Leung Ka Kei", "EN", "local_ft", west, "F"),
        ("王雅琛", "Wong Yat Sum", "HW", "local_ft", east, "F"),
        ("何啟晴", "Ho Kai Ching", "CW", "local_ft", west, "F"),
        ("黃司琦", "Wong Sze Kai", "PTA", "local_ft", east, "M"),
        ("黃靜賢", "Wong Jing Yin", "PCW", "imported_labor", west, "F"),
        ("李紹洪", "Li Shao Hung", "AW", "local_ft", east, "M"),
    ]
    a_ids, a_ranks, a_units = [], [], []
    for name, en, rank, emp, unit, gender in a_staff:
        sid = ins("staff", {
            "facility_id": fa, "name": name, "name_en": en, "rank": rank,
            "employment_type": emp, "primary_unit_id": unit, "gender": gender,
            "contracted_hours": 44, "is_audited_for_medication": rank in ("RN", "EN", "HW"),
            "is_mentor": rank == "RN", "status": "active",
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
    seed_task_definitions(fa)

    period_a = ins("roster_periods", {
        "facility_id": fa, "period_start": dates_a[0], "period_end": dates_a[-1],
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
    roster_a = seed_roster(fa, ver_a, a_ids, a_ranks, a_units, pattern_a,
                           SHIFT_TIMES_A, tasks_a, dates_a)

    def shift_lookup_a(staff_id: str, day: Date) -> str | None:
        """The staff member's working shift id on `day`, else None."""
        want = day.isoformat()
        for shift_id, (i, sid, d, code) in zip(roster_a["shift_ids"], roster_a["meta"]):
            if sid == staff_id and dates_a[d] == want and SHIFT_TIMES_A[code][3]:
                return shift_id
        return None

    # ================= HOME B (natural month) =================
    print("Seeding Home B ...")
    fb = ins("facilities", {
        "code": "B", "name": "Care Home B (多層院舍)", "type": "RCHE",
        "scheduling_cycle_days": 31, "capacity": 60,
    })
    f2 = ins("facility_units", {"facility_id": fb, "unit_type": "floor", "name": "2/F", "code": "2F"})
    f6 = ins("facility_units", {"facility_id": fb, "unit_type": "floor", "name": "6/F", "code": "6F"})
    b_staff = [
        ("陳大文", "Chan Tai Man", "HCA", "imported_labor", f2, "M"),
        ("李美娟", "Li Mei Kuen", "HW", "local_ft", f6, "F"),
        ("王志強", "Wong Chi Keung", "EN", "local_ft", f6, "M"),
    ]
    b_ids, b_ranks, b_units = [], [], []
    for name, en, rank, emp, unit, gender in b_staff:
        sid = ins("staff", {
            "facility_id": fb, "name": name, "name_en": en, "rank": rank,
            "employment_type": emp, "primary_unit_id": unit, "gender": gender,
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
        "facility_id": fb, "period_start": dates_b[0], "period_end": dates_b[-1],
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
    seed_roster(fb, ver_b, b_ids, b_ranks, b_units, pattern_b, SHIFT_TIMES_B, {}, dates_b)

    # ---- auth users + profiles ----
    print("Creating dev auth users ...")
    super_a = make_user("super_a@emma.local", "superintendent", fa)
    make_user("admin_a@emma.local", "admin", fa)
    make_user("staff_a@emma.local", "staff", fa, staff_id=a_ids[0])
    make_user("super_b@emma.local", "superintendent", fb)

    prof_a = sb.table("users_profile").select("id").eq("auth_user_id", super_a).execute().data[0]["id"]
    # Resident counts are the ratio denominator, so they have to be plausible for
    # the seeded headcount: 7 staff cannot lawfully serve 80 residents under the
    # Code of Practice ratios, and an impossible fixture makes every compliance
    # screen fail for a reason that has nothing to do with the roster. 18 residents
    # across two wings leaves a realistic mix — most windows pass, and the genuine
    # gaps (nobody on an RN's rest day, 21:30–07:00 covered by one person) show up.
    seed_resident_counts(fa, [(east, 10), (west, 8)], prof_a, dates_a)
    seed_resident_counts(fb, [(f2, 8), (f6, 7)], prof_a, dates_b)

    # ---- Phase 3 operations layer (Home A carries the demo activity) ----
    print("Seeding Phase 3 operations data ...")
    seed_roi_settings(fa, prof_a, total_budget=1_600_000, salary_budget=1_190_800,
                      vacancies={"RN": 1, "HCA": 2})
    seed_roi_settings(fb, prof_a, total_budget=900_000, salary_budget=640_000,
                      vacancies={})
    seed_leave_requests(fa, a_ids, prof_a, ref)
    seed_incidents(fa, a_ids, prof_a, ref, shift_lookup_a)
    seed_agency(fa, ref)
    seed_attendance(fa, a_ids[0], ref)
    seed_debt(fa, a_ids, period_a)
    seed_notifications(fa, a_ids[0], prof_a)
    seed_report_registry(fa)
    seed_facility_events(fa, ref)

    print("\nSeed complete.")
    print("  Roster: %s .. %s (%d days), Home B %d days"
          % (dates_a[0], dates_a[-1], len(dates_a), len(dates_b)))
    print("  Dev logins (password: %s):" % DEV_PASSWORD)
    print("    super_a@emma.local  (Superintendent, Home A)")
    print("    admin_a@emma.local  (Admin, Home A)")
    print("    staff_a@emma.local  (Staff app, Home A — 余逸詩 / Yu Yat Sze)")
    print("    super_b@emma.local  (Superintendent, Home B)")


if __name__ == "__main__":
    main()
