'use client'
import { usePathname, useRouter } from 'next/navigation'

const NAV = [
  { label: 'Home 首頁', icon: '⊞', path: '/' },
  { label: 'Roster 更表', icon: '◫', path: '/roster' },
  { label: 'Compliance 合規', icon: '✓', path: '/compliance' },
  { label: 'Personnel 人事', icon: '👥', path: '/personnel' },
  { label: 'ROI 效益', icon: '▦', path: '/roi' },
  { label: 'Alert 警報', icon: '🔔', path: '/alert', badge: '3' },
  { label: 'AI Insights AI洞察', icon: '✦', path: '/insights' },
]

export function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()

  return (
    <aside className="w-48 flex flex-col flex-shrink-0" style={{ background: '#1a1a2e' }}>
      {/* Logo */}
      <div className="p-4 border-b border-white/10">
        <div className="text-xl font-bold" style={{ color: '#E8187A', letterSpacing: '-0.5px' }}>Emma AI</div>
        <div className="text-[8px] tracking-[2.5px] mt-0.5" style={{ color: 'rgba(255,255,255,.35)' }}>MEDICAL INTELLIGENCE</div>
      </div>

      {/* Site selector */}
      <div className="mx-2 mt-2 p-2.5 rounded-lg cursor-pointer border border-white/10" style={{ background: 'rgba(255,255,255,.05)' }}>
        <div className="text-[9px] tracking-wider" style={{ color: 'rgba(255,255,255,.4)' }}>HK REGION 01</div>
        <div className="text-[11px] font-medium mt-0.5 text-white">Care Home Admin</div>
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
                color: active ? '#fff' : 'rgba(255,255,255,.45)',
                background: active ? 'rgba(232,24,122,.15)' : 'transparent',
                borderLeftColor: active ? '#E8187A' : 'transparent',
              }}
            >
              <span className="text-sm opacity-70">{icon}</span>
              <span className="flex-1">{label}</span>
              {badge && (
                <span className="text-[9px] px-1.5 rounded-full text-white" style={{ background: '#E8187A' }}>
                  {badge}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* Alert banner */}
      <div className="mx-2 mb-2 p-2.5 rounded-lg border" style={{ background: 'rgba(232,24,122,.12)', borderColor: 'rgba(232,24,122,.35)' }}>
        <div className="text-xs font-semibold" style={{ color: '#E8187A' }}>⚑ 緊急警報</div>
        <div className="text-[10px] mt-0.5" style={{ color: 'rgba(232,24,122,.7)' }}>夜更人手不足 — F3</div>
      </div>

      {/* New Request button */}
      <button
        onClick={() => router.push('/alert')}
        className="mx-2 mb-3 py-2.5 rounded-lg text-white text-xs font-semibold text-center transition-colors"
        style={{ background: '#E8187A' }}
        onMouseEnter={e => (e.currentTarget.style.background = '#c8156a')}
        onMouseLeave={e => (e.currentTarget.style.background = '#E8187A')}
      >
        + New Request 新請求
      </button>
    </aside>
  )
}