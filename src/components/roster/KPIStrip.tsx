import { KPI } from '@/lib/data'

interface KPICardProps {
  label: string
  value: string | number
  unit?: string
  delta?: number
}

function KPICard({ label, value, unit, delta }: KPICardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-4 py-3 flex-1">
      <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-[22px] font-bold text-gray-900">{value}{unit}</div>
      {delta !== undefined && (
        <div className={`text-[10px] mt-0.5 ${delta < 0 ? 'text-pink-600' : 'text-emerald-600'}`}>
          {delta < 0 ? '▼' : '▲'} {Math.abs(delta)}% vs 上月
        </div>
      )}
    </div>
  )
}

export function KPIStrip() {
  return (
    <div className="flex gap-2.5 px-5 py-2.5 bg-gray-50 border-b border-gray-200">
      <KPICard label="Staffing Ratio" value={KPI.staffingRatio} />
      <KPICard label="Emergency Response" value={KPI.emergencyResponseTime} />
      <KPICard label="OT Hours" value={KPI.otHours} unit="h" delta={KPI.otDelta} />
      <KPICard label="Agency Shifts" value={KPI.agencyShifts} delta={KPI.agencyDelta} />
      <KPICard label="Completion" value={KPI.completion} unit="%" />
    </div>
  )
}