import { KPI } from '@/lib/data'
import { useLang } from '@/components/layout/LanguageContext'

interface KPICardProps {
  label: string
  value: string | number
  unit?: string
  delta?: number
  vsLabel: string
}

function KPICard({ label, value, unit, delta, vsLabel }: KPICardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-4 py-3 flex-1">
      <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-[22px] font-bold text-gray-900">{value}{unit}</div>
      {delta !== undefined && (
        <div className={`text-[10px] mt-0.5 ${delta < 0 ? 'text-pink-600' : 'text-emerald-600'}`}>
          {delta < 0 ? '▼' : '▲'} {Math.abs(delta)}% {vsLabel}
        </div>
      )}
    </div>
  )
}

export function KPIStrip() {
  const { lang } = useLang()

  const labels = lang === 'zh'
    ? {
        staffing:   '人手比例',
        emergency:  '緊急響應',
        ot:         '超時工時',
        agency:     '外判更數',
        completion: '完成率',
        vs:         'vs 上月',
      }
    : {
        staffing:   'Staffing Ratio',
        emergency:  'Emergency Response',
        ot:         'OT Hours',
        agency:     'Agency Shifts',
        completion: 'Completion',
        vs:         'vs last month',
      }

  return (
    <div className="flex gap-2.5 px-5 py-2.5 bg-gray-50 border-b border-gray-200">
      <KPICard label={labels.staffing}   value={KPI.staffingRatio}           vsLabel={labels.vs} />
      <KPICard label={labels.emergency}  value={KPI.emergencyResponseTime}   vsLabel={labels.vs} />
      <KPICard label={labels.ot}         value={KPI.otHours}       unit="h"  delta={KPI.otDelta}     vsLabel={labels.vs} />
      <KPICard label={labels.agency}     value={KPI.agencyShifts}            delta={KPI.agencyDelta} vsLabel={labels.vs} />
      <KPICard label={labels.completion} value={KPI.completion}    unit="%"  vsLabel={labels.vs} />
    </div>
  )
}