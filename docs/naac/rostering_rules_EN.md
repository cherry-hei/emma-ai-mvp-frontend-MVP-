# NAAC Rostering Arrangement Rules (TAH Tuen Mun)

This document defines the scheduling rules, constraints, and staffing requirements for NAAC TAH (Tai Hing) residential home.

> **Source:** translated by Cherry Siu from `NAAC編更安排1.docx`, attached to
> ClickUp task 2.2 on 31 Jul 2026.
>
> **Names redacted, 1 Aug 2026.** The original names five staff members and
> attaches a personal quota or a personal preference to each. Cherry's covering
> comment says the files carry no personal data, but per-person rostering quotas
> and stated preferences are employee personal data, and a public git history is
> the wrong place for them. They are replaced below with stable keys
> (`STAFF_Q1`…`STAFF_Q3`, `STAFF_P1`, `STAFF_N1`). The real mapping belongs in
> `facility_json_configs` under `duty_supervisor_quota` and
> `staff_scheduling_preferences`, behind RLS, seeded from the home's own data —
> not in this file. Flagged back to Cherry on 2.2.

---

## 1. Working Hours System (Dual-Track)

| Staff Category | Weekly Hours | Daily Average | Applies To |
|----------------|-------------|---------------|------------|
| Office staff | 44 hours | 8h per day | Officers, social workers, clerks |
| Therapists | 44 hours | 9h per shift (fewer days) | PT, OT |
| Frontline staff | 49 hours | 8h10m (8.1667h) per day | WA, PCW, Cook, WM |

**Rest days per 6-week cycle:**
- Office staff: 9 rest days per 6 weeks
- Frontline staff: 6 rest days per 6 weeks

---

## 2. Duty Supervisor (#) Allocation

The `#` symbol in roster cells marks the duty supervisor for that shift. This is a per-shift responsibility marker, NOT a separate role — it does not grant extra approval rights.

**Per-person quotas (per scheduling cycle):**

| Staff Member | # Shifts per Cycle |
|---|---|
| HP (Nurses) | 12 each |
| `STAFF_Q1` (hostel instructor) | 15 |
| `STAFF_Q2` (hostel instructor) | 13 |
| `STAFF_Q3` (hostel instructor) | 9 |

**Meal break rules for duty supervisors:**
- Weekdays: Regular staff eat at 6:15pm; Duty supervisor eats at 7:15pm
- Sat/Sun/PH: Regular staff eat at 5:45pm; Duty supervisor eats at 6:45pm

---

## 3. Shift Distribution Rules

### General Rules:
- N shifts, duty supervisor shifts (#), A shifts, and P shifts must be **evenly distributed** among eligible staff
- **`STAFF_Q1`** must NOT be assigned N shifts
- **`STAFF_Q2`** should be assigned one extra N shift
- Do NOT schedule more than 8 consecutive working days
- AN shift (double shift): next day MUST be NO (rest after overnight), then O (statutory rest day). Sequence: AN → NO → O

### Sequencing Constraints:
- Day before AN shift: CANNOT assign P shift (staff prefer A7/A1030/A9 before AN)
- After A230 or E-position shift: CANNOT assign A7 the next day
- Kitchen duty (入廚) and A230e position: CANNOT be scheduled on consecutive days

---

## 4. HP (Nursing) Staffing Requirements

| | Mon–Sat | Sunday |
|---|---|---|
| **A shift** | 1× A7# (duty supervisor) + 2× A7. If only 1 nursing staff on A7, assign one colleague for medication verification (*). If no HP/PWR available, assign social worker. | 1× A7# (duty supervisor) + 1× A7 morning. Same medication rule applies. |
| **P shift** | 1× A230# (duty supervisor) + 2× P2/A1. One acts as deputy duty supervisor (#). | 1× A230# (duty supervisor) + 1–2× P2/A1. One acts as deputy (#). |
| **N shift** | No HP required on N shift (Mon–Sat) | 1× N shift (HP only on Sundays) |

---

## 5. WA (Welfare Assistant) Staffing Requirements

### Daily Task Positions (A shift):

| Position Code | Tasks |
|---|---|
| A7 e | Wash bedsheets, apply ointment, distribute clothing, clean ground floor public toilets |
| A7 清 | Supervise dining hall, breakfast supervision, escort residents to appointments, restraint records (7am–3pm), clean dormitory area |
| A1030 約 | Restraint records (10am–6:30pm), check every 2 hours and sign, care for residents staying in dormitory |
| 清 | Clean dormitory area |
| 洗 | Clean toilets rooms 1–15 (morning: male toilets; afternoon: female + staff toilets) |
| * | Assist with medication dispensing |

### Daily Task Positions (P shift):

| Position Code | Tasks |
|---|---|
| P2 心 | Supervise dining hall, restraint records (3–9pm), clean ground floor public toilets |
| P2 心 | Supervise dining hall, clean ground floor public toilets |
| P2*9肌 | Assist with 9pm medication, muscle exercise for specific residents (8–9pm) + records, prepare nutritional milk |
| A230 e | Wash and handle resident clothing, supervise dinner, apply ointment if no nursing team, clean ground floor public toilets |
| K10 | Long-N colleague's shift (9h per shift = 5 working days; other WAs work 6 days) |

### WA Scheduling Rules:
- If sufficient staff: assign 4× A7, others on A9 or day off
- AN shifts, E-position, A shifts must be evenly distributed
- Weekday meals: 6:15pm first batch, 7:15pm second batch
- Sat/Sun/PH: Residents eat 5:30pm; staff 5:45pm first batch (2 心-positions), 6:45pm second batch (E-position and *9肌)
- WA gets one statutory rest day per week (red O). AN shift sequence: AN → NO (next day) → O (statutory rest day)
- Every Sunday and when fewer than 2 cooks are working: assign extra P-shift WA to kitchen duty (shift = A130)
- **`STAFF_P1`** requests fewer A shifts (personal constraint)
- Every Sunday morning: 1 WA assigned to outdoor holiday activity escort

---

## 6. WM (Workman) Staffing

| | Mon–Sat | Sunday |
|---|---|---|
| Staff needed | 2 WM | 1 WM |
| Shifts | 1× A8x + 1× A9x | 1× A8x |

---

## 7. Kitchen Staffing

| | Mon–Fri | Sat–Sun |
|---|---|---|
| Cook 1 | A610 (06:10–14:20) | 2 cooks rotate days off |
| Cook 2 | A130 (13:00–21:00) | Working cook: B930 |
| Kitchen Assistant | A130 (must be A130) | Off on Sundays; shift = P1 when working |

---

## 8. Compliance Rule (Residential Care Home Regulation)

**18:00–07:00:** Minimum 2 staff on duty at all times (this is why B130/A2s/A220x WA shifts exist — to ensure overnight coverage).

**10:00–16:00:** Minimum 1 nurse OR 2 HW on duty (from NAAC RBAC doc).

---

## 9. Shift Code Quick Reference Table

| Code | Hours | Time | Category |
|------|-------|------|----------|
| A610 | 8h | 06:10–14:20 | AM |
| A7 | 8h | 07:00–15:00 | AM |
| A7x | 8h10m | 07:00–15:10 | AM (frontline) |
| A7s | 8.5h | 07:00–15:30 | AM (extended) |
| A7N10 | 17h | 07:00–15:00 + 22:00–07:00 | AM + Night combined |
| A7N1015 | 17h | 07:00–15:00 + 22:15–07:15 | AM + Night combined |
| A9 | 8h | 09:00–17:00 | AM |
| A9x | 8h10m | 09:00–17:10 | AM (frontline) |
| A1030 | 8h | 10:30–18:30 | AM (late start) |
| A230 | 8h | 14:30–22:30 | PM |
| B7 | 9h | 07:00–16:00 | Extended AM |
| G7 | 7h | 07:00–14:00 | Short AM |
| G7s | 7.5h | 07:00–14:30 | Short AM (extended) |
| P1 | 9h | 13:00–22:00 | PM |
| P2 | 8h | 14:00–22:00 | PM |
| K10 | 10h | 22:00–08:00 | Long Night |
| N10 | 9h | 22:00–07:00 | Night |
| N1015 | 9h | 22:15–07:15 | Night (variant) |
| O | 0h | Day off | Red = statutory rest day |
| NO | 0h | Post-overnight rest | Must follow AN shift |
| PH | 0h | Public holiday | |
| AL | 8h/9h/8h10m | Annual leave | Varies by staff category |
| SL | 8h/8h10m | Sick leave | Varies by staff category |
