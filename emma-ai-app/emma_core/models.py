"""Pydantic models returned by services. `extra="ignore"` keeps boundary rows forward-compatible as DB columns are added."""
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    required: float
    actual: float
    passes: bool


# ── solver / optimize contract (Phase 2) ────────────────────────────────────
# Request/response for POST /optimize-roster.
class SolverLimitsModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # Keep caller-controlled solver resources inside an API-safe envelope.
    max_seconds: float = Field(default=10.0, gt=0, le=120)
    workers: int = Field(default=8, ge=1, le=32)
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


class SessionUser(BaseModel):
    """The signed-in user as one object, for clients that want it nested."""
    id: str
    email: str | None = None
    role: Role | None = None
    staff_id: str | None = None
    facility_id: str | None = None
    facility_name: str | None = None


class SessionOut(BaseModel):
    """Serializable auth session - never expose the live Supabase client."""
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_at: int | None = None
    user_id: str
    email: str | None = None
    role: Role | None = None
    facility_id: str | None = None
    facility_name: str | None = None
    # Same identity as the flat fields, nested. Read one shape or the other.
    user: SessionUser | None = None


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
    staff_id: str | None = None
    date: Date | None = None
    unit_id: str | None = None
    task_assignment_id: str | None = None
    event_id: str | None = None
    validation_run_id: str | None = None
    rule_definition_id: str | None = None
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
    model_config = ConfigDict(extra="ignore")
    roster_version_id: str
    method: str
    passes: bool
    hard_violation_count: int = 0
    constraint_score: int | None = None
    violations: list[ViolationOut] = Field(default_factory=list)
    ratio_checks: list[RatioResult] = Field(default_factory=list)
    validation_run_id: str | None = None
    input_digest: str | None = None


class RuleDefinitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_code: str = Field(min_length=1)
    name: str | None = None
    description: str | None = None
    severity: str = Field(default="hard", pattern="^(hard|soft)$")
    config_json: dict = Field(default_factory=dict)
    config_version: int = Field(default=1, ge=1)
    effective_from: Date | None = None
    effective_to: Date | None = None
    active: bool = True


class RuleDefinitionOut(RuleDefinitionCreate):
    model_config = ConfigDict(extra="ignore")
    id: str
    facility_id: str | None = None
    created_at: DateTime | None = None
    updated_at: DateTime | None = None


# ── Phase 3 request bodies ──────────────────────────────────────────────────
# Phase 3 responses are dicts assembled by the services - they are aggregates of
# many tables that change shape as screens evolve, and pinning a response_model
# to each one buys nothing but drift. Request bodies stay typed: those are the
# trust boundary.
class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: str | None = None       # None => the caller's own staff record
    leave_type: str                   # AL|special|marriage|DO|duty_request|SL|DSL|urgent|late
    date_start: Date
    date_end: Date
    reason: str | None = None
    remark: str | None = None
    requested_shift_type: str | None = None
    document_url: str | None = None

    @model_validator(mode="after")
    def validate_request_semantics(self):
        if self.date_end < self.date_start:
            raise ValueError("date_end must be on or after date_start")
        positive_duty = self.leave_type in {"duty_request", "shift_swap"}
        if positive_duty and not self.requested_shift_type:
            raise ValueError(
                "requested_shift_type is required for a duty request or shift swap"
            )
        if not positive_duty and self.requested_shift_type:
            raise ValueError(
                "requested_shift_type is only valid for a duty request or shift swap"
            )
        return self


class LeaveDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(approve|reject|review)$")
    note: str | None = None
    ballot_approved: bool | None = None

    @model_validator(mode="after")
    def validate_ballot_decision(self):
        if self.ballot_approved is not None and self.decision != "approve":
            raise ValueError("ballot_approved is only valid when approving")
        return self


class RecommendationRequest(BaseModel):
    """A first-pass review by an R-grade role (spec 1.1).

    `reason` is required and non-blank: the RBAC definition specifies
    "suggest-approve/suggest-reject **with reason**", and a bare vote gives the
    approver nothing to weigh when two reviewers disagree."""
    model_config = ConfigDict(extra="forbid")

    recommendation: str = Field(pattern="^(approve|reject)$")
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def reason_is_not_whitespace(self):
        if not self.reason.strip():
            raise ValueError("reason cannot be blank")
        return self


class RevokeRequest(BaseModel):
    """Withdrawing an approval already given. OWNER only."""
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def reason_is_not_whitespace(self):
        if not self.reason.strip():
            raise ValueError("reason cannot be blank")
        return self


class WithdrawRequest(BaseModel):
    """Taking back a request that has not been decided. Reason is optional -
    unlike a revocation, nobody has been promised anything yet, so requiring an
    explanation to undo your own pending request would be friction for its own
    sake."""
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)


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


class TaskExceptionRequest(BaseModel):
    """"Could not do this task, and here is why" (spec SA.3).

    `reason_code` is a closed list so the answer to "how often is personal care
    refused on 2/F?" is a count rather than a reading exercise. The pattern is
    kept in step with the database check constraint by
    `test_mvp_staff_app.py::test_exception_reasons_match_the_migration`.
    """
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(pattern="^(resident_refused|resident_absent|clinical_hold"
                                     "|equipment_unavailable|insufficient_time"
                                     "|staff_reassigned|other)$")
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def other_needs_a_note(self):
        if self.reason_code == "other" and not (self.note or "").strip():
            raise ValueError("a note is required when reason_code is 'other'")
        return self


# ── shift swap (spec SA.6) ───────────────────────────────────────────────────
class SwapCreateRequest(BaseModel):
    """Staff A proposes. `requester_staff_id` is never accepted from the body -
    the caller's own staff record is used, so nobody can propose on another
    person's behalf."""
    model_config = ConfigDict(extra="forbid")

    requester_shift_id: str
    counterparty_staff_id: str
    counterparty_shift_id: str
    reason: str | None = Field(default=None, max_length=2000)


class SwapPeerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept: bool
    note: str | None = Field(default=None, max_length=2000)


class SwapDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = Field(default=None, max_length=2000)


class PushSubscriptionRequest(BaseModel):
    """A device registering for push (spec SA.4). Valid before FCM is
    provisioned - delivery is the worker's problem, registration is not."""
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=4096)
    platform: str = Field(default="web", pattern="^(web|ios|android)$")
    user_agent: str | None = Field(default=None, max_length=500)


# ── staff writes (spec 2.1) ──────────────────────────────────────────────────
class StaffCreate(BaseModel):
    """Create a staff record. `facility_id` is not accepted from the body: it
    comes from the caller's profile, so a write can never land in another home."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    rank: Rank
    employment_type: EmploymentType
    primary_unit_id: str | None = None
    contracted_hours: float | None = Field(default=None, ge=0, le=168)
    is_audited_for_medication: bool = False
    is_mentor: bool = False
    gender: str | None = Field(default=None, pattern="^(M|F)$")
    status: str = Field(default="active", pattern="^(active|inactive)$")

    @model_validator(mode="after")
    def name_is_not_whitespace(self):
        if not self.name.strip():
            raise ValueError("name cannot be blank")
        return self


class StaffUpdate(BaseModel):
    """Every field optional - a PATCH that omits a field leaves it alone.
    `rank` and `employment_type` are included because both are correctable data
    entry, and both feed the rule engine, so a wrong one has to be fixable."""
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    rank: Rank | None = None
    employment_type: EmploymentType | None = None
    primary_unit_id: str | None = None
    contracted_hours: float | None = Field(default=None, ge=0, le=168)
    is_audited_for_medication: bool | None = None
    is_mentor: bool | None = None
    gender: str | None = Field(default=None, pattern="^(M|F)$")
    status: str | None = Field(default=None, pattern="^(active|inactive)$")

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_dump(exclude_unset=True):
            raise ValueError("provide at least one field to update")
        return self


class TaskAssignmentCreate(BaseModel):
    shift_assignment_id: str
    task_id: str
    start_at: DateTime | None = None
    end_at: DateTime | None = None
    source_type: str = "manual"
    # Where this escort is going, on this date, for this staff member. Per
    # assignment and not per task definition - Cherry, ClickUp 4.1, 31 Jul 2026.
    escort_location: str | None = Field(default=None, max_length=32)


class TaskAssignmentPatch(BaseModel):
    task_id: str | None = None
    start_at: DateTime | None = None
    end_at: DateTime | None = None
    source_type: str | None = None
    escort_location: str | None = Field(default=None, max_length=32)


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
    escort_location: str | None = None
    escort_location_id: str | None = None


class EscortLocationOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    facility_id: str | None = None
    code: str
    name_en: str | None = None
    name_zh: str | None = None
    aliases: list[str] = Field(default_factory=list)
    active: bool = True


class EscortLocationRequest(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name_en: str | None = None
    name_zh: str | None = None
    aliases: list[str] | None = None


class EscortLocationAssign(BaseModel):
    """`null` clears the destination; the endpoint is how an escort is cancelled."""

    escort_location: str | None = Field(default=None, max_length=32)


class CertificateUpsert(BaseModel):
    cert_type: str = Field(min_length=1, max_length=64)
    expiry_date: Date | None = None
    file_url: str | None = None
    # As printed on the document; the number the registry is checked against.
    cert_number: str | None = Field(default=None, max_length=128)
    issued_date: Date | None = None
    # Set to correct a certificate in place; omit to add or renew by type.
    certificate_id: str | None = None


class CertificateOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    staff_id: str
    cert_type: str
    expiry_date: Date | None = None
    issued_date: Date | None = None
    cert_number: str | None = None
    file_url: str | None = None
    # Derived on read, never stored: a stored `days_left` is wrong by definition
    # the morning after it is written.
    days_left: int | None = None
    is_expired: bool = False
    stage: str | None = None
    notified_stage: str | None = None


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


# ── 4.1 staff qualifications ────────────────────────────────────────────────
class StaffQualificationCreate(BaseModel):
    staff_id: str
    # Free text on purpose: a facility invents its own capability names and the
    # eligibility rules match them by string, so a closed enum would need a
    # migration every time a home adds one.
    qualification_type: str
    is_active: bool = True
    effective_from: Date | None = None
    expiry_date: Date | None = None
    notes: str | None = None


class StaffQualificationPatch(BaseModel):
    qualification_type: str | None = None
    is_active: bool | None = None
    effective_from: Date | None = None
    expiry_date: Date | None = None
    notes: str | None = None


class StaffQualificationOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    staff_id: str
    qualification_type: str
    is_active: bool = True
    effective_from: Date | None = None
    expiry_date: Date | None = None
    notes: str | None = None


# ── 4.3 floor / unit minimum staffing ───────────────────────────────────────
class FloorRuleCreate(BaseModel):
    unit_id: str | None = None
    floor: str | None = None
    time_window_start: str
    time_window_end: str
    # "HCA" or an alternatives expression such as "CW|HCA".
    rank: str
    min_count: int = Field(ge=0)
    condition_json: dict = Field(default_factory=dict)
    active: bool = True
    effective_from: Date | None = None
    effective_to: Date | None = None


class FloorRulePatch(BaseModel):
    unit_id: str | None = None
    floor: str | None = None
    time_window_start: str | None = None
    time_window_end: str | None = None
    rank: str | None = None
    min_count: int | None = Field(default=None, ge=0)
    condition_json: dict | None = None
    active: bool | None = None
    effective_from: Date | None = None
    effective_to: Date | None = None


class FloorRuleOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    unit_id: str | None = None
    floor: str | None = None
    time_window_start: str
    time_window_end: str
    rank: str
    min_count: int
    condition_json: dict = Field(default_factory=dict)
    active: bool = True
    effective_from: Date | None = None
    effective_to: Date | None = None


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


class ReportRequest(BaseModel):
    """Body of the named report endpoints, which fix the report_type themselves."""

    period_id: str | None = None
    date_from: Date | None = None
    date_to: Date | None = None


# ── MVP foundation request bodies (spec 1.4 / 1.5 / 1.6 / 2.2 / 2.3) ─────────
class CalendarDayRequest(BaseModel):
    day_date: Date
    day_type: str = "public_holiday"       # normal|public_holiday|statutory_holiday|special_pay
    holiday_name: str | None = None
    is_agency_allowed: bool = True
    agency_cost_multiplier: float = Field(default=1.0, ge=0)
    staff_cost_multiplier: float = Field(default=1.0, ge=0)
    notes: str | None = None


class FacilityConfigRequest(BaseModel):
    config_key: str = Field(min_length=1, max_length=64)
    config_json: dict
    description: str | None = None
    effective_from: Date | None = None


class ShiftSegmentIn(BaseModel):
    start: str = Field(pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    end: str = Field(pattern=r"^\d{2}:\d{2}(:\d{2})?$")


class ShiftDefinitionRequest(BaseModel):
    """A duty code. `segments` carries a split shift's two windows (A/N, A+P)."""

    shift_type: str = Field(min_length=1, max_length=16)
    label: str | None = None
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    segments: list[ShiftSegmentIn] | None = None
    is_working: bool = True
    weighting_factor: float = Field(default=1.0, ge=0)
    paid_minutes: int | None = Field(default=None, ge=0)
    source_note: str | None = None


class EvidenceStatusRequest(BaseModel):
    status: str                            # pending|pass|fail|not_applicable
    sample_output: str | None = None
    notes: str | None = None
    checked_on: Date | None = None
