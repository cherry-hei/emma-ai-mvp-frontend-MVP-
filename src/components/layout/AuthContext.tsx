'use client'
import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { api, login as apiLogin, logout as apiLogout, getToken, getSession, onUnauthorized, onSessionRefreshed, rememberVerifiedProfile } from '@/lib/api'
import { normaliseRole, type PermissionSubject } from '@/lib/permissions'
import { readCareWorkflow, type CareWorkflow } from '@/lib/care-workflow'

export interface AuthUser {
  userId: string
  email: string | null
  role: string | null
  orgId: string | null
  staffId: string | null
  careWorkflow: CareWorkflow | null
  facilityId: string | null
  facilityName: string | null
}

type Status = 'loading' | 'authed' | 'anon'

interface AuthCtx {
  status: Status
  user: AuthUser | null
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => void
}

const Ctx = createContext<AuthCtx>({
  status: 'loading',
  user: null,
  signIn: async () => {},
  signOut: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)
  const actionGeneration = useRef(0)
  const router = useRouter()

  // Let the API layer hard-drop us to /login when a session dies mid-use (a 401 that
  // even a token refresh can't rescue), from any page, not just on the next mount.
  useEffect(() => {
    onUnauthorized(() => {
      actionGeneration.current += 1
      setUser(null)
      setStatus('anon')
      router.replace('/login')
    })
    return () => onUnauthorized(null)
  }, [router])

  useEffect(() => {
    onSessionRefreshed((session) => {
      actionGeneration.current += 1
      setUser({
        userId: session.user_id, email: session.email ?? null, role: session.role ?? null,
        orgId: session.org_id ?? null, facilityId: session.facility_id ?? null, staffId: session.staff_id ?? null,
        facilityName: session.facility_name ?? null,
        careWorkflow: readCareWorkflow(session.care_workflow, {
          orgId: session.org_id ?? null, facilityId: session.facility_id ?? null,
        }),
      })
      setStatus('authed')
    })
    return () => onSessionRefreshed(null)
  }, [])

  // On mount: if a token is stored, optimistically restore the cached session for
  // an instant header, then verify it against /auth/me (source of truth). A dead or
  // expired token clears itself and drops us to the signed-out state.
  useEffect(() => {
    let cancelled = false
    const hydrateGeneration = actionGeneration.current

    async function hydrate() {
      const token = getToken()
      if (!token) {
        if (!cancelled) setStatus('anon')
        return
      }
      // Optimistic paint from the cached snapshot while /auth/me verifies.
      const snap = getSession()
      if (snap && !cancelled && actionGeneration.current === hydrateGeneration) {
        setUser({
          userId: snap.user_id, email: snap.email, role: snap.role,
          facilityId: snap.facility_id, facilityName: snap.facility_name,
          orgId: null, staffId: null, careWorkflow: null,
        })
      }
      try {
        const p = await api.me()
        if (cancelled || actionGeneration.current !== hydrateGeneration) return
        rememberVerifiedProfile(p)
        setUser({
          userId: p.auth_user_id ?? p.id,
          email: p.email ?? null,
          role: p.role ?? null,
          orgId: p.org_id ?? null,
          staffId: p.staff_id ?? null,
          careWorkflow: readCareWorkflow(p.care_workflow, { orgId: p.org_id ?? null, facilityId: p.facility_id ?? null }),
          facilityId: p.facility_id ?? null,
          facilityName: p.facility?.name ?? null,
        })
        setStatus('authed')
      } catch {
        if (cancelled || actionGeneration.current !== hydrateGeneration) return
        apiLogout()
        setUser(null)
        setStatus('anon')
      }
    }

    hydrate()
    return () => { cancelled = true }
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const signInGeneration = ++actionGeneration.current
    const s = await apiLogin(email, password)
    if (actionGeneration.current !== signInGeneration) {
      throw new Error('Sign-in was superseded by a newer session action.')
    }
    setUser({
      userId: s.user_id, email: s.email ?? null, role: s.role ?? null,
      facilityId: s.facility_id ?? null, facilityName: s.facility_name ?? null,
      orgId: s.org_id ?? null,
      staffId: s.staff_id ?? null,
      careWorkflow: readCareWorkflow(s.care_workflow, { orgId: s.org_id ?? null, facilityId: s.facility_id ?? null }),
    })
    setStatus('authed')
  }, [])

  const signOut = useCallback(() => {
    actionGeneration.current += 1
    apiLogout()
    setUser(null)
    setStatus('anon')
    router.replace('/login')
  }, [router])

  return <Ctx.Provider value={{ status, user, signIn, signOut }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)

// Legacy labels remain for pure role consumers. Authenticated screens use the
// server's reviewed SA/NAAC appointment label, including NAAC deputy versus 主任.
const ROLE_LABELS: Record<string, { en: string; zh: string }> = {
  OWNER:         { en: 'Superintendent',   zh: '院長' },
  NURSE_MGR:     { en: 'Nursing Officer',  zh: '護理主任' },
  ALLIED_HEALTH: { en: 'Allied Health',    zh: '治療師' },
  ADMIN_CLERK:   { en: 'Admin Clerk',      zh: '文員' },
  SCHEDULER:     { en: 'Scheduler',        zh: '排更員' },
  FRONTLINE:     { en: 'Staff',            zh: '員工' },
  HR_AUDITOR:    { en: 'HR / Audit',       zh: '人事及審計' },
}

export function roleLabel(role: PermissionSubject, isZH: boolean): string {
  if (role && typeof role === 'object') {
    return role.careWorkflow?.status === 'ready'
      ? role.careWorkflow.role_label[isZH ? 'zh' : 'en'] : ''
  }
  const resolved = normaliseRole(role)
  if (!resolved) return ''
  return ROLE_LABELS[resolved][isZH ? 'zh' : 'en']
}
