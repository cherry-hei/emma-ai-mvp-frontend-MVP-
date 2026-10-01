"""Owner-controlled request window for frontline duty and day-off requests.

The window is deliberately a versioned ``facility_json_configs`` record rather
than a process-global setting.  A request carries no facility supplied by the
client: its facility is always taken from the authenticated profile/client.
"""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime, timezone
from typing import Mapping

from . import facility_config

CONFIG_KEY = "duty_request_window"


class DutyRequestWindowError(ValueError):
    """A duty/day-off request is outside the currently published window."""


class DutyRequestWindowUnavailable(RuntimeError):
    """The atomic publication procedure has not yet been installed."""


def _as_aware(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        # PostgreSQL commonly serialises UTC with ``+00:00``; accepting ``Z``
        # makes a hand-authored configuration unambiguous too.
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"{field} must be an ISO-8601 datetime with timezone")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed


def _as_date(value: object, field: str) -> Date:
    if isinstance(value, Date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return Date.fromisoformat(value)
    raise ValueError(f"{field} must be an ISO-8601 date")


def _normalised_payload(config: Mapping | None) -> dict:
    """Validate a stored config record and return its public contract shape."""
    raw = (config or {}).get("config_json") if config else None
    raw = raw if isinstance(raw, Mapping) else {}
    enabled = bool(raw.get("enabled", False))
    opens_raw, closes_raw = raw.get("opens_at"), raw.get("closes_at")
    start_raw, end_raw = raw.get("target_start"), raw.get("target_end")

    # A disabled/missing record intentionally has the same safe closed shape.
    if not any((opens_raw, closes_raw, start_raw, end_raw)):
        return {
            "enabled": enabled,
            "opens_at": None,
            "closes_at": None,
            "target_start": None,
            "target_end": None,
        }
    if not all((opens_raw, closes_raw, start_raw, end_raw)):
        raise ValueError("duty_request_window must include all window and target fields")

    opens_at = _as_aware(opens_raw, "opens_at")
    closes_at = _as_aware(closes_raw, "closes_at")
    target_start = _as_date(start_raw, "target_start")
    target_end = _as_date(end_raw, "target_end")
    if closes_at <= opens_at:
        raise ValueError("closes_at must be after opens_at")
    if target_end < target_start:
        raise ValueError("target_end must be on or after target_start")
    return {
        "enabled": enabled,
        "opens_at": opens_at,
        "closes_at": closes_at,
        "target_start": target_start,
        "target_end": target_end,
    }


def status_for(window: Mapping, *, now: datetime | None = None) -> str:
    """Derive the public status. Opening and closing instants are inclusive."""
    if not window.get("enabled"):
        return "closed"
    opens_at, closes_at = window.get("opens_at"), window.get("closes_at")
    if not opens_at or not closes_at:
        return "closed"
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone offset")
    if now < opens_at:
        return "scheduled"
    if now > closes_at:
        return "expired"
    return "open"


def public_window(config: Mapping | None, *, now: datetime | None = None) -> dict:
    """Render the intentionally small frontend contract, never DB metadata."""
    window = _normalised_payload(config)
    return {
        "enabled": window["enabled"],
        "opens_at": window["opens_at"].isoformat() if window["opens_at"] else None,
        "closes_at": window["closes_at"].isoformat() if window["closes_at"] else None,
        "target_start": window["target_start"].isoformat() if window["target_start"] else None,
        "target_end": window["target_end"].isoformat() if window["target_end"] else None,
        "status": status_for(window, now=now),
    }


def get(client, facility_id: str, *, now: datetime | None = None) -> dict:
    return public_window(facility_config.get_config(client, facility_id, CONFIG_KEY), now=now)


def put(client, facility_id: str, *, enabled: bool, opens_at: datetime | None,
        closes_at: datetime | None, target_start: Date | None, target_end: Date | None,
        created_by: str) -> dict:
    """Atomically publish a new version, retaining inactive history.

    A missing RPC fails closed: the old two-query helper can retire the only
    active window before an insert fails, and must never be used here.
    """
    payload = {
        "enabled": enabled,
        "opens_at": opens_at.isoformat() if opens_at else None,
        "closes_at": closes_at.isoformat() if closes_at else None,
        "target_start": target_start.isoformat() if target_start else None,
        "target_end": target_end.isoformat() if target_end else None,
    }
    # Validate before the transaction. The database repeats validation because
    # a caller can bypass this Python route and invoke the authenticated RPC.
    _normalised_payload({"config_json": payload})
    rpc = getattr(client, "rpc", None)
    if not callable(rpc):
        raise DutyRequestWindowUnavailable("atomic duty request window RPC is unavailable")
    rows = rpc("publish_duty_request_window", {
        "p_facility_id": facility_id,
        "p_config_json": payload,
    }).execute().data
    row = rows[0] if isinstance(rows, list) and rows else rows
    if not isinstance(row, dict):
        raise DutyRequestWindowUnavailable("atomic duty request window RPC returned no row")
    return row


def assert_request_allowed(client, facility_id: str, *, leave_type: str,
                           date_start: Date, date_end: Date,
                           now: datetime | None = None) -> None:
    """Reject only DO/duty_request rows that lie outside an open target period.

    This is called before a leave write escalates to its workflow service client,
    so a closed RLS-scoped window cannot be bypassed by a manager-assisted
    submission or by a client-selected facility.
    """
    if leave_type not in {"DO", "duty_request"}:
        return
    config = facility_config.get_config(client, facility_id, CONFIG_KEY)
    window = _normalised_payload(config)
    state = status_for(window, now=now)
    if state != "open":
        raise DutyRequestWindowError(
            f"duty/day-off requests are not open (window status: {state})")
    target_start, target_end = window["target_start"], window["target_end"]
    if date_start < target_start or date_end > target_end:
        raise DutyRequestWindowError(
            "duty/day-off request dates must fall within the published target period")
