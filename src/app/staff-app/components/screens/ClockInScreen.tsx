import { STAFF, KPI } from '../../../../lib/data'

export default function ClockInScreen() {
  const me = STAFF[0]
  const progress = Math.round((me.hoursWorked / me.hoursTotal) * 100)

  return (
    <div className="space-y-4">
      <section className="rounded-3xl bg-gradient-to-br from-[#e87a8e] to-[#d9657b] p-5 text-white shadow-sm">
        <p className="text-sm text-white/80">今日打卡</p>
        <h2 className="mt-2 text-2xl font-semibold">08:42</h2>
        <p className="mt-1 text-sm text-white/80">
          {me.name} · {me.role} · {me.ward}
        </p>
      </section>

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-gray-900">本月工時</h3>
        <p className="mt-1 text-sm text-gray-500">根據 `src/lib/data.ts` 的真資料顯示</p>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-gray-600">
              {me.hoursWorked} / {me.hoursTotal} 小時
            </span>
            <span className="font-semibold text-[#e87a8e]">{progress}%</span>
          </div>
          <div className="h-3 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full rounded-full bg-[#e87a8e]"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-gray-900">值班摘要</h3>
        <div className="mt-3 space-y-3">
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">員工</p>
            <p className="text-sm font-medium text-gray-800">{me.nameEn}</p>
          </div>
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">工作地點</p>
            <p className="text-sm font-medium text-gray-800">{me.ward} · {me.floor}</p>
          </div>
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">機構整體 staffing ratio</p>
            <p className="text-sm font-medium text-gray-800">{KPI.staffingRatio}</p>
          </div>
        </div>
      </div>

      <button className="w-full rounded-2xl bg-[#e87a8e] px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#d9657b]">
        下班打卡
      </button>

      <button className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm font-semibold text-gray-700 transition hover:bg-gray-50">
        查看打卡記錄
      </button>
    </div>
  )
}