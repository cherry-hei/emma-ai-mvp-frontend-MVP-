'use client'

import { usePathname, useRouter } from 'next/navigation'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'
import {
  ROUTE_FEATURE, SIDEBAR_NAVIGATION, canOpenRoute, isActiveRoute,
} from '@/components/layout/navRoutes'

const PINK = '#E8187A'

const FALLBACK: Record<string, { zh: string; en: string }> = {
  nav_dashboard:  { zh: '儀表板', en: 'Dashboard' },
  nav_roster:     { zh: '更表', en: 'Roster' },
  nav_compliance: { zh: '合規', en: 'Compliance' },
  nav_approval:   { zh: '審批', en: 'Approval' },
  nav_personnel:  { zh: '員工檔案', en: 'Staff Portfolio' },
  nav_reports:    { zh: '報告', en: 'Reports' },
  nav_alert:      { zh: '警報中心', en: 'Alert Centre' },
  nav_messages:   { zh: '訊息中心', en: 'Messages' },
  nav_ai:         { zh: 'Emma AI', en: 'Emma AI' },
  nav_settings:   { zh: '院舍設定', en: 'Facility Settings' },
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const pathname = usePathname()
  const router = useRouter()
  const { t, lang } = useLang()
  const { user } = useAuth()
  const isZH = lang === 'zh'

  const nav = SIDEBAR_NAVIGATION.filter(({ path }) => canOpenRoute(user?.role, ROUTE_FEATURE[path]))
  const label = (key: string) => {
    const translated = t(key)
    return translated !== key ? translated : (FALLBACK[key]?.[lang] ?? key)
  }

  return (
    <aside className="flex h-full w-56 max-w-[86vw] flex-col border-r bg-white" style={{ borderColor: '#e8edf3' }}>
      <div className="border-b px-4 py-4" style={{ borderColor: '#f1f3f6' }}>
        {/* Keep the established Emma mark; this is not replaced by a new logo. */}
        <div className="text-xl font-bold tracking-tight" style={{ color: PINK }}>Emma AI</div>
        <div className="mt-0.5 text-[8px] tracking-[0.26em] text-slate-400">MEDICAL INTELLIGENCE</div>
      </div>

      <div className="mx-3 mt-3 rounded-xl border bg-slate-50 px-3 py-2.5" style={{ borderColor: '#e8edf3' }}>
        <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">
          {roleLabel(user?.role, isZH) || (isZH ? '院舍帳戶' : 'Facility account')}
        </div>
        <div className="mt-1 truncate text-xs font-semibold text-slate-700">
          {user?.facilityName || (isZH ? '已登入院舍' : 'Signed-in facility')}
        </div>
      </div>

      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2.5 py-3" aria-label={isZH ? '主要導覽' : 'Primary navigation'}>
        {nav.map(({ key, icon, path }) => {
          const active = isActiveRoute(pathname, path)
          return (
            <button
              key={path}
              type="button"
              onClick={() => { router.push(path); onNavigate?.() }}
              className="flex w-full items-center gap-2.5 rounded-xl border border-transparent px-3 py-2.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300"
              style={{
                color: active ? PINK : '#475569',
                background: active ? '#fff0f6' : 'transparent',
                borderColor: active ? '#fde0ed' : 'transparent',
                fontWeight: active ? 700 : 500,
              }}
              onMouseEnter={(event) => { if (!active) event.currentTarget.style.background = '#f8fafc' }}
              onMouseLeave={(event) => { if (!active) event.currentTarget.style.background = 'transparent' }}
            >
              <span className="w-4 shrink-0 text-center text-sm leading-none opacity-80" aria-hidden>{icon}</span>
              <span className="min-w-0 flex-1 truncate">{label(key)}</span>
            </button>
          )
        })}
      </nav>

      <div className="border-t px-4 py-3 text-[10px] leading-relaxed text-slate-400" style={{ borderColor: '#f1f3f6' }}>
        {isZH ? '管理工具僅顯示帳戶獲授權的功能。' : 'Only functions authorised for this account are shown.'}
      </div>
    </aside>
  )
}
