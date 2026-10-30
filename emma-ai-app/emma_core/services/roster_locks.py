"""Roster cells the optimiser must not move (spec SA.5).

When a manager approves a day-off or a duty request, the roster cell stops being
a suggestion. The solver already understands a lock, but only as an argument to
one run (`solver/inputs.py::LockedAssignment`); an approval is a promise made to
a person and has to outlive whichever solve happens to be in flight. So it is
persisted and read back on every optimisation.

A lock is released, never deleted. "Why was she off on the 12th?" has to stay
answerable after the approval behind it is revoked.
"""
from __future__ import annotations

from datetime import date as Date, timedelta

from ._common import as_date, iso, now_iso

# leave_type -> what the approval promises. Absent from this map means the
# approval carries no cell-level promise: AL and SL already make the person
# unavailable through the `approved_leave_unavailable` rule, and duplicating
# that as a lock would report the same constraint twice to the approver.
DUTY_LOCKS = {
    "DO": "forbid",             # an approved day off: not rostered at all
    "duty_request": "pin",      # "please give me an A shift that day"
    "shift_swap": "pin",
}


def lock_type_for(leave_type: str) -> str | None:
    return DUTY_LOCKS.get(leave_type)


def _days(start: Date, end: Date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def apply_for_request(client, facility_id: str, request: dict, *,
                      profile_id: str | None = None) -> list[dict]:
    """Lock every day an approved duty/DO request covers. Idempotent.

    Returns the rows written, empty when the request type carries no promise.
    """
    lock_type = lock_type_for(str(request.get("leave_type") or ""))
    if not lock_type:
        return []
    shift_type = request.get("requested_shift_type") if lock_type == "pin" else None
    if lock_type == "pin" and not shift_type:
        raise ValueError(
            "a duty request cannot be locked without a requested_shift_type")

    start, end = as_date(request["date_start"]), as_date(request["date_end"])
    if end < start:
        raise ValueError("date_end is before date_start")

    staff_id = request["staff_id"]
    existing = {
        iso(row["date"]): row
        for row in _live_locks(client, facility_id, staff_id, start, end)
    }

    written: list[dict] = []
    for day in _days(start, end):
        key = day.isoformat()
        held = existing.get(key)
        if held:
            # Same promise already recorded - re-approving must not raise.
            if (held["lock_type"] == lock_type
                    and (held.get("shift_type") or None) == (shift_type or None)
                    and held["source_id"] == request["id"]):
                continue
            raise ValueError(
                f"{key} is already locked for this staff member by "
                f"{held['source_table']} {held['source_id']}"
            )
        # SQL: insert into roster_cell_locks
        #        (facility_id, staff_id, date, lock_type, shift_type,
        #         source_table, source_id, locked_by)
        #      values (...) returning *
        written.append(client.table("roster_cell_locks").insert({
            "facility_id": facility_id, "staff_id": staff_id, "date": key,
            "lock_type": lock_type, "shift_type": shift_type,
            "source_table": "leave_requests", "source_id": request["id"],
            "locked_by": profile_id,
        }).execute().data[0])
    return written


def pin_cell(client, facility_id: str, *, staff_id: str, on: Date | str,
             shift_type: str, source_table: str, source_id: str,
             profile_id: str | None = None) -> dict:
    """Pin one person to one shift on one day. Used by the swap flow (spec SA.6),
    where the promise is a single cell rather than a date range."""
    day = iso(on)
    held = [row for row in _live_locks(client, facility_id, staff_id,
                                       as_date(day), as_date(day))]
    if held:
        existing = held[0]
        if (existing["lock_type"] == "pin"
                and existing.get("shift_type") == shift_type
                and existing["source_id"] == source_id):
            return existing
        raise ValueError(
            f"{day} is already locked for this staff member by "
            f"{existing['source_table']} {existing['source_id']}"
        )
    # SQL: insert into roster_cell_locks
    #        (facility_id, staff_id, date, lock_type, shift_type,
    #         source_table, source_id, locked_by)
    #      values (..., 'pin', ...) returning *
    return client.table("roster_cell_locks").insert({
        "facility_id": facility_id, "staff_id": staff_id, "date": day,
        "lock_type": "pin", "shift_type": shift_type,
        "source_table": source_table, "source_id": source_id,
        "locked_by": profile_id,
    }).execute().data[0]


def release_for(client, facility_id: str, *, source_table: str, source_id: str,
                profile_id: str | None = None, reason: str | None = None) -> list[dict]:
    """Release every live lock a decision created - used when it is revoked."""
    # SQL: update roster_cell_locks
    #      set released_at = now(), released_by = :profile_id, release_reason = :reason
    #      where facility_id = :facility_id and source_table = :source_table
    #        and source_id = :source_id and released_at is null
    #      returning *
    return (client.table("roster_cell_locks").update({
        "released_at": now_iso(), "released_by": profile_id,
        "release_reason": reason,
    }).eq("facility_id", facility_id).eq("source_table", source_table)
        .eq("source_id", source_id).is_("released_at", "null").execute().data)


def _live_locks(client, facility_id: str, staff_id: str,
                start: Date, end: Date) -> list[dict]:
    # SQL: select * from roster_cell_locks
    #      where facility_id = :facility_id and staff_id = :staff_id
    #        and date between :start and :end and released_at is null
    return (client.table("roster_cell_locks").select("*")
            .eq("facility_id", facility_id).eq("staff_id", staff_id)
            .gte("date", start.isoformat()).lte("date", end.isoformat())
            .is_("released_at", "null").execute().data)


def live_for_cell(client, facility_id: str, staff_id: str,
                  on: Date | str) -> list[dict]:
    """Return the unreleased promises for exactly one staff/date cell.

    The database's partial unique index normally means this is zero or one row,
    but callers deliberately evaluate every returned row.  That keeps an
    inconsistent legacy/imported dataset fail-closed rather than silently
    choosing one approval to ignore.
    """
    day = iso(on)
    query = (client.table("roster_cell_locks").select("*")
             .eq("facility_id", facility_id).eq("staff_id", staff_id)
             .eq("date", day))
    # Some deliberately small offline adapters do not implement PostgREST's
    # `is_`; retain the final Python filter so their tests exercise the same
    # released-lock semantics as production.
    is_null = getattr(query, "is_", None)
    if callable(is_null):
        query = is_null("released_at", "null")
    return [
        row for row in query.execute().data
        if row.get("released_at") is None and iso(row.get("date")) == day
    ]


def _code(value: object) -> str:
    return str(value or "").strip().upper()


def cell_conflict(lock: dict, *, shift_type: str | None,
                  is_working: bool) -> str | None:
    """Return the hard-rule reason if a prospective cell conflicts with ``lock``.

    A pin is a promise to work one specific duty, so a non-working cell or an
    alternate code cannot replace it.  A forbid is an approved day off: it
    rejects a working duty but still permits an explicit non-working cell such
    as ``DO``.  This mirrors the solver, whose ``forbid`` eliminates working
    demand slots and whose ``pin`` requires one matching slot.
    """
    lock_type = str(lock.get("lock_type") or "")
    if lock_type == "pin":
        if not is_working:
            return "pin_requires_working_shift"
        if _code(shift_type) != _code(lock.get("shift_type")):
            return "pin_shift_type_mismatch"
        return None
    if lock_type == "forbid":
        return "forbid_rejects_working_shift" if is_working else None
    # An unknown lock type cannot be honoured safely.  Schema constraints should
    # prevent it, but a direct/imported row must not create a bypass.
    return "unknown_lock_type"


def assert_cell_write_permitted(client, facility_id: str, *, staff_id: str,
                                on: Date | str, shift_type: str | None,
                                is_working: bool) -> None:
    """Reject a manual cell write that would break a current durable promise."""
    day = iso(on)
    for lock in live_for_cell(client, facility_id, staff_id, day):
        reason = cell_conflict(lock, shift_type=shift_type, is_working=is_working)
        if reason:
            raise ValueError(
                f"roster cell is locked ({reason}): staff {staff_id}, {day}, "
                f"required {lock.get('lock_type')} {lock.get('shift_type') or ''}".strip()
            )


def assert_cell_clear_permitted(client, facility_id: str, *, staff_id: str,
                                on: Date | str) -> None:
    """Reject deletion of a pinned duty; clearing an already-forbidden day is safe."""
    day = iso(on)
    for lock in live_for_cell(client, facility_id, staff_id, day):
        if str(lock.get("lock_type") or "") != "forbid":
            raise ValueError(
                f"roster cell is locked (pin_requires_working_shift): staff {staff_id}, "
                f"{day}, required pin {lock.get('shift_type') or ''}".strip()
            )


def evaluate_assignments(locks, shifts, assignments) -> list[dict]:
    """Evaluate live locks against a roster version without making database calls.

    Returned rows are deliberately service-neutral so validation can turn them
    into its normal auditable hard findings.  Pins require *exactly one*
    matching active working assignment; forbids reject every active working
    assignment for the promised staff/date.  Shift codes compare case
    insensitively, as solver demand does.
    """
    shifts_by_id = {row.get("id"): row for row in shifts if row.get("id")}
    assignments_by_staff_day: dict[tuple[str, str], list[tuple[dict, dict]]] = {}
    for assignment in assignments:
        if assignment.get("status") == "cancelled":
            continue
        shift = shifts_by_id.get(assignment.get("shift_id"))
        staff_id = assignment.get("staff_id")
        if not shift or not staff_id or not shift.get("date"):
            continue
        key = (str(staff_id), iso(shift["date"]))
        assignments_by_staff_day.setdefault(key, []).append((assignment, shift))

    findings: list[dict] = []
    ordered_locks = sorted(
        (row for row in locks if row.get("released_at") is None),
        key=lambda row: (
            iso(row.get("date")), str(row.get("staff_id") or ""),
            str(row.get("id") or ""),
        ),
    )
    for lock in ordered_locks:
        staff_id = str(lock.get("staff_id") or "")
        day = iso(lock.get("date"))
        cells = assignments_by_staff_day.get((staff_id, day), [])
        working = [
            (assignment, shift) for assignment, shift in cells
            if shift.get("is_working", True)
        ]
        actual_codes = sorted(_code(shift.get("shift_type")) for _, shift in working)
        lock_type = str(lock.get("lock_type") or "")
        if lock_type == "pin":
            matches = [
                (assignment, shift) for assignment, shift in working
                if cell_conflict(lock, shift_type=shift.get("shift_type"),
                                 is_working=True) is None
            ]
            if len(matches) == 1:
                continue
            findings.append({
                "lock": lock,
                "reason": "pin_missing_or_mismatched" if not matches else "pin_not_exactly_once",
                "actual_shift_types": actual_codes,
                "matching_assignment_ids": sorted(
                    str(assignment.get("id") or "") for assignment, _ in matches
                ),
            })
            continue
        if lock_type == "forbid":
            conflicts = [
                (assignment, shift) for assignment, shift in working
                if cell_conflict(lock, shift_type=shift.get("shift_type"),
                                 is_working=True)
            ]
            if not conflicts:
                continue
            findings.append({
                "lock": lock,
                "reason": "forbid_has_working_assignment",
                "actual_shift_types": actual_codes,
                "conflicting_assignment_ids": sorted(
                    str(assignment.get("id") or "") for assignment, _ in conflicts
                ),
            })
            continue
        findings.append({
            "lock": lock,
            "reason": "unknown_lock_type",
            "actual_shift_types": actual_codes,
        })
    return findings


def live_for_period(client, facility_id: str, start: Date | str,
                    end: Date | str) -> list[dict]:
    """Every live lock in a date range - what a solve has to honour."""
    # SQL: select * from roster_cell_locks
    #      where facility_id = :facility_id and date between :start and :end
    #        and released_at is null
    #      order by date
    return (client.table("roster_cell_locks").select("*")
            .eq("facility_id", facility_id)
            .gte("date", iso(start)).lte("date", iso(end))
            .is_("released_at", "null").order("date").execute().data)
