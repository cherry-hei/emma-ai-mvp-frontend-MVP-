import { ShiftDay } from '@/lib/types'

const SHIFT_CONFIG = {
  A:     { label: 'A SHIFT',       class: 'bg-blue-50 text-blue-700 border-blue-200' },
  P:     { label: 'P SHIFT',       class: 'bg-green-50 text-green-700 border-green-200' },
  N:     { label: 'N SHIFT',       class: 'bg-violet-50 text-violet-700 border-violet-200' },
  OFF:   { label: 'DAY OFF',       class: 'bg-gray-50 text-gray-400 border-gray-100' },
  REST:  { label: 'REST',          class: 'bg-gray-50 text-gray-400 border-gray-100' },
  SLEEP: { label: 'SLEEPING DAY',  class: 'bg-amber-50 text-amber-700 border-amber-200' },
  ALERT: { label: '⚑ 急假',        class: 'bg-red-50 text-red-600 border-red-300 animate-pulse' },
}

export function ShiftCell({ shift }: { shift: ShiftDay }) {
  const cfg = SHIFT_CONFIG[shift.type]
  return (
    <td className="border-r border-gray-100 p-1 min-w-24 align-top">
      <div className={`rounded-md px-1.5 py-1 border text-[9px] font-bold text-center mb-1 ${cfg.class}`}>
        {cfg.label}
      </div>
      {shift.tasks?.map(t => (
        <div key={t} className="text-[8px] text-gray-500 leading-tight px-0.5">• {t}</div>
      ))}
    </td>
  )
}