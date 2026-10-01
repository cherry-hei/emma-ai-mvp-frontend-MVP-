'use client'
import { usePathname, useRouter } from 'next/navigation'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'
import { ROUTES, ROUTE_FEATURE, canOpenRoute, isActiveRoute } from '@/components/layout/navRoutes'

const PINK       = '#E8187A'
const PINK_HOVER = '#c9156a'

const NAV: { key: string; icon: string; path: string; badge?: string }[] = [
  { key: 'nav_dashboard',   icon: '🏠',  path: ROUTES.dashboard  },
  { key: 'nav_roster',      icon: '📅',  path: ROUTES.roster     },
  { key: 'nav_compliance',  icon: '✅',  path: ROUTES.compliance },
  { key: 'nav_approval',    icon: '👥✓', path: ROUTES.approval   },
  { key: 'nav_personnel',   icon: '👤',  path: ROUTES.staff      },
  // HIDDEN for MVP — Phase 5-8
  // { key: 'nav_roi',         icon: '📈',  path: ROUTES.roi        },
  { key: 'nav_reports',     icon: '📊',  path: ROUTES.reports    },
  { key: 'nav_alert',       icon: '🔔',  path: ROUTES.alert, badge: '3' },
  { key: 'nav_messages',   icon: '💬',  path: ROUTES.messages   },
]

export function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const pathname = usePathname()
  const router   = useRouter()
  const { t, lang }    = useLang()
  const { user }       = useAuth()

  // Menu filtered by the RBAC matrix (spec 1.1). Before this every role was shown
  // all eight items, so a care worker saw the superintendent's sidebar including
  // ROI and could open /roi with the home's financials.
  const canSeeSettings = canOpenRoute(user?.role, ROUTE_FEATURE[ROUTES.settings])
  const nav = [
    ...NAV,
    // Preserve existing route access for roles with task-code read but no settings grant.
    ...(!canSeeSettings ? [
      { key: 'nav_scheduling', icon: '🧩', path: ROUTES.scheduling },
      { key: 'nav_shiftcodes', icon: '📖', path: '/shift-codes' },
    ] : []),
  ].filter(({ path }) => canOpenRoute(user?.role, ROUTE_FEATURE[path]))

  const FALLBACK: Record<string, { zh: string; en: string }> = {
    nav_dashboard:  { zh: '主頁',       en: 'Dashboard'     },
    nav_roster:     { zh: '更表',       en: 'Roster'        },
    nav_scheduling: { zh: '排班規則設定', en: 'Scheduling Rules'},
    nav_compliance: { zh: '合規',       en: 'Compliance'    },
    nav_approval:   { zh: '審批',       en: 'Approval'      },
    nav_personnel:  { zh: '員工檔案',   en: 'Staff Portfolio'},
    nav_roi:        { zh: '投資回報',   en: 'ROI'           },
    nav_reports:    { zh: '報告',       en: 'Reports'       },
    nav_alert:      { zh: '警報中心',   en: 'Alert Centre'  },
    nav_messages:   { zh: '訊息中心',   en: 'Messages'      },
    nav_shiftcodes: { zh: '更期代號',   en: 'Shift Codes'   },
    nav_settings:   { zh: '設定',       en: 'Settings'      },
    urgent_alert:   { zh: '🚨 緊急警報', en: '🚨 Urgent Alert' },
    staff_shortage: { zh: 'P更人手不足 - F3', en: 'P-shift understaffed - F3' },
    new_request:    { zh: '+ 新增請求', en: '+ New Request'  },
  }

  const label = (key: string) => {
    const fromContext = t(key)
    if (fromContext && fromContext !== key) return fromContext
    return FALLBACK[key]?.[lang] ?? key
  }

  return (
    <aside
      className="w-48 flex flex-col flex-shrink-0 border-r border-border bg-card"
    >
      {/* Logo */}
      <div className="p-4 border-b border-border flex items-center gap-2">
        <img src="/emma-mark.png" alt="" width={34} height={34} className="shrink-0 dark:hidden" />
        <img src="/emma-mark-dark.png" alt="" width={34} height={34} className="hidden shrink-0 dark:block" />
        <div className="text-lg font-bold tracking-tight text-foreground">Emma <span style={{ color: PINK }}>AI</span></div>
      </div>

      {/* Site selector - reflects the signed-in account's facility + role */}
      <div
        className="mx-2 mt-2 p-2.5 rounded-lg border"
        style={{ background: '#f9fafb', borderColor: '#e5e7eb' }}
      >
        <div className="text-[9px] tracking-wider text-gray-400">
          {roleLabel(user?.role, lang === 'zh') || (lang === 'zh' ? '院舍' : 'Facility')}
        </div>
        <div className="text-[11px] font-medium mt-0.5 text-gray-700 truncate">
          {user?.facilityName ?? (lang === 'zh' ? '院舍管理' : 'Care Home Admin')}
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-2 space-y-0.5">
        {nav.map(({ key, icon, path, badge }) => {
          const active = isActiveRoute(pathname, path)
          return (
            <button
              key={path}
              onClick={() => { router.push(path); onNavigate?.() }}
              className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs transition-all border-l-2 text-left"
              style={{
                color:           active ? PINK : '#374151',
                background:      active ? '#fff0f5' : 'transparent',
                borderLeftColor: active ? PINK : 'transparent',
                fontWeight:      active ? 700 : 400,
              }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.background = '#f9fafb' }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
            >
              <span className="text-sm opacity-70">{icon}</span>
              <span className="flex-1">{label(key)}</span>
              {badge && (
                <span
                  className="text-[9px] px-1.5 rounded-full text-white"
                  style={{ background: PINK }}
                >
                  {badge}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {canSeeSettings && (
        <div className="border-t border-gray-100 px-2 py-2">
          <button onClick={() => { router.push(ROUTES.settings); onNavigate?.() }}
            aria-current={isActiveRoute(pathname, ROUTES.settings) ? 'page' : undefined}
            className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs border-l-2 text-left"
            style={{ color: isActiveRoute(pathname, ROUTES.settings) ? PINK : '#374151', borderLeftColor: isActiveRoute(pathname, ROUTES.settings) ? PINK : 'transparent', background: isActiveRoute(pathname, ROUTES.settings) ? '#fff0f5' : 'transparent' }}>
            <span aria-hidden="true" className="text-sm">⚙️</span>{label('nav_settings')}
          </button>
        </div>
      )}

      {/* Alert banner */}
      <div
        className="mx-2 mb-2 p-2.5 rounded-lg border hidden"
        style={{ background: '#fff5f7', borderColor: '#fcd5dc' }}
      >
        <div className="text-xs font-semibold" style={{ color: PINK }}>
          {label('urgent_alert')}
        </div>
        <div className="text-[10px] mt-0.5" style={{ color: PINK_HOVER }}>
          {label('staff_shortage')}
        </div>
      </div>

      {/* New Request button - 已移除獨立按鈕，點 Alert 直接跳頁 */}
    </aside>
  )
}
