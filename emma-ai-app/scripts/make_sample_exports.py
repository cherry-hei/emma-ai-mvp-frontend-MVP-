"""Render sample 7.1 / 7.2 exports for design sign-off.

Cherry, 1 Aug 2026: "yes, please send me sample PDF and XLSX files so I can check
layout and Chinese rendering before sign-off."

The samples are rendered from a synthetic payload rather than dumped from the
database, for two reasons:

* it is the layout under review, not the data. A sample built by hand can carry
  the awkward cases on purpose - a 12-hour split duty, an OT cell, a unit-scoped
  event, a name that is long in English and short in Chinese - which a random
  fortnight of real roster may not contain at all;
* the real roster is employee personal data. Nothing about checking column widths
  and Traditional Chinese glyphs needs a real person's shifts, and the
  conservative reading of PDPO minimisation says do not send them.

The renderer, the column set and the draft handling are the production ones -
`emma_core.services.render` is imported, not reimplemented - so what Cherry
approves is what the download endpoint emits.

    python -m scripts.make_sample_exports [outdir]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from emma_core.services import render  # noqa: E402

# Placeholder staff. Real names live in the database behind access control; the
# code dictionaries and anything committed use placeholders (Cherry, 1 Aug).
_STAFF = [
    ("STAFF_001 陳大文", "Chan Tai Man", "RN", "local_ft"),
    ("STAFF_002 李美玲", "Li Mei Ling", "HW", "local_ft"),
    ("STAFF_003 黃志強", "Wong Chi Keung", "CW", "local_pt"),
    ("STAFF_004 何淑儀", "Ho Suk Yi", "HCA", "local_ft"),
    ("STAFF_005 林嘉豪", "Lam Ka Ho", "WA", "agency"),
]

# Both homes' cell styles, deliberately mixed: NAAC embeds the task in the cell
# (A7#清), Salvation Army does not (A2N, A3 OT P2).
_CELLS = [
    ("2026-08-03", 0, "A7", "07:00", "15:00", 7.5, "3/F", "藥物核對, 清潔督導", False, ""),
    ("2026-08-03", 1, "A2N", "07:00", "07:15", 16.0, "3/F", "夜更交更", False, ""),
    ("2026-08-03", 2, "P2", "13:00", "21:00", 7.5, "1/F", "個人護理", False, ""),
    ("2026-08-03", 3, "A3", "13:00", "21:00", 7.5, "1/F", "餵食", False, ""),
    ("2026-08-03", 4, "A1", "07:00", "15:00", 7.5, "1/F", "", True, ""),
    ("2026-08-04", 0, "O", "", "", 0, "3/F", "", False, "剪髮 (+1 CW|HCA)"),
    ("2026-08-04", 1, "S", "", "", 0, "3/F", "", False, "剪髮 (+1 CW|HCA)"),
    ("2026-08-04", 2, "A7", "07:00", "15:00", 7.5, "1/F", "磅重", False, "每月磅重"),
    ("2026-08-04", 3, "7A", "07:00", "19:00", 11.0, "1/F", "個人護理, 洗澡", False, "每月磅重"),
    ("2026-08-04", 4, "P3", "13:00", "21:00", 7.5, "1/F", "", True, "每月磅重"),
    ("2026-08-05", 0, "A7", "07:00", "15:00", 7.5, "3/F", "藥板核對", False, "CGAT 評估 (+1 RN, +1 HW)"),
    ("2026-08-05", 1, "AN", "07:00", "07:00", 16.0, "3/F", "夜更藥物", False, "CGAT 評估 (+1 RN, +1 HW)"),
    ("2026-08-05", 2, "DO", "", "", 0, "1/F", "", False, ""),
    ("2026-08-05", 3, "P2", "13:00", "21:00", 7.5, "1/F", "轉移, 如廁", False, ""),
    ("2026-08-05", 4, "A3 OT P2", "13:00", "23:00", 9.5, "1/F", "超時 2 小時", True, ""),
]


def roster_export_sample() -> dict:
    rows = []
    for date, who, code, start, end, hours, unit, tasks, agency, events in _CELLS:
        label, name_en, rank, employment = _STAFF[who]
        rows.append({
            "date": date,
            "staff": f"{label} / {name_en}",
            "staff_zh": label.split(" ", 1)[-1],
            "rank": rank,
            "employment_type": employment,
            "shift_type": code,
            "start_time": start,
            "end_time": end,
            "paid_hours": hours,
            "unit": unit,
            "tasks": tasks,
            "is_agency": agency,
            "events": events,
        })
    return {
        "columns": [
            {"key": "date", "label": "Date"}, {"key": "staff", "label": "Staff"},
            {"key": "staff_zh", "label": "姓名"}, {"key": "rank", "label": "Rank"},
            {"key": "employment_type", "label": "Employment"},
            {"key": "shift_type", "label": "Shift"},
            {"key": "start_time", "label": "Start"}, {"key": "end_time", "label": "End"},
            {"key": "paid_hours", "label": "Paid hours"},
            {"key": "unit", "label": "Unit"}, {"key": "tasks", "label": "Task codes"},
            {"key": "is_agency", "label": "External"},
            {"key": "events", "label": "Events"},
        ],
        "rows": rows,
        "meta": {
            "description": "Published roster with task codes and events (樣本 / sample)",
            "period_start": "2026-08-03", "period_end": "2026-08-05",
            "roster_version_id": "sample", "roster_version_label": "Cycle 8 v2 (樣本)",
            "roster_version_status": "published",
            "cells": len(rows),
            "working_cells": len([r for r in rows if r["paid_hours"]]),
            "paid_hours_total": round(sum(r["paid_hours"] for r in rows), 1),
        },
    }


def compliance_summary_sample() -> dict:
    rows = [
        ("Staffing ratio", "Pass rate", "96.4%", "FAIL"),
        ("Staffing ratio", "Breach minutes", 135, "FAIL"),
        ("Hard constraints", "Unresolved violations", 0, "PASS"),
        ("Hard constraints", "Conflict rate", "2.1%", "INFO"),
        ("Threshold monitor", "住客與職員比例 Resident-to-staff ratio", 3, "WARN"),
        ("Threshold monitor", "連續夜更 Consecutive night shifts", 0, "PASS"),
        ("Threshold monitor", "證書到期 Certificates expiring", 2, "WARN"),
        ("Workforce", "External dependency", "18.9%", "PASS"),
        ("Workforce", "Agency cost (period)", "HK$41,600", "INFO"),
        ("Fairness", "N Gini", 0.14, "PASS"),
    ]
    return {
        "columns": [
            {"key": "section", "label": "Section"}, {"key": "metric", "label": "Metric"},
            {"key": "value", "label": "Value"}, {"key": "status", "label": "Status"},
        ],
        "rows": [{"section": s, "metric": m, "value": v, "status": st}
                 for s, m, v, st in rows],
        "meta": {
            "description": "SWD compliance summary (樣本 / sample)",
            "period_start": "2026-08-01", "period_end": "2026-08-28",
            "roster_version_id": "sample", "roster_version_label": "Cycle 8 v2 (樣本)",
            "roster_version_status": "published",
        },
    }


SAMPLES = {
    # (report_type, title) -> payload builder. Titles match TITLES in reports.py.
    "roster_export": ("Roster export", roster_export_sample),
    "compliance_summary": ("Compliance summary", compliance_summary_sample),
}


def main(outdir: str | None = None) -> None:
    out = Path(outdir or "sample-exports")
    out.mkdir(parents=True, exist_ok=True)
    for report_type, (title, build) in SAMPLES.items():
        payload = build()
        for fmt, renderer in (("xlsx", render.to_xlsx), ("pdf", render.to_pdf)):
            path = out / f"{report_type}-sample.{fmt}"
            path.write_bytes(renderer(payload, title=title))
            print(f"{path}  {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
