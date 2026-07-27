'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { MyAttendance, MySummary } from '@/lib/apiTypes'

function hhmm(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function ClockInScreen({ summary, onChange }: {
  summary: MySummary
  onChange: () => void
}) {
  const [attendance, setAttendance] = useState<MyAttendance | null>(null)
  const [showLog, setShowLog] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.myAttendance().then(setAttendance)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load attendance'))
  }, [])

  useEffect(() => { load() }, [load])

  const clockedIn = attendance?.today.clocked_in ?? summary.attendance.clocked_in
  const hours = summary.hours

  async function punch() {
    setBusy(true)
    setError('')
    try {
      await api.clock(clockedIn ? 'clock_out' : 'clock_in')
      load()
      onChange()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Clock action failed')
    } finally {
      setBusy(false)
    }
  }

  const worked = attendance?.today.worked_minutes_today ?? summary.attendance.worked_minutes_today

  return (
    <div className="space-y-4">
      <section className="rounded-3xl bg-gradient-to-br from-[#e87a8e] to-[#d9657b] p-5 text-white shadow-sm">
        <p className="text-sm text-white/80">{clockedIn ? '已上班 / On duty' : '未打卡 / Not clocked in'}</p>
        <h2 className="mt-2 text-2xl font-semibold">
          {hhmm(attendance?.today.clock_in_at ?? summary.attendance.clock_in_at)}
        </h2>
        <p className="mt-1 text-sm text-white/80">
          {[summary.staff.name, summary.staff.rank, summary.staff.unit_name].filter(Boolean).join(' · ')}
        </p>
        {summary.today_shift?.start_time && (
          <p className="text-xs text-white/70">
            排更 {summary.today_shift.shift_type} {summary.today_shift.start_time}–{summary.today_shift.end_time}
          </p>
        )}
      </section>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>
      )}

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-gray-900">本週期工時</h3>
        <p className="mt-1 text-sm text-gray-500">{hours.period_start} → {hours.period_end}</p>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-gray-600">{hours.scheduled_hours} / {hours.contracted_hours} 小時</span>
            <span className="font-semibold text-[#e87a8e]">{hours.pct}%</span>
          </div>
          <div className="h-3 w-full overflow-hidden rounded-full bg-gray-100">
            <div className="h-full rounded-full bg-[#e87a8e]" style={{ width: `${Math.min(hours.pct, 100)}%` }} />
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-gray-900">打卡摘要</h3>
        <div className="mt-3 space-y-3">
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">今日已工作</p>
            <p className="text-sm font-medium text-gray-800">
              {Math.floor(worked / 60)}h {worked % 60}m
            </p>
          </div>
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">下班時間</p>
            <p className="text-sm font-medium text-gray-800">
              {hhmm(attendance?.today.clock_out_at ?? summary.attendance.clock_out_at)}
            </p>
          </div>
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">本月實際打卡工時</p>
            <p className="text-sm font-medium text-gray-800">
              {attendance ? `${attendance.month.worked_hours}h · ${attendance.month.days_worked} 天` : '—'}
            </p>
          </div>
        </div>
      </div>

      <button onClick={punch} disabled={busy}
        className="w-full rounded-2xl bg-[#e87a8e] px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#d9657b] disabled:opacity-50">
        {clockedIn ? '下班打卡 / Clock out' : '上班打卡 / Clock in'}
      </button>

      <button onClick={() => setShowLog((s) => !s)}
        className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm font-semibold text-gray-700 transition hover:bg-gray-50">
        {showLog ? '收起打卡記錄' : '查看打卡記錄'}
      </button>

      {showLog && attendance && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          {attendance.recent.length === 0 && (
            <p className="text-sm text-gray-400">尚無打卡記錄</p>
          )}
          {attendance.recent.map((e) => (
            <div key={e.id} className="flex items-center justify-between border-b border-gray-50 py-2 text-xs last:border-0">
              <span className={e.event_type === 'clock_in' ? 'text-emerald-600' : 'text-gray-500'}>
                {e.event_type === 'clock_in' ? '上班' : '下班'}
              </span>
              <span className="text-gray-600">{new Date(e.event_at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
