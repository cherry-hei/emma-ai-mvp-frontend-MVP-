"""Facility units + daily resident-count input (denominator for ratios)."""
from __future__ import annotations

from ..models import Unit


def get_units(client, facility_id: str) -> list[Unit]:
    # SQL: select id, name from facility_units
    #      where facility_id = :facility_id
    #      order by name
    rows = (client.table("facility_units").select("id,name")
            .eq("facility_id", facility_id).order("name").execute().data)
    return [Unit.model_validate(r) for r in rows]


def get_resident_counts(client, facility_id: str, *, on_date=None) -> list[dict]:
    """Stored daily resident counts; filter to one day with ``on_date``, else all rows."""
    # SQL: select * from daily_resident_counts
    #      where facility_id = :facility_id
    #        [and date = :on_date]          -- only when on_date is given
    #      order by date
    q = (client.table("daily_resident_counts").select("*")
         .eq("facility_id", facility_id))
    if on_date is not None:
        q = q.eq("date", str(on_date))
    return q.order("date").execute().data


def set_resident_count(client, *, facility_id, date, unit_id, care_level, count,
                       entered_by=None) -> None:
    """Upsert the resident count for (facility, date, unit, care_level).

    Read-then-write rather than a single statement: there is no unique constraint on
    (facility_id, date, unit_id, care_level), so ``insert ... on conflict`` has no
    arbiter to target.
    """
    # SQL: select id from daily_resident_counts
    #      where facility_id = :facility_id and date = :date
    #        and unit_id = :unit_id and care_level = :care_level
    existing = (client.table("daily_resident_counts").select("id")
                .eq("facility_id", facility_id).eq("date", str(date))
                .eq("unit_id", unit_id).eq("care_level", care_level)
                .execute().data)
    if existing:
        # SQL: update daily_resident_counts
        #      set resident_count = :count, entered_by = :entered_by
        #      where id = :existing_id
        #      returning *
        (client.table("daily_resident_counts")
         .update({"resident_count": count, "entered_by": entered_by})
         .eq("id", existing[0]["id"]).execute())
    else:
        # SQL: insert into daily_resident_counts
        #        (facility_id, date, unit_id, care_level, resident_count, entered_by)
        #      values (:facility_id, :date, :unit_id, :care_level, :count, :entered_by)
        #      returning *
        (client.table("daily_resident_counts").insert({
            "facility_id": facility_id, "date": str(date), "unit_id": unit_id,
            "care_level": care_level, "resident_count": count, "entered_by": entered_by,
        }).execute())
