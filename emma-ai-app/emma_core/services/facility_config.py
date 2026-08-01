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
    "working_hours",        # NAAC's dual 44h office / 49h frontline week
    "duty_supervisor_quota",  # per-person '#' allocation for a cycle
    "meal_breaks",          # when each batch eats, and who eats late
    "coverage_minimums",    # statutory staff-on-duty windows
)


# ── NAAC's facility profile (2.2) ────────────────────────────────────────────
# Source: NAAC編更安排1.docx via ClickUp task 2.2, 31 Jul 2026. Translated set in
# docs/naac/rostering_rules_EN.md.
#
# The dual working week is the load-bearing part. From 2021-01-04 frontline staff
# moved to 49 hours over six days - 8h10m a day, the awkward 8.1667 that produces
# the `x` (+10 min) code family - while office staff and therapists stayed on 44.
# It has to be per *role* rather than per facility, because both regimes run in
# the same building on the same roster, and a leave day is worth 8h to a clerk
# and 8h10m to a care worker.
NAAC_WORKING_HOURS = {
    "regimes": {
        "office": {
            "weekly_hours": 44, "daily_hours": 8.0,
            "rest_days_per_cycle": 9,
            "ranks": ["SW", "AW", "RN", "EN", "HW"],
            "note": "Officers, social workers, clerks.",
        },
        "therapist": {
            "weekly_hours": 44, "daily_hours": 9.0,
            "rest_days_per_cycle": 9,
            "ranks": ["PT", "OT", "PTA", "OTA"],
            "note": "44h over fewer, longer days.",
        },
        "frontline": {
            "weekly_hours": 49, "daily_hours": 8.1667,
            "rest_days_per_cycle": 6,
            "ranks": ["WA", "PCW", "CW", "HCA", "WM", "COOK"],
            "note": "8h10m a day since 2021-01-04. Drives the 'x' code family.",
        },
    },
    "cycle_weeks": 6,
    # Leave is paid at the staff member's own daily hours, which is why the home
    # writes AL and ALx as separate codes rather than one code and a lookup.
    "leave_hours_follow_regime": True,
    "effective_from": "2021-01-04",
}

# The '#' marker is a per-shift responsibility, not a role: it grants no extra
# approval rights, so it is config here rather than a row in the RBAC matrix.
#
# The per-person numbers are deliberately NOT in this file, and not in any file.
# Three named staff carry a personal quota (15/13/9 against the nurses' 12) and
# two more have personal constraints. That is employee data, and Cherry's
# instruction on 1 Aug was explicit about where it goes:
#
#   "the personal constraints ... should be stored as configurable rules in the
#    DB (not hardcoded in any config file), so that the OWNER can update them via
#    the admin UI in future without a code change."
#
# So `staff_scheduling_constraints` (migration 20) holds them, behind RLS and
# editable by the OWNER. What lives here is the shape, the default that applies
# when nobody has an override, and the fact that overrides exist at all.
NAAC_DUTY_SUPERVISOR_QUOTA = {
    "marker": "#",
    "acting_marker": "(#)",
    "grants_approval_rights": False,
    "per_cycle_default": 12,
    "default_applies_to_ranks": ["RN", "EN", "HW"],
    "overrides_source": "staff_scheduling_constraints",
    "distribution": "even",
    "note": "Per-person quotas are rows in staff_scheduling_constraints "
            "(constraint_type='require_quota'), never config. Seeded from the "
            "home's DO更次數 sheet. See docs/naac/README.md.",
}

# Duty supervisors eat an hour after everyone else, because somebody has to be on
# the floor while the first batch eats. Encoded because it decides who is
# countable during the meal window, not because catering needs scheduling.
NAAC_MEAL_BREAKS = {
    "weekday": {"first_batch": "18:15", "duty_supervisor": "19:15"},
    "weekend_or_ph": {
        "residents": "17:30", "first_batch": "17:45", "duty_supervisor": "18:45",
        "note": "First batch is the two 心 positions; second is the E position and *9肌.",
    },
}

# Residential Care Homes (Persons with Disabilities) Regulation, as the home
# applies it. The overnight rule is why the B130 / A2s / A220x codes exist at all.
NAAC_COVERAGE_MINIMUMS = {
    "windows": [
        {"from": "18:00", "to": "07:00", "min_staff": 2,
         "note": "Any two staff. The reason B130 / A2s / A220x exist."},
        {"from": "10:00", "to": "16:00", "min_nurses": 1, "or_min_health_workers": 2,
         "note": "From the NAAC RBAC document."},
    ],
}

NAAC_CONFIGS: dict[str, dict] = {
    "working_hours": NAAC_WORKING_HOURS,
    "duty_supervisor_quota": NAAC_DUTY_SUPERVISOR_QUOTA,
    "meal_breaks": NAAC_MEAL_BREAKS,
    "coverage_minimums": NAAC_COVERAGE_MINIMUMS,
    "scheduling_cycle": {"cycle_type": "42day", "days": 42, "weeks": 6},
}


def seed_naac_configs(client, facility_id: str, *, created_by: str | None = None,
                      overwrite: bool = False) -> list[dict]:
    """Publish NAAC's profile into `facility_json_configs`.

    Skips a key that already has an active version unless `overwrite`, because
    re-running a seed should not silently retire a value the home has since
    corrected by hand.
    """
    written = []
    for key, payload in NAAC_CONFIGS.items():
        if not overwrite and get_config(client, facility_id, key):
            continue
        written.append(put_config(
            client, facility_id, config_key=key, config_json=payload,
            description="NAAC TAH profile, from NAAC編更安排1.docx (ClickUp 2.2, 31 Jul 2026)",
            created_by=created_by,
        ))
    return written


def working_hours_for_rank(config: dict, rank: str | None) -> dict | None:
    """Which of the three regimes a rank falls under.

    Returns None for an unmapped rank rather than guessing. A wrong guess here
    silently misprices every leave day and every overtime hour for that person,
    and 44 is the more likely guess and the cheaper one - so the caller is made
    to decide instead.
    """
    rank = (rank or "").upper()
    if not rank:
        return None
    for name, regime in (config.get("regimes") or {}).items():
        if rank in {str(r).upper() for r in regime.get("ranks") or ()}:
            return {"regime": name, **regime}
    return None


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
