'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, downloadReportCsv } from '@/lib/api'
import type { LeaveCategory, LeaveGroup, LeaveRequest, LeaveStats, Unit } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#f28f9e'
const PINK_HOVER = '#e87a8e'

const STATUS_STYLE: Record<string, { bg: string; text: string }> = {
  pending:  { bg: '#EFF6FF', text: '#1D4ED8' },
  reviewed: { bg: '#FEF3C7', text: '#92400E' },
  approved: { bg: '#D1FAE5', text: '#065F46' },
  rejected: { bg: '#FFE4E6', text: '#9F1239' },
  cancelled:{ bg: '#F3F4F6', text: '#374151' },
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '-'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${Number(d)}/${Number(m)}/${y}`
}

function fmtRange(from: string, to: string): string {
  return from === to ? fmtDate(from) : `${fmtDate(from)} – ${fmtDate(to)}`
}

export default function ApprovalPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const [group, setGroup] = useState<LeaveGroup>('pending')
  const [category, setCategory] = useState<LeaveCategory>('al')
  const [search, setSearch] = useState('')
  const [unitId, setUnitId] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [rows, setRows] = useState<LeaveRequest[]>([])
  const [stats, setStats] = useState<LeaveStats | null>(null)
  const [units, setUnits] = useState<Unit[]>([])
  const [loading, setLoading] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')

  const L = {
    title:        isZH ? '審批中心' : 'Approval Centre',
    subtitle:     isZH ? '院長審批員工申請及假期請求' : 'Approve staff requests and leave applications',
    export:       isZH ? '匯出 Excel' : 'Export CSV',
    total_label:  isZH ? '本月審批總數' : 'Total this month',
    total_title:  isZH ? '審批總數' : 'Total Actions',
    rate_title:   isZH ? '批准率' : 'Approval Rate',
    rate_sub:     isZH ? '已決定的申請中批准比例' : 'of decided requests',
    search_ph:    isZH ? '搜尋員工名稱...' : 'Search staff name...',
    all_units:    isZH ? '所有單位' : 'All units',
    tab_pending:  isZH ? '⏳ 待審批' : '⏳ Pending Approval',
    tab_approved: isZH ? '✅ 已審批' : '✅ Approved',
    sub_al:       isZH ? '年假 / 特別假' : 'Annual & Special Leave',
    sub_duty:     isZH ? '更期 / 補假申請' : 'Duty & Day Off Request',
    sub_sick:     isZH ? '病假 / 遲到 / 緊急假' : 'Sick / Late / Urgent Leave',
    h_staff:      isZH ? '員工' : 'Staff Member',
    h_dates:      isZH ? '日期及類型' : 'Dates & Type',
    h_shift:      isZH ? '申請更期' : 'Shift Requested',
    h_reason:     isZH ? '原因 / 備註' : 'Reason / Remark',
    h_doc:        isZH ? '文件' : 'Document',
    h_status:     isZH ? '狀態' : 'Status',
    h_applied:    isZH ? '申請日期' : 'Applied',
    h_actions:    isZH ? '操作' : 'Actions',
    approve:      isZH ? '批准' : 'Approve',
    reject:       isZH ? '拒絕' : 'Reject',
    review:       isZH ? '標為已審閱' : 'Mark reviewed',
    reviewed_tag: isZH ? '已審閱' : 'Reviewed',
    empty:        isZH ? '沒有符合條件的申請' : 'No requests match these filters',
    loading:      isZH ? '載入中…' : 'Loading…',
    st_pending:   isZH ? '待審批' : 'Pending',
    st_reviewed:  isZH ? '已審閱' : 'Reviewed',
    st_approved:  isZH ? '已批准' : 'Approved',
    st_rejected:  isZH ? '已拒絕' : 'Rejected',
    st_cancelled: isZH ? '已取消' : 'Cancelled',
  }
  const statusLabel = (s: string) => (L as Record<string, string>)[`st_${s}`] ?? s

  const SUB_TABS: { key: LeaveCategory; label: string }[] = [
    { key: 'al',   label: L.sub_al },
    { key: 'duty', label: L.sub_duty },
    { key: 'sick', label: L.sub_sick },
  ]

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    api.leaveRequests({
      group, category,
      search: search || undefined,
      unitId: unitId === 'all' ? undefined : unitId,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
    })
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load requests'))
      .finally(() => setLoading(false))
  }, [group, category, search, unitId, dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    api.leaveStats().then(setStats).catch(() => {})
    api.units().then(setUnits).catch(() => {})
  }, [])

  async function decide(id: string, decision: 'approve' | 'reject' | 'review') {
    setBusyId(id)
    setError('')
    try {
      await api.decideLeaveRequest(id, decision)
      load()
      api.leaveStats().then(setStats).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusyId('')
    }
  }

  const headers = useMemo(() => {
    const base = [L.h_staff, L.h_dates]
    if (category === 'duty') base.push(L.h_shift)
    base.push(L.h_reason)
    if (category === 'sick') base.push(L.h_doc)
    base.push(L.h_status, L.h_applied, L.h_actions)
    return base
  }, [category, L.h_staff, L.h_dates, L.h_shift, L.h_reason, L.h_doc, L.h_status,
      L.h_applied, L.h_actions])

  return (
    <div className="p-5 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{L.title}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{L.subtitle}</p>
        </div>
        <button
          onClick={() => downloadReportCsv('staff_register').catch(
            (e) => setError(e instanceof Error ? e.message : 'Export failed'))}
          className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
          style={{ background: PINK }}
          onMouseEnter={(e) => (e.currentTarget.style.background = PINK_HOVER)}
          onMouseLeave={(e) => (e.currentTarget.style.background = PINK)}>
          {L.export}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {error}
        </div>
      )}

      {/* KPI boxes */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-[9px] text-gray-400 uppercase tracking-wider mb-1">{L.total_title}</div>
          <div className="text-3xl font-bold text-gray-900 tabular-nums">{stats?.total_actions ?? '-'}</div>
          <div className="text-[10px] text-gray-400 mt-1">{L.total_label}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-[9px] text-gray-400 uppercase tracking-wider mb-1">{L.rate_title}</div>
          <div className="text-3xl font-bold tabular-nums" style={{ color: '#10B981' }}>
            {stats ? `${stats.approval_rate}%` : '-'}
          </div>
          <div className="w-full h-1.5 bg-gray-100 rounded-full mt-2 overflow-hidden">
            <div className="h-full rounded-full bg-emerald-400"
              style={{ width: `${stats?.approval_rate ?? 0}%` }} />
          </div>
          <div className="text-[10px] text-gray-400 mt-1">
            {stats ? `${stats.approved_count}/${stats.decided_count} ${L.rate_sub}` : ''}
          </div>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-xs text-gray-700 outline-none focus:border-pink-300 w-40"
          placeholder={L.search_ph}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-700 outline-none"
          value={unitId} onChange={(e) => setUnitId(e.target.value)}>
          <option value="all">{L.all_units}</option>
          {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
          className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-600 outline-none" />
        <span className="text-gray-300 text-xs">-</span>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
          className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-600 outline-none" />
      </div>

      {/* Tabs + table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="flex border-b border-gray-100">
          {(['pending', 'approved'] as LeaveGroup[]).map((t) => (
            <button key={t} onClick={() => setGroup(t)}
              className="flex-1 py-2.5 text-xs font-semibold transition-colors"
              style={{
                color:        group === t ? PINK : '#6B7280',
                background:   group === t ? '#fff5f7' : 'transparent',
                borderBottom: group === t ? `2px solid ${PINK}` : '2px solid transparent',
              }}>
              {t === 'pending' ? L.tab_pending : L.tab_approved}
              {t === 'pending' && stats?.pending_count ? ` (${stats.pending_count})` : ''}
            </button>
          ))}
        </div>

        <div className="flex border-b border-gray-50 bg-gray-50 px-3 gap-1 pt-2">
          {SUB_TABS.map((s) => (
            <button key={s.key} onClick={() => setCategory(s.key)}
              className="px-3 py-1.5 text-[10px] rounded-t-lg font-medium transition-colors"
              style={{
                background:   category === s.key ? '#ffffff' : 'transparent',
                color:        category === s.key ? PINK : '#9CA3AF',
                borderBottom: category === s.key ? `2px solid ${PINK}` : '2px solid transparent',
              }}>
              {s.label}
            </button>
          ))}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-100">
                {headers.map((h) => (
                  <th key={h} className="px-3 py-2.5 text-left text-[9px] font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={headers.length} className="px-3 py-6 text-center text-gray-400">{L.loading}</td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={headers.length} className="px-3 py-6 text-center text-gray-400">{L.empty}</td></tr>
              )}
              {!loading && rows.map((r) => {
                const style = STATUS_STYLE[r.status] ?? STATUS_STYLE.cancelled
                const label = r.status === 'approved' && r.reviewed
                  ? `${statusLabel('approved')} · ${L.reviewed_tag}`
                  : statusLabel(r.status)
                return (
                  <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="px-3 py-3 align-middle">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] text-white font-bold flex-shrink-0"
                          style={{ background: PINK }}>
                          {(r.name_en || r.name || '?')[0]}
                        </div>
                        <div>
                          <div className="text-[11px] font-semibold text-gray-900">{r.name_en || r.name}</div>
                          <div className="text-[9px] text-gray-400">
                            {[r.rank, r.unit_name].filter(Boolean).join(' · ')}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 align-middle">
                      <div className="font-medium text-gray-800">{fmtRange(r.date_start, r.date_end)}</div>
                      <div className="text-[9px] text-gray-400">{r.leave_type}</div>
                    </td>
                    {category === 'duty' && (
                      <td className="px-3 py-3 align-middle text-gray-600">
                        {r.requested_shift_type ?? '-'}
                      </td>
                    )}
                    <td className="px-3 py-3 align-middle text-gray-600">
                      {r.reason ?? '-'}
                      {r.remark && <div className="text-[9px] text-gray-400">{r.remark}</div>}
                    </td>
                    {category === 'sick' && (
                      <td className="px-3 py-3 align-middle">
                        {r.document_url
                          ? <span className="flex items-center gap-1 text-[10px] text-blue-600">📄 {r.document_url}</span>
                          : <span className="text-gray-300">-</span>}
                      </td>
                    )}
                    <td className="px-3 py-3 align-middle">
                      <span className="text-[9px] px-2 py-0.5 rounded-full font-medium"
                        style={{ background: style.bg, color: style.text }}>
                        {label}
                      </span>
                    </td>
                    <td className="px-3 py-3 align-middle text-gray-400">{fmtDate(r.created_at)}</td>
                    <td className="px-3 py-3 align-middle">
                      {group === 'pending' ? (
                        <div className="flex gap-1.5">
                          <button disabled={busyId === r.id} onClick={() => decide(r.id, 'approve')}
                            className="px-2 py-1 text-[10px] rounded-lg text-white font-medium disabled:opacity-50"
                            style={{ background: '#10B981' }}>
                            {L.approve}
                          </button>
                          <button disabled={busyId === r.id} onClick={() => decide(r.id, 'reject')}
                            className="px-2 py-1 text-[10px] rounded-lg border border-rose-200 text-rose-600 font-medium disabled:opacity-50 hover:bg-rose-50">
                            {L.reject}
                          </button>
                          {!r.reviewed && (
                            <button disabled={busyId === r.id} onClick={() => decide(r.id, 'review')}
                              className="px-2 py-1 text-[10px] rounded-lg border border-gray-200 text-gray-500 disabled:opacity-50 hover:bg-gray-50">
                              {L.review}
                            </button>
                          )}
                        </div>
                      ) : (
                        <span className="text-[10px] text-gray-400">{fmtDate(r.decided_at)}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
