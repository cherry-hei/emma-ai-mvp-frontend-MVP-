'use client'

import { useRouter } from 'next/navigation'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

const ALERT_TYPES = [
  { icon: '😷', labelZh: 'Sick Leave (SL)',       labelEn: 'Sick Leave (SL)',        count: 31, color: PINK,      pct: 67 },
  { icon: '🏥', labelZh: 'DSL（病假 > 3日）',     labelEn: 'DSL (Sick Leave > 3d)',  count: 8,  color: '#f59e0b', pct: 17 },
  { icon: '⚡', labelZh: 'Urgent Leave',           labelEn: 'Urgent Leave',           count: 5,  color: '#8b5cf6', pct: 11 },
  { icon: '🕐', labelZh: 'Lateness / Late Report', labelEn: 'Lateness / Late Report', count: 2,  color: '#6b7280', pct: 4  },
]

const QUICK_LINKS = [
  { key: 'ql_roster',     icon: '📅', path: '/roster'     },
  { key: 'ql_compliance', icon: '✅', path: '/compliance' },
  { key: 'ql_alert',      icon: '🔔', path: '/alert'      },
  { key: 'ql_reports',    icon: '📊', path: '/reports'    },
  { key: 'ql_roi',        icon: '📈', path: '/roi'        },
  { key: 'ql_staff',      icon: '👤', path: '/staff'      },
]

const RECENT_ALERTS = [
  { type: 'SL', staff: 'Wong Mei Ling',    ward: 'F3',        time: '08:43 AM',  resolved: true  },
  { type: 'OT', staff: 'Cheung Hiu Ching', ward: 'F-wide',    time: '今日 / Today', resolved: false },
  { type: 'SL', staff: 'Yu Yat Sze',       ward: 'East Wing', time: 'Yesterday', resolved: true  },
]

const SHIFT_SUMMARY = [
  { shift: 'A更', count: 12, pct: 80, color: '#3b82f6' },
  { shift: 'P更', count: 8,  pct: 53, color: '#10b981' },
  { shift: 'N更', count: 6,  pct: 40, color: '#1a1a2e' },
  { shift: 'OFF', count: 5,  pct: 33, color: '#9ca3af' },
]

export default function DashboardPage() {
  const router = useRouter()
  const { lang } = useLang()

  const L = {
    zh: {
      title:          '儀表板',
      subtitle:       'Haven 康寧安老院 · March 2026',
      kpi_sl:         'March SL/DSL 總事件',
      kpi_sl_sub:     'March 2026 實際',
      kpi_ai:         'Emma AI 自動處理',
      kpi_ai_sub:     '82.6% 自動解決',
      kpi_resp:       '平均響應時間',
      kpi_resp_sub:   '人手處理需 45min',
      kpi_comp:       '合規達標率',
      kpi_comp_sub:   'SWD 人手比率',
      distrib_title:  'March 2026 SL/DSL 事件分佈',
      distrib_total:  '共 46 宗',
      cases:          '宗',
      quick_title:    '快速導航',
      ql_roster:      '更表管理',
      ql_compliance:  '合規監察',
      ql_alert:       '警報中心',
      ql_reports:     '報告',
      ql_roi:         'ROI 分析',
      ql_staff:       '員工檔案',
      shift_title:    '今日更次分佈',
      alert_title:    '最近警報',
      resolved:       '已處理',
      pending:        '待處理',
      ai_title:       'Emma AI 本月摘要',
      ai_1:           '自動處理 38 宗請假補更，節省 31 小時人手處理時間',
      ai_2:           'SWD 人手比率合規率維持 98%，零違規記錄',
      ai_3:           '平均補更響應時間 14 分鐘（人手需 45 分鐘）',
      view_all:       '查看全部',
      total_staff:    '總員工：',
    },
    en: {
      title:          'Dashboard',
      subtitle:       'Haven Care Home · March 2026',
      kpi_sl:         'March SL/DSL Events',
      kpi_sl_sub:     'March 2026 Actual',
      kpi_ai:         'Auto-resolved by AI',
      kpi_ai_sub:     '82.6% Auto-resolved',
      kpi_resp:       'Avg Response Time',
      kpi_resp_sub:   'Manual handling: 45min',
      kpi_comp:       'Compliance Rate',
      kpi_comp_sub:   'SWD Staffing Ratio',
      distrib_title:  'March 2026 SL/DSL Distribution',
      distrib_total:  'Total: 46 cases',
      cases:          'cases',
      quick_title:    'Quick Navigation',
      ql_roster:      'Roster',
      ql_compliance:  'Compliance',
      ql_alert:       'Alert Centre',
      ql_reports:     'Reports',
      ql_roi:         'ROI Analysis',
      ql_staff:       'Staff Portfolio',
      shift_title:    "Today's Shift Distribution",
      alert_title:    'Recent Alerts',
      resolved:       'Resolved',
      pending:        'Pending',
      ai_title:       'Emma AI Monthly Summary',
      ai_1:           'Auto-resolved 38 leave cases, saving 31 hours of manual work',
      ai_2:           'SWD staffing compliance maintained at 98% — zero violations',
      ai_3:           'Avg cover response time 14 min (manual: 45 min)',
      view_all:       'View All',
      total_staff:    'Total: ',
    },
  }
  const lx = L[lang]

  const KPI = [
    { label: lx.kpi_sl,   value: '46', unit: lx.cases, color: PINK,      sub: lx.kpi_sl_sub   },
    { label: lx.kpi_ai,   value: '38', unit: lx.cases, color: '#10b981', sub: lx.kpi_ai_sub   },
    { label: lx.kpi_resp, value: '14', unit: 'min',    color: '#f59e0b', sub: lx.kpi_resp_sub  },
    { label: lx.kpi_comp, value: '98', unit: '%',      color: '#6366f1', sub: lx.kpi_comp_sub  },
  ]

  return (
    <div className="p-5 space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-lg font-bold text-gray-900">{lx.title}</h1>
        <p className="text-xs text-gray-500 mt-0.5">{lx.subtitle}</p>
      </div>

      {/* KPI Cards — from Alert page */}
      <div className="grid grid-cols-4 gap-3">
        {KPI.map((k, i) => (
          <div key={i} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{k.label}</div>
            <div className="flex items-end gap-0.5">
              <span className="text-[28px] font-bold tabular-nums leading-none" style={{ color: k.color }}>
                {k.value}
              </span>
              <span className="text-xs text-gray-400 mb-1">{k.unit}</span>
            </div>
            <div className="text-[10px] text-gray-400 mt-1">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* SL/DSL Distribution — from Alert page */}
      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-semibold text-gray-900">{lx.distrib_title}</div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold px-2.5 py-1 rounded-full"
              style={{ background: '#fce8f3', color: PINK }}>{lx.distrib_total}</span>
            <button onClick={() => router.push('/alert')}
              className="text-[10px] font-medium hover:underline" style={{ color: PINK }}>
              {lx.view_all} →
            </button>
          </div>
        </div>
        <div className="space-y-2.5">
          {ALERT_TYPES.map((a) => (
            <div key={a.labelEn} className="flex items-center gap-3">
              <span className="text-base w-6 text-center flex-shrink-0">{a.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs font-medium text-gray-700">
                    {lang === 'zh' ? a.labelZh : a.labelEn}
                  </span>
                  <span className="text-xs font-bold tabular-nums" style={{ color: a.color }}>
                    {a.count} {lx.cases}
                  </span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all"
                    style={{ width: `${a.pct}%`, background: a.color }} />
                </div>
              </div>
              <span className="text-[10px] text-gray-400 w-8 text-right flex-shrink-0">{a.pct}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* 3-col row */}
      <div className="grid grid-cols-3 gap-4">

        {/* Quick Nav */}
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-sm font-semibold text-gray-900 mb-3">{lx.quick_title}</div>
          <div className="grid grid-cols-2 gap-2">
            {QUICK_LINKS.map(q => (
              <button key={q.key} onClick={() => router.push(q.path)}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl border border-gray-100 hover:border-pink-200 hover:bg-pink-50/40 transition-all">
                <span className="text-xl">{q.icon}</span>
                <span className="text-[10px] font-medium text-gray-700 text-center">
                  {lx[q.key as keyof typeof lx]}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Shift Distribution */}
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-sm font-semibold text-gray-900 mb-3">{lx.shift_title}</div>
          <div className="space-y-3">
            {SHIFT_SUMMARY.map(s => (
              <div key={s.shift} className="flex items-center gap-3">
                <span className="text-[11px] font-bold w-8 text-gray-700">{s.shift}</span>
                <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all"
                    style={{ width: `${s.pct}%`, background: s.color }} />
                </div>
                <span className="text-[10px] text-gray-500 w-6 text-right tabular-nums">{s.count}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 pt-3 border-t border-gray-100">
            <div className="text-[10px] text-gray-500">
              {lx.total_staff}<span className="font-bold text-gray-800">31</span>
            </div>
          </div>
        </div>

        {/* Recent Alerts */}
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold text-gray-900">{lx.alert_title}</div>
            <button onClick={() => router.push('/alert')}
              className="text-[10px] font-medium hover:underline" style={{ color: PINK }}>
              {lx.view_all}
            </button>
          </div>
          <div className="space-y-2.5">
            {RECENT_ALERTS.map((a, i) => (
              <div key={i} className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full flex items-center justify-center text-[9px] font-bold text-white flex-shrink-0"
                  style={{ background: a.type === 'OT' ? '#f59e0b' : PINK }}>
                  {a.type}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] font-medium text-gray-800 truncate">{a.staff}</div>
                  <div className="text-[9px] text-gray-400">{a.ward} · {a.time}</div>
                </div>
                <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${
                  a.resolved ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-600'
                }`}>
                  {a.resolved ? lx.resolved : lx.pending}
                </span>
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* Emma AI Summary */}
      <div className="rounded-2xl p-5 text-white" style={{ background: 'linear-gradient(135deg, #1a1a2e, #2d2d5e)' }}>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xl">🤖</span>
          <span className="text-sm font-bold">{lx.ai_title}</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {[lx.ai_1, lx.ai_2, lx.ai_3].map((txt, i) => (
            <div key={i} className="rounded-xl p-3 text-[11px] leading-relaxed text-gray-300"
              style={{ background: 'rgba(255,255,255,0.08)' }}>
              {txt}
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}