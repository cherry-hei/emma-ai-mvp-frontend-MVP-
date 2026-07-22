"""Facility units + daily resident-count input (denominator for ratios)."""
from __future__ import annotations

from ..models import Unit


def get_units(client, facility_id: str) -> list[Unit]:
    rows = (client.table("facility_units").select("id,name")
            .eq("facility_id", facility_id).order("name").execute().data)
    return [Unit.model_validate(r) for r in rows]


def set_resident_count(client, *, facility_id, date, unit_id, care_level, count,
                       entered_by=None) -> None:
    """Upsert the resident count for (facility, date, unit, care_level)."""
    existing = (client.table("daily_resident_counts").select("id")
                .eq("facility_id", facility_id).eq("date", str(date))
                .eq("unit_id", unit_id).eq("care_level", care_level)
                .execute().data)
    if existing:
        (client.table("daily_resident_counts")
         .update({"resident_count": count, "entered_by": entered_by})
         .eq("id", existing[0]["id"]).execute())
    else:
        (client.table("daily_resident_counts").insert({
            "facility_id": facility_id, "date": str(date), "unit_id": unit_id,
            "care_level": care_level, "resident_count": count, "entered_by": entered_by,
        }).execute())
