# NAAC TAH Duty Roster (Feb–May 2026) — English Guide

**Original file:** `NAACTAHDuty(255-0507).xlsx` (attached separately — contains actual staff rosters)

## Overview

This is the real duty roster for NAAC Tai Hing (TAH) residential home covering a 6-week scheduling cycle from February to May 2026. It demonstrates the actual application of all shift codes, constraints, and staffing rules described in the rostering rules document.

## Sheet Structure

Same structure as the annotations workbook (weekly roster sheets + summary reports). See `NAAC_shift_annotations_workbook_README_EN.md` for column definitions.

## Key Implementation Notes for Kien

1. **Staff are grouped by role** in the roster: HP (nurses) at top, then HW, SW, Hostel Instructors, WA, PCW, Cook, WM
2. **Each row = one staff member**, each column = one date
3. **Cell values** are shift codes from the dictionary (A7, P2, N10, O, AL, SL, etc.) optionally followed by task codes (e, 清, 洗, *, #) and/or location codes (TMH, CPH, etc.)
4. **Summary sheets** (hours, PH&dayoff, DO count, AP shifts, gender) are auto-calculated reports — these map to your Reports R1–R4 feature
5. **The # count per person** in the DO sheet validates the quota rule (12/15/13/9 per person per cycle)
6. **Red O vs black O** in the original: Red = statutory rest day (法定休息日), Black = regular day off (休班日). Both show as "O" in the cell but have different legal implications for OT calculation.

## What to Build From This

- **Shift code config (2.2):** Import the full dictionary from `NAAC_shift_codes_and_hours_EN.md`
- **Constraint engine (2.3):** Implement the sequencing rules from `NAAC_rostering_rules_EN.md` (AN→NO→O, no P before AN, no A7 after A230/E, no consecutive kitchen days, etc.)
- **Task code assignment (4.1):** Parse task markers (e, 清, 洗, *, #, 約, 心, 肌) from roster cells
- **Reports:** The summary sheets show exactly what reports R1–R4 should output
- **Fairness checks:** AP shift distribution and gender distribution sheets = KPI data for the shift fairness metric
