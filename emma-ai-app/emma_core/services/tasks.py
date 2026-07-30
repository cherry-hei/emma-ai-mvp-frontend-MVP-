"""Task-code assignments and their completion state (spec 3.10).

`shift_assignments.tasks` stays the planner-facing source of truth - it is what
the roster editor writes. `task_assignments` is the execution record the staff
app ticks off, materialised from that array on first read so the two can never
drift out of sync: labels added in the roster appear, labels removed disappear,
and completion state survives.
"""
from __future__ import annotations

from datetime import date as Date

from ._common import now_iso, to_min

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
    if status not in ("pending", "done", "skipped"):
        raise ValueError("status must be pending, done or skipped")
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
    assigns = (client.table("shift_assignments").select("*")
               .in_("shift_id", list(by_id)).eq("staff_id", staff_id).execute().data)

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
