"""Workbook shape, calculations and source-data removal using invented fixtures."""

import hashlib
from datetime import date
from io import BytesIO

import pytest
from emma_core.services import naac_export
from openpyxl import Workbook, load_workbook


@pytest.fixture
def context():
    return {
        "facility": {"id": "f1", "name": "Synthetic NAAC"},
        "period": {
            "id": "p1",
            "period_start": "2026-11-01",
            "period_end": "2026-12-12",
        },
        "version": {"id": "v1", "status": "draft"},
        "staff": [{"id": "s1", "name": "Synthetic RN", "rank": "RN", "gender": "F"}],
        "shifts": [
            {
                "id": "sh1",
                "date": "2026-11-01",
                "shift_type": "A7",
                "is_working": True,
                "paid_minutes": 480,
            },
            {
                "id": "sh2",
                "date": "2026-11-02",
                "shift_type": "AL",
                "is_working": False,
                "paid_minutes": 480,
            },
            {
                "id": "sh3",
                "date": "2026-11-03",
                "shift_type": "O",
                "is_working": False,
                "paid_minutes": 0,
            },
        ],
        "assignments": [
            {"id": f"a{i}", "shift_id": f"sh{i}", "staff_id": "s1", "tasks": []}
            for i in range(1, 4)
        ],
        "tasks": [{"id": "t1", "shift_assignment_id": "a1", "task_label": "#"}],
        "definitions": [{"shift_type": code} for code in ("A7", "AL", "O")],
    }


@pytest.fixture
def template():
    workbook = Workbook()
    workbook.remove(workbook.active)
    names = [f"Week{i}" for i in range(1, 7)] + [f"Summary{i}" for i in range(1, 13)]
    for name in names:
        sheet = workbook.create_sheet(name)
        sheet["A1"] = "Approved heading"
        sheet["B3"] = "OLD STAFF NAME"
        sheet["L3"] = "=SUM(D3:J3)"
    out = BytesIO()
    workbook.save(out)
    raw = out.getvalue()
    return raw, {
        "sheet_names": names,
        "template_sha256": hashlib.sha256(raw).hexdigest(),
        "preserve_ranges": {name: ["A1:A1"] for name in names},
        "weeks": [
            {
                "sheet": name,
                "staff_rows": [3],
                "name_column": 2,
                "rank_column": 3,
                "day_columns": list(range(4, 11)),
                "date_cells": [f"{col}2" for col in "DEFGHIJ"],
            }
            for name in names[:6]
        ],
        "summaries": [
            {
                "sheet": "Summary1",
                "staff_rows": [3],
                "columns": {
                    "name": 2,
                    "hours": 3,
                    "working_days": 4,
                    "annual_leave": 5,
                    "rest_days": 6,
                    "duty_supervisor": 7,
                },
            }
        ],
    }


def test_export_preserves_18_sheets_and_removes_old_names(context, template):
    raw, mapping = template
    workbook = load_workbook(BytesIO(naac_export.render(context, raw, mapping)))
    assert workbook.sheetnames == mapping["sheet_names"]
    assert workbook["Week1"]["B3"].value == "Synthetic RN"
    assert workbook["Week1"]["D3"].value == "A7 #"
    assert workbook["Week1"]["E3"].value == "AL"
    assert workbook["Week1"]["F3"].font.color.rgb == "00FF0000"
    assert workbook["Week1"]["L3"].value == "=SUM(D3:J3)"
    assert workbook["Summary1"]["C3"].value == 16
    assert workbook["Summary1"]["D3"].value == 1
    assert workbook["Week6"]["D2"].value.date() == date(2026, 12, 6)
    assert all(
        cell.value != "OLD STAFF NAME"
        for sheet in workbook
        for row in sheet
        for cell in row
    )


def test_unknown_duty_code_cannot_silently_produce_summary_totals(context):
    context["shifts"][0]["shift_type"] = "UNKNOWN"
    with pytest.raises(ValueError, match="no confirmed NAAC summary mapping"):
        naac_export.summarize(context)


def test_staff_name_cannot_be_written_as_an_excel_formula(context, template):
    context["staff"][0]["name"] = '=HYPERLINK("https://example.invalid")'
    raw, mapping = template
    workbook = load_workbook(BytesIO(naac_export.render(context, raw, mapping)))
    cell = workbook["Week1"]["B3"]
    assert cell.data_type != "f"
    assert cell.value.startswith("'=")
