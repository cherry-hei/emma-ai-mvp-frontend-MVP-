'use client'

/** Emma AI workspace: chat-first access to evidence-bound Compliance Q&A and Emergency SL suggestions. */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import ComplianceQaPanel from '@/components/compliance/ComplianceQaPanel'
import { api } from '@/lib/api'
import type { EmergencyAiSuggestion, Incident, ReplacementCandidate } from '@/lib/apiTypes'

type AiMode = 'compliance' | 'emergency'

function EmmaMark() {
  return (
    <span className="flex h-9 w-9 flex-col items-center justify-center gap-[3px] rounded-xl bg-gradient-to-br from-[#E8187A] to-[#f28f9e] shadow-[0_10px_24px_-14px_rgba(232,24,122,0.9)]" aria-hidden>
      <span className="h-[2px] w-4 rounded-full bg-white" />
      <span className="ml-1 h-[2px] w-3.5 rounded-full bg-white" />
      <span className="ml-2 h-[2px] w-3 rounded-full bg-white" />
    </span>
  )
}

function AssistantBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <EmmaMark />
      <div className="max-w-3xl rounded-2xl rounded-tl-md border border-rose-100 bg-white px-4 py-3 text-sm leading-relaxed text-slate-700 shadow-[0_16px_42px_-32px_rgba(232,24,122,0.55)]">
        {children}
      </div>
    </div>
  )
}

function EmergencyChat({ isZH }: { isZH: boolean }) {
  const router = useRouter()
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [suggestion, setSuggestion] = useState<EmergencyAiSuggestion | null>(null)
  const [candidates, setCandidates] = useState<ReplacementCandidate[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const loadIncidents = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const rows = await api.incidents({ limit: 100 })
      const openSl = rows.filter((row) => !row.resolved && row.status !== 'cancelled' && (row.incident_type === 'SL' || row.incident_type === 'DSL'))
      setIncidents(openSl)
      setSelectedId((current) => current && openSl.some((row) => row.id === current) ? current : openSl[0]?.id || '')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load incidents')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadIncidents() }, [loadIncidents])

  const selected = useMemo(() => incidents.find((row) => row.id === selectedId), [incidents, selectedId])
  const candidateById = useMemo(() => new Map(candidates.map((row) => [row.candidate_staff_id, row])), [candidates])

  async function runSuggestion() {
    if (!selectedId) return
    setRunning(true)
    setError('')
    setSuggestion(null)
    try {
      const [evidence, answer] = await Promise.all([
        api.replacementCandidates(selectedId, { complianceChecked: false, refresh: true }),
        api.incidentAiSuggestion(selectedId),
      ])
      setCandidates(evidence)
      setSuggestion(answer)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not prepare the suggestion')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-5">
      <AssistantBubble>
        {isZH
          ? '我會先讀取已建立的病假事件，再用deterministic eligibility及可審計證據整理替補建議。更表只會在員工接受及院長批准後更新。'
          : 'I first read an existing sick-leave incident, then explain the deterministic eligibility evidence. The roster changes only after staff acceptance and manager approval.'}
      </AssistantBubble>

      <div className="ml-auto max-w-3xl rounded-2xl rounded-tr-md bg-gradient-to-br from-[#E8187A] to-[#f28f9e] px-4 py-3 text-sm text-white shadow-[0_18px_42px_-28px_rgba(232,24,122,0.9)]">
        <label className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.16em] text-white/75">
          {isZH ? '選擇現有突發病假事件' : 'Choose an existing sick-leave incident'}
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <select
            value={selectedId}
            onChange={(event) => { setSelectedId(event.target.value); setSuggestion(null); setCandidates([]) }}
            disabled={loading || running}
            className="min-h-11 flex-1 rounded-xl border border-white/30 bg-white px-3 text-sm text-slate-800 outline-none ring-white/50 focus:ring-2 disabled:opacity-60"
          >
            {!incidents.length && <option value="">{loading ? (isZH ? '載入中…' : 'Loading…') : (isZH ? '暫未有未處理SL事件' : 'No open SL incident')}</option>}
            {incidents.map((row) => (
              <option key={row.id} value={row.id}>
                {row.date} · {row.name_en || row.name || row.staff_id || row.id} · {row.shift_type || row.shift_id || 'shift'}
              </option>
            ))}
          </select>
          <button
            onClick={runSuggestion}
            disabled={!selectedId || running}
            className="min-h-11 rounded-xl bg-slate-950 px-5 text-xs font-bold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {running ? (isZH ? '整理證據中…' : 'Reading evidence…') : (isZH ? '請Emma建議' : 'Ask Emma')}
          </button>
        </div>
        {selected && <p className="mt-2 text-[10px] text-white/80">{selected.reason || (isZH ? '不顯示病歷或敏感資料' : 'No medical or sensitive detail is displayed')}</p>}
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">{error}</div>}

      {!loading && !incidents.length && (
        <AssistantBubble>
          <p>{isZH ? '目前沒有可分析的未處理SL事件。請先在警報中心建立或確認一個synthetic事件。' : 'There is no open SL incident to analyse. Create or confirm a synthetic incident in Alert Centre first.'}</p>
          <button onClick={() => router.push('/alert')} className="mt-3 rounded-lg bg-slate-950 px-3 py-2 text-xs font-semibold text-white">
            {isZH ? '前往警報中心' : 'Open Alert Centre'}
          </button>
        </AssistantBubble>
      )}

      {suggestion && (
        <AssistantBubble>
          <div className="flex flex-wrap items-center gap-2">
            <b className="text-slate-950">{isZH ? '替補建議已準備' : 'Replacement suggestion ready'}</b>
            <span className={`rounded-full px-2 py-1 font-mono text-[9px] font-bold ${suggestion.degraded ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
              {suggestion.degraded ? (isZH ? 'deterministic降級' : 'deterministic fallback') : (suggestion.provider || 'provider ready')}
            </span>
          </div>
          <p className="mt-2">{suggestion.reason || (isZH ? '建議依據已通過deterministic檢查。' : 'The recommendation is bounded by deterministic checks.')}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-rose-50 p-3">
              <div className="text-[10px] uppercase tracking-wider text-rose-500">{isZH ? '首選' : 'Top pick'}</div>
              <div className="mt-1 font-semibold text-slate-900">{suggestion.pick_alias || suggestion.pick || (isZH ? '沒有合資格人選' : 'No eligible candidate')}</div>
              <div className="mt-1 text-[10px] text-slate-500">{isZH ? '合資格人數' : 'Eligible'}: {suggestion.eligible_count}</div>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <div className="text-[10px] uppercase tracking-wider text-slate-400">{isZH ? '證據排序' : 'Evidence ranking'}</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {suggestion.ranking.length ? suggestion.ranking.map((id, index) => (
                  <span key={`${id}-${index}`} className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] text-slate-700">
                    {index + 1}. {candidateById.get(id)?.name_en || candidateById.get(id)?.name || id}
                  </span>
                )) : <span className="text-xs text-slate-400">—</span>}
              </div>
            </div>
          </div>
          {suggestion.failures.length > 0 && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[10px] text-amber-700">{suggestion.failures.join(' · ')}</div>}
          <button onClick={() => router.push('/alert')} className="mt-4 rounded-xl bg-[#E8187A] px-4 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-[#c9156a]">
            {isZH ? '前往警報中心發邀請及批准' : 'Open Alert Centre to send and approve offers'}
          </button>
        </AssistantBubble>
      )}
    </div>
  )
}

export default function EmmaAiWorkspace({ isZH }: { isZH: boolean }) {
  const [mode, setMode] = useState<AiMode>('compliance')
  const [rosterContext, setRosterContext] = useState({ date: '', versionId: '', rule: '', question: '' })
  const hkDate = useMemo(() => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Hong_Kong' }).format(new Date()), [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('mode') === 'emergency') setMode('emergency')
    if (params.get('mode') === 'compliance') setMode('compliance')
    setRosterContext({
      date: params.get('date') || '',
      versionId: params.get('roster_version_id') || '',
      rule: params.get('rule') || '',
      question: params.get('question') || '',
    })
  }, [])

  return (
    <div className="min-h-full bg-[radial-gradient(circle_at_top_right,rgba(232,24,122,0.08),transparent_32%),linear-gradient(180deg,#fff_0%,#fff8fb_100%)] p-4 md:p-6">
      <div className="mx-auto max-w-5xl space-y-5">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-center gap-3">
            <EmmaMark />
            <div>
              <h1 className="text-2xl font-black tracking-tight text-slate-950">Emma AI</h1>
              <p className="mt-0.5 text-xs text-slate-500">{isZH ? '院舍專用AI排更與合規助手' : 'Care-home scheduling and compliance assistant'}</p>
            </div>
          </div>
          <div className="inline-flex w-fit rounded-xl border border-rose-100 bg-white p-1 shadow-sm">
            <button onClick={() => setMode('compliance')} className={`rounded-lg px-3 py-2 text-xs font-bold transition ${mode === 'compliance' ? 'bg-[#E8187A] text-white shadow-sm' : 'text-slate-500 hover:bg-rose-50'}`}>
              {isZH ? '合規問答' : 'Compliance Q&A'}
            </button>
            <button onClick={() => setMode('emergency')} className={`rounded-lg px-3 py-2 text-xs font-bold transition ${mode === 'emergency' ? 'bg-slate-950 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-50'}`}>
              {isZH ? '緊急病假替補' : 'Emergency SL Cover'}
            </button>
          </div>
        </header>

        <section className="rounded-[26px] border border-rose-100/80 bg-white/90 p-4 shadow-[0_28px_70px_-48px_rgba(232,24,122,0.65)] backdrop-blur-sm md:p-6">
          {mode === 'compliance' ? (
            <div className="space-y-5">
              {rosterContext.rule && (
                <div className="rounded-xl border border-sky-100 bg-sky-50 px-4 py-3 text-[11px] text-sky-800">
                  <span className="font-bold">{isZH ? '更表規則內容' : 'Roster rule context'}:</span>{' '}
                  {rosterContext.rule}{rosterContext.date ? ` · ${rosterContext.date}` : ''}
                </div>
              )}
              <AssistantBubble>
                {isZH
                  ? '問我現時更表的人手比例、違規分鐘、適用門檻或驗證結果。我只會根據deterministic rule evidence解釋，不會自己創作法規。'
                  : 'Ask about staffing ratios, breach minutes, thresholds or roster validation. I explain deterministic rule evidence and do not invent rules.'}
              </AssistantBubble>
              <ComplianceQaPanel
                isZH={isZH}
                date={rosterContext.date || hkDate}
                rosterVersionId={rosterContext.versionId}
                initialQuestion={rosterContext.question}
              />
            </div>
          ) : <EmergencyChat isZH={isZH} />}
        </section>

        <p className="px-2 text-[10px] leading-relaxed text-slate-400">
          {isZH
            ? 'Emma AI只負責解析及解釋；資格、合規及更表更新由deterministic backend和院長最終批准決定。請勿在對話輸入姓名、電話、HKID、病歷或其他敏感資料。'
            : 'Emma AI parses and explains; deterministic services and final manager approval control eligibility, compliance and roster changes. Do not enter names, phone numbers, HKID, medical or other sensitive data.'}
        </p>
      </div>
    </div>
  )
}
