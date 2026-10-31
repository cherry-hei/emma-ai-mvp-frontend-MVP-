'use client'
import { usePathname, useRouter } from 'next/navigation'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'
import { ROUTES, ROUTE_FEATURE, canOpenRoute, isActiveRoute, type RoutePath } from '@/components/layout/navRoutes'

const PINK = '#E8187A'

const NAV: { key: string; icon: string; path: RoutePath }[] = [
  { key: 'nav_dashboard',   icon: '🏠',  path: ROUTES.dashboard  },
  { key: 'nav_roster',      icon: '📅',  path: ROUTES.roster     },
  // Scheduling rules and codes are settings subpages, not duplicate navigation.
  { key: 'nav_compliance',  icon: '✅',  path: ROUTES.compliance },
  { key: 'nav_approval',    icon: '👥✓', path: ROUTES.approval   },
  { key: 'nav_personnel',   icon: '👤',  path: ROUTES.staff      },
  // HIDDEN for MVP — Phase 5-8
  // { key: 'nav_roi',         icon: '📈',  path: ROUTES.roi        },
  { key: 'nav_reports',     icon: '📊',  path: ROUTES.reports    },
  { key: 'nav_alert',       icon: '🔔',  path: ROUTES.alert },
  { key: 'nav_messages',   icon: '💬',  path: ROUTES.messages   },

  { key: 'nav_settings',    icon: '⚙️',  path: ROUTES.settings   },
]

export function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const pathname = usePathname()
  const router   = useRouter()
  const { t, lang }    = useLang()
  const { user }       = useAuth()

  // Menu filtered by the RBAC matrix (spec 1.1). Before this every role was shown
  // all eight items, so a care worker saw the superintendent's sidebar including
  // ROI and could open /roi with the home's financials.
  const nav = NAV.filter(({ path }) => canOpenRoute(user?.role, ROUTE_FEATURE[path]))
  // The owner uses the settings hub. Other permitted roles must not lose their
  // pre-existing task-rule access merely because they cannot open facility settings.
  if (!canOpenRoute(user?.role, 'facility.settings') && canOpenRoute(user?.role, 'task_codes')) {
    nav.push({ key: 'nav_scheduling', icon: '⚙️', path: ROUTES.scheduling })
  }

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
      className="flex h-full w-56 max-w-[86vw] flex-shrink-0 flex-col border-r border-slate-200 bg-white"
    >
      {/* Logo */}
      <div className="border-b border-slate-100 p-4">
        <div className="text-xl font-bold tracking-tight" style={{ color: PINK }}>
          Emma AI
        </div>
        <div className="mt-1 text-xs font-semibold leading-4 tracking-wide text-slate-500">
          SCHEDULING &amp; COMPLIANCE INTELLIGENCE
        </div>
      </div>

      {/* Site selector - reflects the signed-in account's facility + role */}
      <div
        className="mx-3 mt-3 min-h-11 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
      >
        <div className="text-xs font-medium tracking-wide text-slate-500">
          {roleLabel(user?.role, lang === 'zh') || (lang === 'zh' ? '院舍' : 'Facility')}
        </div>
        <div className="emma-reflow-text mt-0.5 break-words text-sm font-medium text-slate-700">
          {user?.facilityName ?? (lang === 'zh' ? '院舍管理' : 'Care Home Admin')}
        </div>
      </div>

      {/* Nav */}
      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 py-3" aria-label={lang === 'zh' ? '主要導覽' : 'Primary navigation'}>
        {nav.map(({ key, icon, path }) => {
          const active = isActiveRoute(pathname, path)
          return (
            <button
              type="button"
              key={path}
              aria-label={label(key)}
              aria-current={active ? 'page' : undefined}
              onClick={() => { router.push(path); onNavigate?.() }}
              className={`flex min-h-11 w-full items-center gap-3 rounded-lg border-l-2 px-3 py-2 text-left text-base font-medium leading-5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-300 focus-visible:ring-offset-2 ${active ? 'border-pink-600 bg-pink-50 text-pink-600' : 'border-transparent text-slate-700 hover:bg-slate-50 hover:text-slate-900'}`}
            >
              <span className="shrink-0 text-base opacity-70" aria-hidden>{icon}</span>
              <span className="emma-reflow-text min-w-0 flex-1 break-words">{label(key)}</span>
            </button>
          )
        })}
      </nav>

      <div className="border-t border-slate-100 px-4 py-3 text-xs leading-relaxed text-slate-500">
        {lang === 'zh' ? '管理工具僅顯示帳戶獲授權的功能。' : 'Only functions authorised for this account are shown.'}
      </div>
    </aside>
  )
}
