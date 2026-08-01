# NAAC TAH configuration inputs

The source data for MVP tasks **2.2** (facility config), **2.3** (shift
dictionary) and **4.1** (task codes and escort locations). Cherry Siu attached
these to ClickUp tasks
[2.2](https://app.clickup.com/t/86d3bh6a3) and
[4.1](https://app.clickup.com/t/86d3bh6c2) on 31 Jul 2026, with her own English
translations alongside the Chinese originals.

They arrived as links in the ClickUp comment bodies rather than as task
attachments, which is why the earlier API check for attachments came back empty.

## What is in this repository

| File | What it is |
|---|---|
| `shift_codes_hours_EN.md` | Cherry's guide to the code grammar: letter = duration, digits = start time, `s`/`x`/`v` modifiers, combined codes |
| `rostering_rules_EN.md` | The constraint set — dual 44h/49h hours, `#` quotas, AN→NO→O, staffing minimums per role and day |
| `escort_location_codes_EN.md` | The 18 medical-escort location codes |
| `annotations_workbook_EN.md` | How to read `NAAC更期代號註解.xlsx` |
| `duty_roster_EN.md` | How to read the Feb–May 2026 duty roster sample |
| `../../emma-ai-app/emma_core/importers/data/naac_shift_codes.csv` | **279 shift codes** extracted from the workbook's `代號及時數` sheet, UTF-8 |
| `../../emma-ai-app/emma_core/importers/data/naac_escort_locations.csv` | 20 places → 18 codes |
| `../../emma-ai-app/emma_core/importers/data/naac_task_codes.csv` | 61 task markers read off the weekly roster legends |

The two CSVs Cherry attached are Big5-encoded and one of them is a partial
transcription of the workbook. The CSVs above were extracted from the `.xlsx`
instead, because the workbook sheet is the fuller and more current copy — 279
codes against the CSV's ~40 — and re-encoded to UTF-8.

## What is deliberately not in this repository

`NAAC更期代號註解.xlsx` and `NAACTAHDuty(255-0507).xlsx`, ~500 KB each.

They hold six weeks of real duty rosters. The `姓名` column has been mostly
cleared, but not entirely, and the summary sheets break hours, day-off counts and
night-shift distribution down per person. Cherry's covering comment says the
files contain no personal data; her own workbook guide says the roster sheets
contain staff names. The second reading is the correct one.

So the code dictionaries were extracted and committed, and the workbooks were
not. Get them from the ClickUp comment when you need the roster sample; they are
the fixture for import testing, not configuration.

The same reasoning applies to five named staff in `rostering_rules_EN.md` — three
with a personal `#` quota, one who may not take N shifts, one who asks for fewer
A shifts. Those are replaced with `STAFF_Q1`…`STAFF_N1`. The rule shape belongs
in git; the mapping to real people belongs in `facility_json_configs` behind RLS,
seeded from the home's own data.

## Reading a roster cell

    A7# TMH
    │ │  └── escort location — per assignment, not per task definition
    │ └───── duty supervisor for this shift
    └─────── shift code: starts 07:00, letter A = 8 hours, so ends 15:00

`A7N10` is one cell holding two disjoint windows: 07:00–15:00 and 22:00–07:00 the
next day, 17 paid hours. That is the same shape as Home A's `A/N` split shift and
is stored the same way — `shift_definitions.segments`, with `paid_minutes` summed
across the windows rather than measured across the gap.
