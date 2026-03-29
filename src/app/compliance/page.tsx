export default function CompliancePage() {
  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Compliance 合規中心</h1>
          <p className="text-xs text-gray-500 mt-0.5">RCHE 法規合規狀態 · 2026 Q1</p>
        </div>
        <button className="px-3 py-1.5 text-xs rounded-lg text-white font-medium" style={{ background: '#f28f9e' }}>
          匯出報告
        </button>
      </div>

      {/* KPI Score Cards */}
      <div className="grid grid-cols-4 gap-3">
        {SCORES.map((s) => (
          <div key={s.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{s.label}</div>
            <div className="text-[28px] font-bold" style={{ color: s.score >= 90 ? '#10B981' : s.score >= 75 ? '#F59E0B' : '#f28f9e' }}>
              {s.score}%
            </div>
            <div className="w-full h-1.5 bg-gray-100 rounded-full mt-2 overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${s.score}%`, background: s.score >= 90 ? '#10B981' : s.score >= 75 ? '#F59E0B' : '#f28f9e' }} />
            </div>
            <div className="text-[10px] text-gray-400 mt-1">{s.desc}</div>
          </div>
        ))}
      </div>

      {/* 合規檢查清單 */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100">
          <div className="text-sm font-semibold text-gray-900">合規檢查清單</div>
        </div>
        {CHECKLIST.map((item, i) => (
          <div key={i} className="px-4 py-3 border-b border-gray-50 flex items-center justify-between hover:bg-gray-50">
            <div className="flex items-center gap-3">
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] text-white flex-shrink-0"
                style={{ background: item.status === 'pass' ? '#10B981' : item.status === 'warn' ? '#F59E0B' : '#f28f9e' }}
              >
                {item.status === 'pass' ? '✓' : item.status === 'warn' ? '!' : '✕'}
              </div>
              <div>
                <div className="text-xs font-medium text-gray-900">{item.title}</div>
                <div className="text-[10px] text-gray-400">{item.desc}</div>
              </div>
            </div>
            <span
              className="text-[9px] px-2 py-0.5 rounded-full text-white"
              style={{ background: item.status === 'pass' ? '#10B981' : item.status === 'warn' ? '#F59E0B' : '#f28f9e' }}
            >
              {item.status === 'pass' ? '合格' : item.status === 'warn' ? '待處理' : '不合格'}
            </span>
          </div>
        ))}
      </div>

      {/* 人手比例合規狀態 */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100">
          <div className="text-sm font-semibold text-gray-900">人手比例合規狀態</div>
        </div>

        {STAFFING_RATIO_SHIFTS.map((shift) => (
          <div key={shift.label} className="px-4 py-3 border-b border-gray-50 last:border-b-0">
            <div className="text-xs font-semibold text-gray-700 mb-2">{shift.label}</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
              {shift.ratios.map((r) => (
                <div key={r} className="flex items-center gap-1.5">
                  <span className="text-[13px] leading-none" style={{ color: '#10B981' }}>✓</span>
                  <span className="text-[11px] text-gray-700 font-medium">{r}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ─── Data ─────────────────────────────────────── */

const SCORES = [
  { label: 'Staffing Ratio',      score: 94,  desc: '符合 1:6 標準' },
  { label: 'Staff Certification', score: 88,  desc: '2 項證書即將到期' },
  { label: 'Documentation',       score: 76,  desc: '部分 ICP 未更新' },
  { label: 'Incident Reports',    score: 100, desc: '本月零事故' },
]

const CHECKLIST = [
  { title: 'ICP 護理計劃更新',    desc: '3 名住客 ICP 超過 30 天未更新',      status: 'warn' },
  { title: 'ACLS 證書 — 余逸詩', desc: '將於 28 天後到期',                   status: 'warn' },
  { title: '藥物紀錄核對',        desc: '本月所有藥物紀錄已核對',              status: 'pass' },
  { title: '消防演習紀錄',        desc: '上季度消防演習已完成',                status: 'pass' },
  { title: '感染控制巡查',        desc: '本月巡查未完成',                      status: 'fail' },
]

const STAFFING_RATIO_SHIFTS = [
  {
    label: '早更 A (0700-1500)',
    ratios: ['RN 1:60', 'EN 1:60', 'HW 1:30', 'CW 1:20', 'AW 1:40'],
  },
  {
    label: '午更 P (1330-2130)',
    ratios: ['RN 1:60', 'EN 1:60', 'HW 1:30', 'CW 1:20', 'AW 1:40'],
  },
  {
    label: '夜更 N (2130-0700)',
    ratios: ['EN 1:60', 'HW 1:30', 'CW 1:40'],
  },
]