'use client'
import { useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'
import { ROUTES, activeItem } from '@/components/layout/navRoutes'

const PINK = '#f28f9e'

const TABS = [
  { key: 'topnav_roster',     path: ROUTES.roster     },
  { key: 'topnav_scheduling', path: ROUTES.scheduling },
  { key: 'topnav_staffing',   path: ROUTES.staff      },
  { key: 'topnav_compliance', path: ROUTES.compliance },
  { key: 'topnav_reports',    path: ROUTES.reports    },
]

export function TopNav() {
  const [search, setSearch]   = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const { lang, setLang, t }  = useLang()
  const { user, signOut } = useAuth()
  const isZH = lang === 'zh'

  // Derived from the URL, not click state: arriving from the sidebar, a deep link
  // or the back button all light the same tab. Screens with no tab (dashboard,
  // ROI, alerts, approval) simply highlight nothing.
  const active = activeItem(TABS, pathname)?.key

  // 'A' / 'B' from "Care Home A (…)", else first letter of the email.
  const avatarLetter =
    user?.facilityName?.match(/Home\s*([A-Za-z0-9])/)?.[1]?.toUpperCase()
    ?? user?.email?.charAt(0).toUpperCase()
    ?? 'U'

  return (
    <header
      className="h-12 flex items-center px-4 gap-4 border-b flex-shrink-0"
      style={{ background: '#ffffff', borderColor: '#f3f4f6' }}
    >
      {/* Tab nav */}
      <nav className="flex items-center gap-1">
        {TABS.map(({ key, path }) => (
          <button
            key={key}
            onClick={() => router.push(path)}
            className="px-3 py-1.5 rounded text-xs font-medium transition-all"
            style={{
              color:      active === key ? PINK : '#6b7280',
              background: active === key ? '#fdf2f4' : 'transparent',
            }}
            onMouseEnter={e => { if (active !== key) e.currentTarget.style.background = '#f9fafb' }}
            onMouseLeave={e => { if (active !== key) e.currentTarget.style.background = 'transparent' }}
          >
            {t(key)}
          </button>
        ))}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Search */}
      <div className="relative">
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t('search_ph')}
          className="pl-7 pr-3 py-1.5 rounded-lg border text-xs focus:outline-none focus:ring-1 w-44"
          style={{ borderColor: '#e5e7eb', background: '#f9fafb' }}
        />
      </div>

      {/* Lang toggle */}
      <button
        onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
        className="px-2.5 py-1 rounded text-xs font-medium border transition-all"
        style={{ borderColor: PINK, color: PINK, background: '#fff5f7' }}
        onMouseEnter={e => (e.currentTarget.style.background = '#fce7eb')}
        onMouseLeave={e => (e.currentTarget.style.background = '#fff5f7')}
      >
        {lang === 'zh' ? 'EN' : '中'}
      </button>

      {/* Notifications */}
      <div className="relative cursor-pointer">
        <span className="text-gray-400">🔔</span>
        <span
          className="absolute -top-1 -right-1 text-[8px] text-white rounded-full w-3.5 h-3.5 flex items-center justify-center"
          style={{ background: PINK }}
        >3</span>
      </div>

      {/* Account */}
      <div className="relative">
        <button
          onClick={() => setMenuOpen(o => !o)}
          className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-full hover:bg-gray-50 transition-colors"
        >
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-semibold"
            style={{ background: PINK }}
          >
            {avatarLetter}
          </div>
          <div className="hidden sm:block text-left leading-tight max-w-[150px]">
            <div className="text-[11px] font-semibold text-gray-800 truncate">
              {user?.facilityName ?? '—'}
            </div>
            <div className="text-[9px] text-gray-400 truncate">
              {roleLabel(user?.role, isZH) || user?.email}
            </div>
          </div>
          <span className="text-gray-400 text-[10px]">▾</span>
        </button>

        {menuOpen && (
          <>
            <button
              className="fixed inset-0 z-40 cursor-default"
              aria-hidden
              onClick={() => setMenuOpen(false)}
            />
            <div className="absolute right-0 top-full mt-1 w-60 rounded-xl border border-gray-200 bg-white shadow-lg z-50 p-1">
              <div className="px-3 py-2">
                <div className="text-[10px] text-gray-400">{isZH ? '已登入' : 'Signed in as'}</div>
                <div className="text-xs font-semibold text-gray-800 truncate">{user?.email ?? '—'}</div>
                <div className="text-[10px] text-gray-500 mt-0.5 truncate">
                  {user?.facilityName}{user?.role ? ` · ${roleLabel(user.role, isZH)}` : ''}
                </div>
              </div>
              <div className="h-px bg-gray-100 my-1" />
              <button
                onClick={() => { setMenuOpen(false); signOut() }}
                className="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                {isZH ? '切換帳戶 / 登出' : 'Switch account / Sign out'}
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  )
}