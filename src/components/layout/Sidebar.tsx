'use client'
import { usePathname, useRouter } from 'next/navigation'

const NAV = [
  { label: 'Home 首頁',           icon: '⊞',   path: '/' },
  { label: 'Roster 更表',         icon: '◫',   path: '/roster' },
  { label: 'Compliance 合規',      icon: '✓',   path: '/compliance' },
  { label: 'Approval 審批',        icon: '👥✓', path: '/approval' },
  { label: 'Personnel 人事',       icon: '👥',  path: '/personnel' },
  { label: 'ROI 效益',             icon: '▦',   path: '/roi' },
  { label: 'Alert 警報',           icon: '🔔',  path: '/alert', badge: '3' },
  { label: 'AI Insights AI洞察',   icon: '✦',   path: '/insights' },
]

const PINK      = '#f28f9e'
const PINK_HOVER = '#e87a8e'

export function Sidebar() {
  const pathname = usePathname()
  const router   = useRouter()

  return (
    <aside
      className="w-48 flex flex-col flex-shrink-0 border-r"
      style={{ background: '#ffffff', borderColor: '#e5e7eb' }}
    >
      {/* Logo */}
      <div className="p-4 border-b" style={{ borderColor: '#f3f4f6' }}>
        <div className="text-xl font-bold" style={{ color: PINK, letterSpacing: '-0.5px' }}>
          Emma AI
        </div>
        <div className="text-[8px] tracking-[2.5px] mt-0.5 text-gray-400">
          MEDICAL INTELLIGENCE
        </div>
      </div>

      {/* Site selector */}
      <div
        className="mx-2 mt-2 p-2.5 rounded-lg cursor-pointer border"
        style={{ background: '#f9fafb', borderColor: '#e5e7eb' }}
      >
        <div className="text-[9px] tracking-wider text-gray-400">HK REGION 01</div>
        <div className="text-[11px] font-medium mt-0.5 text-gray-700">Care Home Admin</div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-2 space-y-0.5">
        {NAV.map(({ label, icon, path, badge }) => {
          const active = pathname === path || (path !== '/' && pathname.startsWith(path))
          return (
            <button
              key={path}
              onClick={() => router.push(path)}
              className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs transition-all border-l-2 text-left"
              style={{
                color:           active ? PINK    : '#374151',
                background:      active ? '#fdf2f4' : 'transparent',
                borderLeftColor: active ? PINK    : 'transparent',
              }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.background = '#f9fafb' }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
            >
              <span className="text-sm opacity-70">{icon}</span>
              <span className="flex-1">{label}</span>
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

      {/* Alert banner */}
      <div
        className="mx-2 mb-2 p-2.5 rounded-lg border"
        style={{ background: '#fff5f7', borderColor: '#fcd5dc' }}
      >
        <div className="text-xs font-semibold" style={{ color: PINK }}>⚑ 緊急警報</div>
        <div className="text-[10px] mt-0.5" style={{ color: PINK_HOVER }}>夜更人手不足 — F3</div>
      </div>

      {/* New Request button */}
      <button
        onClick={() => router.push('/alert')}
        className="mx-2 mb-3 py-2.5 rounded-lg text-white text-xs font-semibold text-center transition-colors"
        style={{ background: PINK }}
        onMouseEnter={e => (e.currentTarget.style.background = PINK_HOVER)}
        onMouseLeave={e => (e.currentTarget.style.background = PINK)}
      >
        + New Request 新請求
      </button>
    </aside>
  )
}