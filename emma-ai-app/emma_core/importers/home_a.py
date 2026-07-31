"""Home A layout: 員工工作時間表 - a 28-day cycle across two rank sheets.

    2026年3月2日 至 2026年3月29日 員工工作時間表 — 護士及保健員
    休:休息日 法:法定假日 公:公眾假期 年:年假 ...
    護士及保健員 (N, HW) - A: 7:00am-3:00pm  B: 8:00AM-4:00PM  ...
    日期/年份 2026 | 02/03 | 03/03 | ...            | 本更期欠 | 上更期欠
    姓名及職位     | 一    | 二    | ...            | 休  | DO | 休 | DO
    RN1            | P     | A     | P | 補休 | ...  | 3   | 2  | 3  | 2

Each rank group is a separate sheet pair - ``… Before`` is the roster as first
published and ``… after`` is the roster as worked. That pair is a gift for an
import: it maps exactly onto the draft/published roster versions the schema
already has, so the home's own record of what changed survives the import.

Staff are anonymised in the source (``RN1``, ``HW9``, ``PT RCW12``), which is why
the row label is the identity here rather than a name.
"""
from __future__ import annotations

import re
from datetime import date as Date

from . import sheets
from .cells import normalise, parse_cell
from .plan import Issue, ParsedCell, ParsedEvent, ParsedRoster, ParsedStaff
from .vocab import HOME_A, resolve_rank

LAYOUT = "home_a_duty_roster"

# Sheet-title fragment -> the duty dictionary that sheet's legend prints.
_SHEET_GROUPS = (("RCW", "care"), ("院舍護理員", "care"),
                 ("RN", "nursing"), ("護士", "nursing"))
# 'Before' is the originally published cycle, 'after' the one actually worked.
_VARIANT_MARKERS = (("before", "before"), ("after", "after"))

# The trailing summary block: 本更期欠休 / 欠DO, then the previous cycle's.
_SUMMARY_HEADERS = ("本更期", "上更期", "1-4週", "備註", "備 註", "欠法")


def matches(workbook) -> bool:
    titles = " ".join(workbook.sheetnames)
    return "員工工作時間表" in _first_title(workbook) or "院舍護理員" in titles


def _first_title(workbook) -> str:
    for name in workbook.sheetnames:
        return sheets.text(workbook[name], 1, 1)
    return ""


def _sheet_group(title: str) -> str:
    for fragment, group in _SHEET_GROUPS:
        if fragment in title:
            return group
    return "nursing"


def _variant(title: str) -> str:
    lowered = title.lower()
    for fragment, variant in _VARIANT_MARKERS:
        if fragment in lowered:
            return variant
    return "after"


def read(workbook, *, source_name: str, variant: str = "after") -> ParsedRoster:
    """Parse every sheet of the requested variant into one roster.

    ``variant`` selects the ``before`` or ``after`` sheet of each rank group; the
    two rank groups are merged because they are one facility's one cycle.
    """
    profile = HOME_A
    issues: list[Issue] = []
    staff: list[ParsedStaff] = []
    cells: list[ParsedCell] = []
    events: list[ParsedEvent] = []
    period: tuple[Date, Date] | None = None
    all_dates: set[Date] = set()

    wanted = [name for name in workbook.sheetnames if _variant(name) == variant
              and _has_grid(workbook[name])]
    if not wanted:
        raise ValueError(f"no '{variant}' roster sheet found in {source_name}")

    for name in wanted:
        ws = workbook[name]
        sheet_period = sheets.find_title_period(ws)
        if not sheet_period:
            issues.append(Issue("no_period", f"sheet {name!r} has no printed date "
                                "range in its title block", "error", sheet=name))
            continue
        period = period or sheet_period
        header = sheets.find_date_header(ws, year=sheet_period[0].year)
        if not header:
            issues.append(Issue("no_date_header", f"sheet {name!r} has no day "
                                "header row", "error", sheet=name))
            continue
        header_row, dates_by_column = header
        all_dates.update(dates_by_column.values())
        group = _sheet_group(name)
        _read_rows(ws, name, group, header_row, dates_by_column,
                   profile, staff, cells, events, issues)

    if not period:
        raise ValueError(f"{source_name}: no sheet carried a readable period")
    return ParsedRoster(
        facility_code=profile.code, profile=profile, layout=LAYOUT,
        source_name=source_name, period_start=period[0], period_end=period[1],
        dates=sorted(all_dates), staff=staff, cells=cells, events=events,
        issues=issues,
    )


def _has_grid(ws) -> bool:
    last_row, last_col = sheets.used_extent(ws, max_scan_rows=60, max_scan_cols=40)
    return last_row > 5 and last_col > 10


def _read_rows(ws, sheet_name: str, group: str, header_row: int,
               dates_by_column: dict[int, Date], profile, staff, cells, events,
               issues) -> None:
    sheet_profile = profile.sheet(group)
    date_columns = sorted(dates_by_column)
    summary_columns = _summary_columns(ws, header_row, date_columns[-1])
    last_row, _ = sheets.used_extent(ws)
    seen_keys = {s.key for s in staff}

    for row in range(header_row + 1, last_row + 1):
        label = sheets.text(ws, row, 1)
        if not label:
            continue
        if "顏色" in label:
            break                                   # colour key ends the grid
        if sheets.looks_like_events_row(label):
            events.extend(_read_events(ws, sheet_name, row, dates_by_column))
            continue
        if sheets.looks_like_legend(label) or sheets.looks_like_header_label(label):
            continue                                # time legend or header row

        spec = resolve_rank(label)
        if not spec:
            for token in sheets.parenthesised_ranks(label):
                spec = resolve_rank(token)
                if spec:
                    break
        row_values = [(column, sheets.text(ws, row, column))
                      for column in date_columns]
        if not any(value for _, value in row_values):
            continue                                # spacer or merged header
        if sheets.looks_like_weekday_row([v for _, v in row_values]):
            continue
        if not spec:
            issues.append(Issue(
                "unknown_rank", f"row label {label!r} did not resolve to a rank",
                "warning", sheet=sheet_name,
                cell_ref=sheets.cell_ref(sheet_name, row, 1), raw_value=label))
            continue

        key = f"{profile.code}:{_normalise_label(label)}"
        if key not in seen_keys:
            seen_keys.add(key)
            staff.append(ParsedStaff(
                key=key, display_name=label, rank=spec.rank,
                employment_type=spec.employment_type, sheet=sheet_name, row=row,
                label=label, is_relief_pool=spec.is_relief_pool,
                rest_days_total=_summary_int(ws, row, summary_columns, "休"),
            ))

        for column, value in row_values:
            if not value:
                continue
            intent = parse_cell(value, profile, sheet_profile)
            if intent.is_empty:
                continue
            reference = sheets.cell_ref(sheet_name, row, column)
            if intent.unparsed:
                issues.append(Issue(
                    "unparsed_cell",
                    f"could not resolve {', '.join(intent.unparsed)} in {value!r}",
                    "warning", sheet=sheet_name, cell_ref=reference,
                    raw_value=value))
            elif not intent.is_working and not intent.leave:
                issues.append(Issue(
                    "note_only_cell", f"cell {value!r} carried no duty or leave "
                    "code", "info", sheet=sheet_name, cell_ref=reference,
                    raw_value=value))
            cells.append(ParsedCell(
                staff_key=key, date=dates_by_column[column], intent=intent,
                sheet=sheet_name, cell_ref=reference,
                unit_name=intent.unit_hint))


def _normalise_label(label: str) -> str:
    """'PT RCW1' / 'PT  RCW 1' -> a single stable identity across sheets."""
    return re.sub(r"\s+", " ", label).strip().upper()


def _summary_columns(ws, header_row: int, last_date_column: int) -> dict[str, int]:
    """Map the trailing 欠休 / 欠DO summary headers to their columns."""
    found: dict[str, int] = {}
    for column in range(last_date_column + 1, last_date_column + 10):
        for probe_row in (header_row, header_row + 1):
            value = sheets.text(ws, probe_row, column)
            if value and value not in _SUMMARY_HEADERS and value not in found:
                found[value] = column
    return found


def _summary_int(ws, row: int, summary_columns: dict[str, int], key: str) -> int | None:
    column = summary_columns.get(key)
    if not column:
        return None
    number = sheets.to_number(sheets.text(ws, row, column))
    return int(number) if number is not None else None


def _read_events(ws, sheet_name: str, row: int,
                 dates_by_column: dict[int, Date]) -> list[ParsedEvent]:
    """The 活動／會議 row: one or more events per day, marked ▲ * # for the cells."""
    out: list[ParsedEvent] = []
    for column, date in sorted(dates_by_column.items()):
        raw = normalise(ws.cell(row=row, column=column).value)
        if not raw:
            continue
        markers = tuple(m for m in ("▲", "*", "#", "※") if m in raw)
        title = re.sub(r"[▲*#※]", "", raw).strip(" /")
        if title:
            out.append(ParsedEvent(date=date, title=title, markers=markers, raw=raw))
    return out
