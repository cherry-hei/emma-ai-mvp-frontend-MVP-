import { STAFF, ROSTER, DAYS } from '../../../../lib/data'

type ShiftType = 'A' | 'B' | 'E' | 'P' | 'N' | 'AN' | 'OFF' | 'AL' | 'SLEEP' | 'ALERT'

function shiftStyle(shift: ShiftType) {
  switch (shift) {
    case 'P':
      return 'bg-[#fdecef] text-[#e87a8e] border border-[#f7c9d1]'
    case 'A':
    case 'B':
    case 'E':
      return 'bg-gray-100 text-gray-700 border border-gray-200'
    case 'N':
    case 'AN':
      return 'bg-gray-800 text-white border border-gray-700'
    case 'OFF':
      return 'bg-white text-gray-400 border border-gray-200'
    case 'AL':
      return 'bg-[#fff5f7] text-[#d9657b] border border-[#f3d7dd]'
    case 'SLEEP':
      return 'bg-gray-50 text-gray-500 border border-gray-200'
    case 'ALERT':
      return 'bg-[#e87a8e] text-white border border-[#e87a8e]'
    default:
      return 'bg-gray-100 text-gray-600 border border-gray-200'
  }
}

export default function MyShiftScreen() {
  const me = STAFF[0]
  const myRoster = ROSTER.find((row) => row.staffId === me.id)

  return (
    <div className="space-y-4">
      <section className="rounded-3xl bg-gradient-to-br from-[#e87a8e] to-[#d9657b] p-5 text-white shadow-sm">
        <p className="text-sm text-white/80">我的更表</p>
        <h2 className="mt-2 text-2xl font-semibold">{me.name}</h2>
        <p className="mt-1 text-sm text-white/80">
          {me.role} · {me.ward} · {me.floor}
        </p>
      </section>

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-gray-900">7 日更表</h3>
        <p className="mt-1 text-sm text-gray-500">根據 `src/lib/data.ts` 的真資料顯示</p>
      </div>

      <div className="space-y-3">
        {myRoster?.days.map((day, idx) => (
          <div
            key={`${DAYS[idx]}-${idx}`}
            className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-gray-400">{DAYS[idx]}</p>
                <p className="mt-1 text-sm text-gray-600">{me.ward}</p>
              </div>
              <div className={`inline-flex rounded-xl px-3 py-2 text-sm font-semibold ${shiftStyle(day.type as ShiftType)}`}>
                {day.type}
              </div>
            </div>

            {day.tasks && day.tasks.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {day.tasks.map((task) => (
                  <span
                    key={task}
                    className="rounded-full bg-gray-50 px-2.5 py-1 text-xs text-gray-600 border border-gray-200"
                  >
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