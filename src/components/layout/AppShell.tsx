'use client'
import { ReactNode, useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Sidebar } from './Sidebar'
import { TopNav } from './TopNav'
import { useAuth } from './AuthContext'
import { CHROMELESS } from './navRoutes'

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
// bare — both bring their own chrome, so wrapping them in the desktop sidebar +
// top bar would frame a mobile screen inside admin navigation. Every route other
// than /login requires a signed-in session, else it redirects to /login.
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { status } = useAuth()
  const isLogin = pathname === '/login'
  const bare = CHROMELESS.includes(pathname)

  useEffect(() => {
    if (status === 'anon' && !isLogin) router.replace('/login')
    if (status === 'authed' && isLogin) router.replace('/dashboard')
  }, [status, isLogin, router])

  if (isLogin) {
    // Already signed in and sitting on /login → we're about to bounce to the app.
    return status === 'authed' ? <Splash /> : <>{children}</>
  }

  if (status !== 'authed') return <Splash />

  if (bare) return <>{children}</>

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <TopNav />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}
