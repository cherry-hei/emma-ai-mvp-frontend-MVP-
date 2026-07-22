"""Pydantic models returned by services (UI + API consume these).

Boundary models parse raw PostgREST rows so the rest of the code works with
typed objects instead of stringly-typed dicts. `extra="ignore"` keeps them
forward-compatible as columns are added.
"""
from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field

from .constants import EmploymentType, Rank, Role


# ── boundary rows (parsed from PostgREST) ───────────────────────────────────
class Unit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str


class ShiftDef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    shift_type: str
    label: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    cross_midnight: bool = False
    is_working: bool = True


class FacilityLite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str | None = None
    name: str | None = None


class Profile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    auth_user_id: str | None = None
    facility_id: str | None = None
    email: str | None = None
    role: Role
    staff_id: str | None = None
    facility: FacilityLite | None = None


# ── roster grid view (already typed) ────────────────────────────────────────
class StaffLite(BaseModel):
    id: str
    name: str
    name_en: str | None = None
    rank: Rank
    employment_type: EmploymentType
    unit_name: str | None = None


class RosterCell(BaseModel):
    date: Date
    shift_type: str | None = None        # None = empty cell
    is_working: bool = False
    tasks: list[str] = Field(default_factory=list)
    assignment_id: str | None = None
    shift_id: str | None = None


class RosterRow(BaseModel):
    staff: StaffLite
    cells: list[RosterCell]


class RosterGrid(BaseModel):
    version_id: str | None = None
    status: str | None = None
    period_start: Date | None = None
    period_end: Date | None = None
    dates: list[Date] = Field(default_factory=list)
    rows: list[RosterRow] = Field(default_factory=list)


class RatioResult(BaseModel):
    label: str
    rank: str | None = None
    window_start: str
    window_end: str
    residents: int
    required: int
    actual: int
    passes: bool
