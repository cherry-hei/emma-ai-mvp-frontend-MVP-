'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type {
  AlertItem, ApiStaff, Incident, IncidentStats, ReplacementCandidate,
} from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'
const PINK_HOVER = '#c9156a'

const KIND_ICON: Record<AlertItem['kind'], string> = {
  cover: '🚨', certificate: '📜', ratio: '⚠️', hours: '⏰',
}
const TYPE_COLOR: Record<string, string> = {
  SL: PINK, DSL: '#f59e0b', urgent: '#8b5cf6', late: '#6b7280',
}

type Step = 1 | 2 | 3 | 4 | 5
type ChatMsg = { from: 'system' | 'staff'; text: string }

/* ─── Resolution flow ─────────────────────────────────────────────────────── */
function ResolutionModal({ incidentId, onClose, onResolved, isZH }: {
  incidentId: string
  onClose: () => void
  onResolved: () => void
  isZH: boolean
}) {
  const [step, setStep] = useState<Step>(1)
  const [incident, setIncident] = useState<Incident | null>(null)
  const [candidates, setCandidates] = useState<ReplacementCandidate[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [outcome, setOutcome] = useState<{ minutes: number; toil: number; name: string } | null>(null)
  const [chatMsgs, setChatMsgs] = useState<ChatMsg[]>([])
  const [chatPhase, setChatPhase] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      api.incidents({ limit: 200 }).then((rows) => rows.find((r) => r.id === incidentId) ?? null),
      // compliance_checked=false so blocked candidates come back with their reasons -
      // hiding them would make the check invisible instead of auditable.
      api.replacementCandidates(incidentId, { complianceChecked: false, refresh: true }),
    ])
      .then(([inc, cands]) => {
        if (cancelled) return
        setIncident(inc)
        setCandidates(cands)
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [incidentId])

  const eligible = candidates.filter((c) => c.compliance_ok)
  const blocked = candidates.filter((c) => !c.compliance_ok)

  const L = {
    title:    isZH ? '補更處理流程' : 'Resolution Flow: Cover Shift',
    steps:    isZH
      ? ['確認請假資料', '核查合規影響', 'AI 推薦候選', '發送通知', '完成處理']
      : ['Confirm Leave Details', 'Compliance Impact Check', 'AI Recommended Cover', 'Send Notification', 'Resolved'],
    staff:    isZH ? '員工：' : 'Staff: ',
    date:     isZH ? '日期：' : 'Date: ',
    shift:    isZH ? '更次：' : 'Shift: ',
    reason:   isZH ? '原因：' : 'Reason: ',
    reported: isZH ? '報告時間：' : 'Reported: ',
    next:     isZH ? '繼續下一步' : 'Next Step',
    viewAi:   isZH ? '查看 AI 推薦' : 'View AI Recommendations',
    eligible: isZH ? '合規候選' : 'Compliance-clean candidates',
    blockedT: isZH ? '被規則排除' : 'Excluded by a rule',
    assign:   isZH ? '✓ 指派' : '✓ Assign',
    noCands:  isZH ? '沒有合規候選 - 需外購人手' : 'No compliant internal candidate - agency cover required',
    complianceOk: isZH ? '所有候選已通過休息時間、工時上限、假期及職級資格檢查'
                       : 'Every listed candidate passes rest-gap, max-hours, leave and rank-eligibility checks',
    resolvedT: isZH ? '✅ 已完成補更' : '✅ Cover assigned',
    assignedTo: isZH ? '接更員工：' : 'Assigned to: ',
    responseT: isZH ? '響應時間：' : 'Response time: ',
    toil:     isZH ? 'TOIL 補時已記入 future_debt_ledger：' : 'TOIL recorded in the future-debt ledger: ',
    notify:   isZH ? '已透過應用內通知員工（WhatsApp 尚未接通）'
                   : 'Staff notified in-app (WhatsApp channel not yet connected)',
    close:    isZH ? '關閉' : 'Close',
    loading:  isZH ? '載入中…' : 'Loading…',
    score:    isZH ? '分' : 'pts',
    assignedSaved: isZH ? '✓ 已指派並儲存至更表' : '✓ Assignment saved to the roster',
    chatPreviewNote: isZH
      ? '以下為 WhatsApp 通知預覽（模擬） - 實際通知現時透過應用內發送'
      : 'Preview of the WhatsApp notification (simulated) - the real notification is sent in-app today',
    chatSystem: (shiftLabel: string) => isZH
      ? `緊急補更通知\n${shiftLabel} 有更次需要接更\n請問你今日有空接更嗎？`
      : `Urgent Cover Request\n${shiftLabel} needs cover\nAre you available to cover today?`,
    chatReply: isZH ? '我可以接更 ✓' : 'I can cover ✓',
    chatConfirm: isZH
      ? '✅ 收到！已確認接更，更表同步更新中'
      : '✅ Confirmed! Cover accepted, roster syncing',
    staffReplyBtn: isZH ? '模擬員工接受（點此模擬回覆）✓' : 'Simulate staff acceptance (click to simulate) ✓',
    online: isZH ? '在線' : 'Online',
  }

  async function assign(staffId: string, name: string) {
    setBusy(staffId)
    setError('')
    try {
      const res = await api.resolveIncident(incidentId, { replacement_staff_id: staffId })
      setOutcome({
        minutes: res.resolution_minutes,
        toil: res.future_debt?.quantity ?? 0,
        name,
      })
      setChatMsgs([{
        from: 'system',
        text: L.chatSystem(incident ? `${incident.shift_type ?? ''} ${incident.shift_window ?? ''}`.trim() : ''),
      }])
      setChatPhase(1)
      setStep(4)
      onResolved()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Assignment failed')
    } finally {
      setBusy('')
    }
  }

  function handleStaffReply() {
    if (chatPhase !== 1) return
    setChatMsgs((m) => [...m, { from: 'staff', text: L.chatReply }])
    setChatPhase(2)
    setTimeout(() => {
      setChatMsgs((m) => [...m, { from: 'system', text: L.chatConfirm }])
      setChatPhase(3)
      setStep(5)
    }, 800)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.45)' }}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl mx-4 overflow-hidden flex flex-col" style={{ maxHeight: '92vh' }}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <div>
            <div className="text-sm font-bold text-gray-900">{L.title}</div>
            <div className="text-[10px] text-gray-400 mt-0.5">
              {incident ? `${incident.name_en || incident.name} · ${incident.date} · ${incident.shift_type ?? ''}` : ''}
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">✕</button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Steps rail */}
          <div className="w-56 flex-shrink-0 border-r border-gray-100 p-4 space-y-1 overflow-y-auto">
            {L.steps.map((label, i) => {
              const n = (i + 1) as Step
              const done = step > n
              const active = step === n
              return (
                <button key={label} onClick={() => step >= n && setStep(n)}
                  className="w-full text-left p-3 rounded-xl transition-all"
                  style={{ background: active ? '#fff0f5' : done ? '#f9fafb' : 'transparent' }}>
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0"
                      style={{ background: done ? '#10B981' : active ? PINK : '#e5e7eb',
                               color: done || active ? '#fff' : '#9ca3af' }}>
                      {done ? '✓' : n}
                    </div>
                    <span className="text-[11px] font-semibold"
                      style={{ color: active ? PINK : done ? '#374151' : '#9ca3af' }}>
                      {label}
                    </span>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-5">
            {error && (
              <div className="mb-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
                {error}
              </div>
            )}
            {loading && <div className="text-xs text-gray-400">{L.loading}</div>}

            {!loading && step === 1 && incident && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">{L.steps[0]}</div>
                <div className="bg-red-50 border border-red-100 rounded-xl p-4 space-y-1.5 text-[11px] text-gray-700">
                  <div><span className="text-gray-400">{L.staff}</span>{incident.name_en || incident.name} ({incident.rank})</div>
                  <div><span className="text-gray-400">{L.date}</span>{incident.date}</div>
                  <div><span className="text-gray-400">{L.shift}</span>{incident.shift_type ?? '-'} {incident.shift_window ?? ''}</div>
                  <div><span className="text-gray-400">{L.reason}</span>{incident.reason ?? incident.incident_type}</div>
                  <div><span className="text-gray-400">{L.reported}</span>{new Date(incident.reported_at).toLocaleString()}</div>
                </div>
                <button onClick={() => setStep(2)} className="w-full py-2 rounded-xl text-white text-xs font-semibold" style={{ background: PINK }}>
                  {L.next}
                </button>
              </div>
            )}

            {!loading && step === 2 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">{L.steps[1]}</div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                    <div className="text-2xl font-bold text-emerald-700 tabular-nums">{eligible.length}</div>
                    <div className="text-[11px] text-emerald-700 mt-0.5">{L.eligible}</div>
                  </div>
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                    <div className="text-2xl font-bold text-amber-700 tabular-nums">{blocked.length}</div>
                    <div className="text-[11px] text-amber-700 mt-0.5">{L.blockedT}</div>
                  </div>
                </div>
                {blocked.length > 0 && (
                  <div className="rounded-xl border border-gray-100 bg-gray-50 p-3 space-y-1.5">
                    {blocked.slice(0, 5).map((c) => (
                      <div key={c.candidate_staff_id} className="text-[10px] text-gray-600">
                        <span className="font-semibold text-gray-800">{c.name_en || c.name}</span>
                        {' - '}{c.blocked_reasons.join('; ')}
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-[10px] text-gray-500">
                  {eligible.length ? L.complianceOk : L.noCands}
                </p>
                <button onClick={() => setStep(3)} className="w-full py-2 rounded-xl text-white text-xs font-semibold" style={{ background: PINK }}>
                  {L.viewAi}
                </button>
              </div>
            )}

            {!loading && step === 3 && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">{L.steps[2]}</div>
                {eligible.length === 0 && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-[11px] text-amber-800">
                    {L.noCands}
                  </div>
                )}
                {eligible.map((c) => (
                  <div key={c.candidate_staff_id} className="bg-white border border-gray-200 rounded-xl p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold text-white flex-shrink-0"
                          style={{ background: PINK }}>
                          {(c.name_en || c.name || '?')[0]}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-gray-900">{c.name_en || c.name}</span>
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full text-white font-medium"
                              style={{ background: c.score >= 80 ? '#10B981' : '#F59E0B' }}>
                              #{c.rank_order} · {c.score} {L.score}
                            </span>
                          </div>
                          <div className="text-[10px] text-gray-500 mt-0.5">
                            {[c.rank, c.unit_name, ...c.reasons].filter(Boolean).join(' · ')}
                          </div>
                        </div>
                      </div>
                      <button disabled={busy === c.candidate_staff_id}
                        onClick={() => assign(c.candidate_staff_id, c.name_en || c.name)}
                        className="px-3 py-1.5 text-[10px] rounded-lg text-white font-medium flex-shrink-0 disabled:opacity-50"
                        style={{ background: PINK }}>
                        {L.assign}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!loading && step === 4 && outcome && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">{L.steps[3]}</div>
                <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-[11px] text-emerald-800">
                  {L.assignedSaved} - {L.assignedTo}{outcome.name}
                </div>
                <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-[11px] text-blue-800 space-y-1">
                  <div>{L.notify}</div>
                  <div className="text-[10px] text-blue-500">{L.chatPreviewNote}</div>
                </div>
                <div className="border border-gray-200 rounded-xl overflow-hidden">
                  <div className="px-3 py-2 border-b border-gray-100 flex items-center gap-2 bg-gray-50">
                    <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] text-white font-bold flex-shrink-0" style={{ background: PINK }}>
                      {outcome.name[0]}
                    </div>
                    <div>
                      <div className="text-[10px] font-semibold text-gray-800">{outcome.name}</div>
                      <div className="text-[8px] text-green-500">● {L.online}</div>
                    </div>
                  </div>
                  <div className="p-2.5 space-y-2 min-h-[80px]">
                    {chatMsgs.map((m, i) => (
                      <div key={i} className={`flex ${m.from === 'staff' ? 'justify-end' : 'justify-start'}`}>
                        <div className="max-w-[85%] px-2.5 py-1.5 rounded-xl text-[10px] leading-relaxed whitespace-pre-line"
                          style={{
                            background: m.from === 'system' ? '#f3f4f6' : PINK,
                            color: m.from === 'system' ? '#374151' : '#fff',
                            borderRadius: m.from === 'system' ? '4px 12px 12px 12px' : '12px 4px 12px 12px',
                          }}>
                          {m.text}
                        </div>
                      </div>
                    ))}
                  </div>
                  {chatPhase === 1 && (
                    <div className="p-2 border-t border-gray-100">
                      <button onClick={handleStaffReply} className="w-full py-1.5 text-[10px] rounded-lg text-white font-medium" style={{ background: '#10B981' }}>
                        {L.staffReplyBtn}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {!loading && step === 5 && outcome && (
              <div className="space-y-3">
                <div className="text-sm font-bold text-gray-900">{L.steps[4]}</div>
                <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-1.5 text-[11px] text-green-800">
                  <div className="font-semibold text-green-700">{L.resolvedT}</div>
                  <div>{L.assignedTo}{outcome.name}</div>
                  <div>{L.responseT}{outcome.minutes} min</div>
                  {outcome.toil > 0 && <div>{L.toil}{outcome.toil}h</div>}
                  <div>{L.notify}</div>
                </div>
                <button onClick={onClose} className="w-full py-2 rounded-xl text-white text-xs font-semibold" style={{ background: PINK }}>
                  {L.close}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ─── New incident form ───────────────────────────────────────────────────── */
function NewIncidentModal({ onClose, onCreated, isZH }: {
  onClose: () => void; onCreated: () => void; isZH: boolean
}) {
  const [staff, setStaff] = useState<ApiStaff[]>([])
  const [staffId, setStaffId] = useState('')
  const [type, setType] = useState('SL')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { api.listStaff().then(setStaff).catch(() => {}) }, [])

  const L = {
    title:  isZH ? '登記緊急請假' : 'Log an urgent absence',
    staff:  isZH ? '員工' : 'Staff',
    type:   isZH ? '類型' : 'Type',
    date:   isZH ? '日期' : 'Date',
    reason: isZH ? '原因' : 'Reason',
    submit: isZH ? '提交' : 'Submit',
    cancel: isZH ? '取消' : 'Cancel',
    pick:   isZH ? '請選擇員工' : 'Select a staff member',
  }

  async function submit() {
    if (!staffId) { setError(L.pick); return }
    setBusy(true)
    setError('')
    try {
      await api.createIncident({ staff_id: staffId, incident_type: type, date, reason })
      onCreated()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to log incident')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.45)' }}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 p-5 space-y-3">
        <div className="text-sm font-bold text-gray-900">{L.title}</div>
        {error && <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">{error}</div>}

        <label className="block text-[10px] text-gray-500">{L.staff}
          <select value={staffId} onChange={(e) => setStaffId(e.target.value)}
            className="mt-1 w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-700 outline-none">
            <option value="">{L.pick}</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>{s.name_en || s.name} ({s.rank})</option>
            ))}
          </select>
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block text-[10px] text-gray-500">{L.type}
            <select value={type} onChange={(e) => setType(e.target.value)}
              className="mt-1 w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-700 outline-none">
              {['SL', 'DSL', 'urgent', 'late'].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="block text-[10px] text-gray-500">{L.date}
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
              className="mt-1 w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-700 outline-none" />
          </label>
        </div>

        <label className="block text-[10px] text-gray-500">{L.reason}
          <input value={reason} onChange={(e) => setReason(e.target.value)}
            className="mt-1 w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs text-gray-700 outline-none" />
        </label>

        <div className="flex gap-2 pt-1">
          <button onClick={submit} disabled={busy}
            className="flex-1 py-2 rounded-xl text-white text-xs font-semibold disabled:opacity-50"
            style={{ background: PINK }}>
            {L.submit}
          </button>
          <button onClick={onClose}
            className="px-4 py-2 rounded-xl border border-gray-200 text-xs text-gray-600 hover:bg-gray-50">
            {L.cancel}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ─── Page ────────────────────────────────────────────────────────────────── */
export default function AlertPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [stats, setStats] = useState<IncidentStats | null>(null)
  const [resolved, setResolved] = useState<Incident[]>([])
  const [complianceRatePct, setComplianceRatePct] = useState<number | null>(null)
  const [handling, setHandling] = useState<string>('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    Promise.all([
      api.alerts(), api.incidentStats(), api.incidents({ status: 'resolved', limit: 6 }), api.dashboard(),
    ])
      .then(([a, s, r, d]) => {
        setAlerts(a); setStats(s); setResolved(r); setComplianceRatePct(d.kpis.compliance_rate_pct); setError('')
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load alerts'))
  }, [])

  useEffect(() => { load() }, [load])

  const L = {
    pageTitle:  isZH ? 'Alert 警報中心' : 'Alert Centre',
    newRequest: isZH ? '+ 登記請假' : '+ Log absence',
    activeTitle: isZH ? '實時警報' : 'Active Alerts',
    recentTitle: isZH ? '最近已處理事件' : 'Recently Resolved',
    distribTitle: isZH ? 'SL/DSL 事件分佈' : 'SL/DSL Distribution',
    resolvedBy: isZH ? '接更' : 'covered by',
    resolvedMin: isZH ? '分鐘完成處理' : 'min to resolve',
    resolved:   isZH ? '已處理' : 'Resolved',
    handle:     isZH ? '處理' : 'Handle',
    urgentBadge: isZH ? '緊急' : 'Urgent',
    normalBadge: isZH ? '一般' : 'Normal',
    cases:      isZH ? '宗' : 'cases',
    none:       isZH ? '目前沒有實時警報 ✓' : 'No active alerts right now ✓',
    noneResolved: isZH ? '本月未有已處理事件' : 'Nothing resolved yet this month',
    kpi: [
      isZH ? 'SL/DSL 總事件' : 'SL/DSL Events',
      isZH ? 'Emma AI 自動處理' : 'Auto-resolved by AI',
      isZH ? '平均響應時間' : 'Avg Response Time',
      isZH ? '未處理' : 'Open',
    ],
    subtitle: (n: number, m: string) =>
      isZH ? `${n} 個實時警報 · ${m} 實時監控中` : `${n} active alerts · ${m} live monitoring`,
    aiSummaryTitle: isZH ? 'Emma AI · 本月 Alert 分析' : 'Emma AI · This Month\'s Alert Analysis',
    aiResponse: isZH ? '平均響應時間' : 'Avg Response Time',
    aiResponseBefore: isZH ? '人手處理 45 min' : 'Manual: 45 min',
    aiCheck: isZH ? '合規核查' : 'Compliance Check',
    aiCheckBefore: isZH ? '人手核查' : 'Manual Check',
    aiCheckAfter: isZH ? 'AI 即時核查' : 'AI Instant Check',
    aiCompliance: isZH ? 'SWD 合規率' : 'SWD Compliance',
    aiComplianceBefore: isZH ? '人手追蹤' : 'Manual Tracking',
    aiComplianceAfter: isZH ? 'AI 自動監控' : 'AI Auto-monitoring',
  }

  const kpiCards = stats ? [
    { label: L.kpi[0], value: String(stats.total), unit: L.cases, color: PINK,
      sub: `${stats.month_start} → ${stats.month_end}` },
    { label: L.kpi[1], value: String(stats.auto_resolved), unit: L.cases, color: '#10b981',
      sub: `${stats.auto_resolved_pct}% ${isZH ? '自動解決' : 'auto-resolved'}` },
    { label: L.kpi[2], value: String(stats.avg_response_minutes), unit: 'min', color: '#f59e0b',
      sub: isZH ? '人手處理需 45min' : 'Manual handling: 45min' },
    { label: L.kpi[3], value: String(stats.open), unit: L.cases, color: '#6366f1',
      sub: isZH ? '待安排補更' : 'awaiting cover' },
  ] : []

  return (
    <div className="p-5 space-y-5">
      {handling && (
        <ResolutionModal incidentId={handling} isZH={isZH}
          onClose={() => setHandling('')} onResolved={load} />
      )}
      {creating && (
        <NewIncidentModal isZH={isZH} onClose={() => setCreating(false)} onCreated={load} />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{L.pageTitle}</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            {L.subtitle(alerts.length, stats?.month_start?.slice(0, 7) ?? '')}
          </p>
        </div>
        <button onClick={() => setCreating(true)}
          className="px-3 py-1.5 text-xs rounded-lg text-white font-medium"
          style={{ background: PINK }}
          onMouseEnter={(e) => (e.currentTarget.style.background = PINK_HOVER)}
          onMouseLeave={(e) => (e.currentTarget.style.background = PINK)}>
          {L.newRequest}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>
      )}

      {/* KPI */}
      <div className="grid grid-cols-4 gap-3">
        {kpiCards.map((c) => (
          <div key={c.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">{c.label}</div>
            <div className="flex items-end gap-0.5">
              <span className="text-[28px] font-bold tabular-nums leading-none" style={{ color: c.color }}>{c.value}</span>
              <span className="text-xs text-gray-400 mb-1">{c.unit}</span>
            </div>
            <div className="text-[10px] text-gray-400 mt-1">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Distribution */}
      {stats && stats.total > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-sm font-semibold text-gray-900 mb-3">{L.distribTitle}</div>
          <div className="space-y-2.5">
            {stats.distribution.map((d) => (
              <div key={d.incident_type} className="flex items-center gap-3">
                <span className="text-[11px] font-bold w-12 text-gray-700">{d.incident_type}</span>
                <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full"
                    style={{ width: `${d.pct}%`, background: TYPE_COLOR[d.incident_type] ?? '#6b7280' }} />
                </div>
                <span className="text-[10px] text-gray-500 w-16 text-right tabular-nums">
                  {d.count} {L.cases} · {d.pct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active alerts */}
      <div>
        <div className="text-sm font-semibold text-gray-900 mb-3">{L.activeTitle}</div>
        {alerts.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-xl p-6 text-center text-xs text-emerald-600">
            {L.none}
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.map((a) => (
              <div key={a.id} className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0 mt-0.5"
                      style={{ background: a.urgent ? '#FFE4E6' : '#FEF3C7' }}>
                      {KIND_ICON[a.kind]}
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-gray-900">{a.title}</div>
                      <div className="text-xs text-gray-500 mt-0.5">{a.detail}</div>
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        {a.unit_name && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{a.unit_name}</span>
                        )}
                        {a.date && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{a.date}</span>
                        )}
                        <span className="text-[10px] px-2 py-0.5 rounded-full text-white font-medium"
                          style={{ background: a.urgent ? PINK : '#F59E0B' }}>
                          {a.urgent ? L.urgentBadge : L.normalBadge}
                        </span>
                      </div>
                    </div>
                  </div>
                  {a.incident_id && (
                    <button onClick={() => setHandling(a.incident_id as string)}
                      className="px-3 py-1.5 text-xs rounded-lg text-white font-medium flex-shrink-0"
                      style={{ background: PINK }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = PINK_HOVER)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = PINK)}>
                      {L.handle}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recently resolved */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100">
          <div className="text-sm font-semibold text-gray-900">{L.recentTitle}</div>
        </div>
        {resolved.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-gray-400">{L.noneResolved}</div>
        ) : resolved.map((a) => (
          <div key={a.id} className="px-4 py-3 border-b border-gray-50 last:border-b-0 hover:bg-gray-50 flex items-center gap-3">
            <div className="w-9 h-8 rounded-full flex items-center justify-center text-[10px] font-bold text-white flex-shrink-0"
              style={{ background: TYPE_COLOR[a.incident_type] ?? PINK }}>
              {a.incident_type}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-gray-900">{a.name_en || a.name}</span>
                <span className="text-[9px] text-gray-400">{a.rank}</span>
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5">
                {[a.unit_name, a.shift_type, a.shift_window].filter(Boolean).join(' · ')}
              </div>
              <div className="text-[10px] text-emerald-600 font-medium mt-0.5">
                ✅ {L.resolvedBy} {a.replacement_name ?? '-'} · {a.resolution_minutes ?? '?'} {L.resolvedMin}
                {a.auto_resolved && ' · Emma AI'}
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-[10px] text-gray-400">{a.date}</div>
              <div className="text-[10px] font-semibold text-emerald-600 mt-0.5">{L.resolved}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Emma AI Summary */}
      {stats && (
        <div className="rounded-2xl p-5 text-white" style={{ background: 'linear-gradient(135deg, #1a1a2e, #2d2d5e)' }}>
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xl">🤖</span>
            <span className="text-sm font-bold">{L.aiSummaryTitle}</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl p-3" style={{ background: 'rgba(255,255,255,0.08)' }}>
              <div className="text-[9px] text-gray-400 tracking-wider mb-1.5">{L.aiResponse}</div>
              <div className="text-[10px] text-gray-300 line-through mb-0.5">{L.aiResponseBefore}</div>
              <div className="text-xs font-bold text-white">{stats.avg_response_minutes} min (AI)</div>
              <div className="text-[10px] font-semibold mt-1" style={{ color: '#34d399' }}>
                ↓ {Math.max(0, Math.round((45 - stats.avg_response_minutes) / 45 * 100))}%
              </div>
            </div>
            <div className="rounded-xl p-3" style={{ background: 'rgba(255,255,255,0.08)' }}>
              <div className="text-[9px] text-gray-400 tracking-wider mb-1.5">{L.aiCheck}</div>
              <div className="text-[10px] text-gray-300 line-through mb-0.5">{L.aiCheckBefore}</div>
              <div className="text-xs font-bold text-white">{L.aiCheckAfter}</div>
              <div className="text-[10px] font-semibold mt-1" style={{ color: '#34d399' }}>
                {stats.auto_resolved_pct}% {isZH ? '自動解決' : 'auto-resolved'}
              </div>
            </div>
            <div className="rounded-xl p-3" style={{ background: 'rgba(255,255,255,0.08)' }}>
              <div className="text-[9px] text-gray-400 tracking-wider mb-1.5">{L.aiCompliance}</div>
              <div className="text-[10px] text-gray-300 line-through mb-0.5">{L.aiComplianceBefore}</div>
              <div className="text-xs font-bold text-white">{L.aiComplianceAfter}</div>
              <div className="text-[10px] font-semibold mt-1" style={{ color: '#34d399' }}>
                {complianceRatePct !== null ? `${complianceRatePct}%` : '-'} {isZH ? '達標率' : 'compliance rate'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
