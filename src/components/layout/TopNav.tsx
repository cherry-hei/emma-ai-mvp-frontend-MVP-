'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#f28f9e'

const TABS = [
  { key: 'topnav_roster',     path: '/roster' },
  { key: 'topnav_staffing',   path: '/personnel' },
  { key: 'topnav_compliance', path: '/compliance' },
  { key: 'topnav_reports',    path: '/reports' },
]

export function TopNav() {
  const [active, setActive] = useState('topnav_roster')
  const [search, setSearch]   = useState('')
  const router = useRouter()
  const { lang, setLang, t }  = useLang()

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
            onClick={() => { setActive(key); router.push(path) }}
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

      {/* Avatar */}
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-semibold cursor-pointer"
        style={{ background: PINK }}
      >
        A
      </div>
    </header>
  )
}