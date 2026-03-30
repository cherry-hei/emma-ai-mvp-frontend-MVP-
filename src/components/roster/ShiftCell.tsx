import { DayEntry, ShiftType } from '@/lib/types'

const SHIFT_CONFIG: Record<ShiftType, { label: string; bg: string; color: string }> = {
  A:     { label: 'A',     bg: '#DBEAFE', color: '#1D4ED8' },
  B:     { label: 'B',     bg: '#e8f4fb', color: '#4a7c9e' },
  E:     { label: 'E',     bg: '#e8f5e9', color: '#3a6b42' },
  P:     { label: 'P',     bg: '#D1FAE5', color: '#065F46' },
  N:     { label: 'N',     bg: '#1a1a2e', color: '#fff'    },
  AN:    { label: 'A/N',   bg: '#F3E8FF', color: '#6D28D9' },
  OFF:   { label: 'OFF',   bg: '#F3F4F6', color: '#9CA3AF' },
  AL:    { label: 'AL',    bg: '#FEF3C7', color: '#92400E' },
  SLEEP: { label: 'SLEEP', bg: '#EDE9FE', color: '#5B21B6' },
  ALERT: { label: '⚠',    bg: '#FFE4E6', color: '#f28f9e' },
}

export function ShiftCell({ shift }: { shift: DayEntry }) {
  const cfg = SHIFT_CONFIG[shift.type] ?? { label: shift.type, bg: '#F3F4F6', color: '#9CA3AF' }
  return (
    <td className="border-r border-gray-100 p-1 min-w-24 align-top">
      <div
        className="rounded-md px-1.5 py-1 text-[9px] font-bold text-center mb-1"
        style={{ background: cfg.bg, color: cfg.color }}
      >
        {cfg.label}
      </div>
      {shift.tasks?.map(t => (
        <div key={t} className="text-[8px] text-gray-500 leading-tight px-0.5">• {t}</div>
      ))}
    </td>
  )
}