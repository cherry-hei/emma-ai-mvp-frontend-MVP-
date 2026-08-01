# NAAC Shift Code Annotations Workbook — English Guide

**Original file:** `NAAC更期代號註解.xlsx` (attached separately as the original — the roster data sheets contain staff names and are best kept as-is for reference)

## Sheet Structure

| Sheet Name | English | Rows | Description |
|---|---|---|---|
| 更期代號註解 | Shift Code Annotations | 55 | Master list of all shift codes with hours, time ranges, and categories |
| 代號及時數(old) | Codes & Hours (old version) | 325 | Historical version — ignore |
| 代號及時數 | Codes & Hours (current) | 295 | Full shift code dictionary with columns: Code, Hours, AM fraction, PM fraction, Sleepover, PH, Night, DO, Remarks, Category |
| 覆診地點代號 | Escort Location Codes | 21 | Medical appointment location abbreviations |
| TAHDuty(week1–6) | Weekly Roster (6 weeks) | ~130 each | Actual duty roster by week. Rows = staff (grouped by role: HP, HW, SW, WA, PCW, Cook, WM). Columns = days. |
| TAHDuty(hours) | Hours Summary | 67 | Total hours worked per staff member for the period |
| TAHDuty(PH&dayoff) | PH & Day-off Count | 69 | Public holidays and days off per staff |
| TAHDuty(DO更次數) | DO Shift Count | 24 | Duty-supervisor shift counts per person |
| TAHDuty(AP更) | A/P Shift Distribution | 56 | Count of A-shifts and P-shifts per person (for fairness check) |
| TAHDuty(C更男女) | C-shift Gender | 53 | Sleepover shift distribution by gender |
| TAHDuty(N更男女) | N-shift Gender | 52 | Night shift distribution by gender (Sunday N cannot be male — `STAFF_N1`; name redacted, see rostering_rules_EN.md) |
| TAHDuty(用膳代號) | Meal Codes | 42 | Meal break timing codes |

## Column Headers in "代號及時數" Sheet

| Column | English |
|---|---|
| 更期代號 | Shift Code |
| 時數 | Hours |
| 早更 | AM shift fraction (1 = full AM, 0.5 = half) |
| 午更 | PM shift fraction |
| 留宿更 | Sleepover shift fraction |
| PH | Public Holiday fraction |
| 通宵更 | Night shift fraction |
| DO更 | Duty-supervisor shift (1 = includes DO responsibility) |
| Remarks | Time range (e.g. "7a-3p") |
| 更期類別 | Shift category description |

## Key Column Headers in Weekly Roster Sheets

| Chinese | English |
|---|---|
| 職位 | Position/Role |
| 姓名 | Staff Name |
| 日期 columns | Date (day number) |
| 時數 | Hours |
| 工作天 | Working Days |
| 休息日 | Rest Days |

## How to Read a Roster Cell

A cell like `A7# TMH` means:
- `A7` = shift starting 07:00, 8 hours
- `#` = duty supervisor for this shift
- `TMH` = escorting resident to Tuen Mun Hospital

A cell like `A7N10` means:
- Split shift: 07:00–15:00 (A7) then 22:00–07:00 (N10) = 17 total hours
