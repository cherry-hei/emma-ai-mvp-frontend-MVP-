'use client'
import { useState } from 'react'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#f28f9e'
const PINK_HOVER = '#e87a8e'

type MainTab = 'pending' | 'approved'
type SubTab  = 'al' | 'duty' | 'sick'

/* ─── Status Badge ─────────────────────────── */
function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { bg: string; text: string }> = {
    'Reviewed':            { bg: '#FEF3C7', text: '#92400E' },
    '已審閱':              { bg: '#FEF3C7', text: '#92400E' },
    'Pending Approve':     { bg: '#EFF6FF', text: '#1D4ED8' },
    '待審批':              { bg: '#EFF6FF', text: '#1D4ED8' },
    'Approved':            { bg: '#D1FAE5', text: '#065F46' },
    '已批准':              { bg: '#D1FAE5', text: '#065F46' },
    'Rejected':            { bg: '#FFE4E6', text: '#9F1239' },
    '已拒絕':              { bg: '#FFE4E6', text: '#9F1239' },
    'Approved & Reviewed': { bg: '#D1FAE5', text: '#065F46' },
    '已批准及審閱':        { bg: '#D1FAE5', text: '#065F46' },
  }
  const c = cfg[status] ?? { bg: '#F3F4F6', text: '#374151' }
  return (
    <span className="text-[9px] px-2 py-0.5 rounded-full font-medium" style={{ background: c.bg, color: c.text }}>
      {status}
    </span>
  )
}

/* ─── Staff Cell ────────────────────────────── */
function StaffCell({ name, rank }: { name: string; rank: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] text-white font-bold flex-shrink-0"
        style={{ background: PINK }}>
        {name[0]}
      </div>
      <div>
        <div className="text-[11px] font-semibold text-gray-900">{name}</div>
        <div className="text-[9px] text-gray-400">{rank}</div>
      </div>
    </div>
  )
}

/* ─── Table wrapper ─────────────────────────── */
function Table({ headers, rows }: { headers: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-gray-100">
            {headers.map(h => (
              <th key={h} className="px-3 py-2.5 text-left text-[9px] font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-3 align-middle">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ─── Main Page ─────────────────────────────── */
export default function ApprovalPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const L = {
    title:        isZH ? '審批中心'                     : 'Approval Centre',
    subtitle:     isZH ? '院長審批員工申請及假期請求'    : 'Approve staff requests and leave applications',
    export:       isZH ? '匯出 Excel'                   : 'Export Excel',
    total_label:  isZH ? '本月審批總數'                 : 'Total this month',
    total_title:  isZH ? '審批總數'                     : 'Total Actions',
    rate_title:   isZH ? '批准率'                       : 'Approval Rate',
    search_ph:    isZH ? '搜尋員工名稱...'              : 'Search staff name...',
    all_floors:   isZH ? '所有樓層'                     : 'All Floors',
    floor1:       isZH ? '1樓'                          : 'Floor 1',
    floor2:       isZH ? '2樓'                          : 'Floor 2',
    floor3:       isZH ? '3樓'                          : 'Floor 3',
    apply_filter: isZH ? '篩選'                         : 'Apply Filter',
    tab_pending:  isZH ? '⏳ 待審批'                    : '⏳ Pending Approval',
    tab_approved: isZH ? '✅ 已審批'                    : '✅ Approved',
    sub_al:       isZH ? '年假 / 特別假'                : 'Annual Leave & Special Leave',
    sub_duty:     isZH ? '更期 / 補假申請'              : 'Duty & Day Off Request',
    sub_sick:     isZH ? '病假 / 遲到 / 緊急假'         : 'Sick / Late / Urgent Leave',
    // AL headers
    al_h:         isZH
      ? ['員工', '日期及假期類型', '備註 / 原因', '狀態', '申請日期']
      : ['Staff Member', 'Date & Leave Type', 'Remark / Reason', 'Status', 'Applied Date'],
    // Duty headers
    duty_h:       isZH
      ? ['員工', '假期日期', '申請更期', '備註', '狀態', '申請日期']
      : ['Staff Member', 'Date of Day Off', 'Shift Requested', 'Remark', 'Status', 'Applied Date'],
    // Sick headers
    sick_h:       isZH
      ? ['員工', '日期', '類型', '原因', '文件', '狀態', '申請日期']
      : ['Staff Member', 'Date', 'Type', 'Reason', 'Document', 'Status', 'Applied Date'],
    // Data labels
    annual_leave: isZH ? '年假'   : 'Annual Leave',
    sick_leave:   isZH ? '病假'   : 'Sick Leave',
    marriage:     isZH ? '婚假'   : 'Marriage',
    fever:        isZH ? '發燒'   : 'Fever',
    a_shift:      isZH ? 'A更 (07:00–15:00)' : 'A Shift (07:00–15:00)',
    // Status labels
    st_reviewed:  isZH ? '已審閱'     : 'Reviewed',
    st_pending:   isZH ? '待審批'     : 'Pending Approve',
    st_approved:  isZH ? '已批准'     : 'Approved',
    st_rejected:  isZH ? '已拒絕'     : 'Rejected',
    st_approved_reviewed: isZH ? '已批准及審閱' : 'Approved & Reviewed',
  }

  const [mainTab, setMainTab] = useState<MainTab>('pending')
  const [subTab,  setSubTab]  = useState<SubTab>('al')
  const [search,  setSearch]  = useState('')
  const [floor,   setFloor]   = useState('all')

  const isPending = mainTab === 'pending'

  const SUB_TABS: { key: SubTab; label: string }[] = [
    { key: 'al',   label: L.sub_al },
    { key: 'duty', label: L.sub_duty },
    { key: 'sick', label: L.sub_sick },
  ]

  /* ── Table content builders ── */
  function PendingAL() {
    return (
      <Table headers={L.al_h} rows={[[
        <StaffCell name="Ho Kai Ching" rank="CW" />,
        <div><div className="font-medium text-gray-800">27/11 – 3/12</div><div className="text-[9px] text-gray-400">{L.annual_leave}</div></div>,
        <span className="text-gray-600">{L.marriage}</span>,
        <StatusBadge status={L.st_reviewed} />,
        <span className="text-gray-400">15/10/2025</span>,
      ]]} />
    )
  }

  function PendingDuty() {
    return (
      <Table headers={L.duty_h} rows={[[
        <StaffCell name="Wong Jing Yin" rank="CW" />,
        <span className="text-gray-400">—</span>,
        <div><div className="font-medium text-gray-800">29/4</div><div className="text-[9px] text-gray-400">{L.a_shift}</div></div>,
        <span className="text-gray-400">—</span>,
        <StatusBadge status={L.st_pending} />,
        <span className="text-gray-400">20/3/2026</span>,
      ]]} />
    )
  }

  function PendingSick() {
    return (
      <Table headers={L.sick_h} rows={[[
        <StaffCell name="Wong Sze Kai" rank="PTA" />,
        <span className="text-gray-600">28/3/2026</span>,
        <span className="text-gray-600">{L.sick_leave}</span>,
        <span className="text-gray-600">{L.fever}</span>,
        <button className="flex items-center gap-1 text-[10px] text-blue-600 hover:underline">
          <span>📄</span> sick leave cert.pdf
        </button>,
        <StatusBadge status={L.st_approved} />,
        <span className="text-gray-400">28/3/2026</span>,
      ]]} />
    )
  }

  function ApprovedAL() {
    return (
      <Table headers={L.al_h} rows={[[
        <StaffCell name="Ho Kai Ching" rank="CW" />,
        <div><div className="font-medium text-gray-800">27/11 – 3/12</div><div className="text-[9px] text-gray-400">{L.annual_leave}</div></div>,
        <span className="text-gray-600">{L.marriage}</span>,
        <StatusBadge status={L.st_approved} />,
        <span className="text-gray-400">15/10/2025</span>,
      ]]} />
    )
  }

  function ApprovedDuty() {
    return (
      <Table headers={L.duty_h} rows={[[
        <StaffCell name="Wong Jing Yin" rank="CW" />,
        <span className="text-gray-400">—</span>,
        <div><div className="font-medium text-gray-800">29/4</div><div className="text-[9px] text-gray-400">{L.a_shift}</div></div>,
        <span className="text-gray-400">—</span>,
        <StatusBadge status={L.st_rejected} />,
        <span className="text-gray-400">20/3/2026</span>,
      ]]} />
    )
  }

  function ApprovedSick() {
    return (
      <Table headers={L.sick_h} rows={[[
        <StaffCell name="Wong Sze Kai" rank="PTA" />,
        <span className="text-gray-600">28/3/2026</span>,
        <span className="text-gray-600">{L.sick_leave}</span>,
        <span className="text-gray-600">{L.fever}</span>,
        <button className="flex items-center gap-1 text-[10px] text-blue-600 hover:underline">
          <span>📄</span> sick leave cert.pdf
        </button>,
        <StatusBadge status={L.st_approved_reviewed} />,
        <span className="text-gray-400">28/3/2026</span>,
      ]]} />
    )
  }

  return (
    <div className="p-5 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{L.title}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{L.subtitle}</p>
        </div>
        <button className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
          style={{ background: PINK }}
          onMouseEnter={e => (e.currentTarget.style.background = PINK_HOVER)}
          onMouseLeave={e => (e.currentTarget.style.background = PINK)}>
          {L.export}
        </button>
      </div>

      {/* KPI boxes */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-[9px] text-gray-400 uppercase tracking-wider mb-1">{L.total_title}</div>
          <div className="text-3xl font-bold text-gray-900">144</div>
          <div className="text-[10px] text-gray-400 mt-1">{L.total_label}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-[9px] text-gray-400 uppercase tracking-wider mb-1">{L.rate_title}</div>
          <div className="text-3xl font-bold" style={{ color: '#10B981' }}>94%</div>
          <div className="w-full h-1.5 bg-gray-100 rounded-full mt-2 overflow-hidden">
            <div className="h-full rounded-full bg-emerald-400" style={{ width: '94%' }} />
          </div>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-xs text-gray-700 outline-none focus:border-pink-300 w-40"
          placeholder={L.search_ph}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-700 outline-none"
          value={floor} onChange={e => setFloor(e.target.value)}>
          <option value="all">{L.all_floors}</option>
          <option value="f1">{L.floor1}</option>
          <option value="f2">{L.floor2}</option>
          <option value="f3">{L.floor3}</option>
        </select>
        <button className="px-3 py-1.5 text-xs rounded-lg text-white font-medium" style={{ background: PINK }}>
          {L.apply_filter}
        </button>
        <input type="date" className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-600 outline-none" />
        <span className="text-gray-300 text-xs">—</span>
        <input type="date" className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-600 outline-none" />
      </div>

      {/* Main tabs */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="flex border-b border-gray-100">
          {(['pending','approved'] as MainTab[]).map(t => (
            <button key={t} onClick={() => setMainTab(t)}
              className="flex-1 py-2.5 text-xs font-semibold transition-colors"
              style={{
                color:        mainTab === t ? PINK : '#6B7280',
                background:   mainTab === t ? '#fff5f7' : 'transparent',
                borderBottom: mainTab === t ? `2px solid ${PINK}` : '2px solid transparent',
              }}>
              {t === 'pending' ? L.tab_pending : L.tab_approved}
            </button>
          ))}
        </div>

        {/* Sub tabs */}
        <div className="flex border-b border-gray-50 bg-gray-50 px-3 gap-1 pt-2">
          {SUB_TABS.map(s => (
            <button key={s.key} onClick={() => setSubTab(s.key)}
              className="px-3 py-1.5 text-[10px] rounded-t-lg font-medium transition-colors"
              style={{
                background:   subTab === s.key ? '#ffffff' : 'transparent',
                color:        subTab === s.key ? PINK : '#9CA3AF',
                borderBottom: subTab === s.key ? `2px solid ${PINK}` : '2px solid transparent',
              }}>
              {s.label}
            </button>
          ))}
        </div>

        {/* Table content */}
        <div className="p-0">
          {isPending
            ? subTab === 'al'   ? <PendingAL />
            : subTab === 'duty' ? <PendingDuty />
            :                     <PendingSick />
            : subTab === 'al'   ? <ApprovedAL />
            : subTab === 'duty' ? <ApprovedDuty />
            :                     <ApprovedSick />
          }
        </div>
      </div>
    </div>
  )
}