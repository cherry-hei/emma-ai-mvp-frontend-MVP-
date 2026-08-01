# NAAC Medical Escort Location Codes

These codes are used in roster cells to indicate where a staff member is escorting a resident for medical appointments. Format in roster: `shift_code + location_code` (e.g. `A7 TMH` = A-shift, escorting to Tuen Mun Hospital).

The code is **per-assignment** (attached to a specific staff member's shift cell on a specific date), not per-task-definition.

| Location | Code | Full Name |
|----------|------|-----------|
| TMH Psychiatric Out-patient Dept | TMH | Tuen Mun Hospital POD |
| TMH General Out-patient Dept | TMC | Tuen Mun General OPD Clinic |
| Yan Oi General Out-patient Clinic | YOPC | Yan Oi Hospital OPC |
| Social Hygiene Clinic | SHC | Social Hygiene Clinic |
| Tuen Mun Hospital | TMH | Tuen Mun Hospital (general) |
| TMH Ambulatory Care Centre | ACC | TMH ACC |
| Yan Oi Dental Clinic | YODC | Yan Oi Dental Clinic |
| Yan Oi Tong Dental Clinic | YOTDC | Yan Oi Tong Dental Clinic |
| Tuen Mun Eye Centre | TMEC | Tuen Mun Eye Centre |
| Castle Peak Hospital | CPH | Castle Peak Hospital |
| CPH Ming Sum House | CPH | Castle Peak Hospital (Ming Sum House) |
| Wu Hong Clinic | WHC | Wu Hong Health Centre |
| Yan Oi Chest Clinic | YOCC | Yan Oi Chest/Pulmonary Clinic |
| Shamshuipo Blind Association | 深盲輔 | HK Society for the Blind (SSP) |
| Yuen Long Blind Association | 元盲輔 | HK Society for the Blind (YL) |
| Pok Oi Hospital | POH | Pok Oi Hospital |
| Ying Oi Dental | 盈愛 | Ying Oi Dental Clinic |
| Tin Shui Wai Hospital | TSW | Tin Shui Wai Hospital |
| Haven of Hope Hospital | HHH | Haven of Hope Hospital |
| Tseung Kwan O Hospital | TKO | Tseung Kwan O Hospital |

**Note for implementation:** Keep the short code (TMH, CPH, etc.) as the system value. The Chinese location names above are for reference only — the roster uses the short codes directly.
