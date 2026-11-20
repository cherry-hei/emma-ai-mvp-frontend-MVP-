"""Fill an approved NAAC workbook layout from one scoped six week roster."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import copy
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.packaging.core import DocumentProperties
from openpyxl.utils.cell import range_boundaries
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from ..config import settings
from ..importers.naac import load_shift_codes
from . import audit
from ._common import (
    as_date,
    assignments_for_shifts,
    fetch_in,
    iso,
    operative_version,
    resolve_period,
)


def _all_rows(query) -> list[dict]:
    page_size = 500
    query = query.order("id")
    rows = []
    while True:
        batch = query.range(len(rows), len(rows) + page_size - 1).execute().data
        if not batch:
            return rows
        rows.extend(batch)


def load_context(
    client, facility_id: str, period_id: str, version_id: str | None = None
) -> dict:
    period = resolve_period(client, facility_id, period_id)
    if not period:
        raise ValueError("roster period not found")
    start, end = as_date(period["period_start"]), as_date(period["period_end"])
    if (end - start).days != 41:
        raise ValueError("NAAC workbook requires a complete six week period")
    home = (
        client.table("facilities")
        .select("id,code,name,org_id")
        .eq("id", facility_id)
        .execute()
        .data
    )
    if not home:
        raise ValueError("facility not found")
    if home[0]["code"] != "NAAC":
        raise ValueError("TAHDuty export is available only for NAAC")
    if version_id:
        versions = (
            client.table("roster_versions")
            .select("*")
            .eq("facility_id", facility_id)
            .eq("period_id", period_id)
            .eq("id", version_id)
            .execute()
            .data
        )
        version = versions[0] if versions else None
    else:
        version = operative_version(client, facility_id, period_id)
    if not version:
        raise ValueError("roster version not found")
    shifts = _all_rows(
        client.table("shifts")
        .select("*")
        .eq("facility_id", facility_id)
        .eq("roster_version_id", version["id"])
    )
    assignments = [
        a
        for a in assignments_for_shifts(
            client, [s["id"] for s in shifts], facility_id=facility_id
        )
        if a.get("status") != "cancelled" and a.get("staff_id")
    ]
    staff = (
        client.table("staff")
        .select("id,name,name_en,rank,gender,status")
        .eq("facility_id", facility_id)
        .execute()
        .data
    )
    tasks = fetch_in(
        client,
        "task_assignments",
        "shift_assignment_id",
        [a["id"] for a in assignments],
        filters={"facility_id": facility_id},
    )
    definitions = (
        client.table("shift_definitions")
        .select("*")
        .eq("org_id", home[0]["org_id"])
        .execute()
        .data
    )
    return {
        "facility": home[0],
        "period": period,
        "version": version,
        "shifts": shifts,
        "assignments": assignments,
        "staff": staff,
        "tasks": tasks,
        "definitions": definitions,
    }


def _text(value):
    value = str(value or "")
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


def _literal(cell, value):
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"


def _asset(location: str) -> bytes:
    if location.startswith("s3://"):
        from urllib.parse import urlparse

        import boto3

        uri = urlparse(location)
        if not uri.netloc or not uri.path.lstrip("/"):
            raise ValueError("invalid workbook asset location")
        return (
            boto3.client("s3")
            .get_object(Bucket=uri.netloc, Key=uri.path.lstrip("/"))["Body"]
            .read()
        )
    return Path(location).read_bytes()


def summarize(context: dict, *, provisional: bool = False) -> dict:
    start = as_date(context["period"]["period_start"])
    shifts = {s["id"]: s for s in context["shifts"]}
    definitions = {d["shift_type"]: d for d in context["definitions"]}
    specs = {} if provisional else load_shift_codes()
    task_labels = defaultdict(list)
    for task in context["tasks"]:
        if task.get("suspended_by_leave"):
            continue
        label = task.get("task_label")
        if label and label not in task_labels[task["shift_assignment_id"]]:
            task_labels[task["shift_assignment_id"]].append(label)
    cells = {}
    totals = defaultdict(
        lambda: {
            "hours": 0.0,
            "working_days": 0,
            "rest_days": 0,
            "regular_days_off": 0,
            "annual_leave": 0,
            "sick_leave": 0,
            "ph": 0.0,
            "am": 0.0,
            "pm": 0.0,
            "night": 0.0,
            "sleepover": 0.0,
            "duty_supervisor": 0,
        }
    )
    for assignment in context["assignments"]:
        shift = shifts[assignment["shift_id"]]
        day = iso(shift["date"])
        offset = (as_date(day) - start).days
        if not 0 <= offset < 42:
            raise ValueError("roster contains a shift outside the six week period")
        key = (assignment["staff_id"], offset)
        if key in cells:
            raise ValueError("multiple shifts occupy the same staff/day cell")
        code = shift["shift_type"]
        if not provisional and (code not in definitions or code not in specs):
            raise ValueError(
                f"Duty code {code!r} has no confirmed NAAC summary mapping"
            )
        spec = specs.get(code)
        labels = list(
            dict.fromkeys(
                [*(assignment.get("tasks") or []), *task_labels[assignment["id"]]]
            )
        )
        cells[key] = {
            "code": code,
            "text": " ".join([code, *labels]),
            "labels": labels,
            "paid_minutes": shift.get("paid_minutes")
            if shift.get("paid_minutes") is not None
            else spec.paid_minutes if spec else None,
            "meal_code": assignment.get("meal_code"),
        }
        total = totals[assignment["staff_id"]]
        if provisional:
            continue
        total["hours"] += cells[key]["paid_minutes"] / 60
        total["working_days"] += int(bool(shift.get("is_working")) and spec.is_working)
        total["rest_days"] += int(code == "O")
        total["regular_days_off"] += int(code == "O,")
        total["annual_leave"] += int(code.startswith("AL"))
        total["sick_leave"] += int(code.startswith("SL"))
        total["ph"] += spec.ph_fraction
        total["am"] += spec.am_fraction
        total["pm"] += spec.pm_fraction
        total["night"] += spec.night_fraction
        total["sleepover"] += spec.sleepover_fraction
        total["duty_supervisor"] += int(spec.duty_supervisor or "#" in labels)
    people = [
        s
        for s in context["staff"]
        if s.get("status", "active") == "active" or s["id"] in totals
    ]
    people.sort(
        key=lambda s: (str(s["rank"]), str(s.get("name_en") or s.get("name")), s["id"])
    )
    for person in people:
        totals[person["id"]]
    return {"staff": people, "cells": cells, "totals": dict(totals), "start": start}


def _write_hours(workbook, plan: dict, data: dict) -> None:
    sheet = workbook[plan["sheet"]]
    rows = plan["staff_rows"]
    if len(rows) < len(data["staff"]):
        raise ValueError("hours sheet has too few staff rows")
    for person, row in zip(data["staff"], rows):
        _literal(sheet.cell(row, 1), person["rank"])
        _literal(sheet.cell(row, 2), person.get("name") or person.get("name_en"))
        for week, first in enumerate(plan["week_start_columns"]):
            for day in range(7):
                cell = data["cells"].get((person["id"], week * 7 + day))
                if cell and cell["paid_minutes"] is not None:
                    sheet.cell(row, first + day, cell["paid_minutes"] / 60)
            left = get_column_letter(first)
            right = get_column_letter(first + 6)
            span = f"{left}{row}:{right}{row}"
            sheet.cell(row, first + 7, f'=IF(COUNT({span})=7,SUM({span}),"")')


def render(context: dict, template: bytes, mapping: dict) -> bytes:
    """Keep approved layout and formulas; populate only declared input cells."""
    workbook = load_workbook(BytesIO(template), keep_links=False)
    if mapping.get("template_sha256") != hashlib.sha256(template).hexdigest():
        raise ValueError("cell mapping does not match the approved workbook template")
    expected = mapping.get("sheet_names")
    if (
        not isinstance(expected, list)
        or len(expected) != 18
        or workbook.sheetnames != expected
    ):
        raise ValueError(
            "approved template must have the exact mapped 18-sheet structure"
        )
    weeks = mapping.get("weeks") or []
    if len(weeks) != 6 or len({w["sheet"] for w in weeks}) != 6:
        raise ValueError("mapping must identify six separate weekly roster sheets")
    provisional = mapping.get("provisional") is True
    data = summarize(context, provisional=provisional)
    # Only explicitly approved labels/reference cells survive from a source file.
    preserve = defaultdict(set)
    for sheet, ranges in (mapping.get("preserve_ranges") or {}).items():
        if sheet not in workbook.sheetnames:
            raise ValueError("mapping references an unknown sheet")
        for area in ranges:
            left, top, right, bottom = range_boundaries(area)
            for row in range(top, bottom + 1):
                for col in range(left, right + 1):
                    preserve[sheet].add((row, col))
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                if isinstance(cell, MergedCell):
                    continue
                if cell.comment:
                    cell.comment = None
                if cell.hyperlink:
                    cell.hyperlink = None
                if cell.data_type == "f":
                    if any(
                        token in cell.value.upper()
                        for token in ("[", "WEBSERVICE(", "HYPERLINK(", "DDE(", "|")
                    ):
                        raise ValueError(
                            "template contains an external or unsafe formula"
                        )
                elif (cell.row, cell.column) not in preserve[sheet.title]:
                    cell.value = None
    for week_index, plan in enumerate(weeks):
        sheet = workbook[plan["sheet"]]
        rows = plan.get("staff_rows") or []
        columns = plan.get("day_columns") or []
        if len(columns) != 7 or len(plan.get("date_cells") or []) != 7:
            raise ValueError(
                "each weekly mapping needs seven date cells and duty columns"
            )
        if len(rows) < len(data["staff"]):
            raise ValueError("approved workbook has too few staff rows")
        for index, address in enumerate(plan["date_cells"]):
            day = data["start"] + timedelta(days=week_index * 7 + index)
            sheet[address] = day
            sheet[address].number_format = plan.get("date_format", "yyyy-mm-dd")
            if "weekday_cells" in plan:
                sheet[plan["weekday_cells"][index]] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[day.weekday()]
        for person, row in zip(data["staff"], rows):
            name = person.get("name") or person.get("name_en")
            if "task_columns" in plan:
                _literal(sheet.cell(row, plan["name_column"]), name)
                _literal(sheet.cell(row, plan["rank_column"]), person["rank"])
            else:
                sheet.cell(row, plan["name_column"], _text(name))
                sheet.cell(row, plan["rank_column"], _text(person["rank"]))
            for day, column in enumerate(columns):
                cell = data["cells"].get((person["id"], week_index * 7 + day))
                target = sheet.cell(row, column)
                if "task_columns" in plan:
                    if cell:
                        _literal(target, cell["code"])
                        _literal(sheet.cell(row, plan["task_columns"][day]), " ".join(cell["labels"]) or None)
                        _literal(sheet.cell(row, plan["meal_columns"][day]), cell["meal_code"])
                else:
                    target.value = _text(cell["text"]) if cell else None
                if cell and cell["code"] in ("O", "O,"):
                    font = copy(target.font)
                    font.color = "FF0000" if cell["code"] == "O" else "000000"
                    target.font = font
    if "recorded_hours" in mapping:
        _write_hours(workbook, mapping["recorded_hours"], data)
    for plan in mapping.get("summaries") or []:
        sheet = workbook[plan["sheet"]]
        rows = plan.get("staff_rows") or []
        if len(rows) < len(data["staff"]):
            raise ValueError("summary sheet has too few staff rows")
        for person, row in zip(data["staff"], rows):
            for field, column in plan["columns"].items():
                value = (
                    (person.get("name") or person.get("name_en"))
                    if field == "name"
                    else (
                        person.get(field)
                        if field in {"rank", "gender"}
                        else data["totals"].get(person["id"], {}).get(field)
                    )
                )
                if value is None:
                    raise ValueError(
                        f"summary field {field!r} needs an explicit mapping"
                    )
                sheet.cell(
                    row,
                    column,
                    _text(value) if isinstance(value, str) else round(value, 4),
                )
    for sheet, addresses in (mapping.get("metadata_cells") or {}).items():
        values = {
            "facility": context["facility"]["name"],
            "period_start": iso(context["period"]["period_start"]),
            "period_end": iso(context["period"]["period_end"]),
            "version_id": context["version"]["id"],
            "status": context["version"]["status"],
        }
        for field, address in addresses.items():
            workbook[sheet][address] = _text(values[field])
    workbook.properties = DocumentProperties(
        creator="Emma AI",
        lastModifiedBy="Emma AI",
        description="NAAC six week roster export",
        title="NAAC TAHDuty PREVIEW" if provisional else "NAAC TAHDuty"
        if context["version"]["status"] == "published"
        else "DRAFT NAAC TAHDuty",
    )
    workbook.calculation = CalcProperties(calcId=191029, fullCalcOnLoad=True)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def export(
    client,
    facility_id: str,
    period_id: str,
    *,
    version_id: str | None = None,
    profile_id: str | None = None,
) -> tuple[bytes, str]:
    if not settings.naac_workbook_template or not settings.naac_workbook_mapping:
        raise ValueError(
            "NAAC workbook requires its approved template and cell mapping"
        )
    context = load_context(client, facility_id, period_id, version_id)
    try:
        mapping = json.loads(_asset(settings.naac_workbook_mapping))
        template = _asset(settings.naac_workbook_template)
    except (OSError, json.JSONDecodeError):
        raise ValueError(
            "NAAC template configuration is unavailable or invalid"
        ) from None
    content = render(context, template, mapping)
    audit.record(
        client,
        facility_id=facility_id,
        action="export",
        entity_table="roster_versions",
        entity_id=context["version"]["id"],
        actor_profile_id=profile_id,
        after={
            "format": "naac_tahduty_xlsx",
            "sheet_count": 18,
            "period_id": period_id,
            "status": context["version"]["status"],
        },
    )
    return content, "preview" if mapping.get("provisional") is True else context["version"]["status"]
