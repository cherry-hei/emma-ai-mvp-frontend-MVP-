"""Clock in / out for the staff app.

Worked time is derived by pairing each clock_in with the next clock_out, so an
unpaired clock_in (still on shift) contributes nothing until the staff member
clocks out — the month total never over-reports.
"""
from __future__ import annotations

from datetime import date as Date, datetime, timezone

from ._common import month_bounds, now_iso

CLOCK_IN = "clock_in"
CLOCK_OUT = "clock_out"


def _dt(v) -> datetime:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _events(client, facility_id: str, staff_id: str, start: str, end: str) -> list[dict]:
    return (client.table("attendance_events").select("*")
            .eq("facility_id", facility_id).eq("staff_id", staff_id)
            .gte("event_at", f"{start}T00:00:00Z").lte("event_at", f"{end}T23:59:59Z")
            .order("event_at").execute().data)


def _paired_minutes(events: list[dict]) -> int:
    total, open_in = 0, None
    for e in events:
        if e["event_type"] == CLOCK_IN:
            open_in = _dt(e["event_at"])
        elif e["event_type"] == CLOCK_OUT and open_in:
            total += max(0, round((_dt(e["event_at"]) - open_in).total_seconds() / 60))
            open_in = None
    return total


def clock(client, facility_id: str, staff_id: str, *, event_type: str,
          shift_id: str | None = None, note: str | None = None) -> dict:
    if event_type not in (CLOCK_IN, CLOCK_OUT):
        raise ValueError("event_type must be clock_in or clock_out")
    today = Date.today().isoformat()
    todays = _events(client, facility_id, staff_id, today, today)
    last = todays[-1]["event_type"] if todays else None
    if last == event_type:
        raise ValueError(f"already {event_type.replace('_', 'ed ')} today")
    if event_type == CLOCK_OUT and last is None:
        raise ValueError("cannot clock out before clocking in")

    return client.table("attendance_events").insert({
        "facility_id": facility_id, "staff_id": staff_id, "shift_id": shift_id,
        "event_type": event_type, "event_at": now_iso(), "source": "staff_app",
        "note": note,
    }).execute().data[0]


def today_status(client, facility_id: str, staff_id: str) -> dict:
    today = Date.today().isoformat()
    events = _events(client, facility_id, staff_id, today, today)
    ins = [e for e in events if e["event_type"] == CLOCK_IN]
    outs = [e for e in events if e["event_type"] == CLOCK_OUT]
    last = events[-1]["event_type"] if events else None
    return {
        "date": today,
        "clocked_in": last == CLOCK_IN,
        "clock_in_at": ins[0]["event_at"] if ins else None,
        "clock_out_at": outs[-1]["event_at"] if outs else None,
        "worked_minutes_today": _paired_minutes(events),
        "events": events,
    }


def month_summary(client, facility_id: str, staff_id: str,
                  on: Date | None = None) -> dict:
    start, end = month_bounds(on)
    events = _events(client, facility_id, staff_id, start, end)
    minutes = _paired_minutes(events)
    days = sorted({str(e["event_at"])[:10] for e in events if e["event_type"] == CLOCK_IN})
    return {
        "month_start": start, "month_end": end,
        "worked_hours": round(minutes / 60, 1),
        "days_worked": len(days),
        "events": events[-20:],
    }


def recent(client, facility_id: str, staff_id: str, limit: int = 20) -> list[dict]:
    return (client.table("attendance_events").select("*")
            .eq("facility_id", facility_id).eq("staff_id", staff_id)
            .order("event_at", desc=True).limit(limit).execute().data)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
