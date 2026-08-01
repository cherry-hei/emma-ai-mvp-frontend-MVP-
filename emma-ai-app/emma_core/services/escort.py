"""Medical-escort destinations (spec 4.1).

A resident goes to an appointment and a staff member goes with them. The home
records that by writing the destination into the roster cell next to the duty
code - `A7 TMH` is "A shift, escorting to Tuen Mun Hospital" - and the escort
shows on the roster grid and in the staff app.

Cherry settled the design question on ClickUp 4.1, 31 Jul 2026:

    "The location code is per-assignment (attached to a specific staff member's
     shift cell on a specific date), not per-task-definition. The same location
     code can appear on different staff on different days."

So the destination lives on `task_assignments`, and `escort_locations` is only
the dictionary of codes that destination is written in. Putting it on
`task_definitions` instead would have forced one task code per clinic - `FU-TMH`,
`FU-CPH`, `FU-POH` - and made "who is out of the building this afternoon" a
question about task codes rather than about today's roster.

Unknown codes are stored, not rejected. The dictionary is reference data that
lags the roster: a home books an appointment at a clinic nobody has catalogued
and writes it in the cell that morning. Losing that cell on import, or refusing
the edit, would trade real roster data for tidy reference data.
"""
from __future__ import annotations

from ..importers import naac


def list_locations(client, facility_id: str, *, include_inactive: bool = False) -> list[dict]:
    """Facility codes plus the shared template rows (facility_id null)."""
    # SQL: select * from escort_locations
    #      where (facility_id = :facility_id or facility_id is null)
    #        [and active]
    #      order by code
    query = (client.table("escort_locations").select("*")
             .or_(f"facility_id.eq.{facility_id},facility_id.is.null"))
    if not include_inactive:
        query = query.eq("active", True)
    return query.order("code").execute().data


def known_codes(client, facility_id: str) -> set[str]:
    return {str(row["code"]).upper() for row in list_locations(client, facility_id)}


def upsert_location(client, facility_id: str, *, code: str, name_en: str | None = None,
                    name_zh: str | None = None, aliases: list[str] | None = None) -> dict:
    code = (code or "").strip()
    if not code or len(code) > 16:
        raise ValueError("code must be 1-16 characters")
    row = {
        "facility_id": facility_id, "code": code, "name_en": name_en,
        "name_zh": name_zh, "aliases": aliases or [], "active": True,
    }
    # SQL: select id from escort_locations
    #      where facility_id = :facility_id and code = :code
    existing = (client.table("escort_locations").select("id")
                .eq("facility_id", facility_id).eq("code", code).execute().data)
    if existing:
        # SQL: update escort_locations set ... where id = :id returning *
        return (client.table("escort_locations").update(row)
                .eq("id", existing[0]["id"]).execute().data[0])
    # SQL: insert into escort_locations (...) values (...) returning *
    return client.table("escort_locations").insert(row).execute().data[0]


def seed_naac_locations(client, facility_id: str) -> list[dict]:
    """Load the 18 NAAC codes from `naac_escort_locations.csv`.

    Two places share `TMH` and two share `CPH` in the home's own sheet. Both are
    kept: the code is the row, and the places it covers become `aliases`, so a
    cell reading TMH still resolves and nobody has to invent a code the home does
    not write on paper.
    """
    rows = []
    for code, entry in sorted(naac.load_escort_locations().items()):
        rows.append(upsert_location(
            client, facility_id,
            code=code,
            name_en=entry["name_en"],
            name_zh=entry["places"][0] if entry["places"] else None,
            aliases=[p for p in entry["places"] if p],
        ))
    return rows


def set_escort_location(client, facility_id: str, task_assignment_id: str, *,
                        location: str | None) -> dict:
    """Attach (or clear) the destination for one assignment on one date.

    Returns the assignment with `escort_location_unknown` set when the code is not
    in the dictionary. The write still succeeds - the flag is for the UI to badge
    the cell and for a manager to catalogue the clinic afterwards, not a rejection.
    """
    location = (location or "").strip() or None
    if location and len(location) > 32:
        raise ValueError("escort location must be 32 characters or fewer")

    resolved_id = None
    unknown = False
    if location:
        # SQL: select id from escort_locations
        #      where (facility_id = :facility_id or facility_id is null)
        #        and upper(code) = upper(:location) and active
        matches = [
            row for row in list_locations(client, facility_id)
            if str(row["code"]).upper() == location.upper()
        ]
        if matches:
            resolved_id = matches[0]["id"]
        else:
            unknown = True

    # SQL: update task_assignments
    #      set escort_location = :location, escort_location_id = :resolved_id
    #      where facility_id = :facility_id and id = :task_assignment_id
    #      returning *
    rows = (client.table("task_assignments").update({
        "escort_location": location,
        "escort_location_id": resolved_id,
    }).eq("facility_id", facility_id).eq("id", task_assignment_id).execute().data)
    if not rows:
        raise ValueError("task assignment not found")
    return {**rows[0], "escort_location_unknown": unknown}


def escorts_on_date(client, facility_id: str, on_date) -> list[dict]:
    """Every escort leaving the building on one day.

    The operational question this answers is "who is off the floor this
    afternoon" - an escort is a staff member who is rostered and present in the
    hours count but not on the unit, which is exactly the case a floor-minimum
    check gets wrong if it only reads the roster grid.
    """
    # SQL: select ta.*, sa.shift_id, s.date, s.shift_type, st.full_name, st.rank
    #      from task_assignments ta
    #      join shift_assignments sa on sa.id = ta.shift_assignment_id
    #      join shifts s on s.id = sa.shift_id
    #      left join staff st on st.id = ta.staff_id
    #      where ta.facility_id = :facility_id
    #        and ta.escort_location is not null
    #        and s.date = :on_date
    rows = (client.table("task_assignments")
            .select("*, shift_assignments!inner(shift_id, shifts!inner(date, shift_type))")
            .eq("facility_id", facility_id)
            .not_.is_("escort_location", "null").execute().data)
    target = str(on_date)[:10]
    out = []
    for row in rows:
        shift = ((row.get("shift_assignments") or {}).get("shifts") or {})
        if str(shift.get("date"))[:10] != target:
            continue
        out.append({
            "task_assignment_id": row["id"],
            "staff_id": row.get("staff_id"),
            "task_label": row.get("task_label"),
            "escort_location": row.get("escort_location"),
            "escort_location_id": row.get("escort_location_id"),
            "scheduled_time": (row.get("scheduled_time") or "")[:5] or None,
            "shift_type": shift.get("shift_type"),
            "date": target,
        })
    out.sort(key=lambda r: (r["scheduled_time"] or "99:99", r["escort_location"] or ""))
    return out
