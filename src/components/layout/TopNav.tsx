'use client'
import { usePathname, useRouter } from 'next/navigation'

const LINKS = [
  { label: 'Roster',     path: '/roster' },
  { label: 'Staffing',   path: '/personnel' },
  { label: 'Compliance', path: '/compliance' },
  { label: 'Reports',    path: '/reports' },
]

export function TopNav() {
  const pathname = usePathname()
  const router   = useRouter()

  return (
    <header className="bg-white border-b border-gray-200 px-5 flex items-center gap-4 flex-shrink-0" style={{ height: '52px' }}>

      {/* Logo — only the E icon, no text */}
      <div className="flex items-center mr-2">
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold"
          style={{ background: '#f28f9e' }}
        >
          E
        </div>
      </div>

      {/* Nav links */}
      <nav className="flex gap-1">
        {LINKS.map(({ label, path }) => {
          const active = pathname.startsWith(path)
          return (
            <button
              key={path}
              onClick={() => router.push(path)}
              className="px-3 py-1.5 rounded-md text-[13px] font-medium transition-all border-b-2"
              style={{
                color:            active ? '#f28f9e' : '#6b7280',
                borderBottomColor: active ? '#f28f9e' : 'transparent',
              }}
            >
              {label}
            </button>
          )
        })}
      </nav>

      {/* Search */}
      <div className="relative ml-auto max-w-72 flex-1">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
        <input
          className="w-full pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-xs bg-gray-50 outline-none focus:border-pink-300"
          placeholder="Search anything..."
        />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 ml-3">
        <button className="w-8 h-8 rounded-lg border border-gray-200 flex items-center justify-center text-gray-500 text-sm hover:bg-gray-50">⚙</button>
        <button className="w-8 h-8 rounded-lg border border-gray-200 flex items-center justify-center text-gray-500 text-sm hover:bg-gray-50 relative">
          🔔
          <span className="absolute top-1 right-1 w-2 h-2 rounded-full border-2 border-white" style={{ background: '#f28f9e' }} />
        </button>
        <div className="flex items-center gap-2 px-2 py-1 border border-gray-200 rounded-lg cursor-pointer">
          <div className="text-right">
            <div className="text-xs font-semibold">Dr. Sarah Wong</div>
            <div className="text-[9px] text-gray-500 tracking-wide">ADMIN</div>
          </div>
          <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[10px] font-bold" style={{ background: '#f28f9e' }}>SW</div>
        </div>
      </div>

    </header>
  )
}