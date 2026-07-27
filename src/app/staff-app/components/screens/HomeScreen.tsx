'use client'

import { useState } from 'react'
import { api } from '@/lib/api'
import type { MySummary } from '@/lib/apiTypes'

export default function HomeScreen({ summary, onChange }: {
  summary: MySummary
  onChange: () => void
}) {
  const [busy, setBusy] = useState('')
  const { staff, today_shift, hours, facility_ratio, tasks, attendance } = summary
  const pending = tasks.filter((t) => t.status === 'pending')

  async function toggle(taskId: string, isDone: boolean) {
    setBusy(taskId)
    try {
      await api.setTaskStatus(taskId, isDone ? 'pending' : 'done')
      onChange()
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="space-y-5">
      <section className="rounded-3xl bg-gradient-to-br from-[#e87a8e] to-[#d9657b] p-5 text-white shadow-sm">
        <p className="text-sm text-white/80">今日值班 / Today</p>
        <div className="mt-2 flex items-end justify-between">
          <div>
            <h2 className="text-2xl font-semibold">{today_shift?.shift_type ?? 'OFF'}</h2>
            <p className="mt-1 text-sm text-white/80">
              {[staff.name, staff.rank, staff.unit_name].filter(Boolean).join(' · ')}
            </p>
            {today_shift?.start_time && (
              <p className="text-xs text-white/70">{today_shift.start_time} – {today_shift.end_time}</p>
            )}
          </div>
          <div className="rounded-2xl bg-white/20 px-3 py-2 text-right">
            <p className="text-xs text-white/80">待辦工作</p>
            <p className="text-lg font-semibold">{summary.tasks_pending}</p>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-gray-400">本週期工時進度</p>
          <p className="mt-2 text-2xl font-semibold text-gray-900">{hours.pct}%</p>
          <p className="mt-1 text-xs text-[#e87a8e]">
            {hours.scheduled_hours}/{hours.contracted_hours} 小時
          </p>
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-gray-400">院舍人手比率</p>
          <p className="mt-2 text-2xl font-semibold text-gray-900">
            {facility_ratio ? `${facility_ratio.pct}%` : '—'}
          </p>
          <p className="mt-1 text-xs text-gray-500">
            {facility_ratio ? `${facility_ratio.passing}/${facility_ratio.total} 項合規` : '未有比率資料'}
          </p>
        </div>
      </section>

      <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">今日重點工作</h3>
          <span className="rounded-full bg-[#fdecef] px-2.5 py-1 text-xs font-medium text-[#e87a8e]">
            {pending.length} 項
          </span>
        </div>

        {tasks.length > 0 ? (
          <div className="space-y-3">
            {tasks.map((task) => (
              <button
                key={task.id}
                disabled={busy === task.id}
                onClick={() => toggle(task.id, task.status === 'done')}
                className="flex w-full items-center gap-3 rounded-2xl bg-gray-50 px-3 py-3 text-left transition hover:bg-[#fffafb] disabled:opacity-50"
              >
                <div className={`h-3 w-3 rounded-full ${task.status === 'done' ? 'bg-emerald-500' : 'bg-[#e87a8e]'}`} />
                <div className="min-w-0 flex-1">
                  <p className={`truncate text-sm font-medium ${task.status === 'done' ? 'text-gray-400 line-through' : 'text-gray-800'}`}>
                    {task.task_label}
                  </p>
                  <p className="text-xs text-gray-400">
                    {[task.scheduled_time, task.shift_type].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <span className={`rounded-full px-2 py-1 text-[11px] font-medium ${
                  task.status === 'done' ? 'bg-emerald-50 text-emerald-600' : 'bg-[#fdecef] text-[#e87a8e]'
                }`}>
                  {task.status === 'done' ? '已完成' : '待處理'}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="rounded-2xl bg-gray-50 px-4 py-6 text-center text-sm text-gray-500">
            今日沒有指定工作
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-gray-900">今日打卡</h3>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">上班時間</p>
            <p className="text-sm font-medium text-gray-800">
              {attendance.clock_in_at
                ? new Date(attendance.clock_in_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                : '—'}
            </p>
          </div>
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">已工作</p>
            <p className="text-sm font-medium text-gray-800">
              {Math.floor(attendance.worked_minutes_today / 60)}h {attendance.worked_minutes_today % 60}m
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
