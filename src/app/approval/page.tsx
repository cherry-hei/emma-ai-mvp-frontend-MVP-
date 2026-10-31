'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '@/lib/api'
import { approvalCsv } from '@/lib/approval-csv.js'
import type { LeaveCategory, LeaveGroup, LeaveRequest, LeaveStats, Unit } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { canDecide, canRecommend, canRead } from '@/lib/permissions'

const PINK = '#E8187A'
const PINK_HOVER = '#cf126b'

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
  recommendation: 'approve' | 'reject'
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
function ReasonModal({ title, placeholder, onConfirm, onCancel, isZH }: {
  title: string; placeholder: string; isZH: boolean
  onConfirm: (reason: string) => Promise<boolean>; onCancel: () => void
}) {
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState('')
  async function submit() {
    if (pending || !reason.trim()) return
    setPending(true); setFailure('')
    try {
      if (!await onConfirm(reason.trim())) setFailure(isZH ? '未保存，理由已保留，請重試。' : 'Not saved. Your reason is retained; please retry.');
    } finally { setPending(false) }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div role="dialog" aria-modal="true" aria-label={title} className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[85dvh] overflow-y-auto p-5 space-y-4">
        <h3 className="text-sm font-bold text-gray-900">{title}</h3>
        <textarea
          className="w-full border border-gray-200 rounded-xl p-3 text-xs text-gray-700 outline-none focus:border-pink-300 resize-none"
          disabled={pending} rows={3} placeholder={placeholder} value={reason}
          onChange={(e) => setReason(e.target.value)} autoFocus
        />
        {failure && <p role="alert" className="text-sm text-rose-700">{failure}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <button disabled={pending} onClick={onCancel}
            className="px-4 py-2 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">
            {isZH ? '取消' : 'Cancel'}
          </button>
          <button onClick={() => void submit()} disabled={pending || !reason.trim()}
            className="px-4 py-2 text-xs rounded-lg text-white font-medium disabled:opacity-40"
            style={{ background: PINK }}>
            {isZH ? '確認' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Recommendation Badge ───────────────────────────────────────────────────
function RecommendationBadge({ rec }: { rec: Recommendation }) {
  const isApprove = rec.recommendation === 'approve'
  return (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs ${
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
  onAction: (id: string, action: string, note?: string) => Promise<boolean>
  busy: boolean
}) {
  const [showRejectModal, setShowRejectModal] = useState(false)
  const [showRecommendModal, setShowRecommendModal] = useState(false)
  const [showWithdrawModal, setShowWithdrawModal] = useState(false)

  const recs = request.recommendations ?? []
  const hasDisagreement = recs.length >= 2 &&
    recs.some(r => r.recommendation === 'approve') &&
    recs.some(r => r.recommendation === 'reject')

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
        <div className="emma-reflow-wrap flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full flex items-center justify-center text-xs text-white font-bold flex-shrink-0"
              style={{ background: PINK }}>
              {(request.name_en || request.name || '?')[0]}
            </div>
            <div>
              <div className="text-sm font-semibold text-gray-900">{isZH ? request.name || request.name_en : request.name_en || request.name}</div>
              <div className="text-xs text-gray-400">
                {[request.rank, request.unit_name].filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {hasDisagreement && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
                {isZH ? '⚠️ 意見分歧' : '⚠️ Disagreement'}
              </span>
            )}
            <span className="text-xs px-2 py-0.5 rounded-full font-medium"
              style={{ background: statusStyle.bg, color: statusStyle.text }}>
              {statusLabel}
            </span>
          </div>
        </div>

        {/* Request details */}
        <div className="emma-reflow-stack grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-0.5">
              {isZH ? '類型' : 'Type'}
            </div>
            <div className="font-medium text-gray-800">{request.leave_type}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-0.5">
              {isZH ? '日期' : 'Dates'}
            </div>
            <div className="font-medium text-gray-800">{fmtRange(request.date_start, request.date_end)}</div>
          </div>
          {request.requested_shift_type && (
            <div>
              <div className="text-xs text-gray-400 uppercase tracking-wider mb-0.5">
                {isZH ? '申請更期' : 'Shift'}
              </div>
              <div className="font-medium text-gray-800">{request.requested_shift_type}</div>
            </div>
          )}
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-0.5">
              {isZH ? '申請日期' : 'Applied'}
            </div>
            <div className="text-gray-600">{fmtDate(request.created_at)}</div>
          </div>
        </div>

        {/* Reason */}
        {request.reason && (
          <div className="text-xs text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
            <span className="text-xs text-gray-400 font-medium uppercase mr-2">
              {isZH ? '原因' : 'Reason'}:
            </span>
            {request.reason}
            {request.remark && <span className="text-gray-400 ml-2">({request.remark})</span>}
          </div>
        )}

        {/* Document */}
        {request.document_url && (
          <div className="flex items-center gap-1 text-xs text-blue-600">
            📄 <a href={request.document_url} target="_blank" rel="noopener noreferrer" className="hover:underline">
              {isZH ? '查看附件' : 'View attachment'}
            </a>
          </div>
        )}

        {/* Recommendations section */}
        {recs.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs text-gray-400 uppercase tracking-wider font-medium">
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
            <span className="text-xs text-gray-400 font-medium uppercase mr-2 not-italic">
              {isZH ? '決定備註' : 'Decision note'}:
            </span>
            {request.decision_note}
          </div>
        )}

        {isApproved && (
          <div className="flex flex-col gap-2 rounded-lg border border-sky-100 bg-sky-50 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-xs font-semibold text-sky-800">
                {isZH ? 'A.5 更表同步核對' : 'A.5 roster sync verification'}
              </div>
              <div className="mt-0.5 text-xs leading-relaxed text-sky-700">
                {isZH ? '審批狀態已保存；請核對更表限制及通知。批准假期與自動填更是不同步驟，前端不會假裝已改更。' : 'The decision is saved. Verify roster constraints and notifications. Leave approval and roster autofill are separate steps; the frontend never fabricates a roster change.'}
              </div>
            </div>
            <a href="/roster" className="shrink-0 rounded-lg border border-sky-200 bg-white px-3 py-1.5 text-xs font-semibold text-sky-700 hover:bg-sky-50">
              {isZH ? '開啟更表核對' : 'Open roster'}
            </a>
          </div>
        )}

        {/* Action buttons */}
        <div className="emma-reflow-wrap flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-gray-100">
          <div className="text-xs text-gray-400">
            {request.priority && request.priority !== 'normal' && (
              <span className={`px-1.5 py-0.5 rounded text-xs font-medium uppercase ${
                request.priority === 'urgent' ? 'bg-red-100 text-red-700' :
                request.priority === 'high' ? 'bg-orange-100 text-orange-700' :
                'bg-blue-100 text-blue-700'
              }`}>
                {request.priority}
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            {/* OWNER sees Approve / Reject / Withdraw */}
            {isOwner && isPending && (
              <>
                <button disabled={busy} onClick={() => onAction(request.id, 'approve')}
                  className="px-3 py-1.5 text-xs rounded-lg text-white font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
                  style={{ background: '#10B981' }}>
                  {isZH ? '✅ 批准' : '✅ Approve'}
                </button>
                <button disabled={busy} onClick={() => setShowRejectModal(true)}
                  className="px-3 py-1.5 text-xs rounded-lg border border-rose-200 text-rose-600 font-medium disabled:opacity-50 hover:bg-rose-50 transition-colors">
                  {isZH ? '❌ 拒絕' : '❌ Reject'}
                </button>
              </>
            )}

            {isOwner && isApproved && (
              <button disabled={busy} onClick={() => setShowWithdrawModal(true)}
                className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 text-gray-600 font-medium disabled:opacity-50 hover:bg-gray-50 transition-colors">
                {isZH ? '↩️ 撤回' : '↩️ Withdraw'}
              </button>
            )}

            {/* Recommender sees Recommend Approve / Recommend Reject */}
            {isRecommender && isPending && (
              <>
                <button disabled={busy} onClick={() => setShowRecommendModal(true)}
                  className="px-3 py-1.5 text-xs rounded-lg border border-emerald-200 text-emerald-700 font-medium disabled:opacity-50 hover:bg-emerald-50 transition-colors">
                  {isZH ? '👍 建議批准' : '👍 Recommend Approve'}
                </button>
                <button disabled={busy} onClick={() => setShowRejectModal(true)}
                  className="px-3 py-1.5 text-xs rounded-lg border border-rose-200 text-rose-600 font-medium disabled:opacity-50 hover:bg-rose-50 transition-colors">
                  {isZH ? '👎 建議拒絕' : '👎 Recommend Reject'}
                </button>
              </>
            )}

            {/* Mark as reviewed (any recommender or owner) */}
            {isOwner && isPending && !request.reviewed && (
              <button disabled={busy} onClick={() => onAction(request.id, 'review')}
                className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-500 disabled:opacity-50 hover:bg-gray-50 transition-colors">
                {isZH ? '👁️ 標為已閱' : '👁️ Mark reviewed'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Recommendations are not final decisions; both require a reason. */}
      {showRecommendModal && <ReasonModal isZH={isZH}
        title={isZH ? '建議批准理由（必填）' : 'Reason for recommending approval (required)'}
        placeholder={isZH ? '請輸入理由…' : 'Enter a reason…'}
        onConfirm={async reason => {
          const saved = await onAction(request.id, 'recommend_approve', reason)
          if (saved) setShowRecommendModal(false)
          return saved
        }} onCancel={() => setShowRecommendModal(false)} />}
      {/* Modals */}
      {showRejectModal && (
        <ReasonModal isZH={isZH}
          title={isRecommender
            ? (isZH ? '建議拒絕原因' : 'Reason for recommending rejection')
            : (isZH ? '拒絕原因（必填）' : 'Reason for rejection (required)')
          }
          placeholder={isZH ? '請輸入原因...' : 'Enter reason...'}
          onConfirm={async (reason) => {
            const saved = await onAction(request.id, isRecommender ? 'recommend_reject' : 'reject', reason)
            if (saved) setShowRejectModal(false)
            return saved
          }}
          onCancel={() => setShowRejectModal(false)}
        />
      )}
      {showWithdrawModal && (
        <ReasonModal isZH={isZH}
          title={isZH ? '撤回原因（必填）' : 'Reason for withdrawal (required)'}
          placeholder={isZH ? '請輸入撤回原因...' : 'Enter reason for withdrawal...'}
          onConfirm={async (reason) => {
            const saved = await onAction(request.id, 'withdraw', reason)
            if (saved) setShowWithdrawModal(false)
            return saved
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
  const [syncNotice, setSyncNotice] = useState('')

  const L = {
    title:        isZH ? '審批中心' : 'Approval Centre',
    subtitle:     isZH ? '審批員工申請及假期請求' : 'Approve staff requests and leave applications',
    export:       isZH ? '匯出目前清單' : 'Export Current List',
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

  const scope = user ? `${user.userId}:${user.facilityId ?? ''}:${role ?? ''}` : ''
  const activeScope = useRef(scope)
  activeScope.current = scope
  const loads = useRef(0)
  const statsLoads = useRef(0)
  const saving = useRef(false)

  const loadStats = useCallback(async () => {
    const generation = ++statsLoads.current
    if (!scope) return
    try {
      const data = await api.leaveStats()
      if (scope === activeScope.current && generation === statsLoads.current) setStats(data)
    } catch {
      if (scope === activeScope.current && generation === statsLoads.current) setStats(null)
    }
  }, [scope])

  const load = useCallback(async (silent = false) => {
    const generation = ++loads.current
    if (!scope) return
    if (!silent) setLoading(true)
    setError('')
    try {
      const data = await api.leaveRequests({
        group, category, search: search || undefined,
        unitId: unitId === 'all' ? undefined : unitId,
        dateFrom: dateFrom || undefined, dateTo: dateTo || undefined,
      })
      if (scope !== activeScope.current || generation !== loads.current) return
      setRows(data as LeaveRequestExtended[])
    } catch (cause) {
      if (scope !== activeScope.current || generation !== loads.current) return
      setRows([])
      setError(cause instanceof Error ? cause.message : 'Failed to load requests')
    } finally {
      if (scope === activeScope.current && generation === loads.current) setLoading(false)
    }
  }, [group, category, search, unitId, dateFrom, dateTo, scope])

  useEffect(() => {
    setRows([]); setStats(null); setUnits([]); setSyncNotice(''); setError(''); setBusyId('')
    saving.current = false
    if (!scope) return
    let live = true
    void api.units().then(data => {
      if (live && activeScope.current === scope) setUnits(data)
    }).catch(() => {})
    return () => { live = false }
  }, [scope])

  useEffect(() => { void load(); void loadStats() }, [load, loadStats])
  useEffect(() => {
    const update = () => {
      if (document.visibilityState === 'visible' && navigator.onLine && !saving.current) {
        void load(true); void loadStats()
      }
    }
    const timer = window.setInterval(update, 30_000)
    window.addEventListener('focus', update); window.addEventListener('online', update)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', update); window.removeEventListener('online', update)
    }
  }, [load, loadStats])

  async function handleAction(id: string, action: string, note?: string): Promise<boolean> {
    if (!scope || saving.current || !rows.some(row => row.id === id)) return false
    const originatingScope = scope
    saving.current = true
    setBusyId(id); setError('')
    try {
      if (action === 'withdraw') {
        await api.revokeLeaveRequest(id, note || (isZH ? '管理員撤回批准' : 'Approval revoked by manager'))
      } else if (action === 'recommend_approve' || action === 'recommend_reject') {
        if (!note?.trim()) throw new Error(isZH ? '推薦理由必填' : 'A recommendation reason is required')
        await api.recommendLeaveRequest(id, action === 'recommend_approve' ? 'approve' : 'reject', note.trim())
      } else if (action === 'approve' || action === 'reject' || action === 'review') {
        await api.decideLeaveRequest(id, action, note)
      } else {
        throw new Error('Unsupported approval action')
      }
      if (originatingScope !== activeScope.current) return false
      if (action === 'approve' || action === 'withdraw') {
        setSyncNotice(isZH ? '後端已保存審批決定。請核對更表、限制及通知；批准不等於前端已自動填更。' : 'The backend saved the decision. Check the roster, constraints and notifications; approval does not mean the frontend has automatically filled a shift.')
      }
      void load(); void loadStats()
      return true
    } catch (cause) {
      if (originatingScope === activeScope.current) setError(cause instanceof Error ? cause.message : 'Action failed')
      return false
    } finally {
      if (originatingScope === activeScope.current) { saving.current = false; setBusyId('') }
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{L.title}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{L.subtitle}</p>
        </div>
        {canRead(role, 'reports') && <button disabled={loading || Boolean(error) || rows.length === 0}
          onClick={() => {
            const url = URL.createObjectURL(new Blob([approvalCsv(rows, isZH)], { type: 'text/csv;charset=utf-8' }))
            const link = document.createElement('a'); link.href = url; link.download = 'approval-current-list.csv'; link.click()
            window.setTimeout(() => URL.revokeObjectURL(url), 1000)
          }}
          className="px-4 py-2 text-xs rounded-lg text-white font-medium self-start sm:self-auto"
          style={{ background: PINK }}
          onMouseEnter={(e) => (e.currentTarget.style.background = PINK_HOVER)}
          onMouseLeave={(e) => (e.currentTarget.style.background = PINK)}>
          {L.export}
        </button>}
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">
          {error}
        </div>
      )}

      {/* KPI boxes */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">{L.total_title}</div>
          <div className="text-3xl font-bold text-gray-900 tabular-nums">{stats?.total_actions ?? '-'}</div>
          <div className="text-xs text-gray-400 mt-1">{L.total_label}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">{L.rate_title}</div>
          <div className="text-3xl font-bold tabular-nums" style={{ color: '#10B981' }}>
            {stats ? `${stats.approval_rate}%` : '-'}
          </div>
          <div className="w-full h-1.5 bg-gray-100 rounded-full mt-2 overflow-hidden">
            <div className="h-full rounded-full bg-emerald-400"
              style={{ width: `${stats?.approval_rate ?? 0}%` }} />
          </div>
          <div className="text-xs text-gray-400 mt-1">
            {stats ? `${stats.approved_count}/${stats.decided_count} ${L.rate_sub}` : ''}
          </div>
        </div>
      </div>

      {syncNotice && (
        <div className="emma-reflow-wrap flex flex-wrap items-start justify-between gap-3 gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
          <span>{syncNotice}</span>
          <button onClick={() => setSyncNotice('')} aria-label="Dismiss" className="font-bold text-sky-500">×</button>
        </div>
      )}

      {/* Summary cards */}
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
              className="px-3 py-2 text-xs rounded-t-lg font-medium transition-colors whitespace-nowrap"
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
              key={`${scope}:${r.id}`}
              request={r}
              role={role}
              isZH={isZH}
              onAction={handleAction}
              busy={Boolean(busyId)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
