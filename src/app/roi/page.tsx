'use client'

import { useState, useMemo } from 'react'

// ── Types ──────────────────────────────────────────────────────────────
interface Inputs {
  frontlineStaffCost:  number   // 前線員工月薪總和
  totalFT:             number   // 全職人數
  totalPT:             number   // 兼職人數
  managerHourlyRate:   number   // 院長/ASRN 時薪
  agencyMonthlyCost:   number   // 外購實際月費
  slIncidentsPerMonth: number   // 每月 SL/DSL 事件
  agencyReductionPct:  number   // Emma 可削減非必要外購比率
  ftRcwCount:          number   // 全職 RCW 人數
  ftRcwAvgWorkDays:    number   // FT RCW 平均出勤日
  ptRcwShiftsMonth:    number   // 本月外購 RCW 更數
}

interface ComplianceResult {
  ftShifts:    number
  maxPtShifts: number
  usagePct:    number
  remaining:   number
  status:      'safe' | 'warning' | 'over'
}

// ── Helpers ────────────────────────────────────────────────────────────
const fmt = (n: number) => `HK$${Math.round(n).toLocaleString()}`

function computeCompliance(i: Inputs): ComplianceResult {
  const ftShifts    = i.ftRcwCount * i.ftRcwAvgWorkDays
  const maxPtShifts = Math.floor(ftShifts / 2)
  const usagePct    = ftShifts > 0 ? Math.round((i.ptRcwShiftsMonth / ftShifts) * 100) : 0
  const remaining   = maxPtShifts - i.ptRcwShiftsMonth
  const status: ComplianceResult['status'] =
    usagePct >= 50 ? 'over' : usagePct >= 40 ? 'warning' : 'safe'
  return { ftShifts, maxPtShifts, usagePct, remaining, status }
}

function compute(i: Inputs) {
  const totalStaff     = i.totalFT + i.totalPT
  const emmaAnnualFee  = totalStaff * 840
  const emmaMonthlyFee = Math.round(emmaAnnualFee / 12)

  // ── 行政時間節省 ──────────────────────────────────────────────────
  // 排更: 26h/週 → 7h/週 (Emma後)
  const rosterHrsBefore   = Math.round(26 * 4.33)   // 113h/月
  const rosterHrsAfter    = Math.round(7  * 4.33)   // 30h/月
  const rosterHrSaved     = rosterHrsBefore - rosterHrsAfter  // 83h
  // 每小時節省: 院長時薪 × 25%（排更佔工作比例估算）
  const rosterSaving      = Math.round(rosterHrSaved * i.managerHourlyRate * 0.25)

  // 緊急補更: 每次事件 院長花 1h 處理 → Emma 後 0.25h
  const emergencyHrSaved  = Math.round(i.slIncidentsPerMonth * (1.0 - 0.25))
  const emergencySaving   = Math.round(emergencyHrSaved * i.managerHourlyRate)

  const totalAdminSaving  = rosterSaving + emergencySaving
  const totalAdminHrSaved = rosterHrSaved + emergencyHrSaved

  // ── 外購費用節省 ──────────────────────────────────────────────────
  // 大部分外購為 SWD 最低人手剛性需求，Emma 透過優化 FT 排更削減非必要外購
  const agencySaving = Math.round(i.agencyMonthlyCost * i.agencyReductionPct / 100)

  // ── 合計 ──────────────────────────────────────────────────────────
  const totalMonthlySaving = totalAdminSaving + agencySaving
  const annualSavings      = totalMonthlySaving * 12
  const netAnnualBenefit   = annualSavings - emmaAnnualFee
  const paybackMonths      = totalMonthlySaving > 0
    ? parseFloat((emmaAnnualFee / totalMonthlySaving).toFixed(1)) : 99
  const roiMultiple        = emmaAnnualFee > 0
    ? parseFloat((annualSavings / emmaAnnualFee).toFixed(1)) : 0

  return {
    rosterHrsBefore, rosterHrsAfter, rosterHrSaved, rosterSaving,
    emergencyHrSaved, emergencySaving, totalAdminSaving, totalAdminHrSaved,
    agencySaving, totalMonthlySaving, annualSavings, netAnnualBenefit,
    paybackMonths, roiMultiple, totalStaff, emmaAnnualFee, emmaMonthlyFee,
  }
}

// ── Sub-components ─────────────────────────────────────────────────────
function InputField({ label, value, onChange, suffix = '', hint }: {
  label: string; value: number; onChange: (v: number) => void
  suffix?: string; hint?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-500">
        {label}
        {hint && <span className="ml-1.5 text-[10px] text-slate-400">({hint})</span>}
      </label>
      <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2
                      focus-within:border-pink-400 focus-within:ring-1 focus-within:ring-pink-400/20 transition-all">
        <input
          type="number" value={value || ''}
          onChange={e => onChange(Number(e.target.value) || 0)}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-slate-800 outline-none tabular-nums"
          placeholder="0"
        />
        {suffix && <span className="text-xs text-slate-400">{suffix}</span>}
      </div>
    </div>
  )
}

function SliderField({ label, value, onChange, min, max, step = 5, hint }: {
  label: string; value: number; onChange: (v: number) => void
  min: number; max: number; step?: number; hint?: string
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-between items-center">
        <label className="text-xs font-medium text-slate-500">
          {label}
          {hint && <span className="ml-1.5 text-[10px] text-slate-400">{hint}</span>}
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

function SavingRow({ label, saving, detail, color = 'pink' }: {
  label: string; saving: number; detail: string; color?: 'pink' | 'emerald' | 'blue'
}) {
  const colors = {
    pink:    'bg-pink-50 border-pink-100 text-pink-600',
    emerald: 'bg-emerald-50 border-emerald-100 text-emerald-600',
    blue:    'bg-blue-50 border-blue-100 text-blue-600',
  }
  return (
    <div className={`flex items-center justify-between rounded-xl border px-4 py-3 ${colors[color]}`}>
      <div>
        <p className="text-sm font-semibold text-slate-800">{label}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">{detail}</p>
      </div>
      <p className={`text-base font-bold tabular-nums ${colors[color].split(' ')[2]}`}>{fmt(saving)}</p>
    </div>
  )
}

function CompliancePanel({ inputs, result }: { inputs: Inputs; result: ComplianceResult }) {
  const { ftShifts, maxPtShifts, usagePct, remaining, status } = result
  const cfg = {
    safe:    { bar: 'bg-emerald-500', border: 'border-emerald-200 bg-emerald-50', text: 'text-emerald-700', label: '✅ SWD 合規' },
    warning: { bar: 'bg-orange-400',  border: 'border-orange-200 bg-orange-50',  text: 'text-orange-700',  label: '⚠️ 接近上限' },
    over:    { bar: 'bg-red-500',     border: 'border-red-200 bg-red-50',        text: 'text-red-700',     label: '🚨 超出上限' },
  }[status]
  const barWidth = Math.min((usagePct / 50) * 100, 100)

  return (
    <div className={`rounded-2xl border p-5 ${cfg.border}`}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">外購 RCW 更數合規</p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {inputs.ftRcwCount}人 × {inputs.ftRcwAvgWorkDays}日 = <strong>{ftShifts}更</strong>；
            外購上限 = <strong>{maxPtShifts}更</strong>
          </p>
        </div>
        <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${cfg.border} ${cfg.text}`}>
          {cfg.label}
        </span>
      </div>

      <div className="mb-1 flex justify-between text-xs text-slate-500">
        <span>外購佔全職更數比率</span>
        <span className={`font-bold tabular-nums ${cfg.text}`}>{usagePct}% / 上限 50%</span>
      </div>
      <div className="relative h-3 w-full rounded-full bg-white/60 overflow-hidden mb-1">
        <div className={`h-full rounded-full transition-all duration-700 ${cfg.bar}`}
          style={{ width: `${barWidth}%` }} />
      </div>
      <p className="text-center text-[9px] text-slate-400 mb-4">← 安全區 ｜ 50% 上限 ｜ 違規 →</p>

      <div className="grid grid-cols-3 gap-2 mb-4">
        {[
          { label: '全職更數/月',   value: `${ftShifts}更` },
          { label: '外購上限(50%)', value: `${maxPtShifts}更` },
          { label: '本月外購更數',  value: `${inputs.ptRcwShiftsMonth}更` },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl bg-white/70 p-2.5 text-center">
            <p className="text-[10px] text-slate-500">{label}</p>
            <p className="text-sm font-bold text-slate-800 tabular-nums">{value}</p>
          </div>
        ))}
      </div>

      <div className={`rounded-xl px-3 py-2 text-center text-xs font-medium
        ${remaining >= 0 ? 'bg-white/60 text-slate-600' : 'bg-red-100 text-red-700'}`}>
        {remaining >= 0
          ? `尚餘 ${remaining} 更外購空間 — Emma 排更時自動提示剩餘配額`
          : `超出 ${Math.abs(remaining)} 更 — 須減少外購或向 SWD 申請豁免`}
      </div>
    </div>
  )
}
// ── Scale Slider Component ─────────────────────────────────────────────
function ScaleSlider() {
  const [staffCount, setStaffCount] = useState(50)

  const perPersonMonthly  = 788
  const emmaRatePerPerson = 840

  const monthlyTotal   = Math.round(staffCount * perPersonMonthly)
  const annualSavings  = monthlyTotal * 12
  const emmaAnnualFee  = staffCount * emmaRatePerPerson
  const emmaMonthlyFee = Math.round(emmaAnnualFee / 12)
  const netAnnual      = annualSavings - emmaAnnualFee
  const roiMultiple    = (annualSavings / emmaAnnualFee).toFixed(1)
  const paybackDays    = Math.round((emmaAnnualFee / annualSavings) * 365)

  const SCALE_DATA = [50, 100, 150, 200, 250, 300]
  const fmtS = (n: number) => `HK$${Math.round(n).toLocaleString()}`

  return (
    <div>
      <div className="mb-5">
        <div className="flex justify-between items-center mb-2">
          <label className="text-xs font-medium text-slate-600">員工人數</label>
          <span className="text-2xl font-bold tabular-nums" style={{ color: '#E8187A' }}>
            {staffCount}人
          </span>
        </div>
        <input
          type="range" min={10} max={300} step={5} value={staffCount}
          onChange={e => setStaffCount(Number(e.target.value))}
          className="w-full accent-pink-500"
        />
        <div className="flex justify-between text-[10px] text-slate-400 mt-1">
          <span>10人</span><span>150人</span><span>300人</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-5">
        {[
          { label: '每月節省',   value: fmtS(monthlyTotal),  sub: `${staffCount}人 × HK$788`,       color: 'text-pink-500'  },
          { label: 'Emma 月費', value: fmtS(emmaMonthlyFee), sub: `${staffCount}人 × HK$840 ÷ 12`, color: 'text-slate-700' },
          { label: '年度淨效益', value: fmtS(netAnnual),     sub: '年節省 − Emma 年費',             color: 'text-blue-600'  },
        ].map(k => (
          <div key={k.label} className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-center">
            <p className="text-[10px] text-slate-500 mb-1">{k.label}</p>
            <p className={`text-lg font-bold tabular-nums ${k.color}`}>{k.value}</p>
            <p className="text-[9px] text-slate-400 mt-1">{k.sub}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl p-5 mb-5 text-center" style={{ background: '#1a1a2e' }}>
        <p className="text-[11px] font-semibold tracking-widest text-white/40 mb-3">SCALE ROI SUMMARY</p>
        <div className="flex items-center justify-center gap-8">
          <div>
            <p className="text-4xl font-bold text-pink-400 tabular-nums">{roiMultiple}x</p>
            <p className="text-[10px] text-white/50 mt-1">ROI 倍數</p>
          </div>
          <div className="w-px h-12 bg-white/10" />
          <div>
            <p className="text-4xl font-bold text-emerald-400 tabular-nums">{paybackDays}</p>
            <p className="text-[10px] text-white/50 mt-1">回本天數</p>
          </div>
          <div className="w-px h-12 bg-white/10" />
          <div>
            <p className="text-3xl font-bold text-blue-400 tabular-nums">{fmtS(netAnnual)}</p>
            <p className="text-[10px] text-white/50 mt-1">年度淨效益</p>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-100">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['員工人數', '每月節省', '年度節省', 'Emma 年費', '年度淨效益', 'ROI'].map(h => (
                <th key={h} className="px-3 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wide text-left">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SCALE_DATA.map(n => {
              const monthly  = n * perPersonMonthly
              const annual   = monthly * 12
              const fee      = n * emmaRatePerPerson
              const net      = annual - fee
              const isActive = Math.abs(n - staffCount) < 30
              return (
                <tr key={n}
                  onClick={() => setStaffCount(n)}
                  className={`border-b border-slate-50 cursor-pointer transition-colors ${
                    isActive ? 'bg-pink-50' : 'hover:bg-slate-50/50'
                  }`}>
                  <td className={`px-3 py-2.5 font-bold tabular-nums ${isActive ? 'text-pink-600' : 'text-slate-700'}`}>
                    {n}人 {n === 300 && '🏆'}
                  </td>
                  <td className="px-3 py-2.5 text-slate-600 tabular-nums">{fmtS(monthly)}</td>
                  <td className="px-3 py-2.5 text-slate-600 tabular-nums">{fmtS(annual)}</td>
                  <td className="px-3 py-2.5 text-slate-500 tabular-nums">{fmtS(fee)}</td>
                  <td className={`px-3 py-2.5 font-bold tabular-nums ${isActive ? 'text-pink-600' : 'text-emerald-600'}`}>{fmtS(net)}</td>
                  <td className="px-3 py-2.5 font-bold text-blue-600">11.3x</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[10px] text-slate-400 text-center">
        * 點擊表格任意行可快速切換人數 · 規模效益供 Sales Demo 參考用途
      </p>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────
export default function ROIPage() {
  const [inputs, setInputs] = useState<Inputs>({
    frontlineStaffCost:  912220,
    totalFT:             33,
    totalPT:             16,
    managerHourlyRate:   409,    // ASRN 時薪
    agencyMonthlyCost:   148070, // March 2026 實際
    slIncidentsPerMonth: 46,     // March SL/DSL 事件
    agencyReductionPct:  15,     // 保守估計：Emma 優化FT排更削減非必要外購
    ftRcwCount:          19,
    ftRcwAvgWorkDays:    16,
    ptRcwShiftsMonth:    111,
  })

  const set = (key: keyof Inputs) => (v: number) =>
    setInputs(prev => ({ ...prev, [key]: v }))

  const r  = useMemo(() => compute(inputs), [inputs])
  const cr = useMemo(() => computeCompliance(inputs), [inputs])

  return (
    <div className="p-5 space-y-5">

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">ROI 效益計算器</h1>
          <p className="text-xs text-gray-500 mt-0.5">基於 March 2026 實際數字 · Haven Elderly Home</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-[10px] text-gray-400">ROI 倍數</div>
            <div className="text-2xl font-bold text-pink-500">{r.roiMultiple}x</div>
          </div>
          <div className="w-12 h-12 rounded-full border-4 border-pink-400 flex items-center justify-center text-[10px] font-bold text-pink-500">
            {r.paybackMonths}月
          </div>
        </div>
      </div>

      {/* ── KPI Banner ── */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: '每月節省',   value: fmt(r.totalMonthlySaving), color: 'text-pink-500'     },
          { label: '年度節省',   value: fmt(r.annualSavings),      color: 'text-emerald-600'  },
          { label: 'Emma 月費', value: fmt(r.emmaMonthlyFee),     color: 'text-slate-700'    },
          { label: '淨年度收益', value: fmt(r.netAnnualBenefit),   color: 'text-blue-600'     },
        ].map(k => (
          <div key={k.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{k.label}</div>
            <div className={`text-[20px] font-bold tabular-nums ${k.color}`}>{k.value}</div>
            <div className="w-full h-1 bg-gray-100 rounded-full mt-2" />
          </div>
        ))}
      </div>

      {/* ── Section 1: 基本數字輸入 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">👥</div>
          <h2 className="text-base font-semibold text-slate-800">員工成本基本數字</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <InputField label="前線員工成本/月"  value={inputs.frontlineStaffCost}  onChange={set('frontlineStaffCost')}  suffix="HK$" hint="March 33FT" />
          <InputField label="全職員工人數"      value={inputs.totalFT}             onChange={set('totalFT')}             suffix="人"   hint="March 33人" />
          <InputField label="兼職員工人數"      value={inputs.totalPT}             onChange={set('totalPT')}             suffix="人"   hint="March 16人" />
          <InputField label="管理層時薪"        value={inputs.managerHourlyRate}   onChange={set('managerHourlyRate')}   suffix="HK$" hint="ASRN HK$409" />
        </div>

        {/* OT 說明欄（只解釋，不計算） */}
        <div className="mt-4 rounded-xl bg-slate-50 border border-slate-200 px-4 py-3">
          <p className="text-[11px] font-semibold text-slate-600 mb-1">📌 關於OT：無現金支出，已涵蓋於行政節省內</p>
          <p className="text-[10px] text-slate-500 leading-relaxed">
            全職員工超時 → 累積 CL補鐘（無現金OT費用）。
            院長需額外行政時間追蹤CL積累及安排提早離班，
            此行政成本已計入下方「行政時間節省」項目。
            外購員工OT費用已反映在外購月費實際數字內。
          </p>
        </div>
      </div>

      {/* ── Section 2: 外購費用輸入 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-1 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">🏥</div>
          <h2 className="text-base font-semibold text-slate-800">外購費用（SWD 剛性需求 + 非必要部分）</h2>
        </div>
        <p className="text-[11px] text-slate-400 mb-4 ml-9">
          大部分外購為 SWD 最低人手剛性需求 — Emma 透過優化 FT 排更，削減<strong>非必要</strong>外購
        </p>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 mb-5">
          <InputField label="外購實際月費"      value={inputs.agencyMonthlyCost}   onChange={set('agencyMonthlyCost')}   suffix="HK$" hint="March HK$148,070" />
          <InputField label="每月 SL/DSL 事件"  value={inputs.slIncidentsPerMonth} onChange={set('slIncidentsPerMonth')} suffix="次"  hint="March 46次" />
        </div>

        <SliderField
          label="非必要外購削減幅度（Emma 優化 FT 排更後）"
          value={inputs.agencyReductionPct}
          onChange={set('agencyReductionPct')}
          min={5} max={40}
          hint="（保守估計 15%）"
        />

        {/* Agency breakdown 說明 */}
        <div className="mt-4 grid grid-cols-3 gap-3">
          {[
            { label: '剛性需求（SWD）', pct: Math.round(100 - inputs.agencyReductionPct),
              desc: '無法削減，SWD 最低人手要求', color: 'bg-slate-100 text-slate-600' },
            { label: 'Emma 可優化', pct: inputs.agencyReductionPct,
              desc: 'FT排更優化後可減少此部分', color: 'bg-pink-50 text-pink-600' },
            { label: '預計節省/月', pct: null,
              desc: fmt(Math.round(inputs.agencyMonthlyCost * inputs.agencyReductionPct / 100)),
              color: 'bg-emerald-50 text-emerald-600' },
          ].map(k => (
            <div key={k.label} className={`rounded-xl p-3 text-center ${k.color}`}>
              <p className="text-[9px] uppercase tracking-wide mb-1 opacity-70">{k.label}</p>
              <p className="text-xl font-bold tabular-nums">
                {k.pct !== null ? `${k.pct}%` : k.desc}
              </p>
              {k.pct !== null && <p className="text-[10px] opacity-70 mt-1">{k.desc}</p>}
            </div>
          ))}
        </div>
      </div>

      {/* ── Section 3: 行政時間節省明細 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">⏱️</div>
          <h2 className="text-base font-semibold text-slate-800">行政時間節省明細</h2>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-4">
          {[
            { label: '排更時間（前）', value: `${r.rosterHrsBefore}h/月`,  sub: '26h/週 × 4.33',     color: 'text-slate-500' },
            { label: '排更時間（後）', value: `${r.rosterHrsAfter}h/月`,   sub: '7h/週 × 4.33',      color: 'text-emerald-600' },
            { label: '排更節省時數',   value: `${r.rosterHrSaved}h/月`,    sub: `× HK$${inputs.managerHourlyRate} × 25%`, color: 'text-blue-600' },
            { label: '緊急事件節省',   value: `${r.emergencyHrSaved}h/月`, sub: `${inputs.slIncidentsPerMonth}次 × 0.75h`, color: 'text-blue-600' },
          ].map(k => (
            <div key={k.label} className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-center">
              <p className="text-[10px] text-slate-500 mb-1">{k.label}</p>
              <p className={`text-lg font-bold tabular-nums ${k.color}`}>{k.value}</p>
              <p className="text-[9px] text-slate-400 mt-1">{k.sub}</p>
            </div>
          ))}
        </div>

        <div className="rounded-xl bg-blue-50 border border-blue-100 px-4 py-3">
          <p className="text-[11px] text-blue-700 leading-relaxed">
            💡 <strong>行政節省計算邏輯：</strong>
            排更節省 {r.rosterHrSaved}h × HK${inputs.managerHourlyRate}/h × 25%（排更比例估算）
            + 緊急補更處理 {inputs.slIncidentsPerMonth}次 × 0.75h × HK${inputs.managerHourlyRate}/h
            = <strong>{fmt(r.totalAdminSaving)}/月</strong>（已包含CL追蹤及安排行政成本）
          </p>
        </div>
      </div>

      {/* ── Section 4: 節省總覽 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">📊</div>
          <h2 className="text-base font-semibold text-slate-800">節省總覽</h2>
        </div>
        <div className="space-y-2.5">
          <SavingRow
            label="行政時間節省"
            saving={r.totalAdminSaving}
            detail={`排更 ${r.rosterHrsBefore}h→${r.rosterHrsAfter}h（-${r.rosterHrSaved}h）+ 緊急 -${r.emergencyHrSaved}h = 共 ${r.totalAdminHrSaved}h`}
            color="blue"
          />
          <SavingRow
            label="外購費用節省（非必要部分）"
            saving={r.agencySaving}
            detail={`${fmt(inputs.agencyMonthlyCost)} × ${inputs.agencyReductionPct}%（FT排更優化，SWD剛性需求不計）`}
            color="pink"
          />
          <div className="flex items-center justify-between rounded-xl border-2 border-pink-300 bg-pink-50 px-4 py-3.5">
            <p className="text-base font-bold text-slate-800">每月總節省</p>
            <p className="text-2xl font-bold text-pink-600 tabular-nums">{fmt(r.totalMonthlySaving)}</p>
          </div>
        </div>
      </div>

      {/* ── Section 5: Emma 費用 vs 回報 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">💰</div>
          <h2 className="text-base font-semibold text-slate-800">Emma AI 費用 vs 回報</h2>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-5">
          {[
            { label: 'Emma 月費',  value: fmt(r.emmaMonthlyFee),   sub: `${r.totalStaff}人 × HK$840 ÷ 12`,   color: 'text-slate-800'   },
            { label: 'Emma 年費',  value: fmt(r.emmaAnnualFee),    sub: `${r.totalStaff}人 × HK$840/年`,      color: 'text-slate-800'   },
            { label: '年度節省',   value: fmt(r.annualSavings),    sub: '每月節省 × 12',                      color: 'text-emerald-600' },
            { label: '淨年度收益', value: fmt(r.netAnnualBenefit), sub: '年度節省 − Emma 年費',               color: 'text-blue-600'    },
          ].map(k => (
            <div key={k.label} className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-center">
              <p className="text-[10px] text-slate-500 mb-1">{k.label}</p>
              <p className={`text-lg font-bold tabular-nums ${k.color}`}>{k.value}</p>
              <p className="text-[9px] text-slate-400 mt-1">{k.sub}</p>
            </div>
          ))}
        </div>

        {/* ROI Banner */}
        <div className="rounded-2xl p-5 text-center" style={{ background: '#1a1a2e' }}>
          <p className="text-[11px] font-semibold tracking-widest text-white/40 mb-3">EMMA AI ROI SUMMARY</p>
          <div className="flex items-center justify-center gap-8">
            <div>
              <p className="text-4xl font-bold text-pink-400 tabular-nums">{r.roiMultiple}x</p>
              <p className="text-[10px] text-white/50 mt-1">回報倍數</p>
            </div>
            <div className="w-px h-12 bg-white/10" />
            <div>
              <p className="text-4xl font-bold text-emerald-400 tabular-nums">{r.paybackMonths}</p>
              <p className="text-[10px] text-white/50 mt-1">回本月數</p>
            </div>
            <div className="w-px h-12 bg-white/10" />
            <div>
              <p className="text-3xl font-bold text-blue-400 tabular-nums">{fmt(r.netAnnualBenefit)}</p>
              <p className="text-[10px] text-white/50 mt-1">淨年度收益</p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Section 6: 外購 RCW 合規監察 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">🛡️</div>
          <h2 className="text-base font-semibold text-slate-800">外購 RCW 合規監察</h2>
          <span className="ml-2 text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
            獨立監察 · 不計入 ROI
          </span>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-5">
          <InputField label="全職 RCW 人數"        value={inputs.ftRcwCount}       onChange={set('ftRcwCount')}       suffix="人" hint="March 19人" />
          <InputField label="FT RCW 平均出勤日/月" value={inputs.ftRcwAvgWorkDays} onChange={set('ftRcwAvgWorkDays')} suffix="日" hint="扣休假後實際" />
          <InputField label="本月外購 RCW 更數"    value={inputs.ptRcwShiftsMonth} onChange={set('ptRcwShiftsMonth')} suffix="更" hint="March 111更" />
        </div>
        <CompliancePanel inputs={inputs} result={cr} />
      </div>

      {/* ── Section 7: 規模效益計算器 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">📈</div>
          <h2 className="text-base font-semibold text-slate-800">規模效益計算器</h2>
          <span className="ml-auto text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
            Sales Demo 用途
          </span>
        </div>

        {/* 說明 */}
        <div className="mb-5 rounded-xl bg-blue-50 border border-blue-100 px-4 py-3">
          <p className="text-[11px] text-blue-700 leading-relaxed">
            📌 <strong>標準化公式：</strong>
            每人月節省 = HK$788（行政+外購優化）·
            Emma 年費 = 員工人數 × HK$840 ·
            ROI = 恆定 <strong>11.3x</strong>（規模越大，絕對效益越高）
          </p>
        </div>

        {/* Slider */}
        <ScaleSlider />
      </div>
    </div>
  )
}