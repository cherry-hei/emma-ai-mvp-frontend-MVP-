'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { MySummary } from '@/lib/apiTypes'
import BottomNav from './BottomNav'
import HomeScreen from './screens/HomeScreen'
import TasksScreen from './screens/TasksScreen'
import MyShiftScreen from './screens/MyShiftScreen'
import ProfileScreen from './screens/ProfileScreen'

export type TabKey = 'home' | 'tasks' | 'shift' | 'profile'

export default function StaffShell() {
  const [activeTab, setActiveTab] = useState<TabKey>('home')
  const [summary, setSummary] = useState<MySummary | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  // One shared read for the whole app; every screen mutation calls back into it so
  // the header badge, hours ring and task counts can't drift apart.
  const reload = useCallback(async () => {
    try {
      setSummary(await api.mySummary())
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto flex min-h-screen max-w-md flex-col bg-gray-50">
        <header className="sticky top-0 z-20 border-b border-gray-200 bg-white/95 backdrop-blur">
          <div className="flex items-center justify-between px-5 py-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-[#e87a8e]">Emma AI · Staff App</p>
              <h1 className="mt-1 text-lg font-semibold text-gray-900">
                {summary?.staff.name_en || summary?.staff.name || '員工手機 App'}
              </h1>
            </div>
            <div className="relative flex h-10 w-10 items-center justify-center rounded-full bg-[#fdecef] text-[#e87a8e]">
              <svg viewBox="0 0 24 24" className="w-5 h-5 fill-none stroke-current" strokeWidth="1.8">
                <path d="M12 6v6l4 2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {!!summary?.unread_notifications && (
                <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#e87a8e] px-1 text-[9px] font-bold text-white">
                  {summary.unread_notifications}
                </span>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-5">
          {loading && (
            <div className="rounded-2xl bg-white p-6 text-center text-sm text-gray-400">載入中… / Loading…</div>
          )}

          {!loading && error && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
              <p className="font-semibold">無法載入員工資料 / Cannot load staff data</p>
              <p className="mt-1 text-xs">{error}</p>
              <p className="mt-3 text-xs text-rose-600">
                此頁需要以綁定員工紀錄的帳戶登入。
                <br />
                Sign in with a staff-linked account to use the staff app.
              </p>
            </div>
          )}

          {!loading && !error && summary && (
            <>
              {activeTab === 'home' && <HomeScreen summary={summary} onChange={reload} />}
              {activeTab === 'tasks' && <TasksScreen summary={summary} onChange={reload} />}
              {activeTab === 'shift' && <MyShiftScreen />}
              {activeTab === 'profile' && <ProfileScreen />}
            </>
          )}
        </main>

        <BottomNav activeTab={activeTab} onChange={setActiveTab} />
      </div>
    </div>
  )
}
