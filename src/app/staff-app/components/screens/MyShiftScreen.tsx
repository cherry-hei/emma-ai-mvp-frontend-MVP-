'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { MyRoster } from '@/lib/apiTypes'

function shiftStyle(shift: string | null | undefined) {
  switch (shift) {
    case 'P':
    case '7P':
      return 'bg-[#fdecef] text-[#e87a8e] border border-[#f7c9d1]'
    case 'A':
    case 'B':
    case 'E':
    case '7A':
    case '9A':
      return 'bg-gray-100 text-gray-700 border border-gray-200'
    case 'N':
    case 'AN':
      return 'bg-gray-800 text-white border border-gray-700'
    case 'OFF':
    case 'DO':
      return 'bg-white text-gray-400 border border-gray-200'
    case 'AL':
      return 'bg-[#fff5f7] text-[#d9657b] border border-[#f3d7dd]'
    case 'SLEEP':
      return 'bg-gray-50 text-gray-500 border border-gray-200'
    default:
      return 'bg-gray-100 text-gray-600 border border-gray-200'
  }
}

function dayLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  const wd = d.toLocaleDateString('en-GB', { weekday: 'short' }).toUpperCase()
  return `${wd} ${d.getDate()}/${d.getMonth() + 1}`
}

export default function MyShiftScreen() {
  const [roster, setRoster] = useState<MyRoster | null>(null)
  const [days, setDays] = useState(7)
  const [error, setError] = useState('')

  useEffect(() => {
    api.myRoster(days).then(setRoster)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load roster'))
  }, [days])

  if (error) {
    return <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
  }
  if (!roster) {
    return <div className="rounded-2xl bg-white p-6 text-center text-sm text-gray-400">載入中… / Loading…</div>
  }

  const today = new Date().toISOString().slice(0, 10)

  return (
    <div className="space-y-4">
      <section className="rounded-3xl bg-gradient-to-br from-[#e87a8e] to-[#d9657b] p-5 text-white shadow-sm">
        <p className="text-sm text-white/80">我的更表 / My Roster</p>
        <h2 className="mt-2 text-2xl font-semibold">{roster.name_en || roster.name}</h2>
        <p className="mt-1 text-sm text-white/80">
          {[roster.rank, roster.unit_name].filter(Boolean).join(' · ')}
        </p>
        <p className="mt-1 text-xs text-white/70">{roster.start} → {roster.end}</p>
      </section>

      <div className="flex gap-2">
        {[7, 14, 28].map((n) => (
          <button key={n} onClick={() => setDays(n)}
            className={`flex-1 rounded-xl px-3 py-2 text-xs font-semibold transition ${
              days === n ? 'bg-[#e87a8e] text-white' : 'border border-gray-200 bg-white text-gray-600'
            }`}>
            {n} 日
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {roster.days.map((day) => (
          <div key={day.date}
            className={`rounded-2xl border bg-white p-4 shadow-sm ${
              day.date === today ? 'border-[#e87a8e]' : 'border-gray-200'
            }`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-gray-400">
                  {dayLabel(day.date)}{day.date === today ? ' · 今日' : ''}
                </p>
                <p className="mt-1 text-sm text-gray-600">
                  {day.unit_name ?? '-'}
                  {day.start_time && ` · ${day.start_time}–${day.end_time}`}
                </p>
              </div>
              <div className={`inline-flex rounded-xl px-3 py-2 text-sm font-semibold ${shiftStyle(day.shift_type)}`}>
                {day.shift_type ?? '-'}
              </div>
            </div>

            {day.tasks.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {day.tasks.map((task) => (
                  <span key={task}
                    className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs text-gray-600">
                    {task}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
