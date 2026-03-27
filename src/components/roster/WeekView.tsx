import { STAFF, ROSTER, DAYS } from '@/lib/data'
import { ShiftType } from '@/lib/types'

const SHIFT_CONFIG: Record<ShiftType, { label: string; bg: string; color: string }> = {
  A: { label: 'A', bg: '#DBEAFE', color: '#1D4ED8' },
  P: { label: 'P', bg: '#D1FAE5', color: '#065F46' },
  N: { label: 'N', bg: '#1a1a2e', color: '#fff' },
  OFF: { label: 'OFF', bg: '#F3F4F6', color: '#9CA3AF' },
  REST: { label: 'REST', bg: '#FEF3C7', color: '#92400E' },
  SLEEP: { label: 'SLEEP', bg: '#EDE9FE', color: '#5B21B6' },
  ALERT: { label: '⚠', bg: '#FFE4E6', color: '#E8187A' },
}

const ROLE_COLOR: Record<string, string> = {
  RN: '#E8187A',
  EN: '#8B5CF6',
  HW: '#0EA5E9',
  PCW: '#10B981',
  PTA: '#F59E0B',
  CW: '#6366F1',
  AW: '#64748B',
}

export function WeekView() {
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      {/* Table header */}
      <div className="grid border-b border-gray-100" style={{ gridTemplateColumns: '180px repeat(7, 1fr)' }}>
        <div className="px-3 py-2 text-[10px] font-semibold text-gray-500 uppercase tracking-wider bg-gray-50">Staff</div>
        {DAYS.map(day => (
          <div key={day} className="px-2 py-2 text-center bg-gray-50 border-l border-gray-100">
            <div className="text-[10px] font-semibold text-gray-700">{day.split(' ')[0]}</div>
            <div className="text-[9px] text-gray-400">{day.split(' ')[1]}</div>
          </div>
        ))}
      </div>

      {/* Rows */}
      {ROSTER.map((row) => {
        const staff = STAFF.find(s => s.id === row.staffId)!
        const pct = Math.round((staff.hoursWorked / staff.hoursTotal) * 100)
        return (
          <div
            key={row.staffId}
            className="grid border-b border-gray-50 hover:bg-gray-50/50 transition-colors"
            style={{ gridTemplateColumns: '180px repeat(7, 1fr)' }}
          >
            {/* Staff info */}
            <div className="px-3 py-2 flex items-center gap-2">
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0"
                style={{ background: ROLE_COLOR[staff.role] }}
              >
                {staff.avatar}
              </div>
              <div className="min-w-0">
                <div className="text-xs font-medium text-gray-900 truncate">{staff.name}</div>
                <div className="flex items-center gap-1 mt-0.5">
                  <span
                    className="text-[9px] px-1.5 rounded-full text-white font-medium"
                    style={{ background: ROLE_COLOR[staff.role] }}
                  >
                    {staff.role}
                  </span>
                  <span className="text-[9px] text-gray-400">{pct}%</span>
                </div>
              </div>
            </div>

            {/* Shift cells */}
            {row.days.map((shift, i) => {
              const cfg = SHIFT_CONFIG[shift.type]
              return (
                <div key={i} className="border-l border-gray-100 p-1 flex flex-col items-center justify-center min-h-[52px]">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-[11px] font-bold"
                    style={{ background: cfg.bg, color: cfg.color }}
                  >
                    {cfg.label}
                  </div>
                  {shift.tasks && shift.tasks.length > 0 && (
                    <div className="mt-0.5 w-full px-0.5">
                      {shift.tasks.slice(0, 1).map((t, ti) => (
                        <div key={ti} className="text-[8px] text-gray-400 truncate text-center">{t}</div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}