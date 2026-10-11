'use client'

import { useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'
import { ROUTES, ROUTE_FEATURE, canOpenRoute } from '@/components/layout/navRoutes'

const PINK = '#E8187A'

export function TopNav({ onMenuToggle }: { onMenuToggle?: () => void } = {}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const { lang, setLang } = useLang()
  const { user, signOut } = useAuth()
  const isZH = lang === 'zh'
  const onInsights = pathname?.startsWith(ROUTES.insights)
  const avatarLetter = user?.facilityName?.trim().charAt(0).toUpperCase() || user?.email?.charAt(0).toUpperCase() || 'U'

  return (
    <header className="flex h-14 min-w-0 shrink-0 items-center gap-2 overflow-hidden border-b bg-white px-3 md:px-4" style={{ borderColor: '#edf1f5' }}>
      <button
        type="button"
        onClick={onMenuToggle}
        className="shrink-0 rounded-xl p-2 text-slate-600 transition hover:bg-slate-100 md:hidden"
        aria-label={isZH ? '開啟選單' : 'Open menu'}
      >
        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <div className="min-w-0 flex-1" />

      {canOpenRoute(user?.role, ROUTE_FEATURE[ROUTES.insights]) && (
        <button
          type="button"
          onClick={() => router.push(ROUTES.insights)}
          aria-label={isZH ? '開啟 Emma AI' : 'Open Emma AI'}
          className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl border px-2.5 text-[11px] font-bold transition hover:-translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 sm:px-3"
          style={{
            borderColor: onInsights ? PINK : '#f6c6db',
            color: onInsights ? '#fff' : PINK,
            background: onInsights ? 'linear-gradient(135deg,#E8187A,#f28f9e)' : '#fff5f9',
          }}
        >
          <span aria-hidden>✦</span><span className="hidden sm:inline">Emma AI</span>
        </button>
      )}

      <button
        type="button"
        onClick={() => setLang(isZH ? 'en' : 'zh')}
        className="h-9 shrink-0 rounded-xl border px-2.5 text-xs font-bold transition hover:bg-rose-50"
        style={{ borderColor: '#f6c6db', color: PINK, background: '#fffafb' }}
        aria-label={isZH ? 'Switch to English' : '切換為中文'}
      >
        {isZH ? 'EN' : '中'}
      </button>

      {canOpenRoute(user?.role, ROUTE_FEATURE[ROUTES.alert]) && (
        <button
          type="button"
          onClick={() => router.push(ROUTES.alert)}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
          aria-label={isZH ? '前往警報中心' : 'Open Alert Centre'}
        >
          <span aria-hidden>🔔</span>
        </button>
      )}

      <div className="relative shrink-0">
        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          className="flex h-9 max-w-[12rem] items-center gap-2 rounded-full py-1 pl-1 pr-2 transition hover:bg-slate-50"
          aria-expanded={menuOpen}
          aria-label={isZH ? '帳戶選單' : 'Account menu'}
        >
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white" style={{ background: PINK }}>{avatarLetter}</div>
          <div className="hidden min-w-0 text-left leading-tight md:block">
            <div className="truncate text-[11px] font-semibold text-slate-800">{user?.facilityName || (isZH ? '院舍帳戶' : 'Facility account')}</div>
            <div className="truncate text-[9px] text-slate-400">{roleLabel(user?.role, isZH) || user?.email}</div>
          </div>
          <span className="hidden text-[10px] text-slate-400 sm:inline" aria-hidden>▾</span>
        </button>

        {menuOpen && (
          <>
            <button className="fixed inset-0 z-40 cursor-default" aria-label={isZH ? '關閉帳戶選單' : 'Close account menu'} onClick={() => setMenuOpen(false)} />
            <div className="absolute right-0 top-full z-50 mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-1 shadow-xl">
              <div className="px-3 py-2.5">
                <div className="text-[10px] text-slate-400">{isZH ? '已登入' : 'Signed in as'}</div>
                <div className="truncate text-xs font-semibold text-slate-800">{user?.email || '—'}</div>
                <div className="mt-0.5 truncate text-[10px] text-slate-500">{user?.facilityName}{user?.role ? ` · ${roleLabel(user.role, isZH)}` : ''}</div>
              </div>
              <div className="my-1 h-px bg-slate-100" />
              <button type="button" onClick={() => { setMenuOpen(false); signOut() }} className="w-full rounded-xl px-3 py-2 text-left text-xs font-semibold text-slate-700 transition hover:bg-slate-50">
                {isZH ? '切換帳戶 / 登出' : 'Switch account / Sign out'}
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  )
}
