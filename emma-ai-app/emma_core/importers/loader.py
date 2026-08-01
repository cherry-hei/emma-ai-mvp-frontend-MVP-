"""Write a parsed roster workbook into the database (spec 1.4).

`apply` is the only function here that mutates anything, and it does so in the
order the schema requires: reference data, then staff, then the period and
version, then the roster content, then the records derived from it (leave, tasks,
events, holidays, facility configuration).

Two behaviours are worth knowing before reading the code.

**Leave is charged against a real balance.** The Phase 5 trigger
`sync_leave_balance_usage` refuses an approved leave request unless exactly one
configured `leave_balances` row covers every requested day and the balance can
absorb it. An import that created leave rows without balances would either fail
or - worse - silently teach the system that leave is unlimited. So the loader
sizes each staff member's balance from what the home actually recorded, carrying
in the compensatory hours printed in the workbook's own summary column, and only
then writes the requests.

**Nothing is written in validate mode.** `mode="validate"` performs the same
reads and reports what a commit would create, which is what makes the endpoint's
"validation summary" trustworthy: it is the commit path minus the writes.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as Date, timedelta

from ..constants import AssignmentStatus, RosterStatus
from ..shifttime import paid_minutes
from .plan import ParsedCell, ParsedRoster, ParsedStaff
from .vocab import LEAVE_CODES

# Contract defaults per employment type, from the scheduling specification.
# Imported labour rests 12 hours between duties; local staff 11.
_MIN_REST_MINUTES = {"imported_labor": 720}
_DEFAULT_MIN_REST = 660
_WEEKLY_HOURS = {
    "local_ft": 44, "local_pt": 24, "imported_labor": 60,
    "agency": None, "outsource": None, "casual": None,
}
# A balance is sized to what the home recorded plus a little headroom, so a
# correction entered after the import does not immediately breach the trigger.
_BALANCE_HEADROOM_DAYS = 2


@dataclass
class LoadResult:
    """What the import did (or, in validate mode, would do)."""

    mode: str
    facility_id: str
    period_id: str | None = None
    roster_version_id: str | None = None
    staff_matched: int = 0
    staff_created: int = 0
    shift_definitions: int = 0
    task_definitions: int = 0
    units: int = 0
    shifts: int = 0
    assignments: int = 0
    task_assignments: int = 0
    leave_requests: int = 0
    leave_balances: int = 0
    events: int = 0
    calendar_days: int = 0
    facility_configs: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    # Findings about the loaded roster that the caller should record alongside the
    # parser's own issues - see _check_resident_counts.
    warnings: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def apply(client, parsed: ParsedRoster, *, mode: str = "commit",
          version_label: str | None = None, version_status: str = "draft",
          created_by: str | None = None, replace_period: bool = True,
          write_period_records: bool = True) -> LoadResult:
    """Load one parsed workbook into its facility.

    ``version_status`` of ``published`` makes the imported roster the operative
    one for its period, which is what a historical "as worked" sheet is. The
    caller supplies a service-role client: creating staff and publishing a roster
    are trusted server operations, not tenant writes.

    ``write_period_records`` controls the records that belong to the *period*
    rather than to one version of it - leave, events, holidays, configuration.
    Home A publishes each cycle twice (the plan, then the roster as worked), and
    both sheets describe the same month's leave; only the authoritative sheet
    should write it, or the period ends up with two of everything.
    """
    if mode not in ("validate", "commit"):
        raise ValueError("mode must be 'validate' or 'commit'")

    facility = _facility(client, parsed.facility_code)
    result = LoadResult(mode=mode, facility_id=facility["id"])
    write = mode == "commit"

    units = _ensure_units(client, facility["id"], parsed, result, write=write)
    _ensure_shift_definitions(client, facility["id"], parsed, result, write=write)
    task_ids = _ensure_task_definitions(client, facility["id"], parsed, result,
                                        write=write)
    staff_ids = _ensure_staff(client, facility["id"], parsed, units, result,
                              write=write)
    period = _ensure_period(client, facility["id"], parsed, result, write=write)
    if not write:
        result.shifts = len([c for c in parsed.cells if _cell_shift_code(c)])
        result.leave_requests = len(_leave_spans(parsed))
        result.events = len(parsed.events)
        return result

    version = _create_version(client, facility["id"], period["id"], parsed,
                              label=version_label, created_by=created_by,
                              replace_period=replace_period, result=result)
    _write_cells(client, facility["id"], parsed, version["id"], staff_ids, units,
                 task_ids, result)
    if write_period_records:
        _write_leave(client, facility["id"], parsed, period["id"], staff_ids, result)
        _write_events(client, facility["id"], parsed, units, result)
        _write_calendar_days(client, facility["id"], parsed, result)
        _write_facility_configs(client, facility["id"], parsed, created_by, result)
    _check_resident_counts(client, facility["id"], parsed, result)
    if version_status == RosterStatus.PUBLISHED:
        _publish(client, facility["id"], version["id"], created_by, result)
    return result


# ── reference data ───────────────────────────────────────────────────────────
def _facility(client, code: str) -> dict:
    # SQL: select * from facilities where code = :code
    rows = client.table("facilities").select("*").eq("code", code).execute().data
    if not rows:
        raise ValueError(f"facility {code!r} does not exist; create it before importing")
    return rows[0]


def _ensure_units(client, facility_id: str, parsed: ParsedRoster,
                  result: LoadResult, *, write: bool) -> dict[str, str]:
    """Return {unit name -> id}, creating the profile's units and any floor the
    workbook mentions that the facility does not have yet."""
    # SQL: select id, name from facility_units where facility_id = :facility_id
    existing = {r["name"]: r["id"] for r in
                client.table("facility_units").select("id,name")
                .eq("facility_id", facility_id).execute().data}
    wanted: dict[str, str] = {name: unit_type
                              for unit_type, name, _ in parsed.profile.units}
    for cell in parsed.cells:
        if cell.unit_name and cell.unit_name not in wanted:
            wanted[cell.unit_name] = "floor"
    missing = [(name, kind) for name, kind in wanted.items() if name not in existing]
    result.units = len(missing)
    if not (write and missing):
        return existing
    codes = {name: code for _, name, code in parsed.profile.units}
    # SQL: insert into facility_units (facility_id, unit_type, name, code)
    #      values ... returning id, name
    created = client.table("facility_units").insert([
        {"facility_id": facility_id, "unit_type": kind, "name": name,
         "code": codes.get(name) or name.replace("/", "")}
        for name, kind in missing
    ]).execute().data
    existing.update({r["name"]: r["id"] for r in created})
    return existing


def _ensure_shift_definitions(client, facility_id: str, parsed: ParsedRoster,
                              result: LoadResult, *, write: bool) -> None:
    """Register every duty code the sheets use, plus the non-working codes their
    leave vocabulary needs, so a manual edit can pick any of them."""
    # SQL: select shift_type from shift_definitions where facility_id = :facility_id
    existing = {r["shift_type"] for r in
                client.table("shift_definitions").select("shift_type")
                .eq("facility_id", facility_id).execute().data}
    rows = []
    for window in parsed.profile.shift_windows:
        if window.code in existing:
            continue
        segments = [dict(s) for s in window.segments] or None
        rows.append({
            "facility_id": facility_id, "shift_type": window.code,
            "label": window.label, "start_time": window.start,
            "end_time": window.end, "cross_midnight": window.cross_midnight,
            "is_working": window.is_working, "segments": segments,
            "paid_minutes": paid_minutes({"segments": segments}) if segments else None,
            "weighting_factor": window.weighting_factor,
            "source_note": f"imported from {parsed.source_name}",
        })
        existing.add(window.code)
    for code in sorted({c.shift_code for c in LEAVE_CODES.values()}):
        if code in existing:
            continue
        leave = next(c for c in LEAVE_CODES.values() if c.shift_code == code)
        # Every key present on every row: PostgREST unifies the column list across
        # a bulk insert, so an omitted key becomes an explicit null.
        rows.append({
            "facility_id": facility_id, "shift_type": code, "label": leave.label,
            "start_time": None, "end_time": None, "cross_midnight": False,
            "is_working": False, "segments": None, "paid_minutes": None,
            "weighting_factor": 0,
            "source_note": f"imported from {parsed.source_name}",
        })
        existing.add(code)
    result.shift_definitions = len(rows)
    if write and rows:
        # SQL: insert into shift_definitions (...) values ...
        client.table("shift_definitions").insert(rows).execute()


class TaskDictionary:
    """Resolves a written task code to the task definition the validator will see.

    The same code legitimately exists more than once - ``A1`` is a different duty
    for an HW than for a CW - and a facility can also carry retired rows. The
    validator only loads *active* definitions, so linking a cell to an inactive one
    makes it report "Unknown task" against a code the home writes every day.
    Resolution therefore prefers an active row whose rank and shift match the cell.
    """

    def __init__(self, rows: list[dict]):
        self._by_code: dict[str, list[dict]] = {}
        for row in rows:
            self._by_code.setdefault(row["task_code"], []).append(row)

    def resolve(self, code: str, rank: str | None, shift_type: str | None) -> str | None:
        candidates = [r for r in self._by_code.get(code, []) if r.get("active", True)]
        if not candidates:
            return None
        candidates.sort(key=lambda r: (
            _rank_matches(rank, r.get("required_rank")),
            not r.get("required_rank"),                    # unrestricted next
            r.get("shift_type") == shift_type,
            not r.get("shift_type"),
        ), reverse=True)
        return candidates[0]["id"]

    def add(self, rows: list[dict]) -> None:
        for row in rows:
            self._by_code.setdefault(row["task_code"], []).append(row)

    def covers(self, code: str, rank: str | None) -> bool:
        """Is there an active definition of `code` this rank may actually perform?

        Task codes are profession-specific, so a code defined only for HW does not
        cover a CW performing it - the facility needs its own row for that rank.
        """
        return any(r.get("active", True) and _rank_matches(rank, r.get("required_rank"))
                   for r in self._by_code.get(code, []))


def _ensure_task_definitions(client, facility_id: str, parsed: ParsedRoster,
                             result: LoadResult, *, write: bool) -> TaskDictionary:
    """Register the task codes the cells carry (A1-A8 / P1-P6 / N2-N3) and the
    standing duties Home B writes on its floor row."""
    # SQL: select id, task_code, required_rank, shift_type, active
    #      from task_definitions where facility_id = :facility_id
    dictionary = TaskDictionary(
        client.table("task_definitions")
        .select("id,task_code,required_rank,shift_type,active")
        .eq("facility_id", facility_id).execute().data)

    # Keyed by (code, rank): the homes' rosters are the evidence of which rank
    # performs which code, and a code the facility has not defined for that rank
    # needs its own definition rather than borrowing another profession's.
    seen: dict[tuple[str, str | None], str | None] = {}
    for cell in parsed.cells:
        rank = _rank_of(parsed, cell.staff_key)
        for code in cell.intent.task_codes:
            seen.setdefault((code, rank), cell.intent.duties[0].shift_code)
        for label in cell.extra_tasks:
            seen.setdefault((label, rank), None)
    missing = {key: shift for key, shift in seen.items()
               if not dictionary.covers(key[0], key[1])}
    result.task_definitions = len(missing)
    if not (write and missing):
        return dictionary
    # SQL: insert into task_definitions
    #        (facility_id, task_code, task_name, required_rank, shift_type, active,
    #         description)
    #      values ... returning id, task_code, required_rank, shift_type, active
    created = client.table("task_definitions").insert([
        {"facility_id": facility_id, "task_code": code, "task_name": code,
         "required_rank": rank, "shift_type": shift, "active": True,
         "description": f"imported from {parsed.source_name}"}
        for (code, rank), shift in sorted(missing.items(),
                                          key=lambda kv: (kv[0][0], kv[0][1] or ""))
    ]).execute().data
    dictionary.add(created)
    return dictionary


def _rank_matches(actual: str | None, required: str | None) -> bool:
    """The task dictionary's own view of rank, matching the Phase 4 evaluator."""
    from ..services.scheduling import task_rank_matches

    return task_rank_matches(actual, required)


def _ensure_staff(client, facility_id: str, parsed: ParsedRoster,
                  units: dict[str, str], result: LoadResult, *,
                  write: bool) -> dict[str, str]:
    """Match each roster row to a staff record, creating the ones that are new.

    Home A anonymises its staff as row labels, Home B writes names; both are
    matched on the displayed name so re-importing the same home updates rather
    than duplicates.
    """
    # SQL: select id, name from staff where facility_id = :facility_id
    existing = {r["name"]: r["id"] for r in
                client.table("staff").select("id,name")
                .eq("facility_id", facility_id).execute().data}
    ids: dict[str, str] = {}
    to_create: list[ParsedStaff] = []
    for member in parsed.staff:
        found = existing.get(member.display_name)
        if found:
            ids[member.key] = found
            result.staff_matched += 1
        else:
            to_create.append(member)
    result.staff_created = len(to_create)
    if not (write and to_create):
        return ids

    # SQL: insert into staff (facility_id, name, rank, employment_type,
    #        primary_unit_id, contracted_hours, is_audited_for_medication,
    #        is_mentor, status)
    #      values ... returning id, name
    created = client.table("staff").insert([{
        "facility_id": facility_id, "name": member.display_name,
        "rank": member.rank, "employment_type": member.employment_type,
        "primary_unit_id": units.get(member.unit_name or ""),
        "contracted_hours": _WEEKLY_HOURS.get(member.employment_type),
        # Medication audit follows rank in both homes; the unaudited-agency rule
        # (spec 4.1) then restricts what an external worker may be given.
        "is_audited_for_medication": member.rank in ("RN", "EN", "HW"),
        "is_mentor": member.rank == "RN",
        "status": "active",
    } for member in to_create]).execute().data
    by_name = {r["name"]: r["id"] for r in created}
    for member in to_create:
        ids[member.key] = by_name[member.display_name]

    # SQL: insert into staff_contracts (facility_id, staff_id, weekly_hours,
    #        max_weekly_hours, min_rest_minutes, allowed_shift_types, effective_from)
    #      values ...
    working_codes = sorted({w.code for w in parsed.profile.shift_windows
                            if w.is_working})
    client.table("staff_contracts").insert([{
        "facility_id": facility_id, "staff_id": ids[member.key],
        "weekly_hours": _WEEKLY_HOURS.get(member.employment_type),
        "max_weekly_hours": (_WEEKLY_HOURS.get(member.employment_type) or 0) + 10
                            or None,
        "min_rest_minutes": _MIN_REST_MINUTES.get(member.employment_type,
                                                  _DEFAULT_MIN_REST),
        "allowed_shift_types": working_codes,
        "effective_from": parsed.period_start.isoformat(),
    } for member in to_create]).execute()
    return ids


# ── period and version ───────────────────────────────────────────────────────
def _ensure_period(client, facility_id: str, parsed: ParsedRoster,
                   result: LoadResult, *, write: bool) -> dict:
    """Reuse the period that already covers the workbook's dates, else create it."""
    # SQL: select * from roster_periods
    #      where facility_id = :facility_id and period_start = :start
    #        and period_end = :end
    rows = (client.table("roster_periods").select("*")
            .eq("facility_id", facility_id)
            .eq("period_start", parsed.period_start.isoformat())
            .eq("period_end", parsed.period_end.isoformat()).execute().data)
    if rows:
        result.period_id = rows[0]["id"]
        return rows[0]
    if not write:
        return {"id": None}
    # SQL: insert into roster_periods
    #        (facility_id, period_start, period_end, cycle_type, status)
    #      values (..., 'rostered') returning *
    period = client.table("roster_periods").insert({
        "facility_id": facility_id,
        "period_start": parsed.period_start.isoformat(),
        "period_end": parsed.period_end.isoformat(),
        "cycle_type": parsed.profile.cycle_type,
        "status": "planning",
    }).execute().data[0]
    result.period_id = period["id"]
    return period


def _create_version(client, facility_id: str, period_id: str,
                    parsed: ParsedRoster, *, label: str | None,
                    created_by: str | None, replace_period: bool,
                    result: LoadResult) -> dict:
    """Create the roster version this workbook becomes.

    ``replace_period`` drops any earlier version carrying the same label, so
    re-running an import corrects the roster instead of stacking duplicates.
    """
    label = label or f"{parsed.source_name} ({parsed.period_start:%b %Y})"
    if replace_period:
        # SQL: select id from roster_versions
        #      where facility_id = :facility_id and period_id = :period_id
        #        and label = :label
        stale = (client.table("roster_versions").select("id")
                 .eq("facility_id", facility_id).eq("period_id", period_id)
                 .eq("label", label).execute().data)
        for row in stale:
            # Content cascades from the version, and the service client is
            # allowed to remove an operative one.
            # SQL: delete from roster_versions where id = :id
            client.table("roster_versions").delete().eq("id", row["id"]).execute()
    # SQL: insert into roster_versions
    #        (facility_id, period_id, version_type, label, status, created_by)
    #      values (..., 'manual', :label, 'draft', :created_by) returning *
    version = client.table("roster_versions").insert({
        "facility_id": facility_id, "period_id": period_id,
        "version_type": "manual", "label": label,
        "status": RosterStatus.DRAFT, "created_by": created_by,
    }).execute().data[0]
    result.roster_version_id = version["id"]
    return version


def _publish(client, facility_id: str, version_id: str, created_by: str | None,
             result: LoadResult) -> None:
    """Publish an imported 'as worked' roster - if it passes validation.

    `publish_roster_version` requires a passed deterministic validation run, and
    that gate is not negotiable just because the roster is historical: a month
    that breached the rules must not become an operative, rule-compliant record
    merely by being imported.

    So the import validates, and publishes only on a pass. On a fail the version
    stays a draft and the violation count is reported - which is the answer the
    pilot actually wants from importing a real month.
    """
    from ..services.roster import publish_version
    from ..services.validation import validate_roster

    validation = validate_roster(client, facility_id, version_id,
                                 validated_by=created_by, persist=True)
    if not validation.get("passes"):
        result.warnings.append({
            "severity": "warning", "code": "not_publishable",
            "message": (
                f"The imported roster has "
                f"{validation.get('hard_violation_count', 0)} hard compliance "
                "violation(s) against the current rule set, so it stays a draft. "
                "Open Validate on the roster for the breakdown."),
            "raw_value": f"score {validation.get('constraint_score')}",
        })
        return
    publish_version(client, facility_id=facility_id,
                    roster_version_id=version_id, created_by=created_by)
    result.warnings.append({
        "severity": "info", "code": "published",
        "message": "The imported roster passed validation and is now the "
                   "operative version for its period.",
    })


# ── roster content ───────────────────────────────────────────────────────────
def _cell_shift_code(cell: ParsedCell) -> str | None:
    """The shift type a cell becomes: its duty, else its leave's non-working code."""
    if cell.intent.duties:
        return cell.intent.duties[0].shift_code
    if cell.intent.leave:
        return cell.intent.leave.shift_code
    return None


def _write_cells(client, facility_id: str, parsed: ParsedRoster, version_id: str,
                 staff_ids: dict[str, str], units: dict[str, str],
                 task_ids: TaskDictionary, result: LoadResult) -> None:
    """One shift + assignment per staff × day, including the non-working days.

    Rest days and leave are written as non-working shifts, the same shape the
    manual editor produces, so the roster grid renders exactly what the home
    wrote rather than a hole.
    """
    shift_rows, meta = [], []
    skipped: dict[str, int] = defaultdict(int)
    for cell in parsed.cells:
        staff_id = staff_ids.get(cell.staff_key)
        code = _cell_shift_code(cell)
        if not staff_id or not code:
            skipped["no_shift_code" if staff_id else "unmatched_staff"] += 1
            continue
        duty = cell.intent.duties[0] if cell.intent.duties else None
        segments = [dict(s) for s in (duty.segments if duty else ())] or None
        shift_rows.append({
            "facility_id": facility_id, "roster_version_id": version_id,
            "date": cell.date.isoformat(), "shift_type": code,
            "start_time": duty.start if duty else None,
            "end_time": duty.end if duty else None,
            "cross_midnight": bool(duty and duty.end and duty.start
                                   and duty.end <= duty.start),
            "unit_id": units.get(cell.unit_name or ""),
            "required_rank": _rank_of(parsed, cell.staff_key),
            "required_count": 1,
            "is_working": cell.intent.is_working,
            "segments": segments,
            "paid_minutes": paid_minutes({"segments": segments}) if segments else None,
        })
        meta.append((cell, staff_id))

    shift_ids = _insert_many(client, "shifts", shift_rows)
    result.shifts = len(shift_ids)

    assignment_rows = []
    for shift_id, (cell, staff_id) in zip(shift_ids, meta):
        labels = list(cell.intent.task_codes) + list(cell.extra_tasks)
        assignment_rows.append({
            "facility_id": facility_id, "shift_id": shift_id,
            "staff_id": staff_id, "role": _rank_of(parsed, cell.staff_key),
            "status": AssignmentStatus.ASSIGNED,
            "is_agency": _is_external(parsed, cell.staff_key),
            "tasks": labels,
        })
    assignment_ids = _insert_many(client, "shift_assignments", assignment_rows)
    result.assignments = len(assignment_ids)

    task_rows = []
    for assignment_id, (cell, staff_id) in zip(assignment_ids, meta):
        rank = _rank_of(parsed, cell.staff_key)
        shift_code = _cell_shift_code(cell)
        for label in list(cell.intent.task_codes) + list(cell.extra_tasks):
            task_rows.append({
                "facility_id": facility_id, "shift_assignment_id": assignment_id,
                "roster_version_id": version_id, "staff_id": staff_id,
                "task_id": task_ids.resolve(label, rank, shift_code),
                "task_label": label,
                "task_status": "pending", "source_type": "legacy_cell",
            })
    result.task_assignments = len(_insert_many(client, "task_assignments", task_rows))
    result.skipped = dict(skipped)


def _rank_of(parsed: ParsedRoster, staff_key: str) -> str | None:
    for member in parsed.staff:
        if member.key == staff_key:
            return member.rank
    return None


def _is_external(parsed: ParsedRoster, staff_key: str) -> bool:
    for member in parsed.staff:
        if member.key == staff_key:
            return member.employment_type in ("agency", "outsource", "casual")
    return False


# ── leave ────────────────────────────────────────────────────────────────────
def _leave_spans(parsed: ParsedRoster) -> list[tuple[str, str, Date, Date, str]]:
    """Collapse consecutive leave cells into (staff_key, type, start, end, category).

    A five-day annual-leave block is one request in the source and should be one
    request in the database, not five.
    """
    by_staff_type: dict[tuple[str, str], list[Date]] = defaultdict(list)
    categories: dict[str, str] = {}
    for cell in parsed.cells:
        leave = cell.intent.leave
        if not leave or not leave.is_leave_request:
            continue
        by_staff_type[(cell.staff_key, leave.code)].append(cell.date)
        categories[leave.code] = leave.category

    spans: list[tuple[str, str, Date, Date, str]] = []
    for (staff_key, code), dates in by_staff_type.items():
        dates.sort()
        start = previous = dates[0]
        for current in dates[1:]:
            if current - previous > timedelta(days=1):
                spans.append((staff_key, code, start, previous, categories[code]))
                start = current
            previous = current
        spans.append((staff_key, code, start, previous, categories[code]))
    return spans


def _write_leave(client, facility_id: str, parsed: ParsedRoster, period_id: str,
                 staff_ids: dict[str, str], result: LoadResult) -> None:
    """Write the leave the roster records, with the balances it has to charge.

    Order matters: `sync_leave_balance_usage` rejects an approved request unless a
    single configured balance already covers every day of it.
    """
    spans = [s for s in _leave_spans(parsed) if s[0] in staff_ids]
    if not spans:
        return

    days_used: dict[tuple[str, str], int] = defaultdict(int)
    for staff_key, code, start, end, _ in spans:
        days_used[(staff_key, code)] += (end - start).days + 1
    carried = {m.key: (m.carried_cl_hours or 0) for m in parsed.staff}

    # Re-importing a period rewrites its leave rather than adding a second copy.
    # The requests go first: deleting an approved request releases the balance it
    # charged, so the balance rows are only removable afterwards.
    #
    # SQL: delete from leave_requests
    #      where facility_id = :facility_id and staff_id = any(:staff_ids)
    #        and date_start >= :period_start and date_end <= :period_end
    #        and remark like 'imported from %'
    owned_staff = sorted(set(staff_ids.values()))
    (client.table("leave_requests").delete()
     .eq("facility_id", facility_id).in_("staff_id", owned_staff)
     .gte("date_start", parsed.period_start.isoformat())
     .lte("date_end", parsed.period_end.isoformat())
     .like("remark", "imported from %").execute())
    # SQL: delete from leave_balances
    #      where facility_id = :facility_id and period_id = :period_id
    #        and staff_id = any(:staff_ids)
    (client.table("leave_balances").delete()
     .eq("facility_id", facility_id).eq("period_id", period_id)
     .in_("staff_id", owned_staff).execute())

    balance_rows = []
    for (staff_key, code), days in sorted(days_used.items()):
        # Compensatory pools open with the hours the home carried forward; every
        # other type opens with what the roster consumed, plus headroom.
        carried_days = round(carried.get(staff_key, 0) / 8, 2) if code in ("CL", "CO") else 0
        balance_rows.append({
            "facility_id": facility_id, "staff_id": staff_ids[staff_key],
            "period_id": period_id, "leave_type": code,
            "opening_balance": days + _BALANCE_HEADROOM_DAYS,
            "carried": carried_days,
        })
    result.leave_balances = len(_insert_many(client, "leave_balances", balance_rows))

    # SQL: insert into leave_requests (facility_id, staff_id, category, leave_type,
    #        date_start, date_end, status, reason, remark, decided_at)
    #      values ...   -- 'approved': these are days the home already worked to
    request_rows = []
    for staff_key, code, start, end, category in sorted(
            spans, key=lambda s: (s[0], s[2])):
        leave = LEAVE_CODES[code]
        request_rows.append({
            "facility_id": facility_id, "staff_id": staff_ids[staff_key],
            "category": category, "leave_type": code,
            "date_start": start.isoformat(), "date_end": end.isoformat(),
            "status": "approved",
            "reason": f"{leave.label} ({leave.label_zh})" if leave.label_zh
                      else leave.label,
            "remark": f"imported from {parsed.source_name}",
            # A roster records the leave that was taken, never the day it was
            # asked for. Flagging that keeps the request-cutoff rule from judging
            # a deadline the source does not contain - see evaluate_leave_rules.
            "policy_result_json": {
                "source": "roster_import",
                "source_name": parsed.source_name,
                "submitted_on_unknown": True,
            },
        })
    result.leave_requests = len(_insert_many(client, "leave_requests", request_rows))


# ── events, holidays, configuration ──────────────────────────────────────────
def _write_events(client, facility_id: str, parsed: ParsedRoster,
                  units: dict[str, str], result: LoadResult) -> None:
    """The events row becomes facility_events, so Phase 4.2 demand overlays and
    the roster date headers show what the home actually had on."""
    if not parsed.events:
        return
    dates = sorted({e.date for e in parsed.events})
    # SQL: delete from facility_events
    #      where facility_id = :facility_id and date >= :first and date <= :last
    #        and notes like 'imported from %'
    (client.table("facility_events").delete()
     .eq("facility_id", facility_id)
     .gte("date", dates[0].isoformat()).lte("date", dates[-1].isoformat())
     .like("notes", "imported from %").execute())
    rows = [{
        "facility_id": facility_id, "event_type": _event_type(event.title),
        "date": event.date.isoformat(), "title": event.title[:200],
        "demand_json": {"markers": list(event.markers), "source": event.raw},
        "notes": f"imported from {parsed.source_name}",
    } for event in parsed.events]
    result.events = len(_insert_many(client, "facility_events", rows))


# The recurring events the homes name, mapped to the Phase 4.2 event types the
# staffing overlays are configured against. Anything else stays 'other'.
_EVENT_TYPES = (
    ("CGAT", "cgat"), ("PGT", "pgt"), ("VMO", "vmo"),
    ("剪髮", "hair_cutting"), ("足療", "podiatry"), ("磅重", "weighing"),
    ("藥板", "medication_check"), ("藥紙", "medication_check"),
    ("藥物", "medication_check"), ("會議", "meeting"), ("職員會", "meeting"),
    ("懇親", "visiting"), ("探訪", "visiting"), ("講座", "training"),
    ("培訓", "training"), ("導向", "training"), ("活動", "activity"),
    ("營養", "assessment"), ("評估", "assessment"), ("消防", "fire_drill"),
    ("走火警", "fire_drill"),
)


def _event_type(title: str) -> str:
    upper = title.upper()
    for token, event_type in _EVENT_TYPES:
        if token in title or token in upper:
            return event_type
    return "other"


def _write_calendar_days(client, facility_id: str, parsed: ParsedRoster,
                         result: LoadResult) -> None:
    """Statutory and public holidays, as evidenced by the roster's own cells.

    The homes mark 法 / 公 on the day itself, so the calendar the solver and cost
    engine read is derived from the roster rather than typed in twice.
    """
    holidays: dict[Date, str] = {}
    for cell in parsed.cells:
        leave = cell.intent.leave
        if leave and leave.code in ("SH", "PH"):
            holidays.setdefault(cell.date, leave.code)
    if not holidays:
        return
    dates = sorted(holidays)
    # SQL: select date from calendar_days
    #      where facility_id = :facility_id and date = any(:dates)
    present = {str(r["date"])[:10] for r in
               client.table("calendar_days").select("date")
               .eq("facility_id", facility_id)
               .in_("date", [d.isoformat() for d in dates]).execute().data}
    rows = [{
        "facility_id": facility_id, "date": date.isoformat(),
        "day_type": "statutory_holiday" if code == "SH" else "public_holiday",
        "holiday_name": LEAVE_CODES[code].label,
        # Home A's calendar bans agency cover on a peak holiday (spec 5.4); the
        # restriction is configured per facility, so the imported day only
        # records the multiplier the rosters price against.
        "is_agency_allowed": True, "staff_cost_multiplier": 2.0,
        "notes": f"imported from {parsed.source_name}",
    } for date, code in sorted(holidays.items()) if date.isoformat() not in present]
    result.calendar_days = len(_insert_many(client, "calendar_days", rows))


def _write_facility_configs(client, facility_id: str, parsed: ParsedRoster,
                            created_by: str | None, result: LoadResult) -> None:
    """Record what the workbook says the facility looks like (spec 2.2)."""
    configs = {
        "scheduling_cycle": {
            "cycle_type": parsed.profile.cycle_type,
            "cycle_days": parsed.profile.scheduling_cycle_days,
            "period_start": parsed.period_start.isoformat(),
            "period_end": parsed.period_end.isoformat(),
        },
        "shift_dictionary": {
            "sheets": [
                {"sheet": sheet.name, "note": sheet.note,
                 "windows": [{"code": w.code, "label": w.label, "start": w.start,
                              "end": w.end,
                              "segments": [dict(s) for s in w.segments],
                              "weighting_factor": w.weighting_factor}
                             for w in sheet.windows]}
                for sheet in parsed.profile.sheets
            ],
        },
    }
    if parsed.request_quota:
        configs["request_quota"] = {
            "note": "staff duty/leave requests the home allows per day",
            "by_date": {d.isoformat(): n
                        for d, n in sorted(parsed.request_quota.items())},
        }
    rows = []
    for key, payload in configs.items():
        # Superseding a config deactivates the previous version rather than
        # overwriting it, so a configuration change stays auditable.
        # SQL: update facility_json_configs set active = false
        #      where facility_id = :facility_id and config_key = :key and active
        previous = (client.table("facility_json_configs")
                    .select("version")
                    .eq("facility_id", facility_id).eq("config_key", key)
                    .order("version", desc=True).limit(1).execute().data)
        (client.table("facility_json_configs").update({"active": False})
         .eq("facility_id", facility_id).eq("config_key", key)
         .eq("active", True).execute())
        rows.append({
            "facility_id": facility_id, "config_key": key,
            "config_json": payload,
            "version": (previous[0]["version"] + 1) if previous else 1,
            "description": f"imported from {parsed.source_name}",
            "effective_from": parsed.period_start.isoformat(),
            "active": True, "created_by": created_by,
        })
    result.facility_configs = len(_insert_many(client, "facility_json_configs", rows))


def _check_resident_counts(client, facility_id: str, parsed: ParsedRoster,
                           result: LoadResult) -> None:
    """Report the days the imported roster cannot be ratio-checked.

    A roster spreadsheet records who worked, never how many residents were in the
    home, and the resident count is the denominator of every statutory ratio. The
    importer will not invent one: it reports the gap so a manager fills it in
    through `POST /resident-counts` (spec 3.4), because a fabricated denominator
    would turn a breach into a pass.
    """
    if not parsed.dates:
        return
    # SQL: select date from daily_resident_counts
    #      where facility_id = :facility_id and date >= :first and date <= :last
    counted = {str(r["date"])[:10] for r in
               client.table("daily_resident_counts").select("date")
               .eq("facility_id", facility_id)
               .gte("date", parsed.dates[0].isoformat())
               .lte("date", parsed.dates[-1].isoformat()).execute().data}
    missing = [d.isoformat() for d in parsed.dates if d.isoformat() not in counted]
    if not missing:
        return
    result.warnings.append({
        "severity": "warning", "code": "missing_resident_counts",
        "message": (f"{len(missing)} of {len(parsed.dates)} imported days have no "
                    "daily resident count, so statutory staffing-ratio checks "
                    "cannot be evaluated for them. Enter counts via "
                    "POST /resident-counts."),
        "raw_value": f"{missing[0]} .. {missing[-1]}",
    })


# ── batching ─────────────────────────────────────────────────────────────────
_BATCH = 500


def _insert_many(client, table: str, rows: list[dict]) -> list[str]:
    """Insert in batches, returning ids in the order the rows were given.

    PostgREST returns inserted rows in input order, which is what lets the caller
    zip shift ids back onto the cells they came from.
    """
    ids: list[str] = []
    for start in range(0, len(rows), _BATCH):
        chunk = rows[start:start + _BATCH]
        # SQL: insert into <table> (<keys>) values (...), (...) returning id
        response = client.table(table).insert(
            json.loads(json.dumps(chunk, default=str))).execute()
        ids.extend(r["id"] for r in response.data)
    return ids
