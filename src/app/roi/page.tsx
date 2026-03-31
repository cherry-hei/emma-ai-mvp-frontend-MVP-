'use client'

import { useState, useMemo } from 'react'

interface Inputs {
  frontlineStaffCost: number
  managerFee: number
  totalFT: number
  totalPT: number
  agencyStaff: number
}

function compute(inputs: Inputs) {
  const { frontlineStaffCost, managerFee, totalFT, totalPT, agencyStaff } = inputs

  const totalStaff = totalFT + totalPT + agencyStaff
  const totalStaffCost = frontlineStaffCost + managerFee

  const emmaAnnualFee = totalStaff * 840

  const adminBefore = 30
  const adminAfter = 8
  const adminSavingPct = Math.round(((adminBefore - adminAfter) / adminBefore) * 100)
  const adminHrSaved = adminBefore - adminAfter

  const otAfter = 44

  const savingRate = 0.015
  const baseMonthlySaving = Math.round(totalStaffCost * savingRate)

  const otCostSaving = Math.round(baseMonthlySaving * 0.40)
  const agencyCostSaving = Math.round(baseMonthlySaving * 0.40)
  const adminValueSaved = Math.round(baseMonthlySaving * 0.20)

  const agencyShifts = agencyStaff * 4
  const rosterCompletionRate = Math.min(98, 80 + Math.round(totalStaff * 0.4))

  const totalMonthlySaving = otCostSaving + agencyCostSaving + adminValueSaved
  const annualSavings = totalMonthlySaving * 12
  const paybackMonths = totalMonthlySaving > 0
    ? Math.ceil(emmaAnnualFee / totalMonthlySaving)
    : 3
  const netAnnualBenefit = annualSavings - emmaAnnualFee

  return {
    adminSavingPct, adminBefore, adminAfter, adminHrSaved,
    otAfter, agencyShifts, otCostSaving,
    agencyCostSaving, rosterCompletionRate,
    totalMonthlySaving, annualSavings, paybackMonths,
    netAnnualBenefit, totalStaff,
  }
}

const fmt = (n: number) => `HK$${n.toLocaleString()}`
const fmtPct = (n: number) => `${n}%`

function InputField({
  label, value, onChange, prefix = '', suffix = '',
}: {
  label: string; value: number; onChange: (v: number) => void; prefix?: string; suffix?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-500">{label}</label>
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

function BarMetric({
  label, before, after, unit = 'h', color = 'bg-pink-400',
}: {
  label: string; before: number; after: number; unit?: string; color?: string
}) {
  const pct = Math.round((after / before) * 100)
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

export default function ROIPage() {
  const [inputs, setInputs] = useState<Inputs>({
    frontlineStaffCost: 1190800,
    managerFee: 180000,
    totalFT: 44,
    totalPT: 0,
    agencyStaff: 12,
  })

  const set = (key: keyof Inputs) => (v: number) => setInputs(prev => ({ ...prev, [key]: v }))

  const r = useMemo(() => compute(inputs), [inputs])

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      <div className="border-b border-slate-200 bg-white px-6 py-5">
        <div className="mx-auto max-w-4xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-pink-500">Emma AI</p>
          <h1 className="mt-1 text-xl font-semibold text-slate-800">ROI 效益模擬器</h1>
          <p className="mt-1 text-sm text-slate-500">
            輸入你的機構數字，即時計算 Emma AI 能為你節省的成本與行政時間
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-4xl space-y-6 px-6 py-6">

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">✏️</div>
            <h2 className="text-base font-semibold text-slate-800">機構基本資料</h2>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <InputField label="前線員工總人工成本（月）" value={inputs.frontlineStaffCost} onChange={set('frontlineStaffCost')} prefix="HK$" />
            <InputField label="管理層費用（月）" value={inputs.managerFee} onChange={set('managerFee')} prefix="HK$" />
            <InputField label="全職員工總人數" value={inputs.totalFT} onChange={set('totalFT')} suffix="人" />
            <InputField label="兼職員工總人數" value={inputs.totalPT} onChange={set('totalPT')} suffix="人" />
            <InputField label="外判人手人數" value={inputs.agencyStaff} onChange={set('agencyStaff')} suffix="人" />
          </div>
          <div className="mt-4 rounded-xl bg-pink-50 px-4 py-3">
            <p className="text-xs text-pink-600">
              💡 Emma AI 會根據你的人手結構，透過 AI 自動排更演算法找出最省成本的組合，
              同時把管理層節省下來的 <strong>{r.adminHrSaved}h</strong> 行政時間轉化為服務工作。
            </p>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-slate-800">效率提升指標</h2>
          <div className="space-y-5">
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-sm font-medium text-slate-700">行政時間節省</span>
                <span className="rounded-full bg-pink-50 px-2.5 py-0.5 text-xs font-semibold text-pink-500">
                  節省 {r.adminSavingPct}%
                </span>
              </div>
              <BarMetric label="每月排班行政工時" before={r.adminBefore} after={r.adminAfter} color="bg-pink-400" />
            </div>
            <div className="border-t border-slate-100 pt-4">
              <BarMetric label="OT 超時工時" before={64} after={r.otAfter} color="bg-orange-400" />
            </div>
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-base font-semibold text-slate-700">每月節省概覽</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <KpiCard label="OT 成本節省" value={fmt(r.otCostSaving)} sub="每月" accent />
            <KpiCard label="外判成本節省" value={fmt(r.agencyCostSaving)} sub="每月" accent />
            <KpiCard label="OT 超時工時" value={`${r.otAfter}h`} sub={`節省 ${64 - r.otAfter}h`} />
            <KpiCard label="外判更數" value={`${r.agencyShifts}更`} sub="本月估算" />
          </div>
          <div className="mt-3">
            <KpiCard label="更表完成率" value={fmtPct(r.rosterCompletionRate)} sub="AI 最優化排更結果" accent />
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-base font-semibold text-slate-800">Emma AI 如何節省成本</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              {
                icon: '🤖',
                title: 'AI 最優排更',
                desc: `系統從 ${r.totalStaff} 名員工中自動計算最省成本的組合，優先安排全職員工，減少超時及外判需求`,
              },
              {
                icon: '⏰',
                title: '行政時間轉化',
                desc: `管理層每月節省 ${r.adminHrSaved}h 排更行政時間，等同多出 ${Math.round(r.adminHrSaved / 8)} 天服務工作時間`,
              },
              {
                icon: '💰',
                title: '實時成本監控',
                desc: `系統即時顯示每更成本，確保每月人力支出受控，年度總節省約 ${fmt(r.annualSavings)}`,
              },
            ].map(item => (
              <div key={item.title} className="rounded-xl bg-slate-50 p-4">
                <div className="text-2xl">{item.icon}</div>
                <h3 className="mt-2 text-sm font-semibold text-slate-800">{item.title}</h3>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">{item.desc}</p>
              </div>
            ))}
          </div>
        </section>

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
              <p className={`mt-2 text-3xl font-bold tabular-nums ${r.netAnnualBenefit > 0 ? 'text-pink-500' : 'text-red-500'}`}>
                {r.netAnnualBenefit > 0 ? '+' : ''}{fmt(r.netAnnualBenefit)}
              </p>
              <p className="mt-1 text-xs text-slate-400">Net Annual Benefit</p>
            </div>
          </div>

          <div className="mt-4 rounded-xl bg-pink-500 px-4 py-3 text-center">
            <p className="text-sm font-semibold text-white">
              每投入 HK$1，Emma AI 預計回報{' '}
              <span className="text-yellow-300">
                HK${r.emmaAnnualFee > 0 ? (r.annualSavings / r.emmaAnnualFee).toFixed(1) : '∞'}
              </span>
            </p>
          </div>
        </section>

      </div>
    </div>
  )
}