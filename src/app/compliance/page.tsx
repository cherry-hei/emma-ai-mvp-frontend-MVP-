'use client'

import { useState, useMemo } from 'react'

const PINK = '#E8187A'

interface ComplianceInputs {
  totalResidents:      number
  ftRnPerAShift:       number
  ftRnPerPShift:       number
  ftEnPerAShift:       number
  ftEnPerPShift:       number
  ftHwPerAShift:       number
  ftHwPerPShift:       number
  agencyHwPerShift:    number
  ftRcwPerAShift:      number
  agencyRcwPerAShift:  number
  ftRcwPerPShift:      number
  agencyRcwPerPShift:  number
  ftRcwPerNShift:      number
  agencyRcwPerNShift:  number
  ftRcwCount:          number
  ftRcwAvgWorkDays:    number
  ptRcwShiftsMonth:    number
}

const SCORES = [
  { label: 'RN 覆蓋率',     score: 68, desc: 'P更43% / A更18% 無RN' },
  { label: 'Staff Ratio',   score: 88, desc: '個別更次剛達標' },
  { label: 'Certification', score: 85, desc: '2項證書30天內到期' },
  { label: 'CL/AN 管理',   score: 55, desc: 'CL積壓156.5h / 22人AN超限' },
]

const AUDIT_ITEMS = [
  { item: 'RN 覆蓋（P更）',      status: 'over', detail: 'P更 12/28天（43%）無 FT RN 在場 — 最嚴重違規', ref: 'Cap.459A s.11(1)', freq: '12/28天' },
  { item: 'RN 覆蓋（A更）',      status: 'over', detail: 'A更 5/28天（18%）無 FT RN 在場',               ref: 'Cap.459A s.11(1)', freq: '5/28天'  },
  { item: 'RCW 人數（P更）',     status: 'over', detail: 'P更 2天總人數僅5人（最低要求6人）',             ref: 'Cap.459A Sch.1',   freq: '2/28天'  },
  { item: 'AN更 超限',           status: 'warn', detail: '22名員工月AN更數超過2次（院舍內部規定）',       ref: '院舍內部規定',     freq: '全月持續' },
  { item: 'CL 積壓管理',         status: 'warn', detail: '全院積壓 CL 156.5h — 財務負債，影響排更彈性', ref: '僱傭條例 Cap.57',  freq: '持續累積' },
  { item: 'RCW PT比率（A/P更）', status: 'ok',   detail: 'A更外購≤3人 / P更外購≤3人 — 符合50%上限 ✓',  ref: 'Cap.459A s.11(3)', freq: '—'        },
  { item: 'Agency Staff 人數',   status: 'ok',   detail: '13名活躍外購員工 — 在SWD批准上限內 ✓',        ref: 'Cap.459A Sch.1',   freq: '—'        },
  { item: 'RCW12 長期SL',        status: 'warn', detail: '1名RCW整月病假 — 直接導致外購成本急升',        ref: '—',               freq: '單一事件' },
  { item: '節假日外購預警',       status: 'warn', detail: '6個雙倍費率節日未設預算提醒',                 ref: '—',               freq: '每年6天'  },
  { item: '交更記錄',             status: 'ok',   detail: '所有交更紀錄已完成 ✓',                        ref: 'SWD Guideline',    freq: '—'        },
]

const CERTS = [
  { name: 'Leung Ka Kei',  role: 'EN',  cert: 'First Aid',     expiry: '2026-04-15', daysLeft: 3,   status: 'over' },
  { name: 'Wong Jing Yin', role: 'PCW', cert: 'BLS',           expiry: '2026-04-20', daysLeft: 8,   status: 'warn' },
  { name: 'Yu Yat Sze',    role: 'RN',  cert: 'ACLS',          expiry: '2026-05-01', daysLeft: 19,  status: 'warn' },
  { name: 'Ho Kai Ching',  role: 'CW',  cert: 'Personal Care', expiry: '2026-06-30', daysLeft: 79,  status: 'ok'   },
  { name: 'Wong Yat Sum',  role: 'HW',  cert: 'Elder Care',    expiry: '2026-08-10', daysLeft: 120, status: 'ok'   },
  { name: 'Li Shao Hung',  role: 'AW',  cert: 'Infection Ctrl',expiry: '2027-01-15', daysLeft: 278, status: 'ok'   },
]

const VIOLATIONS = [
  { level: 'over', label: '🔴 RN P更空更',    detail: 'P更12天(43%)無RN',         law: 'Cap.459A s.11(1)', action: '排班時強制確認RN覆蓋；自動觸發後備RN通知' },
  { level: 'over', label: '🔴 RN A更空更',    detail: 'A更5天(18%)無RN',          law: 'Cap.459A s.11(1)', action: '同上' },
  { level: 'over', label: '🔴 RCW P更不達標', detail: 'P更2天總人數僅5（min=6）', law: 'Cap.459A Sch.1',   action: '即時阻截；提示加排1名外購RCW' },
  { level: 'warn', label: '🟠 AN超限',        detail: '22名員工月AN更超2次',       law: '院舍內部規定',     action: '加入第3次AN時阻截' },
  { level: 'warn', label: '🟠 CL積壓',        detail: '全院積壓156.5h',           law: '僱傭條例Cap.57',   action: '月度CL財務負債報告 + 更表優先安排' },
  { level: 'warn', label: '🟡 RCW12全月SL',  detail: '整月病假致外購急升',        law: '—',               action: '長期SL預測 + 外購成本預警' },
  { level: 'warn', label: '🟡 節假日外購',    detail: '6個雙倍費率節日無預算提醒', law: '—',               action: '排班前30天節日費率警示' },
]

const AGENCY_RULES = [
  { icon: '📊', title: '更數上限',   desc: '特定鐘點（A/P更）外購 ≤ 最低人手 × 50%；N更無上限' },
  { icon: '🕐', title: '可編更種',   desc: 'A更（07-15）、P更（13:30-21:30）、N更（21:30-07）' },
  { icon: '✅', title: '可做工序',   desc: '餵食、換片、沖涼、轉移（限4項）' },
  { icon: '👥', title: '人數上限',   desc: '最多 1個HW unit外購；PT EN不可使用（超出HW cap）' },
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
  { type: 'PT RCW（124更）',  shifts: 124, rate: 955,  total: 118520 },
  { type: 'PT EN/HW（24更）', shifts: 24,  rate: 1231, total: 29550  },
]

const ROLE_COLOR: Record<string, string> = {
  RN:  'bg-blue-50 text-blue-700',
  EN:  'bg-green-50 text-green-700',
  HW:  'bg-amber-50 text-amber-800',
  CW:  'bg-rose-50 text-rose-700',
  PCW: 'bg-purple-50 text-purple-700',
  AW:  'bg-gray-100 text-gray-600',
}

const statusCfg = {
  ok:   { dot: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: '✓ 合規' },
  warn: { dot: 'bg-amber-400',   badge: 'bg-amber-50 text-amber-700 border-amber-200',       label: '⚠ 留意' },
  over: { dot: 'bg-red-500',     badge: 'bg-red-50 text-red-700 border-red-200',             label: '✕ 違規' },
}

const fmt = (n: number) => `HK$${n.toLocaleString()}`

function InputField({ label, value, onChange, suffix = '', hint }: {
  label: string; value: number; onChange: (v: number) => void; suffix?: string; hint?: string
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

function computeRatioCompliance(i: ComplianceInputs) {
  const calcBase  = Math.ceil(i.totalResidents / 20) * 20
  const minRCW_AP = Math.floor(calcBase / 20)
  const minRCW_N  = Math.ceil(i.totalResidents / 35)
  const capRCW_AP = Math.floor(minRCW_AP * 0.5)
  const minHW_AP  = Math.floor(calcBase / 60)
  const capHW_AP  = Math.floor(minHW_AP * 0.5)

  const hwUnitsA = (i.ftEnPerAShift * 2) + i.ftHwPerAShift + i.agencyHwPerShift
  const hwUnitsP = (i.ftEnPerPShift * 2) + i.ftHwPerPShift + i.agencyHwPerShift

  return {
    calcBase, minRCW_AP, minRCW_N, capRCW_AP, minHW_AP, capHW_AP,
    checks: [
      { label: 'RN A更',  category: 'RN',  ft: i.ftRnPerAShift, agency: 0, total: i.ftRnPerAShift,
        minReq: 1, ptCap: 0, ok: i.ftRnPerAShift >= 1, ptOk: true, note: 'PT RN 不計入最低要求' },
      { label: 'RN P更',  category: 'RN',  ft: i.ftRnPerPShift, agency: 0, total: i.ftRnPerPShift,
        minReq: 1, ptCap: 0, ok: i.ftRnPerPShift >= 1, ptOk: true, note: '3月實際：12天=0（最嚴重違規）' },
      { label: 'HW units A更', category: 'HW', ft: hwUnitsA, agency: i.agencyHwPerShift, total: hwUnitsA,
        minReq: minHW_AP, ptCap: capHW_AP, ok: hwUnitsA >= minHW_AP, ptOk: i.agencyHwPerShift <= capHW_AP,
        note: `1 EN=2 HW units；A更：(${i.ftEnPerAShift}EN×2)+(${i.ftHwPerAShift}HW)=${hwUnitsA}units` },
      { label: 'HW units P更', category: 'HW', ft: hwUnitsP, agency: i.agencyHwPerShift, total: hwUnitsP,
        minReq: minHW_AP, ptCap: capHW_AP, ok: hwUnitsP >= minHW_AP, ptOk: i.agencyHwPerShift <= capHW_AP,
        note: `P更：(${i.ftEnPerPShift}EN×2)+(${i.ftHwPerPShift}HW)=${hwUnitsP}units` },
      { label: 'RCW A更', category: 'RCW', ft: i.ftRcwPerAShift, agency: i.agencyRcwPerAShift,
        total: i.ftRcwPerAShift + i.agencyRcwPerAShift, minReq: minRCW_AP, ptCap: capRCW_AP,
        ok: i.ftRcwPerAShift + i.agencyRcwPerAShift >= minRCW_AP, ptOk: i.agencyRcwPerAShift <= capRCW_AP,
        note: `特定鐘點 PT上限≤${capRCW_AP}人` },
      { label: 'RCW P更', category: 'RCW', ft: i.ftRcwPerPShift, agency: i.agencyRcwPerPShift,
        total: i.ftRcwPerPShift + i.agencyRcwPerPShift, minReq: minRCW_AP, ptCap: capRCW_AP,
        ok: i.ftRcwPerPShift + i.agencyRcwPerPShift >= minRCW_AP, ptOk: i.agencyRcwPerPShift <= capRCW_AP,
        note: '3月實際：2天僅5人（違規）' },
      { label: 'RCW N更', category: 'RCW', ft: i.ftRcwPerNShift, agency: i.agencyRcwPerNShift,
        total: i.ftRcwPerNShift + i.agencyRcwPerNShift, minReq: minRCW_N, ptCap: null,
        ok: i.ftRcwPerNShift + i.agencyRcwPerNShift >= minRCW_N, ptOk: true,
        note: '指明期間外 — 無PT上限' },
    ]
  }
}

export default function CompliancePage() {
  const [tab, setTab] = useState<'ratio' | 'certs' | 'agency' | 'audit'>('audit')
  const [inputs, setInputs] = useState<ComplianceInputs>({
    totalResidents: 105,
    ftRnPerAShift: 1, ftRnPerPShift: 1,
    ftEnPerAShift: 1, ftEnPerPShift: 1,
    ftHwPerAShift: 4, ftHwPerPShift: 3, agencyHwPerShift: 0,
    ftRcwPerAShift: 7, agencyRcwPerAShift: 2,
    ftRcwPerPShift: 4, agencyRcwPerPShift: 2,
    ftRcwPerNShift: 3, agencyRcwPerNShift: 1,
    ftRcwCount: 19, ftRcwAvgWorkDays: 16, ptRcwShiftsMonth: 111,
  })

  const set = (key: keyof ComplianceInputs) => (v: number) =>
    setInputs(prev => ({ ...prev, [key]: v }))

  const ratio = useMemo(() => computeRatioCompliance(inputs), [inputs])

  const okCount   = AUDIT_ITEMS.filter(a => a.status === 'ok').length
  const warnCount = AUDIT_ITEMS.filter(a => a.status === 'warn').length
  const overCount = AUDIT_ITEMS.filter(a => a.status === 'over').length
  const score     = Math.round((okCount / AUDIT_ITEMS.length) * 100)

  return (
    <div className="p-5 space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Compliance 合規中心</h1>
          <p className="text-xs text-gray-500 mt-0.5">Cap.459A 實時監控 · March 2026 · 105院友</p>
        </div>
        <button className="px-3 py-1.5 text-xs rounded-lg text-white font-medium" style={{ background: PINK }}>
          匯出報告
        </button>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-4 gap-3">
        {SCORES.map(s => (
          <div key={s.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{s.label}</div>
            <div className="text-[28px] font-bold"
              style={{ color: s.score >= 90 ? '#10B981' : s.score >= 70 ? '#F59E0B' : PINK }}>
              {s.score}%
            </div>
            <div className="w-full h-1.5 bg-gray-100 rounded-full mt-2 overflow-hidden">
              <div className="h-full rounded-full"
                style={{ width: `${s.score}%`, background: s.score >= 90 ? '#10B981' : s.score >= 70 ? '#F59E0B' : PINK }} />
            </div>
            <div className="text-[10px] text-gray-400 mt-1">{s.desc}</div>
          </div>
        ))}
      </div>

      {/* Violation Banner */}
      <div className="rounded-xl border border-red-200 bg-red-50 p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-sm font-bold text-red-700">🔴 March 2026 違規問題總表</span>
          <span className="text-[10px] bg-red-100 text-red-600 px-2 py-0.5 rounded-full border border-red-200">
            {VIOLATIONS.filter(v => v.level === 'over').length}項違規 · {VIOLATIONS.filter(v => v.level === 'warn').length}項警告
          </span>
        </div>
        <div className="space-y-2">
          {VIOLATIONS.map((v, i) => (
            <div key={i} className={`flex items-start justify-between rounded-lg px-3 py-2
              ${v.level === 'over' ? 'bg-red-100' : 'bg-amber-50 border border-amber-100'}`}>
              <div className="flex-1">
                <span className="text-xs font-bold text-slate-800">{v.label}</span>
                <span className="text-[10px] text-slate-500 ml-2">{v.detail}</span>
              </div>
              <span className="text-[9px] text-slate-400 flex-shrink-0 ml-3">{v.law}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {[
          { id: 'audit',  label: '📊 合規審核' },
          { id: 'ratio',  label: '🏥 人手比率' },
          { id: 'certs',  label: '📋 證書管理' },
          { id: 'agency', label: '🛡️ 外購管理' },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id as typeof tab)}
            className="px-4 py-2 text-xs font-semibold border-b-2 transition-all"
            style={{ borderBottomColor: tab === t.id ? PINK : 'transparent', color: tab === t.id ? PINK : '#6b7280' }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── 合規審核 ── */}
      {tab === 'audit' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900">月度合規審核 — March 2026</h2>
            <div className="flex gap-2">
              {[
                { label: `✅ ${okCount} 合規`,   bg: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
                { label: `⚠️ ${warnCount} 留意`, bg: 'bg-amber-50 text-amber-700 border-amber-200' },
                { label: `🔴 ${overCount} 違規`, bg: 'bg-red-50 text-red-700 border-red-200' },
              ].map(b => (
                <span key={b.label} className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${b.bg}`}>{b.label}</span>
              ))}
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  {['合規項目', '頻率', '狀態', '詳情', '法規'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-[10px] font-semibold text-gray-500 uppercase tracking-wide text-left">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {AUDIT_ITEMS.map((item, i) => {
                  const cfg = statusCfg[item.status as keyof typeof statusCfg]
                  return (
                    <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50">
                      <td className="px-3 py-3 font-semibold text-gray-800">{item.item}</td>
                      <td className="px-3 py-3 text-[10px] text-gray-500 whitespace-nowrap">{item.freq}</td>
                      <td className="px-3 py-3">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${cfg.badge}`}>{cfg.label}</span>
                      </td>
                      <td className="px-3 py-3 text-[10px] text-gray-500 max-w-xs">{item.detail}</td>
                      <td className="px-3 py-3 text-[10px] text-gray-400 whitespace-nowrap">{item.ref}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl border border-gray-200 bg-white p-3.5 text-center">
              <div className="text-[10px] text-gray-500 mb-1">本月合規評分</div>
              <div className="text-2xl font-bold" style={{ color: score >= 70 ? '#10B981' : PINK }}>{score}%</div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-3.5 text-center">
              <div className="text-[10px] text-gray-500 mb-1">上月評分</div>
              <div className="text-2xl font-bold text-gray-700">71%</div>
            </div>
            <div className="rounded-xl p-3.5 text-center" style={{ background: '#fce8f3', border: `1px solid rgba(232,24,122,.3)` }}>
              <div className="text-[10px] text-gray-500 mb-1">改善幅度</div>
              <div className="text-2xl font-bold" style={{ color: PINK }}>{score >= 71 ? '+' : ''}{score - 71}%</div>
            </div>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <h3 className="text-xs font-semibold text-gray-700 mb-3">✦ Emma AI 改善建議（優先順序）</h3>
            <div className="space-y-2">
              {[
                { p: '1', action: '立即為所有P更補排FT RN，或聯絡外購RN覆蓋（12/28天=43%違規）', urgent: true },
                { p: '2', action: '安排 Leung Ka Kei 本週完成 First Aid 更新（3天後到期）',       urgent: true },
                { p: '3', action: '建立AN更阻截規則：每人每月第3次AN更自動阻截確認',               urgent: false },
                { p: '4', action: '制定月度CL消化計劃：優先安排156.5h積壓員工提早離班',           urgent: false },
                { p: '5', action: '設定6個節假日外購費率預警（30天前自動提示預算）',               urgent: false },
              ].map(r => (
                <div key={r.p} className={`flex items-start gap-3 p-3 rounded-xl ${r.urgent ? 'bg-red-50' : 'bg-gray-50'}`}>
                  <div className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0"
                    style={r.urgent ? { background: PINK, color: 'white' } : { background: '#e5e7eb', color: '#6b7280' }}>
                    {r.p}
                  </div>
                  <span className="text-[11px] text-gray-700 leading-relaxed">{r.action}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── 人手比率 ── */}
      {tab === 'ratio' && (
        <div className="space-y-5">
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold text-gray-700">院舍基本參數</h3>
              <span className="text-[10px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full border border-blue-100">
                計算基準：{ratio.calcBase}人
              </span>
            </div>
            <div className="max-w-xs">
              <InputField label="院友人數" value={inputs.totalResidents} onChange={set('totalResidents')} suffix="人" hint="105人→基準120人" />
            </div>
            <div className="mt-3 rounded-xl bg-blue-50 border border-blue-100 px-4 py-2.5">
              <p className="text-[10px] text-blue-700">
                📌 最低RCW（A/P更）= {ratio.calcBase}÷20 = <strong>{ratio.minRCW_AP}人</strong>；
                PT上限 = <strong>≤{ratio.capRCW_AP}人</strong>；
                HW最低 = <strong>{ratio.minHW_AP} units</strong>（1 EN=2 HW units）；N更無PT上限
              </p>
            </div>
          </div>

          {[
            {
              title: 'RN 覆蓋（全時段 min=1；PT不計入最低）',
              keys: [
                { label: 'A更 FT RN', k: 'ftRnPerAShift' as keyof ComplianceInputs },
                { label: 'P更 FT RN', k: 'ftRnPerPShift' as keyof ComplianceInputs },
              ],
              checks: ratio.checks.filter(c => c.category === 'RN'),
              alert: 'PT RN 不計入最低人手要求（PT cap = 0）',
            },
            {
              title: 'HW Units（1 EN=2 HW units；min=2；PT cap=1 unit）',
              keys: [
                { label: 'A更 FT EN', k: 'ftEnPerAShift' as keyof ComplianceInputs },
                { label: 'A更 FT HW', k: 'ftHwPerAShift' as keyof ComplianceInputs },
                { label: 'P更 FT EN', k: 'ftEnPerPShift' as keyof ComplianceInputs },
                { label: 'P更 FT HW', k: 'ftHwPerPShift' as keyof ComplianceInputs },
                { label: '外購 HW（≤1 unit）', k: 'agencyHwPerShift' as keyof ComplianceInputs },
              ],
              checks: ratio.checks.filter(c => c.category === 'HW'),
              alert: null,
            },
            {
              title: 'RCW（A/P更 min=6；N更 min=3；A/P更 PT上限≤3）',
              keys: [
                { label: 'A更 FT RCW',  k: 'ftRcwPerAShift'      as keyof ComplianceInputs },
                { label: 'A更 外購 RCW', k: 'agencyRcwPerAShift'  as keyof ComplianceInputs },
                { label: 'P更 FT RCW',  k: 'ftRcwPerPShift'      as keyof ComplianceInputs },
                { label: 'P更 外購 RCW', k: 'agencyRcwPerPShift'  as keyof ComplianceInputs },
                { label: 'N更 FT RCW',  k: 'ftRcwPerNShift'      as keyof ComplianceInputs },
                { label: 'N更 外購 RCW', k: 'agencyRcwPerNShift'  as keyof ComplianceInputs },
              ],
              checks: ratio.checks.filter(c => c.category === 'RCW'),
              alert: null,
            },
          ].map(section => (
            <div key={section.title} className="bg-white border border-gray-200 rounded-xl p-4">
              <h3 className="text-xs font-semibold text-gray-800 mb-3">{section.title}</h3>
              {section.alert && (
                <div className="mb-3 rounded-lg bg-amber-50 border border-amber-100 px-3 py-2 text-[10px] text-amber-700">
                  ⚠️ {section.alert}
                </div>
              )}
              <div className={`grid gap-3 mb-4 ${section.keys.length <= 2 ? 'grid-cols-2' : 'grid-cols-2 sm:grid-cols-3'}`}>
                {section.keys.map(({ label, k }) => (
                  <InputField key={k} label={label} value={inputs[k]} onChange={set(k)} suffix="人" />
                ))}
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {section.checks.map(c => {
                  const isOk   = c.ok && c.ptOk
                  const isWarn = isOk && c.total === c.minReq
                  const borderCls = !isOk ? 'border-red-200 bg-red-50' : isWarn ? 'border-amber-200 bg-amber-50' : 'border-emerald-200 bg-emerald-50'
                  const textCls   = !isOk ? 'text-red-700' : isWarn ? 'text-amber-700' : 'text-emerald-700'
                  return (
                    <div key={c.label} className={`rounded-xl border p-3 ${borderCls}`}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-bold text-slate-800">{c.label}</span>
                        <span className={`text-[10px] font-bold ${textCls}`}>
                          {!isOk ? '🚨 違規' : isWarn ? '⚠️ 邊緣' : '✅ 合規'}
                        </span>
                      </div>
                      <div className="grid grid-cols-3 gap-1.5 text-center">
                        <div className="rounded-lg bg-white/70 p-1.5">
                          <p className="text-[8px] text-slate-400">合計</p>
                          <p className={`text-sm font-bold tabular-nums ${!c.ok ? 'text-red-600' : textCls}`}>{c.total}</p>
                        </div>
                        <div className="rounded-lg bg-white/70 p-1.5">
                          <p className="text-[8px] text-slate-400">最低</p>
                          <p className="text-sm font-bold text-slate-700">{c.minReq}</p>
                        </div>
                        <div className="rounded-lg bg-white/70 p-1.5">
                          <p className="text-[8px] text-slate-400">PT上限</p>
                          <p className={`text-sm font-bold tabular-nums ${!c.ptOk ? 'text-red-600' : 'text-slate-700'}`}>
                            {c.ptCap === null ? '∞' : `≤${c.ptCap}`}
                          </p>
                        </div>
                      </div>
                      <p className="text-[9px] text-slate-400 mt-1.5 text-center">{c.note}</p>
                      {!c.ok && (
                        <div className="mt-2 rounded-lg bg-red-100 px-2 py-1 text-[9px] text-red-700 font-medium text-center">
                          人數不足 — 需再加 {c.minReq - c.total}人
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── 證書管理 ── */}
      {tab === 'certs' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900">員工證書到期監察</h2>
            <span className="text-[10px] font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
              {CERTS.filter(c => c.status !== 'ok').length} 項需跟進
            </span>
          </div>
          <div className="space-y-2">
            {CERTS.sort((a, b) => a.daysLeft - b.daysLeft).map(c => {
              const cfg = statusCfg[c.status as keyof typeof statusCfg]
              return (
                <div key={c.name + c.cert}
                  className={`flex items-center justify-between p-3.5 rounded-xl border ${
                    c.status === 'over' ? 'bg-red-50 border-red-200' :
                    c.status === 'warn' ? 'bg-amber-50 border-amber-100' : 'bg-white border-gray-100'}`}>
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-gray-800">{c.name}</span>
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${ROLE_COLOR[c.role]}`}>{c.role}</span>
                      </div>
                      <div className="text-[10px] text-gray-500 mt-0.5">{c.cert} · 到期：{c.expiry}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm font-bold tabular-nums ${
                      c.status === 'over' ? 'text-red-600' : c.status === 'warn' ? 'text-amber-600' : 'text-emerald-600'}`}>
                      {c.daysLeft}天
                    </div>
                    <div className="text-[9px] text-gray-400">剩餘</div>
                  </div>
                </div>
              )
            })}
          </div>
          <div className="rounded-xl p-4 border" style={{ background: '#fce8f3', borderColor: 'rgba(232,24,122,.3)' }}>
            <p className="text-xs font-bold mb-1.5" style={{ color: PINK }}>✦ Emma AI 自動提醒（3層警示）</p>
            <div className="space-y-1">
              {[
                { days: 90, level: '🟡 提醒', action: '發送提醒至員工及院長' },
                { days: 30, level: '🟠 警告', action: '發送警告 + 上報助理院長' },
                { days: 7,  level: '🔴 緊急', action: '緊急通知 + 暫緩排入該更' },
              ].map(r => (
                <div key={r.days} className="flex items-center gap-2 text-[10px] text-gray-600">
                  <span>{r.level}</span>
                  <span className="text-gray-400">到期前{r.days}天：</span>
                  <span>{r.action}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── 外購管理 ── */}
      {tab === 'agency' && (
        <div className="space-y-5">
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="mb-4 flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">💰</div>
              <h2 className="text-base font-semibold text-slate-800">March 2026 外購費用實況</h2>
            </div>
            <div className="space-y-2.5 mb-4">
              {MARCH_AGENCY.map(a => (
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
                <p className="text-lg font-bold text-pink-600 tabular-nums">
                  {fmt(MARCH_AGENCY.reduce((s, a) => s + a.total, 0))}
                </p>
              </div>
            </div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">外購收費表（每更）</p>
            <div className="overflow-x-auto rounded-xl border border-slate-100">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    {['職位', 'A/P更', 'N更'].map(h => (
                      <th key={h} className="px-3 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {AGENCY_RATES.map(r => (
                    <tr key={r.role} className="border-b border-slate-50 hover:bg-slate-50/50">
                      <td className="px-3 py-2.5 font-semibold text-slate-700">{r.role}</td>
                      <td className="px-3 py-2.5 font-bold text-slate-800 tabular-nums">{fmt(r.ap)}</td>
                      <td className="px-3 py-2.5 font-bold text-pink-500 tabular-nums">{fmt(r.n)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-[10px] text-slate-400">
              🎄 雙倍費率節日（全年6天）：中秋節正日、冬至、農曆年前夕、初一、初二、初三
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="mb-4 flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-50 text-pink-500 text-sm">📋</div>
              <h2 className="text-base font-semibold text-slate-800">SWD 外購規定</h2>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {AGENCY_RULES.map(rule => (
                <div key={rule.title} className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3.5">
                  <span className="text-xl flex-shrink-0">{rule.icon}</span>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{rule.title}</p>
                    <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{rule.desc}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-xl px-4 py-3 text-center" style={{ background: PINK }}>
              <p className="text-sm font-semibold text-white">
                Emma AI 排更時自動計算外購配額 · 超出上限前即時警示 🛡️
              </p>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}