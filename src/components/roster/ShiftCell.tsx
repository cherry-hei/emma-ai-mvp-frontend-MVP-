import { DayEntry, ShiftType } from '@/lib/types'

const SHIFT_CONFIG: Record<ShiftType, { bg: string; color: string }> = {
  A:     { bg: '#DBEAFE', color: '#1D4ED8' },   // A更 藍色系
  B:     { bg: '#e0f2fe', color: '#0369a1' },   // B更 深藍色
  E:     { bg: '#e8f5e9', color: '#2e7d32' },   // E更 深綠
  P:     { bg: '#D1FAE5', color: '#047857' },   // P更 翡翠綠
  N:     { bg: '#1a1a2e', color: '#ffffff' },   // N更 黑色
  AN:    { bg: '#ede9fe', color: '#6D28D9' },   // A/N更 紫色
  OFF:   { bg: '#F3F4F6', color: '#9CA3AF' },   // 休班 灰色
  AL:    { bg: '#FEF3C7', color: '#92400E' },   // 年假 黃色
  SLEEP: { bg: '#EDE9FE', color: '#5B21B6' },
  ALERT: { bg: '#FFE4E6', color: '#f28f9e' },
}

export function ShiftCell({
  shift,
  onClick,
}: {
  shift: DayEntry
  onClick?: () => void
}) {
  const cfg = SHIFT_CONFIG[shift.type] ?? { bg: '#F3F4F6', color: '#9CA3AF' }
  // Display the original shift code (e.g. A7, B7, P2, K10) if available
  const displayLabel = shift.shiftLabel || shift.type

  return (
    <td
      onClick={onClick}
      className="border-r border-gray-100 p-1 min-w-24 align-top cursor-pointer hover:bg-pink-50/40 transition-colors"
    >
      {/* Shift code badge */}
      <div
        className="rounded-md px-1.5 py-1 text-[9px] font-bold text-center mb-0.5"
        style={{ background: cfg.bg, color: cfg.color }}
      >
        {displayLabel}
      </div>

      {/* Meal code (用膳代號) */}
      {shift.mealCode && (
        <div className="text-[7px] text-orange-600 font-semibold text-center mb-0.5 bg-orange-50 rounded px-0.5">
          🍽 {shift.mealCode}
        </div>
      )}

      {/* Note for OFF/PH days */}
      {shift.note && (shift.type === 'OFF' || shift.shiftLabel === 'PH' || shift.shiftLabel === 'O' || shift.shiftLabel === 'O,') && (
        <div className="text-[7px] text-gray-500 italic text-center mb-0.5 px-0.5">
          {shift.note}
        </div>
      )}

      {/* Task list */}
      {shift.tasks && shift.tasks.length > 0 && shift.tasks.map(t => (
        <div key={t} className="text-[7px] text-gray-500 leading-tight px-0.5">• {t}</div>
      ))}
    </td>
  )
}
