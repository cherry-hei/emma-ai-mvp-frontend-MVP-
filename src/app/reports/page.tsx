'use client'

import { useState } from 'react'

const PINK = '#E8187A'

const SCHEDULED_REPORTS = [
  {
    name: '月度人手合規報告',
    cron: '每月1日 08:00',
    icon: '📊',
    recipients: ['院長', '助理院長'],
    lastRun: '2026-04-01',
    nextRun: '2026-05-01',
    status: 'ready',
    content: [
      '各更次 FT/PT 實際人數 vs Cap.459A 最低要求',
      'PT比例統計（特定鐘點A/P更；N更另列無上限）',
      'AN超限員工名單（每月>2次AN更）',
      'CL積壓時數及財務負債估算',
      'SL/DSL日數及外購替更成本',
      '下月預測：節假日外購雙倍費率預警',
    ],
    law: 'Cap.459A s.11(1)(3)',
  },
  {
    name: '季度服務質素報告（SQS）',
    cron: '每季首日 08:00',
    icon: '📋',
    recipients: ['院長', '助理院長', 'SWD'],
    lastRun: '2026-04-01',
    nextRun: '2026-07-01',
    status: 'ready',
    content: [
      '服務使用者人數統計',
      '員工訓練完成率（SQS 5.3/5.4）',
      '投訴處理記錄（SQS 15）',
      '意外事故趨勢分析',
      '合規自評（16項SQS逐項）',
    ],
    law: 'SQS 3.2',
  },
  {
    name: '年度牌照申報',
    cron: '每年1月1日 08:00',
    icon: '🏛️',
    recipients: ['院長', '牌照處'],
    lastRun: '2026-01-01',
    nextRun: '2027-01-01',
    status: 'ok',
    content: [
      '安老院員工名單（附件3.2格式）',
      '年度營辦人申報表（附件3.8）',
      '持續進修記錄（主管/保健員；Cap.459A s.10.10/11.10）',
    ],
    law: 'Cap.459A s.9.6',
  },
]

const EVENT_TRIGGERS = [
  {
    trigger: 'STAFF_JOIN_LEAVE',
    icon: '👤',
    label: '員工入職/離職',
    action: '自動更新SWD員工名單 + 通知牌照處',
    sla: '1個工作天內',
    law: 'Cap.459A s.9.6',
    status: 'active',
    recentCount: 2,
    recentNote: '本月2次觸發',
  },
  {
    trigger: 'INCIDENT_REPORTED',
    icon: '🚨',
    label: '特別事故登記',
    action: '生成附件8.3預填草稿 + 提醒24h通報時限',
    sla: '即時',
    law: 'Cap.459A s.8.3',
    status: 'active',
    recentCount: 0,
    recentNote: '本月零事故 ✓',
  },
  {
    trigger: 'INFECTION_OUTBREAK',
    icon: '🦠',
    label: '感染控制事件',
    action: '啟動感染控制流程 + 生成附件13.2呈報表 + 通知相關員工',
    sla: '即時',
    law: 'Cap.459A s.13 / Cap.599',
    status: 'active',
    recentCount: 0,
    recentNote: '本月無感染事件 ✓',
  },
  {
    trigger: 'RESIDENT_ADMISSION',
    icon: '🛏️',
    label: '住客入住',
    action: '建立個人照顧計劃提醒 + 6個月後自動提示更新',
    sla: '入住當日',
    law: 'Cap.459A s.12',
    status: 'active',
    recentCount: 3,
    recentNote: '本月3名新住客',
  },
]

const THRESHOLD_TRIGGERS = [
  {
    name: '執照到期警示',
    icon: '📜',
    condition: '執照到期 ≤ 90天',
    severity: 'warn',
    currentCount: 3,
    currentNote: '3人需跟進（Leung 3天、Wong 8天、Yu 19天）',
    levels: [
      { days: 90, label: '🟡 提醒', action: '發送提醒至員工及院長' },
      { days: 30, label: '🟠 警告', action: '發送警告 + 上報助理院長' },
      { days: 7,  label: '🔴 緊急', action: '緊急通知 + 暫緩排入該更' },
    ],
    law: 'SWD Registration',
  },
  {
    name: 'PT比例超標攔截',
    icon: '🛡️',
    condition: '特定鐘點PT人數 > floor(最低×50%)',
    severity: 'over',
    currentCount: 0,
    currentNote: '本月未觸發 — A/P更均在上限內',
    levels: [
      { label: '🔴 即時阻截', action: '阻止排班確認 + 顯示Cap.459A s.11(3)說明 + 建議SWD 686申請' },
    ],
    law: 'Cap.459A s.11(3)',
  },
  {
    name: 'AN更超限阻截',
    icon: '🌙',
    condition: '每人每月AN更數 > 2次',
    severity: 'over',
    currentCount: 22,
    currentNote: '⚠️ 3月22名員工超出2次AN更',
    levels: [
      { label: '🔴 阻截第3次', action: '阻止加入第3次AN更 + 記錄至合規日誌' },
    ],
    law: '院舍內部規定',
  },
  {
    name: 'RN空更緊急通知',
    icon: '🏥',
    condition: 'FT RN = 0 於任何更次',
    severity: 'over',
    currentCount: 17,
    currentNote: '⚠️ 3月17天（P更12天+A更5天）無RN',
    levels: [
      { label: '🔴 即時警告', action: '即時警告院長 + 自動啟動後備RN聯絡流程' },
    ],
    law: 'Cap.459A s.11(1)',
  },
  {
    name: 'CL積壓超限提醒',
    icon: '⏰',
    condition: '每人CL積壓 > 20h',
    severity: 'warn',
    currentCount: 156,
    currentNote: '全院積壓156.5h — 財務負債持續增加',
    levels: [
      { label: '🟠 警告', action: '列入下月更表優先補休 + 財務負債月報更新' },
    ],
    law: '僱傭條例 Cap.57',
  },
  {
    name: '入住率低於90%提醒',
    icon: '🏠',
    condition: '入住率 < 90%',
    severity: 'ok',
    currentCount: 0,
    currentNote: '現時入住率 100% (105/105) ✓',
    levels: [
      { label: '🟡 提醒', action: '提示入住率影響政府撥款計算' },
    ],
    law: 'LSG撥款規定',
  },
]

const REGULATORY_DOCS = [
  { id: 'CAP459A',  name: '《安老院規例》Cap.459A',          lastSync: '2024-06-16', key: 's.11(3) PT人數上限' },
  { id: 'COP_2024', name: '《安老院實務守則》2024年6月修訂版', lastSync: '2025-04-01', key: '第9章 外購服務' },
  { id: 'SQS_16',   name: '社署16項服務質素標準',             lastSync: '2026-04-01', key: 'SQS 8 法律合規' },
  { id: 'LSG_TIPS', name: 'LSG SmartTips 2026年4月版',        lastSync: '2026-04-01', key: '認可/不認可項目' },
]

function SeverityBadge({ s }: { s: string }) {
  const cfg: Record<string, string> = {
    ok:   'bg-emerald-50 text-emerald-700 border-emerald-200',
    warn: 'bg-amber-50 text-amber-700 border-amber-200',
    over: 'bg-red-50 text-red-700 border-red-200',
  }
  const label: Record<string, string> = { ok: '✅ 正常', warn: '⚠️ 警告', over: '🔴 違規' }
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${cfg[s]}`}>
      {label[s]}
    </span>
  )
}

export default function ReportsPage() {
  const [tab, setTab] = useState<'scheduled' | 'event' | 'threshold' | 'laws'>('scheduled')
  const [generating, setGenerating] = useState<string | null>(null)

  const handleGenerate = (name: string) => {
    setGenerating(name)
    setTimeout(() => setGenerating(null), 2000)
  }

  const activeViolations = THRESHOLD_TRIGGERS.filter(t => t.severity === 'over' && t.currentCount > 0).length
  const activeWarnings   = THRESHOLD_TRIGGERS.filter(t => t.severity === 'warn' && t.currentCount > 0).length

  return (
    <div className="p-5 space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">自動報告引擎</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            定時觸發 · 事件觸發 · 閾值觸發 · Emma AI · March 2026
          </p>
        </div>
        <div className="flex items-center gap-2">
          {activeViolations > 0 && (
            <span className="text-xs font-bold px-2.5 py-1 rounded-full border bg-red-50 text-red-700 border-red-200">
              🔴 {activeViolations} 項違規觸發中
            </span>
          )}
          {activeWarnings > 0 && (
            <span className="text-xs font-bold px-2.5 py-1 rounded-full border bg-amber-50 text-amber-700 border-amber-200">
              ⚠️ {activeWarnings} 項警告
            </span>
          )}
        </div>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: '定時報告', value: SCHEDULED_REPORTS.length, color: 'text-blue-600',    bg: 'bg-blue-50 border-blue-200'       },
          { label: '事件觸發', value: EVENT_TRIGGERS.length,    color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' },
          { label: '閾值違規', value: activeViolations,         color: 'text-red-600',     bg: 'bg-red-50 border-red-200'         },
          { label: '監控警告', value: activeWarnings,           color: 'text-amber-600',   bg: 'bg-amber-50 border-amber-200'     },
        ].map(k => (
          <div key={k.label} className={`rounded-xl border p-4 text-center ${k.bg}`}>
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{k.label}</div>
            <div className={`text-2xl font-bold ${k.color}`}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {[
          { id: 'scheduled', label: '🕐 定時報告' },
          { id: 'event',     label: '⚡ 事件觸發' },
          { id: 'threshold', label: '🎯 閾值監控' },
          { id: 'laws',      label: '📚 法規同步' },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id as typeof tab)}
            className="px-4 py-2 text-xs font-semibold border-b-2 transition-all"
            style={{
              borderBottomColor: tab === t.id ? PINK : 'transparent',
              color: tab === t.id ? PINK : '#6b7280',
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── 定時報告 ── */}
      {tab === 'scheduled' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">
            以下報告由 Emma AI 自動生成並發送至指定收件人，院長可隨時手動觸發。
          </p>
          {SCHEDULED_REPORTS.map(r => (
            <div key={r.name} className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-pink-50 text-2xl">
                    {r.icon}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-800">{r.name}</h3>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      ⏰ {r.cron} · 法規：{r.law}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleGenerate(r.name)}
                  disabled={generating === r.name}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white rounded-lg transition-all disabled:opacity-50"
                  style={{ background: PINK }}>
                  {generating === r.name ? '⏳ 生成中...' : '⬇ 立即生成'}
                </button>
              </div>

              <div className="flex items-center gap-2 mb-3">
                <span className="text-[10px] text-slate-400">收件人：</span>
                {r.recipients.map(re => (
                  <span key={re} className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{re}</span>
                ))}
              </div>

              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-2">報告包含內容</p>
                <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                  {r.content.map((c, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-[11px] text-slate-600">
                      <span className="text-emerald-500 mt-0.5 flex-shrink-0">✓</span>
                      <span>{c}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex gap-4 mt-3">
                <div className="text-[10px] text-slate-400">
                  上次生成：<span className="font-semibold text-slate-600">{r.lastRun}</span>
                </div>
                <div className="text-[10px] text-slate-400">
                  下次預定：<span className="font-semibold text-slate-600">{r.nextRun}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── 事件觸發 ── */}
      {tab === 'event' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">
            以下報告/動作在特定事件發生時自動觸發，確保院舍在法定時限內完成通報。
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {EVENT_TRIGGERS.map(e => (
              <div key={e.trigger} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-start gap-3 mb-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-pink-50 text-xl flex-shrink-0">
                    {e.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-bold text-slate-800">{e.label}</h3>
                    <p className="text-[10px] text-slate-400 mt-0.5">法規：{e.law}</p>
                  </div>
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-1 ${
                    e.status === 'active' ? 'bg-emerald-500 animate-pulse' : 'bg-gray-300'
                  }`} />
                </div>

                <div className="rounded-xl bg-slate-50 border border-slate-100 p-3 mb-3">
                  <p className="text-[10px] font-semibold text-slate-500 mb-1">自動動作</p>
                  <p className="text-[11px] text-slate-700 leading-relaxed">{e.action}</p>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-slate-400">SLA：</span>
                    <span className="text-[10px] font-bold text-slate-600">{e.sla}</span>
                  </div>
                  <span className={`text-[10px] font-semibold ${
                    e.recentCount > 0 ? 'text-amber-600' : 'text-emerald-600'
                  }`}>
                    {e.recentNote}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 閾值監控 ── */}
      {tab === 'threshold' && (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            系統持續監控以下指標，達到閾值時自動觸發警示或阻截動作。
          </p>
          {THRESHOLD_TRIGGERS.map(t => {
            const borderCls = t.severity === 'over' ? 'border-red-200'
                            : t.severity === 'warn' ? 'border-amber-200'
                            : 'border-emerald-200'
            const bgCls     = t.severity === 'over' ? 'bg-red-50'
                            : t.severity === 'warn' ? 'bg-amber-50'
                            : 'bg-emerald-50'
            return (
              <div key={t.name} className={`rounded-2xl border ${borderCls} ${bgCls} p-4`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{t.icon}</span>
                    <div>
                      <h3 className="text-sm font-bold text-slate-800">{t.name}</h3>
                      <p className="text-[10px] text-slate-500 mt-0.5">
                        條件：<code className="bg-white/60 px-1 rounded text-[9px]">{t.condition}</code>
                        　·　{t.law}
                      </p>
                    </div>
                  </div>
                  <SeverityBadge s={t.severity} />
                </div>

                <div className={`rounded-xl px-3 py-2 mb-3 ${
                  t.severity === 'over' ? 'bg-red-100 text-red-700'
                  : t.severity === 'warn' ? 'bg-amber-100 text-amber-700'
                  : 'bg-emerald-100 text-emerald-700'
                }`}>
                  <p className="text-[11px] font-semibold">{t.currentNote}</p>
                </div>

                <div className="space-y-1">
                  {t.levels.map((l, i) => (
                    <div key={i} className="flex items-start gap-2 text-[11px]">
                      <span className="font-bold flex-shrink-0 text-slate-700">
                        {'days' in l ? `${l.days}天前：` : ''}
                        {l.label}
                      </span>
                      <span className="text-slate-500">{l.action}</span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── 法規同步 ── */}
      {tab === 'laws' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">
            Emma AI 每月自動檢查以下法規文件是否有更新，有變更時自動通知院長並更新合規引擎。
          </p>

          <div className="space-y-3">
            {REGULATORY_DOCS.map(doc => (
              <div key={doc.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-slate-800">{doc.name}</h3>
                    <p className="text-[10px] text-slate-400 mt-0.5">關鍵條款：{doc.key}</p>
                  </div>
                  <div className="text-right flex-shrink-0 ml-4">
                    <div className="flex items-center gap-1.5 justify-end">
                      <div className="w-2 h-2 rounded-full bg-emerald-500" />
                      <span className="text-[10px] text-emerald-600 font-semibold">已同步</span>
                    </div>
                    <p className="text-[9px] text-slate-400 mt-0.5">最後更新：{doc.lastSync}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-3">⚙️ 自動同步設定</h3>
            <div className="space-y-3">
              {[
                { label: '同步頻率', value: '每月第一個工作天',         icon: '🔄' },
                { label: '變更偵測', value: '自動對比文件版本',         icon: '🔍' },
                { label: '更新通知', value: '即時通知院長/助理院長',    icon: '🔔' },
                { label: '引擎更新', value: '人手比率/表格範本自動更新', icon: '⚡' },
                { label: '版本記錄', value: '保留所有歷史版本比對',     icon: '📁' },
              ].map(s => (
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
            <p className="text-xs font-semibold text-white">
              Emma AI 自動追蹤 SWD 法規更新 · 有變更即時通知 + 自動更新合規引擎 ⚡
            </p>
          </div>
        </div>
      )}

    </div>
  )
}