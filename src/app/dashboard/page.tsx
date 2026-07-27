'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { DashboardSummary } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

const QUICK_LINKS = [
  { key: 'ql_roster',     icon: '📅', path: '/roster'     },
  { key: 'ql_compliance', icon: '✅', path: '/compliance' },
  { key: 'ql_alert',      icon: '🔔', path: '/alert'      },
  { key: 'ql_reports',    icon: '📊', path: '/reports'    },
  { key: 'ql_roi',        icon: '📈', path: '/roi'        },
  { key: 'ql_staff',      icon: '👤', path: '/staff'      },
]

// Presentation only — which colour/icon each incident type gets in the chart.
const INCIDENT_STYLE: Record<string, { icon: string; color: string }> = {
  SL:     { icon: '😷', color: PINK      },
  DSL:    { icon: '🏥', color: '#f59e0b' },
  urgent: { icon: '⚡', color: '#8b5cf6' },
  late:   { icon: '🕐', color: '#6b7280' },
}

const SHIFT_COLORS = ['#3b82f6', '#10b981', '#1a1a2e', '#9ca3af', '#8b5cf6', '#f59e0b']

function monthLabel(iso: string | undefined, isZH: boolean): string {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString(isZH ? 'zh-HK' : 'en-GB', { month: 'long', year: 'numeric' })
}

export default function DashboardPage() {
  const router = useRouter()
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const [data, setData] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.dashboard().then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load dashboard'))
  }, [])

  const L = {
    title:         isZH ? '儀表板' : 'Dashboard',
    kpi_sl:        isZH ? 'SL/DSL 總事件' : 'SL/DSL Events',
    kpi_sl_sub:    isZH ? '本月實際' : 'This month, actual',
    kpi_ai:        isZH ? 'Emma AI 自動處理' : 'Auto-resolved by AI',
    kpi_resp:      isZH ? '平均響應時間' : 'Avg Response Time',
    kpi_resp_sub:  isZH ? '人手處理需 45min' : 'Manual handling: 45min',
    kpi_comp:      isZH ? '合規達標率' : 'Compliance Rate',
    kpi_comp_sub:  isZH ? 'SWD 人手比率' : 'SWD Staffing Ratio',
    distrib_title: isZH ? 'SL/DSL 事件分佈' : 'SL/DSL Distribution',
    cases:         isZH ? '宗' : 'cases',
    quick_title:   isZH ? '快速導航' : 'Quick Navigation',
    ql_roster:     isZH ? '更表管理' : 'Roster',
    ql_compliance: isZH ? '合規監察' : 'Compliance',
    ql_alert:      isZH ? '警報中心' : 'Alert Centre',
    ql_reports:    isZH ? '報告' : 'Reports',
    ql_roi:        isZH ? 'ROI 分析' : 'ROI Analysis',
    ql_staff:      isZH ? '員工檔案' : 'Staff Portfolio',
    shift_title:   isZH ? '今日更次分佈' : "Today's Shift Distribution",
    alert_title:   isZH ? '最近事件' : 'Recent Incidents',
    resolved:      isZH ? '已處理' : 'Resolved',
    pending:       isZH ? '待處理' : 'Pending',
    ai_title:      isZH ? 'Emma AI 本月摘要' : 'Emma AI Monthly Summary',
    view_all:      isZH ? '查看全部' : 'View All',
    total_staff:   isZH ? '總員工：' : 'Total: ',
    total:         isZH ? '共' : 'Total:',
    loading:       isZH ? '載入中…' : 'Loading…',
    no_roster:     isZH ? '本週期未有更表資料' : 'No roster data for this period',
    no_incidents:  isZH ? '本月未有事件' : 'No incidents this month',
  }

  if (error) {
    return (
      <div className="p-5">
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-700">{error}</div>
      </div>
    )
  }
  if (!data) {
    return <div className="p-5 text-xs text-gray-400">{L.loading}</div>
  }

  const k = data.kpis
  const KPI = [
    { label: L.kpi_sl,   value: String(k.incidents_month), unit: L.cases, color: PINK,
      sub: L.kpi_sl_sub },
    { label: L.kpi_ai,   value: String(k.auto_resolved),   unit: L.cases, color: '#10b981',
      sub: `${k.auto_resolved_pct}% ${isZH ? '自動解決' : 'auto-resolved'}` },
    { label: L.kpi_resp, value: String(k.avg_response_minutes), unit: 'min', color: '#f59e0b',
      sub: L.kpi_resp_sub },
    { label: L.kpi_comp, value: String(k.compliance_rate_pct), unit: '%', color: '#6366f1',
      sub: L.kpi_comp_sub },
  ]

  const totalIncidents = data.incident_distribution.reduce((a, d) => a + d.count, 0)
  const subtitle = [
    data.facility.name,
    monthLabel(data.period?.start, isZH),
    data.roster_version?.label,
  ].filter(Boolean).join(' · ')

  return (
    <div className="p-5 space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-lg font-bold text-gray-900">{L.title}</h1>
        <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-4 gap-3">
        {KPI.map((c) => (
          <div key={c.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{c.label}</div>
            <div className="flex items-end gap-0.5">
              <span className="text-[28px] font-bold tabular-nums leading-none" style={{ color: c.color }}>
                {c.value}
              </span>
              <span className="text-xs text-gray-400 mb-1">{c.unit}</span>
            </div>
            <div className="text-[10px] text-gray-400 mt-1">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* SL/DSL distribution */}
      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-semibold text-gray-900">{L.distrib_title}</div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold px-2.5 py-1 rounded-full"
              style={{ background: '#fce8f3', color: PINK }}>
              {L.total} {totalIncidents} {L.cases}
            </span>
            <button onClick={() => router.push('/alert')}
              className="text-[10px] font-medium hover:underline" style={{ color: PINK }}>
              {L.view_all} →
            </button>
          </div>
        </div>
        {totalIncidents === 0 ? (
          <div className="text-[11px] text-gray-400 py-3">{L.no_incidents}</div>
        ) : (
          <div className="space-y-2.5">
            {data.incident_distribution.map((a) => {
              const style = INCIDENT_STYLE[a.incident_type] ?? { icon: '•', color: '#6b7280' }
              return (
                <div key={a.incident_type} className="flex items-center gap-3">
                  <span className="text-base w-6 text-center flex-shrink-0">{style.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs font-medium text-gray-700">{a.incident_type}</span>
                      <span className="text-xs font-bold tabular-nums" style={{ color: style.color }}>
                        {a.count} {L.cases}
                      </span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all"
                        style={{ width: `${a.pct}%`, background: style.color }} />
                    </div>
                  </div>
                  <span className="text-[10px] text-gray-400 w-8 text-right flex-shrink-0">{a.pct}%</span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 3-col row */}
      <div className="grid grid-cols-3 gap-4">

        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-sm font-semibold text-gray-900 mb-3">{L.quick_title}</div>
          <div className="grid grid-cols-2 gap-2">
            {QUICK_LINKS.map((q) => (
              <button key={q.key} onClick={() => router.push(q.path)}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl border border-gray-100 hover:border-pink-200 hover:bg-pink-50/40 transition-all">
                <span className="text-xl">{q.icon}</span>
                <span className="text-[10px] font-medium text-gray-700 text-center">
                  {L[q.key as keyof typeof L]}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-sm font-semibold text-gray-900 mb-3">{L.shift_title}</div>
          {data.shift_distribution.length === 0 ? (
            <div className="text-[11px] text-gray-400 py-3">{L.no_roster}</div>
          ) : (
            <div className="space-y-3">
              {data.shift_distribution.map((s, i) => (
                <div key={s.shift_type} className="flex items-center gap-3">
                  <span className="text-[11px] font-bold w-8 text-gray-700">{s.shift_type}</span>
                  <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all"
                      style={{ width: `${s.pct}%`, background: SHIFT_COLORS[i % SHIFT_COLORS.length] }} />
                  </div>
                  <span className="text-[10px] text-gray-500 w-6 text-right tabular-nums">{s.count}</span>
                </div>
              ))}
            </div>
          )}
          <div className="mt-4 pt-3 border-t border-gray-100">
            <div className="text-[10px] text-gray-500">
              {L.total_staff}<span className="font-bold text-gray-800">{data.total_staff}</span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold text-gray-900">{L.alert_title}</div>
            <button onClick={() => router.push('/alert')}
              className="text-[10px] font-medium hover:underline" style={{ color: PINK }}>
              {L.view_all}
            </button>
          </div>
          {data.recent_incidents.length === 0 ? (
            <div className="text-[11px] text-gray-400 py-3">{L.no_incidents}</div>
          ) : (
            <div className="space-y-2.5">
              {data.recent_incidents.map((a) => (
                <div key={a.id} className="flex items-center gap-2.5">
                  <div className="w-8 h-7 rounded-full flex items-center justify-center text-[9px] font-bold text-white flex-shrink-0"
                    style={{ background: INCIDENT_STYLE[a.incident_type]?.color ?? PINK }}>
                    {a.incident_type}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-medium text-gray-800 truncate">
                      {a.name_en || a.name}
                    </div>
                    <div className="text-[9px] text-gray-400">
                      {[a.unit_name, a.date].filter(Boolean).join(' · ')}
                    </div>
                  </div>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${
                    a.resolved ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-600'
                  }`}>
                    {a.resolved ? L.resolved : L.pending}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>

      {/* Emma AI summary — derived from this facility's own numbers */}
      <div className="rounded-2xl p-5 text-white" style={{ background: 'linear-gradient(135deg, #1a1a2e, #2d2d5e)' }}>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xl">🤖</span>
          <span className="text-sm font-bold">{L.ai_title}</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {data.highlights.map((h) => (
            <div key={h.key} className="rounded-xl p-3 text-[11px] leading-relaxed text-gray-300"
              style={{ background: 'rgba(255,255,255,0.08)' }}>
              {isZH ? h.text_zh : h.text_en}
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
