'use client'

import { useState } from 'react'
import { api } from '@/lib/api'
import type { MySummary } from '@/lib/apiTypes'

export default function TasksScreen({ summary, onChange }: {
  summary: MySummary
  onChange: () => void
}) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const tasks = summary.tasks

  async function toggle(taskId: string, isDone: boolean) {
    setBusy(taskId)
    setError('')
    try {
      await api.setTaskStatus(taskId, isDone ? 'pending' : 'done')
      onChange()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-gray-900">今日工作清單</h3>
        <p className="mt-1 text-sm text-gray-500">
          {summary.date} · {summary.today_shift?.shift_type ?? 'OFF'} · 點擊可切換完成狀態
        </p>
      </div>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>
      )}

      {tasks.length === 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white px-4 py-8 text-center text-sm text-gray-500">
          今日沒有指定工作 / No tasks assigned today
        </div>
      )}

      {tasks.map((task) => (
        <button
          key={task.id}
          disabled={busy === task.id}
          onClick={() => toggle(task.id, task.status === 'done')}
          className="flex w-full items-center gap-3 rounded-2xl border border-gray-200 bg-white p-4 text-left shadow-sm transition hover:border-[#f3c7cf] hover:bg-[#fffafb] disabled:opacity-50"
        >
          <div
            className={`flex h-6 w-6 items-center justify-center rounded-full border ${
              task.status === 'done'
                ? 'border-[#e87a8e] bg-[#e87a8e] text-white'
                : 'border-gray-300 bg-white text-transparent'
            }`}
          >
            ✓
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className={`text-sm font-medium ${task.status === 'done' ? 'text-gray-400 line-through' : 'text-gray-900'}`}>
                {task.task_label}
              </p>
              {task.priority === 'high' && (
                <span className="rounded-full bg-[#fdecef] px-2 py-0.5 text-[10px] font-semibold text-[#e87a8e]">
                  HIGH
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-400">
              {[task.scheduled_time, task.shift_type].filter(Boolean).join(' · ')}
              {task.completed_at && ` · 完成於 ${new Date(task.completed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
            </p>
          </div>
        </button>
      ))}
    </div>
  )
}
