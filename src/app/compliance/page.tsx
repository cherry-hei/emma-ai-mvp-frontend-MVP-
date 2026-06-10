'use client'

import { useState, useMemo, useEffect } from 'react'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

interface ComplianceInputs {
  totalResidents: number
  ftRnPerAShift: number; ftRnPerPShift: number
  ftEnPerAShift: number; ftEnPerPShift: number
  ftHwPerAShift: number; ftHwPerPShift: number
  agencyHwPerShift: number
  ftRcwPerAShift: number; agencyRcwPerAShift: number
  ftRcwPerPShift: number; agencyRcwPerPShift: number
  ftRcwPerNShift: number; agencyRcwPerNShift: number
  ftRcwCount: number; ftRcwAvgWorkDays: number; ptRcwShiftsMonth: number
}

const ZH: Record<string, string> = {
  title: '合規監察',
  subtitle: 'RCHE 2026 Q1 · March',
  export: '匯出報告',
  tab_ratio: '人手比例',
  tab_certs: '員工證書',
  tab_agency: '外判規則',
  tab_audit: '審計核對',
  score_rn: 'RN 覆蓋',
  score_ratio: '人手比例',
  score_cert: '員工認證',
  score_clan: '假期/AN',
  score_rn_desc: 'P更43次 A更18次 RN不足',
  score_ratio_desc: '3更合規',
  score_cert_desc: '2人30天內到期',
  score_clan_desc: 'CL 156.5h · 22次AN缺失',
  col_role: '職位',
  col_ft: '長工',
  col_agency: '外判',
  col_total: '總數',
  col_min: '最低要求',
  col_pt: 'PT上限',
  col_status: '狀態',
  rcw_title: 'RCW PT比例 (Cap.459A s.113)',
  rcw_ft: 'FT RCW 人數',
  rcw_days: 'FT RCW 平均工作日',
  rcw_pt: 'PT RCW 更次/月',
  rcw_max_pt: '50% 上限',
  rcw_remaining: '餘額',
  rcw_exceeded: '超標',
  pt_usage: 'PT 使用率',
  suffix_person: '人',
  suffix_day: '日',
  suffix_shift: '更',
  cert_name: '員工姓名',
  cert_role: '職位',
  cert_type: '證書類型',
  cert_expiry: '到期日',
  cert_days: '剩餘天數',
  cert_status: '狀態',
  violation_title: 'March 2026 違規記錄',
  col_sev: '嚴重性',
  col_cat: '類別',
  col_issue: '問題',
  col_freq: '頻次',
  col_ref: '法規',
  col_action: '建議行動',
  sev_high: '高',
  sev_mid: '中',
  sev_low: '低',
  audit_ok: '通過',
  audit_warn: '待處理',
  audit_over: '違規',
  residents: '院友人數',
  emergency: '緊急響應',
  ot_hours: '超時工時',
  agency_shifts: '外判更數',
  completion: '完成率',
}

const EN: Record<string, string> = {
  title: 'Compliance',
  subtitle: 'RCHE 2026 Q1 · March',
  export: 'Export Report',
  tab_ratio: 'Staffing Ratio',
  tab_certs: 'Certifications',
  tab_agency: 'Agency Rules',
  tab_audit: 'Audit Checklist',
  score_rn: 'RN Cover',
  score_ratio: 'Staff Ratio',
  score_cert: 'Certification',
  score_clan: 'Leave/AN',
  score_rn_desc: 'P-shift 43x A-shift 18x RN short',
  score_ratio_desc: '3 shifts compliant',
  score_cert_desc: '2 expiring in 30 days',
  score_clan_desc: 'CL 156.5h · 22 AN missing',
  col_role: 'Role',
  col_ft: 'FT',
  col_agency: 'Agency',
  col_total: 'Total',
  col_min: 'Minimum',
  col_pt: 'PT Cap',
  col_status: 'Status',
  rcw_title: 'RCW PT Ratio (Cap.459A s.113)',
  rcw_ft: 'FT RCW Count',
  rcw_days: 'FT RCW Avg Work Days',
  rcw_pt: 'PT RCW Shifts/Month',
  rcw_max_pt: '50% Cap',
  rcw_remaining: 'Remaining',
  rcw_exceeded: 'Exceeded by',
  pt_usage: 'PT Usage',
  suffix_person: '',
  suffix_day: 'd',
  suffix_shift: 'shifts',
  cert_name: 'Staff Name',
  cert_role: 'Role',
  cert_type: 'Certificate',
  cert_expiry: 'Expiry',
  cert_days: 'Days Left',
  cert_status: 'Status',
  violation_title: 'March 2026 Violations',
  col_sev: 'Severity',
  col_cat: 'Category',
  col_issue: 'Issue',
  col_freq: 'Freq',
  col_ref: 'Reference',
  col_action: 'Action',
  sev_high: 'High',
  sev_mid: 'Mid',
  sev_low: 'Low',
  audit_ok: 'Pass',
  audit_warn: 'Pending',
  audit_over: 'Breach',
  residents: 'Residents',
  emergency: 'Emergency response',
  ot_hours: 'Overtime hours',
  agency_shifts: 'Agency shifts',
  completion: 'Completion rate',
}

const CERTS = [
  { name: 'Leung Ka Kei', role: 'EN',  type: 'First Aid',      expiry: '2026-04-15', daysLeft: 3,   status: 'over' },
  { name: 'Wong Jing Yin',role: 'PCW', type: 'BLS',            expiry: '2026-04-20', daysLeft: 8,   status: 'warn' },
  { name: 'Yu Yat Sze',   role: 'RN',  type: 'ACLS',           expiry: '2026-05-01', daysLeft: 19,  status: 'warn' },
  { name: 'Ho Kai Ching', role: 'CW',  type: 'Personal Care',  expiry: '2026-06-30', daysLeft: 79,  status: 'ok'   },
  { name: 'Wong Yat Sum', role: 'HW',  type: 'Elder Care',     expiry: '2026-08-10', daysLeft: 120, status: 'ok'   },
  { name: 'Li Shao Hung', role: 'AW',  type: 'Infection Ctrl', expiry: '2027-01-15', daysLeft: 278, status: 'ok'   },
]

const VIOLATIONS_ZH = [
  { sev: 'red',   category: 'RN P更',   issue: 'P更12天僅43人次FT RN',   freq: '12/28天', ref: 'Cap.459A s.111', action: '增加RN覆蓋/RN外判' },
  { sev: 'red',   category: 'RN A更',   issue: 'A更5天僅18人次FT RN',    freq: '5/28天',  ref: 'Cap.459A s.111', action: '排程調整' },
  { sev: 'red',   category: 'RCW P更',  issue: 'P更25次低於最低要求6人', freq: '2/28天',  ref: 'Cap.459A Sch.1', action: '增加1名外判RCW' },
  { sev: 'amber', category: 'AN假期',   issue: '2名員工連續2個月無AN',   freq: '持續',   ref: '',              action: '安排3次AN' },
  { sev: 'amber', category: 'CL假期',   issue: '15人累積CL超156.5小時', freq: '持續',   ref: 'Cap.57',        action: '清除CL積存' },
  { sev: 'yellow',category: '員工安排', issue: '6名員工連續超6天上班',   freq: '6人次',  ref: '',              action: '30天內糾正' },
]
const VIOLATIONS_EN = [
  { sev: 'red',   category: 'RN P-shift',  issue: 'P-shift 12/28 days only 43 FT RN',   freq: '12/28d', ref: 'Cap.459A s.111', action: 'Add RN / agency RN' },
  { sev: 'red',   category: 'RN A-shift',  issue: 'A-shift 5/28 days only 18 FT RN',    freq: '5/28d',  ref: 'Cap.459A s.111', action: 'Reschedule RN' },
  { sev: 'red',   category: 'RCW P-shift', issue: 'P-shift 25x below min 6 staff',      freq: '2/28d',  ref: 'Cap.459A Sch.1', action: 'Add 1 agency RCW' },
  { sev: 'amber', category: 'AN Leave',    issue: '2 staff no AN for 2 consecutive mths', freq: 'Ongoing', ref: '',            action: 'Arrange 3 AN sessions' },
  { sev: 'amber', category: 'CL Leave',    issue: '15 staff CL backlog >156.5h',        freq: 'Ongoing', ref: 'Cap.57',       action: 'Clear CL backlog' },
  { sev: 'yellow',category: 'Scheduling',  issue: '6 staff worked >6 consecutive days', freq: '6x',      ref: '',             action: 'Rectify within 30 days' },
]

const AUDIT_ITEMS_ZH = [
  { item: 'RN P更覆蓋',    status: 'over', detail: 'P更 12/28天僅43人次 FT RN', ref: 'Cap.459A s.111', freq: '12/28' },
  { item: 'RN A更覆蓋',    status: 'over', detail: 'A更 5/28天僅18人次 FT RN',  ref: 'Cap.459A s.111', freq: '5/28' },
  { item: 'RCW P更比例',    status: 'over', detail: 'P更 25次低於要求6人',       ref: 'Cap.459A Sch.1', freq: '2/28' },
  { item: 'AN假期',        status: 'warn', detail: '2名員工連續2月無AN',         ref: '',               freq: '' },
  { item: 'CL假期積存',     status: 'warn', detail: 'CL累積156.5小時',           ref: 'Cap.57',         freq: '' },
  { item: 'RCW PT比例',     status: 'ok',   detail: 'A更3人 P更3人 佔50%以內',    ref: 'Cap.459A s.113', freq: '' },
  { item: '外判人手記錄',   status: 'ok',   detail: '13人 符合SWD要求',          ref: 'Cap.459A Sch.1', freq: '' },
  { item: 'RCW 12小時上限', status: 'warn', detail: '1名RCW曾超時',             ref: '',               freq: '' },
  { item: '連續上班天數',   status: 'warn', detail: '6名員工超6天',             ref: '',               freq: '6' },
  { item: '院友入住記錄',   status: 'ok',   detail: '入住資料完整',             ref: 'SWD Guideline',  freq: '' },
]
const AUDIT_ITEMS_EN = [
  { item: 'RN P-shift Cover',  status: 'over', detail: 'P-shift 12/28 days only 43 FT RN', ref: 'Cap.459A s.111', freq: '12/28' },
  { item: 'RN A-shift Cover',  status: 'over', detail: 'A-shift 5/28 days only 18 FT RN',  ref: 'Cap.459A s.111', freq: '5/28' },
  { item: 'RCW P-shift Ratio', status: 'over', detail: 'P-shift 25x below min 6 staff',   ref: 'Cap.459A Sch.1', freq: '2/28' },
  { item: 'AN Leave',          status: 'warn', detail: '2 staff no AN for 2 months',      ref: '',               freq: '' },
  { item: 'CL Leave Backlog',  status: 'warn', detail: 'CL backlog 156.5h',               ref: 'Cap.57',         freq: '' },
  { item: 'RCW PT Ratio',      status: 'ok',   detail: 'A:3 P:3 within 50% cap',          ref: 'Cap.459A s.113', freq: '' },
  { item: 'Agency Records',    status: 'ok',   detail: '13 staff meet SWD requirements',  ref: 'Cap.459A Sch.1', freq: '' },
  { item: 'RCW 12h Limit',     status: 'warn', detail: '1 RCW exceeded hours',            ref: '',               freq: '' },
  { item: 'Consecutive Days',  status: 'warn', detail: '6 staff worked >6 days',          ref: '',               freq: '6' },
  { item: 'Resident Records',  status: 'ok',   detail: 'Admission records complete',      ref: 'SWD Guideline',  freq: '' },
]

const AGENCY_RULES_ZH = [
  { icon: '📋', title: '50%上限',   desc: 'PT外判人數不得超過FT同類職位的50%（AP更）' },
  { icon: '🕐', title: '更次要求',  desc: 'A更07:00-15:00 / P更13:30-21:30 / N更21:30-07:00' },
  { icon: '📅', title: '合約期限',  desc: '外判合約最長4個月，需提前續約' },
  { icon: '👥', title: '人數限制',  desc: '每更最多2名HW/EN外判，最多12名CW外判' },
  { icon: '🔍', title: '審計要求',  desc: '每季A更3次、P更3次外判審核記錄' },
  { icon: '⏰', title: '通知時限',  desc: '外判需提前6小時確認，緊急情況除外' },
]
const AGENCY_RULES_EN = [
  { icon: '📋', title: '50% Cap',        desc: 'PT agency staff cannot exceed 50% of FT equivalent (AP shifts)' },
  { icon: '🕐', title: 'Shift Hours',    desc: 'A 07:00-15:00 / P 13:30-21:30 / N 21:30-07:00' },
  { icon: '📅', title: 'Contract Limit', desc: 'Max 4-month agency contracts, must renew in advance' },
  { icon: '👥', title: 'Count Limit',    desc: 'Max 2 HW/EN agency per shift, max 12 CW agency per shift' },
  { icon: '🔍', title: 'Audit Record',   desc: '3 A-shift + 3 P-shift agency audit records per quarter' },
  { icon: '⏰', title: 'Notice Period',  desc: '6-hour advance notice required, except emergencies' },
]

function computeRatioCompliance(i: ComplianceInputs) {
  const calcBase    = Math.ceil(i.totalResidents / 20) * 20
  const minRCWAP    = Math.floor(calcBase / 20)
  const minRCWN     = Math.ceil(i.totalResidents / 35)
  const capRCWAP    = Math.floor(minRCWAP * 0.5)
  const minHWAP     = Math.floor(calcBase / 60)
  const capHWAP     = Math.floor(minHWAP * 0.5)
  const hwUnitsA    = i.ftEnPerAShift * 2 + i.ftHwPerAShift + i.agencyHwPerShift
  const hwUnitsP    = i.ftEnPerPShift * 2 + i.ftHwPerPShift + i.agencyHwPerShift
  const ftShifts    = i.ftRcwCount * i.ftRcwAvgWorkDays
  const maxPtShifts = Math.floor(ftShifts / 2)
  const usagePct    = ftShifts > 0 ? Math.round(i.ptRcwShiftsMonth / ftShifts * 100) : 0
  const remaining   = maxPtShifts - i.ptRcwShiftsMonth
  const ptStatus    = usagePct > 50 ? 'over' : usagePct > 40 ? 'warn' : 'ok'

  return {
    calcBase, minRCWAP, minRCWN, capRCWAP, minHWAP, capHWAP,
    hwUnitsA, hwUnitsP, ftShifts, maxPtShifts, usagePct, remaining, ptStatus,
    checks: [
      { label: 'RN A',  ft: i.ftRnPerAShift, agency: 0, total: i.ftRnPerAShift, minReq: 1, ptCap: 0,   ok: i.ftRnPerAShift >= 1 },
      { label: 'RN P',  ft: i.ftRnPerPShift, agency: 0, total: i.ftRnPerPShift, minReq: 1, ptCap: 0,   ok: i.ftRnPerPShift >= 1 },
      { label: 'HW A',  ft: i.ftHwPerAShift, agency: i.agencyHwPerShift, total: hwUnitsA, minReq: minHWAP, ptCap: capHWAP, ok: hwUnitsA >= minHWAP },
      { label: 'HW P',  ft: i.ftHwPerPShift, agency: i.agencyHwPerShift, total: hwUnitsP, minReq: minHWAP, ptCap: capHWAP, ok: hwUnitsP >= minHWAP },
      { label: 'RCW A', ft: i.ftRcwPerAShift, agency: i.agencyRcwPerAShift, total: i.ftRcwPerAShift + i.agencyRcwPerAShift, minReq: minRCWAP, ptCap: capRCWAP, ok: i.ftRcwPerAShift + i.agencyRcwPerAShift >= minRCWAP },
      { label: 'RCW P', ft: i.ftRcwPerPShift, agency: i.agencyRcwPerPShift, total: i.ftRcwPerPShift + i.agencyRcwPerPShift, minReq: minRCWAP, ptCap: capRCWAP, ok: i.ftRcwPerPShift + i.agencyRcwPerPShift >= minRCWAP },
      { label: 'RCW N', ft: i.ftRcwPerNShift, agency: i.agencyRcwPerNShift, total: i.ftRcwPerNShift + i.agencyRcwPerNShift, minReq: minRCWN,  ptCap: null,     ok: i.ftRcwPerNShift + i.agencyRcwPerNShift >= minRCWN },
    ],
  }
}

function StatusBadge({ s }: { s: string }) {
  const cls: Record<string, string> = {
    ok:   'bg-emerald-50 text-emerald-700 border-emerald-200',
    warn: 'bg-amber-50 text-amber-700 border-amber-200',
    over: 'bg-red-50 text-red-700 border-red-200',
  }
  const sym: Record<string, string> = { ok: '✓', warn: '⚠', over: '✗' }
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${cls[s]}`}>
      {sym[s]}
    </span>
  )
}

function InputField({
  label,
  value,
  onChange,
  suffix,
  hint,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  suffix?: string
  hint?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-500">
        {label}
        {hint && <span className="ml-1.5 text-[10px] text-slate-400">{hint}</span>}
      </label>
      <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 focus-within:border-pink-400 transition-all">
        <input
          type="number"
          value={value}
          onChange={e => onChange(Number(e.target.value) || 0)}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-slate-800 outline-none tabular-nums"
        />
        {suffix && <span className="text-xs text-slate-400 flex-shrink-0">{suffix}</span>}
      </div>
    </div>
  )
}

function SmallKpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-3 py-2 shadow-sm">
      <div className="text-[11px] text-gray-500 mb-1">{label}</div>
      <div className="text-sm font-semibold text-gray-900">{value}</div>
    </div>
  )
}

export default function CompliancePage() {
  const { lang } = useLang()
  const dict = lang === 'zh' ? ZH : EN
  const t = (k: string) => dict[k] ?? k

  const VIOLATIONS  = lang === 'zh' ? VIOLATIONS_ZH  : VIOLATIONS_EN
  const AUDIT_ITEMS = lang === 'zh' ? AUDIT_ITEMS_ZH : AUDIT_ITEMS_EN
  const agencyRules = lang === 'zh' ? AGENCY_RULES_ZH : AGENCY_RULES_EN

  const [tab, setTab] = useState<'ratio' | 'certs' | 'agency' | 'audit'>('ratio')

  const [inputs, setInputs] = useState<ComplianceInputs>({
    totalResidents: 105,
    ftRnPerAShift: 1, ftRnPerPShift: 1,
    ftEnPerAShift: 1, ftEnPerPShift: 1,
    ftHwPerAShift: 4, ftHwPerPShift: 3,
    agencyHwPerShift: 0,
    ftRcwPerAShift: 7, agencyRcwPerAShift: 2,
    ftRcwPerPShift: 4, agencyRcwPerPShift: 2,
    ftRcwPerNShift: 3, agencyRcwPerNShift: 1,
    ftRcwCount: 19, ftRcwAvgWorkDays: 16, ptRcwShiftsMonth: 111,
  })

  // 從 roster 讀取「實際住客數」
  useEffect(() => {
    if (typeof window === 'undefined') return
    const stored = window.localStorage.getItem('emma-total-residents')
    if (!stored) return
    const value = Number(stored)
    if (Number.isNaN(value) || value <= 0) return
    setInputs(prev => ({ ...prev, totalResidents: value }))
  }, [])

  const set = (key: keyof ComplianceInputs, v: number) =>
    setInputs(p => ({ ...p, [key]: v }))

  const r = useMemo(() => computeRatioCompliance(inputs), [inputs])

  const okCount   = AUDIT_ITEMS.filter(a => a.status === 'ok').length
  const warnCount = AUDIT_ITEMS.filter(a => a.status === 'warn').length
  const overCount = AUDIT_ITEMS.filter(a => a.status === 'over').length

  // 四個主分數卡
  const SCORES = [
    { label: t('score_rn'),    score: 68, desc: t('score_rn_desc') },
    { label: t('score_ratio'), score: 88, desc: t('score_ratio_desc') },
    { label: t('score_cert'),  score: 85, desc: t('score_cert_desc') },
    { label: t('score_clan'),  score: 55, desc: t('score_clan_desc') },
  ]

  const TABS: { id: typeof tab; label: string }[] = [
    { id: 'ratio',  label: t('tab_ratio') },
    { id: 'certs',  label: t('tab_certs') },
    { id: 'agency', label: t('tab_agency') },
    { id: 'audit',  label: t('tab_audit') },
  ]

  // 從 roster 帶過來嘅 4 個 KPI（暫時寫死，可改成 props）
  const emergencyResponse = 95
  const otHours = 16
  const agencyShifts = 12
  const completionRate = 94

  return (
    <div className="p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{t('title')}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{t('subtitle')} · Cap.459A</p>
        </div>
        <button
          className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
          style={{ background: PINK }}
        >
          {t('export')}
        </button>
      </div>

      {/* 四個主分數卡 */}
      <div className="grid grid-cols-4 gap-3">
        {SCORES.map(s => (
          <div
            key={s.label}
            className="bg-white border border-gray-200 rounded-xl p-4"
          >
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">
              {s.label}
            </div>
            <div
              className="text-[28px] font-bold"
              style={{
                color:
                  s.score >= 90 ? '#10B981' : s.score >= 75 ? '#F59E0B' : PINK,
              }}
            >
              {s.score}
            </div>
            <div className="w-full h-1.5 bg-gray-100 rounded-full mt-2 overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${s.score}%`,
                  background:
                    s.score >= 90 ? '#10B981' : s.score >= 75 ? '#F59E0B' : PINK,
                }}
              />
            </div>
            <div className="text-[10px] text-gray-400 mt-1">{s.desc}</div>
          </div>
        ))}
      </div>

      {/* 新增一行：緊急響應 / 超時工時 / 外判更數 / 完成率 */}
      <section>
        <div className="grid grid-cols-4 gap-3">
          <SmallKpiCard
            label={t('emergency')}
            value={`${emergencyResponse}%`}
          />
          <SmallKpiCard
            label={t('ot_hours')}
            value={`${otHours}h`}
          />
          <SmallKpiCard
            label={t('agency_shifts')}
            value={`${agencyShifts}`}
          />
          <SmallKpiCard
            label={t('completion')}
            value={`${completionRate}%`}
          />
        </div>
      </section>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map(t2 => (
          <button
            key={t2.id}
            onClick={() => setTab(t2.id)}
            className="px-4 py-2 text-xs font-semibold border-b-2 transition-all"
            style={{
              borderBottomColor: tab === t2.id ? PINK : 'transparent',
              color: tab === t2.id ? PINK : '#6b7280',
            }}
          >
            {t2.label}
          </button>
        ))}
      </div>

      {/* TAB: Ratio */}
      {tab === 'ratio' && (
        <div className="space-y-4">
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <div className="text-xs font-semibold text-gray-700 mb-3">
              {t('residents')}: {inputs.totalResidents}
            </div>
            <div className="overflow-x-auto rounded-xl border border-gray-100">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    {[
                      t('col_role'),
                      t('col_ft'),
                      t('col_agency'),
                      t('col_total'),
                      t('col_min'),
                      t('col_pt'),
                      t('col_status'),
                    ].map(h => (
                      <th
                        key={h}
                        className="px-3 py-2.5 text-[10px] font-semibold text-gray-500 uppercase tracking-wide text-left"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.checks.map(c => (
                    <tr
                      key={c.label}
                      className="border-b border-gray-50 hover:bg-gray-50/50"
                    >
                      <td className="px-3 py-2.5 font-semibold text-gray-700">
                        {c.label}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600">{c.ft}</td>
                      <td className="px-3 py-2.5 text-gray-600">{c.agency}</td>
                      <td className="px-3 py-2.5 font-bold text-gray-800">
                        {c.total}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600">
                        {c.minReq}
                      </td>
                      <td className="px-3 py-2.5 text-gray-500">
                        {c.ptCap ?? '—'}
                      </td>
                      <td className="px-3 py-2.5">
                        <StatusBadge s={c.ok ? 'ok' : 'over'} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* RCW PT ratio */}
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">
              {t('rcw_title')}
            </h2>
            <div className="grid grid-cols-2 gap-3 mb-4 sm:grid-cols-4">
              <InputField
                label={t('rcw_ft')}
                value={inputs.ftRcwCount}
                onChange={v => set('ftRcwCount', v)}
                suffix={t('suffix_person')}
                hint="March:19"
              />
              <InputField
                label={t('rcw_days')}
                value={inputs.ftRcwAvgWorkDays}
                onChange={v => set('ftRcwAvgWorkDays', v)}
                suffix={t('suffix_day')}
                hint="avg:16"
              />
              <InputField
                label={t('rcw_pt')}
                value={inputs.ptRcwShiftsMonth}
                onChange={v => set('ptRcwShiftsMonth', v)}
                suffix={t('suffix_shift')}
                hint="March:111"
              />
              <div className="flex flex-col justify-center p-3 rounded-xl bg-gray-50 border border-gray-100">
                <div className="text-[10px] text-gray-500 mb-1">
                  {t('rcw_max_pt')}
                </div>
                <div className="text-lg font-bold text-gray-800">
                  {r.maxPtShifts}
                </div>
                <div className="text-[10px] text-gray-400">
                  {r.ftShifts} × 50%
                </div>
              </div>
            </div>
            <div className="mb-1 flex justify-between text-xs text-slate-500">
              <span>{t('pt_usage')}</span>
              <span
                className={`font-bold tabular-nums ${
                  r.ptStatus === 'over'
                    ? 'text-red-600'
                    : r.ptStatus === 'warn'
                    ? 'text-amber-600'
                    : 'text-emerald-600'
                }`}
              >
                {r.usagePct}% / 50%
              </span>
            </div>
            <div className="relative h-3 w-full rounded-full bg-gray-100 overflow-hidden mb-1">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${Math.min((r.usagePct / 50) * 100, 100)}%`,
                  background:
                    r.ptStatus === 'over'
                      ? '#ef4444'
                      : r.ptStatus === 'warn'
                      ? '#f97316'
                      : '#10b981',
                }}
              />
            </div>
            <div
              className={`text-xs font-semibold mt-2 text-center rounded-lg py-1 ${
                r.remaining >= 0
                  ? 'bg-emerald-50 text-emerald-700'
                  : 'bg-red-100 text-red-700'
              }`}
            >
              {r.remaining >= 0
                ? `${t('rcw_remaining')}: ${r.remaining} ${t('suffix_shift')}`
                : `${t('rcw_exceeded')} ${Math.abs(
                    r.remaining
                  )} ${t('suffix_shift')}`}
            </div>
          </div>
        </div>
      )}

      {/* TAB: Certs */}
      {tab === 'certs' && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="overflow-x-auto rounded-xl border border-gray-100">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  {[
                    t('cert_name'),
                    t('cert_role'),
                    t('cert_type'),
                    t('cert_expiry'),
                    t('cert_days'),
                    t('cert_status'),
                  ].map(h => (
                    <th
                      key={h}
                      className="px-3 py-2.5 text-[10px] font-semibold text-gray-500 uppercase tracking-wide text-left"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {CERTS.map(c => (
                  <tr
                    key={c.name}
                    className="border-b border-gray-50 hover:bg-gray-50/50"
                  >
                    <td className="px-3 py-2.5 font-semibold text-gray-800">
                      {c.name}
                    </td>
                    <td className="px-3 py-2.5 text-gray-600">{c.role}</td>
                    <td className="px-3 py-2.5 text-gray-600">{c.type}</td>
                    <td className="px-3 py-2.5 text-gray-600">
                      {c.expiry}
                    </td>
                    <td
                      className="px-3 py-2.5 font-bold tabular-nums"
                      style={{
                        color:
                          c.daysLeft <= 7
                            ? '#ef4444'
                            : c.daysLeft <= 30
                            ? '#f59e0b'
                            : '#10b981',
                      }}
                    >
                      {c.daysLeft}
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge s={c.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB: Agency */}
      {tab === 'agency' && (
        <div className="space-y-4">
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {agencyRules.map(rule => (
                <div
                  key={rule.title}
                  className="rounded-xl border border-gray-100 bg-gray-50 p-4 flex gap-3"
                >
                  <span className="text-xl flex-shrink-0">{rule.icon}</span>
                  <div>
                    <div className="text-xs font-semibold text-gray-800 mb-1">
                      {rule.title}
                    </div>
                    <div className="text-[11px] text-gray-500 leading-relaxed">
                      {rule.desc}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-3">
              {t('violation_title')}
            </h2>
            <div className="overflow-x-auto rounded-xl border border-gray-100">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    {[
                      t('col_sev'),
                      t('col_cat'),
                      t('col_issue'),
                      t('col_freq'),
                      t('col_ref'),
                      t('col_action'),
                    ].map(h => (
                      <th
                        key={h}
                        className="px-3 py-2.5 text-[10px] font-semibold text-gray-500 uppercase tracking-wide text-left"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {VIOLATIONS.map((v, i) => (
                    <tr
                      key={i}
                      className="border-b border-gray-50 hover:bg-gray-50/50"
                    >
                      <td className="px-3 py-2.5">
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            v.sev === 'red'
                              ? 'bg-red-100 text-red-700'
                              : v.sev === 'amber'
                              ? 'bg-amber-100 text-amber-700'
                              : 'bg-yellow-100 text-yellow-700'
                          }`}
                        >
                          {v.sev === 'red'
                            ? t('sev_high')
                            : v.sev === 'amber'
                            ? t('sev_mid')
                            : t('sev_low')}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-semibold text-gray-800">
                        {v.category}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600">
                        {v.issue}
                      </td>
                      <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">
                        {v.freq}
                      </td>
                      <td className="px-3 py-2.5 text-[10px] text-gray-400 whitespace-nowrap">
                        {v.ref}
                      </td>
                      <td className="px-3 py-2.5 text-[10px] text-gray-600">
                        {v.action}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB: Audit */}
      {tab === 'audit' && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            {[
              {
                label: t('audit_ok'),
                count: okCount,
                color: '#10b981',
                bg: 'bg-emerald-50 border-emerald-200',
              },
              {
                label: t('audit_warn'),
                count: warnCount,
                color: '#f59e0b',
                bg: 'bg-amber-50 border-amber-200',
              },
              {
                label: t('audit_over'),
                count: overCount,
                color: '#ef4444',
                bg: 'bg-red-50 border-red-200',
              },
            ].map(s => (
              <div
                key={s.label}
                className={`rounded-xl border p-4 text-center ${s.bg}`}
              >
                <div
                  className="text-2xl font-bold tabular-nums"
                  style={{ color: s.color }}
                >
                  {s.count}
                </div>
                <div
                  className="text-[11px] font-semibold mt-1"
                  style={{ color: s.color }}
                >
                  {s.label}
                </div>
              </div>
            ))}
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <div className="overflow-x-auto rounded-xl border border-gray-100">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    {[
                      t('col_cat'),
                      t('col_issue'),
                      t('col_ref'),
                      t('col_freq'),
                      t('col_status'),
                    ].map(h => (
                      <th
                        key={h}
                        className="px-3 py-2.5 text-[10px] font-semibold text-gray-500 uppercase tracking-wide text-left"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {AUDIT_ITEMS.map((a, i) => (
                    <tr
                      key={i}
                      className="border-b border-gray-50 hover:bg-gray-50/50"
                    >
                      <td className="px-3 py-2.5 font-semibold text-gray-800">
                        {a.item}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600">
                        {a.detail}
                      </td>
                      <td className="px-3 py-2.5 text-[10px] text-gray-400 whitespace-nowrap">
                        {a.ref}
                      </td>
                      <td className="px-3 py-2.5 text-gray-500">{a.freq}</td>
                      <td className="px-3 py-2.5">
                        <StatusBadge s={a.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}