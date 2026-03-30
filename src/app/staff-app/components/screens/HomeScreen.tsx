import { STAFF, ROSTER, KPI } from '../../../../lib/data'

export default function HomeScreen() {
  const me = STAFF[0]
  const myRoster = ROSTER.find((row) => row.staffId === me.id)
  const todayShift = myRoster?.days?.[0]
  const pendingTasks = todayShift?.tasks ?? []
  const progress = Math.round((me.hoursWorked / me.hoursTotal) * 100)

  return (
    <div className="space-y-5">
      <section className="rounded-3xl bg-gradient-to-br from-[#e87a8e] to-[#d9657b] p-5 text-white shadow-sm">
        <p className="text-sm text-white/80">今日值班</p>
        <div className="mt-2 flex items-end justify-between">
          <div>
            <h2 className="text-2xl font-semibold">{todayShift?.type ?? 'OFF'}</h2>
            <p className="mt-1 text-sm text-white/80">
              {me.name} · {me.role} · {me.ward}
            </p>
          </div>
          <div className="rounded-2xl bg-white/20 px-3 py-2 text-right">
            <p className="text-xs text-white/80">待辦工作</p>
            <p className="text-lg font-semibold">{pendingTasks.length}</p>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-gray-400">本月工時進度</p>
          <p className="mt-2 text-2xl font-semibold text-gray-900">{progress}%</p>
          <p className="mt-1 text-xs text-[#e87a8e]">
            {me.hoursWorked}/{me.hoursTotal} 小時
          </p>
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-gray-400">機構 staffing ratio</p>
          <p className="mt-2 text-2xl font-semibold text-gray-900">{KPI.staffingRatio}</p>
          <p className="mt-1 text-xs text-gray-500">Emergency {KPI.emergencyResponseTime}</p>
        </div>
      </section>

      <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">今日重點工作</h3>
          <span className="rounded-full bg-[#fdecef] px-2.5 py-1 text-xs font-medium text-[#e87a8e]">
            {pendingTasks.length} 項
          </span>
        </div>

        {pendingTasks.length > 0 ? (
          <div className="space-y-3">
            {pendingTasks.map((task) => (
              <div
                key={task}
                className="flex items-center gap-3 rounded-2xl bg-gray-50 px-3 py-3"
              >
                <div className="h-3 w-3 rounded-full bg-[#e87a8e]" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-gray-800">{task}</p>
                  <p className="text-xs text-gray-400">{todayShift?.type ?? 'Shift'}</p>
                </div>
                <span className="rounded-full bg-[#fdecef] px-2 py-1 text-[11px] font-medium text-[#e87a8e]">
                  待處理
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-2xl bg-gray-50 px-4 py-6 text-center text-sm text-gray-500">
            今日沒有指定工作
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-gray-900">快速摘要</h3>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">OT Hours</p>
            <p className="text-sm font-medium text-gray-800">{KPI.otHours}</p>
          </div>
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">Completion</p>
            <p className="text-sm font-medium text-gray-800">{KPI.completion}%</p>
          </div>
        </div>
      </section>
    </div>
  )
}