'use client'
import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'
import { ROUTES, ROUTE_FEATURE, canOpenRoute } from '@/components/layout/navRoutes'
import {
  DISPLAY_TEXT_SCALES,
  applyDisplayTextScale,
  readDisplayTextScale,
  saveDisplayTextScale,
  type DisplayTextScale,
} from './display-preferences'

const PINK = '#E8187A'

export function TopNav({ onMenuToggle }: { onMenuToggle?: () => void } = {}) {
  const [search, setSearch] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [textScale, setTextScale] = useState<DisplayTextScale>(100)
  const pathname = usePathname()
  const router = useRouter()
  const { lang, setLang, t } = useLang()
  const { user, signOut } = useAuth()
  const isZH = lang === 'zh'

  // 'A' / 'B' from "Care Home A (…)", else first letter of the email.
  const avatarLetter =
    user?.facilityName?.match(/Home\s*([A-Za-z0-9])/)?.[1]?.toUpperCase()
    ?? user?.email?.charAt(0).toUpperCase()
    ?? 'U'

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setTextScale(applyDisplayTextScale(readDisplayTextScale()))
    })
    return () => window.cancelAnimationFrame(frame)
  }, [])

  function changeTextScale(value: string) {
    const next = saveDisplayTextScale(value)
    setTextScale(applyDisplayTextScale(next))
  }

  const textScaleLabel = isZH ? '文字大小' : 'Text size'

  return (
    <header
      className="emma-topnav flex min-h-14 shrink-0 flex-wrap items-center gap-2 border-b bg-white px-3 py-2 sm:gap-3 md:px-4"
      style={{ background: '#ffffff', borderColor: '#f3f4f6' }}
    >
      {/* Mobile hamburger */}
      <button
        type="button"
        onClick={onMenuToggle}
        className="shrink-0 rounded-lg p-2 text-slate-600 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-300 md:hidden"
        aria-label={isZH ? '開啟選單' : 'Open menu'}
      >
        <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <div className="text-sm font-black tracking-tight md:hidden" style={{ color: PINK }}>Emma AI</div>
      {/* The sidebar is the only primary navigation; header carries utilities. */}
      <div className="min-w-2 flex-1" />

      {canOpenRoute(user?.role, ROUTE_FEATURE[ROUTES.insights]) && (
        <button
          type="button"
          onClick={() => router.push(ROUTES.insights)}
          aria-label={isZH ? '開啟 Emma AI' : 'Open Emma AI'}
          className="flex min-h-11 shrink-0 items-center gap-1.5 rounded-lg border px-2.5 text-sm font-semibold transition hover:-translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-300 sm:px-3"
          style={{
            borderColor: pathname?.startsWith(ROUTES.insights) ? '#E8187A' : '#f6c6db',
            color: pathname?.startsWith(ROUTES.insights) ? '#ffffff' : '#E8187A',
            background: pathname?.startsWith(ROUTES.insights) ? 'linear-gradient(135deg,#E8187A,#f28f9e)' : '#fff5f9',
          }}
        >
          <span aria-hidden>✦</span><span className="hidden lg:inline">Emma AI</span>
        </button>
      )}

      {/* Search */}
      <div className="relative hidden min-w-0 sm:block">
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-gray-400" aria-hidden>🔍</span>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t('search_ph')}
          className="min-h-11 w-36 rounded-lg border bg-slate-50 py-1.5 pl-7 pr-3 text-sm text-slate-700 placeholder:text-slate-500 focus:outline-none focus:ring-1 lg:w-44"
          style={{ borderColor: '#e5e7eb', background: '#f9fafb' }}
        />
      </div>

      <div className="flex min-h-11 items-center rounded-lg border bg-white p-0.5" style={{ borderColor: '#f0a0c0' }}>
        <label className="sr-only" htmlFor="emma-text-scale">{textScaleLabel}</label>
        <select
          id="emma-text-scale"
          value={textScale}
          onChange={event => changeTextScale(event.target.value)}
          className="min-h-10 cursor-pointer rounded-md border-0 bg-white px-2 py-1 text-sm font-semibold outline-none focus:ring-1"
          style={{ color: PINK, width: 'calc(8.5rem * var(--emma-text-scale, 1))', maxWidth: 'calc(100vw - 2rem)' }}
          aria-label={textScaleLabel}
        >
          {DISPLAY_TEXT_SCALES.map(scale => (
            <option key={scale} value={scale}>{isZH ? `文字 ${scale}%` : `Text ${scale}%`}</option>
          ))}
        </select>
      </div>

      <div className="flex min-h-11 items-center rounded-lg border p-0.5" style={{ borderColor: '#f0a0c0' }} aria-label={isZH ? '語言選擇' : 'Language selector'}>
        <button
          type="button"
          onClick={() => setLang('zh')}
          aria-pressed={isZH}
          className="min-h-10 rounded-md px-2 py-1 text-sm font-semibold transition-colors sm:px-2.5"
          style={{ background: isZH ? PINK : 'transparent', color: isZH ? '#fff' : PINK }}
        >
          中文
        </button>
        <button
          type="button"
          onClick={() => setLang('en')}
          aria-pressed={!isZH}
          className="min-h-10 rounded-md px-2 py-1 text-sm font-semibold transition-colors sm:px-2.5"
          style={{ background: !isZH ? PINK : 'transparent', color: !isZH ? '#fff' : PINK }}
        >
          EN
        </button>
      </div>

      {/* Alert utility intentionally does not fabricate a badge count. */}
      <div className="flex min-h-11 min-w-11 items-center justify-center rounded-xl text-slate-600" aria-label={isZH ? '警報' : 'Alerts'}>
        <span aria-hidden>🔔</span>
      </div>

      {/* Account */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setMenuOpen(o => !o)}
          className="flex min-h-11 items-center gap-2 rounded-full py-1 pl-1 pr-2 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-300"
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          aria-label={isZH ? '帳戶選單' : 'Account menu'}
        >
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white"
            style={{ background: PINK }}
          >
            {avatarLetter}
          </div>
          <div className="hidden max-w-[150px] text-left leading-tight sm:block">
            <div className="truncate text-sm font-semibold text-gray-800">
              {user?.facilityName ?? '-'}
            </div>
            <div className="truncate text-xs text-gray-500">
              {roleLabel(user?.role, isZH) || user?.email}
            </div>
          </div>
          <span className="text-gray-400 text-[10px]">▾</span>
        </button>

        {menuOpen && (
          <>
            <button
              type="button"
              className="fixed inset-0 z-40 cursor-default"
              aria-hidden
              onClick={() => setMenuOpen(false)}
            />
            <div className="absolute right-0 top-full z-50 mt-1 w-[min(24rem,calc(100vw-1.5rem))] max-h-[70dvh] overflow-y-auto rounded-xl border border-gray-200 bg-white p-1 shadow-lg" role="menu">
              <div className="px-3 py-2">
                <div className="text-[10px] text-gray-400">{isZH ? '已登入帳戶' : 'Signed-in account'}</div>
                <div className="break-words text-xs font-semibold text-gray-800">{user?.email ?? '-'}</div>
                <div className="mt-0.5 break-words text-[10px] text-gray-500">
                  {user?.facilityName}{user?.role ? ` · ${roleLabel(user.role, isZH)}` : ''}
                </div>
              </div>
              <div className="h-px bg-gray-100 my-1" />
              {canOpenRoute(user?.role, ROUTE_FEATURE[ROUTES.settings]) && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setMenuOpen(false); router.push(ROUTES.settings) }}
                  className="w-full rounded-lg px-3 py-2 text-left text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
                >
                  {isZH ? '設定' : 'Settings'}
                </button>
              )}
              <button
                type="button"
                role="menuitem"
                onClick={() => { setMenuOpen(false); signOut() }}
                className="w-full rounded-lg px-3 py-2 text-left text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                {isZH ? '登出' : 'Sign out'}
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  )
}
