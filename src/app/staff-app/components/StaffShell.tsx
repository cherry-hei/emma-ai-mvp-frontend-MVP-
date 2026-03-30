'use client'

import { useState } from 'react'
import BottomNav from './BottomNav'
import HomeScreen from './screens/HomeScreen'
import TasksScreen from './screens/TasksScreen'
import MyShiftScreen from './screens/MyShiftScreen'
import ClockInScreen from './screens/ClockInScreen'
import ProfileScreen from './screens/ProfileScreen'

export type TabKey = 'home' | 'tasks' | 'shift' | 'clockin' | 'profile'

export default function StaffShell() {
  const [activeTab, setActiveTab] = useState<TabKey>('home')

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto flex min-h-screen max-w-md flex-col bg-gray-50">
        <header className="sticky top-0 z-20 border-b border-gray-200 bg-white/95 backdrop-blur">
          <div className="flex items-center justify-between px-5 py-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-[#e87a8e]">Emma AI · Staff App</p>
              <h1 className="mt-1 text-lg font-semibold text-gray-900">員工手機 App</h1>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#fdecef] text-[#e87a8e]">
              <svg viewBox="0 0 24 24" className="w-5 h-5 fill-none stroke-current" strokeWidth="1.8">
                <path d="M12 6v6l4 2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-5">
          {activeTab === 'home' && <HomeScreen />}
          {activeTab === 'tasks' && <TasksScreen />}
          {activeTab === 'shift' && <MyShiftScreen />}
          {activeTab === 'clockin' && <ClockInScreen />}
          {activeTab === 'profile' && <ProfileScreen />}
        </main>

        <BottomNav activeTab={activeTab} onChange={setActiveTab} />
      </div>
    </div>
  )
}