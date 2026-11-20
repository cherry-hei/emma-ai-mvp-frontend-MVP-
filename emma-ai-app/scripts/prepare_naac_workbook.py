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
WEEKS = [f"Week{i}" for i in range(1, 7)]
SHEETS = [
    "Shift Code Legend", "Codes & Hours (old)", "Codes & Hours",
    "Clinic Location Codes", *WEEKS[:5], "Sheet2", WEEKS[5], "Hours",
    "PH & Off", "DOCounts", "APShifts", "CGender", "NGender", "MealCodes",
]
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


def _literal(sheet, address, text, preserve):
    sheet[address] = text
    sheet[address].data_type = "s"
    preserve[sheet.title].append(f"{address}:{address}")


def prepare(source_bytes: bytes, confirmation_bytes: bytes) -> tuple[bytes, dict]:
    if hashlib.sha256(source_bytes).hexdigest() != SOURCE_SHA:
        raise ValueError("Expected Gary's reviewed 28 Sep to 8 Nov English roster")
    if hashlib.sha256(confirmation_bytes).hexdigest() != CONFIRMATION_SHA:
        raise ValueError("Expected Gary's 20 November working confirmation sheet")
    source = load_workbook(BytesIO(source_bytes), keep_links=False)
    confirmation = load_workbook(BytesIO(confirmation_bytes), keep_links=False)
    if [name for name in source.sheetnames if name != "README-EN"] != SHEETS:
        raise ValueError("unexpected TAHDuty workbook tab order")

    book = Workbook()
    book.remove(book.active)
    preserve = {name: [] for name in SHEETS}
    for name in SHEETS:
        _layout(source[name], book.create_sheet(name))
    pending = "Pending NAAC confirmation"
    for name in ("Shift Code Legend", "Codes & Hours (old)", "Codes & Hours",
                 "Clinic Location Codes", "MealCodes"):
        _literal(book[name], "A1", f"{name} / {pending}", preserve)
    for name in ("PH & Off", "DOCounts", "APShifts", "CGender", "NGender"):
        _literal(book[name], "A1", f"{name} / {pending}", preserve)

    plans = []
    for name in WEEKS:
        sheet = book[name]
        for address, value in {
            "A1": "TAHDuty preview",
            "A2": "Roster records only. Codes and rules pending NAAC confirmation.",
            "A15": "Rank", "B15": "Date", "B16": "Name",
        }.items():
            _literal(sheet, address, value, preserve)
        plans.append({
            "sheet": name, "staff_rows": STAFF_ROWS, "name_column": 2,
            "rank_column": 1, "meal_columns": DAY_STARTS,
            "day_columns": [col + 1 for col in DAY_STARTS],
            "task_columns": [col + 2 for col in DAY_STARTS],
            "date_cells": [f"{get_column_letter(col)}15" for col in DAY_STARTS],
            "weekday_cells": [f"{get_column_letter(col)}16" for col in DAY_STARTS],
            "date_format": "d mmm",
        })

    hours = book["Hours"]
    hours.print_area = "A1:BC46"
    hours.sheet_properties.pageSetUpPr.fitToPage = True
    hours.page_setup.orientation = "landscape"
    hours.page_setup.fitToWidth = 1
    hours.page_setup.fitToHeight = 0
    _literal(hours, "A1", "Recorded hours", preserve)
    _literal(hours, "A2", "Rank", preserve)
    _literal(hours, "B2", "Name", preserve)
    for week, first in enumerate(HOUR_STARTS, 1):
        _literal(hours, f"{get_column_letter(first)}1", f"Week {week}", preserve)
        for day in range(7):
            _literal(hours, f"{get_column_letter(first + day)}2", f"Day {day + 1}", preserve)
        _literal(hours, f"{get_column_letter(first + 7)}2", "Week total", preserve)
    book.active = book["Week1"]
    output = BytesIO()
    book.save(output)
    raw = output.getvalue()
    shift_rows = list(confirmation["Shift Code Confirmation"].iter_rows(min_row=2, max_col=19, values_only=True))
    task_rows = list(confirmation["Task Code Confirmation"].iter_rows(min_row=2, max_col=5, values_only=True))
    return raw, {
        "template_sha256": hashlib.sha256(raw).hexdigest(),
        "sheet_names": SHEETS, "provisional": True,
        "source_sha256": SOURCE_SHA, "confirmation_sha256": CONFIRMATION_SHA,
        "source_confirmation": {
            "shift_rows": sum(row[1] is not None for row in shift_rows),
            "shift_active_status_answers": sum(row[1] is not None and row[15] in ("Y", "N") for row in shift_rows),
            "task_rows_pending": sum(row[0] is not None and row[3] == "To be confirmed (TBC)" for row in task_rows),
        },
        "weeks": plans, "preserve_ranges": preserve,
        "recorded_hours": {
            "sheet": "Hours", "staff_rows": list(range(3, 47)),
            "week_start_columns": HOUR_STARTS,
        },
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
