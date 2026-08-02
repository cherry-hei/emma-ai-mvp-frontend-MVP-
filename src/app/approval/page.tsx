'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, downloadReportCsv } from '@/lib/api'
import type { LeaveCategory, LeaveGroup, LeaveRequest, LeaveStats, Unit } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { canDecide, canRecommend, grantFor } from '@/lib/permissions'

const PINK = '#f28f9e'
const PINK_HOVER = '#e87a8e'

const STATUS_STYLE: Record<string, { bg: string; text: string }> = {
  pending:     { bg: '#EFF6FF', text: '#1D4ED8' },
  reviewed:    { bg: '#FEF3C7', text: '#92400E' },
  recommended: { bg: '#E0E7FF', text: '#3730A3' },
  approved:    { bg: '#D1FAE5', text: '#065F46' },
  rejected:    { bg: '#FFE4E6', text: '#9F1239' },
  withdrawn:   { bg: '#F3F4F6', text: '#6B7280' },
  cancelled:   { bg: '#F3F4F6', text: '#374151' },
}

// Recommendation type — will be populated when API supports it
interface Recommendation {
  recommender_name: string
  recommender_role: string
  decision: 'approve' | 'reject'
  reason?: string
  created_at?: string
}

// Extended LeaveRequest with recommendations
interface LeaveRequestExtended extends LeaveRequest {
  recommendations?: Recommendation[]
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '-'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${Number(d)}/${Number(m)}/${y}`
}

function fmtRange(from: string, to: string): string {
  return from === to ? fmtDate(from) : `${fmtDate(from)} – ${fmtDate(to)}`
}

// ─── Reject / Withdraw Reason Modal ────────────────────────────────────────
function ReasonModal({ title, placeholder, onConfirm, onCancel }: {
  title: string; placeholder: string
  onConfirm: (reason: string) => void; onCancel: () => void
}) {
  const [reason, setReason] = useState('')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-5 space-y-4">
        <h3 className="text-sm font-bold text-gray-900">{title}</h3>
        <textarea
          className="w-full border border-gray-200 rounded-xl p-3 text-xs text-gray-700 outline-none focus:border-pink-300 resize-none"
          rows={3} placeholder={placeholder} value={reason}
          onChange={(e) => setReason(e.target.value)} autoFocus
        />
        <div className="flex justify-end gap-2">
          <button onClick={onCancel}
            className="px-4 py-2 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">
            取消 / Cancel
          </button>
          <button onClick={() => onConfirm(reason)} disabled={!reason.trim()}
            className="px-4 py-2 text-xs rounded-lg text-white font-medium disabled:opacity-40"
            style={{ background: PINK }}>
            確認 / Confirm
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Recommendation Badge ───────────────────────────────────────────────────
function RecommendationBadge({ rec }: { rec: Recommendation }) {
  const isApprove = rec.decision === 'approve'
  return (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] ${
      isApprove ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
    }`}>
      <span>{isApprove ? '✅' : '❌'}</span>
      <span className="font-medium">{rec.recommender_name}</span>
      <span className="text-gray-400">({rec.recommender_role})</span>
      {rec.reason && <span className="text-gray-500 ml-1">— {rec.reason}</span>}
    </div>
  )
}

// ─── Approval Card (stacked list item) ──────────────────────────────────────
function ApprovalCard({ request, role, isZH, onAction, busy }: {
  request: LeaveRequestExtended
  role: string | null
  isZH: boolean
  onAction: (id: string, action: string, note?: string) => void
  busy: boolean
}) {
  const [showRejectModal, setShowRejectModal] = useState(false)
  const [showWithdrawModal, setShowWithdrawModal] = useState(false)

  const recs = request.recommendations ?? []
  const hasDisagreement = recs.length >= 2 &&
    recs.some(r => r.decision === 'approve') &&
    recs.some(r => r.decision === 'reject')

  const isOwner = canDecide(role, 'approve.leave')
  const isRecommender = canRecommend(role, 'approve.leave') && !isOwner
  const isPending = request.status === 'pending' || request.status === 'reviewed'
  const isApproved = request.status === 'approved'

  const statusStyle = STATUS_STYLE[request.status] ?? STATUS_STYLE.cancelled
  const statusLabel = isZH
    ? { pending: '待審批', reviewed: '已審閱', recommended: '已建議', approved: '已批准', rejected: '已拒絕', withdrawn: '已撤回', cancelled: '已取消' }[request.status] ?? request.status
    : { pending: 'Pending', reviewed: 'Reviewed', recommended: 'Recommended', approved: 'Approved', rejected: 'Rejected', withdrawn: 'Withdrawn', cancelled: 'Cancelled' }[request.status] ?? request.status

  return (
    <>
      <div className={`bg-white border rounded-xl p-4 space-y-3 transition-all hover:shadow-sm ${
        hasDisagreement ? 'border-amber-300 ring-1 ring-amber-100' : 'border-gray-200'
      }`}>
        {/* Header: Staff info + Status */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full flex items-center justify-center text-xs text-white font-bold flex-shrink-0"
              style={{ background: PINK }}>
              {(request.name_en || request.name || '?')[0]}
            </div>
            <div>
              <div className="text-sm font-semibold text-gray-900">{request.name_en || request.name}</div>
              <div className="text-[10px] text-gray-400">
                {[request.rank, request.unit_name].filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {hasDisagreement && (
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
                {isZH ? '⚠️ 意見分歧' : '⚠️ Disagreement'}
              </span>
            )}
            <span className="text-[9px] px-2 py-0.5 rounded-full font-medium"
              style={{ background: statusStyle.bg, color: statusStyle.text }}>
              {statusLabel}
            </span>
          </div>
        </div>

        {/* Request details */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div>
            <div className="text-[9px] text-gray-400 uppercase tracking-wider mb-0.5">
              {isZH ? '類型' : 'Type'}
            </div>
            <div className="font-medium text-gray-800">{request.leave_type}</div>
          </div>
          <div>
            <div className="text-[9px] text-gray-400 uppercase tracking-wider mb-0.5">
              {isZH ? '日期' : 'Dates'}
            </div>
            <div className="font-medium text-gray-800">{fmtRange(request.date_start, request.date_end)}</div>
          </div>
          {request.requested_shift_type && (
            <div>
              <div className="text-[9px] text-gray-400 uppercase tracking-wider mb-0.5">
                {isZH ? '申請更期' : 'Shift'}
              </div>
              <div className="font-medium text-gray-800">{request.requested_shift_type}</div>
            </div>
          )}
          <div>
            <div className="text-[9px] text-gray-400 uppercase tracking-wider mb-0.5">
              {isZH ? '申請日期' : 'Applied'}
            </div>
            <div className="text-gray-600">{fmtDate(request.created_at)}</div>
          </div>
        </div>

        {/* Reason */}
        {request.reason && (
          <div className="text-xs text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
            <span className="text-[9px] text-gray-400 font-medium uppercase mr-2">
              {isZH ? '原因' : 'Reason'}:
            </span>
            {request.reason}
            {request.remark && <span className="text-gray-400 ml-2">({request.remark})</span>}
          </div>
        )}

        {/* Document */}
        {request.document_url && (
          <div className="flex items-center gap-1 text-[10px] text-blue-600">
            📄 <a href={request.document_url} target="_blank" rel="noopener noreferrer" className="hover:underline">
              {isZH ? '查看附件' : 'View attachment'}
            </a>
          </div>
        )}

        {/* Recommendations section */}
        {recs.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[9px] text-gray-400 uppercase tracking-wider font-medium">
              {isZH ? '建議意見' : 'Recommendations'}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {recs.map((rec, i) => <RecommendationBadge key={i} rec={rec} />)}
            </div>
          </div>
        )}

        {/* Decision note (for already-decided items) */}
        {request.decision_note && (
          <div className="text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2 italic">
            <span className="text-[9px] text-gray-400 font-medium uppercase mr-2 not-italic">
              {isZH ? '決定備註' : 'Decision note'}:
            </span>
            {request.decision_note}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex items-center justify-between pt-2 border-t border-gray-100">
          <div className="text-[9px] text-gray-400">
            {request.priority && request.priority !== 'normal' && (
              <span className={`px-1.5 py-0.5 rounded text-[8px] font-medium uppercase ${
                request.priority === 'urgent' ? 'bg-red-100 text-red-700' :
                request.priority === 'high' ? 'bg-orange-100 text-orange-700' :
                'bg-blue-100 text-blue-700'
              }`}>
                {request.priority}
              </span>
            )}
          </div>

          <div className="flex gap-2">
            {/* OWNER sees Approve / Reject / Withdraw */}
            {isOwner && isPending && (
              <>
                <button disabled={busy} onClick={() => onAction(request.id, 'approve')}
                  className="px-3 py-1.5 text-[10px] rounded-lg text-white font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
                  style={{ background: '#10B981' }}>
                  {isZH ? '✅ 批准' : '✅ Approve'}
                </button>
                <button disabled={busy} onClick={() => setShowRejectModal(true)}
                  className="px-3 py-1.5 text-[10px] rounded-lg border border-rose-200 text-rose-600 font-medium disabled:opacity-50 hover:bg-rose-50 transition-colors">
                  {isZH ? '❌ 拒絕' : '❌ Reject'}
                </button>
              </>
            )}

            {isOwner && isApproved && (
              <button disabled={busy} onClick={() => setShowWithdrawModal(true)}
                className="px-3 py-1.5 text-[10px] rounded-lg border border-gray-300 text-gray-600 font-medium disabled:opacity-50 hover:bg-gray-50 transition-colors">
                {isZH ? '↩️ 撤回' : '↩️ Withdraw'}
              </button>
            )}

            {/* Recommender sees Recommend Approve / Recommend Reject */}
            {isRecommender && isPending && (
              <>
                <button disabled={busy} onClick={() => onAction(request.id, 'recommend_approve')}
                  className="px-3 py-1.5 text-[10px] rounded-lg border border-emerald-200 text-emerald-700 font-medium disabled:opacity-50 hover:bg-emerald-50 transition-colors">
                  {isZH ? '👍 建議批准' : '👍 Recommend Approve'}
                </button>
                <button disabled={busy} onClick={() => setShowRejectModal(true)}
                  className="px-3 py-1.5 text-[10px] rounded-lg border border-rose-200 text-rose-600 font-medium disabled:opacity-50 hover:bg-rose-50 transition-colors">
                  {isZH ? '👎 建議拒絕' : '👎 Recommend Reject'}
                </button>
              </>
            )}

            {/* Mark as reviewed (any recommender or owner) */}
            {(isOwner || isRecommender) && isPending && !request.reviewed && (
              <button disabled={busy} onClick={() => onAction(request.id, 'review')}
                className="px-3 py-1.5 text-[10px] rounded-lg border border-gray-200 text-gray-500 disabled:opacity-50 hover:bg-gray-50 transition-colors">
                {isZH ? '👁️ 標為已閱' : '👁️ Mark reviewed'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Modals */}
      {showRejectModal && (
        <ReasonModal
          title={isRecommender
            ? (isZH ? '建議拒絕原因' : 'Reason for recommending rejection')
            : (isZH ? '拒絕原因（必填）' : 'Reason for rejection (required)')
          }
          placeholder={isZH ? '請輸入原因...' : 'Enter reason...'}
          onConfirm={(reason) => {
            setShowRejectModal(false)
            onAction(request.id, isRecommender ? 'recommend_reject' : 'reject', reason)
          }}
          onCancel={() => setShowRejectModal(false)}
        />
      )}
      {showWithdrawModal && (
        <ReasonModal
          title={isZH ? '撤回原因（必填）' : 'Reason for withdrawal (required)'}
          placeholder={isZH ? '請輸入撤回原因...' : 'Enter reason for withdrawal...'}
          onConfirm={(reason) => {
            setShowWithdrawModal(false)
            onAction(request.id, 'withdraw', reason)
          }}
          onCancel={() => setShowWithdrawModal(false)}
        />
      )}
    </>
  )
}

// ─── Main Page ──────────────────────────────────────────────────────────────
export default function ApprovalPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const role = user?.role ?? null
  const isZH = lang === 'zh'

  const [group, setGroup] = useState<LeaveGroup>('pending')
  const [category, setCategory] = useState<LeaveCategory>('al')
  const [search, setSearch] = useState('')
  const [unitId, setUnitId] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [rows, setRows] = useState<LeaveRequestExtended[]>([])
  const [stats, setStats] = useState<LeaveStats | null>(null)
  const [units, setUnits] = useState<Unit[]>([])
  const [loading, setLoading] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')

  const L = {
    title:        isZH ? '審批中心' : 'Approval Centre',
    subtitle:     isZH ? '審批員工申請及假期請求' : 'Approve staff requests and leave applications',
    export:       isZH ? '匯出報告' : 'Export Report',
    total_title:  isZH ? '審批總數' : 'Total Actions',
    total_label:  isZH ? '本月審批總數' : 'Total this month',
    rate_title:   isZH ? '批准率' : 'Approval Rate',
    rate_sub:     isZH ? '已決定的申請中批准比例' : 'of decided requests',
    search_ph:    isZH ? '搜尋員工名稱...' : 'Search staff name...',
    all_units:    isZH ? '所有單位' : 'All units',
    tab_pending:  isZH ? '⏳ 待審批' : '⏳ Pending',
    tab_approved: isZH ? '✅ 已處理' : '✅ Processed',
    sub_al:       isZH ? '年假 / 特別假' : 'Annual & Special Leave',
    sub_duty:     isZH ? '更期 / 補假申請' : 'Duty & Day Off Request',
    sub_sick:     isZH ? '病假 / 遲到 / 緊急假' : 'Sick / Late / Urgent Leave',
    empty:        isZH ? '沒有符合條件的申請' : 'No requests match these filters',
    loading:      isZH ? '載入中…' : 'Loading…',
  }

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
      .then((data) => setRows(data as LeaveRequestExtended[]))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load requests'))
      .finally(() => setLoading(false))
  }, [group, category, search, unitId, dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    api.leaveStats().then(setStats).catch(() => {})
    api.units().then(setUnits).catch(() => {})
  }, [])

  async function handleAction(id: string, action: string, note?: string) {
    setBusyId(id)
    setError('')
    try {
      // Map frontend actions to API decisions
      const apiDecision = (() => {
        switch (action) {
          case 'approve': return 'approve'
          case 'reject': return 'reject'
          case 'review': return 'review'
          case 'withdraw': return 'reject' // withdraw uses reject with special note
          case 'recommend_approve': return 'review' // recommend uses review for now
          case 'recommend_reject': return 'review'  // recommend uses review for now
          default: return action
        }
      })() as 'approve' | 'reject' | 'review'

      const decisionNote = action === 'withdraw'
        ? `[WITHDRAWN] ${note}`
        : action === 'recommend_approve'
        ? `[RECOMMEND APPROVE] ${note || ''}`
        : action === 'recommend_reject'
        ? `[RECOMMEND REJECT] ${note}`
        : note

      await api.decideLeaveRequest(id, apiDecision, decisionNote || undefined)
      load()
      api.leaveStats().then(setStats).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-5xl mx-auto">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{L.title}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{L.subtitle}</p>
        </div>
        <button
          onClick={() => downloadReportCsv('staff_register').catch(
            (e) => setError(e instanceof Error ? e.message : 'Export failed'))}
          className="px-4 py-2 text-xs rounded-lg text-white font-medium self-start sm:self-auto"
          style={{ background: PINK }}
          onMouseEnter={(e) => (e.currentTarget.style.background = PINK_HOVER)}
          onMouseLeave={(e) => (e.currentTarget.style.background = PINK)}>
          {L.export}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">
          {error}
        </div>
      )}

      {/* KPI boxes */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
          className="border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-700 outline-none focus:border-pink-300 w-full sm:w-40"
          placeholder={L.search_ph}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="border border-gray-200 rounded-lg px-2 py-2 text-xs text-gray-700 outline-none"
          value={unitId} onChange={(e) => setUnitId(e.target.value)}>
          <option value="all">{L.all_units}</option>
          {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
          className="border border-gray-200 rounded-lg px-2 py-2 text-xs text-gray-600 outline-none" />
        <span className="text-gray-300 text-xs">–</span>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
          className="border border-gray-200 rounded-lg px-2 py-2 text-xs text-gray-600 outline-none" />
      </div>

      {/* Tabs */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="flex border-b border-gray-100">
          {(['pending', 'approved'] as LeaveGroup[]).map((t) => (
            <button key={t} onClick={() => setGroup(t)}
              className="flex-1 py-3 text-xs font-semibold transition-colors"
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

        <div className="flex border-b border-gray-50 bg-gray-50 px-3 gap-1 pt-2 overflow-x-auto">
          {SUB_TABS.map((s) => (
            <button key={s.key} onClick={() => setCategory(s.key)}
              className="px-3 py-2 text-[10px] rounded-t-lg font-medium transition-colors whitespace-nowrap"
              style={{
                background:   category === s.key ? '#ffffff' : 'transparent',
                color:        category === s.key ? PINK : '#9CA3AF',
                borderBottom: category === s.key ? `2px solid ${PINK}` : '2px solid transparent',
              }}>
              {s.label}
            </button>
          ))}
        </div>

        {/* Stacked card list */}
        <div className="p-3 md:p-4 space-y-3">
          {loading && (
            <div className="py-8 text-center text-gray-400 text-xs">{L.loading}</div>
          )}
          {!loading && rows.length === 0 && (
            <div className="py-8 text-center text-gray-400 text-xs">{L.empty}</div>
          )}
          {!loading && rows.map((r) => (
            <ApprovalCard
              key={r.id}
              request={r}
              role={role}
              isZH={isZH}
              onAction={handleAction}
              busy={busyId === r.id}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
