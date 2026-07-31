"""Facility-scoped configuration and the shift dictionary (spec 2.2 / 2.3).

The split is deliberate. `rule_definitions` holds anything the compliance engine
*evaluates* - it is versioned, typed and testable because a bad rule can block a
legal roster. This module holds what a facility *is*: its scheduling cycle, its
agency vacancy formula, its floor minimums, its request quotas, its duty
dictionary. The engine reads both; only the former decides pass or fail.

Configs are effective-dated and versioned. Superseding a key deactivates the
previous row instead of overwriting it, so "what was the cycle in March?" stays
answerable after the home changes it.
"""
from __future__ import annotations

from ..shifttime import paid_minutes
from ._common import iso

# The keys the importer and the engine agree on. Free-form keys are allowed - a
# home can carry its own - but these are the ones the platform reads.
KNOWN_KEYS = (
    "scheduling_cycle",     # cycle type, days, current period
    "shift_dictionary",     # per-sheet duty windows as printed in the roster
    "request_quota",        # staff duty/leave requests allowed per day
    "agency_formula",       # Home B's vacancy-driven agency cap
    "floor_minimums",       # per-floor minimum staffing (mirrors Phase 4.3 rules)
    "holiday_priority",     # which leave wins on a high-demand holiday
)


def list_configs(client, facility_id: str, *, config_key: str | None = None,
                 include_history: bool = False) -> list[dict]:
    # SQL: select * from facility_json_configs
    #      where facility_id = :facility_id [and config_key = :config_key]
    #        [and active]                      -- unless include_history
    #      order by config_key, version desc
    query = (client.table("facility_json_configs").select("*")
             .eq("facility_id", facility_id))
    if config_key:
        query = query.eq("config_key", config_key)
    if not include_history:
        query = query.eq("active", True)
    return query.order("config_key").order("version", desc=True).execute().data


def get_config(client, facility_id: str, config_key: str) -> dict | None:
    rows = list_configs(client, facility_id, config_key=config_key)
    return rows[0] if rows else None


def put_config(client, facility_id: str, *, config_key: str, config_json: dict,
               description: str | None = None, effective_from=None,
               created_by: str | None = None) -> dict:
    """Publish a new version of one config key, retiring the previous one."""
    if not isinstance(config_json, dict):
        raise ValueError("config_json must be an object")
    if not config_key or len(config_key) > 64:
        raise ValueError("config_key must be 1-64 characters")
    # SQL: select version from facility_json_configs
    #      where facility_id = :facility_id and config_key = :config_key
    #      order by version desc limit 1
    previous = (client.table("facility_json_configs").select("version")
                .eq("facility_id", facility_id).eq("config_key", config_key)
                .order("version", desc=True).limit(1).execute().data)
    # SQL: update facility_json_configs set active = false
    #      where facility_id = :facility_id and config_key = :config_key and active
    (client.table("facility_json_configs").update({"active": False})
     .eq("facility_id", facility_id).eq("config_key", config_key)
     .eq("active", True).execute())
    row = {
        "facility_id": facility_id, "config_key": config_key,
        "config_json": config_json, "description": description,
        "version": (previous[0]["version"] + 1) if previous else 1,
        "active": True, "created_by": created_by,
    }
    if effective_from:
        row["effective_from"] = iso(effective_from)
    # SQL: insert into facility_json_configs (...) values (...) returning *
    return client.table("facility_json_configs").insert(row).execute().data[0]


# ── shift dictionary (2.3) ───────────────────────────────────────────────────
def upsert_shift_definition(client, facility_id: str, *, shift_type: str,
                            label: str | None = None,
                            start_time: str | None = None,
                            end_time: str | None = None,
                            segments: list[dict] | None = None,
                            is_working: bool = True,
                            weighting_factor: float = 1.0,
                            paid_minutes_override: int | None = None,
                            source_note: str | None = None) -> dict:
    """Create or update one duty code.

    `paid_minutes` is derived from the segments when a shift is split, because the
    A/N shift's pay is the sum of its two windows and not the elapsed span between
    them - see `emma_core.shifttime`. An explicit override still wins, for a home
    that pays a handover or a sleep-in differently.
    """
    if not shift_type or len(shift_type) > 16:
        raise ValueError("shift_type must be 1-16 characters")
    if segments:
        _validate_segments(segments)
    cross_midnight = bool(
        segments and segments[-1]["end"] <= segments[-1]["start"]
        or (not segments and start_time and end_time and end_time <= start_time))
    row = {
        "facility_id": facility_id, "shift_type": shift_type,
        "label": label or shift_type, "start_time": start_time,
        "end_time": end_time, "cross_midnight": cross_midnight,
        "is_working": is_working, "segments": segments,
        "weighting_factor": weighting_factor, "source_note": source_note,
        "paid_minutes": paid_minutes_override if paid_minutes_override is not None
                        else (paid_minutes({"segments": segments}) if segments
                              else None),
    }
    # SQL: select id from shift_definitions
    #      where facility_id = :facility_id and shift_type = :shift_type
    existing = (client.table("shift_definitions").select("id")
                .eq("facility_id", facility_id).eq("shift_type", shift_type)
                .execute().data)
    if existing:
        # SQL: update shift_definitions set ... where id = :id returning *
        return (client.table("shift_definitions").update(row)
                .eq("id", existing[0]["id"]).execute().data[0])
    # SQL: insert into shift_definitions (...) values (...) returning *
    return client.table("shift_definitions").insert(row).execute().data[0]


def _validate_segments(segments: list[dict]) -> None:
    for segment in segments:
        if not isinstance(segment, dict) or "start" not in segment or "end" not in segment:
            raise ValueError("each segment needs a 'start' and an 'end' (HH:MM)")
        for key in ("start", "end"):
            value = str(segment[key])
            if len(value) < 4 or ":" not in value:
                raise ValueError(f"segment {key} must be HH:MM, got {value!r}")
