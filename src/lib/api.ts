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
  ApiError, ApiStaff, CompareOptionsResponse, CreatePeriodResponse, JobView,
  OptimizeResponse, PeriodOut, Profile, RatioResult, ResidentCountOut, RosterGrid,
  RosterOption, SessionOut, ShiftDef, StaffDetail, TaskDefOut, Unit, ValidationOut,
  VersionOut,
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

