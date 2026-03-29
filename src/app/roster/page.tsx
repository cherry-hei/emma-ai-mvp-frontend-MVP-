'use client'
import { useState, useRef } from 'react'
import { STAFF, ROSTER } from '@/lib/data'
import { KPIStrip } from '@/components/roster/KPIStrip'
import { StaffCell } from '@/components/roster/StaffCell'
import { ShiftCell } from '@/components/roster/ShiftCell'
import { CreateShiftModal } from '@/components/modals/CreateShiftModal'
import { CreateEventModal } from '@/components/modals/CreateEventModal'

const DAY_LABELS = ['MON','TUE','WED','THU','FRI','SAT','SUN']
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

function getWeekDays(weekOffset: number) {
  const base = new Date(2026, 2, 23)
  base.setDate(base.getDate() + weekOffset * 7)
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(base)
    d.setDate(d.getDate() + i)
    return { dayLabel: DAY_LABELS[i], dateLabel: `${d.getDate()}/${d.getMonth() + 1}`, date: d }
  })
}

const SHIFT_LEGEND = [
  { color: '#3b82f6', label: 'A SHIFT (07:00–15:00)' },
  { color: '#B1D0E2', label: 'B SHIFT (08:00–16:00)' },
  { color: '#A5D6A7', label: 'E SHIFT (09:00–17:00)' },
  { color: '#10b981', label: 'P SHIFT (13:30–21:30)' },
  { color: '#8b5cf6', label: 'A/N SHIFT (07:00–13:30 / 21:30–07:00)' },
  { color: '#fbbf24', label: 'AL (年假)' },
  { color: '#9ca3af', label: 'DAY OFF' },
  { color: '#a78bfa', label: 'SLEEPING DAY' },
]

export default function RosterPage() {
  const [view,       setView]       = useState<'week' | 'month'>('week')
  const [shiftOpen,  setShiftOpen]  = useState(false)
  const [eventOpen,  setEventOpen]  = useState(false)
  const [aiLoading,  setAiLoading]  = useState(false)
  const [weekOffset, setWeekOffset] = useState(0)
  const dateInputRef = useRef<HTMLInputElement>(null)

  const handleAI = () => {
    setAiLoading(true)
    setTimeout(() => setAiLoading(false), 1800)
  }

  const weekDays  = getWeekDays(weekOffset)
  const startDay  = weekDays[0].date
  const endDay    = weekDays[6].date
  const dateLabel = `${MONTHS[startDay.getMonth()]} ${startDay.getDate()} — ${MONTHS[endDay.getMonth()]} ${endDay.getDate()}, ${endDay.getFullYear()}`

  const handleDatePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.value) return
    const picked    = new Date(e.target.value)
    const base      = new Date(2026, 2, 23)
    const diffMs    = picked.getTime() - base.getTime()
    const diffWeeks = Math.round(diffMs / (7 * 24 * 60 * 60 * 1000))
    setWeekOffset(diffWeeks)
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Toolbar ── */}
      <div className="bg-white border-b border-gray-200 px-5 py-3 flex-shrink-0 space-y-2.5">
        {/* Row 1: title + view toggle + AI */}
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-900">Weekly Roster 更表</h1>
          <button className="flex items-center gap-2 px-3 py-1.5 border border-gray-200 rounded-lg text-[13px] font-medium hover:bg-gray-50">
            🏠 Haven Elderly Home
            <span className="text-gray-400 text-xs">▾</span>
          </button>
          <div className="ml-auto flex items-center gap-2.5">
            <div className="flex border border-gray-200 rounded-lg overflow-hidden">
              {(['week','month'] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className="px-3.5 py-1.5 text-xs font-medium transition-all capitalize"
                  style={{ background: view === v ? '#374151' : '#fff', color: view === v ? '#fff' : '#6b7280' }}
                >
                  {v === 'week' ? 'Week' : 'Month'}
                </button>
              ))}
            </div>
            <button
              onClick={handleAI}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-white text-xs font-semibold rounded-lg transition-colors"
              style={{ background: aiLoading ? '#e87a8e' : '#f28f9e' }}
            >
              {aiLoading ? '✦ 計算中...' : '✦ AI排更建議'}
            </button>
          </div>
        </div>

        {/* Row 2: Date nav + action buttons */}
        <div className="flex items-center gap-2">
          {/* Left arrow */}
          <button
            onClick={() => setWeekOffset(o => o - 1)}
            className="w-7 h-7 rounded-md border border-gray-200 flex items-center justify-center text-gray-500 hover:bg-gray-50 text-sm"
          >‹</button>

          {/* Date label + calendar picker */}
          <div className="relative flex items-center gap-1">
            <span className="text-[13px] font-semibold text-gray-900">{dateLabel}</span>
            <button
              onClick={() => dateInputRef.current?.showPicker?.() ?? dateInputRef.current?.click()}
              className="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-100 text-sm"
              aria-label="Open calendar"
            >
              📅
            </button>
            <input
              ref={dateInputRef}
              type="date"
              className="absolute opacity-0 w-0 h-0 pointer-events-none"
              onChange={handleDatePick}
            />
          </div>

          {/* Right arrow */}
          <button
            onClick={() => setWeekOffset(o => o + 1)}
            className="w-7 h-7 rounded-md border border-gray-200 flex items-center justify-center text-gray-500 hover:bg-gray-50 text-sm"
          >›</button>

          {/* Action buttons */}
          <div className="ml-auto flex gap-2">
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-[#f28f9e] rounded-lg text-[#f28f9e] hover:bg-pink-50 transition-colors">
              ⬇ Download Schedule
            </button>
            <button
              onClick={() => setShiftOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              ＋ Create Shift
            </button>
            <button
              onClick={() => setEventOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              ✦ Create Special Event
            </button>
            <button
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white rounded-lg transition-colors"
              style={{ background: '#f28f9e' }}
              onMouseEnter={e => (e.currentTarget.style.background = '#e87a8e')}
              onMouseLeave={e => (e.currentTarget.style.background = '#f28f9e')}
            >
              ✓ Publish Change
            </button>
          </div>
        </div>
      </div>

      {/* ── Shift Legend ── */}
      <div className="flex items-center gap-5 px-5 py-2 bg-white border-b border-gray-200 flex-shrink-0 flex-wrap">
        {SHIFT_LEGEND.map(s => (
          <div key={s.label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: s.color }} />
            <span className="text-[10px] text-gray-600">{s.label}</span>
          </div>
        ))}
      </div>

      {/* ── KPI Strip ── */}
      <KPIStrip />

      {/* ── Table ── */}
      <div className="flex-1 overflow-auto px-5 py-3">
        {view === 'week' ? (
          <table
            className="w-full border-collapse bg-white rounded-xl border border-gray-200"
            style={{ borderRadius: '12px', overflow: 'hidden' }}
          >
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-3.5 py-2.5 text-[10px] font-semibold text-gray-500 border-r border-gray-200 w-52">
                  STAFF MEMBER
                </th>
                {weekDays.map((d, i) => (
                  <th key={i} className="px-2 py-2.5 text-center border-r border-gray-100 last:border-r-0 min-w-24">
                    <div className="text-[9px] text-gray-400 tracking-wide">{d.dayLabel}</div>
                    <div className={`text-[15px] font-bold ${d.date.getDay() === 4 ? 'text-[#f28f9e]' : 'text-gray-800'}`}>
                      {d.dateLabel}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROSTER.map(row => {
                const staff = STAFF.find(s => s.id === row.staffId)!
                return (
                  <tr key={row.staffId} className="border-t border-gray-100 hover:bg-pink-50/30 transition-colors">
                    <StaffCell staff={staff} />
                    {row.days.map((shift, idx) => <ShiftCell key={idx} shift={shift} />)}
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div className="overflow-x-auto">
            <table
              className="border-collapse bg-white rounded-xl border border-gray-200 text-[10px]"
              style={{ minWidth: '1100px' }}
            >
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-3 py-2 text-[9px] font-semibold text-gray-500 border-r border-gray-200 w-36">員工</th>
                  {Array.from({ length: 31 }, (_, i) => (
                    <th key={i} className="px-0.5 py-2 text-[9px] text-gray-400 text-center border-r border-gray-100 w-8">{i + 1}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {STAFF.map(s => {
                  const shiftTypes = ['A','P','N','AL','AL','A','P','P','N','A','AL','P','A','N','AL','A','P','A','N','AL','A','P','N','A','AL','P','A','N','AL','A','P']
                  return (
                    <tr key={s.id} className="border-t border-gray-100 hover:bg-pink-50/20">
                      <td className="px-2.5 py-1.5 border-r border-gray-200 bg-gray-50">
                        <div className="font-semibold text-gray-900 truncate">{s.nameEn.split(' ').slice(-1)[0]}</div>
                        <div className="text-gray-400 text-[8px]">{s.role} · {s.floor}</div>
                      </td>
                      {shiftTypes.map((t, i) => {
                        const cfg: { [k: string]: { bg: string; color: string } } = {
                          A:  { bg: '#eff6ff', color: '#1d4ed8' },
                          P:  { bg: '#f0fdf4', color: '#15803d' },
                          N:  { bg: '#faf5ff', color: '#7e22ce' },
                          AN: { bg: '#F3E8FF', color: '#6D28D9' },
                          AL: { bg: '#FEF3C7', color: '#92400E' },
                        }
                        const c = cfg[t] ?? { bg: '#f9fafb', color: '#9ca3af' }
                        return (
                          <td key={i} className="px-0.5 py-1 text-center border-r border-gray-50">
                            <span
                              className="inline-block w-4 h-4 rounded text-[8px] font-bold leading-4 text-center"
                              style={{ background: c.bg, color: c.color }}
                            >
                              {t}
                            </span>
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Modals ── */}
      <CreateShiftModal open={shiftOpen} onClose={() => setShiftOpen(false)} />
      <CreateEventModal open={eventOpen} onClose={() => setEventOpen(false)} />
    </div>
  )
}