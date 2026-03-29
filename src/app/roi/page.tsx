import { KPI } from '@/lib/data'

export default function ROIPage() {
  return (
    <div className="p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">ROI 效益分析</h1>
          <p className="text-xs text-gray-500 mt-0.5">Emma AI 成本效益 · 2025 Q1</p>
        </div>
        <button
          className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
          style={{ background: '#f28f9e' }}
        >
          匯出報告
        </button>
      </div>

      {/* Main KPI cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white border border-gray-200 rounded-xl p-4 col-span-1">
          <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">OT 成本節省</div>
          <div className="text-[28px] font-bold text-gray-900">HK${KPI.otCost.toLocaleString()}</div>
          <div className="text-[10px] mt-0.5 text-pink-600">▼ {Math.abs(KPI.otDelta)}% vs 上月</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 col-span-1">
          <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">外判成本節省</div>
          <div className="text-[28px] font-bold text-gray-900">HK${KPI.agencyCost.toLocaleString()}</div>
          <div className="text-[10px] mt-0.5 text-pink-600">▼ {Math.abs(KPI.agencyDelta)}% vs 上月</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 col-span-1">
          <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">行政時間節省</div>
          <div className="text-[28px] font-bold text-gray-900">{KPI.adminSaved}h</div>
          <div className="text-[10px] mt-0.5 text-emerald-600">▲ 每月節省</div>
        </div>
      </div>

      {/* Breakdown table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100">
          <div className="text-sm font-semibold text-gray-900">效益明細</div>
        </div>
        {BREAKDOWN.map((item, i) => (
          <div key={i} className="px-4 py-3 border-b border-gray-50 flex items-center justify-between hover:bg-gray-50">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm" style={{ background: '#FFF0F6' }}>
                {item.icon}
              </div>
              <div>
                <div className="text-xs font-medium text-gray-900">{item.title}</div>
                <div className="text-[10px] text-gray-400">{item.desc}</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm font-bold text-gray-900">{item.value}</div>
              <div className={`text-[10px] ${item.positive ? 'text-emerald-600' : 'text-pink-600'}`}>
                {item.delta}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const BREAKDOWN = [
  { icon: '⏱', title: 'OT 超時工時', desc: '本月總超時工時', value: `${284}h`, delta: '▼ 18% vs 上月', positive: false },
  { icon: '🏥', title: '外判更數', desc: '本月外判班次總數', value: '12 shifts', delta: '▼ 31% vs 上月', positive: false },
  { icon: '📋', title: '更表完成率', desc: 'AI 自動排班完成率', value: '94%', delta: '▲ 6% vs 上月', positive: true },
  { icon: '👩‍💼', title: '行政時間節省', desc: '每月排班行政工時', value: '62h', delta: '▲ 持續改善', positive: true },
  { icon: '📊', title: '人手比例', desc: '平均住客護理比例', value: '1:6.2', delta: '符合 RCHE 標準', positive: true },
]