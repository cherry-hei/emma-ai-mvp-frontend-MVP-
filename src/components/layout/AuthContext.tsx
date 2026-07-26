'use client'
import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { api, login as apiLogin, logout as apiLogout, getToken, getSession, onUnauthorized } from '@/lib/api'

export interface AuthUser {
  userId: string
  email: string | null
  role: string | null
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
  const router = useRouter()

  // Let the API layer hard-drop us to /login when a session dies mid-use (a 401 that
  // even a token refresh can't rescue), from any page, not just on the next mount.
  useEffect(() => {
    onUnauthorized(() => {
      setUser(null)
      setStatus('anon')
      router.replace('/login')
    })
    return () => onUnauthorized(null)
  }, [router])

  // On mount: if a token is stored, optimistically restore the cached session for
  // an instant header, then verify it against /auth/me (source of truth). A dead or
  // expired token clears itself and drops us to the signed-out state.
  useEffect(() => {
    let cancelled = false

    async function hydrate() {
      const token = getToken()
      if (!token) {
        if (!cancelled) setStatus('anon')
        return
      }
      // Optimistic paint from the cached snapshot while /auth/me verifies.
      const snap = getSession()
      if (snap && !cancelled) {
        setUser({
          userId: snap.user_id, email: snap.email, role: snap.role,
          facilityId: snap.facility_id, facilityName: snap.facility_name,
        })
      }
      try {
        const p = await api.me()
        if (cancelled) return
        setUser({
          userId: p.auth_user_id ?? p.id,
          email: p.email ?? null,
          role: p.role ?? null,
          facilityId: p.facility_id ?? null,
          facilityName: p.facility?.name ?? null,
        })
        setStatus('authed')
      } catch {
        if (cancelled) return
        apiLogout()
        setUser(null)
        setStatus('anon')
      }
    }

    hydrate()
    return () => { cancelled = true }
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const s = await apiLogin(email, password)
    setUser({
      userId: s.user_id, email: s.email ?? null, role: s.role ?? null,
      facilityId: s.facility_id ?? null, facilityName: s.facility_name ?? null,
    })
    setStatus('authed')
  }, [])

  const signOut = useCallback(() => {
    apiLogout()
    setUser(null)
    setStatus('anon')
    router.replace('/login')
  }, [router])

  return <Ctx.Provider value={{ status, user, signIn, signOut }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)

const ROLE_LABELS: Record<string, { en: string; zh: string }> = {
  superintendent: { en: 'Superintendent', zh: '院長' },
  admin:          { en: 'Admin',          zh: '管理員' },
  staff:          { en: 'Staff',          zh: '員工' },
  scheduler:      { en: 'Scheduler',      zh: '排更員' },
  hr:             { en: 'HR',             zh: '人事' },
  auditor:        { en: 'Auditor',        zh: '審計' },
}

export function roleLabel(role: string | null | undefined, isZH: boolean): string {
  if (!role) return ''
  return ROLE_LABELS[role]?.[isZH ? 'zh' : 'en'] ?? role
}
