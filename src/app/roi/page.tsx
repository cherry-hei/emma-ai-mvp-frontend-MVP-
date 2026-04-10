'use client'

import { useState, useMemo } from 'react'

interface Inputs {
  frontlineStaffCost: number
  totalFT: number
  totalPT: number
  managerHourlyRate: number
  monthlyOTHours: number
  agencyMonthlyCost: number
  slIncidentsPerMonth: number
  otReductionPct: number
  agencyReductionPct: number
  ftRcwCount: number
  ftRcwAvgWorkDays: number
  ptRcwShiftsMonth: number
}

function compute(inputs: Inputs) {
  const {
    frontlineStaffCost, totalFT, totalPT,
    agencyMonthlyCost, managerHourlyRate,
    monthlyOTHours, agencyReductionPct, otReductionPct,
    slIncidentsPerMonth,
  } = inputs

  const totalStaff     = totalFT + totalPT
  const emmaAnnualFee  = totalStaff * 840
  const emmaMonthlyFee = Math.round(emmaAnnualFee / 12)

  const rosterHrsBefore = Math.round(26 * 4.33)
  const rosterHrsAfter  = Math.round(7  * 4.33)
  const rosterHrSaved   = rosterHrsBefore - rosterHrsAfter
  const rosterSaving    = Math.round(rosterHrSaved * managerHourlyRate)

  const emergencyHrSaved = Math.round(slIncidentsPerMonth * 0.75)
  const emergencySaving  = Math.round(emergencyHrSaved * managerHourlyRate)

  const totalAdminSaving  = rosterSaving + emergencySaving
  const totalAdminHrSaved = rosterHrSaved + emergencyHrSaved

  const avgHourlyRate    = totalFT > 0 ? Math.round(frontlineStaffCost / totalFT / 173) : 0
  const otReductionHours = Math.round(monthlyOTHours * (otReductionPct / 100))
  const otSaving         = Math.round(otReductionHours * avgHourlyRate * 1.5)
  const otAfter          = monthlyOTHours - otReductionHours

  const agencySaving = Math.round(agencyMonthlyCost * (agencyReductionPct / 100))

  const totalMonthlySaving = totalAdminSaving + otSaving + agencySaving
  const annualSavings      = totalMonthlySaving * 12
  const netAnnualBenefit   = annualSavings - emmaAnnualFee
  const paybackMonths      = totalMonthlySaving > 0
    ? parseFloat((emmaAnnualFee / totalMonthlySaving).toFixed(1)) : 99
  const roiMultiple = emmaAnnualFee > 0
    ? (annualSavings / emmaAnnualFee).toFixed(1) : '0'

  return {
    rosterHrsBefore, rosterHrsAfter, rosterHrSaved, rosterSaving,
    emergencyHrSaved, emergencySaving,
    totalAdminSaving, totalAdminHrSaved,
    avgHourlyRate, otReductionHours, otAfter, otSaving,
    agencySaving,
    totalMonthlySaving, annualSavings, netAnnualBenefit,
    paybackMonths, roiMultiple,
    totalStaff, emmaAnnualFee, emmaMonthlyFee,
    monthlyOTHours,
  }
}

interface ComplianceResult {
  ftShifts: number
  maxPtShifts: number
  usagePct: number
  remaining: number
  status: 'safe' | 'warning' | 'over'
}

function computeCompliance(inputs: Inputs): ComplianceResult {
  const ftShifts    = inputs.ftRcwCount * inputs.ftRcwAvgWorkDays
  const maxPtShifts = Math.floor(ftShifts / 2)
  const usagePct    = ftShifts > 0
    ? Math.round((inputs.ptRcwShiftsMonth / ftShifts) * 100) : 0
  const remaining = maxPtShifts - inputs.ptRcwShiftsMonth
  const status: ComplianceResult['status'] =
    usagePct >= 50 ? 'over' : usagePct >= 40 ? 'warning' : 'safe'
  return { ftShifts, maxPtShifts, usagePct, remaining, status }
}

const fmt = (n: number) => `HK$${n.toLocaleString()}`

function InputField({
  label, value, onChange, prefix = '', suffix = '', hint,
}: {
  label: string; value: number; onChange: (v: number) => void
  prefix?: string; suffix?: string; hint?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-500">
        {label}
        {hint && <span className="ml-1.5 text-[10px] font-normal text-slate-400">({hint})</span>}
      </label>
      <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 focus-within:border-pink-400 focus-within:ring-1 focus-within:ring-pink-400/20 transition-all">
        {prefix && <span className="text-sm text-slate-400">{prefix}</span>}
        <input
          type="number"
          value={value || ''}
          onChange={e => onChange(Number(e.target.value) || 0)}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-slate-800 outline-none tabular-nums"
          placeholder="0"
        />
        {suffix && <span className="text-xs text-slate-400">{suffix}</span>}
      </div>
    </div>
  )
}

function SliderField({
  label, value, onChange, min, max, step = 5, hint,
}: {
  label: string; value: number; onChange: (v: number) => void
  min: number; max: number; step?: number; hint?: string
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-between items-center">
        <label className="text-xs font-medium text-slate-500">
          {label}
          {hint && <span className="ml-1.5 text-[10px] text-slate-400">({hint})</span>}
        </label>
        <span className="text-sm font-bold text-pink-500 tabular-nums">{value}%</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-pink-500"
      />
      <div className="flex justify-between text-[10px] text-slate-400">
        <span>{min}%</span><span>{max}%</span>
      </div>
    </div>
  )
}

function BarMetric({
  label, before, after, unit = 'h', color = 'bg-pink-400',
}: {
  label: string; before: number; after: number; unit?: string; color?: string
}) {
  const pct = before > 0 ? Math.round((after / before) * 100) : 0
  return (
    <div className="space-y-1.5">
      <div className="flex items-end justify-between">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-400 line-through">{before}{unit}</span>
          <span className="font-semibold text-pink-500">{after}{unit}</span>
        </div>
      </div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div className={`${color} h-full rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-right text-[11px] text-slate-400">優化後 {pct}% 工時</p>
    </div>
  )
}

function KpiCard({
  label, value, sub, accent = false,
}: {
  label: string; value: string; sub?: string; accent?: boolean
}) {
  return (
    <div className={`rounded-2xl border p-4 ${accent ? 'border-pink-200 bg-pink-50' : 'border-slate-200 bg-white'}`}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${accent ? 'text-pink-600' : 'text-slate-800'}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-slate-400">{sub}</p>}
    </div>
  )
}

function SavingRow({
  icon, label, formula, monthly, annual,
}: {
  icon: string; label: string; formula: string; monthly: number; annual: number
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3.5">
      <span className="text-xl">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-slate-800">{label}</p>
        <p className="mt-0.5 text-[11px] text-slate-400 leading-relaxed">{formula}</p>
      </div>
      <div className="text-right shrink-0">
        <p className="text-sm font-bold text-pink-500">{fmt(monthly)}<span className="text-[10px] font-normal text-slate-400">/月</span></p>
        <p className="text-[11px] text-slate-500">{fmt(annual)}/年</p>
      </div>
    </div>
  )
}

function CompliancePanel({ inputs, result }: { inputs: Inputs; result: ComplianceResult }) {
  const { ftShifts, maxPtShifts, usagePct, remaining, status } = result
  const cfg = {
    safe:    { bar: 'bg-emerald-500', border: 'border-emerald-200 bg-emerald-50', text: 'text-emerald-700', label: '✅ 符合 SWD 規定' },
    warning: { bar: 'bg-orange-400',  border: 'border-orange-200 bg-orange-50',  text: 'text-orange-700',  label: '⚠️ 接近上限，建議留意' },
    over:    { bar: 'bg-red-500',     border: 'border-red-200 bg-red-50',        text: 'text-red-700',     label: '🚨 超出 SWD 上限' },
  }[status]
  const barWidth = Math.min((usagePct / 50) * 100, 100)

  return (
    <div className={`rounded-2xl border p-5 ${cfg.border}`}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">外購 RCW 合規狀態</p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            監察工具 — 此欄為 SWD 合規監察，<strong>不計入 ROI 節省計算</strong>
          </p>
        </div>
        <span className={`text-xs font-bold px-2.5 py-1 rounded-full bg-white/70 ${cfg.text}`}>
          {cfg.label}
        </span>
      </div>
      <div className="mb-1 flex justify-between text-xs text-slate-500">
        <span>外購佔全職更數比率</span>
        <span className={`font-bold tabular-nums ${cfg.text}`}>{usagePct}% / 上限 50%</span>
      </div>
      <div className="relative h-3 w-full rounded-full bg-white/60 overflow-hidden mb-1">
        <div className={`h-full rounded-full transition-all duration-700 ${cfg.bar}`} style={{ width: `${barWidth}%` }} />
      </div>
      <p className="text-center text-[9px] text-slate-400 mb-4">← 安全區 ｜ 50% 上限 ｜ 違規 →</p>
      <div className="grid grid-cols-3 gap-2 mb-4">
        {[
          { label: '全職更數/月', value: `${ftShifts}更` },
          { label: '外購上限 (50%)', value: `${maxPtShifts}更` },
          { label: '本月外購更數', value: `${inputs.ptRcwShiftsMonth}更` },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl bg-white/70 p-2.5 text-center">
            <p className="text-[10px] text-slate-500">{label}</p>
            <p className="text-sm font-bold text-slate-800 tabular-nums">{value}</p>
          </div>
        ))}
      </div>
      <div className={`rounded-xl px-3 py-2 text-center text-xs font-medium ${remaining >= 0 ? 'bg-white/60 text-slate-600' : 'bg-red-100 text-red-700'}`}>
        {remaining >= 0
          ? `尚餘 ${remaining} 更外購空間 — Emma 在排更時自動提示剩餘配額`
          : `超出 ${Math.abs(remaining)} 更 — 須減少外購或向 SWD 申請豁免`}
      </div>
      <div className="mt-3 rounded-xl bg-white/50 px-3 py-2.5 space-y-1">
        <p className="text-[11px] font-semibold text-slate-700">📋 SWD 規定說明</p>
        <ul className="text-[10px] text-slate-500 leading-relaxed space-y-0.5 list-disc list-inside">
          <li>外購更數 ≤ 全職更數 × 50%（按<strong>更數</strong>計算，非人頭）</li>
          <li>外購只可做：餵食、換片、沖涼、轉移</li>
          <li>外購只可編 A更 / P更 / N更</li>
          <li>上限：2名 HW/EN 外購；12名 CW 外購</li>
        </ul>
        <p className="text-[10px] text-slate-400 leading-relaxed mt-1">
          計算：{inputs.ftRcwCount}人 × {inputs.ftRcwAvgWorkDays}日 = {ftShifts}更（全職）；
          上限 = {ftShifts} × 50% = {maxPtShifts}更；
          本月外購 {inputs.ptRcwShiftsMonth}更 = {usagePct}%
        </p>
      </div>
    </div>
  )
}

export default function ROIPage() {
  const [inputs, setInputs] = useState<Inputs>({
    frontlineStaffCost: 912220,
    totalFT: 33,
    totalPT: 16,
    managerHourlyRate: 409,
    monthlyOTHours: 55,
    agencyMonthlyCost: 148070,
    slIncidentsPerMonth: 46,
    otReductionPct: 30,
    agencyReductionPct: 15,
    ftRcwCount: 19,
    ftRcwAvgWorkDays: 16,
    ptRcwShiftsMonth: 111,
  })

  const set = (key: keyof Inputs) => (v: number) =>
    setInputs(prev => ({ ...prev, [key]: v }))

  const r  = useMemo(() => compute(inputs), [inputs])
  const cr = useMemo(() => computeCompliance(inputs), [inputs])

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      <div className="border-b border-slate-200 bg-white px-6 py-5">
        <div className="mx-auto max-w-4xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-pink-500">Emma AI</p>
          <h1 className="mt-1 text-xl font-semibold text-slate-800">ROI 效益模擬器</h1>
          <p className="mt-1 text-sm text-slate-500">輸入你的機構數字，即時計算 Emma AI 能為你節省的成本與行政時間</p>
        </div>
      </div>

      <div className="mx-auto max-w-4xl space-y-6 px-6 py-6">

        {/* S1 */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">✏️</div>
            <h2 className="text-base font-semibold text-slate-800">機構基本資料</h2>
          </div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">人員成本</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-5">
            <InputField label="FT員工總月薪" value={inputs.frontlineStaffCost} onChange={set('frontlineStaffCost')} prefix="HK$" />
            <InputField label="AS/RN 時薪" value={inputs.managerHourlyRate} onChange={set('managerHourlyRate')} prefix="HK$" hint="行政節省計算用" />
            <InputField label="全職員工人數" value={inputs.totalFT} onChange={set('totalFT')} suffix="人" />
            <InputField label="兼職員工人數" value={inputs.totalPT} onChange={set('totalPT')} suffix="人" />
          </div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">運營參數</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-5">
            <InputField label="每月OT工時" value={inputs.monthlyOTHours} onChange={set('monthlyOTHours')} suffix="小時" hint="March實際 54.5h" />
            <InputField label="外購實際月費" value={inputs.agencyMonthlyCost} onChange={set('agencyMonthlyCost')} prefix="HK$" hint="March實際 148,070" />
            <InputField label="每月SL/DSL事件數" value={inputs.slIncidentsPerMonth} onChange={set('slIncidentsPerMonth')} suffix="宗" hint="March實際 46宗" />
          </div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">AI 優化假設</p>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <SliderField label="OT 減少比率" value={inputs.otReductionPct} onChange={set('otReductionPct')} min={10} max={60} hint="預設 30%" />
            <SliderField label="外購費減少比率" value={inputs.agencyReductionPct} onChange={set('agencyReductionPct')} min={5} max={40} hint="保守估算，85%為SWD剛性需求" />
          </div>
          <div className="mt-4 rounded-xl bg-pink-50 px-4 py-3">
            <p className="text-xs text-pink-600">
              💡 加權平均時薪：HK${r.avgHourlyRate}/hr（{inputs.frontlineStaffCost.toLocaleString()} ÷ {inputs.totalFT}人 ÷ 173h）．
              Emma年費：{r.totalStaff}人 × HK$840 = <strong>HK${r.emmaAnnualFee.toLocaleString()}</strong>
            </p>
          </div>
        </section>

        {/* S2 */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-slate-800">效率提升指標</h2>
          <div className="space-y-5">
            <BarMetric label="每月排班行政工時" before={r.rosterHrsBefore} after={r.rosterHrsAfter} color="bg-pink-400" />
            <div className="border-t border-slate-100 pt-4">
              <BarMetric
                label={`緊急替更處理（${inputs.slIncidentsPerMonth}宗 × 1h → 0.25h）`}
                before={inputs.slIncidentsPerMonth}
                after={Math.round(inputs.slIncidentsPerMonth * 0.25)}
                color="bg-rose-400"
              />
            </div>
            <div className="border-t border-slate-100 pt-4">
              <BarMetric label="每月OT超時工時" before={inputs.monthlyOTHours} after={r.otAfter} color="bg-orange-400" />
            </div>
          </div>
        </section>

        {/* S3 */}
        <section>
          <h2 className="mb-3 text-base font-semibold text-slate-700">每月節省概覽</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <KpiCard label="行政時間節省" value={fmt(r.totalAdminSaving)} sub={`節省 ${r.totalAdminHrSaved}h/月`} accent />
            <KpiCard label="OT 成本節省" value={fmt(r.otSaving)} sub="每月" accent />
            <KpiCard label="外購成本節省" value={fmt(r.agencySaving)} sub="每月" accent />
            <KpiCard label="Emma 月費" value={fmt(r.emmaMonthlyFee)} sub={`${r.totalStaff}人 × HK$70`} />
          </div>
        </section>

        {/* S4 */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-base font-semibold text-slate-800">節省成本拆解</h2>
          <div className="space-y-2.5">
            <SavingRow
              icon="📋"
              label="排更行政節省"
              formula={`${r.rosterHrsBefore}h → ${r.rosterHrsAfter}h/月，節省 ${r.rosterHrSaved}h × HK$${inputs.managerHourlyRate}/hr（AS/RN時薪）`}
              monthly={r.rosterSaving}
              annual={r.rosterSaving * 12}
            />
            <SavingRow
              icon="🚨"
              label="緊急替更節省"
              formula={`${inputs.slIncidentsPerMonth}宗 × 0.75h節省 = ${r.emergencyHrSaved}h × HK$${inputs.managerHourlyRate}/hr`}
              monthly={r.emergencySaving}
              annual={r.emergencySaving * 12}
            />
            <SavingRow
              icon="⏰"
              label="OT 成本節省"
              formula={`${inputs.monthlyOTHours}h × ${inputs.otReductionPct}% = ${r.otReductionHours}h × HK$${r.avgHourlyRate}/hr × 1.5x`}
              monthly={r.otSaving}
              annual={r.otSaving * 12}
            />
            <SavingRow
              icon="👥"
              label="外購成本節省"
              formula={`HK$${inputs.agencyMonthlyCost.toLocaleString()} × ${inputs.agencyReductionPct}%（保守估算，85%為SWD剛性需求）`}
              monthly={r.agencySaving}
              annual={r.agencySaving * 12}
            />
            <div className="flex items-center justify-between rounded-xl border-2 border-pink-200 bg-pink-50 px-4 py-3">
              <p className="text-sm font-bold text-slate-800">每月總節省</p>
              <div className="text-right">
                <p className="text-lg font-bold text-pink-600">{fmt(r.totalMonthlySaving)}<span className="text-xs font-normal text-slate-400">/月</span></p>
                <p className="text-xs text-slate-500">{fmt(r.annualSavings)}/年</p>
              </div>
            </div>
          </div>
        </section>

        {/* S5 */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <span className="text-lg">🛡️</span>
            <div>
              <h2 className="text-base font-semibold text-slate-800">外購 RCW 合規檢查</h2>
              <p className="text-[11px] text-slate-400">SWD監察工具 — 此欄<strong>不計入</strong> ROI 節省</p>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-4">
            <InputField label="全職RCW人數" value={inputs.ftRcwCount} onChange={set('ftRcwCount')} suffix="人" />
            <InputField label="FT RCW平均出勤日/月" value={inputs.ftRcwAvgWorkDays} onChange={set('ftRcwAvgWorkDays')} suffix="日" hint="扣休假後" />
            <InputField label="本月外購RCW更數" value={inputs.ptRcwShiftsMonth} onChange={set('ptRcwShiftsMonth')} suffix="更" />
          </div>
          <CompliancePanel inputs={inputs} result={cr} />
        </section>

        {/* S6 */}
        <section className="rounded-2xl border-2 border-pink-200 bg-gradient-to-br from-pink-50 to-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <span className="text-xl">📈</span>
            <h2 className="text-base font-semibold text-slate-800">預計成效 Projected Results</h2>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-2xl bg-white p-5 text-center shadow-sm">
              <p className="text-xs font-medium text-slate-500">年度總節省</p>
              <p className="mt-2 text-3xl font-bold tabular-nums text-pink-500">{fmt(r.annualSavings)}</p>
              <p className="mt-1 text-xs text-slate-400">Annual Savings</p>
            </div>
            <div className="rounded-2xl bg-white p-5 text-center shadow-sm">
              <p className="text-xs font-medium text-slate-500">回本期</p>
              <p className="mt-2 text-3xl font-bold tabular-nums text-orange-500">{r.paybackMonths} 個月</p>
              <p className="mt-1 text-xs text-slate-400">Payback Period</p>
            </div>
            <div className="rounded-2xl bg-white p-5 text-center shadow-sm">
              <p className="text-xs font-medium text-slate-500">年度淨效益</p>
              <p className={`mt-2 text-3xl font-bold tabular-nums ${r.netAnnualBenefit >= 0 ? 'text-pink-500' : 'text-red-500'}`}>
                {r.netAnnualBenefit >= 0 ? '+' : ''}{fmt(r.netAnnualBenefit)}
              </p>
              <p className="mt-1 text-xs text-slate-400">Net Annual Benefit</p>
            </div>
          </div>
          <div className="mt-4 rounded-xl border border-pink-100 bg-white px-4 py-3 flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-500">Emma AI 年費</p>
              <p className="text-sm font-bold text-slate-700">{r.totalStaff} 人 × HK$840 = {fmt(r.emmaAnnualFee)}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-500">每月攤分</p>
              <p className="text-sm font-bold text-slate-700">{fmt(r.emmaMonthlyFee)}/月</p>
            </div>
          </div>
          <div className="mt-4 rounded-xl bg-pink-500 px-4 py-3 text-center">
            <p className="text-sm font-semibold text-white">
              每投入 HK$1，Emma AI 預計回報{' '}
              <span className="text-yellow-300">{r.roiMultiple}x ROI</span>
            </p>
          </div>
        </section>

      </div>
    </div>
  )
}