// src/lib/api.ts
// Thin typed client for the Emma AI FastAPI backend.
//
// Base URL: NEXT_PUBLIC_API_URL (default http://localhost:8000).
// Auth: every endpoint (except /auth/login) needs a bearer token. For LOCAL dev
// you can set NEXT_PUBLIC_DEV_EMAIL / NEXT_PUBLIC_DEV_PASSWORD in .env.local to a
// seeded account and calls auto-authenticate. In production, build a real login
// screen on top of login()/logout() (or move auth to a server-side BFF) — do not
// ship credentials in NEXT_PUBLIC_* vars.
import type {
  ApiError, ApiStaff, JobView, OptimizeResponse, PeriodOut, Profile,
  RatioResult, RosterGrid, SessionOut, VersionOut,
} from './apiTypes'

const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '')
const TOKEN_KEY = 'emma_token'

let cachedToken: string | null = null
let loginInFlight: Promise<string | null> | null = null

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

export function getToken(): string | null {
  return readToken()
}

export function logout(): void {
  writeToken(null)
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
  return session
}

async function ensureToken(): Promise<string | null> {
  const existing = readToken()
  if (existing) return existing
  const email = process.env.NEXT_PUBLIC_DEV_EMAIL
  const password = process.env.NEXT_PUBLIC_DEV_PASSWORD
  if (!email || !password) return null
  if (!loginInFlight) {
    loginInFlight = login(email, password)
      .then((s) => s.access_token)
      .catch(() => null)
      .finally(() => {
        loginInFlight = null
      })
  }
  return loginInFlight
}

export async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = await ensureToken()
  const headers = new Headers(opts.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (opts.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  const res = await fetch(`${BASE}${path}`, { ...opts, headers })
  if (res.status === 401) writeToken(null)
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

  rosterPeriods: () => apiFetch<PeriodOut[]>('/roster-periods'),

  rosterVersions: (periodId?: string) =>
    apiFetch<VersionOut[]>(`/roster-versions${periodId ? `?period_id=${periodId}` : ''}`),

  rosterGrid: (periodId: string, opts?: { versionId?: string }) =>
    apiFetch<RosterGrid>(`/rosters/${periodId}${opts?.versionId ? `?version_id=${opts.versionId}` : ''}`),

  complianceRatio: (date: string, versionId?: string) => {
    const q = new URLSearchParams({ date })
    if (versionId) q.set('roster_version_id', versionId)
    return apiFetch<RatioResult[]>(`/compliance/ratio?${q.toString()}`)
  },

  // Async solve — returns a pending job_id; poll job() until status === 'completed'.
  optimizeRoster: (body: { period_id: string; plan_mode?: string; source_version_id?: string }) =>
    apiFetch<OptimizeResponse>('/optimize-roster', {
      method: 'POST',
      body: JSON.stringify({ facility_id: '', ...body }), // facility_id is overridden from the token
    }),

  job: (jobId: string) => apiFetch<JobView>(`/optimization-jobs/${jobId}`),
}
