"""Public / statutory / special-pay calendar (spec 1.5).

The solver and the cost engine both need to know what kind of day a date is: a
statutory holiday changes pay, a peak public holiday can ban agency cover, and a
special double-pay day changes what a roster costs. Rows with a null
`facility_id` are the shared Hong Kong calendar; a facility row overrides it for
that home only.
"""
from __future__ import annotations

from datetime import date as Date

from ._common import as_date, iso, month_bounds

DAY_TYPES = ("normal", "public_holiday", "statutory_holiday", "special_pay")


def list_days(client, facility_id: str, *, date_from: Date | str | None = None,
              date_to: Date | str | None = None,
              include_shared: bool = True) -> list[dict]:
    """Calendar days in a range, the facility's own rows plus the shared ones."""
    if not date_from or not date_to:
        start, end = month_bounds(as_date(date_from) if date_from else None)
        date_from, date_to = date_from or start, date_to or end
    # SQL: select * from calendar_days
    #      where (facility_id = :facility_id [or facility_id is null])
    #        and date >= :date_from and date <= :date_to
    #      order by date
    query = client.table("calendar_days").select("*")
    query = (query.or_(f"facility_id.eq.{facility_id},facility_id.is.null")
             if include_shared else query.eq("facility_id", facility_id))
    rows = (query.gte("date", iso(date_from)).lte("date", iso(date_to))
            .order("date").execute().data)
    # A facility row wins over the shared row for the same date.
    by_date: dict[str, dict] = {}
    for row in rows:
        key = iso(row["date"])
        if key not in by_date or row.get("facility_id"):
            by_date[key] = row
    return [by_date[k] for k in sorted(by_date)]


def upsert_day(client, facility_id: str, *, date: Date | str, day_type: str,
               holiday_name: str | None = None, is_agency_allowed: bool = True,
               agency_cost_multiplier: float = 1.0,
               staff_cost_multiplier: float = 1.0,
               notes: str | None = None) -> dict:
    """Create or replace one facility calendar day.

    Writing is always facility-scoped: the shared Hong Kong calendar is reference
    data owned by a migration, and a home overriding a date does so for itself.
    """
    if day_type not in DAY_TYPES:
        raise ValueError(f"day_type must be one of {', '.join(DAY_TYPES)}")
    row = {
        "facility_id": facility_id, "date": iso(date), "day_type": day_type,
        "holiday_name": holiday_name, "is_agency_allowed": is_agency_allowed,
        "agency_cost_multiplier": agency_cost_multiplier,
        "staff_cost_multiplier": staff_cost_multiplier, "notes": notes,
    }
    # SQL: select id from calendar_days
    #      where facility_id = :facility_id and date = :date
    existing = (client.table("calendar_days").select("id")
                .eq("facility_id", facility_id).eq("date", iso(date))
                .execute().data)
    if existing:
        # SQL: update calendar_days set ... where id = :id returning *
        return (client.table("calendar_days").update(row)
                .eq("id", existing[0]["id"]).execute().data[0])
    # SQL: insert into calendar_days (...) values (...) returning *
    return client.table("calendar_days").insert(row).execute().data[0]
