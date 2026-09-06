'use client'

// Design: Emma clinical warmth — evidence first, pink only for decisive actions,
// compact bilingual operations UI, and no simulated state presented as real.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import type {
  EmergencyAiSuggestion, Incident, ReplacementCandidate, ReplacementOffer,
} from '@/lib/apiTypes'

const PINK = '#E8187A'

const STATUS_STYLE: Record<string, string> = {
  pending: 'bg-sky-50 text-sky-700 border-sky-200',
  accepted: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  declined: 'bg-gray-50 text-gray-600 border-gray-200',
  approved: 'bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200',
  withdrawn: 'bg-gray-50 text-gray-500 border-gray-200',
  superseded: 'bg-gray-50 text-gray-500 border-gray-200',
}

function formatStatus(status: string, isZH: boolean) {
  const zh: Record<string, string> = {
    pending: '等待回覆', accepted: '員工接受', declined: '員工拒絕',
    approved: '院長批准', withdrawn: '已撤回', superseded: '其他人已補更',
  }
  const en: Record<string, string> = {
    pending: 'Awaiting reply', accepted: 'Accepted by staff', declined: 'Declined',
    approved: 'Approved', withdrawn: 'Withdrawn', superseded: 'Closed — another approved',
  }
  return (isZH ? zh : en)[status] ?? status
}

export default function EmergencyResolutionModal({ incidentId, onClose, onResolved, isZH }: {
  incidentId: string
  onClose: () => void
  onResolved: () => void
  isZH: boolean
}) {
  const [incident, setIncident] = useState<Incident | null>(null)
  const [candidates, setCandidates] = useState<ReplacementCandidate[]>([])
  const [suggestion, setSuggestion] = useState<EmergencyAiSuggestion | null>(null)
  const [offers, setOffers] = useState<ReplacementOffer[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const loadOffers = useCallback(async () => {
    const rows = await api.replacementOffers(incidentId)
    setOffers(rows)
    return rows
  }, [incidentId])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [allIncidents, candidateRows, offerRows] = await Promise.all([
        api.incidents({ limit: 200 }),
        api.replacementCandidates(incidentId, { complianceChecked: false, refresh: true }),
        api.replacementOffers(incidentId),
      ])
      setIncident(allIncidents.find((row) => row.id === incidentId) ?? null)
      setCandidates(candidateRows)
      setOffers(offerRows)
      setSelected((current) => current.length ? current : candidateRows.filter((c) => c.compliance_ok).slice(0, 3).map((c) => c.candidate_staff_id))
      try {
        setSuggestion(await api.incidentAiSuggestion(incidentId))
      } catch {
        setSuggestion(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load replacement workflow')
    } finally {
      setLoading(false)
    }
  }, [incidentId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!offers.some((offer) => offer.status === 'pending' || offer.status === 'accepted')) return
    const timer = window.setInterval(() => {
      loadOffers().catch(() => {})
    }, 5000)
    return () => window.clearInterval(timer)
  }, [offers, loadOffers])

  const eligible = useMemo(() => candidates.filter((c) => c.compliance_ok), [candidates])
  const blocked = useMemo(() => candidates.filter((c) => !c.compliance_ok), [candidates])
  const candidateById = useMemo(() => new Map(candidates.map((c) => [c.candidate_staff_id, c])), [candidates])
  const activeOffers = offers.filter((offer) => offer.status !== 'withdrawn' && offer.status !== 'superseded')
  const approved = offers.find((offer) => offer.status === 'approved')

  const L = {
    title: isZH ? '緊急病假替補' : 'Emergency Sick Leave Cover',
    sub: isZH ? '規則引擎篩選 · AI只解釋 · 員工回覆 · 院長最後批准' : 'Rules decide eligibility · AI explains · Staff responds · Manager approves',
    eligible: isZH ? '合規候選人' : 'Eligible candidates',
    blocked: isZH ? '規則排除' : 'Excluded by rules',
    ai: isZH ? 'AI 建議解釋' : 'AI-assisted explanation',
    select: isZH ? '選擇要通知的員工' : 'Choose staff to notify',
    note: isZH ? '通知備註（不要輸入病歷或其他敏感資料）' : 'Offer note — do not include medical or other sensitive data',
    send: isZH ? `發送 ${selected.length} 個接更邀請` : `Send ${selected.length} cover offer${selected.length === 1 ? '' : 's'}`,
    offers: isZH ? '員工回覆狀態' : 'Staff response status',
    refresh: isZH ? '立即刷新' : 'Refresh now',
    approve: isZH ? '院長批准' : 'Manager approve',
    withdraw: isZH ? '撤回' : 'Withdraw',
    noOffer: isZH ? '尚未發送邀請。更表只會在員工接受並由院長批准後更新。' : 'No offers sent. The roster changes only after staff accepts and the manager approves.',
    success: isZH ? '替補已批准；其他邀請已自動關閉，更表及審計紀錄由backend更新。' : 'Cover approved. Other offers were closed and the backend updated the roster and audit trail.',
    close: isZH ? '關閉' : 'Close',
    degraded: isZH ? '目前使用deterministic降級解釋' : 'Deterministic degraded explanation',
    provider: isZH ? '解釋來源' : 'Explanation source',
    noReason: isZH ? '候選次序沿用規則引擎分數。' : 'Candidate order follows the deterministic score.',
  }

  function toggleCandidate(id: string) {
    if (offers.some((offer) => offer.status === 'pending' || offer.status === 'accepted' || offer.status === 'approved')) return
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  async function sendOffers() {
    if (!selected.length) return
    setBusy('send')
    setError('')
    setSuccess('')
    try {
      await api.createReplacementOffers(incidentId, { staff_ids: selected, note: note.trim() || undefined })
      await loadOffers()
      setSuccess(isZH ? '邀請已送到Staff PWA通知列表。' : 'Offers were sent to the Staff PWA notification feed.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send offers')
    } finally {
      setBusy('')
    }
  }

  async function approveOffer(offer: ReplacementOffer) {
    setBusy(offer.id)
    setError('')
    setSuccess('')
    try {
      await api.approveReplacementOffer(offer.id)
      await loadOffers()
      setSuccess(L.success)
      onResolved()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not approve this offer')
    } finally {
      setBusy('')
    }
  }

  async function withdrawOffer(offer: ReplacementOffer) {
    setBusy(offer.id)
    setError('')
    try {
      await api.withdrawReplacementOffer(offer.id)
      await loadOffers()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not withdraw this offer')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3" style={{ background: 'rgba(15,23,42,.55)' }}>
      <div className="flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between border-b border-gray-100 px-5 py-4">
          <div>
            <h2 className="text-base font-bold text-gray-900">{L.title}</h2>
            <p className="mt-0.5 text-[11px] text-gray-500">{L.sub}</p>
          </div>
          <button aria-label={L.close} onClick={onClose} className="text-xl leading-none text-gray-400 hover:text-gray-700">×</button>
        </div>

        <div className="overflow-y-auto p-5">
          {error && <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">{error}</div>}
          {success && <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-700">{success}</div>}
          {loading && <div className="py-12 text-center text-sm text-gray-400">Loading…</div>}

          {!loading && incident && (
            <div className="space-y-5">
              <div className="grid gap-3 rounded-xl border border-rose-100 bg-rose-50/60 p-4 text-xs text-gray-700 sm:grid-cols-4">
                <div><div className="text-[9px] uppercase tracking-wider text-gray-400">Staff</div><b>{incident.name_en || incident.name}</b></div>
                <div><div className="text-[9px] uppercase tracking-wider text-gray-400">Date</div><b>{incident.date}</b></div>
                <div><div className="text-[9px] uppercase tracking-wider text-gray-400">Shift</div><b>{incident.shift_type || '-'} {incident.shift_window || ''}</b></div>
                <div><div className="text-[9px] uppercase tracking-wider text-gray-400">Incident</div><b>{incident.incident_type}</b></div>
              </div>

              <div className="grid gap-4 lg:grid-cols-[1.45fr_.85fr]">
                <section className="rounded-xl border border-gray-200 bg-white p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-gray-900">{L.select}</h3>
                      <p className="text-[10px] text-gray-500">{eligible.length} {L.eligible} · {blocked.length} {L.blocked}</p>
                    </div>
                    {approved && <span className="rounded-full border border-fuchsia-200 bg-fuchsia-50 px-2 py-1 text-[10px] font-bold text-fuchsia-700">{formatStatus('approved', isZH)}</span>}
                  </div>
                  <div className="space-y-2">
                    {eligible.map((candidate) => {
                      const checked = selected.includes(candidate.candidate_staff_id)
                      const locked = activeOffers.length > 0
                      return (
                        <label key={candidate.candidate_staff_id} className={`flex items-start gap-3 rounded-xl border p-3 ${checked ? 'border-pink-200 bg-pink-50/50' : 'border-gray-200 bg-white'} ${locked ? 'cursor-default' : 'cursor-pointer'}`}>
                          <input type="checkbox" checked={checked} disabled={locked} onChange={() => toggleCandidate(candidate.candidate_staff_id)} className="mt-1 h-4 w-4 accent-pink-600" />
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <b className="text-xs text-gray-900">{candidate.name_en || candidate.name}</b>
                              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[9px] text-gray-600">#{candidate.rank_order} · {candidate.score} pts</span>
                              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-semibold text-emerald-700">✓ {candidate.rank}</span>
                            </div>
                            <p className="mt-1 text-[10px] leading-relaxed text-gray-500">{candidate.reasons.join(' · ') || L.noReason}</p>
                          </div>
                        </label>
                      )
                    })}
                    {!eligible.length && <div className="rounded-xl bg-amber-50 p-4 text-xs text-amber-800">{isZH ? '沒有合規內部候選，請由院長啟動人工升級流程。' : 'No compliant internal candidate. Start the manager escalation process.'}</div>}
                  </div>
                  {blocked.length > 0 && (
                    <details className="mt-3 rounded-xl border border-gray-100 bg-gray-50 p-3">
                      <summary className="cursor-pointer text-[10px] font-semibold text-gray-600">{L.blocked} ({blocked.length})</summary>
                      <div className="mt-2 space-y-1">
                        {blocked.map((candidate) => <p key={candidate.candidate_staff_id} className="text-[10px] text-gray-500"><b>{candidate.name_en || candidate.name}</b> — {candidate.blocked_reasons.join('; ')}</p>)}
                      </div>
                    </details>
                  )}
                </section>

                <section className="rounded-xl border border-slate-200 bg-slate-950 p-4 text-white">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-bold">{L.ai}</h3>
                    <span className="rounded-full bg-white/10 px-2 py-1 text-[9px] text-slate-200">{suggestion?.provider || 'deterministic'}</span>
                  </div>
                  <p className="mt-3 text-xs leading-relaxed text-slate-200">{suggestion?.reason || L.noReason}</p>
                  <div className="mt-4 space-y-2 text-[10px] text-slate-300">
                    <div>{L.provider}: <b className="text-white">{suggestion?.provider || 'offline'}</b></div>
                    <div>{isZH ? '符合資格人數' : 'Eligible count'}: <b className="text-white">{suggestion?.eligible_count ?? eligible.length}</b></div>
                    {(suggestion?.degraded || !suggestion?.explained) && <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-2 text-amber-200">{L.degraded}</div>}
                  </div>
                </section>
              </div>

              {!activeOffers.length && !approved && (
                <section className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                  <label className="block text-[10px] font-semibold text-gray-600">{L.note}
                    <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2} className="mt-2 w-full rounded-xl border border-gray-200 bg-white p-3 text-xs text-gray-800 outline-none focus:border-pink-300" />
                  </label>
                  <button onClick={sendOffers} disabled={!selected.length || busy === 'send'} className="mt-3 w-full rounded-xl py-2.5 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-40" style={{ background: PINK }}>
                    {busy === 'send' ? '…' : L.send}
                  </button>
                </section>
              )}

              <section className="rounded-xl border border-gray-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-bold text-gray-900">{L.offers}</h3>
                  <button onClick={() => loadOffers().catch((e) => setError(e instanceof Error ? e.message : 'Refresh failed'))} className="rounded-lg border border-gray-200 px-3 py-1.5 text-[10px] font-semibold text-gray-600 hover:bg-gray-50">{L.refresh}</button>
                </div>
                {!offers.length ? <p className="text-xs text-gray-500">{L.noOffer}</p> : (
                  <div className="space-y-2">
                    {offers.map((offer) => {
                      const candidate = candidateById.get(offer.offered_staff_id)
                      return (
                        <div key={offer.id} className="flex flex-col gap-3 rounded-xl border border-gray-200 p-3 sm:flex-row sm:items-center">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <b className="text-xs text-gray-900">{candidate?.name_en || candidate?.name || offer.offered_staff_id}</b>
                              <span className={`rounded-full border px-2 py-0.5 text-[9px] font-bold ${STATUS_STYLE[offer.status] || STATUS_STYLE.pending}`}>{formatStatus(offer.status, isZH)}</span>
                            </div>
                            <p className="mt-1 text-[10px] text-gray-500">{offer.response_note || offer.note || (isZH ? '未有備註' : 'No note')}</p>
                          </div>
                          <div className="flex gap-2">
                            {offer.status === 'accepted' && <button onClick={() => approveOffer(offer)} disabled={busy === offer.id} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-[10px] font-bold text-white disabled:opacity-50">{L.approve}</button>}
                            {(offer.status === 'pending' || offer.status === 'accepted') && <button onClick={() => withdrawOffer(offer)} disabled={busy === offer.id} className="rounded-lg border border-gray-200 px-3 py-1.5 text-[10px] font-semibold text-gray-600 disabled:opacity-50">{L.withdraw}</button>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </section>
            </div>
          )}
        </div>

        <div className="border-t border-gray-100 px-5 py-3 text-right">
          <button onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-xs font-semibold text-gray-600 hover:bg-gray-50">{L.close}</button>
        </div>
      </div>
    </div>
  )
}
