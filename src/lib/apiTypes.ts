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
  scheduled_hours: number             // rostered working hours this period
  contracted_period_hours: number     // weekly contract scaled to the period
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

export interface ApiError {
  detail: { code: string; message: string } | string
}
