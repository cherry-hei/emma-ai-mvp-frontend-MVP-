// src/lib/api.ts
// Thin typed client for the Emma AI FastAPI backend.
//
// Base URL: NEXT_PUBLIC_API_URL (default http://localhost:8000).
// Auth: every endpoint except /auth/login and /auth/refresh needs a bearer token.
// Sign-in is owned by the /login screen (see AuthContext) via login(). The access
// token is short-lived, so apiFetch transparently swaps the refresh token for a new
// session on a 401 and replays the request once; if that fails it hard-logs-out and
// signals AuthContext to route to /login. Tokens live in localStorage — for a
// higher-security posture, move auth to a server-side BFF with httpOnly cookies.
import type {
  AlertItem, ApiError, ApiStaff, CompareOptionsResponse, CreatePeriodResponse,
  DashboardSummary, EventTrigger, FacilityEvent, FutureDebtRow, GeneratedReport, Incident,
  IncidentStats, JobView, LeaveCategory, LeaveGroup, LeaveRequest, LeaveStats,
  MyAttendance, MyProfile, MyRoster, MySummary, MyTask, OptimizeResponse, PeriodOut,
  Profile, RatioResult, RegulatoryDoc, ReplacementCandidate, ReportRow,
  ReportSchedule, ReportType, ResidentCountOut, RoiSettings, RoiSummary, RosterGrid,
  RosterOption, SessionOut, ShiftDef, StaffAiAnalysis, StaffDetail, TaskAssignment, TaskDefOut,
  ThresholdMonitor, Unit, ValidationOut, VersionOut,
} from './apiTypes'

const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '')
const TOKEN_KEY = 'emma_token'
const REFRESH_KEY = 'emma_refresh'
const SESSION_KEY = 'emma_session'

// Lightweight session snapshot persisted next to the token so the app shell
// (facility name / role / email in the header) can paint instantly on reload,
// before the /auth/me round-trip returns.
export interface StoredSession {
  user_id: string
  email: string | null
  role: string | null
  facility_id: string | null
  facility_name: string | null
}

let cachedToken: string | null = null

function readToken(): string | null {
  if (cachedToken) return cachedToken
  if (typeof window !== 'undefined') cachedToken = window.localStorage.getItem(TOKEN_KEY)
  return cachedToken
}

function writeToken(t: string | null): void {
  cachedToken = t
  if (typeof window !== 'undefined') {
    if (t) window.localStorage.setItem(TOKEN_KEY, t)
    else window.localStorage.removeItem(TOKEN_KEY)
  }
}

function readRefresh(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem(REFRESH_KEY) : null
}

function writeRefresh(t: string | null): void {
  if (typeof window === 'undefined') return
  if (t) window.localStorage.setItem(REFRESH_KEY, t)
  else window.localStorage.removeItem(REFRESH_KEY)
}

function writeSession(s: SessionOut | null): void {
  if (typeof window === 'undefined') return
  if (s) {
    const snap: StoredSession = {
      user_id: s.user_id, email: s.email ?? null, role: s.role ?? null,
      facility_id: s.facility_id ?? null, facility_name: s.facility_name ?? null,
    }
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(snap))
  } else {
    window.localStorage.removeItem(SESSION_KEY)
  }
}

export function getSession(): StoredSession | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as StoredSession) : null
  } catch {
    return null
  }
}

export function getToken(): string | null {
  return readToken()
}

export function logout(): void {
  writeToken(null)
  writeSession(null)
  writeRefresh(null)
}

async function toError(res: Response): Promise<Error> {
  let msg = `${res.status} ${res.statusText}`
  try {
    const body = (await res.json()) as ApiError
    const d = body.detail
    msg = typeof d === 'string' ? d : d?.message || msg
  } catch {
    /* non-JSON body */
  }
  return new Error(msg)
}

export async function login(email: string, password: string): Promise<SessionOut> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw await toError(res)
  const session = (await res.json()) as SessionOut
  writeToken(session.access_token)
  writeSession(session)
  writeRefresh(session.refresh_token ?? null)
  return session
}

// The bearer token for the current user, or null when signed out. Sign-in is owned
// by the /login screen (see AuthContext) — there is no implicit env auto-login, so
// switching facility means signing out and back in as a different account.
async function ensureToken(): Promise<string | null> {
  return readToken()
}

// AuthContext registers a callback here so a dead session (refresh exhausted) can
// drop the app to /login from anywhere, not only on the next mount.
let unauthorizedHandler: (() => void) | null = null
export function onUnauthorized(fn: (() => void) | null): void {
  unauthorizedHandler = fn
}

// Swap the stored refresh token for a fresh session. De-duplicated so a burst of
// parallel 401s triggers only one refresh. Resolves to the new access token, or
// null when there is no refresh token or it has expired.
let refreshInFlight: Promise<string | null> | null = null
function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async (): Promise<string | null> => {
    const rt = readRefresh()
    if (!rt) return null
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      })
      if (!res.ok) throw new Error('refresh failed')
      const session = (await res.json()) as SessionOut
      writeToken(session.access_token)
      writeSession(session)
      writeRefresh(session.refresh_token ?? null)
      return session.access_token
    } catch {
      return null
    }
  })().finally(() => { refreshInFlight = null })
  return refreshInFlight
}

export async function apiFetch<T>(path: string, opts: RequestInit = {}, retry = true): Promise<T> {
  const token = await ensureToken()
  const headers = new Headers(opts.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (opts.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  const res = await fetch(`${BASE}${path}`, { ...opts, headers })

  if (res.status === 401) {
    // One silent refresh attempt; if it yields a new token, replay the request once.
    if (retry) {
      const fresh = await refreshAccessToken()
      if (fresh) return apiFetch<T>(path, opts, false)
    }
    logout()
    unauthorizedHandler?.()
    throw await toError(res)
  }

  if (!res.ok) throw await toError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// ── typed endpoint helpers ───────────────────────────────────────────────────
export const api = {
  me: () => apiFetch<Profile>('/auth/me'),

  listStaff: (params?: { search?: string; rank?: string }) => {
    const q = new URLSearchParams()
    if (params?.search) q.set('search', params.search)
    if (params?.rank && params.rank !== 'ALL') q.set('rank', params.rank)
    const qs = q.toString()
    return apiFetch<ApiStaff[]>(`/staff${qs ? `?${qs}` : ''}`)
  },

  staffDetail: (id: string) => apiFetch<StaffDetail>(`/staff/${id}`),

  publish: (versionId: string) =>
    apiFetch<{ roster_version_id: string; status: string }>(
      `/rosters/${versionId}/publish`, { method: 'POST' }),

  rosterPeriods: () => apiFetch<PeriodOut[]>('/roster-periods'),

  rosterVersions: (periodId?: string) =>
    apiFetch<VersionOut[]>(`/roster-versions${periodId ? `?period_id=${periodId}` : ''}`),

  rosterGrid: (periodId: string, opts?: { versionId?: string }) =>
    apiFetch<RosterGrid>(`/rosters/${periodId}${opts?.versionId ? `?version_id=${opts.versionId}` : ''}`),

  // ── period + manual editing + publish workflow ──────────────────────────────
  createPeriod: (body: {
    period_start: string; period_end: string; cycle_type?: string; create_manual_version?: boolean
  }) => apiFetch<CreatePeriodResponse>('/roster-periods', { method: 'POST', body: JSON.stringify(body) }),

  shiftDefinitions: () => apiFetch<ShiftDef[]>('/shift-definitions'),
  taskDefinitions: () => apiFetch<TaskDefOut[]>('/task-definitions'),

  taskAssignments: (params?: { rosterVersionId?: string; shiftAssignmentId?: string }) => {
    const q = new URLSearchParams()
    if (params?.rosterVersionId) q.set('roster_version_id', params.rosterVersionId)
    if (params?.shiftAssignmentId) q.set('shift_assignment_id', params.shiftAssignmentId)
    return apiFetch<TaskAssignment[]>(`/task-assignments${q.size ? `?${q.toString()}` : ''}`)
  },

  createTaskAssignment: (body: {
    shift_assignment_id: string; task_id: string; start_at?: string; end_at?: string; source_type?: string
  }) => apiFetch<TaskAssignment>('/task-assignments', {
    method: 'POST', body: JSON.stringify(body),
  }),

  updateTaskAssignment: (id: string, body: {
    task_id?: string; start_at?: string | null; end_at?: string | null; source_type?: string
  }) => apiFetch<TaskAssignment>(`/task-assignments/${id}`, {
    method: 'PATCH', body: JSON.stringify(body),
  }),

  deleteTaskAssignment: (id: string) =>
    apiFetch<void>(`/task-assignments/${id}`, { method: 'DELETE' }),

  facilityEvents: (params?: { dateFrom?: string; dateTo?: string }) => {
    const q = new URLSearchParams()
    if (params?.dateFrom) q.set('date_from', params.dateFrom)
    if (params?.dateTo) q.set('date_to', params.dateTo)
    return apiFetch<FacilityEvent[]>(`/facility-events${q.size ? `?${q.toString()}` : ''}`)
  },

  createFacilityEvent: (body: {
    event_type: string; event_date: string; start_at?: string; end_at?: string
    unit_id?: string; title?: string; notes?: string
    staffing_requirements?: Array<{ rank: string; count: number; is_additive?: boolean; notes?: string }>
  }) => apiFetch<FacilityEvent>('/facility-events', {
    method: 'POST', body: JSON.stringify(body),
  }),

  updateFacilityEvent: (id: string, body: Partial<{
    event_type: string; event_date: string; start_at: string | null; end_at: string | null
    unit_id: string | null; title: string | null; notes: string | null
    staffing_requirements: Array<{ rank: string; count: number; is_additive?: boolean; notes?: string }>
  }>) => apiFetch<FacilityEvent>(`/facility-events/${id}`, {
    method: 'PATCH', body: JSON.stringify(body),
  }),

  deleteFacilityEvent: (id: string) =>
    apiFetch<void>(`/facility-events/${id}`, { method: 'DELETE' }),

  // POST and PATCH /shifts share the same upsert-cell behavior on the backend.
  upsertCell: (body: {
    roster_version_id: string; staff_id: string; date: string; shift_type: string; tasks?: string[]
  }) => apiFetch<{ assignment_id: string }>('/shifts', { method: 'PATCH', body: JSON.stringify(body) }),

  clearCell: (versionId: string, staffId: string, date: string) => {
    const q = new URLSearchParams({ roster_version_id: versionId, staff_id: staffId, date })
    return apiFetch<void>(`/shifts?${q.toString()}`, { method: 'DELETE' })
  },

  saveDraft: (versionId: string) =>
    apiFetch<{ ok: boolean }>(`/rosters/${versionId}/save-draft`, { method: 'POST' }),

  validateRoster: (versionId: string) =>
    apiFetch<ValidationOut>('/validate-roster', {
      method: 'POST', body: JSON.stringify({ roster_version_id: versionId }),
    }),

  compareOptions: (periodId: string) =>
    apiFetch<CompareOptionsResponse>(`/roster-option-scores/compare/${periodId}`),

  complianceRatio: (date: string, versionId?: string) => {
    const q = new URLSearchParams({ date })
    if (versionId) q.set('roster_version_id', versionId)
    return apiFetch<RatioResult[]>(`/compliance/ratio?${q.toString()}`)
  },

  units: () => apiFetch<Unit[]>('/units'),

  residentCounts: (date?: string) =>
    apiFetch<ResidentCountOut[]>(`/resident-counts${date ? `?date=${date}` : ''}`),

  setResidentCount: (body: { date: string; unit_id: string; care_level?: string; count: number }) =>
    apiFetch<{ ok: boolean }>('/resident-counts', { method: 'POST', body: JSON.stringify(body) }),

  // Async solve — returns a pending job_id; poll job() until status === 'completed'.
  optimizeRoster: (body: { period_id: string; plan_mode?: string; source_version_id?: string }) =>
    apiFetch<OptimizeResponse>('/optimize-roster', {
      method: 'POST',
      body: JSON.stringify({ facility_id: '', ...body }), // facility_id is overridden from the token
    }),

  job: (jobId: string) => apiFetch<JobView>(`/optimization-jobs/${jobId}`),

  // ── Phase 3 · approval centre ───────────────────────────────────────────────
  leaveRequests: (params?: {
    group?: LeaveGroup; category?: LeaveCategory; search?: string
    unitId?: string; dateFrom?: string; dateTo?: string; staffId?: string
  }) => {
    const q = new URLSearchParams()
    if (params?.group) q.set('group', params.group)
    if (params?.category) q.set('category', params.category)
    if (params?.search) q.set('search', params.search)
    if (params?.unitId) q.set('unit_id', params.unitId)
    if (params?.dateFrom) q.set('date_from', params.dateFrom)
    if (params?.dateTo) q.set('date_to', params.dateTo)
    if (params?.staffId) q.set('staff_id', params.staffId)
    const qs = q.toString()
    return apiFetch<LeaveRequest[]>(`/leave-requests${qs ? `?${qs}` : ''}`)
  },

  leaveStats: () => apiFetch<LeaveStats>('/leave-requests/stats'),

  createLeaveRequest: (body: {
    staff_id?: string; leave_type: string; date_start: string; date_end: string
    reason?: string; remark?: string; requested_shift_type?: string; document_url?: string
  }) => apiFetch<LeaveRequest>('/leave-requests', {
    method: 'POST', body: JSON.stringify(body),
  }),

  decideLeaveRequest: (id: string, decision: 'approve' | 'reject' | 'review', note?: string) =>
    apiFetch<LeaveRequest>(`/leave-requests/${id}`, {
      method: 'PATCH', body: JSON.stringify({ decision, note }),
    }),

  // ── Phase 3 · alert centre + emergency cover ────────────────────────────────
  incidents: (params?: { status?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set('status', params.status)
    if (params?.limit) q.set('limit', String(params.limit))
    const qs = q.toString()
    return apiFetch<Incident[]>(`/sl-incidents${qs ? `?${qs}` : ''}`)
  },

  incidentStats: () => apiFetch<IncidentStats>('/sl-incidents/stats'),

  createIncident: (body: {
    staff_id?: string; incident_type?: string; date?: string; reason?: string; shift_id?: string
  }) => apiFetch<{ id: string }>('/sl-incidents', { method: 'POST', body: JSON.stringify(body) }),

  // compliance_checked=false also returns blocked candidates, with their reasons.
  replacementCandidates: (incidentId: string, opts?: { complianceChecked?: boolean; refresh?: boolean }) => {
    const q = new URLSearchParams({ incident_id: incidentId })
    if (opts?.complianceChecked === false) q.set('compliance_checked', 'false')
    if (opts?.refresh) q.set('refresh', 'true')
    return apiFetch<ReplacementCandidate[]>(`/replacement-candidates?${q.toString()}`)
  },

  resolveIncident: (incidentId: string, body: {
    replacement_staff_id: string; auto?: boolean; note?: string
  }) => apiFetch<{ resolution_minutes: number; future_debt: { quantity: number } | null }>(
    `/sl-incidents/${incidentId}/resolve`, { method: 'POST', body: JSON.stringify(body) }),

  alerts: () => apiFetch<AlertItem[]>('/alerts'),

  futureDebt: () => apiFetch<FutureDebtRow[]>('/future-debt'),

  // ── Phase 3 · dashboard, ROI, compliance monitors ───────────────────────────
  dashboard: () => apiFetch<DashboardSummary>('/dashboard/summary'),

  roiSummary: () => apiFetch<RoiSummary>('/roi/summary'),
  roiSettings: () => apiFetch<RoiSettings>('/roi/settings'),
  saveRoiSettings: (patch: Partial<RoiSettings>) =>
    apiFetch<RoiSettings>('/roi/settings', { method: 'PUT', body: JSON.stringify(patch) }),

  thresholds: () => apiFetch<ThresholdMonitor[]>('/compliance/thresholds'),

  // ── Phase 3 · reports ───────────────────────────────────────────────────────
  reportSchedules: () => apiFetch<ReportSchedule[]>('/reports/schedules'),
  reportTypes: () => apiFetch<ReportType[]>('/reports/types'),
  eventTriggers: () => apiFetch<EventTrigger[]>('/reports/event-triggers'),
  regulatoryDocs: () => apiFetch<RegulatoryDoc[]>('/reports/regulatory-docs'),
  reports: () => apiFetch<ReportRow[]>('/reports'),
  generateReport: (reportType: string) =>
    apiFetch<GeneratedReport>('/reports/generate', {
      method: 'POST', body: JSON.stringify({ report_type: reportType }),
    }),
  runReportSchedule: (scheduleId: string) =>
    apiFetch<GeneratedReport>(`/reports/schedules/${scheduleId}/run`, { method: 'POST' }),

  // ── Phase 3 · staff app (always the caller's own records) ───────────────────
  mySummary: () => apiFetch<MySummary>('/me/summary'),
  myRoster: (days = 7) => apiFetch<MyRoster>(`/me/roster?days=${days}`),
  myProfile: () => apiFetch<MyProfile>('/me/profile'),
  myTasks: (date?: string) => apiFetch<MyTask[]>(`/me/tasks${date ? `?date=${date}` : ''}`),
  setTaskStatus: (taskId: string, status: 'pending' | 'done') =>
    apiFetch<MyTask>(`/me/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  myAttendance: () => apiFetch<MyAttendance>('/me/attendance'),
  clock: (eventType: 'clock_in' | 'clock_out') =>
    apiFetch<{ id: string; event_at: string }>('/me/attendance/clock', {
      method: 'POST', body: JSON.stringify({ event_type: eventType }),
    }),

  // ── Phase 3 · staff AI analysis ─────────────────────────────────────────────
  staffAiAnalysis: (staffId: string) =>
    apiFetch<StaffAiAnalysis>(`/staff/${staffId}/ai-analysis`),
}

/** Download a generated report as CSV without leaving the page. */
export async function downloadReportCsv(reportType: string): Promise<void> {
  const token = getToken()
  const res = await fetch(`${BASE}/reports/download/${reportType}.csv`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw await toError(res)
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = `${reportType}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// Enqueue an A/B/C solve and poll the job until it finishes; returns the options.
export async function optimizeAndPoll(
  periodId: string,
  opts: { onStatus?: (s: string) => void; intervalMs?: number; timeoutMs?: number; sourceVersionId?: string } = {},
): Promise<RosterOption[]> {
  const { onStatus, intervalMs = 1500, timeoutMs = 120_000, sourceVersionId } = opts
  const { job_id } = await api.optimizeRoster({ period_id: periodId, source_version_id: sourceVersionId })
  onStatus?.('pending')
  const deadline = Date.now() + timeoutMs
  let transientFails = 0
  for (;;) {
    await new Promise((r) => setTimeout(r, intervalMs))
    if (Date.now() > deadline) throw new Error('optimization timed out')
    let job: JobView
    try {
      job = await api.job(job_id)
      transientFails = 0
    } catch (e) {
      // tolerate a few transient poll failures (network blip) before giving up
      if (++transientFails >= 3) throw e
      continue
    }
    onStatus?.(job.status)
    if (job.status === 'completed') return job.result_json?.roster_options ?? []
    if (job.status === 'failed') {
      throw new Error((job.error_json as { message?: string } | null)?.message || 'optimization failed')
    }
  }
}

