"""Pydantic models returned by services. `extra="ignore"` keeps boundary rows forward-compatible as DB columns are added."""
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

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
    # Split shifts (A/N) carry their separate duty windows; None = contiguous.
    segments: list[dict] | None = None
    paid_minutes: int | None = None


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
class StaffingRequirementOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    rank: str
    count: int
    is_additive: bool = True
    notes: str | None = None


class FacilityEventOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    event_type: str
    event_date: Date
    start_at: DateTime | None = None
    end_at: DateTime | None = None
    unit_id: str | None = None
    title: str | None = None
    notes: str | None = None
    staffing_requirements: list[StaffingRequirementOut] = Field(default_factory=list)


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
    events: list[FacilityEventOut] = Field(default_factory=list)


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
# Request/response for POST /optimize-roster.
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


# ── REST API request/response contracts (Phase 2, consumed by the Next.js app) ──
class LoginRequest(BaseModel):
    email: str
    password: str


class SessionOut(BaseModel):
    """Serializable auth session — never expose the live Supabase client."""
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_at: int | None = None
    user_id: str
    email: str | None = None
    role: Role | None = None
    facility_id: str | None = None
    facility_name: str | None = None


class PeriodOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    period_start: Date
    period_end: Date
    cycle_type: str | None = None
    status: str | None = None


class PeriodCreateRequest(BaseModel):
    period_start: Date
    period_end: Date
    cycle_type: str = "28day"
    # Bootstrap a blank 'manual' version so the grid/solver has a source (nothing else creates one).
    create_manual_version: bool = True


class VersionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    period_id: str | None = None
    version_type: str
    label: str | None = None
    status: str
    published_at: str | None = None
    created_at: str | None = None


class CellWriteRequest(BaseModel):
    roster_version_id: str
    staff_id: str
    date: Date
    shift_type: str
    tasks: list[str] = Field(default_factory=list)


class ResidentCountRequest(BaseModel):
    date: Date
    unit_id: str
    care_level: str = "general"
    count: int


class ResidentCountOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: Date
    unit_id: str | None = None
    care_level: str | None = None
    resident_count: int


class CertOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cert_type: str
    expiry_date: Date | None = None


class StaffOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    name_en: str | None = None
    rank: Rank
    employment_type: EmploymentType
    unit_name: str | None = None
    status: str | None = None                 # 'scheduled' | 'on_leave' | 'available' | raw
    contracted_hours: float | None = None      # weekly contract (raw)
    is_audited_for_medication: bool = False
    is_mentor: bool = False
    certs: list[str] = Field(default_factory=list)               # cert-type names (compat)
    certificates: list[CertOut] = Field(default_factory=list)    # + expiry, for compliance
    scheduled_hours: float = 0.0               # rostered working hours this period
    contracted_period_hours: float = 0.0       # weekly contract scaled to the period


class ShiftHistoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: Date
    shift_type: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    tasks: list[str] = Field(default_factory=list)


class StaffDetail(StaffOut):
    shift_history: list[ShiftHistoryItem] = Field(default_factory=list)


class TaskDefOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    task_code: str
    task_name: str | None = None
    shift_type: str | None = None
    required_rank: str | None = None
    requires_audit: bool = False
    unit_id: str | None = None
    description: str | None = None
    required_qualification_json: dict | list | str | None = None
    is_restricted: bool = False
    active: bool = True


class ViolationOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rule_code: str
    shift_id: str | None = None
    date: Date | None = None
    unit_id: str | None = None
    task_assignment_id: str | None = None
    event_id: str | None = None
    severity: str = "hard"
    message: str | None = None
    details: dict = Field(default_factory=dict)
    resolved: bool = False


class OptionScoreOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    roster_version_id: str
    plan_mode: str
    constraint_score: int
    hard_violation_count: int = 0
    soft_penalty_total: int = 0
    objective_weights: dict | None = None
    infeasible_reasons: list[str] = Field(default_factory=list)
    publishable: bool = False
    version_label: str | None = None
    version_status: str | None = None
    violations: list[ViolationOut] = Field(default_factory=list)


class ValidationOut(BaseModel):
    roster_version_id: str
    method: str                       # 'solver-scored' | 'ratio-check'
    passes: bool
    hard_violation_count: int = 0
    constraint_score: int | None = None
    violations: list[ViolationOut] = Field(default_factory=list)
    ratio_checks: list[RatioResult] = Field(default_factory=list)


# ── Phase 3 request bodies ──────────────────────────────────────────────────
# Phase 3 responses are dicts assembled by the services — they are aggregates of
# many tables that change shape as screens evolve, and pinning a response_model
# to each one buys nothing but drift. Request bodies stay typed: those are the
# trust boundary.
class LeaveRequestCreate(BaseModel):
    staff_id: str | None = None       # None => the caller's own staff record
    leave_type: str                   # AL|special|marriage|DO|duty_request|SL|DSL|urgent|late
    date_start: Date
    date_end: Date
    reason: str | None = None
    remark: str | None = None
    requested_shift_type: str | None = None
    document_url: str | None = None


class LeaveDecisionRequest(BaseModel):
    decision: str                     # approve|reject|review
    note: str | None = None


class IncidentCreate(BaseModel):
    staff_id: str | None = None       # None => the caller's own staff record
    incident_type: str = "SL"         # SL|DSL|urgent|late
    date: Date | None = None
    reason: str | None = None
    shift_id: str | None = None


class IncidentResolveRequest(BaseModel):
    replacement_staff_id: str
    auto: bool = True                 # accepted from an Emma suggestion
    note: str | None = None


class ClockRequest(BaseModel):
    event_type: str                   # clock_in|clock_out
    shift_id: str | None = None
    note: str | None = None


class TaskStatusRequest(BaseModel):
    status: str                       # pending|done|skipped


class TaskAssignmentCreate(BaseModel):
    shift_assignment_id: str
    task_id: str
    start_at: DateTime | None = None
    end_at: DateTime | None = None
    source_type: str = "manual"


class TaskAssignmentPatch(BaseModel):
    task_id: str | None = None
    start_at: DateTime | None = None
    end_at: DateTime | None = None
    source_type: str | None = None


class TaskAssignmentOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    roster_version_id: str | None = None
    shift_assignment_id: str
    staff_id: str | None = None
    task_id: str | None = None
    task_label: str
    start_at: DateTime | None = None
    end_at: DateTime | None = None
    source_type: str = "manual"
    task_status: str = "pending"
    completed_at: DateTime | None = None


class StaffingRequirementIn(BaseModel):
    rank: str
    count: int = Field(default=1, ge=1)
    is_additive: bool = True
    notes: str | None = None


class FacilityEventCreate(BaseModel):
    event_type: str
    event_date: Date
    start_at: DateTime | None = None
    end_at: DateTime | None = None
    unit_id: str | None = None
    title: str | None = None
    notes: str | None = None
    staffing_requirements: list[StaffingRequirementIn] | None = None


class FacilityEventPatch(BaseModel):
    event_type: str | None = None
    event_date: Date | None = None
    start_at: DateTime | None = None
    end_at: DateTime | None = None
    unit_id: str | None = None
    title: str | None = None
    notes: str | None = None
    staffing_requirements: list[StaffingRequirementIn] | None = None


class RoiSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    manager_hourly_rate: float | None = None
    roster_hours_before: float | None = None
    roster_hours_after: float | None = None
    hours_saved_per_incident: float | None = None
    agency_reduction_pct: float | None = None
    total_budget: float | None = None
    salary_budget: float | None = None
    contract_years: str | None = None       # 3yr|5yr|10yr
    vacancies_json: dict | None = None


class ReportGenerateRequest(BaseModel):
    report_type: str
    period_id: str | None = None
    date_from: Date | None = None
    date_to: Date | None = None
