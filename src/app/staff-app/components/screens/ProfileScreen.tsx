import { STAFF } from '../../../../lib/data'

export default function ProfileScreen() {
  const me = STAFF[0]
  const progress = Math.round((me.hoursWorked / me.hoursTotal) * 100)

  return (
    <div className="space-y-4">
      <div className="rounded-3xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#e87a8e] text-2xl font-bold text-white">
            {me.avatar}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900">{me.name}</h3>
            <p className="text-sm text-gray-500">
              {me.role} · {me.ward} · {me.floor}
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h4 className="text-sm font-semibold text-gray-900">我的資料</h4>
        <div className="mt-3 space-y-3">
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">英文名</p>
            <p className="text-sm font-medium text-gray-800">{me.nameEn}</p>
          </div>

          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">工作地點</p>
            <p className="text-sm font-medium text-gray-800">
              {me.ward} · {me.floor}
            </p>
          </div>

          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">本月工時</p>
            <p className="text-sm font-medium text-gray-800">
              {me.hoursWorked} / {me.hoursTotal} 小時
            </p>
          </div>

          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs text-gray-400">工時進度</p>
              <p className="text-xs font-semibold text-[#e87a8e]">{progress}%</p>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-gray-200">
              <div
                className="h-full rounded-full bg-[#e87a8e]"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">專業資格</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {me.certs.map((cert) => (
                <span
                  key={cert}
                  className="rounded-full border border-[#f3c7cf] bg-[#fdecef] px-2.5 py-1 text-xs font-medium text-[#e87a8e]"
                >
                  {cert}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <button className="w-full rounded-2xl bg-[#e87a8e] px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#d9657b]">
        編輯個人資料
      </button>

      <button className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm font-semibold text-gray-700 transition hover:bg-gray-50">
        查看工時詳情
      </button>
    </div>
  )
}