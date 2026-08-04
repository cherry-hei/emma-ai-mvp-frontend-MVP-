'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { MySummary } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'
import AccountMenu from './AccountMenu'
import BottomNav from './BottomNav'
import PushPrompt from './PushPrompt'
import HomeScreen from './screens/HomeScreen'
import TasksScreen from './screens/TasksScreen'
import MyShiftScreen from './screens/MyShiftScreen'
import ClockInScreen from './screens/ClockInScreen'
import ProfileScreen from './screens/ProfileScreen'

export type TabKey = 'home' | 'tasks' | 'shift' | 'clockin' | 'profile'

export default function StaffShell() {
  const { t } = useLang()
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

  // Tapping a background notification lands here (spec SA.4b). The service
  // worker focuses an open tab rather than opening a second copy of the app, so
  // without this the notification would bring the app forward on whatever screen
  // it was left on - and the roster change it was announcing would be a tap away
  // instead of on screen. `reload()` because the row it refers to has changed.
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return

    const onMessage = (event: MessageEvent) => {
      if (event.data?.type !== 'emma:notification-click') return
      const relatedType = event.data.data?.related_type
      if (relatedType === 'task_assignment') setActiveTab('tasks')
      else if (relatedType === 'leave_request' || relatedType === 'roster_version') setActiveTab('shift')
      reload()
    }

    navigator.serviceWorker.addEventListener('message', onMessage)
    return () => navigator.serviceWorker.removeEventListener('message', onMessage)
  }, [reload])

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto flex min-h-screen max-w-md flex-col bg-gray-50">
        <header className="sticky top-0 z-20 border-b border-gray-200 bg-white/95 backdrop-blur">
          <div className="flex items-center justify-between gap-2 px-4 py-4">
            <div className="min-w-0">
              <p className="truncate text-xs font-medium uppercase tracking-wide text-[#e87a8e]">{t('sa_brand')}</p>
              <h1 className="mt-1 truncate text-lg font-semibold text-gray-900">
                {summary?.staff.name_en || summary?.staff.name || t('sa_fallback_name')}
              </h1>
            </div>
            <div className="flex flex-shrink-0 items-center gap-2">
              <div className="relative flex h-9 w-9 items-center justify-center rounded-full bg-[#fdecef] text-[#e87a8e]">
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
              {/* Outside the `summary` guard on purpose: the error branch below is
                  exactly when a staff member needs to sign out of the wrong
                  account, so these controls must not depend on the fetch. */}
              <AccountMenu />
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-5">
          {loading && (
            <div className="rounded-2xl bg-white p-6 text-center text-sm text-gray-400">{t('sa_loading')}</div>
          )}

          {!loading && error && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
              <p className="font-semibold">{t('sa_load_error_title')}</p>
              <p className="mt-1 text-xs">{error}</p>
              <p className="mt-3 text-xs text-rose-600">{t('sa_load_error_hint')}</p>
            </div>
          )}

          {!loading && !error && summary && (
            <>
              {activeTab === 'home' && <PushPrompt />}
              {activeTab === 'home' && <HomeScreen summary={summary} onChange={reload} />}
              {activeTab === 'tasks' && <TasksScreen summary={summary} onChange={reload} />}
              {activeTab === 'shift' && <MyShiftScreen />}
              {activeTab === 'clockin' && <ClockInScreen />}
              {activeTab === 'profile' && <ProfileScreen />}
            </>
          )}
        </main>

        <BottomNav activeTab={activeTab} onChange={setActiveTab} />
      </div>
    </div>
  )
}
