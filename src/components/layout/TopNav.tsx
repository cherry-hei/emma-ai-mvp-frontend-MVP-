'use client'
import { useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'
import { useDisplayPreferences, type TextSize } from '@/components/layout/DisplayPreferencesContext'
import { ROUTES, ROUTE_FEATURE, activeItem, canOpenRoute } from '@/components/layout/navRoutes'

const PINK = '#f28f9e'

// REMOVED for MVP: duplicate of sidebar navigation
const TABS: { key: string; path: string }[] = [
  // { key: 'topnav_roster',     path: ROUTES.roster     },
  // { key: 'topnav_scheduling', path: ROUTES.scheduling },
  // { key: 'topnav_staffing',   path: ROUTES.staff      },
  // { key: 'topnav_compliance', path: ROUTES.compliance },
  // { key: 'topnav_reports',    path: ROUTES.reports    },
]

export function TopNav({ onMenuToggle }: { onMenuToggle?: () => void } = {}) {
  const [search, setSearch]   = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const { lang, setLang, t }  = useLang()
  const { user, signOut } = useAuth()
  const { textSize, setTextSize, theme, setTheme } = useDisplayPreferences()
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
      className="h-12 flex items-center px-3 md:px-4 gap-2 md:gap-4 border-b border-border bg-card flex-shrink-0"
    >
      {/* Mobile hamburger */}
      <button
        onClick={onMenuToggle}
        className="md:hidden p-1.5 rounded-lg hover:bg-accent transition-colors"
        aria-label="Toggle menu"
      >
        <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

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

      {canOpenRoute(user?.role, ROUTE_FEATURE[ROUTES.insights]) && (
        <button
          onClick={() => router.push(ROUTES.insights)}
          aria-label="Open Emma AI"
          className={`flex min-h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-[10px] font-bold transition-all hover:-translate-y-px ${pathname?.startsWith(ROUTES.insights) ? 'border-pink-600 bg-pink-600 text-white' : 'border-pink-200 bg-pink-50 text-pink-700 dark:border-pink-700 dark:bg-pink-950/40 dark:text-pink-200'}`}
        >
          <img src="/icons/emma-badge.png" alt="" width={18} height={18} className="rounded-sm" />
          <span>Emma AI</span>
        </button>
      )}

      {/* Search */}
      <div className="relative hidden sm:block">
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-xs">🔍</span>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t('search_ph')}
          className="pl-7 pr-3 py-1.5 rounded-lg border text-xs focus:outline-none focus:ring-1 w-36 lg:w-44"
          style={{ borderColor: '#e5e7eb', background: '#f9fafb' }}
        />
      </div>

      {/* Notifications */}
      <div className="relative cursor-pointer">
        <span className="text-muted-foreground">🔔</span>
        <span
          className="absolute -top-1 -right-1 text-[8px] text-white rounded-full w-3.5 h-3.5 flex items-center justify-center"
          style={{ background: PINK }}
        >3</span>
      </div>

      {/* Account */}
      <div className="relative">
        <button
          onClick={() => setMenuOpen(o => !o)}
          aria-expanded={menuOpen}
          aria-label={isZH ? '開啟帳戶及顯示設定' : 'Open account and display settings'}
          className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-full hover:bg-accent transition-colors"
        >
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-semibold"
            style={{ background: PINK }}
          >
            {avatarLetter}
          </div>
          <div className="hidden sm:block text-left leading-tight max-w-[150px]">
            <div className="text-[11px] font-semibold text-foreground truncate">
              {user?.facilityName ?? '-'}
            </div>
            <div className="text-[9px] text-muted-foreground truncate">
              {roleLabel(user?.role, isZH) || user?.email}
            </div>
          </div>
          <span className="text-muted-foreground text-[10px]">▾</span>
        </button>

        {menuOpen && (
          <>
            <button
              className="fixed inset-0 z-40 cursor-default"
              aria-hidden
              onClick={() => setMenuOpen(false)}
            />
            <div className="absolute right-0 top-full mt-1 w-72 rounded-xl border border-border bg-popover text-popover-foreground shadow-lg z-50 p-1">
              <div className="px-3 py-2">
                <div className="text-[10px] text-muted-foreground">{isZH ? '已登入' : 'Signed in as'}</div>
                <div className="text-xs font-semibold text-foreground truncate">{user?.email ?? '-'}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5 truncate">
                  {user?.facilityName}{user?.role ? ` · ${roleLabel(user.role, isZH)}` : ''}
                </div>
              </div>
              <div className="h-px bg-border my-1" />
              <div className="px-3 py-2 text-[10px] font-semibold text-muted-foreground">{isZH ? '語言' : 'Language'}</div>
              <div className="flex gap-1 px-2 pb-2" role="group" aria-label={isZH ? '語言' : 'Language'}>
                {(['zh', 'en'] as const).map(code => (
                  <button key={code} type="button" aria-pressed={lang === code}
                    onClick={() => { setLang(code); setMenuOpen(false) }}
                    className={`flex-1 rounded-lg px-2 py-1.5 text-xs font-medium ${lang === code ? 'bg-pink-100 text-pink-700' : 'text-foreground hover:bg-accent'}`}>
                    {code === 'zh' ? '繁體中文' : 'English'}
                  </button>
                ))}
              </div>
              <div className="h-px bg-border my-1" />
              <div className="px-3 py-2 text-xs font-semibold">{isZH ? '文字大小' : 'Text size'}</div>
              <div className="flex gap-1 px-2 pb-2" role="group" aria-label={isZH ? '文字大小' : 'Text size'}>
                {([['standard', 'A', '16px'], ['comfortable', 'AA', '18px'], ['large', 'AAA', '22px']] as [TextSize, string, string][]).map(([size, label, px]) => (
                  <button key={size} type="button" onClick={() => setTextSize(size)} aria-pressed={textSize === size}
                    className={`min-h-10 flex-1 rounded-lg border text-xs font-bold ${textSize === size ? 'border-pink-500 bg-pink-100 text-pink-800' : 'border-border bg-background text-foreground'}`}
                    title={`${label} · ${px}`}>
                    {label}<span className="block font-normal text-[10px]">{px}</span>
                  </button>
                ))}
              </div>
              <p className="px-3 pb-1 text-[10px] text-muted-foreground">{isZH ? '只在此裝置保存；仍可用瀏覽器放大。' : 'Saved on this device; browser zoom remains available.'}</p>
              <div className="h-px bg-border my-1" />
              <button type="button" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
                className="w-full text-left rounded-lg px-3 py-2 text-xs hover:bg-accent"
                aria-pressed={theme === 'dark'}>
                {theme === 'dark' ? '☾ ' : '☼ '}{isZH ? '深色模式（預覽）' : 'Dark mode (preview)'} · {theme === 'dark' ? 'On' : 'Off'}
              </button>
              <p className="px-3 pb-1 text-[10px] text-muted-foreground">{isZH ? '舊頁面仍需逐頁對比測試。' : 'Legacy pages still need contrast review.'}</p>
              <div className="h-px bg-border my-1" />
              <button
                onClick={() => { setMenuOpen(false); signOut() }}
                className="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-foreground hover:bg-accent transition-colors"
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
