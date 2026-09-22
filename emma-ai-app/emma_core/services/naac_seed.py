"""Provision the NAAC facility from its own config files (spec 2.2 / 2.3 / 4.1).

One entry point, `provision`, because the four things it writes only make sense
together: a shift dictionary whose codes no task references, or escort tasks with
no destinations to choose from, is a half-configured home that fails at the first
roster edit rather than at setup.

Idempotent by design. It is run once to set the home up and again every time
Cherry sends a corrected sheet, so every step is an upsert and nothing is deleted
- a home that has hand-corrected a duty window keeps the correction unless the
caller passes `overwrite`.

What this deliberately does not load
------------------------------------
The per-person `#` quotas (15/13/9 against the nurses' 12) and the two personal
scheduling constraints. Those are employee data; they belong in the database
seeded from the home's own DO更次數 sheet, not in a file in this repository. See
`docs/naac/README.md`.
"""
from __future__ import annotations

from ..importers import naac
from . import escort, facility_config
from .organisations import org_id_for

FACILITY_CODE = "NAAC"


def _facility_id(client, facility_code: str = FACILITY_CODE) -> str:
    # SQL: select id from facilities where code = :facility_code
    rows = (client.table("facilities").select("id")
            .eq("code", facility_code).execute().data)
    if not rows:
        raise ValueError(
            f"facility {facility_code!r} does not exist; create it before seeding")
    return rows[0]["id"]


def seed_shift_definitions(client, facility_id: str, *,
                           overwrite: bool = False) -> list[dict]:
    """The 277 duty codes, from the home's own 代號及時數 sheet.

    Hours come from the sheet's 時數 column rather than from the clock times,
    because they are not always the same number - a duty with an unpaid meal
    break is on the floor longer than it is paid for, and payroll follows the
    column. That is why `paid_minutes_override` is set on every row.
    """
    # SQL: select shift_type from shift_definitions where org_id = :org_id
    existing = {
        row["shift_type"] for row in
        client.table("shift_definitions").select("shift_type")
        .eq("org_id", org_id_for(client, facility_id)).execute().data
    }
    written = []
    for spec in naac.load_shift_codes().values():
        if spec.code in existing and not overwrite:
            continue
        segments = [{"start": s, "end": e} for s, e in spec.windows]
        written.append(facility_config.upsert_shift_definition(
            client, facility_id,
            shift_type=spec.code,
            label=spec.category_zh or spec.code,
            start_time=segments[0]["start"] if segments else None,
            end_time=segments[-1]["end"] if segments else None,
            segments=segments if len(segments) > 1 else None,
            is_working=spec.is_working,
            paid_minutes_override=spec.paid_minutes,
            source_note="NAAC更期代號註解.xlsx / 代號及時數 (ClickUp 2.2, 31 Jul 2026)",
        ))
    return written


def seed_task_definitions(client, facility_id: str, *,
                          overwrite: bool = False) -> list[dict]:
    """The task markers the home writes into a roster cell next to the duty code.

    `needs_location` is carried through so validation can ask the definition
    whether an escort destination is required, instead of matching against a
    hardcoded list of codes that a home cannot extend.
    """
    org_id = org_id_for(client, facility_id)
    # Matched by hand rather than by `on conflict`. The only unique index here is
    # over (facility_id, task_code, required_rank) and it is partial, which
    # Postgres will not accept as a conflict target; these codes also carry no
    # rank, and a null rank makes every row unique again, so a blind insert
    # quietly builds a second copy of the whole dictionary on the second run.
    #
    # SQL: select id, task_code from task_definitions where org_id = :org_id
    existing = {
        row["task_code"]: row["id"] for row in
        client.table("task_definitions").select("id,task_code")
        .eq("org_id", org_id).execute().data
    }
    written: list[dict] = []
    new_rows: list[dict] = []
    for spec in naac.load_task_codes().values():
        row = {
            "facility_id": facility_id,
            "task_code": spec.code,
            "task_name": spec.name_en or spec.code,
            "task_name_zh": spec.name_zh or None,
            "task_category": spec.category or None,
            "needs_location": spec.needs_location,
            # The medication markers are the ones a home audits people for.
            "requires_audit": spec.category == "medication",
            "active": True,
        }
        if spec.code not in existing:
            new_rows.append(row)
        elif overwrite:
            # The code belongs to the charity and a sister home may have created
            # it, so a corrected sheet updates the entry without claiming it.
            row.pop("facility_id")
            # SQL: update task_definitions set ... where id = :id returning *
            written.extend(client.table("task_definitions").update(row)
                           .eq("id", existing[spec.code]).execute().data)
    if new_rows:
        # SQL: insert into task_definitions (...) values (...), ... returning *
        written.extend(client.table("task_definitions")
                       .insert(new_rows).execute().data)
    return written


def provision(client, *, facility_code: str = FACILITY_CODE,
              created_by: str | None = None, overwrite: bool = False) -> dict:
    """Set the home up end to end. Returns a count per step."""
    facility_id = _facility_id(client, facility_code)
    configs = facility_config.seed_naac_configs(
        client, facility_id, created_by=created_by, overwrite=overwrite)
    shifts = seed_shift_definitions(client, facility_id, overwrite=overwrite)
    tasks = seed_task_definitions(client, facility_id, overwrite=overwrite)
    locations = escort.seed_naac_locations(client, facility_id)
    return {
        "facility_id": facility_id,
        "facility_code": facility_code,
        "configs": len(configs),
        "shift_definitions": len(shifts),
        "task_definitions": len(tasks),
        "escort_locations": len(locations),
    }
