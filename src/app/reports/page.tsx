'use client'

import { useState } from 'react'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

const T = {
  zh: {
    pageTitle: '自動報告引擎',
    pageSubtitle: '定時觸發 · 事件觸發 · 閾值觸發 · Emma AI · March 2026',
    violationsLabel: (n: number) => `🔴 ${n} 項違規觸發中`,
    warningsLabel: (n: number) => `⚠️ ${n} 項警告`,
    kpi: ['定時報告', '事件觸發', '閾值違規', '監控警告'],
    tabs: ['🕐 定時報告', '⚡ 事件觸發', '🎯 閾值監控', '📚 法規同步'],
    tabKeys: ['scheduled', 'event', 'threshold', 'laws'],
    scheduledDesc: '以下報告由 Emma AI 自動生成並發送至指定收件人，院長可隨時手動觸發。',
    eventDesc: '以下報告/動作在特定事件發生時自動觸發，確保院舍在法定時限內完成通報。',
    thresholdDesc: '系統持續監控以下指標，達到閾值時自動觸發警示或阻截動作。',
    lawsDesc: 'Emma AI 每月自動檢查以下法規文件是否有更新，有變更時自動通知院長並更新合規引擎。',
    generateBtn: '⬇ 立即生成',
    generatingBtn: '⏳ 生成中...',
    recipientsLabel: '收件人：',
    reportContents: '報告包含內容',
    lastGenerated: '上次生成：',
    nextScheduled: '下次預定：',
    regulationLabel: '法規：',
    slaLabel: 'SLA：',
    autoActionLabel: '自動動作',
    conditionLabel: '條件：',
    keyClause: '關鍵條款：',
    synced: '已同步',
    lastUpdated: '最後更新：',
    autoSyncTitle: '⚙️ 自動同步設定',
    syncSettings: [
      { label: '同步頻率', value: '每月第一個工作天', icon: '🔄' },
      { label: '變更偵測', value: '自動對比文件版本', icon: '🔍' },
      { label: '更新通知', value: '即時通知院長/助理院長', icon: '🔔' },
      { label: '引擎更新', value: '人手比率/表格範本自動更新', icon: '⚡' },
      { label: '版本記錄', value: '保留所有歷史版本比對', icon: '📁' },
    ],
    footerNote: 'Emma AI 自動追蹤 SWD 法規更新 · 有變更即時通知 + 自動更新合規引擎 ⚡',
    severity: { ok: '✅ 正常', warn: '⚠️ 警告', over: '🔴 違規' },
    daysPrefix: (d: number) => `${d}天前：`,
  },
  en: {
    pageTitle: 'Automated Report Engine',
    pageSubtitle: 'Scheduled · Event-triggered · Threshold-triggered · Emma AI · March 2026',
    violationsLabel: (n: number) => `🔴 ${n} Active Violation${n > 1 ? 's' : ''}`,
    warningsLabel: (n: number) => `⚠️ ${n} Warning${n > 1 ? 's' : ''}`,
    kpi: ['Scheduled', 'Event Triggers', 'Violations', 'Warnings'],
    tabs: ['🕐 Scheduled', '⚡ Event Triggers', '🎯 Threshold Monitor', '📚 Regulatory Sync'],
    tabKeys: ['scheduled', 'event', 'threshold', 'laws'],
    scheduledDesc: 'The following reports are automatically generated and sent by Emma AI to designated recipients. The Home Manager may manually trigger any report at any time.',
    eventDesc: 'The following reports/actions are automatically triggered when specific events occur, ensuring the home meets statutory reporting deadlines.',
    thresholdDesc: 'The system continuously monitors the following indicators and automatically triggers alerts or blocking actions when thresholds are reached.',
    lawsDesc: 'Emma AI automatically checks the following regulatory documents for updates every month. If changes are detected, the Home Manager is notified immediately and the compliance engine is updated.',
    generateBtn: '⬇ Generate Now',
    generatingBtn: '⏳ Generating...',
    recipientsLabel: 'Recipients: ',
    reportContents: 'Report Contents',
    lastGenerated: 'Last generated: ',
    nextScheduled: 'Next scheduled: ',
    regulationLabel: 'Regulation: ',
    slaLabel: 'SLA: ',
    autoActionLabel: 'Automated Action',
    conditionLabel: 'Condition: ',
    keyClause: 'Key clause: ',
    synced: 'Synced',
    lastUpdated: 'Last updated: ',
    autoSyncTitle: '⚙️ Auto-sync Settings',
    syncSettings: [
      { label: 'Sync Frequency', value: 'First working day of every month', icon: '🔄' },
      { label: 'Change Detection', value: 'Auto document version comparison', icon: '🔍' },
      { label: 'Update Alerts', value: 'Instant notification to Home Manager / Asst. Manager', icon: '🔔' },
      { label: 'Engine Updates', value: 'Staffing ratios & form templates auto-updated', icon: '⚡' },
      { label: 'Version History', value: 'All historical versions retained for comparison', icon: '📁' },
    ],
    footerNote: 'Emma AI auto-tracks SWD regulatory updates · Instant notification + compliance engine auto-update on change ⚡',
    severity: { ok: '✅ Normal', warn: '⚠️ Warning', over: '🔴 Violation' },
    daysPrefix: (d: number) => `${d} days: `,
  },
}

const SCHEDULED_REPORTS = [
  {
    name: { zh: '月度人手合規報告', en: 'Monthly Staffing Compliance Report' },
    cron: { zh: '每月1日 08:00', en: '1st of every month, 08:00' },
    icon: '📊',
    recipients: { zh: ['院長', '助理院長'], en: ['Home Manager', 'Assistant Home Manager'] },
    lastRun: '2026-04-01',
    nextRun: '2026-05-01',
    content: {
      zh: [
        '各更次 FT/PT 實際人數 vs Cap.459A 最低要求',
        'PT比例統計（特定鐘點A/P更；N更另列無上限）',
        'AN超限員工名單（每月>2次AN更）',
        'CL積壓時數及財務負債估算',
        'SL/DSL日數及外購替更成本',
        '下月預測：節假日外購雙倍費率預警',
      ],
      en: [
        'Actual FT/PT headcount per shift vs. Cap.459A minimum requirements',
        'PT ratio statistics (specific-hour A/P shifts; N shift listed separately — no cap)',
        'Staff with >2 AN shifts per month (AN over-limit list)',
        'CL accrued hours & estimated financial liability',
        'SL/DSL days & agency replacement cost',
        'Next month forecast: public holiday double-rate agency cost alert',
      ],
    },
    law: 'Cap.459A s.11(1)(3)',
  },
  {
    name: { zh: '季度服務質素報告（SQS）', en: 'Quarterly Service Quality Report (SQS)' },
    cron: { zh: '每季首日 08:00', en: 'First day of every quarter, 08:00' },
    icon: '📋',
    recipients: { zh: ['院長', '助理院長', 'SWD'], en: ['Home Manager', 'Assistant Home Manager', 'SWD'] },
    lastRun: '2026-04-01',
    nextRun: '2026-07-01',
    content: {
      zh: ['服務使用者人數統計', '員工訓練完成率（SQS 5.3/5.4）', '投訴處理記錄（SQS 15）', '意外事故趨勢分析', '合規自評（16項SQS逐項）'],
      en: ['Service user headcount statistics', 'Staff training completion rate (SQS 5.3/5.4)', 'Complaint handling records (SQS 15)', 'Incident trend analysis', 'Self-assessment compliance (all 16 SQS items)'],
    },
    law: 'SQS 3.2',
  },
  {
    name: { zh: '年度牌照申報', en: 'Annual Licence Declaration' },
    cron: { zh: '每年1月1日 08:00', en: '1 January every year, 08:00' },
    icon: '🏛️',
    recipients: { zh: ['院長', '牌照處'], en: ['Home Manager', 'Licensing Office'] },
    lastRun: '2026-01-01',
    nextRun: '2027-01-01',
    content: {
      zh: ['安老院員工名單（附件3.2格式）', '年度營辦人申報表（附件3.8）', '持續進修記錄（主管/保健員；Cap.459A s.10.10/11.10）'],
      en: ['RCH staff list (Annex 3.2 format)', 'Annual operator declaration form (Annex 3.8)', 'Continuing education records (Supervisors/Health Workers; Cap.459A s.10.10/11.10)'],
    },
    law: 'Cap.459A s.9.6',
  },
]

const EVENT_TRIGGERS = [
  {
    trigger: 'STAFF_JOIN_LEAVE', icon: '👤',
    label:      { zh: '員工入職/離職', en: 'Staff Joining / Leaving' },
    action:     { zh: '自動更新SWD員工名單 + 通知牌照處', en: 'Auto-update SWD staff list + notify Licensing Office' },
    sla:        { zh: '1個工作天內', en: 'Within 1 working day' },
    law: 'Cap.459A s.9.6', status: 'active', recentCount: 2,
    recentNote: { zh: '本月2次觸發', en: '2 triggers this month' },
  },
  {
    trigger: 'INCIDENT_REPORTED', icon: '🚨',
    label:      { zh: '特別事故登記', en: 'Notifiable Incident' },
    action:     { zh: '生成附件8.3預填草稿 + 提醒24h通報時限', en: 'Generate pre-filled Annex 8.3 draft + remind 24h reporting deadline' },
    sla:        { zh: '即時', en: 'Immediate' },
    law: 'Cap.459A s.8.3', status: 'active', recentCount: 0,
    recentNote: { zh: '本月零事故 ✓', en: 'Zero incidents this month ✓' },
  },
  {
    trigger: 'INFECTION_OUTBREAK', icon: '🦠',
    label:      { zh: '感染控制事件', en: 'Infection Control Event' },
    action:     { zh: '啟動感染控制流程 + 生成附件13.2呈報表 + 通知相關員工', en: 'Activate infection control protocol + generate Annex 13.2 form + alert relevant staff' },
    sla:        { zh: '即時', en: 'Immediate' },
    law: 'Cap.459A s.13 / Cap.599', status: 'active', recentCount: 0,
    recentNote: { zh: '本月無感染事件 ✓', en: 'No infection events this month ✓' },
  },
  {
    trigger: 'RESIDENT_ADMISSION', icon: '🛏️',
    label:      { zh: '住客入住', en: 'Resident Admission' },
    action:     { zh: '建立個人照顧計劃提醒 + 6個月後自動提示更新', en: 'Create individual care plan reminder + auto-prompt review after 6 months' },
    sla:        { zh: '入住當日', en: 'Day of admission' },
    law: 'Cap.459A s.12', status: 'active', recentCount: 3,
    recentNote: { zh: '本月3名新住客', en: '3 new residents this month' },
  },
]

const THRESHOLD_TRIGGERS = [
  {
    name: { zh: '執照到期警示', en: 'Licence Expiry Alert' }, icon: '📜',
    condition: { zh: '執照到期 ≤ 90天', en: 'Licence expiry ≤ 90 days' },
    severity: 'warn', currentCount: 3,
    currentNote: { zh: '3人需跟進（Leung 3天、Wong 8天、Yu 19天）', en: '3 staff require follow-up (Leung: 3 days, Wong: 8 days, Yu: 19 days)' },
    levels: [
      { days: 90, label: { zh: '🟡 提醒', en: '🟡 Reminder' }, action: { zh: '發送提醒至員工及院長', en: 'Send reminder to staff and Home Manager' } },
      { days: 30, label: { zh: '🟠 警告', en: '🟠 Warning' },  action: { zh: '發送警告 + 上報助理院長', en: 'Send warning + escalate to Assistant Home Manager' } },
      { days: 7,  label: { zh: '🔴 緊急', en: '🔴 Urgent' },   action: { zh: '緊急通知 + 暫緩排入該更', en: 'Emergency alert + suspend assignment to that shift' } },
    ],
    law: 'SWD Registration',
  },
  {
    name: { zh: 'PT比例超標攔截', en: 'PT Ratio Overage Block' }, icon: '🛡️',
    condition: { zh: '特定鐘點PT人數 > floor(最低×50%)', en: 'Specific-hour PT headcount > floor(minimum × 50%)' },
    severity: 'over', currentCount: 0,
    currentNote: { zh: '本月未觸發 — A/P更均在上限內', en: 'No triggers this month — A/P shifts within limit' },
    levels: [
      { label: { zh: '🔴 即時阻截', en: '🔴 Immediate Block' }, action: { zh: '阻止排班確認 + 顯示Cap.459A s.11(3)說明 + 建議SWD 686申請', en: 'Block roster confirmation + display Cap.459A s.11(3) explanation + suggest SWD 686 application' } },
    ],
    law: 'Cap.459A s.11(3)',
  },
  {
    name: { zh: 'AN更超限阻截', en: 'AN Shift Over-limit Block' }, icon: '🌙',
    condition: { zh: '每人每月AN更數 > 2次', en: 'AN shifts per staff per month > 2' },
    severity: 'over', currentCount: 22,
    currentNote: { zh: '⚠️ 3月22名員工超出2次AN更', en: '⚠️ 22 staff exceeded 2 AN shifts in March' },
    levels: [
      { label: { zh: '🔴 阻截第3次', en: '🔴 Block 3rd AN' }, action: { zh: '阻止加入第3次AN更 + 記錄至合規日誌', en: 'Block adding a 3rd AN shift + log to compliance journal' } },
    ],
    law: { zh: '院舍內部規定', en: 'Internal Home Policy' },
  },
  {
    name: { zh: 'RN空更緊急通知', en: 'RN-Absent Shift Emergency Alert' }, icon: '🏥',
    condition: { zh: 'FT RN = 0 於任何更次', en: 'FT RN = 0 in any shift' },
    severity: 'over', currentCount: 17,
    currentNote: { zh: '⚠️ 3月17天（P更12天+A更5天）無RN', en: '⚠️ 17 days in March without RN (P shift: 12 days, A shift: 5 days)' },
    levels: [
      { label: { zh: '🔴 即時警告', en: '🔴 Immediate Alert' }, action: { zh: '即時警告院長 + 自動啟動後備RN聯絡流程', en: 'Instant notification to Home Manager + auto-initiate standby RN contact process' } },
    ],
    law: 'Cap.459A s.11(1)',
  },
  {
    name: { zh: 'CL積壓超限提醒', en: 'CL Accrual Over-limit Reminder' }, icon: '⏰',
    condition: { zh: '每人CL積壓 > 20h', en: 'CL accrual per staff > 20h' },
    severity: 'warn', currentCount: 156,
    currentNote: { zh: '全院積壓156.5h — 財務負債持續增加', en: 'Total home accrual: 156.5h — financial liability continues to grow' },
    levels: [
      { label: { zh: '🟠 警告', en: '🟠 Warning' }, action: { zh: '列入下月更表優先補休 + 財務負債月報更新', en: "Prioritise compensatory rest in next month's roster + update financial liability monthly report" } },
    ],
    law: { zh: '僱傭條例 Cap.57', en: 'Employment Ordinance Cap.57' },
  },
  {
    name: { zh: '入住率低於90%提醒', en: 'Occupancy Below 90% Reminder' }, icon: '🏠',
    condition: { zh: '入住率 < 90%', en: 'Occupancy rate < 90%' },
    severity: 'ok', currentCount: 0,
    currentNote: { zh: '現時入住率 100% (105/105) ✓', en: 'Current occupancy: 100% (105/105) ✓' },
    levels: [
      { label: { zh: '🟡 提醒', en: '🟡 Reminder' }, action: { zh: '提示入住率影響政府撥款計算', en: 'Alert that occupancy rate affects government subvention calculation' } },
    ],
    law: { zh: 'LSG撥款規定', en: 'LSG Subvention Rules' },
  },
]

const REGULATORY_DOCS = [
  { id: 'CAP459A',  name: { zh: '《安老院規例》Cap.459A', en: 'Residential Care Homes (Elderly Persons) Regulation Cap.459A' }, lastSync: '2024-06-16', key: { zh: 's.11(3) PT人數上限', en: 's.11(3) PT headcount cap' } },
  { id: 'COP_2024', name: { zh: '《安老院實務守則》2024年6月修訂版', en: 'Code of Practice for RCH(E) — June 2024 Revision' }, lastSync: '2025-04-01', key: { zh: '第9章 外購服務', en: 'Chapter 9: Agency Services' } },
  { id: 'SQS_16',   name: { zh: '社署16項服務質素標準', en: 'SWD 16 Service Quality Standards' }, lastSync: '2026-04-01', key: { zh: 'SQS 8 法律合規', en: 'SQS 8: Legal Compliance' } },
  { id: 'LSG_TIPS', name: { zh: 'LSG SmartTips 2026年4月版', en: 'LSG SmartTips April 2026 Edition' }, lastSync: '2026-04-01', key: { zh: '認可/不認可項目', en: 'Recognised / Non-recognised Items' } },
]

function SeverityBadge({ s, lang }: { s: string; lang: 'zh' | 'en' }) {
  const cfg: Record<string, string> = {
    ok:   'bg-emerald-50 text-emerald-700 border-emerald-200',
    warn: 'bg-amber-50 text-amber-700 border-amber-200',
    over: 'bg-red-50 text-red-700 border-red-200',
  }
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${cfg[s]}`}>
      {T[lang].severity[s as 'ok' | 'warn' | 'over']}
    </span>
  )
}

export default function ReportsPage() {
  // ✅ 用全局 useLang()，唔需要本地 lang state
  const { lang } = useLang()
  const [tab, setTab] = useState<'scheduled' | 'event' | 'threshold' | 'laws'>('scheduled')
  const [generating, setGenerating] = useState<string | null>(null)

  const t = T[lang]

  const handleGenerate = (name: string) => {
    setGenerating(name)
    setTimeout(() => setGenerating(null), 2000)
  }

  const activeViolations = THRESHOLD_TRIGGERS.filter(x => x.severity === 'over' && x.currentCount > 0).length
  const activeWarnings   = THRESHOLD_TRIGGERS.filter(x => x.severity === 'warn' && x.currentCount > 0).length

  return (
    <div className="p-5 space-y-5">

      {/* Header — 無切換掣，由右上全局掣控制 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{t.pageTitle}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{t.pageSubtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          {activeViolations > 0 && (
            <span className="text-xs font-bold px-2.5 py-1 rounded-full border bg-red-50 text-red-700 border-red-200">
              {t.violationsLabel(activeViolations)}
            </span>
          )}
          {activeWarnings > 0 && (
            <span className="text-xs font-bold px-2.5 py-1 rounded-full border bg-amber-50 text-amber-700 border-amber-200">
              {t.warningsLabel(activeWarnings)}
            </span>
          )}
        </div>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: t.kpi[0], value: SCHEDULED_REPORTS.length, color: 'text-blue-600',    bg: 'bg-blue-50 border-blue-200'       },
          { label: t.kpi[1], value: EVENT_TRIGGERS.length,    color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' },
          { label: t.kpi[2], value: activeViolations,         color: 'text-red-600',     bg: 'bg-red-50 border-red-200'         },
          { label: t.kpi[3], value: activeWarnings,           color: 'text-amber-600',   bg: 'bg-amber-50 border-amber-200'     },
        ].map(k => (
          <div key={k.label} className={`rounded-xl border p-4 text-center ${k.bg}`}>
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{k.label}</div>
            <div className={`text-2xl font-bold ${k.color}`}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {t.tabs.map((label, i) => (
          <button key={t.tabKeys[i]} onClick={() => setTab(t.tabKeys[i] as typeof tab)}
            className="px-4 py-2 text-xs font-semibold border-b-2 transition-all"
            style={{
              borderBottomColor: tab === t.tabKeys[i] ? PINK : 'transparent',
              color: tab === t.tabKeys[i] ? PINK : '#6b7280',
            }}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Scheduled / 定時報告 ── */}
      {tab === 'scheduled' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">{t.scheduledDesc}</p>
          {SCHEDULED_REPORTS.map(r => (
            <div key={r.name.zh} className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-pink-50 text-2xl">{r.icon}</div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-800">{r.name[lang]}</h3>
                    <p className="text-[11px] text-slate-400 mt-0.5">⏰ {r.cron[lang]} · {t.regulationLabel}{r.law}</p>
                  </div>
                </div>
                <button
                  onClick={() => handleGenerate(r.name.zh)}
                  disabled={generating === r.name.zh}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white rounded-lg transition-all disabled:opacity-50"
                  style={{ background: PINK }}>
                  {generating === r.name.zh ? t.generatingBtn : t.generateBtn}
                </button>
              </div>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-[10px] text-slate-400">{t.recipientsLabel}</span>
                {r.recipients[lang].map(re => (
                  <span key={re} className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{re}</span>
                ))}
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-2">{t.reportContents}</p>
                <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                  {r.content[lang].map((c, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-[11px] text-slate-600">
                      <span className="text-emerald-500 mt-0.5 flex-shrink-0">✓</span>
                      <span>{c}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex gap-4 mt-3">
                <div className="text-[10px] text-slate-400">{t.lastGenerated}<span className="font-semibold text-slate-600">{r.lastRun}</span></div>
                <div className="text-[10px] text-slate-400">{t.nextScheduled}<span className="font-semibold text-slate-600">{r.nextRun}</span></div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Event / 事件觸發 ── */}
      {tab === 'event' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">{t.eventDesc}</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {EVENT_TRIGGERS.map(e => (
              <div key={e.trigger} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-start gap-3 mb-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-pink-50 text-xl flex-shrink-0">{e.icon}</div>
                  <div className="flex-1">
                    <h3 className="text-sm font-bold text-slate-800">{e.label[lang]}</h3>
                    <p className="text-[10px] text-slate-400 mt-0.5">{t.regulationLabel}{e.law}</p>
                  </div>
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-1 ${e.status === 'active' ? 'bg-emerald-500 animate-pulse' : 'bg-gray-300'}`} />
                </div>
                <div className="rounded-xl bg-slate-50 border border-slate-100 p-3 mb-3">
                  <p className="text-[10px] font-semibold text-slate-500 mb-1">{t.autoActionLabel}</p>
                  <p className="text-[11px] text-slate-700 leading-relaxed">{e.action[lang]}</p>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-slate-400">{t.slaLabel}</span>
                    <span className="text-[10px] font-bold text-slate-600">{e.sla[lang]}</span>
                  </div>
                  <span className={`text-[10px] font-semibold ${e.recentCount > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>
                    {e.recentNote[lang]}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Threshold / 閾值監控 ── */}
      {tab === 'threshold' && (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">{t.thresholdDesc}</p>
          {THRESHOLD_TRIGGERS.map(tr => {
            const borderCls = tr.severity === 'over' ? 'border-red-200' : tr.severity === 'warn' ? 'border-amber-200' : 'border-emerald-200'
            const bgCls     = tr.severity === 'over' ? 'bg-red-50'     : tr.severity === 'warn' ? 'bg-amber-50'     : 'bg-emerald-50'
            const noteCls   = tr.severity === 'over' ? 'bg-red-100 text-red-700' : tr.severity === 'warn' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
            const lawStr    = typeof tr.law === 'object' ? (tr.law as Record<string, string>)[lang] : tr.law
            return (
              <div key={tr.name.zh} className={`rounded-2xl border ${borderCls} ${bgCls} p-4`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{tr.icon}</span>
                    <div>
                      <h3 className="text-sm font-bold text-slate-800">{tr.name[lang]}</h3>
                      <p className="text-[10px] text-slate-500 mt-0.5">
                        {t.conditionLabel}<code className="bg-white/60 px-1 rounded text-[9px]">{tr.condition[lang]}</code>　·　{lawStr}
                      </p>
                    </div>
                  </div>
                  <SeverityBadge s={tr.severity} lang={lang} />
                </div>
                <div className={`rounded-xl px-3 py-2 mb-3 ${noteCls}`}>
                  <p className="text-[11px] font-semibold">{tr.currentNote[lang]}</p>
                </div>
                <div className="space-y-1">
                  {tr.levels.map((l, i) => (
                    <div key={i} className="flex items-start gap-2 text-[11px]">
                      <span className="font-bold flex-shrink-0 text-slate-700">
                        {'days' in l ? t.daysPrefix(l.days as number) : ''}
                        {(l.label as Record<string, string>)[lang]}
                      </span>
                      <span className="text-slate-500">{(l.action as Record<string, string>)[lang]}</span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Laws / 法規同步 ── */}
      {tab === 'laws' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">{t.lawsDesc}</p>
          <div className="space-y-3">
            {REGULATORY_DOCS.map(doc => (
              <div key={doc.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-slate-800">{doc.name[lang]}</h3>
                    <p className="text-[10px] text-slate-400 mt-0.5">{t.keyClause}{doc.key[lang]}</p>
                  </div>
                  <div className="text-right flex-shrink-0 ml-4">
                    <div className="flex items-center gap-1.5 justify-end">
                      <div className="w-2 h-2 rounded-full bg-emerald-500" />
                      <span className="text-[10px] text-emerald-600 font-semibold">{t.synced}</span>
                    </div>
                    <p className="text-[9px] text-slate-400 mt-0.5">{t.lastUpdated}{doc.lastSync}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-3">{t.autoSyncTitle}</h3>
            <div className="space-y-3">
              {t.syncSettings.map(s => (
                <div key={s.label} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                  <div className="flex items-center gap-2">
                    <span className="text-base">{s.icon}</span>
                    <span className="text-xs text-slate-600">{s.label}</span>
                  </div>
                  <span className="text-xs font-semibold text-slate-800">{s.value}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-xl px-4 py-3 text-center" style={{ background: '#1a1a2e' }}>
            <p className="text-xs font-semibold text-white">{t.footerNote}</p>
          </div>
        </div>
      )}

    </div>
  )
}