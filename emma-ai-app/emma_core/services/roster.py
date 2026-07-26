"""Roster read/write: pivots the shift/assignment model into the staff × day grid, plus manual CRUD and publish."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..constants import AssignmentStatus, OverrideAction, PublishEvent, RosterStatus
from ..models import RosterCell, RosterGrid, RosterRow, ShiftDef, StaffLite


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _delete_shift_if_empty(client, shift_id: str) -> None:
    """Drop the shift only when no assignments remain. shift_id is ON DELETE CASCADE,
    so deleting a shift shared by sibling assignments (required_count > 1) would wipe
    their cells."""
    remaining = (client.table("shift_assignments").select("id")
                 .eq("shift_id", shift_id).limit(1).execute().data)
    if not remaining:
        client.table("shifts").delete().eq("id", shift_id).execute()


def _latest_version(client, facility_id: str, period_id: str | None = None,
                    version_type: str | None = "manual", version_id: str | None = None):
    """Newest roster version for a facility/period. Defaults to ``manual`` so generated
    A/B/C options don't hijack the main view; pass ``version_type=None`` for any, or an
    explicit ``version_id`` for a specific option."""
    if version_id:
        rows = client.table("roster_versions").select("*").eq("id", version_id).execute().data
        return rows[0] if rows else None
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

    period = None
    if ver.get("period_id"):
        p = client.table("roster_periods").select("*").eq("id", ver["period_id"]).execute().data
        period = p[0] if p else None

    shifts = client.table("shifts").select("*").eq("roster_version_id", ver["id"]).execute().data
    shift_by_id = {s["id"]: s for s in shifts}
    shift_ids = list(shift_by_id)

    assigns = []
    if shift_ids:
        assigns = (client.table("shift_assignments").select("*")
                   .in_("shift_id", shift_ids).execute().data)

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

    return RosterGrid(
        version_id=ver["id"], period_id=ver.get("period_id"), status=ver["status"],
        period_start=(period or {}).get("period_start"),
        period_end=(period or {}).get("period_end"),
        dates=dates, rows=rows,
    )


def get_shift_defs(client, facility_id: str) -> list[ShiftDef]:
    rows = (client.table("shift_definitions").select("*")
            .eq("facility_id", facility_id).order("is_working", desc=True)
            .execute().data)
    return [ShiftDef.model_validate(r) for r in rows]


def list_task_definitions(client, facility_id: str) -> list[dict]:
    """Facility-scoped task-code dictionary; template rows (facility_id null) are shared."""
    return (client.table("task_definitions").select("*")
            .or_(f"facility_id.eq.{facility_id},facility_id.is.null")
            .eq("active", True).order("task_code").execute().data)


# ── periods / versions ──────────────────────────────────────────────────────
def list_periods(client, facility_id: str) -> list[dict]:
    return (client.table("roster_periods").select("*")
            .eq("facility_id", facility_id).order("period_start", desc=True)
            .execute().data)


def create_period(client, *, facility_id, period_start, period_end, cycle_type="28day",
                  created_by=None, create_manual_version=True):
    """Create a roster period and, by default, a blank 'manual' version to hang shifts
    on (the grid, manual edit and solver all need one and nothing else bootstraps it)."""
    period = (client.table("roster_periods").insert({
        "facility_id": facility_id, "period_start": str(period_start),
        "period_end": str(period_end), "cycle_type": cycle_type, "status": "planning",
    }).execute().data[0])
    version = None
    if create_manual_version:
        version = (client.table("roster_versions").insert({
            "facility_id": facility_id, "period_id": period["id"],
            "version_type": "manual", "label": "Manual roster",
            "status": RosterStatus.DRAFT, "created_by": created_by,
        }).execute().data[0])
    return period, version


def list_versions(client, facility_id: str, period_id: str | None = None) -> list[dict]:
    q = client.table("roster_versions").select("*").eq("facility_id", facility_id)
    if period_id:
        q = q.eq("period_id", period_id)
    return q.order("created_at", desc=True).execute().data


# ── manual edit (CRUD) ──────────────────────────────────────────────────────
def set_cell(client, *, facility_id, roster_version_id, staff_id, date, shift_type,
             shift_def: ShiftDef, tasks=None, changed_by=None):
    """Upsert one staff/day cell (create/replace shift + assignment) and log to manual_override_log."""
    tasks = tasks or []
    existing_shifts = (client.table("shifts").select("id")
                       .eq("roster_version_id", roster_version_id).eq("date", str(date))
                       .execute().data)
    existing_shift_ids = [s["id"] for s in existing_shifts]
    old = None
    if existing_shift_ids:
        found = (client.table("shift_assignments").select("*")
                 .in_("shift_id", existing_shift_ids).eq("staff_id", staff_id)
                 .execute().data)
        old = found[0] if found else None
        for a in found:  # clear any prior cell for this staff/day
            client.table("shift_assignments").delete().eq("id", a["id"]).execute()
            _delete_shift_if_empty(client, a["shift_id"])

    shift_id = (client.table("shifts").insert({
        "facility_id": facility_id, "roster_version_id": roster_version_id,
        "date": str(date), "shift_type": shift_type,
        "start_time": shift_def.start_time, "end_time": shift_def.end_time,
        "cross_midnight": shift_def.cross_midnight,
        "is_working": shift_def.is_working,
    }).execute().data[0]["id"])

    assignment_id = (client.table("shift_assignments").insert({
        "facility_id": facility_id, "shift_id": shift_id, "staff_id": staff_id,
        "status": AssignmentStatus.ASSIGNED, "tasks": tasks,
    }).execute().data[0]["id"])

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
    existing_shifts = (client.table("shifts").select("id")
                       .eq("roster_version_id", roster_version_id).eq("date", str(date))
                       .execute().data)
    ids = [s["id"] for s in existing_shifts]
    if not ids:
        return
    found = (client.table("shift_assignments").select("*")
             .in_("shift_id", ids).eq("staff_id", staff_id).execute().data)
    for a in found:
        client.table("shift_assignments").delete().eq("id", a["id"]).execute()
        _delete_shift_if_empty(client, a["shift_id"])
        client.table("manual_override_log").insert({
            "facility_id": facility_id, "roster_version_id": roster_version_id,
            "action": OverrideAction.DELETE,
            "before_json": json.loads(json.dumps(a, default=str)),
            "changed_by": changed_by,
        }).execute()


# ── publish workflow ────────────────────────────────────────────────────────
def publish_version(client, *, facility_id, roster_version_id, created_by=None):
    (client.table("roster_versions")
     .update({"status": RosterStatus.PUBLISHED, "published_at": _now()})
     .eq("id", roster_version_id).execute())
    client.table("roster_publish_events").insert({
        "facility_id": facility_id, "roster_version_id": roster_version_id,
        "event_type": PublishEvent.PUBLISH, "created_by": created_by,
    }).execute()


def save_draft(client, *, facility_id, roster_version_id, created_by=None):
    client.table("roster_publish_events").insert({
        "facility_id": facility_id, "roster_version_id": roster_version_id,
        "event_type": PublishEvent.SAVE_DRAFT, "created_by": created_by,
    }).execute()
