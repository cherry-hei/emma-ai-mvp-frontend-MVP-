"""Home B layout: 更期表 - one natural month, three floors, paired rows.

           迎進生活 2026年 6 月 1/F, 2/F, 6/F 護士/保健員/健康照顧大使更期表
           一  | 二  | 三 | ...                        | DO總數 | 上月帶落補鐘
    職級 姓名  1  |  2  |  3 | ...                     |        |
           ST | VMO | PT | ...        <- events row
    SRN  邵純希 D  |  D  | D  | ...                     |   8    |
    EN   吳碧柔 A# | 2/F P | Run A | ...
         1/F   R  |  R  | R  | ...  <- floor / duty row

Every staff member owns two rows: the duty codes, and underneath them the floor
and the standing duty for that day (``R`` runner, ``C`` canteen, ``AA`` assist
exercise). The floor row is what makes Home B's floor-coverage rules (Phase 4.3)
checkable, so it is read rather than skipped.

Two rows carry people instead of codes - the outsourced (``外判``) and relief
(``替假``) pools name whoever actually covered. Those names are recorded as the
cell's relief worker so the roster shows a person, not a placeholder.
"""
from __future__ import annotations

import re
from datetime import date as Date

from . import sheets
from .cells import normalise, parse_cell, parse_subrow
from .plan import Issue, ParsedCell, ParsedEvent, ParsedRoster, ParsedStaff
from .vocab import FLOOR_TOKENS, HOME_B, resolve_rank

LAYOUT = "home_b_floor_roster"

RANK_COLUMN, NAME_COLUMN, INDEX_COLUMN = 2, 3, 1
# Placeholders the home writes in the name column for a pool rather than a person.
_POOL_LABELS = {"外判": "outsource", "替假": "casual"}
# An unfilled post. Real information - it is why the agency formula exists - but
# not a staff member, so the row is counted and skipped.
_VACANCY_LABELS = {"VAC", "VACANT", "VACANCY", "空缺"}
# Trailing summary block, from the printed headers.
_SUMMARY_HEADERS = {"DO總數": "rest_days", "上月帶落補鐘": "carried_cl",
                    "剩餘補鐘": "remaining_cl"}
_QUOTA_MARKERS = ("quoto", "quota", "request")


def matches(workbook) -> bool:
    for name in workbook.sheetnames:
        ws = workbook[name]
        for column in range(1, 12):
            if "更期表" in sheets.text(ws, 1, column):
                return True
    return False


def read(workbook, *, source_name: str) -> ParsedRoster:
    profile = HOME_B
    issues: list[Issue] = []
    sheet_name = _roster_sheet(workbook)
    ws = workbook[sheet_name]

    period = sheets.find_title_period(ws)
    if not period:
        raise ValueError(f"{source_name}: no month in the sheet title")
    header = sheets.find_date_header(
        ws, year=period[0].year, month_hint=period[0].month)
    if not header:
        raise ValueError(f"{source_name}: no day header row")
    header_row, dates_by_column = header

    summary_columns = _summary_columns(ws, header_row, max(dates_by_column))
    staff, cells, events, quota = _read_rows(
        ws, sheet_name, header_row, dates_by_column, summary_columns,
        profile, issues)

    return ParsedRoster(
        facility_code=profile.code, profile=profile, layout=LAYOUT,
        source_name=source_name, period_start=period[0], period_end=period[1],
        dates=sorted(dates_by_column.values()), staff=staff, cells=cells,
        events=events, request_quota=quota, issues=issues,
    )


def _roster_sheet(workbook) -> str:
    """The sheet whose title says 更期表.

    Selecting by size would pick 'Leave Summary', which is taller than the roster
    itself; the printed title is what actually identifies the grid.
    """
    for name in workbook.sheetnames:
        ws = workbook[name]
        for column in range(1, 12):
            if "更期表" in sheets.text(ws, 1, column):
                return name
    best, best_size = workbook.sheetnames[0], -1
    for name in workbook.sheetnames:
        rows, columns = sheets.used_extent(workbook[name], max_scan_rows=120,
                                          max_scan_cols=60)
        if rows > 20 and columns * rows > best_size:
            best, best_size = name, columns * rows
    return best


def _summary_columns(ws, header_row: int, last_date_column: int) -> dict[str, int]:
    found: dict[str, int] = {}
    for column in range(last_date_column + 1, last_date_column + 10):
        for probe_row in range(max(1, header_row - 2), header_row + 1):
            label = re.sub(r"\s+", "", sheets.text(ws, probe_row, column))
            if key := _SUMMARY_HEADERS.get(label):
                found.setdefault(key, column)
    return found


def _read_rows(ws, sheet_name: str, header_row: int,
               dates_by_column: dict[int, Date], summary_columns: dict[str, int],
               profile, issues) -> tuple[list, list, list, dict]:
    sheet_profile = profile.sheets[0]
    date_columns = sorted(dates_by_column)
    last_row, _ = sheets.used_extent(ws)

    staff: list[ParsedStaff] = []
    cells: list[ParsedCell] = []
    events: list[ParsedEvent] = []
    quota: dict[Date, int] = {}
    by_key: dict[str, ParsedStaff] = {}
    current_floor: str | None = None
    pending_pool: str | None = None
    last_duty_row: int | None = None
    duty_rows: dict[int, str] = {}          # sheet row -> staff key

    for row in range(header_row + 1, last_row + 1):
        index_label = sheets.text(ws, row, INDEX_COLUMN)
        rank_label = sheets.text(ws, row, RANK_COLUMN)
        name_label = sheets.text(ws, row, NAME_COLUMN)

        if _is_quota_row(name_label, rank_label):
            quota.update(_read_quota(ws, row, dates_by_column))
            continue
        if any(token in name_label for token in ("編更者", "覆核者")) or \
                sheets.looks_like_legend(name_label):
            break                                    # sign-off block ends the grid

        # A floor label in the index column scopes the staff rows beneath it.
        floor = next((f for f in FLOOR_TOKENS if index_label.startswith(f)), None)
        if floor:
            current_floor = floor
        if pool := _POOL_LABELS.get(name_label):
            pending_pool = pool

        if name_label.upper() in _VACANCY_LABELS:
            issues.append(Issue(
                "vacant_post", f"vacant {rank_label or 'staff'} post on row {row}",
                "info", sheet=sheet_name,
                cell_ref=sheets.cell_ref(sheet_name, row, NAME_COLUMN),
                raw_value=name_label))
            continue

        spec = resolve_rank(rank_label) if rank_label else None
        is_duty_row = bool(spec) and _is_name_cell(name_label)
        if not is_duty_row and spec and pending_pool and not name_label:
            # The pool's own row: 替假 is written above, the rank below it.
            is_duty_row, name_label = True, _pool_display(pending_pool)

        if not is_duty_row:
            if row == header_row + 1 and _looks_like_events(ws, row, date_columns):
                events.extend(_read_events(ws, sheet_name, row, dates_by_column))
                continue
            if last_duty_row is not None and row == last_duty_row + 1:
                _attach_subrow(ws, row, date_columns, dates_by_column,
                               duty_rows[last_duty_row], cells, by_key,
                               sheet_name, issues)
            continue

        employment_type = pending_pool or spec.employment_type
        key = f"{profile.code}:{name_label}"
        record = by_key.get(key)
        if not record:
            record = ParsedStaff(
                key=key, display_name=name_label, rank=spec.rank,
                employment_type=employment_type, sheet=sheet_name, row=row,
                unit_name=_row_floor(ws, row, current_floor),
                is_relief_pool=bool(pending_pool),
                rest_days_total=_summary_number(ws, row, summary_columns,
                                                "rest_days", as_int=True),
                carried_cl_hours=_summary_number(ws, row, summary_columns,
                                                 "carried_cl"),
            )
            by_key[key] = record
            staff.append(record)
        pending_pool = None
        last_duty_row, duty_rows[row] = row, key

        for column in date_columns:
            value = sheets.text(ws, row, column)
            if not value:
                continue
            reference = sheets.cell_ref(sheet_name, row, column)
            intent = parse_cell(value, profile, sheet_profile)
            relief_name = None
            if record.is_relief_pool and not intent.duties and not intent.leave:
                relief_name = next(
                    (n for n in intent.notes if sheets.is_personal_name(n)), None)
            if intent.is_empty and not relief_name:
                continue
            if intent.unparsed:
                issues.append(Issue(
                    "unparsed_cell",
                    f"could not resolve {', '.join(intent.unparsed)} in {value!r}",
                    "warning", sheet=sheet_name, cell_ref=reference,
                    raw_value=value))
            cells.append(ParsedCell(
                staff_key=key, date=dates_by_column[column], intent=intent,
                sheet=sheet_name, cell_ref=reference,
                unit_name=intent.unit_hint or record.unit_name,
                relief_name=relief_name))

    return staff, cells, events, quota


# ── row helpers ──────────────────────────────────────────────────────────────
def _is_name_cell(value: str) -> bool:
    """True for a person or a pool placeholder, false for '#' or a floor label."""
    if not value or value == "#":
        return False
    if any(value.startswith(f) for f in FLOOR_TOKENS):
        return False
    return bool(re.search(r"[一-鿿A-Za-z]", value))


def _pool_display(pool: str) -> str:
    return {"outsource": "外判 (outsourced)", "casual": "替假 (relief pool)"}[pool]


def _row_floor(ws, row: int, current_floor: str | None) -> str | None:
    """The floor from this row's own labels, else the block's floor."""
    for column in (INDEX_COLUMN, NAME_COLUMN):
        value = sheets.text(ws, row, column)
        for token in FLOOR_TOKENS:
            if value.startswith(token):
                return token
    for probe in (row + 1,):
        value = sheets.text(ws, probe, NAME_COLUMN)
        for token in FLOOR_TOKENS:
            if value.startswith(token):
                return token
    return current_floor


def _is_quota_row(name_label: str, rank_label: str) -> bool:
    joined = f"{name_label} {rank_label}".lower()
    return any(marker in joined for marker in _QUOTA_MARKERS)


def _read_quota(ws, row: int, dates_by_column: dict[int, Date]) -> dict[Date, int]:
    """'Quoto for request O' - how many staff requests the home allows that day."""
    out: dict[Date, int] = {}
    for column, date in dates_by_column.items():
        number = sheets.to_number(sheets.text(ws, row, column))
        if number is not None:
            out[date] = int(number)
    return out


def _looks_like_events(ws, row: int, date_columns: list[int]) -> bool:
    """The events row holds free text on most days and no rank or name."""
    values = [sheets.text(ws, row, column) for column in date_columns]
    filled = [v for v in values if v]
    if len(filled) < 3:
        return False
    return sum(1 for v in filled if len(v) > 2 or re.search(r"[一-鿿]", v)) >= 2


def _read_events(ws, sheet_name: str, row: int,
                 dates_by_column: dict[int, Date]) -> list[ParsedEvent]:
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


def _attach_subrow(ws, row: int, date_columns: list[int],
                   dates_by_column: dict[int, Date], staff_key: str,
                   cells: list[ParsedCell], by_key: dict[str, ParsedStaff],
                   sheet_name: str, issues: list[Issue]) -> None:
    """Fold the floor/duty row underneath a staff member into their cells."""
    by_date = {c.date: c for c in cells if c.staff_key == staff_key}
    named: list[str] = []
    for column in date_columns:
        value = sheets.text(ws, row, column)
        if not value:
            continue
        note = parse_subrow(value)
        cell = by_date.get(dates_by_column[column])
        if not cell:
            continue
        if note.floor:
            cell.unit_name = note.floor
        if note.tasks:
            cell.extra_tasks = tuple(dict.fromkeys(cell.extra_tasks + note.tasks))
        # A person's name on the floor row is who covered that day's duty.
        for candidate in note.notes:
            if sheets.is_personal_name(candidate):
                cell.relief_name = cell.relief_name or candidate
                named.append(candidate)
    if named:
        # Reported once per row: a floor row full of names belongs to whichever
        # pool row it sits beside, and the homes are not consistent about which.
        issues.append(Issue(
            "relief_names_on_floor_row",
            f"{len(named)} relief name(s) on the floor row of "
            f"{by_key[staff_key].display_name} "
            f"({', '.join(sorted(set(named)))})", "info", sheet=sheet_name,
            cell_ref=sheets.cell_ref(sheet_name, row, date_columns[0])))


def _summary_number(ws, row: int, summary_columns: dict[str, int], key: str,
                    *, as_int: bool = False) -> float | int | None:
    column = summary_columns.get(key)
    if not column:
        return None
    number = sheets.to_number(sheets.text(ws, row, column))
    if number is None:
        return None
    return int(number) if as_int else number
