"""Task-code assignments and their completion state (spec 3.10).

`shift_assignments.tasks` stays the planner-facing source of truth - it is what
the roster editor writes. `task_assignments` is the execution record the staff
app ticks off, materialised from that array on first read so the two can never
drift out of sync: labels added in the roster appear, labels removed disappear,
and completion state survives.
"""
from __future__ import annotations

from datetime import date as Date

from ._common import assignments_for_shifts, now_iso, to_min

# Task labels the facility considers time-critical; drives the staff app's HIGH tag.
HIGH_PRIORITY_HINTS = ("med", "medication", "wound", "vital", "aom", "icp")


def _priority(label: str) -> str:
    low = label.lower()
    return "high" if any(h in low for h in HIGH_PRIORITY_HINTS) else "normal"


def sync_assignment_tasks(client, facility_id: str, assignment: dict,
                          shift: dict, task_defs: dict[str, dict] | None = None) -> list[dict]:
    """Reconcile task_assignments for one shift assignment against its `tasks` array."""
    labels = list(assignment.get("tasks") or [])
    # SQL: select * from task_assignments
    #      where facility_id = :facility_id
    #        and shift_assignment_id = :assignment_id
    existing = (client.table("task_assignments").select("*")
                .eq("facility_id", facility_id)
                .eq("shift_assignment_id", assignment["id"]).execute().data)
    by_label = {r["task_label"]: r for r in existing}

    stale = [r["id"] for label, r in by_label.items() if label not in labels]
    if stale:
        # SQL: delete from task_assignments where id = any(:stale_ids)
        client.table("task_assignments").delete().in_("id", stale).execute()

    start = to_min(shift.get("start_time"))
    new_rows = []
    for i, label in enumerate(labels):
        if label in by_label:
            continue
        at = None
        if start is not None:                      # spread tasks across the shift
            minute = (start + i * 120) % 1440
            at = f"{minute // 60:02d}:{minute % 60:02d}:00"
        defn = (task_defs or {}).get(label)
        new_rows.append({
            "facility_id": facility_id, "shift_assignment_id": assignment["id"],
            "roster_version_id": shift.get("roster_version_id"),
            "staff_id": assignment.get("staff_id"),
            "task_id": defn["id"] if defn else None,
            "task_label": label, "scheduled_time": at,
            "start_at": f"{str(shift.get('date'))[:10]}T{at}" if at else None,
            "source_type": "legacy_cell",
            "priority": _priority(label), "task_status": "pending",
        })
    if new_rows:
        # SQL: insert into task_assignments
        #        (facility_id, shift_assignment_id, staff_id, task_id, task_label,
        #         scheduled_time, priority, task_status)
        #      values (...), (...), ...      -- one tuple per missing label
        #      returning *
        client.table("task_assignments").insert(new_rows).execute()

    # SQL: select * from task_assignments
    #      where facility_id = :facility_id
    #        and shift_assignment_id = :assignment_id
    #      order by scheduled_time
    return (client.table("task_assignments").select("*")
            .eq("facility_id", facility_id)
            .eq("shift_assignment_id", assignment["id"])
            .order("scheduled_time").execute().data)


def task_definitions_by_label(client, facility_id: str) -> dict[str, dict]:
    # SQL: select * from task_definitions
    #      where (facility_id = :facility_id or facility_id is null)   -- null = global default
    #        and active = true
    rows = (client.table("task_definitions").select("*")
            .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
            .eq("active", True).execute().data)
    out: dict[str, dict] = {}
    for r in rows:
        for key in (r.get("task_name"), r.get("task_code")):
            if key:
                out.setdefault(key, r)
    return out


def set_status(client, facility_id: str, task_assignment_id: str, *, status: str,
               staff_id: str | None = None) -> dict:
    if status not in ("pending", "done", "skipped", "exception"):
        raise ValueError("status must be pending, done, skipped or exception")
    if status == "exception":
        # An exception is the *outcome* of report_exception, which also writes the
        # reason. Letting it be set here would create an unexplained exception -
        # exactly the state the reason codes exist to prevent.
        raise ValueError("report an exception via report_exception, not set_status")
    done = status == "done"
    # SQL: update task_assignments
    #      set task_status  = :status,
    #          completed_at = case when :done then now() end,
    #          completed_by = case when :done then :staff_id end
    #      where facility_id = :facility_id and id = :task_assignment_id
    #      returning *
    rows = (client.table("task_assignments").update({
        "task_status": status,
        "completed_at": now_iso() if done else None,
        "completed_by": staff_id if done else None,
    }).eq("facility_id", facility_id).eq("id", task_assignment_id).execute().data)
    if not rows:
        raise ValueError("task assignment not found")
    return rows[0]


# The closed list the staff app offers. Mirrors the check constraint on
# task_exceptions.reason_code; `test_mvp_staff_app.py` asserts the two agree,
# because a code the UI can send and the database rejects is a 500 on a nurse's
# phone at 3am.
EXCEPTION_REASONS = (
    "resident_refused",
    "resident_absent",
    "clinical_hold",
    "equipment_unavailable",
    "insufficient_time",
    "staff_reassigned",
    "other",
)


def report_exception(client, facility_id: str, task_assignment_id: str, *,
                     reason_code: str, note: str | None = None,
                     staff_id: str | None = None) -> dict:
    """Record why a task could not be done, and flag the assignment (spec SA.3).

    The exception row is written first. If the status update then fails, the
    facility is left with a logged reason on a task that still reads 'pending' -
    visibly incomplete. The reverse order would leave a task marked 'exception'
    with nothing saying why, which reads as complete-and-explained to anyone
    scanning the dashboard.
    """
    if reason_code not in EXCEPTION_REASONS:
        raise ValueError(
            f"reason_code must be one of {', '.join(EXCEPTION_REASONS)}")
    if reason_code == "other" and not (note or "").strip():
        raise ValueError("a note is required when reason_code is 'other'")

    # SQL: select id, task_status from task_assignments
    #      where facility_id = :facility_id and id = :task_assignment_id
    rows = (client.table("task_assignments").select("id,task_status")
            .eq("facility_id", facility_id)
            .eq("id", task_assignment_id).execute().data)
    if not rows:
        raise ValueError("task assignment not found")

    # SQL: insert into task_exceptions
    #        (facility_id, task_assignment_id, reported_by, reason_code, note)
    #      values (...) returning *
    exception_row = client.table("task_exceptions").insert({
        "facility_id": facility_id,
        "task_assignment_id": task_assignment_id,
        "reported_by": staff_id,
        "reason_code": reason_code,
        "note": (note or "").strip() or None,
    }).execute().data[0]

    # SQL: update task_assignments set task_status = 'exception'
    #      where facility_id = :facility_id and id = :task_assignment_id
    #      returning *
    assignment = (client.table("task_assignments")
                  .update({"task_status": "exception"})
                  .eq("facility_id", facility_id)
                  .eq("id", task_assignment_id).execute().data[0])
    return {"task_assignment": assignment, "exception": exception_row}


def exceptions_for(client, facility_id: str, *, task_assignment_id: str | None = None,
                   limit: int = 100) -> list[dict]:
    """Newest first. Drives the manager dashboard's exception feed."""
    # SQL: select * from task_exceptions
    #      where facility_id = :facility_id
    #        [and task_assignment_id = :task_assignment_id]
    #      order by reported_at desc
    #      limit :limit
    query = (client.table("task_exceptions").select("*")
             .eq("facility_id", facility_id))
    if task_assignment_id:
        query = query.eq("task_assignment_id", task_assignment_id)
    return query.order("reported_at", desc=True).limit(limit).execute().data


def for_staff_date(client, facility_id: str, staff_id: str, on: Date) -> list[dict]:
    """Materialised tasks for one staff member on one day, newest roster wins."""
    from ._common import operative_version, resolve_period

    period = resolve_period(client, facility_id, None)
    if not period:
        return []
    version = operative_version(client, facility_id, period["id"])
    if not version:
        return []
    # SQL: select * from shifts
    #      where roster_version_id = :version_id and date = :on
    shifts = (client.table("shifts").select("*")
              .eq("roster_version_id", version["id"]).eq("date", str(on)).execute().data)
    if not shifts:
        return []
    by_id = {s["id"]: s for s in shifts}
    # SQL: select * from shift_assignments
    #      where shift_id = any(:shift_ids) and staff_id = :staff_id
    assigns = assignments_for_shifts(client, by_id, staff_id=staff_id)

    defs = task_definitions_by_label(client, facility_id)
    out: list[dict] = []
    for a in assigns:
        if a.get("status") == "cancelled":
            continue
        shift = by_id[a["shift_id"]]
        for row in sync_assignment_tasks(client, facility_id, a, shift, defs):
            out.append({
                "id": row["id"], "task_label": row["task_label"],
                "scheduled_time": (row.get("scheduled_time") or "")[:5] or None,
                "priority": row["priority"], "status": row["task_status"],
                "completed_at": row.get("completed_at"),
                "shift_type": shift["shift_type"],
            })
    out.sort(key=lambda t: (t["scheduled_time"] or "99:99"))
    return out
