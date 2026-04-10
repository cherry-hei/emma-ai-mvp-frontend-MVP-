'use client'

import { useState, useMemo } from 'react'

// ── Types ──────────────────────────────────────────────────────────────
interface ComplianceInputs {
  ftRcwCount: number
  ftRcwAvgWorkDays: number
  ptRcwShiftsMonth: number
  totalResidents: number
  rnOnDutyAM: number
  hwOnDutyAM: number
  rnOnDutyPM: number
  hwOnDutyPM: number
}

interface ComplianceResult {
  ftShifts: number
  maxPtShifts: number
  usagePct: number
  remaining: number
  status: 'safe' | 'warning' | 'over'
}

// ── Static Data ────────────────────────────────────────────────────────
const SCORES = [
  { label: 'Staffing Ratio',      score: 94,  desc: '符合 1:6 標準' },
  { label: 'Staff Certification', score: 88,  desc: '2 項證書即將到期' },
  { label: 'Documentation',       score: 76,  desc: '部分 ICP 未更新' },
  { label: 'Incident Reports',    score: 100, desc: '本月零事故' },
]

const CHECKLIST = [
  { title: 'ICP 護理計劃更新',   desc: '3 名住客 ICP 超過 30 天未更新', status: 'warn' },
  { title: 'ACLS 證書 — 余逸詩', desc: '將於 28 天後到期',              status: 'warn' },
  { title: '本月藥物紀錄',       desc: '本月所有藥物紀錄已核對',        status: 'pass' },
  { title: '本月藥板',           desc: '本月藥板已核對',                status: 'pass' },
  { title: '下月藥物紀錄',       desc: '未核對，將於 10 天後到期',      status: 'warn' },
  { title: '下月藥板',           desc: '未核對，將於 10 天後到期',      status: 'warn' },
  { title: '消防演習紀錄',       desc: '上季度消防演習已完成',          status: 'pass' },
  { title: '感染控制巡查',       desc: '4 月已巡查',                    status: 'pass' },
]

const STAFFING_RATIO_SHIFTS = [
  { label: '早更 A (0700-1500)', ratios: ['RN 1:60', 'EN 1:60', 'HW 1:30', 'CW 1:20', 'AW 1:40'] },
  { label: '午更 P (1330-2130)', ratios: ['RN 1:60', 'EN 1:60', 'HW 1:30', 'CW 1:20', 'AW 1:40'] },
  { label: '夜更 N (2130-0700)', ratios: ['EN 1:60', 'HW 1:30', 'CW 1:40'] },
]

const SWD_RATIOS = [
  { role: 'EN/RN', window: '07:00–18:00 (11h)', ratio: '1:60',  residents: 60,  color: 'blue' },
  { role: 'HW',    window: '07:00–18:00 (11h)', ratio: '1:30',  residents: 30,  color: 'amber' },
  { role: 'CW',    window: '07:00–17:00 (10h)', ratio: '1:20',  residents: 20,  color: 'violet' },
  { role: 'CW',    window: '17:00–07:00 (14h)', ratio: '1:240', residents: 240, color: 'violet' },
  { role: 'AW',    window: '08:30–19:30 (11h)', ratio: '1:40',  residents: 40,  color: 'emerald' },
]

const ROLE_COLOR: Record<string, string> = {
  blue:    'bg-blue-50 text-blue-700 border-blue-200',
  amber:   'bg-amber-50 text-amber-700 border-amber-200',
  violet:  'bg-violet-50 text-violet-700 border-violet-200',
  emerald: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

const AGENCY_RULES = [
  { icon: '📊', title: '更數上限',   desc: '外購更數 ≤ 全職更數 × 50%（按更數計算，非人頭）' },
  { icon: '🕐', title: '可編更種',   desc: 'A更（07-15）、P更（13:30-21:30）、N更（21:30-07）' },
  { icon: '✅', title: '可做工序',   desc: '餵食、換片、沖涼、轉移（限4項）' },
  { icon: '👥', title: '人數上限',   desc: '最多 2名 HW/EN 外購；最多 12名 CW 外購' },
  { icon: '🎓', title: 'Audit 要求', desc: '未過 audit 新人只可派 A3/P3 task，不可獨立帶更' },
  { icon: '💰', title: '雙倍收費日', desc: '中秋正日、冬至、年三十、初一、初二、初三（全年6天）' },
]

const AGENCY_RATES = [
  { role: 'PT RN',  ap: 1950, n: 2150 },
  { role: 'PT EN',  ap: 1700, n: 1900 },
  { role: 'PT HW',  ap: 950,  n: 1150 },
  { role: 'PT RCW', ap: 930,  n: 1130 },
]

const MARCH_AGENCY = [
  { type: 'PT RCW',   shifts: 124, rate: 955,  total: 118520 },
  { type: 'PT HW/EN', shifts: 24,  rate: 1231, total: 29550 },
]

// ── Helpers ────────────────────────────────────────────────────────────
const fmt = (n: number) => `HK$${n.toLocaleString()}`

function computeCompliance(inputs: ComplianceInputs): ComplianceResult {
  const ftShifts    = inputs.ftRcwCount * inputs.ftRcwAvgWorkDays
  const maxPtShifts = Math.floor(ftShifts / 2)
  const usagePct    = ftShifts > 0
    ? Math.round((inputs.ptRcwShiftsMonth / ftShifts) * 100) : 0
  const remaining   = maxPtShifts - inputs.ptRcwShiftsMonth
  const status: ComplianceResult['status'] =
    usagePct >= 50 ? 'over' : usagePct >= 40 ? 'warning' : 'safe'
  return { ftShifts, maxPtShifts, usagePct, remaining, status }
}

function InputField({
  label, value, onChange, suffix = '', hint,
}: {
  label: string; value: number; onChange: (v: number) => void
  suffix?: string; hint?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-500">
        {label}
        {hint && <span className="ml-1.5 text-[10px] text-slate-400">({hint})</span>}
      </label>
      <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 focus-within:border-pink-400 focus-within:ring-1 focus-within:ring-pink-400/20 transition-all">
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

function StatusBadge({ status }: { status: 'safe' | 'warning' | 'over' | 'ok' }) {
  const cfg = {
    safe:    { label: '✅ 符合規定', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
    ok:      { label: '✅ 符合規定', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
    warning: { label: '⚠️ 接近上限', cls: 'bg-orange-50 text-orange-700 border-orange-200' },
    over:    { label: '🚨 超出上限', cls: 'bg-red-50 text-red-700 border-red-200' },
  }[status]
  return (
    <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${cfg.cls}`}>
      {cfg.label}
    </span>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────
export default function CompliancePage() {
  const [inputs, setInputs] = useState<ComplianceInputs>({
    ftRcwCount: 19,
    ftRcwAvgWorkDays: 16,
    ptRcwShiftsMonth: 111,
    totalResidents: 60,
    rnOnDutyAM: 1,
    hwOnDutyAM: 2,
    rnOnDutyPM: 1,
    hwOnDutyPM: 2,
  })

  const set = (key: keyof ComplianceInputs) => (v: number) =>
    setInputs(prev => ({ ...prev, [key]: v }))

  const cr = useMemo(() => computeCompliance(inputs), [inputs])

  const requiredRN  = Math.ceil(inputs.totalResidents / 60)
  const requiredHW  = Math.ceil(inputs.totalResidents / 30)
  const ratioChecks = [
    { label: 'EN/RN（AM）', required: requiredRN, actual: inputs.rnOnDutyAM, ok: inputs.rnOnDutyAM >= requiredRN },
    { label: 'HW（AM）',    required: requiredHW, actual: inputs.hwOnDutyAM, ok: inputs.hwOnDutyAM >= requiredHW },
    { label: 'EN/RN（PM）', required: requiredRN, actual: inputs.rnOnDutyPM, ok: inputs.rnOnDutyPM >= requiredRN },
    { label: 'HW（PM）',    required: requiredHW, actual: inputs.hwOnDutyPM, ok: inputs.hwOnDutyPM >= requiredHW },
  ]
  const allRatioOk = ratioChecks.every(r => r.ok)

  const barCfg = {
    safe:    { bar: 'bg-emerald-500', border: 'border-emerald-200 bg-emerald-50', text: 'text-emerald-700' },
    warning: { bar: 'bg-orange-400',  border: 'border-orange-200 bg-orange-50',  text: 'text-orange-700'  },
    over:    { bar: 'bg-red-500',     border: 'border-red-200 bg-red-50',        text: 'text-red-700'     },
  }[cr.status]

  return (
    <div className="p-5 space-y-5">

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Compliance 合規中心</h1>
          <p className="text-xs text-gray-500 mt-0.5">RCHE 法規合規狀態 · 2026 Q1 · March 實際數字</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={allRatioOk ? 'safe' : 'over'} />
          <button className="px-3 py-1.5 text-xs rounded-lg text-white font-medium" style={{ background: '#f28f9e' }}>
            匯出報告
          </button>
        </div>
      </div>

      {/* ── KPI Score Cards ── */}
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

      {/* ── 合規檢查清單 ── */}
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

      {/* ── 人手比例合規狀態（靜態） ── */}
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

      {/* ── SWD 最低人手比率（互動） ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">🏥</div>
            <h2 className="text-base font-semibold text-slate-800">SWD 最低人手比率（互動計算）</h2>
          </div>
          <StatusBadge status={allRatioOk ? 'safe' : 'over'} />
        </div>

        <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">院舍人數 & 當更人手</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-5">
          <InputField label="院友人數"         value={inputs.totalResidents} onChange={set('totalResidents')} suffix="人" hint="影響所需人手" />
          <InputField label="AM EN/RN 當更人數" value={inputs.rnOnDutyAM}    onChange={set('rnOnDutyAM')}    suffix="人" />
          <InputField label="AM HW 當更人數"    value={inputs.hwOnDutyAM}    onChange={set('hwOnDutyAM')}    suffix="人" />
          <InputField label="PM EN/RN 當更人數" value={inputs.rnOnDutyPM}    onChange={set('rnOnDutyPM')}    suffix="人" />
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-5">
          {ratioChecks.map((rc) => (
            <div key={rc.label} className={`rounded-xl border p-3 text-center ${rc.ok ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'}`}>
              <p className="text-[10px] text-slate-500 mb-1">{rc.label}</p>
              <p className={`text-xl font-bold tabular-nums ${rc.ok ? 'text-emerald-600' : 'text-red-600'}`}>
                {rc.actual}<span className="text-xs font-normal text-slate-400">/{rc.required}</span>
              </p>
              <p className={`text-[10px] mt-1 font-semibold ${rc.ok ? 'text-emerald-600' : 'text-red-600'}`}>
                {rc.ok ? '✅ 達標' : '🚨 不足'}
              </p>
            </div>
          ))}
        </div>

        <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">SWD 法定比率參考表</p>
        <div className="overflow-x-auto rounded-xl border border-slate-100">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="text-left px-3 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">職位</th>
                <th className="text-left px-3 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">當值時段</th>
                <th className="text-center px-3 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">法定比率</th>
                <th className="text-center px-3 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">60位院友所需</th>
              </tr>
            </thead>
            <tbody>
              {SWD_RATIOS.map((r, i) => (
                <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                  <td className="px-3 py-2.5">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${ROLE_COLOR[r.color]}`}>{r.role}</span>
                  </td>
                  <td className="px-3 py-2.5 text-slate-600">{r.window}</td>
                  <td className="px-3 py-2.5 text-center font-bold text-slate-800">{r.ratio}</td>
                  <td className="px-3 py-2.5 text-center">
                    <span className="font-bold text-pink-500">{Math.ceil(60 / r.residents)}</span>
                    <span className="text-slate-400"> 人</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[10px] text-slate-400">💡 1名 EN/RN 可等同 2名 HW 計算（SWD 認可）</p>
      </div>

      {/* ── 外購 RCW 合規檢查 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">🛡️</div>
          <h2 className="text-base font-semibold text-slate-800">外購 RCW 合規檢查</h2>
          <span className="ml-2 text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">獨立監察 · 不計入 ROI</span>
        </div>

        <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">輸入數字</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-5">
          <InputField label="全職 RCW 人數"        value={inputs.ftRcwCount}       onChange={set('ftRcwCount')}       suffix="人" hint="March 實際 19人" />
          <InputField label="FT RCW 平均出勤日/月" value={inputs.ftRcwAvgWorkDays} onChange={set('ftRcwAvgWorkDays')} suffix="日" hint="扣休假後實際" />
          <InputField label="本月外購 RCW 更數"    value={inputs.ptRcwShiftsMonth} onChange={set('ptRcwShiftsMonth')} suffix="更" hint="March 實際 111更" />
        </div>

        <div className={`rounded-2xl border p-5 ${barCfg.border}`}>
          <div className="flex items-start justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-slate-800">外購更數 vs 全職更數</p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {inputs.ftRcwCount}人 × {inputs.ftRcwAvgWorkDays}日 = <strong>{cr.ftShifts}更</strong>（全職）；
                上限 = {cr.ftShifts} × 50% = <strong>{cr.maxPtShifts}更</strong>
              </p>
            </div>
            <StatusBadge status={cr.status} />
          </div>

          <div className="mb-1 flex justify-between text-xs text-slate-500">
            <span>外購佔全職更數比率</span>
            <span className={`font-bold tabular-nums ${barCfg.text}`}>{cr.usagePct}% / 上限 50%</span>
          </div>
          <div className="relative h-3 w-full rounded-full bg-white/60 overflow-hidden mb-1">
            <div className={`h-full rounded-full transition-all duration-700 ${barCfg.bar}`}
              style={{ width: `${Math.min((cr.usagePct / 50) * 100, 100)}%` }} />
          </div>
          <p className="text-center text-[9px] text-slate-400 mb-4">← 安全區 ｜ 50% 上限 ｜ 違規 →</p>

          <div className="grid grid-cols-3 gap-2 mb-4">
            {[
              { label: '全職更數/月',    value: `${cr.ftShifts}更` },
              { label: '外購上限 (50%)', value: `${cr.maxPtShifts}更` },
              { label: '本月外購更數',   value: `${inputs.ptRcwShiftsMonth}更` },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-xl bg-white/70 p-2.5 text-center">
                <p className="text-[10px] text-slate-500">{label}</p>
                <p className="text-sm font-bold text-slate-800 tabular-nums">{value}</p>
              </div>
            ))}
          </div>

          <div className={`rounded-xl px-3 py-2 text-center text-xs font-medium ${cr.remaining >= 0 ? 'bg-white/60 text-slate-600' : 'bg-red-100 text-red-700'}`}>
            {cr.remaining >= 0
              ? `尚餘 ${cr.remaining} 更外購空間 — Emma 排更時自動提示剩餘配額`
              : `超出 ${Math.abs(cr.remaining)} 更 — 須減少外購或向 SWD 申請豁免`}
          </div>
        </div>
      </div>

      {/* ── March 2026 外購費用實況 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">💰</div>
          <h2 className="text-base font-semibold text-slate-800">March 2026 外購費用實況</h2>
        </div>

        <div className="space-y-2.5 mb-4">
          {MARCH_AGENCY.map((a) => (
            <div key={a.type} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
              <div>
                <p className="text-sm font-semibold text-slate-800">{a.type}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">{a.shifts}更 × 平均 {fmt(a.rate)}/更</p>
              </div>
              <p className="text-sm font-bold text-pink-500 tabular-nums">{fmt(a.total)}</p>
            </div>
          ))}
          <div className="flex items-center justify-between rounded-xl border-2 border-pink-200 bg-pink-50 px-4 py-3">
            <p className="text-sm font-bold text-slate-800">月費合計</p>
            <div className="text-right">
              <p className="text-lg font-bold text-pink-600 tabular-nums">{fmt(MARCH_AGENCY.reduce((s, a) => s + a.total, 0))}</p>
              <p className="text-[11px] text-slate-400">March 2026 實際</p>
            </div>
          </div>
        </div>

        <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">外購收費表（每更）</p>
        <div className="overflow-x-auto rounded-xl border border-slate-100">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="text-left px-3 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">職位</th>
                <th className="text-center px-3 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">A更 / P更</th>
                <th className="text-center px-3 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">N更</th>
              </tr>
            </thead>
            <tbody>
              {AGENCY_RATES.map((r) => (
                <tr key={r.role} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                  <td className="px-3 py-2.5 font-semibold text-slate-700">{r.role}</td>
                  <td className="px-3 py-2.5 text-center font-bold text-slate-800 tabular-nums">{fmt(r.ap)}</td>
                  <td className="px-3 py-2.5 text-center font-bold text-pink-500 tabular-nums">{fmt(r.n)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[10px] text-slate-400">🎄 雙倍收費節日（全年6天）：中秋節正日、冬至、農曆年前夕、初一、初二、初三</p>
      </div>

      {/* ── SWD 外購規定清單 ── */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">📋</div>
          <h2 className="text-base font-semibold text-slate-800">SWD 外購規定清單</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {AGENCY_RULES.map((rule) => (
            <div key={rule.title} className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3.5">
              <span className="text-xl flex-shrink-0">{rule.icon}</span>
              <div>
                <p className="text-sm font-semibold text-slate-800">{rule.title}</p>
                <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{rule.desc}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-xl bg-pink-500 px-4 py-3 text-center">
          <p className="text-sm font-semibold text-white">
            Emma AI 排更時自動計算外購配額 · 超出上限前即時警示 🛡️
          </p>
        </div>
      </div>

    </div>
  )
}