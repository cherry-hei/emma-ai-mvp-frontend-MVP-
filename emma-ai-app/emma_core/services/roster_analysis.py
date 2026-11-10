"""Versioned, facility-owned analysis contract shared by generation and export.

No customer presets or employee records are bundled here. Only a manager-confirmed
profile is consumed; observed patterns alone are never activated as legal rules.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

KEY = "roster_analysis"
INCOMPLETE_MARKER = " · analysis incomplete"
SHEETS = (
    "更期代號註解", "代號及時數(old)", "代號及時數", "覆診地點代號",
    "第一週", "第二週", "第三週", "第四週", "第五週", "第六週",
    "Hours", "PH & Off", "DO更次數", "AP更", "C更男女", "N更男女", "用膳代號",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Code(StrictModel):
    code: str = Field(min_length=1, max_length=16, pattern=r"^[^=+@\r\n]+$")
    active: bool
    credit_minutes: int = Field(ge=0, le=1440)
    is_working: bool
    am: float = Field(default=0, ge=0, le=2)
    pm: float = Field(default=0, ge=0, le=2)
    night: float = Field(default=0, ge=0, le=2)
    sleepover: float = Field(default=0, ge=0, le=2)
    ph: float = Field(default=0, ge=0, le=1)
    al: float = Field(default=0, ge=0, le=1)
    duty_officer: float = Field(default=0, ge=0, le=1)
    remarks: str = Field(default="", max_length=600)
    source: str = Field(min_length=1, max_length=240)


class Role(StrictModel):
    rank: str = Field(min_length=1, max_length=32)
    weekly_minutes: int = Field(gt=0, le=10080)
    ph_minutes: int = Field(ge=0, le=1440)
    max_weekly_minutes: int | None = Field(default=None, gt=0, le=10080)
    min_rest_minutes: int = Field(ge=0, le=2880)
    allowed_codes: list[str] = Field(min_length=1, max_length=400)
    leave_codes: dict[str, str] = Field(default_factory=dict)


class Demand(StrictModel):
    code: str
    rank: str
    weekdays: list[int] = Field(min_length=1, max_length=7)
    count: int = Field(ge=1, le=100)
    day_type: Literal["all", "public_holiday", "non_public_holiday"] = "all"
    source: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def valid_days(self):
        if len(set(self.weekdays)) != len(self.weekdays) or any(d not in range(7) for d in self.weekdays):
            raise ValueError("weekdays must be unique integers from 0 (Monday) to 6")
        return self


class AnalysisProfile(StrictModel):
    schema_version: Literal[1] = 1
    label: str = Field(min_length=1, max_length=120)
    status: Literal["proposed", "confirmed"] = "proposed"
    evidence: list[str] = Field(min_length=1, max_length=30)
    codes: list[Code] = Field(min_length=1, max_length=400)
    roles: list[Role] = Field(min_length=1, max_length=40)
    demand: list[Demand] = Field(min_length=1, max_length=300)
    off_code: str
    duty_officer_task_code: str | None = Field(default=None, min_length=1, max_length=16)
    # The manager confirms which calendar dates count towards this profile's PH.
    # Export pairs are not inferred from the count of scheduled PH codes.
    holiday_dates: list[date] = Field(default_factory=list, max_length=366)

    @model_validator(mode="after")
    def consistent(self):
        codes = {c.code: c for c in self.codes}
        roles = {r.rank: r for r in self.roles}
        if len(codes) != len(self.codes) or len(roles) != len(self.roles):
            raise ValueError("duplicate code or rank in analysis profile")
        off = codes.get(self.off_code)
        if not off or not off.active or off.is_working or off.credit_minutes or off.ph or off.al:
            raise ValueError("off_code must be an active zero-credit non-leave code")
        if len(set(self.holiday_dates)) != len(self.holiday_dates):
            raise ValueError("duplicate holiday date")
        for role in self.roles:
            for code in [*role.allowed_codes, *role.leave_codes.values()]:
                if code not in codes or not codes[code].active:
                    raise ValueError("role references an unknown or retired code")
            if any(codes[c].is_working for c in role.leave_codes.values()):
                raise ValueError("leave mapping cannot refer to a working code")
        seen = set()
        for item in self.demand:
            code, role = codes.get(item.code), roles.get(item.rank)
            if not code or not code.active or not code.is_working or not role or item.code not in role.allowed_codes:
                raise ValueError("demand needs an active working code allowed for its rank")
            for day in item.weekdays:
                for category in (["public_holiday", "non_public_holiday"] if item.day_type == "all" else [item.day_type]):
                    key = (item.code, item.rank, day, category)
                    if key in seen:
                        raise ValueError("overlapping demand rows would double-count staffing")
                    seen.add(key)
        return self


def parse(payload: dict) -> AnalysisProfile:
    return AnalysisProfile.model_validate(payload)


def freeze(client, facility_id: str, config_id: str, period: dict) -> dict:
    rows = (client.table("facility_json_configs").select("*")
            .eq("facility_id", facility_id).eq("id", config_id)
            .eq("config_key", KEY).eq("active", True).execute().data)
    if not rows:
        raise ValueError("analysis configuration is unavailable for this facility")
    row = rows[0]
    profile = parse(row["config_json"])
    if profile.status != "confirmed":
        raise ValueError("analysis configuration needs manager confirmation")
    if row.get("effective_from") and str(row["effective_from"])[:10] > str(period["period_start"])[:10]:
        raise ValueError("analysis configuration is not effective for this period")
    payload = profile.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"config_id": row["id"], "version": row["version"], "digest": digest, "profile": payload}


def for_version(client, facility_id: str, version_id: str) -> dict | None:
    rows = (client.table("roster_option_scores").select("objective_weights_json")
            .eq("facility_id", facility_id).eq("roster_version_id", version_id).execute().data)
    if not rows:
        return None
    return (rows[0].get("objective_weights_json") or {}).get("analysis_snapshot")


def configured_shifts(profile: AnalysisProfile, definitions: list[dict], start: date, end: date) -> list[dict]:
    """Expand reviewed weekday/holiday demand using the organisation dictionary."""
    from ..shifttime import duty_segments, envelope, paid_minutes
    by_code = {d["shift_type"]: d for d in definitions}
    codes = {c.code: c for c in profile.codes}
    result = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        category = "public_holiday" if day in profile.holiday_dates else "non_public_holiday"
        for item in profile.demand:
            if day.weekday() not in item.weekdays or item.day_type not in {"all", category}:
                continue
            definition = by_code.get(item.code)
            if not definition or not definition.get("is_working") or not envelope(definition):
                raise ValueError(f"demand code {item.code!r} needs a working organisation dictionary definition")
            if paid_minutes(definition) != codes[item.code].credit_minutes:
                raise ValueError(f"analysis/dictionary credit mismatch for {item.code!r}")
            segments = duty_segments(definition)
            span = envelope(definition)
            result.append({**definition, "id": f"analysis:{day}:{item.rank}:{item.code}",
                           "date": day.isoformat(), "required_rank": item.rank,
                           "required_count": item.count, "unit_id": None,
                           "segments": [{"start": f"{a//60:02}:{a%60:02}", "end": f"{b//60:02}:{b%60:02}"} for a,b,_ in segments],
                           "start_time": f"{span[0]//60:02}:{span[0]%60:02}",
                           "end_time": f"{span[1]//60:02}:{span[1]%60:02}",
                           "cross_midnight": span[2], "paid_minutes": codes[item.code].credit_minutes})
    if not result:
        raise ValueError("analysis contains no working demand for this period")
    if sum(x["required_count"] for x in result) > 12000:
        raise ValueError("analysis demand exceeds the supported generation size")
    return result


def prepare_generation(client, facility_id, profile, start, end, shifts, assignments, staff_rows, requests):
    from .organisations import org_id_for
    if start.weekday() != 0 or (end - start).days != 41:
        raise ValueError("analysis generation requires 42 days beginning on Monday; use the monthly view within that period")
    definitions = (client.table("shift_definitions").select("*")
                   .eq("org_id", org_id_for(client, facility_id)).execute().data)
    generated = configured_shifts(profile, definitions, start, end)
    by_code = {c.code: c for c in profile.codes}
    roles = {r.rank: r for r in profile.roles}
    people = {s["id"]: s for s in staff_rows}
    if not people or any(s["rank"] not in roles for s in staff_rows):
        raise ValueError("every active employee needs an explicit role mapping")
    if len(people) > 200:
        raise ValueError("analysis generation supports at most 200 staff")
    holidays = sum(start <= day <= end for day in profile.holiday_dates)
    if any(holidays * role.ph_minutes > role.weekly_minutes * 6 for role in profile.roles):
        raise ValueError("PH deduction exceeds the six-week reference hours")
    existing = {s["id"]: s for s in shifts}
    held = {}
    for a in assignments:
        s = existing.get(a["shift_id"])
        if not s or s.get("is_working") or a.get("status") == "cancelled" or not a.get("staff_id"):
            continue
        if a["staff_id"] not in people:
            raise ValueError("source contains a nonworking assignment for unavailable staff")
        code = by_code.get(s["shift_type"])
        if not code or not code.active or code.is_working:
            raise ValueError("source nonworking code is not active in the analysis dictionary")
        day = date.fromisoformat(str(s["date"])[:10])
        if not start <= day <= end:
            raise ValueError("source assignment is outside its period")
        key = (a["staff_id"], day)
        if key in held:
            raise ValueError("duplicate source staff/day assignment")
        held[key] = (code.code, code.credit_minutes)
    for req in requests:
        if req.get("status") != "approved" or req.get("leave_type") in {"duty_request", "shift_swap"}:
            continue
        person = people.get(req.get("staff_id"))
        if not person:
            continue
        first = max(start, date.fromisoformat(str(req["date_start"])[:10]))
        last = min(end, date.fromisoformat(str(req["date_end"])[:10]))
        role = roles[person["rank"]]
        for offset in range((last-first).days + 1):
            day = first + timedelta(days=offset)
            code_name = role.leave_codes.get(str(req["leave_type"]))
            if not code_name:
                raise ValueError("approved leave needs an explicit role/leave-code mapping")
            code = by_code[code_name]
            if (person["id"], day) in held and held[(person["id"], day)][0] != code_name:
                raise ValueError("approved leave conflicts with a source nonworking cell")
            held[(person["id"], day)] = (code.code, code.credit_minutes)
    definitions_by_code = {d["shift_type"]: d for d in definitions}
    for code_name in {profile.off_code, *(code for code, _ in held.values())}:
        definition = definitions_by_code.get(code_name)
        if not definition or definition.get("is_working") or definition.get("paid_minutes") != by_code[code_name].credit_minutes:
            raise ValueError("nonworking code needs a matching organisation dictionary definition")
    return generated, tuple((sid, day, code, minutes) for (sid, day), (code, minutes) in sorted(held.items()))
