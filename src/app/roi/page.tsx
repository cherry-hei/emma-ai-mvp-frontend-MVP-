'use client'

import { useState, useMemo } from 'react'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

// ── Tier pricing (5yr contract default) ──────────────────────
// Tier 1: ≤500   → HK$45/user/mo
// Tier 2: ≤800   → HK$42/user/mo
// Tier 3: ≤1,200 → HK$39/user/mo
// Tier 4: ≤1,700 → HK$36/user/mo
// Tier 4+: >1,700→ HK$33/user/mo
const TIER_DEFS = [
  { tier: 1, label: '300–500',     max: 500,  rates: { '3yr': 48, '5yr': 45, '10yr': 42 } },
  { tier: 2, label: '501–800',     max: 800,  rates: { '3yr': 45, '5yr': 42, '10yr': 39 } },
  { tier: 3, label: '801–1,200',   max: 1200, rates: { '3yr': 42, '5yr': 39, '10yr': 36 } },
  { tier: 4, label: '1,201–1,700', max: 1700, rates: { '3yr': 39, '5yr': 36, '10yr': 33 } },
] as const

function getTierDef(n: number) {
  return TIER_DEFS.find(t => n <= t.max) ?? TIER_DEFS[TIER_DEFS.length - 1]
}

// Default contract type for per-home cost section
const DEFAULT_CONTRACT = '5yr' as const

// ── Types ─────────────────────────────────────────────────────────────────────
interface Inputs {
  totalFT:             number
  totalPT:             number
  managerHourlyRate:   number
  agencyMonthlyCost:   number
  slIncidentsPerMonth: number
  agencyReductionPct:  number
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n: number) => `HK$${Math.round(n).toLocaleString()}`

// ── Core compute ───────────────────────────────
function compute(i: Inputs) {
  const totalStaff = i.totalFT + i.totalPT

  // Part A1 — Roster scheduling
  const rosterHrsBefore = 26
  const rosterHrsAfter  = 7
  const rosterHrSaved   = rosterHrsBefore - rosterHrsAfter
  const a1Saving        = Math.round(rosterHrSaved * i.managerHourlyRate)

  // Part A2 — Emergency cover
  const emergencyHrSaved = parseFloat((i.slIncidentsPerMonth * 0.75).toFixed(1))
  const a2Saving         = Math.round(emergencyHrSaved * i.managerHourlyRate)

  const totalAdminSaving = a1Saving + a2Saving

  // Part B — Agency
  const agencySaving5  = Math.round(i.agencyMonthlyCost * 0.05)
  const agencySaving8  = Math.round(i.agencyMonthlyCost * 0.08)
  const agencySaving15 = Math.round(i.agencyMonthlyCost * 0.15)
  const agencySaving   = Math.round(i.agencyMonthlyCost * i.agencyReductionPct / 100)

  const totalMonthlySaving = totalAdminSaving + agencySaving
  const annualSavings      = totalMonthlySaving * 12

  // Emma fee — tier pricing (5yr contract)
  const tierDef        = getTierDef(totalStaff)
  const tierRate       = tierDef.rates[DEFAULT_CONTRACT]  // HK$/user/mo
  const emmaAnnualFee  = totalStaff * tierRate * 12
  const emmaMonthlyFee = Math.round(emmaAnnualFee / 12)

  const netAnnualBenefit = annualSavings - emmaAnnualFee
  const paybackMonths    = totalMonthlySaving > 0
    ? parseFloat((emmaAnnualFee / totalMonthlySaving).toFixed(1)) : 99
  const roiMultiple      = emmaAnnualFee > 0
    ? parseFloat((annualSavings / emmaAnnualFee).toFixed(1)) : 0

  return {
    rosterHrsBefore, rosterHrsAfter, rosterHrSaved,
    a1Saving, emergencyHrSaved, a2Saving, totalAdminSaving,
    agencySaving, agencySaving5, agencySaving8, agencySaving15,
    totalMonthlySaving, annualSavings,
    tierDef, tierRate,
    emmaAnnualFee, emmaMonthlyFee, netAnnualBenefit,
    paybackMonths, roiMultiple, totalStaff,
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────
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

function SliderField({ label, value, onChange, min, max, step = 1, hint }: {
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

// ── Scale Calculator : HK$29,286/mo × (staff ÷ 49) × 12 ─────
const PILOT_MONTHLY = 29286
const PILOT_STAFF   = 49

function ScaleSlider({ isZH }: { isZH: boolean }) {
  const [staffCount, setStaffCount] = useState(300)

  const currentTier    = getTierDef(staffCount)
  const rate5yr        = currentTier.rates['5yr']
  const monthlyTotal   = Math.round(PILOT_MONTHLY * (staffCount / PILOT_STAFF))
  const annualSavings  = monthlyTotal * 12
  const emmaAnnualFee  = staffCount * rate5yr * 12
  const emmaMonthlyFee = Math.round(emmaAnnualFee / 12)
  const netAnnual      = annualSavings - emmaAnnualFee
  const roiMultiple    = (annualSavings / emmaAnnualFee).toFixed(1)
  const paybackDays    = Math.round((emmaAnnualFee / annualSavings) * 365)
  const annualMinus15  = Math.round(emmaAnnualFee * 0.85)

    return (
    <div>
      <div className="mb-5">
        <div className="flex justify-between items-center mb-2">
          <label className="text-xs font-medium text-slate-600">{isZH ? '員工人數' : 'Staff Count'}</label>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full text-white" style={{ background: PINK }}>
              Tier {currentTier.tier}
            </span>
            <span className="text-2xl font-bold tabular-nums" style={{ color: PINK }}>
              {staffCount.toLocaleString()} {isZH ? '人' : 'staff'}
            </span>
          </div>
        </div>
        <input
          type="range" min={49} max={1700} step={1} value={staffCount}
          onChange={e => setStaffCount(Number(e.target.value))}
          className="w-full accent-pink-500"
        />
        <div className="flex justify-between text-[10px] text-slate-400 mt-1">
          <span>49 (Pilot)</span>
          <span>T1: ≤500</span>
          <span>T2: ≤800</span>
          <span>T3: ≤1,200</span>
          <span>T4: 1,700</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-5">
        {[
          { label: isZH ? '月度節省'   : 'Monthly Savings',    value: fmt(monthlyTotal),   sub: `${staffCount} ÷ ${PILOT_STAFF} × HK$${PILOT_MONTHLY.toLocaleString()}`, color: 'text-pink-500' },
          { label: isZH ? 'Emma 月費'  : 'Emma Monthly Fee',   value: fmt(emmaMonthlyFee), sub: `HK$${rate5yr}/user · Tier ${currentTier.tier} · 5yr`, color: 'text-slate-700' },
          { label: isZH ? '年度節省'   : 'Annual Savings',     value: fmt(annualSavings),  sub: isZH ? '月度 × 12' : 'Monthly × 12', color: 'text-emerald-600' },
          { label: isZH ? '年度淨收益' : 'Net Annual Benefit', value: fmt(netAnnual),      sub: isZH ? '年節省 − Emma 年費' : 'Annual − Emma fee', color: 'text-blue-600' },
        ].map(k => (
          <div key={k.label} className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-center">
            <p className="text-[10px] text-slate-500 mb-1">{k.label}</p>
            <p className={`text-lg font-bold tabular-nums ${k.color}`}>{k.value}</p>
            <p className="text-[9px] text-slate-400 mt-1">{k.sub}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl p-5 mb-5 text-center" style={{ background: '#1a1a2e' }}>
        <p className="text-[11px] font-semibold tracking-widest text-white/40 mb-3">
          EMMA AI ROI · TIER {currentTier.tier} · {currentTier.label} {isZH ? '人' : 'STAFF'}
        </p>
        <div className="flex items-center justify-center gap-8">
          <div>
            <p className="text-4xl font-bold text-pink-400 tabular-nums">{roiMultiple}x</p>
            <p className="text-[10px] text-white/50 mt-1">{isZH ? 'ROI 倍數' : 'ROI Multiple'}</p>
          </div>
          <div className="w-px h-12 bg-white/10" />
          <div>
            <p className="text-4xl font-bold text-emerald-400 tabular-nums">{paybackDays}</p>
            <p className="text-[10px] text-white/50 mt-1">{isZH ? '回本天數' : 'Payback Days'}</p>
          </div>
          <div className="w-px h-12 bg-white/10" />
          <div>
            <p className="text-3xl font-bold text-blue-400 tabular-nums">{fmt(netAnnual)}</p>
            <p className="text-[10px] text-white/50 mt-1">{isZH ? '年度淨收益' : 'Net Annual Benefit'}</p>
          </div>
        </div>
        <p className="text-[9px] text-white/30 mt-3">
          {isZH ? '年費 -15% 預付：' : 'Annual -15% prepay: '}{fmt(annualMinus15)}/yr
        </p>
      </div>

      <div className="space-y-4">
        {TIER_DEFS.map(tier => {
          const CONTRACTS: Array<{ yr: '3yr' | '5yr' | '10yr' }> = [
            { yr: '3yr' },
            { yr: '5yr' },
            { yr: '10yr' },
          ]
          const repStaff = tier.max
          const basisAnn = Math.round(PILOT_MONTHLY * (repStaff / PILOT_STAFF)) * 12
          const isActive = currentTier.tier === tier.tier

          return (
            <div
              key={tier.tier}
              className={`rounded-2xl border p-4 transition-colors ${isActive ? 'border-pink-300 bg-pink-50/30' : 'border-slate-200 bg-white'}`}
            >
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-bold px-2.5 py-1 rounded-full text-white" style={{ background: PINK }}>
                  Tier {tier.tier}
                </span>
                <span className="text-sm font-semibold text-slate-800">{tier.label} {isZH ? '人' : 'Staff'}</span>
                {isActive && (
                  <span className="ml-auto text-[9px] font-bold text-pink-600 bg-pink-100 px-2 py-0.5 rounded-full">
                    {isZH ? '目前選擇' : 'Selected'}
                  </span>
                )}
              </div>

              <div className="mb-3 rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
                <p className="text-[10px] text-slate-500">
                  {isZH ? '計算基準 (最大人數)' : 'Saving Basis (max staff)'}:{' '}
                  HK${PILOT_MONTHLY.toLocaleString()}/mo × ({repStaff} ÷ {PILOT_STAFF}) × 12 = <strong>{fmt(basisAnn)}</strong>
                </p>
              </div>

              <div className="overflow-x-auto rounded-xl border border-slate-100">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {(isZH
                        ? ['合約', '月費/人', '年度節省', 'Emma 年費', '年費-15%', '淨收益', 'ROI', '回本']
                        : ['Contract', 'Rate/User', 'Annual Saving', 'Emma Fee', 'Fee -15%', 'Net Benefit', 'ROI', 'Payback']
                      ).map(h => (
                        <th key={h} className="px-2 py-2 text-[10px] font-semibold text-slate-400 uppercase text-left">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {CONTRACTS.map(c => {
                      const rate  = tier.rates[c.yr]
                      const fee   = repStaff * rate * 12
                      const net   = basisAnn - fee
                      const roi   = (basisAnn / fee).toFixed(1)
                      const pb    = (fee / (basisAnn / 12)).toFixed(1)
                      const is5yr = c.yr === '5yr'
                      return (
                        <tr key={c.yr} className={`border-b border-slate-50 ${is5yr ? 'bg-emerald-50/50' : ''}`}>
                          <td className={`px-2 py-2 font-bold ${is5yr ? 'text-emerald-700' : 'text-slate-600'}`}>
                            {c.yr}
                            {is5yr && <span className="ml-1 text-[9px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">★</span>}
                          </td>
                          <td className="px-2 py-2 font-semibold text-slate-700 tabular-nums">HK${rate}</td>
                          <td className="px-2 py-2 text-slate-600 tabular-nums">{fmt(basisAnn)}</td>
                          <td className="px-2 py-2 text-slate-500 tabular-nums">{fmt(fee)}</td>
                          <td className="px-2 py-2 text-slate-400 tabular-nums">{fmt(Math.round(fee * 0.85))}</td>
                          <td className={`px-2 py-2 font-bold tabular-nums ${is5yr ? 'text-emerald-700' : 'text-pink-600'}`}>{fmt(net)}</td>
                          <td className="px-2 py-2 font-bold text-blue-600">{roi}x</td>
                          <td className="px-2 py-2 text-slate-500">{pb}mo</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )
        })}
      </div>

      <p className="mt-3 text-[10px] text-slate-400 text-center">
        {isZH
          ? '★ = NAAC 推薦 5年合約 · 公式: HK$29,286/mo × (員工數 ÷ 49) × 12 · 基於 49 人 Pilot 院舍數據'
          : '★ = NAAC Recommended 5yr · Formula: HK$29,286/mo × (Staff ÷ 49) × 12 · Based on 49-staff pilot site'}
      </p>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function ROIPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const [inputs, setInputs] = useState<Inputs>({
    totalFT:             33,
    totalPT:             16,
    managerHourlyRate:   409,
    agencyMonthlyCost:   148070,
    slIncidentsPerMonth: 46,
    agencyReductionPct:  5,
  })

  const set = (key: keyof Inputs) => (v: number) =>
    setInputs(prev => ({ ...prev, [key]: v }))

  const r = useMemo(() => compute(inputs), [inputs])

  return (
    <div className="p-5 space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">
            {isZH ? 'ROI 效益計算' : 'ROI Calculator'}
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-[10px] text-gray-400">{isZH ? 'ROI 倍數' : 'ROI Multiple'}</div>
            <div className="text-2xl font-bold text-pink-500">{r.roiMultiple}x</div>
          </div>
          <div className="w-12 h-12 rounded-full border-4 border-pink-400 flex items-center justify-center text-[10px] font-bold text-pink-500 text-center leading-tight px-1">
            {r.paybackMonths}{isZH ? '月' : 'mo'}
          </div>
        </div>
      </div>

      {/* KPI Banner */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: isZH ? '月度節省'   : 'Monthly Savings',    value: fmt(r.totalMonthlySaving), color: 'text-pink-500' },
          { label: isZH ? '年度節省'   : 'Annual Savings',     value: fmt(r.annualSavings),      color: 'text-emerald-600' },
          { label: isZH ? 'Emma 月費'  : 'Emma Monthly Fee',   value: fmt(r.emmaMonthlyFee),     color: 'text-slate-700' },
          { label: isZH ? '年度淨收益' : 'Net Annual Benefit', value: fmt(r.netAnnualBenefit),   color: 'text-blue-600' },
        ].map(k => (
          <div key={k.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{k.label}</div>
            <div className={`text-[20px] font-bold tabular-nums ${k.color}`}>{k.value}</div>
            <div className="w-full h-1 bg-gray-100 rounded-full mt-2" />
          </div>
        ))}
      </div>

      {/* ── Section 1: Staff Inputs ─────────────────────────────────────────── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">👥</div>
          <h2 className="text-base font-semibold text-slate-800">{isZH ? '員工基本資料' : 'Staff Baseline'}</h2>
          <span className="ml-auto text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
            {isZH ? `Tier ${r.tierDef.tier} · HK$${r.tierRate}/user/mo (5yr)` : `Tier ${r.tierDef.tier} · HK$${r.tierRate}/user/mo (5yr)`}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <InputField
            label={isZH ? '全職員工人數' : 'Full-Time Staff'}
            value={inputs.totalFT} onChange={set('totalFT')}
            suffix={isZH ? '人' : 'pax'} hint="March 33"
          />
          <InputField
            label={isZH ? '兼職員工人數' : 'Part-Time Staff'}
            value={inputs.totalPT} onChange={set('totalPT')}
            suffix={isZH ? '人' : 'pax'} hint="March 16"
          />
          <InputField
            label={isZH ? '經理/ASRN 時薪' : 'Manager/ASRN Hourly Rate'}
            value={inputs.managerHourlyRate} onChange={set('managerHourlyRate')}
            suffix="HK$" hint="HK$70,720÷173h=HK$409"
          />
          <InputField
            label={isZH ? '每月 SL/DSL 事件' : 'Monthly SL/DSL Incidents'}
            value={inputs.slIncidentsPerMonth} onChange={set('slIncidentsPerMonth')}
            suffix={isZH ? '次' : 'cases'} hint="March 46"
          />
        </div>
        <div className="mt-3 rounded-xl bg-slate-50 border border-slate-100 px-3 py-2 flex items-center gap-3">
          <span className="text-[10px] text-slate-500">
            {isZH ? '總員工人數' : 'Total staff'}: <strong className="text-slate-700">{r.totalStaff}</strong>
          </span>
          <span className="text-slate-300">|</span>
          <span className="text-[10px] text-slate-500">
            {isZH ? 'NAAC Tier' : 'NAAC Tier'}: <strong style={{ color: PINK }}>Tier {r.tierDef.tier} ({r.tierDef.label})</strong>
          </span>
          <span className="text-slate-300">|</span>
          <span className="text-[10px] text-slate-500">
            {isZH ? '5yr 月費/人' : '5yr rate/user'}: <strong className="text-slate-700">HK${r.tierRate}</strong>
          </span>
        </div>
      </div>

      {/* ── Section 2: Admin Time Saving ──────────────────────────── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">⏱️</div>
          <h2 className="text-base font-semibold text-slate-800">
            {isZH ? 'Part A — 管理時間節省' : 'Part A — Admin Time Saving'}
          </h2>
          <span className="ml-auto text-[9px] font-bold bg-pink-50 text-pink-500 px-2 py-0.5 rounded-full border border-pink-100">v2.2 FORMULA</span>
        </div>

        {/* A1 */}
        <div className="mb-4 rounded-xl bg-blue-50 border border-blue-100 p-4">
          <p className="text-xs font-bold text-blue-800 mb-2">A1 · {isZH ? '排班時間節省' : 'Roster Scheduling Time Saving'}</p>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="rounded-xl bg-white p-3 text-center border border-blue-100">
              <p className="text-[9px] text-slate-500 mb-1">{isZH ? '排班前（時/月）' : 'Roster Time Before'}</p>
              <p className="text-xl font-bold text-slate-500 tabular-nums">{r.rosterHrsBefore}h</p>
              <p className="text-[9px] text-slate-400 mt-1">{isZH ? '調查 n=2 院舍' : 'Survey n=2 homes'}</p>
            </div>
            <div className="rounded-xl bg-white p-3 text-center border border-emerald-200">
              <p className="text-[9px] text-slate-500 mb-1">{isZH ? '排班後（時/月）' : 'Roster Time After'}</p>
              <p className="text-xl font-bold text-emerald-600 tabular-nums">{r.rosterHrsAfter}h</p>
              <p className="text-[9px] text-slate-400 mt-1">{isZH ? 'Emma AI 優化後' : 'After Emma AI'}</p>
            </div>
            <div className="rounded-xl bg-white p-3 text-center border border-blue-200">
              <p className="text-[9px] text-slate-500 mb-1">{isZH ? '節省時數' : 'Hours Saved'}</p>
              <p className="text-xl font-bold text-blue-600 tabular-nums">{r.rosterHrSaved}h</p>
              <p className="text-[9px] text-slate-400 mt-1">{isZH ? '每月直接節省' : 'Per month direct'}</p>
            </div>
          </div>
          <div className="rounded-lg bg-white/70 px-3 py-2 text-[11px] text-blue-700">
            <span className="font-bold">A1 {isZH ? '公式' : 'Formula'}:</span>{' '}
            ({r.rosterHrsBefore}h − {r.rosterHrsAfter}h) × HK${inputs.managerHourlyRate}/hr
            = {r.rosterHrSaved}h × HK${inputs.managerHourlyRate}
            = <span className="font-bold">{fmt(r.a1Saving)}/mo</span>
          </div>
          <p className="text-[9px] text-blue-500 mt-1.5">
            ⚠ {isZH ? '月份時數，不需 ×4.33 或 ×25%（PDF v2.2 修正）' : 'Monthly hours — no ×4.33 or ×25% conversion (PDF v2.2 correction)'}
          </p>
        </div>

        {/* A2 */}
        <div className="rounded-xl bg-purple-50 border border-purple-100 p-4">
          <p className="text-xs font-bold text-purple-800 mb-2">A2 · {isZH ? '緊急召喚節省 (SL/DSL)' : 'Emergency Cover Saving (SL/DSL Incidents)'}</p>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="rounded-xl bg-white p-3 text-center border border-purple-100">
              <p className="text-[9px] text-slate-500 mb-1">{isZH ? '每月事件數' : 'Monthly Incidents'}</p>
              <p className="text-xl font-bold text-slate-700 tabular-nums">{inputs.slIncidentsPerMonth}</p>
              <p className="text-[9px] text-slate-400 mt-1">March 2026 {isZH ? '實際' : 'actual'}</p>
            </div>
            <div className="rounded-xl bg-white p-3 text-center border border-purple-100">
              <p className="text-[9px] text-slate-500 mb-1">{isZH ? '每次節省時數' : 'Time Saved/Incident'}</p>
              <p className="text-xl font-bold text-purple-600 tabular-nums">0.75h</p>
              <p className="text-[9px] text-slate-400 mt-1">{isZH ? 'Emma 自動配對' : 'Emma auto-match'}</p>
            </div>
            <div className="rounded-xl bg-white p-3 text-center border border-purple-200">
              <p className="text-[9px] text-slate-500 mb-1">{isZH ? '節省時數/月' : 'Hours Saved/Month'}</p>
              <p className="text-xl font-bold text-purple-600 tabular-nums">{r.emergencyHrSaved}h</p>
              <p className="text-[9px] text-slate-400 mt-1">{inputs.slIncidentsPerMonth} × 0.75h</p>
            </div>
          </div>
          <div className="rounded-lg bg-white/70 px-3 py-2 text-[11px] text-purple-700">
            <span className="font-bold">A2 {isZH ? '公式' : 'Formula'}:</span>{' '}
            {inputs.slIncidentsPerMonth} × 0.75h × HK${inputs.managerHourlyRate}/hr
            = {r.emergencyHrSaved}h × HK${inputs.managerHourlyRate}
            = <span className="font-bold">{fmt(r.a2Saving)}/mo</span>
          </div>
        </div>

        {/* Part A Total */}
        <div className="mt-4 flex items-center justify-between rounded-xl border-2 border-blue-300 bg-blue-50 px-4 py-3">
          <div>
            <p className="text-sm font-bold text-slate-800">Part A {isZH ? '合計' : 'Total'} (A1 + A2)</p>
            <p className="text-[11px] text-slate-500">{fmt(r.a1Saving)} + {fmt(r.a2Saving)}</p>
          </div>
          <p className="text-2xl font-bold text-blue-600 tabular-nums">{fmt(r.totalAdminSaving)}/mo</p>
        </div>
      </div>

      {/* ── Section 3:  Agency Cost Saving ─────────────────────────── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">🏥</div>
          <h2 className="text-base font-semibold text-slate-800">
            {isZH ? '兼職費用節省（5% 保守）' : 'Part B — Agency Cost Saving (5% Conservative)'}
          </h2>
          <span className="ml-auto text-[9px] font-bold bg-pink-50 text-pink-500 px-2 py-0.5 rounded-full border border-pink-100">v2.2</span>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 mb-4">
          <InputField
            label={isZH ? '兼職撥款月費' : 'Agency Monthly Cost'}
            value={inputs.agencyMonthlyCost} onChange={set('agencyMonthlyCost')}
            suffix="HK$" hint="March HK$148,070"
          />
          <div className="rounded-xl bg-slate-50 border border-slate-200 p-3">
            <p className="text-[10px] text-slate-500 mb-1">{isZH ? '兼職費用明細 (March)' : 'Agency Breakdown (March)'}</p>
            <p className="text-[11px] text-slate-600">PT RCW 124 {isZH ? '班' : 'shifts'}: HK$118,520</p>
            <p className="text-[11px] text-slate-600">PT HW/EN 24 {isZH ? '班' : 'shifts'}: HK$29,550</p>
          </div>
        </div>

        {/* 3 scenarios */}
        <div className="rounded-xl border border-slate-200 overflow-hidden mb-4">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                {[isZH ? '方案' : 'Scenario', isZH ? '減少%' : 'Reduction', isZH ? '月度節省' : 'Monthly Saving', isZH ? '備註' : 'Rationale'].map(h => (
                  <th key={h} className="px-3 py-2 text-[10px] font-semibold text-slate-500 uppercase text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                { scenario: isZH ? '保守 — 採用 ✓' : 'Conservative — USED ✓', pct: 5,  saving: r.agencySaving5,  note: isZH ? 'SWD 最低人手要求' : 'SWD minimum staffing floor', active: true },
                { scenario: isZH ? '中間 — 參考'   : 'Mid case — ref only',   pct: 8,  saving: r.agencySaving8,  note: isZH ? 'Paper 1 pilot 參考' : 'Paper 1 pilot reference',   active: false },
                { scenario: isZH ? '原始 — 移除'   : 'Original — REMOVED',    pct: 15, saving: r.agencySaving15, note: isZH ? '過於樂觀' : 'Overly optimistic',                 active: false },
              ].map(row => (
                <tr key={row.pct} className={`border-b border-slate-100 ${row.active ? 'bg-pink-50' : ''}`}>
                  <td className={`px-3 py-2.5 font-semibold ${row.active ? 'text-pink-600' : 'text-slate-500'}`}>{row.scenario}</td>
                  <td className={`px-3 py-2.5 font-bold tabular-nums ${row.active ? 'text-pink-600' : 'text-slate-400'}`}>{row.pct}%</td>
                  <td className={`px-3 py-2.5 font-bold tabular-nums ${row.active ? 'text-pink-600' : 'text-slate-400'}`}>{fmt(row.saving)}</td>
                  <td className="px-3 py-2.5 text-slate-500">{row.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SliderField
          label={isZH ? '調整兼職減少比例（預設 5%）' : 'Adjust Agency Reduction % (default 5%)'}
          value={inputs.agencyReductionPct} onChange={set('agencyReductionPct')}
          min={1} max={20} step={1}
          hint={isZH ? '（採用 5%）' : '(uses 5%)'}
        />

        <div className="mt-3 flex items-center justify-between rounded-xl border-2 border-pink-300 bg-pink-50 px-4 py-3">
          <div>
            <p className="text-sm font-bold text-slate-800">Part B {isZH ? '合計' : 'Total'}</p>
            <p className="text-[11px] text-slate-500">{fmt(inputs.agencyMonthlyCost)} × {inputs.agencyReductionPct}%</p>
          </div>
          <p className="text-2xl font-bold text-pink-600 tabular-nums">{fmt(r.agencySaving)}/mo</p>
        </div>
      </div>

      {/* ── Section 4: Savings Summary ──────────────────────────────────────── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">💰</div>
          <h2 className="text-base font-semibold text-slate-800">{isZH ? '節省彙總' : 'Savings Summary'}</h2>
        </div>
        <div className="space-y-2.5">
          <SavingRow
            label={isZH ? '管理時間節省' : 'Admin Time Saving'}
            saving={r.totalAdminSaving}
            detail={`A1 ${fmt(r.a1Saving)} + A2 ${fmt(r.a2Saving)}`}
            color="blue"
          />
          <SavingRow
            label={isZH ? '兼職費用節省（5%）' : 'Agency Cost Saving (5%)'}
            saving={r.agencySaving}
            detail={`${fmt(inputs.agencyMonthlyCost)} × ${inputs.agencyReductionPct}% · SWD Cap.459 ${isZH ? '保守估算' : 'conservative'}`}
            color="pink"
          />
          <div className="flex items-center justify-between rounded-xl border-2 border-pink-300 bg-pink-50 px-4 py-3.5">
            <div>
              <p className="text-base font-bold text-slate-800">{isZH ? '月度總節省' : 'Total Monthly Saving'}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {isZH ? '以 49 人院舍為基準：HK$29,286/mo' : 'Pilot basis (49 staff): HK$29,286/mo'}
              </p>
            </div>
            <p className="text-2xl font-bold text-pink-600 tabular-nums">{fmt(r.totalMonthlySaving)}</p>
          </div>
        </div>
      </div>

      {/* ── Section 5: Emma Cost vs ROI Banner ─────────────────────────────── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">📊</div>
          <h2 className="text-base font-semibold text-slate-800">{isZH ? 'Emma AI 費用 vs 節省' : 'Emma AI Cost vs Savings'}</h2>
          <span className="ml-auto text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
            Tier {r.tierDef.tier} · HK${r.tierRate}/user/mo · 5yr
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-5">
          {[
            {
              label: isZH ? 'Emma 月費'  : 'Emma Monthly Fee',
              value: fmt(r.emmaMonthlyFee),
              sub:   `${r.totalStaff} × HK$${r.tierRate} (Tier ${r.tierDef.tier} 5yr)`,
              color: 'text-slate-800',
            },
            {
              label: isZH ? 'Emma 年費'  : 'Emma Annual Fee',
              value: fmt(r.emmaAnnualFee),
              sub:   `${r.totalStaff} × HK$${r.tierRate} × 12${isZH ? '月' : 'mo'}`,
              color: 'text-slate-800',
            },
            {
              label: isZH ? '年度節省'   : 'Annual Savings',
              value: fmt(r.annualSavings),
              sub:   isZH ? '月節省 × 12' : 'Monthly × 12',
              color: 'text-emerald-600',
            },
            {
              label: isZH ? '年度淨收益' : 'Net Annual Benefit',
              value: fmt(r.netAnnualBenefit),
              sub:   isZH ? '年節省 − Emma 年費' : 'Annual − Emma fee',
              color: 'text-blue-600',
            },
          ].map(k => (
            <div key={k.label} className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-center">
              <p className="text-[10px] text-slate-500 mb-1">{k.label}</p>
              <p className={`text-lg font-bold tabular-nums ${k.color}`}>{k.value}</p>
              <p className="text-[9px] text-slate-400 mt-1">{k.sub}</p>
            </div>
          ))}
        </div>

        <div className="rounded-2xl p-5 text-center" style={{ background: '#1a1a2e' }}>
          <p className="text-[11px] font-semibold tracking-widest text-white/40 mb-3">
            EMMA AI ROI · TIER {r.tierDef.tier} · {r.tierDef.label} {isZH ? '人 · 5yr HK$' : 'STAFF · 5yr HK$'}{r.tierRate}/user/mo
          </p>
          <div className="flex items-center justify-center gap-8">
            <div>
              <p className="text-4xl font-bold text-pink-400 tabular-nums">{r.roiMultiple}x</p>
              <p className="text-[10px] text-white/50 mt-1">{isZH ? 'ROI 倍數' : 'ROI Multiple'}</p>
            </div>
            <div className="w-px h-12 bg-white/10" />
            <div>
              <p className="text-4xl font-bold text-emerald-400 tabular-nums">{r.paybackMonths}</p>
              <p className="text-[10px] text-white/50 mt-1">{isZH ? '回本月數' : 'Months to Payback'}</p>
            </div>
            <div className="w-px h-12 bg-white/10" />
            <div>
              <p className="text-3xl font-bold text-blue-400 tabular-nums">{fmt(r.netAnnualBenefit)}</p>
              <p className="text-[10px] text-white/50 mt-1">{isZH ? '年度淨收益' : 'Net Annual Benefit'}</p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Section 6: Scale Calculator ──────────────────────── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">📈</div>
          <h2 className="text-base font-semibold text-slate-800">
            {isZH ? '規模化試算' : 'Scale Calculator'}
          </h2>
          <span className="ml-auto text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
            {isZH ? 'Sales Demo 用途' : 'Sales Demo'}
          </span>
        </div>

        <div className="mb-5 rounded-xl bg-blue-50 border border-blue-100 px-4 py-3">
          <p className="text-[11px] text-blue-700 leading-relaxed">
            <strong>📊 {isZH ? '規模化計算基準' : 'Scale Calculator Formula'}:</strong>{' '}
            {isZH
              ? `年度節省 = HK$${PILOT_MONTHLY.toLocaleString()}/mo × (員工數 ÷ ${PILOT_STAFF}) × 12。Pilot: 一個 ${PILOT_STAFF} 人院舍，月節省 HK$${PILOT_MONTHLY.toLocaleString()}（A1+A2+B 5%）。`
              : `Annual Saving = HK$${PILOT_MONTHLY.toLocaleString()}/mo × (Staff Count ÷ ${PILOT_STAFF}) × 12. Pilot: one ${PILOT_STAFF}-staff home, HK$${PILOT_MONTHLY.toLocaleString()}/mo saving (A1+A2+B 5%).`}
          </p>
          <p className="text-[10px] text-blue-600 mt-1.5">
            {isZH
              ? 'Emma 年費 = 員工數 × Tier 月費 × 12 (NAAC Option B 5yr 合約)'
              : 'Emma Fee = Staff × Tier Rate × 12 (NAAC Option B 5yr contract)'}
          </p>
        </div>

        <ScaleSlider isZH={isZH} />
      </div>

    </div>
  )
}