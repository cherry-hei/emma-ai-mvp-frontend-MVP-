"""Roster read/write: pivots the shift/assignment model into the staff × day grid, plus manual CRUD and publish."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..constants import AssignmentStatus, OverrideAction, PublishEvent, RosterStatus
from ..models import RosterCell, RosterGrid, RosterRow, ShiftDef, StaffLite
from ._common import assignments_for_shifts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _delete_shift_if_empty(client, shift_id: str) -> None:
    """Drop the shift only when no assignments remain. shift_id is ON DELETE CASCADE,
    so deleting a shift shared by sibling assignments (required_count > 1) would wipe
    their cells."""
    # SQL: select id from shift_assignments where shift_id = :shift_id limit 1
    remaining = (client.table("shift_assignments").select("id")
                 .eq("shift_id", shift_id).limit(1).execute().data)
    if not remaining:
        # SQL: delete from shifts where id = :shift_id
        client.table("shifts").delete().eq("id", shift_id).execute()


def _latest_version(client, facility_id: str, period_id: str | None = None,
                    version_type: str | None = "manual", version_id: str | None = None):
    """Newest roster version for a facility/period. Defaults to ``manual`` so generated
    A/B/C options don't hijack the main view; pass ``version_type=None`` for any, or an
    explicit ``version_id`` for a specific option."""
    if version_id:
        # SQL: select * from roster_versions where id = :version_id
        rows = client.table("roster_versions").select("*").eq("id", version_id).execute().data
        return rows[0] if rows else None
    # SQL: select * from roster_versions
    #      where facility_id = :facility_id
    #        [and period_id = :period_id]        -- when period_id is given
    #        [and version_type = :version_type]  -- unless version_type is None
    #      order by created_at desc
    #      limit 1
    q = client.table("roster_versions").select("*").eq("facility_id", facility_id)
    if period_id:
        q = q.eq("period_id", period_id)
    if version_type:
        q = q.eq("version_type", version_type)
    rows = q.order("created_at", desc=True).limit(1).execute().data
    return rows[0] if rows else None


def get_roster_grid(client, facility_id: str, period_id: str | None = None, *,
                    version_type: str | None = "manual", version_id: str | None = None) -> RosterGrid:
    ver = _latest_version(client, facility_id, period_id,
                          version_type=version_type, version_id=version_id)
    if not ver:
        return RosterGrid()

    # The grid is assembled from four flat reads and pivoted in Python below; there is
    # no single query that returns the staff × day shape the UI wants.
    period = None
    if ver.get("period_id"):
        # SQL: select * from roster_periods where id = :period_id
        p = client.table("roster_periods").select("*").eq("id", ver["period_id"]).execute().data
        period = p[0] if p else None

    # SQL: select * from shifts where roster_version_id = :version_id
    shifts = client.table("shifts").select("*").eq("roster_version_id", ver["id"]).execute().data
    shift_by_id = {s["id"]: s for s in shifts}
    shift_ids = list(shift_by_id)

    assigns = []
    if shift_ids:
        assigns = assignments_for_shifts(client, shift_ids)

    # SQL: select s.*, jsonb_build_object('name', u.name) as unit
    #      from staff s
    #      left join facility_units u on u.id = s.primary_unit_id
    #      where s.facility_id = :facility_id
    #      order by s.created_at
    staff_rows = (client.table("staff").select("*, unit:facility_units(name)")
                  .eq("facility_id", facility_id).order("created_at").execute().data)

    dates = sorted({s["date"] for s in shifts})
    cell_by: dict[tuple[str, str], tuple[dict, dict]] = {}
    for a in assigns:
        sh = shift_by_id.get(a["shift_id"])
        if sh and a.get("staff_id"):
            cell_by[(a["staff_id"], sh["date"])] = (sh, a)

    rows: list[RosterRow] = []
    for st in staff_rows:
        unit = st.get("unit") or {}
        cells: list[RosterCell] = []
        for d in dates:
            pair = cell_by.get((st["id"], d))
            if pair:
                sh, a = pair
                cells.append(RosterCell(
                    date=d, shift_type=sh["shift_type"], is_working=sh["is_working"],
                    tasks=a.get("tasks") or [], assignment_id=a["id"], shift_id=sh["id"],
                ))
            else:
                cells.append(RosterCell(date=d))
        rows.append(RosterRow(
            staff=StaffLite(
                id=st["id"], name=st["name"], name_en=st.get("name_en"),
                rank=st["rank"], employment_type=st["employment_type"],
                unit_name=unit.get("name"),
            ),
            cells=cells,
        ))

    from .scheduling import list_facility_events

    event_start = (period or {}).get("period_start") or (dates[0] if dates else None)
    event_end = (period or {}).get("period_end") or (dates[-1] if dates else None)
    events = list_facility_events(
        client, facility_id, date_from=event_start, date_to=event_end,
    ) if event_start and event_end else []

    return RosterGrid(
        version_id=ver["id"], period_id=ver.get("period_id"), status=ver["status"],
        period_start=(period or {}).get("period_start"),
        period_end=(period or {}).get("period_end"),
        dates=dates, rows=rows, events=events,
    )


def get_shift_defs(client, facility_id: str) -> list[ShiftDef]:
    # SQL: select * from shift_definitions
    #      where facility_id = :facility_id
    #      order by is_working desc      -- working codes first, OFF/leave last
    rows = (client.table("shift_definitions").select("*")
            .eq("facility_id", facility_id).order("is_working", desc=True)
            .execute().data)
    return [ShiftDef.model_validate(r) for r in rows]


def list_task_definitions(client, facility_id: str) -> list[dict]:
    """Facility-scoped task-code dictionary; template rows (facility_id null) are shared."""
    # SQL: select * from task_definitions
    #      where (facility_id = :facility_id or facility_id is null)   -- null = template
    #        and active = true
    #      order by task_code
    return (client.table("task_definitions").select("*")
            .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
            .eq("active", True).order("task_code").execute().data)


# ── periods / versions ──────────────────────────────────────────────────────
def list_periods(client, facility_id: str) -> list[dict]:
    # SQL: select * from roster_periods
    #      where facility_id = :facility_id
    #      order by period_start desc
    return (client.table("roster_periods").select("*")
            .eq("facility_id", facility_id).order("period_start", desc=True)
            .execute().data)


def create_period(client, *, facility_id, period_start, period_end, cycle_type="28day",
                  created_by=None, create_manual_version=True):
    """Create a roster period and, by default, a blank 'manual' version to hang shifts
    on (the grid, manual edit and solver all need one and nothing else bootstraps it)."""
    # SQL: insert into roster_periods
    #        (facility_id, period_start, period_end, cycle_type, status)
    #      values (:facility_id, :period_start, :period_end, :cycle_type, 'planning')
    #      returning *
    period = (client.table("roster_periods").insert({
        "facility_id": facility_id, "period_start": str(period_start),
        "period_end": str(period_end), "cycle_type": cycle_type, "status": "planning",
    }).execute().data[0])
    version = None
    if create_manual_version:
        # SQL: insert into roster_versions
        #        (facility_id, period_id, version_type, label, status, created_by)
        #      values (:facility_id, :period_id, 'manual', 'Manual roster',
        #              'draft', :created_by)
        #      returning *
        version = (client.table("roster_versions").insert({
            "facility_id": facility_id, "period_id": period["id"],
            "version_type": "manual", "label": "Manual roster",
            "status": RosterStatus.DRAFT, "created_by": created_by,
        }).execute().data[0])
    return period, version


def list_versions(client, facility_id: str, period_id: str | None = None) -> list[dict]:
    # SQL: select * from roster_versions
    #      where facility_id = :facility_id
    #        [and period_id = :period_id]   -- when period_id is given
    #      order by created_at desc
    q = client.table("roster_versions").select("*").eq("facility_id", facility_id)
    if period_id:
        q = q.eq("period_id", period_id)
    return q.order("created_at", desc=True).execute().data


# ── manual edit (CRUD) ──────────────────────────────────────────────────────
def set_cell(client, *, facility_id, roster_version_id, staff_id, date, shift_type,
             shift_def: ShiftDef, tasks=None, changed_by=None):
    """Upsert one staff/day cell (create/replace shift + assignment) and log to manual_override_log."""
    tasks = tasks or []
    staff_rows = (client.table("staff").select("id,rank,primary_unit_id")
                  .eq("facility_id", facility_id).eq("id", staff_id)
                  .execute().data)
    if not staff_rows:
        raise ValueError("staff member not found")
    staff = staff_rows[0]
    # SQL: select id from shifts
    #      where roster_version_id = :roster_version_id and date = :date
    existing_shifts = (client.table("shifts").select("id")
                       .eq("roster_version_id", roster_version_id).eq("date", str(date))
                       .execute().data)
    existing_shift_ids = [s["id"] for s in existing_shifts]
    old = None
    if existing_shift_ids:
        # SQL: select * from shift_assignments
        #      where shift_id = any(:existing_shift_ids) and staff_id = :staff_id
        found = assignments_for_shifts(client, existing_shift_ids,
                                       staff_id=staff_id)
        old = found[0] if found else None
        for a in found:  # clear any prior cell for this staff/day
            # SQL: delete from shift_assignments where id = :assignment_id
            # (one statement per row rather than `id = any(...)`, because each
            #  deletion is followed by the empty-shift check below)
            client.table("shift_assignments").delete().eq("id", a["id"]).execute()
            _delete_shift_if_empty(client, a["shift_id"])

    # SQL: insert into shifts
    #        (facility_id, roster_version_id, date, shift_type, start_time, end_time,
    #         cross_midnight, is_working, segments, paid_minutes)
    #      values (:facility_id, :roster_version_id, :date, :shift_type,
    #              :start_time, :end_time, :cross_midnight, :is_working,
    #              :segments::jsonb, :paid_minutes)
    #      returning id
    shift_id = (client.table("shifts").insert({
        "facility_id": facility_id, "roster_version_id": roster_version_id,
        "date": str(date), "shift_type": shift_type,
        "start_time": shift_def.start_time, "end_time": shift_def.end_time,
        "cross_midnight": shift_def.cross_midnight,
        "is_working": shift_def.is_working,
        "unit_id": staff.get("primary_unit_id"),
        "required_rank": staff.get("rank"),
        # a manually placed A/N cell must keep its split-shift shape
        "segments": shift_def.segments, "paid_minutes": shift_def.paid_minutes,
    }).execute().data[0]["id"])

    # SQL: insert into shift_assignments (facility_id, shift_id, staff_id, status, tasks)
    #      values (:facility_id, :shift_id, :staff_id, 'assigned', :tasks)
    #      returning id
    assignment_id = (client.table("shift_assignments").insert({
        "facility_id": facility_id, "shift_id": shift_id, "staff_id": staff_id,
        "role": staff.get("rank"),
        "status": AssignmentStatus.ASSIGNED, "tasks": tasks,
    }).execute().data[0]["id"])

    # SQL: insert into manual_override_log
    #        (facility_id, roster_version_id, shift_assignment_id, action,
    #         before_json, after_json, changed_by)
    #      values (:facility_id, :roster_version_id, :assignment_id,
    #              case when :old is not null then 'update' else 'create' end,
    #              :before_json::jsonb, :after_json::jsonb, :changed_by)
    #      returning *
    client.table("manual_override_log").insert({
        "facility_id": facility_id, "roster_version_id": roster_version_id,
        "shift_assignment_id": assignment_id,
        "action": OverrideAction.UPDATE if old else OverrideAction.CREATE,
        "before_json": json.loads(json.dumps(old, default=str)) if old else None,
        "after_json": {"shift_type": shift_type, "tasks": tasks},
        "changed_by": changed_by,
    }).execute()
    return assignment_id


def clear_cell(client, *, facility_id, roster_version_id, staff_id, date, changed_by=None):
    # SQL: select id from shifts
    #      where roster_version_id = :roster_version_id and date = :date
    existing_shifts = (client.table("shifts").select("id")
                       .eq("roster_version_id", roster_version_id).eq("date", str(date))
                       .execute().data)
    ids = [s["id"] for s in existing_shifts]
    if not ids:
        return
    # SQL: select * from shift_assignments
    #      where shift_id = any(:shift_ids) and staff_id = :staff_id
    found = assignments_for_shifts(client, ids, staff_id=staff_id)
    for a in found:
        # SQL: delete from shift_assignments where id = :assignment_id
        client.table("shift_assignments").delete().eq("id", a["id"]).execute()
        _delete_shift_if_empty(client, a["shift_id"])
        # SQL: insert into manual_override_log
        #        (facility_id, roster_version_id, action, before_json, changed_by)
        #      values (:facility_id, :roster_version_id, 'delete',
        #              :before_json::jsonb, :changed_by)
        #      returning *
        client.table("manual_override_log").insert({
            "facility_id": facility_id, "roster_version_id": roster_version_id,
            "action": OverrideAction.DELETE,
            "before_json": json.loads(json.dumps(a, default=str)),
            "changed_by": changed_by,
        }).execute()


# ── publish workflow ────────────────────────────────────────────────────────
def publish_version(client, *, facility_id, roster_version_id, created_by=None):
    """Make one validated version operative for its period.

    Production clients use the database function so archiving the old
    operative version, publishing the target and writing its audit event are
    one transaction. The small fallback keeps in-memory/offline adapters useful
    while preserving the same single-operative semantics.
    """
    rpc = getattr(client, "rpc", None)
    if callable(rpc):
        result = rpc(
            "publish_roster_version",
            {
                "p_facility_id": facility_id,
                "p_roster_version_id": roster_version_id,
                "p_created_by": created_by,
            },
        ).execute()
        rows = result.data or []
        if isinstance(rows, dict):
            return rows
        if not rows:
            raise ValueError("roster version not found")
        return rows[0]

    # Offline adapter fallback. The production RPC above is atomic; here the
    # explicit facility/period predicates still prevent cross-tenant updates.
    target_rows = (
        client.table("roster_versions")
        .select("*")
        .eq("id", roster_version_id)
        .eq("facility_id", facility_id)
        .limit(1)
        .execute()
        .data
    )
    if not target_rows:
        raise ValueError("roster version not found")
    target = target_rows[0]
    period_id = target.get("period_id")
    if not period_id:
        raise ValueError("a roster period is required for publication")
    prior = (
        client.table("roster_versions")
        .update({"status": RosterStatus.ARCHIVED})
        .eq("facility_id", facility_id)
        .eq("period_id", period_id)
        .eq("status", RosterStatus.PUBLISHED)
        .execute()
        .data
    )
    _ = prior  # returned rows are useful to richer adapters, but not required here
    published_at = _now()
    updated = (
        client.table("roster_versions")
        .update({
            "status": RosterStatus.PUBLISHED,
            "published_at": published_at,
        })
        .eq("id", roster_version_id)
        .eq("facility_id", facility_id)
        .eq("period_id", period_id)
        .execute()
        .data
    )
    if not updated:
        raise ValueError("roster version not found")
    # SQL: insert into roster_publish_events
    #        (facility_id, roster_version_id, event_type, created_by)
    #      values (:facility_id, :roster_version_id, 'publish', :created_by)
    #      returning *
    client.table("roster_publish_events").insert({
        "facility_id": facility_id, "roster_version_id": roster_version_id,
        "event_type": PublishEvent.PUBLISH, "created_by": created_by,
    }).execute()
    return updated[0]


def save_draft(client, *, facility_id, roster_version_id, created_by=None):
    # SQL: insert into roster_publish_events
    #        (facility_id, roster_version_id, event_type, created_by)
    #      values (:facility_id, :roster_version_id, 'save_draft', :created_by)
    #      returning *
    client.table("roster_publish_events").insert({
        "facility_id": facility_id, "roster_version_id": roster_version_id,
        "event_type": PublishEvent.SAVE_DRAFT, "created_by": created_by,
    }).execute()
