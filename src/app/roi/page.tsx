'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { RoiSettings, RoiSummary } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

const fmt = (n: number) => `HK$${Math.round(n).toLocaleString()}`

/* ── inputs ───────────────────────────────────────────────────────────────── */
function InputField({ label, value, onChange, onCommit, suffix = '', hint }: {
  label: string; value: number; onChange: (v: number) => void; onCommit: () => void
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
          onChange={(e) => onChange(Number(e.target.value) || 0)}
          onBlur={onCommit}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-slate-800 outline-none tabular-nums"
          placeholder="0"
        />
        {suffix && <span className="text-xs text-slate-400">{suffix}</span>}
      </div>
    </div>
  )
}

function ReadOnlyField({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-500">{label}</label>
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
        <span className="text-sm font-semibold text-slate-800 tabular-nums">{value}</span>
        {sub && <span className="ml-2 text-[10px] text-slate-400">{sub}</span>}
      </div>
    </div>
  )
}

function SavingRow({ label, saving, detail, color }: {
  label: string; saving: number; detail: string; color: 'pink' | 'blue'
}) {
  const cls = color === 'pink'
    ? 'bg-pink-50 border-pink-100 text-pink-600'
    : 'bg-blue-50 border-blue-100 text-blue-600'
  return (
    <div className={`flex items-center justify-between rounded-xl border px-4 py-3 ${cls}`}>
      <div>
        <p className="text-sm font-semibold text-slate-800">{label}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">{detail}</p>
      </div>
      <p className={`text-base font-bold tabular-nums ${cls.split(' ')[2]}`}>{fmt(saving)}</p>
    </div>
  )
}

/* ── scale calculator ─────────────────────────────────────────────────────── */
function ScaleCalculator({ data, isZH }: { data: RoiSummary; isZH: boolean }) {
  const [staffCount, setStaffCount] = useState(Math.max(data.staff.total, 300))

  // Scale from this home's own measured monthly saving, not a hardcoded pilot figure.
  const basisStaff = Math.max(1, data.staff.total)
  const basisMonthly = data.totals.monthly_saving
  const tier = data.tiers.find((t) => staffCount <= t.max_staff) ?? data.tiers[data.tiers.length - 1]
  const contract = data.emma.contract_years
  const rate = tier.rates[contract]

  const monthlyTotal = Math.round(basisMonthly * (staffCount / basisStaff))
  const annualSavings = monthlyTotal * 12
  const annualFee = staffCount * rate * 12
  const netAnnual = annualSavings - annualFee
  const roiMultiple = annualFee > 0 ? (annualSavings / annualFee).toFixed(1) : '-'
  const paybackDays = annualSavings > 0 ? Math.round((annualFee / annualSavings) * 365) : 0

  return (
    <div>
      <div className="mb-5 rounded-xl bg-blue-50 border border-blue-100 px-4 py-3">
        <p className="text-[11px] text-blue-700 leading-relaxed">
          <strong>📊 {isZH ? '規模化計算基準' : 'Scale basis'}:</strong>{' '}
          {isZH
            ? `本院舍實測月節省 ${fmt(basisMonthly)}（${basisStaff} 人）× (目標人數 ÷ ${basisStaff}) × 12`
            : `This home's measured ${fmt(basisMonthly)}/mo across ${basisStaff} staff × (target ÷ ${basisStaff}) × 12`}
        </p>
      </div>

      <div className="mb-5">
        <div className="flex justify-between items-center mb-2">
          <label className="text-xs font-medium text-slate-600">{isZH ? '員工人數' : 'Staff Count'}</label>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full text-white" style={{ background: PINK }}>
              Tier {tier.tier}
            </span>
            <span className="text-2xl font-bold tabular-nums" style={{ color: PINK }}>
              {staffCount.toLocaleString()} {isZH ? '人' : 'staff'}
            </span>
          </div>
        </div>
        <input type="range" min={basisStaff} max={1700} step={1} value={staffCount}
          onChange={(e) => setStaffCount(Number(e.target.value))}
          className="w-full accent-pink-500" />
        <div className="flex justify-between text-[10px] text-slate-400 mt-1">
          <span>{basisStaff} ({isZH ? '本院舍' : 'this home'})</span>
          {data.tiers.map((t) => <span key={t.tier}>T{t.tier}: ≤{t.max_staff}</span>)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-5">
        {[
          { label: isZH ? '月度節省' : 'Monthly Savings', value: fmt(monthlyTotal),
            sub: `${staffCount} ÷ ${basisStaff} × ${fmt(basisMonthly)}`, color: 'text-pink-500' },
          { label: isZH ? 'Emma 月費' : 'Emma Monthly Fee', value: fmt(Math.round(annualFee / 12)),
            sub: `HK$${rate}/user · Tier ${tier.tier} · ${contract}`, color: 'text-slate-700' },
          { label: isZH ? '年度節省' : 'Annual Savings', value: fmt(annualSavings),
            sub: isZH ? '月度 × 12' : 'Monthly × 12', color: 'text-emerald-600' },
          { label: isZH ? '年度淨收益' : 'Net Annual Benefit', value: fmt(netAnnual),
            sub: isZH ? '年節省 − Emma 年費' : 'Annual − Emma fee', color: 'text-blue-600' },
        ].map((k) => (
          <div key={k.label} className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-center">
            <p className="text-[10px] text-slate-500 mb-1">{k.label}</p>
            <p className={`text-lg font-bold tabular-nums ${k.color}`}>{k.value}</p>
            <p className="text-[9px] text-slate-400 mt-1">{k.sub}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl p-5 mb-5 text-center" style={{ background: '#1a1a2e' }}>
        <p className="text-[11px] font-semibold tracking-widest text-white/40 mb-3">
          EMMA AI ROI · TIER {tier.tier} · {tier.label} {isZH ? '人' : 'STAFF'}
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
      </div>

      <div className="space-y-4">
        {data.tiers.map((t) => {
          const repStaff = t.max_staff
          const basisAnn = Math.round(basisMonthly * (repStaff / basisStaff)) * 12
          const isActive = tier.tier === t.tier
          return (
            <div key={t.tier}
              className={`rounded-2xl border p-4 transition-colors ${isActive ? 'border-pink-300 bg-pink-50/30' : 'border-slate-200 bg-white'}`}>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-bold px-2.5 py-1 rounded-full text-white" style={{ background: PINK }}>
                  Tier {t.tier}
                </span>
                <span className="text-sm font-semibold text-slate-800">{t.label} {isZH ? '人' : 'Staff'}</span>
                {isActive && (
                  <span className="ml-auto text-[9px] font-bold text-pink-600 bg-pink-100 px-2 py-0.5 rounded-full">
                    {isZH ? '目前選擇' : 'Selected'}
                  </span>
                )}
              </div>
              <div className="overflow-x-auto rounded-xl border border-slate-100">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {(isZH
                        ? ['合約', '月費/人', '年度節省', 'Emma 年費', '年費-15%', '淨收益', 'ROI', '回本']
                        : ['Contract', 'Rate/User', 'Annual Saving', 'Emma Fee', 'Fee -15%', 'Net Benefit', 'ROI', 'Payback']
                      ).map((h) => (
                        <th key={h} className="px-2 py-2 text-[10px] font-semibold text-slate-400 uppercase text-left">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(Object.keys(t.rates) as string[]).map((yr) => {
                      const r = t.rates[yr]
                      const fee = repStaff * r * 12
                      const net = basisAnn - fee
                      const isChosen = yr === contract
                      return (
                        <tr key={yr} className={`border-b border-slate-50 ${isChosen ? 'bg-emerald-50/50' : ''}`}>
                          <td className={`px-2 py-2 font-bold ${isChosen ? 'text-emerald-700' : 'text-slate-600'}`}>
                            {yr}{isChosen && <span className="ml-1 text-[9px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">★</span>}
                          </td>
                          <td className="px-2 py-2 font-semibold text-slate-700 tabular-nums">HK${r}</td>
                          <td className="px-2 py-2 text-slate-600 tabular-nums">{fmt(basisAnn)}</td>
                          <td className="px-2 py-2 text-slate-500 tabular-nums">{fmt(fee)}</td>
                          <td className="px-2 py-2 text-slate-400 tabular-nums">{fmt(Math.round(fee * 0.85))}</td>
                          <td className={`px-2 py-2 font-bold tabular-nums ${isChosen ? 'text-emerald-700' : 'text-pink-600'}`}>{fmt(net)}</td>
                          <td className="px-2 py-2 font-bold text-blue-600">{fee ? (basisAnn / fee).toFixed(1) : '-'}x</td>
                          <td className="px-2 py-2 text-slate-500">{basisAnn ? (fee / (basisAnn / 12)).toFixed(1) : '-'}mo</td>
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
          ? '★ = 現時合約年期 · 節省基準取自本院舍實際事件、外購開支及員工人數'
          : "★ = current contract term · saving basis derived from this home's actual incidents, agency spend and headcount"}
      </p>
    </div>
  )
}

/* ── page ─────────────────────────────────────────────────────────────────── */
export default function ROIPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const [data, setData] = useState<RoiSummary | null>(null)
  const [draft, setDraft] = useState<Partial<RoiSettings>>({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const reload = useCallback(() => {
    api.roiSummary()
      .then((d) => {
        setData(d)
        setDraft({
          manager_hourly_rate: Number(d.settings.manager_hourly_rate),
          roster_hours_before: Number(d.settings.roster_hours_before),
          roster_hours_after: Number(d.settings.roster_hours_after),
          hours_saved_per_incident: Number(d.settings.hours_saved_per_incident),
          agency_reduction_pct: Number(d.settings.agency_reduction_pct),
          total_budget: Number(d.settings.total_budget),
          salary_budget: Number(d.settings.salary_budget),
          contract_years: d.emma.contract_years as RoiSettings['contract_years'],
          vacancies_json: (d.settings.vacancies_json ?? {}) as Record<string, number>,
        })
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load ROI'))
  }, [])

  useEffect(() => { reload() }, [reload])

  const commit = useCallback(async (patch: Partial<RoiSettings>) => {
    setSaving(true)
    setError('')
    try {
      await api.saveRoiSettings(patch)
      reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }, [reload])

  const setField = (key: keyof RoiSettings) => (v: number) =>
    setDraft((p) => ({ ...p, [key]: v }))

  if (error && !data) {
    return <div className="p-5"><div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-700">{error}</div></div>
  }
  if (!data) return <div className="p-5 text-xs text-gray-400">{isZH ? '載入中…' : 'Loading…'}</div>

  const T = {
    title:      isZH ? 'ROI 效益計算' : 'ROI Calculator',
    sub:        isZH ? '基於本院舍實際數據 · ROI v2.2 公式' : "Computed from this home's actual data · ROI v2.2 formulas",
    roiMult:    isZH ? 'ROI 倍數' : 'ROI Multiple',
    monthly:    isZH ? '月度節省' : 'Monthly Savings',
    annual:     isZH ? '年度節省' : 'Annual Savings',
    fee:        isZH ? 'Emma 月費' : 'Emma Monthly Fee',
    net:        isZH ? '年度淨收益' : 'Net Annual Benefit',
    baseline:   isZH ? 'ROI 基準設定' : 'ROI Baseline',
    baselineHint: isZH ? '這些數值會儲存到本院舍設定；其餘全部由實際數據計算'
                       : 'These are saved per facility; everything else is measured',
    budget:     isZH ? '本月總營運預算' : 'Monthly Operating Budget',
    salary:     isZH ? '本月薪金預算' : 'Monthly Salary Budget',
    rate:       isZH ? '經理/ASRN 時薪' : 'Manager/ASRN Hourly Rate',
    before:     isZH ? '排班前工時（月）' : 'Roster hours before (per month)',
    after:      isZH ? '排班後工時（月）' : 'Roster hours after (per month)',
    perIncident: isZH ? '每宗事件節省時數' : 'Hours saved per incident',
    reduction:  isZH ? '外購減少比例' : 'Agency reduction %',
    contract:   isZH ? '合約年期' : 'Contract term',
    staffTitle: isZH ? '員工基準（實際人數）' : 'Staff Baseline (measured headcount)',
    headcount:  isZH ? '在職人數' : 'Headcount',
    vacancies:  isZH ? '空缺' : 'Vacancies',
    totalStaff: isZH ? '總員工人數' : 'Total staff',
    ftpt:       isZH ? '全職 / 兼職' : 'Full-time / Part-time',
    partA:      isZH ? 'Part A - 管理時間節省' : 'Part A - Admin Time Saving',
    partB:      isZH ? 'Part B - 外購費用節省' : 'Part B - Agency Cost Saving',
    a1:         isZH ? 'A1 · 排班時間節省' : 'A1 · Roster Scheduling Time Saving',
    a2:         isZH ? 'A2 · 緊急補更節省' : 'A2 · Emergency Cover Saving',
    incidents:  isZH ? '本月實際事件' : 'Incidents this month (actual)',
    agencyCost: isZH ? '本月外購開支（實際）' : 'Agency spend this month (actual)',
    agencyShifts: isZH ? '外購更次' : 'agency shifts',
    scenario:   isZH ? '方案' : 'Scenario',
    reductionH: isZH ? '減少%' : 'Reduction',
    savingH:    isZH ? '月度節省' : 'Monthly Saving',
    rationale:  isZH ? '備註' : 'Rationale',
    adopted:    isZH ? '採用 ✓' : 'adopted ✓',
    summary:    isZH ? '節省彙總' : 'Savings Summary',
    totalMonthly: isZH ? '月度總節省' : 'Total Monthly Saving',
    costVs:     isZH ? 'Emma AI 費用 vs 節省' : 'Emma AI Cost vs Savings',
    scale:      isZH ? '規模化試算' : 'Scale Calculator',
    payback:    isZH ? '回本月數' : 'Months to Payback',
    saving:     isZH ? '儲存中…' : 'Saving…',
    pctBudget:  (p: number) => isZH ? `約佔年度預算 ${p}%` : `${p}% of the annual budget`,
    noAgency:   isZH ? '本月未有外購開支記錄' : 'No agency spend recorded this month',
  }

  return (
    <div className="p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{T.title}</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            {T.sub} · {data.month_start} → {data.month_end}
            {saving && <span className="ml-2 text-pink-500">{T.saving}</span>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-[10px] text-gray-400">{T.roiMult}</div>
            <div className="text-2xl font-bold text-pink-500">{data.emma.roi_multiple ?? '-'}x</div>
          </div>
          <div className="w-12 h-12 rounded-full border-4 border-pink-400 flex items-center justify-center text-[10px] font-bold text-pink-500 text-center leading-tight px-1">
            {data.emma.payback_months ?? '-'}{isZH ? '月' : 'mo'}
          </div>
        </div>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>}

      {/* KPI banner */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: T.monthly, value: fmt(data.totals.monthly_saving), color: 'text-pink-500' },
          { label: T.annual,  value: fmt(data.totals.annual_saving),  color: 'text-emerald-600',
            sub: data.totals.pct_of_annual_budget !== null
              ? T.pctBudget(data.totals.pct_of_annual_budget) : undefined },
          { label: T.fee,     value: fmt(data.emma.monthly_fee),      color: 'text-slate-700',
            sub: `Tier ${data.emma.tier} · HK$${data.emma.rate_per_user}/user · ${data.emma.contract_years}` },
          { label: T.net,     value: fmt(data.emma.net_annual_benefit), color: 'text-blue-600' },
        ].map((k) => (
          <div key={k.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{k.label}</div>
            <div className={`text-[20px] font-bold tabular-nums ${k.color}`}>{k.value}</div>
            {k.sub && <div className="mt-1 text-[10px] text-gray-500">{k.sub}</div>}
          </div>
        ))}
      </div>

      {/* Baseline settings */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">⚙️</div>
          <h2 className="text-base font-semibold text-slate-800">{T.baseline}</h2>
          <span className="ml-auto text-[10px] text-slate-400">{T.baselineHint}</span>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <InputField label={T.budget} value={draft.total_budget ?? 0} suffix="HK$"
            onChange={setField('total_budget')} onCommit={() => commit({ total_budget: draft.total_budget })} />
          <InputField label={T.salary} value={draft.salary_budget ?? 0} suffix="HK$"
            onChange={setField('salary_budget')} onCommit={() => commit({ salary_budget: draft.salary_budget })} />
          <InputField label={T.rate} value={draft.manager_hourly_rate ?? 0} suffix="HK$"
            hint="HK$70,720÷173h" onChange={setField('manager_hourly_rate')}
            onCommit={() => commit({ manager_hourly_rate: draft.manager_hourly_rate })} />
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-500">{T.contract}</label>
            <select value={draft.contract_years ?? '5yr'}
              onChange={(e) => {
                const v = e.target.value as RoiSettings['contract_years']
                setDraft((p) => ({ ...p, contract_years: v }))
                commit({ contract_years: v })
              }}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none">
              {['3yr', '5yr', '10yr'].map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <InputField label={T.before} value={draft.roster_hours_before ?? 0} suffix="h"
            hint={isZH ? '調查 n=2' : 'survey n=2'} onChange={setField('roster_hours_before')}
            onCommit={() => commit({ roster_hours_before: draft.roster_hours_before })} />
          <InputField label={T.after} value={draft.roster_hours_after ?? 0} suffix="h"
            onChange={setField('roster_hours_after')}
            onCommit={() => commit({ roster_hours_after: draft.roster_hours_after })} />
          <InputField label={T.perIncident} value={draft.hours_saved_per_incident ?? 0} suffix="h"
            onChange={setField('hours_saved_per_incident')}
            onCommit={() => commit({ hours_saved_per_incident: draft.hours_saved_per_incident })} />
          <InputField label={T.reduction} value={draft.agency_reduction_pct ?? 0} suffix="%"
            onChange={setField('agency_reduction_pct')}
            onCommit={() => commit({ agency_reduction_pct: draft.agency_reduction_pct })} />
        </div>
      </div>

      {/* Staff baseline - measured */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">👥</div>
          <h2 className="text-base font-semibold text-slate-800">{T.staffTitle}</h2>
          <span className="ml-auto text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
            Tier {data.emma.tier} · HK${data.emma.rate_per_user}/user/mo ({data.emma.contract_years})
          </span>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-4">
          <ReadOnlyField label={T.totalStaff} value={String(data.staff.total)} />
          <ReadOnlyField label={T.ftpt} value={`${data.staff.full_time} / ${data.staff.part_time}`} />
          <ReadOnlyField label={T.incidents} value={String(data.a2.incidents)} />
          <ReadOnlyField label={T.agencyCost} value={fmt(data.agency.monthly_cost)}
            sub={`${data.agency.shifts} ${T.agencyShifts}`} />
        </div>
        <div className="rounded-xl bg-slate-50 border border-slate-200 px-4 py-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-[10px] uppercase text-slate-400">
                <th className="py-1.5 pr-4">{isZH ? '職級' : 'Rank'}</th>
                {data.staff.by_rank.map((r) => (
                  <th key={r.rank} className="py-1.5 px-2 text-center">{r.rank}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-slate-200">
                <td className="py-1.5 pr-4 text-slate-500">{T.headcount}</td>
                {data.staff.by_rank.map((r) => (
                  <td key={r.rank} className="py-1.5 px-2 text-center font-semibold text-slate-800 tabular-nums">
                    {r.headcount}
                  </td>
                ))}
              </tr>
              <tr className="border-t border-slate-100">
                <td className="py-1.5 pr-4 text-slate-500">{T.vacancies}</td>
                {data.staff.by_rank.map((r) => (
                  <td key={r.rank} className="py-1.5 px-2 text-center">
                    <input type="number" value={r.vacancies}
                      onChange={(e) => {
                        const next = { ...(draft.vacancies_json ?? {}), [r.rank]: Number(e.target.value) || 0 }
                        setDraft((p) => ({ ...p, vacancies_json: next }))
                      }}
                      onBlur={() => commit({ vacancies_json: draft.vacancies_json })}
                      className="w-12 rounded-md border border-slate-200 bg-white px-1 py-0.5 text-center text-xs tabular-nums outline-none focus:border-pink-400" />
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Part A */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">⏱️</div>
          <h2 className="text-base font-semibold text-slate-800">{T.partA}</h2>
          <span className="ml-auto text-[9px] font-bold bg-pink-50 text-pink-500 px-2 py-0.5 rounded-full border border-pink-100">
            v2.2 FORMULA
          </span>
        </div>

        <div className="mb-4 rounded-xl bg-blue-50 border border-blue-100 p-4">
          <p className="text-xs font-bold text-blue-800 mb-2">{T.a1}</p>
          <div className="grid grid-cols-3 gap-3 mb-3">
            {[
              { l: isZH ? '排班前' : 'Before', v: `${data.a1.hours_before}h`, c: 'text-slate-500' },
              { l: isZH ? '排班後' : 'After',  v: `${data.a1.hours_after}h`,  c: 'text-emerald-600' },
              { l: isZH ? '節省時數' : 'Saved', v: `${data.a1.hours_saved}h`, c: 'text-blue-600' },
            ].map((x) => (
              <div key={x.l} className="rounded-xl bg-white p-3 text-center border border-blue-100">
                <p className="text-[9px] text-slate-500 mb-1">{x.l}</p>
                <p className={`text-xl font-bold tabular-nums ${x.c}`}>{x.v}</p>
              </div>
            ))}
          </div>
          <div className="rounded-lg bg-white/70 px-3 py-2 text-[11px] text-blue-700">
            <span className="font-bold">A1:</span> {data.a1.formula} = <span className="font-bold">{fmt(data.a1.saving)}/mo</span>
          </div>
        </div>

        <div className="rounded-xl bg-purple-50 border border-purple-100 p-4">
          <p className="text-xs font-bold text-purple-800 mb-2">{T.a2}</p>
          <div className="grid grid-cols-3 gap-3 mb-3">
            {[
              { l: T.incidents, v: String(data.a2.incidents), c: 'text-slate-700' },
              { l: isZH ? '每次節省' : 'Per incident', v: `${data.a2.hours_per_incident}h`, c: 'text-purple-600' },
              { l: isZH ? '節省時數/月' : 'Hours saved', v: `${data.a2.hours_saved}h`, c: 'text-purple-600' },
            ].map((x) => (
              <div key={x.l} className="rounded-xl bg-white p-3 text-center border border-purple-100">
                <p className="text-[9px] text-slate-500 mb-1">{x.l}</p>
                <p className={`text-xl font-bold tabular-nums ${x.c}`}>{x.v}</p>
              </div>
            ))}
          </div>
          <div className="rounded-lg bg-white/70 px-3 py-2 text-[11px] text-purple-700">
            <span className="font-bold">A2:</span> {data.a2.formula} = <span className="font-bold">{fmt(data.a2.saving)}/mo</span>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between rounded-xl border-2 border-blue-300 bg-blue-50 px-4 py-3">
          <div>
            <p className="text-sm font-bold text-slate-800">Part A (A1 + A2)</p>
            <p className="text-[11px] text-slate-500">{fmt(data.a1.saving)} + {fmt(data.a2.saving)}</p>
          </div>
          <p className="text-2xl font-bold text-blue-600 tabular-nums">{fmt(data.totals.admin_saving)}/mo</p>
        </div>
      </div>

      {/* Part B */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">🏥</div>
          <h2 className="text-base font-semibold text-slate-800">{T.partB}</h2>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 mb-4">
          <ReadOnlyField label={T.agencyCost} value={fmt(data.agency.monthly_cost)}
            sub={`${data.agency.shifts} ${T.agencyShifts}`} />
          <div className="rounded-xl bg-slate-50 border border-slate-200 p-3">
            <p className="text-[10px] text-slate-500 mb-1">{isZH ? '外購明細' : 'Agency breakdown'}</p>
            {data.agency.breakdown.length === 0
              ? <p className="text-[11px] text-slate-400">{T.noAgency}</p>
              : data.agency.breakdown.map((b) => (
                <p key={b.role} className="text-[11px] text-slate-600">
                  {b.role} · {b.shifts} {isZH ? '班' : 'shifts'}: {fmt(b.cost)}
                </p>
              ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 overflow-hidden mb-4">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                {[T.scenario, T.reductionH, T.savingH, T.rationale].map((h) => (
                  <th key={h} className="px-3 py-2 text-[10px] font-semibold text-slate-500 uppercase text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.agency.scenarios.map((s) => (
                <tr key={s.pct} className={`border-b border-slate-100 ${s.adopted ? 'bg-pink-50' : ''}`}>
                  <td className={`px-3 py-2.5 font-semibold ${s.adopted ? 'text-pink-600' : 'text-slate-500'}`}>
                    {s.key}{s.adopted ? ` - ${T.adopted}` : ''}
                  </td>
                  <td className={`px-3 py-2.5 font-bold tabular-nums ${s.adopted ? 'text-pink-600' : 'text-slate-400'}`}>{s.pct}%</td>
                  <td className={`px-3 py-2.5 font-bold tabular-nums ${s.adopted ? 'text-pink-600' : 'text-slate-400'}`}>{fmt(s.saving)}</td>
                  <td className="px-3 py-2.5 text-slate-500">{s.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between rounded-xl border-2 border-pink-300 bg-pink-50 px-4 py-3">
          <div>
            <p className="text-sm font-bold text-slate-800">Part B</p>
            <p className="text-[11px] text-slate-500">{data.agency.formula}</p>
          </div>
          <p className="text-2xl font-bold text-pink-600 tabular-nums">{fmt(data.agency.saving)}/mo</p>
        </div>
      </div>

      {/* Summary */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">💰</div>
          <h2 className="text-base font-semibold text-slate-800">{T.summary}</h2>
        </div>
        <div className="space-y-2.5">
          <SavingRow label={T.partA} saving={data.totals.admin_saving} color="blue"
            detail={`A1 ${fmt(data.a1.saving)} + A2 ${fmt(data.a2.saving)}`} />
          <SavingRow label={T.partB} saving={data.agency.saving} color="pink"
            detail={data.agency.formula} />
          <div className="flex items-center justify-between rounded-xl border-2 border-pink-300 bg-pink-50 px-4 py-3.5">
            <div>
              <p className="text-base font-bold text-slate-800">{T.totalMonthly}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {data.staff.total} {isZH ? '名員工 · 本月實測' : 'staff · measured this month'}
              </p>
            </div>
            <p className="text-2xl font-bold text-pink-600 tabular-nums">{fmt(data.totals.monthly_saving)}</p>
          </div>
        </div>
      </div>

      {/* Emma cost vs ROI */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">📊</div>
          <h2 className="text-base font-semibold text-slate-800">{T.costVs}</h2>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-5">
          {[
            { label: T.fee, value: fmt(data.emma.monthly_fee),
              sub: `${data.staff.total} × HK$${data.emma.rate_per_user}`, color: 'text-slate-800' },
            { label: isZH ? 'Emma 年費' : 'Emma Annual Fee', value: fmt(data.emma.annual_fee),
              sub: `${isZH ? '預付 -15%' : '-15% prepaid'}: ${fmt(data.emma.annual_fee_prepaid)}`, color: 'text-slate-800' },
            { label: T.annual, value: fmt(data.totals.annual_saving),
              sub: isZH ? '月節省 × 12' : 'Monthly × 12', color: 'text-emerald-600' },
            { label: T.net, value: fmt(data.emma.net_annual_benefit),
              sub: isZH ? '年節省 − Emma 年費' : 'Annual − Emma fee', color: 'text-blue-600' },
          ].map((k) => (
            <div key={k.label} className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-center">
              <p className="text-[10px] text-slate-500 mb-1">{k.label}</p>
              <p className={`text-lg font-bold tabular-nums ${k.color}`}>{k.value}</p>
              <p className="text-[9px] text-slate-400 mt-1">{k.sub}</p>
            </div>
          ))}
        </div>
        <div className="rounded-2xl p-5 text-center" style={{ background: '#1a1a2e' }}>
          <p className="text-[11px] font-semibold tracking-widest text-white/40 mb-3">
            EMMA AI ROI · TIER {data.emma.tier} · {data.emma.tier_label} · {data.emma.contract_years} HK${data.emma.rate_per_user}/user/mo
          </p>
          <div className="flex items-center justify-center gap-8">
            <div>
              <p className="text-4xl font-bold text-pink-400 tabular-nums">{data.emma.roi_multiple ?? '-'}x</p>
              <p className="text-[10px] text-white/50 mt-1">{T.roiMult}</p>
            </div>
            <div className="w-px h-12 bg-white/10" />
            <div>
              <p className="text-4xl font-bold text-emerald-400 tabular-nums">{data.emma.payback_months ?? '-'}</p>
              <p className="text-[10px] text-white/50 mt-1">{T.payback}</p>
            </div>
            <div className="w-px h-12 bg-white/10" />
            <div>
              <p className="text-3xl font-bold text-blue-400 tabular-nums">{fmt(data.emma.net_annual_benefit)}</p>
              <p className="text-[10px] text-white/50 mt-1">{T.net}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Scale calculator */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">📈</div>
          <h2 className="text-base font-semibold text-slate-800">{T.scale}</h2>
          <span className="ml-auto text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
            {isZH ? 'Sales Demo 用途' : 'Sales Demo'}
          </span>
        </div>
        <ScaleCalculator data={data} isZH={isZH} />
      </div>
    </div>
  )
}
