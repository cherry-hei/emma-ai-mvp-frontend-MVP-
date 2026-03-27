import { Staff } from '@/lib/types'

const ROLE_STYLE: Record<string, string> = {
  RN:  'bg-blue-50 text-blue-700',
  EN:  'bg-green-50 text-green-700',
  HW:  'bg-amber-50 text-amber-800',
  PCW: 'bg-purple-50 text-purple-700',
  PTA: 'bg-sky-50 text-sky-700',
  CW:  'bg-rose-50 text-rose-700',
  AW:  'bg-gray-100 text-gray-600',
}

const AVATAR_STYLE: Record<string, string> = {
  RN:  'bg-blue-50 text-blue-600',
  EN:  'bg-green-50 text-green-600',
  HW:  'bg-amber-50 text-amber-700',
  PCW: 'bg-purple-50 text-purple-600',
  PTA: 'bg-sky-50 text-sky-600',
  CW:  'bg-rose-50 text-rose-600',
  AW:  'bg-gray-100 text-gray-600',
}

export function StaffCell({ staff }: { staff: Staff }) {
  const pct = (staff.hoursWorked / staff.hoursTotal) * 100
  const barColor = pct >= 100 ? '#dc2626' : pct >= 90 ? '#d97706' : '#E8187A'

  return (
    <td className="border-r border-gray-100 p-2.5 w-52 min-w-52 bg-white">
      <div className="flex items-center gap-2 mb-1.5">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 border border-pink-100 ${AVATAR_STYLE[staff.role]}`}>
          {staff.avatar}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1">
            <span className="text-[12px] font-semibold text-gray-900 truncate">{staff.nameEn}</span>
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${ROLE_STYLE[staff.role]}`}>{staff.role}</span>
          </div>
          <div className="text-[10px] text-gray-500 truncate">{staff.ward} / {staff.floor}</div>
        </div>
      </div>

      <div className="flex gap-1 flex-wrap mb-1.5">
        {staff.certs.slice(0,3).map(c => (
          <span key={c} className="text-[8px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded border border-gray-200">{c}</span>
        ))}
      </div>

      <div>
        <div className="flex justify-between text-[9px] text-gray-400 mb-1">
          <span>已工作</span>
          <span className="font-semibold" style={{ color: barColor }}>{staff.hoursWorked}/{staff.hoursTotal}h</span>
        </div>
        <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(pct, 100)}%`, background: barColor }} />
        </div>
      </div>
    </td>
  )
}