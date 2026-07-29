// src/lib/apiTypes.ts
// TypeScript shapes for the Emma AI FastAPI backend (emma_core.models).
// Kept in sync by hand; regenerate from http://localhost:8000/openapi.json with
// `npx openapi-typescript` if you prefer generated types.

export interface SessionOut {
  access_token: string
  refresh_token?: string | null
  token_type: string
  expires_at?: number | null
  user_id: string
  email?: string | null
  role?: string | null
  facility_id?: string | null
  facility_name?: string | null
}

export interface Profile {
  id: string
  auth_user_id?: string | null
  facility_id?: string | null
  email?: string | null
  role: string
  staff_id?: string | null
  facility?: { code?: string | null; name?: string | null } | null
}

export interface CertOut {
  cert_type: string
  expiry_date?: string | null
}

export interface ApiStaff {
  id: string
  name: string
  name_en?: string | null
  rank: string
  employment_type: string
  unit_name?: string | null
  status?: string | null              // 'scheduled' | 'on_leave' | 'available'
  contracted_hours?: number | null
  is_audited_for_medication: boolean
  is_mentor: boolean
  certs: string[]
  certificates: CertOut[]             // cert_type + expiry_date, for compliance
  scheduled_hours: number             // rostered working hours this period
  contracted_period_hours: number     // weekly contract scaled to the period
}

export interface Unit {
  id: string
  name: string
}

export interface ResidentCountOut {
  date: string
  unit_id?: string | null
  care_level?: string | null
  resident_count: number
}

export interface ShiftHistoryItem {
  date: string
  shift_type?: string | null
  start_time?: string | null
  end_time?: string | null
  tasks: string[]
}

export interface StaffDetail extends ApiStaff {
  shift_history: ShiftHistoryItem[]
}

export interface PeriodOut {
  id: string
  period_start: string
  period_end: string
  cycle_type?: string | null
  status?: string | null
}

export interface VersionOut {
  id: string
  period_id?: string | null
  version_type: string
  label?: string | null
  status: string
  published_at?: string | null
  created_at?: string | null
}

export interface ShiftDef {
  id: string
  shift_type: string
  label?: string | null
  start_time?: string | null
  end_time?: string | null
  cross_midnight: boolean
  is_working: boolean
}

export interface RosterCell {
  date: string
  shift_type?: string | null
  is_working: boolean
  tasks: string[]
  assignment_id?: string | null
  shift_id?: string | null
}

export interface StaffLite {
  id: string
  name: string
  name_en?: string | null
  rank: string
  employment_type: string
  unit_name?: string | null
}

export interface RosterRowApi {
  staff: StaffLite
  cells: RosterCell[]
}

export interface RosterGrid {
  version_id?: string | null
  period_id?: string | null
  status?: string | null
  period_start?: string | null
  period_end?: string | null
  dates: string[]
  rows: RosterRowApi[]
  events: FacilityEvent[]
}

export interface RatioResult {
  label: string
  rank?: string | null
  window_start: string
  window_end: string
  residents: number
  required: number
  actual: number
  passes: boolean
}

export interface KpiSummary {
  headcount_assigned: number
  agency_count: number
  ot_hours: number
  coverage_gap: number
  ratio_breaches: number
  deviation_from_baseline: number
  fairness_spread_minutes: number
}

export interface RosterOption {
  plan_mode: string
  version_label: string
  status: string
  roster_version_id?: string | null
  constraint_score: number
  hard_violation_count: number
  soft_penalty_total: number
  kpi: KpiSummary
  infeasible_reasons: string[]
}

export interface OptimizeResponse {
  job_id: string
  status: string
  roster_options: RosterOption[]
}

export interface JobView {
  id: string
  status: string
  plan_mode?: string | null
  result_json?: { roster_options?: RosterOption[] } | null
  error_json?: Record<string, unknown> | null
  started_at?: string | null
  completed_at?: string | null
  created_at?: string | null
}

export interface TaskDefOut {
  id: string
  task_code: string
  task_name?: string | null
  shift_type?: string | null
  required_rank?: string | null
  requires_audit: boolean
  unit_id?: string | null
  description?: string | null
  required_qualification_json?: Record<string, unknown> | unknown[] | string | null
  is_restricted: boolean
  active: boolean
}

export interface ViolationOut {
  rule_code: string
  shift_id?: string | null
  staff_id?: string | null
  date?: string | null
  unit_id?: string | null
  task_assignment_id?: string | null
  event_id?: string | null
  validation_run_id?: string | null
  rule_definition_id?: string | null
  severity: string
  message?: string | null
  details: Record<string, unknown>
  resolved: boolean
}

export interface StaffingRequirement {
  id?: string | null
  rank: string
  count: number
  is_additive: boolean
  notes?: string | null
}

export interface FacilityEvent {
  id: string
  event_type: string
  event_date: string
  start_at?: string | null
  end_at?: string | null
  unit_id?: string | null
  title?: string | null
  notes?: string | null
  staffing_requirements: StaffingRequirement[]
}

export interface TaskAssignment {
  id: string
  roster_version_id?: string | null
  shift_assignment_id: string
  staff_id?: string | null
  task_id?: string | null
  task_label: string
  start_at?: string | null
  end_at?: string | null
  source_type: string
  task_status: string
  completed_at?: string | null
}

export interface OptionScoreOut {
  roster_version_id: string
  plan_mode: string
  constraint_score: number
  hard_violation_count: number
  soft_penalty_total: number
  objective_weights?: Record<string, unknown> | null
  infeasible_reasons: string[]
  publishable: boolean
  version_label?: string | null
  version_status?: string | null
  violations: ViolationOut[]
}

export interface CompareOptionsResponse {
  period_id: string
  options: OptionScoreOut[]
}

export interface ValidationOut {
  roster_version_id: string
  method: string
  passes: boolean
  hard_violation_count: number
  constraint_score?: number | null
  violations: ViolationOut[]
  ratio_checks: RatioResult[]
  validation_run_id?: string | null
  input_digest?: string | null
}

export interface RuleDefinition {
  id: string
  facility_id?: string | null
  rule_code: string
  name?: string | null
  description?: string | null
  severity: 'hard' | 'soft'
  config_json: Record<string, unknown>
  config_version: number
  effective_from?: string | null
  effective_to?: string | null
  active: boolean
  created_at?: string | null
  updated_at?: string | null
}

export type RuleDefinitionCreate =
  Pick<RuleDefinition, 'rule_code'> &
  Partial<Pick<
    RuleDefinition,
    'name' | 'description' | 'severity' | 'config_json' | 'config_version' |
    'effective_from' | 'effective_to' | 'active'
  >>

export interface CreatePeriodResponse {
  period: PeriodOut
  manual_version_id: string | null
}

export interface ApiError {
  detail: { code: string; message: string } | string
}

// ── Phase 3 ───────────────────────────────────────────────────────────────────

/** Staff identity carried on every Phase 3 list row. */
export interface StaffBrief {
  staff_id: string | null
  name: string
  name_en?: string | null
  rank?: string | null
  unit_name?: string | null
}

export type LeaveCategory = 'al' | 'duty' | 'sick'
export type LeaveGroup = 'pending' | 'approved'

export interface LeaveRequest extends StaffBrief {
  id: string
  category: LeaveCategory
  leave_type: string
  date_start: string
  date_end: string
  requested_shift_type?: string | null
  reason?: string | null
  remark?: string | null
  document_url?: string | null
  priority?: 'low' | 'normal' | 'high' | 'urgent'
  priority_reason?: string | null
  policy_result_json?: {
    passes?: boolean
    issues?: Array<Record<string, unknown>>
    priority_weight?: number
  }
  status: 'pending' | 'reviewed' | 'approved' | 'rejected' | 'cancelled'
  reviewed: boolean
  decided_at?: string | null
  decision_note?: string | null
  created_at?: string | null
}

export interface LeaveStats {
  month_start: string
  month_end: string
  total_actions: number
  decided_count: number
  approved_count: number
  pending_count: number
  approval_rate: number
}

export interface Incident extends StaffBrief {
  id: string
  incident_type: 'SL' | 'DSL' | 'urgent' | 'late'
  reason?: string | null
  reported_at: string
  date: string
  shift_id?: string | null
  shift_type?: string | null
  shift_window?: string | null
  status: 'open' | 'notified' | 'resolved' | 'cancelled'
  resolved: boolean
  resolved_at?: string | null
  resolution_minutes?: number | null
  auto_resolved: boolean
  replacement_staff_id?: string | null
  replacement_name?: string | null
  notes?: string | null
}

export interface IncidentStats {
  month_start: string
  month_end: string
  total: number
  open: number
  resolved: number
  auto_resolved: number
  auto_resolved_pct: number
  avg_response_minutes: number
  distribution: { incident_type: string; count: number; pct: number }[]
}

export interface ReplacementCandidate extends StaffBrief {
  candidate_staff_id: string
  score: number
  rank_order: number
  compliance_ok: boolean
  blocked_reasons: string[]
  reasons: string[]
  future_debt: { open_entries?: number }
}

export interface AlertItem {
  id: string
  kind: 'cover' | 'certificate' | 'ratio' | 'hours'
  urgent: boolean
  title: string
  detail: string
  unit_name?: string | null
  date?: string | null
  incident_id?: string
}

export interface FutureDebtRow extends StaffBrief {
  id: string
  debt_type: string
  quantity: number
  unit: string
  status: string
  note?: string | null
  created_at?: string | null
}

export interface Highlight {
  key: string
  value: number
  text_en: string
  text_zh: string
}

export interface DashboardSummary {
  facility: { id?: string; code?: string | null; name?: string | null; capacity?: number | null }
  period: { id: string; start: string; end: string; status?: string | null } | null
  roster_version: { id: string; label?: string | null; status?: string | null; version_type?: string | null } | null
  date: string
  kpis: {
    incidents_month: number
    auto_resolved: number
    auto_resolved_pct: number
    avg_response_minutes: number
    compliance_rate_pct: number
    open_alerts: number
  }
  incident_distribution: { incident_type: string; count: number; pct: number }[]
  shift_distribution: { shift_type: string; count: number; pct: number; is_working: boolean }[]
  recent_incidents: Incident[]
  alerts: AlertItem[]
  total_staff: number
  compliance_days: { date: string; checks: number; passed: number; failed: number; pass_rate: number }[]
  highlights: Highlight[]
}

export interface RoiSettings {
  facility_id: string
  manager_hourly_rate: number
  roster_hours_before: number
  roster_hours_after: number
  hours_saved_per_incident: number
  agency_reduction_pct: number
  total_budget: number
  salary_budget: number
  contract_years: '3yr' | '5yr' | '10yr'
  vacancies_json: Record<string, number>
}

export interface RoiSummary {
  month_start: string
  month_end: string
  settings: Record<string, number | string | Record<string, number>>
  staff: {
    total: number
    full_time: number
    part_time: number
    by_rank: { rank: string; headcount: number; vacancies: number }[]
  }
  a1: { hours_before: number; hours_after: number; hours_saved: number; hourly_rate: number; saving: number; formula: string }
  a2: { incidents: number; hours_per_incident: number; hours_saved: number; hourly_rate: number; saving: number; formula: string }
  agency: {
    monthly_cost: number
    shifts: number
    breakdown: { role: string; shifts: number; cost: number }[]
    reduction_pct: number
    saving: number
    formula: string
    scenarios: { pct: number; key: string; rationale: string; adopted: boolean; saving: number }[]
  }
  totals: {
    admin_saving: number
    monthly_saving: number
    annual_saving: number
    pct_of_annual_budget: number | null
  }
  emma: {
    tier: number
    tier_label: string
    contract_years: string
    rate_per_user: number
    monthly_fee: number
    annual_fee: number
    annual_fee_prepaid: number
    net_annual_benefit: number
    payback_months: number | null
    roi_multiple: number | null
  }
  tiers: { tier: number; label: string; max_staff: number; rates: Record<string, number> }[]
}

export interface ThresholdLevel {
  days?: number
  label_en: string
  label_zh: string
  action_en: string
  action_zh: string
}

export interface ThresholdMonitor {
  code: string
  icon: string
  name_en: string
  name_zh: string
  condition_en: string
  condition_zh: string
  severity: 'ok' | 'warn' | 'over'
  current_count: number
  note_en: string
  note_zh: string
  levels: ThresholdLevel[]
  law_en: string
  law_zh: string
}

export interface ReportSchedule {
  id: string
  report_type: string
  icon?: string | null
  name_en: string
  name_zh?: string | null
  cron_label_en?: string | null
  cron_label_zh?: string | null
  recipients_en: string[]
  recipients_zh: string[]
  content_en: string[]
  content_zh: string[]
  law_reference?: string | null
  last_run_at?: string | null
  next_run_at?: string | null
}

export interface EventTrigger {
  id: string
  trigger_code: string
  icon?: string | null
  label_en: string
  label_zh?: string | null
  action_en?: string | null
  action_zh?: string | null
  sla_en?: string | null
  sla_zh?: string | null
  law_reference?: string | null
  recent_count: number
}

export interface RegulatoryDoc {
  id: string
  doc_code: string
  name_en: string
  name_zh?: string | null
  key_clause_en?: string | null
  key_clause_zh?: string | null
  version_label?: string | null
  last_synced_at?: string | null
  sync_status: 'synced' | 'changed' | 'error'
}

export interface ReportType {
  report_type: string
  title: string
}

export interface ReportRow {
  id: string
  report_type: string
  title: string
  period_start?: string | null
  period_end?: string | null
  format: string
  row_count: number
  created_at?: string | null
}

export interface GeneratedReport extends ReportRow {
  payload: {
    columns: { key: string; label: string }[]
    rows: Record<string, string | number>[]
    meta: Record<string, unknown>
  }
}

// ── staff app ────────────────────────────────────────────────────────────────
export interface MyRosterDay {
  date: string
  shift_type?: string | null
  is_working: boolean
  start_time?: string | null
  end_time?: string | null
  unit_name?: string | null
  tasks: string[]
}

export interface MyRoster {
  staff_id: string
  name?: string | null
  name_en?: string | null
  rank?: string | null
  unit_name?: string | null
  start: string
  end: string
  days: MyRosterDay[]
}

export interface MyTask {
  id: string
  task_label: string
  scheduled_time?: string | null
  priority: 'high' | 'normal'
  status: 'pending' | 'done' | 'skipped'
  completed_at?: string | null
  shift_type: string
}

export interface HoursProgress {
  period_start?: string
  period_end?: string
  scheduled_hours: number
  contracted_hours: number
  pct: number
}

export interface AttendanceToday {
  date: string
  clocked_in: boolean
  clock_in_at?: string | null
  clock_out_at?: string | null
  worked_minutes_today: number
}

export interface MySummary {
  staff: { id: string; name?: string | null; name_en?: string | null; rank?: string | null; unit_name?: string | null; employment_type?: string | null }
  date: string
  today_shift: { shift_type: string; start_time?: string | null; end_time?: string | null; is_working: boolean; tasks: string[] } | null
  tasks_total: number
  tasks_pending: number
  tasks: MyTask[]
  hours: HoursProgress
  attendance: AttendanceToday
  facility_ratio: { passing: number; total: number; pct: number; worst_label: string } | null
  unread_notifications: number
}

export interface MyProfile {
  id: string
  name?: string | null
  name_en?: string | null
  rank?: string | null
  employment_type?: string | null
  unit_name?: string | null
  gender?: string | null
  is_mentor: boolean
  is_audited_for_medication: boolean
  certificates: { cert_type: string; expiry_date?: string | null; days_left?: number | null }[]
  hours: HoursProgress
  attendance_month: { month_start: string; month_end: string; worked_hours: number; days_worked: number }
}

export interface MyAttendance {
  today: AttendanceToday & { events: { id: string; event_type: string; event_at: string }[] }
  month: { month_start: string; month_end: string; worked_hours: number; days_worked: number }
  recent: { id: string; event_type: string; event_at: string; note?: string | null }[]
}

// ── staff AI analysis ────────────────────────────────────────────────────────
export interface StaffAiAnalysis {
  staff: { id: string; name?: string | null; name_en?: string | null; rank?: string | null; unit_name?: string | null; is_mentor: boolean; is_audited_for_medication: boolean }
  explicit_skills: { skill: string; expiry_date?: string | null; days_left?: number | null; status: 'valid' | 'expiring' | 'expired'; score: number }[]
  implicit_skills: { skill: string; occurrences: number; score: number }[]
  skill_bars: { skill: string; explicit: number; implicit: number; occurrences: number; certified: boolean }[]
  gaps: { skill: string; kind: 'eligibility' | 'experience' | 'certificate'; detail: string }[]
  recommended_training: { title: string; reason: string; priority: string }[]
  events: { date: string; title: string; detail: string; skill: string }[]
  activity: {
    working_shifts: number
    hours: number
    night_shifts: number
    distinct_units: number
    tasks_performed: number
    emergency_covers: number
  }
  evidence_note: string
}
