'use client'

import type { ReactNode } from 'react'
import { useLang } from '@/components/layout/LanguageContext'

export type TabKey = 'home' | 'tasks' | 'shift' | 'clockin' | 'profile'

interface BottomNavProps {
  activeTab: TabKey
  onChange: (tab: TabKey) => void
}

const tabs: { key: TabKey; labelKey: string; icon: ReactNode }[] = [
  { key: 'home', labelKey: 'sa_tab_home', icon: <span className="text-base">🏠</span> },
  { key: 'tasks', labelKey: 'sa_tab_tasks', icon: <span className="text-base">📝</span> },
  { key: 'shift', labelKey: 'sa_tab_shift', icon: <span className="text-base">📅</span> },
  { key: 'clockin', labelKey: 'sa_tab_clockin', icon: <span className="text-base">⏰</span> },
  { key: 'profile', labelKey: 'sa_tab_profile', icon: <span className="text-base">👤</span> },
]

export default function BottomNav({ activeTab, onChange }: BottomNavProps) {
  const { t } = useLang()
  return (
    <div className="sticky bottom-0 z-30 border-t border-gray-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-md items-center justify-around px-2 py-2">
        {tabs.map((tab) => {
          const active = activeTab === tab.key
          return (
            <button
              key={tab.key}
              onClick={() => onChange(tab.key)}
              className={`flex min-w-[64px] flex-col items-center gap-1 rounded-2xl px-2 py-2 text-[11px] font-medium transition-all ${
                active
                  ? 'bg-[#fdecef] text-[#e87a8e]'
                  : 'text-gray-400 hover:bg-gray-50 hover:text-gray-600'
              }`}
            >
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-full transition-all ${
                  active ? 'bg-[#e87a8e] text-white shadow-sm' : 'bg-gray-100 text-gray-400'
                }`}
              >
                {tab.icon}
              </span>
              <span>{t(tab.labelKey)}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}