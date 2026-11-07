"""Durable, tenant-scoped request-window operations.

The database is authoritative for availability.  In particular, the
``leave_requests`` trigger introduced with this service repeats the gate at the
same transaction that inserts the request, so this Python preflight is helpful
feedback rather than a race-prone security boundary.
"""
from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Any, Mapping


DUTY_LEAVE_TYPES = frozenset({"do", "duty_request", "shift_swap"})
WINDOW_KINDS = frozenset({"duty", "leave"})


class RequestWindowUnavailable(ValueError):
    """A gated request cannot be accepted under the database's current window."""


class RequestWindowConflict(RuntimeError):
    """A compare-and-swap update used an obsolete window version."""


class RequestWindowNotFound(ValueError):
    """The scoped durable request-window row does not exist."""


class RequestWindowDatabaseUnavailable(RuntimeError):
    """The required request-window RPC is absent or returned an invalid result."""


def kind_for_leave_type(leave_type: str) -> str | None:
    """Return the currently enforced kind for a leave type.

    ``SL``, ``DSL``, ``urgent`` and ``late`` deliberately return ``None``. They
    are sick/emergency reporting paths in the existing workflow and must remain
    reportable even while duty/day-off applications are closed.  Ordinary leave
    has a window resource available for the UI and future policy work, but is
    not newly gated here: only the confirmed DO/specific-duty paths are gated.
    """
    return "duty" if str(leave_type or "").strip().lower() in DUTY_LEAVE_TYPES else None


def _rpc_json(client: object, name: str, params: Mapping[str, Any]) -> dict:
    rpc = getattr(client, "rpc", None)
    if not callable(rpc):
        raise RequestWindowDatabaseUnavailable(
            "request-window database procedure is unavailable; the request was not accepted"
        )
    try:
        data = rpc(name, dict(params)).execute().data
    except Exception as exc:  # noqa: BLE001 - database driver types vary by version
        code = str(getattr(exc, "code", "") or "")
        message = str(getattr(exc, "message", "") or str(exc))
        if (
            code in {"P0001", "23505"}
            or "stale request-window version" in message.lower()
            or "idempotency key already belongs" in message.lower()
        ):
            raise RequestWindowConflict("request window was changed by another manager") from exc
        if code == "P0002" or "request window not found" in message.lower():
            raise RequestWindowNotFound("request window not found") from exc
        raise RequestWindowDatabaseUnavailable(
            "request-window database procedure failed; the request was not accepted"
        ) from exc
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise RequestWindowDatabaseUnavailable(
            "request-window database procedure returned no usable result"
        )
    return data


def availability(
    client: object,
    facility_id: str,
    staff_id: str,
    *,
    leave_type: str,
    date_start: Date | None = None,
    date_end: Date | None = None,
) -> dict:
    """Get a DB-clock availability decision for one staff member and request.

    The RPC resolves facility/org/unit scope itself.  Neither the web client nor
    this service chooses a tenant, unit, server timestamp, or effective window.
    """
    return _rpc_json(
        client,
        "request_window_availability",
        {
            "p_facility_id": facility_id,
            "p_staff_id": staff_id,
            "p_leave_type": leave_type,
            "p_date_start": date_start.isoformat() if date_start else None,
            "p_date_end": date_end.isoformat() if date_end else None,
        },
    )


def assert_request_allowed(
    client: object,
    facility_id: str,
    *,
    staff_id: str,
    leave_type: str,
    date_start: Date,
    date_end: Date,
) -> None:
    """Fail closed before a service write for confirmed DO/duty request kinds.

    The database trigger performs the same check on INSERT.  A close occurring
    after this preflight but before the insert therefore still rejects the row.
    """
    if kind_for_leave_type(leave_type) is None:
        return
    result = availability(
        client,
        facility_id,
        staff_id,
        leave_type=leave_type,
        date_start=date_start,
        date_end=date_end,
    )
    if result.get("available") is True:
        return
    status = str(result.get("status") or "unavailable")
    reason = str(result.get("reason") or "duty/day-off requests are unavailable")
    raise RequestWindowUnavailable(f"{reason} (window status: {status})")


def list_scoped(client: object, facility_id: str) -> dict:
    """List the caller's tenant-scoped durable windows using DB time."""
    return _rpc_json(
        client,
        "request_window_catalog",
        {"p_facility_id": facility_id},
    )


def create(
    client: object,
    facility_id: str,
    *,
    kind: str,
    scope: str,
    unit_id: str | None,
    state: str,
    opens_at: str,
    closes_at: str,
    target_start: str,
    target_end_exclusive: str,
    idempotency_key: str,
    reason: str | None,
) -> dict:
    """Create (or exactly replay) one durable request-window row via its RPC."""
    return _rpc_json(
        client,
        "create_request_window",
        {
            "p_facility_id": facility_id,
            "p_kind": kind,
            "p_scope_level": scope,
            "p_unit_id": unit_id,
            "p_state": state,
            "p_opens_at": opens_at,
            "p_closes_at": closes_at,
            "p_target_start": target_start,
            "p_target_end_exclusive": target_end_exclusive,
            "p_idempotency_key": idempotency_key,
            "p_reason": reason,
        },
    )


def patch(
    client: object,
    facility_id: str,
    window_id: str,
    *,
    version: int,
    patch_values: Mapping[str, Any],
    reason: str | None,
) -> dict:
    """Apply a versioned compare-and-swap patch through the database RPC."""
    return _rpc_json(
        client,
        "patch_request_window",
        {
            "p_facility_id": facility_id,
            "p_window_id": window_id,
            "p_expected_version": version,
            "p_patch": dict(patch_values),
            "p_reason": reason,
        },
    )


def my_window(client: object, facility_id: str, staff_id: str, *, kind: str) -> dict:
    """Return the effective window for a Staff PWA caller without a request date."""
    if kind not in WINDOW_KINDS:
        raise ValueError("kind must be 'duty' or 'leave'")
    # ``request_window_availability`` derives the expected kind from leave type.
    # A representative duty type is therefore used for duty; leave is rendered
    # from the catalog below because ordinary leave is intentionally not gated.
    if kind == "duty":
        return availability(
            client,
            facility_id,
            staff_id,
            leave_type="duty_request",
        )

    catalog = list_scoped(client, facility_id)
    windows = catalog.get("windows") if isinstance(catalog.get("windows"), list) else []
    own_unit_id = _own_unit_id(client, facility_id, staff_id)
    candidates = [
        row for row in windows
        if isinstance(row, dict)
        and row.get("kind") == "leave"
        and (row.get("scope") == "facility" or row.get("unit_id") == own_unit_id)
    ]
    candidates.sort(key=lambda row: 0 if row.get("scope") == "unit" else 1)
    window = candidates[0] if candidates else None
    status = str(window.get("status")) if window else "unavailable"
    return {
        "kind": "leave",
        "available": status == "open",
        "status": status,
        "reason": None if window else "No leave request window is configured for your scope.",
        "server_now": catalog.get("server_now"),
        "window": window,
    }


def _own_unit_id(client: object, facility_id: str, staff_id: str) -> str | None:
    """Resolve only the caller's own unit; failure never broadens visibility."""
    try:
        rows = (
            client.table("staff").select("primary_unit_id")
            .eq("facility_id", facility_id).eq("id", staff_id).execute().data
        )
    except Exception:  # noqa: BLE001 - a missing unit means no unit window visibility
        return None
    return str(rows[0].get("primary_unit_id")) if rows and rows[0].get("primary_unit_id") else None


def legacy_duty_window(result: Mapping[str, Any]) -> dict:
    """Map the new `/me` contract to the currently shipped PWA duty shape.

    Legacy ``target_end`` remains inclusive. Subtract one calendar day from the
    canonical exclusive bound so an unchanged PWA never enables an invalid day.
    """
    window = result.get("window") if isinstance(result.get("window"), Mapping) else {}
    status = str(result.get("status") or "unavailable")
    exclusive = window.get("target_end_exclusive")
    try:
        inclusive_end = (Date.fromisoformat(str(exclusive)) - timedelta(days=1)).isoformat() if exclusive else None
    except (ValueError, OverflowError):
        raise RequestWindowDatabaseUnavailable("request window returned an invalid target date")
    return {
        "enabled": bool(window and window.get("state") == "open"),
        "opens_at": window.get("opens_at"),
        "closes_at": window.get("closes_at"),
        "target_start": window.get("target_start"),
        "target_end": inclusive_end,
        "status": status if status in {"open", "closed", "scheduled", "expired"} else "closed",
        "server_now": result.get("server_now"),
    }
