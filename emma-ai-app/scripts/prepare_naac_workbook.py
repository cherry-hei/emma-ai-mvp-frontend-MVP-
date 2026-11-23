"""Build private M3 preview assets from Gary's 28 Sep to 8 Nov workbook."""

import argparse
import hashlib
import json
from copy import copy
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

SOURCE_SHA = "f577a07e848b2a2cd52ceb006c2c27106b1395d0db7090888af1d36fbfa90b30"
CONFIRMATION_SHA = "627acd2af249a51feee53893ddb3b51daf42ff645460241e3ff2399586717e09"
ORIGINAL_SOURCE_SHA = "7cba97ef85338f8c6337bc9793ffcd7c2d31f549f9303e8f95be6306f9065bd0"
ORIGINAL_CONFIRMATION_SHA = "a269e6c0bb89eb9d52fb402c389515fc4b37df86f9aea1ba53467f8a2730afd4"
WEEKS = [f"Week{i}" for i in range(1, 7)]
SHEETS = [
    "Shift Code Legend", "Codes & Hours (old)", "Codes & Hours",
    "Clinic Location Codes", *WEEKS[:5], "Sheet2", WEEKS[5], "Hours",
    "PH & Off", "DOCounts", "APShifts", "CGender", "NGender", "MealCodes",
]
ORIGINAL_SHEETS = [
    "更期代號註解", "代號及時數(old)", "代號及時數", "覆診地點代號",
    "第一週", "第二週", "第三週", "第四週", "第五週", "工作表2", "第六週",
    "Hours", "PH & Off", "DO更次數", "AP更", "C更男女", "N更男女", "用膳代號",
]
PENDING_FORMULAS = {"CGender": ["E6", "N36", "AP6"], "NGender": ["E6", "AP6"]}
STAFF_ROWS = [*range(17, 33), *range(34, 58), *range(73, 77)]
DAY_STARTS = list(range(3, 22, 3))
HOUR_STARTS = list(range(3, 49, 9))


def _layout(source, target):
    """Copy formatting without values, names, drawings, links or print text."""
    for key, dim in source.row_dimensions.items():
        target.row_dimensions[key].height = dim.height
        target.row_dimensions[key].hidden = dim.hidden
    for key, dim in source.column_dimensions.items():
        column = target.column_dimensions[key]
        column.width, column.hidden = dim.width, dim.hidden
        column.min, column.max = dim.min, dim.max
    target.sheet_format = copy(source.sheet_format)
    for row in source.iter_rows():
        for cell in row:
            if cell.has_style:
                new = target.cell(cell.row, cell.column)
                for style in ("font", "fill", "border", "alignment"):
                    setattr(new, style, copy(getattr(cell, style)))
    for merged in source.merged_cells.ranges:
        target.merge_cells(str(merged))
    target.sheet_state = source.sheet_state
    target.freeze_panes = source.freeze_panes
    target.print_options = copy(source.print_options)
    target.page_margins = copy(source.page_margins)
    target.sheet_properties.pageSetUpPr = copy(source.sheet_properties.pageSetUpPr)
    target.page_setup = copy(source.page_setup)
    target.page_setup.id = None
    if source.print_area:
        target.print_area = source.print_area
    if source.print_title_rows:
        target.print_title_rows = source.print_title_rows
    if source.print_title_cols:
        target.print_title_cols = source.print_title_cols


def _literal(sheet, address, text, preserve):
    sheet[address] = text
    sheet[address].data_type = "s"
    preserve[sheet.title].append(f"{address}:{address}")


def prepare(source_bytes: bytes, confirmation_bytes: bytes) -> tuple[bytes, dict]:
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    confirmation_hash = hashlib.sha256(confirmation_bytes).hexdigest()
    if source_hash not in (SOURCE_SHA, ORIGINAL_SOURCE_SHA):
        raise ValueError("Expected Gary's reviewed 28 Sep to 8 Nov roster")
    if confirmation_hash not in (CONFIRMATION_SHA, ORIGINAL_CONFIRMATION_SHA):
        raise ValueError("Expected Gary's 20 November working confirmation sheet")
    original = source_hash == ORIGINAL_SOURCE_SHA
    sheet_names = ORIGINAL_SHEETS if original else SHEETS
    sheet_map = dict(zip(SHEETS, sheet_names, strict=True))
    source = load_workbook(BytesIO(source_bytes), keep_links=False)
    confirmation = load_workbook(BytesIO(confirmation_bytes), keep_links=False)
    if [name for name in source.sheetnames if name != "README-EN"] != sheet_names:
        raise ValueError("unexpected TAHDuty workbook tab order")

    book = Workbook()
    book.remove(book.active)
    preserve = {name: [] for name in sheet_names}
    for name in sheet_names:
        _layout(source[name], book.create_sheet(name))
    pending = "待 NAAC 確認" if original else "Pending NAAC confirmation"
    pending_cells = {}
    for layout in ("Shift Code Legend", "Codes & Hours (old)", "Codes & Hours",
                   "Clinic Location Codes", "MealCodes", "PH & Off", "DOCounts",
                   "APShifts", "CGender", "NGender"):
        name = sheet_map[layout]
        note = f"{name} / {pending}"
        if layout in PENDING_FORMULAS:
            pending_cells[name] = PENDING_FORMULAS[layout]
            note += " (" + ", ".join(pending_cells[name]) + ")"
        _literal(book[name], "A1", note, preserve)

    plans = []
    week_labels = {
        "A1": "更表預覽", "A2": "只顯示現有更表記錄。代號及規則待 NAAC 確認。",
        "A16": "職位", "B15": "日期", "B16": "姓名",
    } if original else {
        "A1": "TAHDuty preview", "A2": "Roster records only. Codes and rules pending NAAC confirmation.",
        "A15": "Rank", "B15": "Date", "B16": "Name",
    }
    for layout in WEEKS:
        name = sheet_map[layout]
        sheet = book[name]
        for address, value in week_labels.items():
            _literal(sheet, address, value, preserve)
        plans.append({
            "sheet": name, "staff_rows": STAFF_ROWS, "name_column": 2,
            "rank_column": 1, "meal_columns": DAY_STARTS,
            "day_columns": [col + 1 for col in DAY_STARTS],
            "task_columns": [col + 2 for col in DAY_STARTS],
            "date_cells": [f"{get_column_letter(col)}15" for col in DAY_STARTS],
            "weekday_cells": [f"{get_column_letter(col)}16" for col in DAY_STARTS],
            "date_format": 'm"月"d"日"' if original else "d mmm",
            "weekday_labels": list("一二三四五六日") if original else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        })

    hours = book["Hours"]
    hours_plan = {
        "sheet": "Hours", "staff_rows": list(range(3, 47)), "week_start_columns": HOUR_STARTS,
    }
    if original:
        hours_plan["print_summary"] = {
            "name_columns": [57, 67], "week_start_column": 68, "total_columns": [63, 74],
        }
        for address, value in {
            "BE1": "姓名", "BK1": "已記錄工時", "BO1": "姓名", "BV1": "六週已記錄工時",
        }.items():
            _literal(hours, address, value, preserve)
    else:
        hours.print_area = "A1:BC46"
        hours.sheet_properties.pageSetUpPr.fitToPage = True
        hours.page_setup.orientation = "landscape"
        hours.page_setup.fitToWidth = 1
        hours.page_setup.fitToHeight = 0
    _literal(hours, "A1", "已記錄工時" if original else "Recorded hours", preserve)
    _literal(hours, "A2", "職位" if original else "Rank", preserve)
    _literal(hours, "B2", "姓名" if original else "Name", preserve)
    for week, first in enumerate(HOUR_STARTS, 1):
        week_label = sheet_map[WEEKS[week - 1]] if original else f"Week {week}"
        _literal(hours, f"{get_column_letter(first)}1", week_label, preserve)
        for day in range(7):
            label = f"第 {day + 1} 日" if original else f"Day {day + 1}"
            _literal(hours, f"{get_column_letter(first + day)}2", label, preserve)
        _literal(hours, f"{get_column_letter(first + 7)}2", "每週合計" if original else "Week total", preserve)
        if original:
            _literal(hours, f"{get_column_letter(67 + week)}1", week_label, preserve)
    book.active = book[sheet_map["Week1"]]
    output = BytesIO()
    book.save(output)
    raw = output.getvalue()
    zh_confirmation = confirmation_hash == ORIGINAL_CONFIRMATION_SHA
    shift_sheet = "更期及工作代號確認" if zh_confirmation else "Shift Code Confirmation"
    task_sheet = "工作內容代號確認" if zh_confirmation else "Task Code Confirmation"
    shift_rows = list(confirmation[shift_sheet].iter_rows(min_row=2, max_col=19, values_only=True))
    task_rows = list(confirmation[task_sheet].iter_rows(min_row=2, max_col=5, values_only=True))
    return raw, {
        "template_sha256": hashlib.sha256(raw).hexdigest(),
        "sheet_names": sheet_names, "provisional": True,
        "source_sha256": source_hash, "confirmation_sha256": confirmation_hash,
        "pending_formula_cells": pending_cells,
        "source_confirmation": {
            "shift_rows": sum(row[1] is not None for row in shift_rows),
            "shift_active_status_answers": sum(row[1] is not None and row[15] in ("Y", "N") for row in shift_rows),
            "task_rows_pending": sum(row[0] is not None and (not row[3] or "待" in str(row[3]) or "TBC" in str(row[3])) for row in task_rows),
        },
        "weeks": plans, "preserve_ranges": preserve,
        "recorded_hours": hours_plan,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roster", type=Path)
    parser.add_argument("confirmation", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    raw, mapping = prepare(args.roster.read_bytes(), args.confirmation.read_bytes())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "tahduty-template.xlsx").write_bytes(raw)
    (args.output_dir / "tahduty-mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    print(f"Prepared {len(mapping['sheet_names'])} tabs. Code confirmation remains pending.")


if __name__ == "__main__":
    main()
