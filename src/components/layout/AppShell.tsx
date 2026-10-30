'use client'
import { ReactNode, useEffect, useRef, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Sidebar } from './Sidebar'
import { TopNav } from './TopNav'
import { useAuth } from './AuthContext'
import {
  CHROMELESS, canOpenRoute, fallbackRoute, isGuardedRoute, routeFeature,
} from './navRoutes'
import { readPageViewPosition, savePageViewPosition } from './display-preferences'

function Splash() {
  return (
    <div className="flex h-screen items-center justify-center bg-gray-50">
      <div className="flex flex-col items-center gap-3">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-gray-200"
          style={{ borderTopColor: '#E8187A' }}
        />
        <div className="text-sm font-semibold" style={{ color: '#E8187A' }}>Emma AI</div>
      </div>
    </div>
  )
}

// Client shell: owns the auth gate. /login and the phone-sized /staff-app render
// bare - both bring their own chrome, so wrapping them in the desktop sidebar +
// top bar would frame a mobile screen inside admin navigation. Every route other
// than /login requires a signed-in session, else it redirects to /login.
//
// It also owns the RBAC route guard (spec 1.1). Filtering the sidebar hides the
// link; this stops the screen being reached by typing the URL. Neither is the
// security boundary - the API guards are - but a screen that paints and then
// fills with 403s is worse than one the user never reaches.
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { status, user } = useAuth()
  const isLogin = pathname === '/login'
  const bare = CHROMELESS.includes(pathname)

  // Fails closed. A guarded path with no matrix entry is refused rather than
  // shown: an unmapped screen is an unreviewed screen, and the cost of getting
  // that wrong is the whole bug class this guard exists to end.
  //
  // Accepted trade-off: `not-found` renders inside this layout, so an unknown URL
  // is also unmapped and gets bounced to the user's landing screen instead of a
  // 404 page. Redirecting a mistyped path is a smaller harm than publishing an
  // unreviewed management screen, and for a signed-in app it reads as ordinary.
  // If a real 404 page is wanted later, add its path to REDIRECTORS.
  const guarded = isGuardedRoute(pathname)
  const feature = guarded ? routeFeature(pathname) : undefined
  const forbidden =
    status === 'authed' && guarded &&
    (feature === undefined || !canOpenRoute(user?.role, feature))

  useEffect(() => {
    if (status === 'anon' && !isLogin) router.replace('/login')
    if (status === 'authed' && isLogin) router.replace(fallbackRoute(user?.role))
    if (forbidden) router.replace(fallbackRoute(user?.role))
  }, [status, isLogin, forbidden, user?.role, router])

  if (isLogin) {
    // Already signed in and sitting on /login → we're about to bounce to the app.
    return status === 'authed' ? <Splash /> : <>{children}</>
  }

  if (status !== 'authed') return <Splash />

  // Hold the splash rather than paint a screen we are leaving.
  if (forbidden) return <Splash />

  if (bare) return <>{children}</>

  return (
    <ResponsiveShell>
      {children}
    </ResponsiveShell>
  )
}

function ResponsiveShell({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const pathname = usePathname()
  const mainRef = useRef<HTMLElement>(null)

  // Close sidebar on navigation.
  useEffect(() => { setSidebarOpen(false) }, [pathname])

  // Store only validated, numeric UI scroll offsets keyed by route. The helper
  // deliberately has no knowledge of user/account state or page/API data.
  useEffect(() => {
    const main = mainRef.current
    if (!main || !pathname) return

    const saved = readPageViewPosition(pathname)
    const restoreFrame = window.requestAnimationFrame(() => {
      if (!saved) return
      const maxTop = Math.max(0, main.scrollHeight - main.clientHeight)
      const maxLeft = Math.max(0, main.scrollWidth - main.clientWidth)
      if (saved.top <= maxTop && saved.left <= maxLeft) {
        main.scrollTo({ top: saved.top, left: saved.left, behavior: 'auto' })
      }
    })

    let saveTimer: number | undefined
    const save = () => {
      saveTimer = undefined
      savePageViewPosition(pathname, { top: main.scrollTop, left: main.scrollLeft })
    }
    const scheduleSave = () => {
      if (saveTimer !== undefined) return
      saveTimer = window.setTimeout(save, 120)
    }

    main.addEventListener('scroll', scheduleSave, { passive: true })
    window.addEventListener('pagehide', save)
    return () => {
      window.cancelAnimationFrame(restoreFrame)
      if (saveTimer !== undefined) window.clearTimeout(saveTimer)
      save()
      main.removeEventListener('scroll', scheduleSave)
      window.removeEventListener('pagehide', save)
    }
  }, [pathname])

  return (
    <div className="emma-manager-shell flex h-[100dvh] overflow-hidden bg-gray-50">
      {/* Desktop sidebar - hidden on mobile */}
      <div className="hidden md:block">
        <Sidebar />
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <>
          <button
            className="fixed inset-0 z-40 bg-black/30 md:hidden"
            aria-label="Close menu"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="fixed inset-y-0 left-0 z-50 md:hidden animate-in slide-in-from-left duration-200">
            <Sidebar onNavigate={() => setSidebarOpen(false)} />
          </div>
        </>
      )}

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <TopNav onMenuToggle={() => setSidebarOpen(o => !o)} />
        <main ref={mainRef} className="emma-scroll-main min-h-0 min-w-0 flex-1 overflow-x-auto overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}
