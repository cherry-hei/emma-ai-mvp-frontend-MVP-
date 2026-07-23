"""Pydantic models returned by services (UI + API consume these).

Boundary models parse raw PostgREST rows so the rest of the code works with
typed objects instead of stringly-typed dicts. `extra="ignore"` keeps them
forward-compatible as columns are added.
"""
from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field

from .constants import EmploymentType, JobStatus, PlanMode, Rank, Role, SolveStatus


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
    period_id: str | None = None
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


# ── solver / optimize contract (Phase 2) ────────────────────────────────────
# Request/response for POST /optimize-roster (also used by the Reflex UI in-process).
class SolverLimitsModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    max_seconds: float = 10.0
    workers: int = 8
    seed: int = 42


class WritebackOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")
    persist: bool = True
    archive_previous_auto: bool = True   # archive prior auto A/B/C drafts for the period


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    facility_id: str
    period_id: str
    rule_profile_id: str | None = None
    plan_mode: PlanMode | None = None                    # None => generate all three
    source_version_id: str | None = None                 # default: latest 'manual' for period
    locked_assignments: list[dict] = Field(default_factory=list)   # {staff_id, slot_id, pin?}
    approved_leave_request_ids: list[str] = Field(default_factory=list)  # forward-compat
    include_staff_ids: list[str] = Field(default_factory=list)
    exclude_staff_ids: list[str] = Field(default_factory=list)
    solver_limits: SolverLimitsModel = Field(default_factory=SolverLimitsModel)
    writeback: WritebackOptions = Field(default_factory=WritebackOptions)
    created_by: str | None = None


class KpiSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    headcount_assigned: int = 0
    agency_count: int = 0
    ot_hours: float = 0.0
    coverage_gap: int = 0
    ratio_breaches: int = 0
    deviation_from_baseline: int = 0
    fairness_spread_minutes: int = 0


class RosterOption(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_mode: PlanMode
    version_label: str
    status: SolveStatus
    roster_version_id: str | None = None
    constraint_score: int
    hard_violation_count: int
    soft_penalty_total: int
    kpi: KpiSummary = Field(default_factory=KpiSummary)
    infeasible_reasons: list[str] = Field(default_factory=list)


class OptimizeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    job_id: str
    status: JobStatus
    roster_options: list[RosterOption] = Field(default_factory=list)


class JobView(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    status: JobStatus
    plan_mode: str | None = None
    result_json: dict | None = None
    error_json: dict | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
