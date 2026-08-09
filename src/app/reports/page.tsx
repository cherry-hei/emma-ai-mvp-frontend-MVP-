'use client'

import { useCallback, useEffect, useState } from 'react'
import { api, downloadReportCsv } from '@/lib/api'
import type {
  EventTrigger, GeneratedReport, RegulatoryDoc, ReportRow, ReportSchedule,
  ThresholdMonitor,
} from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

type Tab = 'scheduled' | 'event' | 'threshold' | 'laws'

// Shift-report cards: report_type is the backend generator; the wording is UI copy.
const SHIFT_REPORTS = [
  { id: 'roster_hours',  icon: '⏰', en: 'Hours Report',            zh: '工時報告',
    desc_en: 'Total rostered hours per staff over the period', desc_zh: '各員工整個週期總工時' },
  { id: 'ph_dayoff',     icon: '📅', en: 'PH & Day Off Report',     zh: 'PH & Day Off 報告',
    desc_en: 'Public holidays worked and day-off counts', desc_zh: '公眾假期出勤及休班日統計' },
  { id: 'do_count',      icon: '📊', en: 'DO Shift Count Report',   zh: 'DO更次數報告',
    desc_en: 'Day-off counts and longest run without a day off', desc_zh: '休班日次數及最長連續工作天' },
  { id: 'ap_shifts',     icon: '⚖️', en: 'A/P Shift Distribution',  zh: 'AP更分配報告',
    desc_en: 'A vs P vs N shift fairness per staff', desc_zh: 'A更/P更/N更分配公平性' },
  { id: 'night_gender',  icon: '🌙', en: 'Night Shift Gender Report', zh: 'N更男女報告',
    desc_en: 'Night shift distribution by gender', desc_zh: '通宵更按性別分配' },
  { id: 'staffing_ratio', icon: '📐', en: 'Staffing Ratio Report',  zh: '人手比率報告',
    desc_en: 'Per-shift and minute-level statutory window results', desc_zh: '逐更及分鐘級法定時段結果' },
]

const SEVERITY_LABEL = {
  ok:   { en: '✅ Normal',    zh: '✅ 正常' },
  warn: { en: '⚠️ Warning',  zh: '⚠️ 警告' },
  over: { en: '🔴 Violation', zh: '🔴 違規' },
}

function SeverityBadge({ s, isZH }: { s: ThresholdMonitor['severity']; isZH: boolean }) {
  const cls = {
    ok:   'bg-emerald-50 text-emerald-700 border-emerald-200',
    warn: 'bg-amber-50 text-amber-700 border-amber-200',
    over: 'bg-red-50 text-red-700 border-red-200',
  }[s]
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${cls}`}>
      {isZH ? SEVERITY_LABEL[s].zh : SEVERITY_LABEL[s].en}
    </span>
  )
}

/* Preview of a freshly generated report. */
function ReportPreview({ report, onClose, isZH }: {
  report: GeneratedReport; onClose: () => void; isZH: boolean
}) {
  const { columns, rows } = report.payload
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6" style={{ background: 'rgba(0,0,0,0.45)' }}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl overflow-hidden flex flex-col" style={{ maxHeight: '88vh' }}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <div>
            <div className="text-sm font-bold text-gray-900">{report.title}</div>
            <div className="text-[10px] text-gray-400 mt-0.5">
              {report.period_start} → {report.period_end} · {report.row_count} {isZH ? '行' : 'rows'}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => downloadReportCsv(report.report_type)}
              className="px-3 py-1.5 text-xs rounded-lg text-white font-medium" style={{ background: PINK }}>
              {isZH ? '下載 CSV' : 'Download CSV'}
            </button>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none px-1">✕</button>
          </div>
        </div>
        <div className="overflow-auto p-4">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-200">
                {columns.map((c) => (
                  <th key={c.key} className="px-2 py-2 text-left text-[9px] font-semibold text-gray-400 uppercase whitespace-nowrap">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-gray-50">
                  {columns.map((c) => (
                    <td key={c.key} className="px-2 py-1.5 text-gray-700 whitespace-nowrap">{String(r[c.key] ?? '')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default function ReportsPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const [tab, setTab] = useState<Tab>('scheduled')
  const [reportPeriodStart, setReportPeriodStart] = useState('')
  const [reportPeriodEnd, setReportPeriodEnd] = useState('')
  const [schedules, setSchedules] = useState<ReportSchedule[]>([])
  const [triggers, setTriggers] = useState<EventTrigger[]>([])
  const [monitors, setMonitors] = useState<ThresholdMonitor[]>([])
  const [docs, setDocs] = useState<RegulatoryDoc[]>([])
  const [recent, setRecent] = useState<ReportRow[]>([])
  const [generating, setGenerating] = useState('')
  const [preview, setPreview] = useState<GeneratedReport | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    Promise.all([
      api.reportSchedules(), api.eventTriggers(), api.thresholds(),
      api.regulatoryDocs(), api.reports(),
    ])
      .then(([s, e, m, d, r]) => { setSchedules(s); setTriggers(e); setMonitors(m); setDocs(d); setRecent(r) })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load reports'))
  }, [])

  useEffect(() => { load() }, [load])

  const T = {
    title:      isZH ? '自動報告引擎' : 'Automated Report Engine',
    subtitle:   isZH ? '定時觸發 · 事件觸發 · 閾值觸發 · Emma AI'
                     : 'Scheduled · Event-triggered · Threshold-triggered · Emma AI',
    violations: (n: number) => isZH ? `🔴 ${n} 項違規觸發中` : `🔴 ${n} Active Violation${n > 1 ? 's' : ''}`,
    warnings:   (n: number) => isZH ? `⚠️ ${n} 項警告` : `⚠️ ${n} Warning${n > 1 ? 's' : ''}`,
    kpi:        isZH ? ['定時報告', '事件觸發', '閾值違規', '監控警告']
                     : ['Scheduled', 'Event Triggers', 'Violations', 'Warnings'],
    tabs:       isZH ? ['🕐 定時報告', '⚡ 事件觸發', '🎯 閾值監控', '📚 法規同步']
                     : ['🕐 Scheduled', '⚡ Event Triggers', '🎯 Threshold Monitor', '📚 Regulatory Sync'],
    scheduledDesc: isZH
      ? '以下報告由 Emma AI 自動生成並發送至指定收件人，院長可隨時手動觸發。'
      : 'These reports are generated and sent by Emma AI on schedule; the Home Manager may trigger any of them at any time.',
    eventDesc: isZH
      ? '以下報告/動作在特定事件發生時自動觸發。本月觸發次數取自 facility_events 實際記錄。'
      : 'These actions fire when the matching event occurs. This month\'s counts come from the facility\'s own event log.',
    thresholdDesc: isZH
      ? '系統持續監控以下指標，所有數字均由現行更表、證書及負債帳實時計算。'
      : 'Continuously monitored indicators - every number is computed live from the current roster, certificates and debt ledger.',
    lawsDesc: isZH
      ? 'Emma AI 追蹤以下法規文件版本，有變更時通知院長並更新合規引擎。'
      : 'Emma AI tracks the version of each regulatory document and notifies the Home Manager when one changes.',
    generate:   isZH ? '⬇ 立即生成' : '⬇ Generate Now',
    generating: isZH ? '⏳ 生成中...' : '⏳ Generating...',
    recipients: isZH ? '收件人：' : 'Recipients: ',
    contents:   isZH ? '報告包含內容' : 'Report Contents',
    lastRun:    isZH ? '上次生成：' : 'Last generated: ',
    nextRun:    isZH ? '下次預定：' : 'Next scheduled: ',
    regulation: isZH ? '法規：' : 'Regulation: ',
    sla:        isZH ? 'SLA：' : 'SLA: ',
    autoAction: isZH ? '自動動作' : 'Automated Action',
    condition:  isZH ? '條件：' : 'Condition: ',
    keyClause:  isZH ? '關鍵條款：' : 'Key clause: ',
    synced:     isZH ? '已同步' : 'Synced',
    lastUpdated: isZH ? '最後更新：' : 'Last updated: ',
    shiftReports: isZH ? '更期報告 / Shift Reports' : 'Shift Reports',
    shiftReportsSub: isZH ? '由現行更表即時生成' : 'Generated live from the current roster',
    recentTitle: isZH ? '最近生成的報告' : 'Recently generated',
    noRecent:   isZH ? '尚未生成任何報告' : 'No reports generated yet',
    thisMonth:  isZH ? '本月觸發' : 'this month',
    noTrigger:  isZH ? '本月未觸發 ✓' : 'No triggers this month ✓',
  }

  const violations = monitors.filter((m) => m.severity === 'over' && m.current_count > 0).length
  const warnings = monitors.filter((m) => m.severity === 'warn' && m.current_count > 0).length

  async function generate(reportType: string, key: string) {
    setGenerating(key)
    setError('')
    try {
      setPreview(await api.generateReport(reportType))
      api.reports().then(setRecent).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Report generation failed')
    } finally {
      setGenerating('')
    }
  }

  return (
    <div className="p-5 space-y-5">
      {preview && <ReportPreview report={preview} isZH={isZH} onClose={() => setPreview(null)} />}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{T.title}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{T.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          {violations > 0 && (
            <span className="text-xs font-bold px-2.5 py-1 rounded-full border bg-red-50 text-red-700 border-red-200">
              {T.violations(violations)}
            </span>
          )}
          {warnings > 0 && (
            <span className="text-xs font-bold px-2.5 py-1 rounded-full border bg-amber-50 text-amber-700 border-amber-200">
              {T.warnings(warnings)}
            </span>
          )}
        </div>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>}

      {/* KPI strip */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: T.kpi[0], value: schedules.length, color: 'text-blue-600',    bg: 'bg-blue-50 border-blue-200' },
          { label: T.kpi[1], value: triggers.length,  color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' },
          { label: T.kpi[2], value: violations,       color: 'text-red-600',     bg: 'bg-red-50 border-red-200' },
          { label: T.kpi[3], value: warnings,         color: 'text-amber-600',   bg: 'bg-amber-50 border-amber-200' },
        ].map((k) => (
          <div key={k.label} className={`rounded-xl border p-4 text-center ${k.bg}`}>
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{k.label}</div>
            <div className={`text-2xl font-bold ${k.color}`}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {(['scheduled'] as Tab[]) /* MVP: event/threshold/laws hidden */.map((key, i) => (
          <button key={key} onClick={() => setTab(key)}
            className="px-4 py-2 text-xs font-semibold border-b-2 transition-all"
            style={{ borderBottomColor: tab === key ? PINK : 'transparent',
                     color: tab === key ? PINK : '#6b7280' }}>
            {T.tabs[i]}
          </button>
        ))}
      </div>

      {/* Scheduled */}
      {tab === 'scheduled' && (
        <>
          {/* Period Selector */}
          <div className="flex items-center gap-3 mb-4 p-3 bg-gray-50 rounded-xl border border-gray-100">
            <span className="text-xs font-medium text-gray-600">{isZH ? '報告期間：' : 'Report Period:'}</span>
            <input type="date" value={reportPeriodStart} onChange={e => setReportPeriodStart(e.target.value)}
              className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:ring-1 focus:ring-pink-300 outline-none" />
            <span className="text-xs text-gray-400">→</span>
            <input type="date" value={reportPeriodEnd} onChange={e => setReportPeriodEnd(e.target.value)}
              className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:ring-1 focus:ring-pink-300 outline-none" />
          </div>
        <div className="space-y-4">
          <p className="text-xs text-gray-500">{T.scheduledDesc}</p>

          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-2xl">📅</div>
              <div>
                <h3 className="text-sm font-bold text-slate-800">{T.shiftReports}</h3>
                <p className="text-[11px] text-slate-400 mt-0.5">{T.shiftReportsSub}</p>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {SHIFT_REPORTS.map((r) => (
                <button key={r.id} onClick={() => generate(r.id, r.id)} disabled={generating === r.id}
                  className="rounded-xl border border-gray-200 p-3 hover:border-pink-200 hover:bg-pink-50/30 transition-all block text-left disabled:opacity-50">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">{r.icon}</span>
                    <span className="text-xs font-semibold text-gray-800">{isZH ? r.zh : r.en}</span>
                  </div>
                  <div className="text-[10px] text-gray-500">
                    {generating === r.id ? T.generating : (isZH ? r.desc_zh : r.desc_en)}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {schedules.map((s) => (
            <div key={s.id} className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-pink-50 text-2xl">{s.icon ?? '📄'}</div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-800">{(isZH && s.name_zh) || s.name_en}</h3>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      ⏰ {(isZH && s.cron_label_zh) || s.cron_label_en} · {T.regulation}{s.law_reference}
                    </p>
                  </div>
                </div>
                <button onClick={() => generate(s.report_type, s.id)} disabled={generating === s.id}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white rounded-lg transition-all disabled:opacity-50"
                  style={{ background: PINK }}>
                  {generating === s.id ? T.generating : T.generate}
                </button>
              </div>
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <span className="text-[10px] text-slate-400">{T.recipients}</span>
                {((isZH && s.recipients_zh.length ? s.recipients_zh : s.recipients_en)).map((re) => (
                  <span key={re} className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{re}</span>
                ))}
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-2">{T.contents}</p>
                <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                  {((isZH && s.content_zh.length ? s.content_zh : s.content_en)).map((c, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-[11px] text-slate-600">
                      <span className="text-emerald-500 mt-0.5 flex-shrink-0">✓</span>
                      <span>{c}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex gap-4 mt-3">
                <div className="text-[10px] text-slate-400">{T.lastRun}<span className="font-semibold text-slate-600">{s.last_run_at ?? '-'}</span></div>
                <div className="text-[10px] text-slate-400">{T.nextRun}<span className="font-semibold text-slate-600">{s.next_run_at ?? '-'}</span></div>
              </div>
            </div>
          ))}

          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-3">{T.recentTitle}</h3>
            {recent.length === 0 ? (
              <p className="text-[11px] text-slate-400">{T.noRecent}</p>
            ) : (
              <div className="space-y-1.5">
                {recent.map((r) => (
                  <div key={r.id} className="flex items-center justify-between text-[11px] border-b border-slate-50 py-1.5 last:border-0">
                    <span className="font-medium text-slate-700">{r.title}</span>
                    <span className="text-slate-400">
                      {r.row_count} {isZH ? '行' : 'rows'} · {(r.created_at ?? '').slice(0, 16).replace('T', ' ')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Event triggers */}
        </>
      )}

      {false && tab === 'event' && ( /* HIDDEN for MVP */
        <div className="space-y-4">
          <p className="text-xs text-gray-500">{T.eventDesc}</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {triggers.map((e) => (
              <div key={e.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-start gap-3 mb-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-pink-50 text-xl flex-shrink-0">{e.icon ?? '⚡'}</div>
                  <div className="flex-1">
                    <h3 className="text-sm font-bold text-slate-800">{(isZH && e.label_zh) || e.label_en}</h3>
                    <p className="text-[10px] text-slate-400 mt-0.5">{T.regulation}{e.law_reference}</p>
                  </div>
                  <div className="w-2 h-2 rounded-full flex-shrink-0 mt-1 bg-emerald-500 animate-pulse" />
                </div>
                <div className="rounded-xl bg-slate-50 border border-slate-100 p-3 mb-3">
                  <p className="text-[10px] font-semibold text-slate-500 mb-1">{T.autoAction}</p>
                  <p className="text-[11px] text-slate-700 leading-relaxed">{(isZH && e.action_zh) || e.action_en}</p>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-slate-400">{T.sla}</span>
                    <span className="text-[10px] font-bold text-slate-600">{(isZH && e.sla_zh) || e.sla_en}</span>
                  </div>
                  <span className={`text-[10px] font-semibold ${e.recent_count > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>
                    {e.recent_count > 0 ? `${e.recent_count} ${T.thisMonth}` : T.noTrigger}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Threshold monitors */}
      {false && tab === 'threshold' && ( /* HIDDEN for MVP */
        <div className="space-y-3">
          <p className="text-xs text-gray-500">{T.thresholdDesc}</p>
          {monitors.map((m) => {
            const border = m.severity === 'over' ? 'border-red-200' : m.severity === 'warn' ? 'border-amber-200' : 'border-emerald-200'
            const bg     = m.severity === 'over' ? 'bg-red-50'     : m.severity === 'warn' ? 'bg-amber-50'     : 'bg-emerald-50'
            const note   = m.severity === 'over' ? 'bg-red-100 text-red-700' : m.severity === 'warn' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
            return (
              <div key={m.code} className={`rounded-2xl border ${border} ${bg} p-4`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{m.icon}</span>
                    <div>
                      <h3 className="text-sm font-bold text-slate-800">{isZH ? m.name_zh : m.name_en}</h3>
                      <p className="text-[10px] text-slate-500 mt-0.5">
                        {T.condition}
                        <code className="bg-white/60 px-1 rounded text-[9px]">{isZH ? m.condition_zh : m.condition_en}</code>
                        {'　·　'}{isZH ? m.law_zh : m.law_en}
                      </p>
                    </div>
                  </div>
                  <SeverityBadge s={m.severity} isZH={isZH} />
                </div>
                <div className={`rounded-xl px-3 py-2 mb-3 ${note}`}>
                  <p className="text-[11px] font-semibold">{isZH ? m.note_zh : m.note_en}</p>
                </div>
                <div className="space-y-1">
                  {m.levels.map((l, i) => (
                    <div key={i} className="flex items-start gap-2 text-[11px]">
                      <span className="font-bold flex-shrink-0 text-slate-700">
                        {l.days ? `${l.days}${isZH ? '天前：' : ' days: '}` : ''}{isZH ? l.label_zh : l.label_en}
                      </span>
                      <span className="text-slate-500">{isZH ? l.action_zh : l.action_en}</span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Regulatory sync */}
      {false && tab === 'laws' && ( /* HIDDEN for MVP */
        <div className="space-y-4">
          <p className="text-xs text-gray-500">{T.lawsDesc}</p>
          <div className="space-y-3">
            {docs.map((d) => (
              <div key={d.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-slate-800">{(isZH && d.name_zh) || d.name_en}</h3>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      {T.keyClause}{(isZH && d.key_clause_zh) || d.key_clause_en}
                      {d.version_label && ` · v${d.version_label}`}
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0 ml-4">
                    <div className="flex items-center gap-1.5 justify-end">
                      <div className={`w-2 h-2 rounded-full ${d.sync_status === 'synced' ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                      <span className={`text-[10px] font-semibold ${d.sync_status === 'synced' ? 'text-emerald-600' : 'text-amber-600'}`}>
                        {d.sync_status === 'synced' ? T.synced : d.sync_status}
                      </span>
                    </div>
                    <p className="text-[9px] text-slate-400 mt-0.5">{T.lastUpdated}{d.last_synced_at ?? '-'}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
