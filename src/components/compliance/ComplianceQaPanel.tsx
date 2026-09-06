'use client'

// Design: Emma clinical warmth — the deterministic decision is visually primary;
// model wording is secondary and every unsupported/degraded state is explicit.
import { useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import type { AiStatus, ComplianceQaAnswer } from '@/lib/apiTypes'

const PINK = '#E8187A'

const VERDICT_STYLE: Record<string, string> = {
  compliant: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  not_compliant: 'border-rose-200 bg-rose-50 text-rose-700',
  no_data: 'border-gray-200 bg-gray-50 text-gray-600',
  unsupported: 'border-amber-200 bg-amber-50 text-amber-800',
  needs_detail: 'border-sky-200 bg-sky-50 text-sky-700',
}

function valueSummary(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? '' : 's'}`
  if (typeof value === 'object') return `${Object.keys(value as Record<string, unknown>).length} fields`
  return String(value)
}

export default function ComplianceQaPanel({ isZH, date, rosterVersionId }: {
  isZH: boolean
  date: string
  rosterVersionId: string
}) {
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<ComplianceQaAnswer | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.aiStatus().then(setStatus).catch(() => setStatus(null))
  }, [])

  const prompts = isZH ? [
    `我哋喺${date || '今日'}嘅人手比例合規嗎？`,
    `我哋喺${date || '今日'}有幾多分鐘違反人手要求？`,
    '現時有冇員工證書即將到期？',
    '目前選擇嘅更表有冇hard violations？',
  ] : [
    `Does staffing meet every ratio on ${date || 'today'}?`,
    `How many breach minutes are there on ${date || 'today'}?`,
    'Are any staff certificates expiring?',
    'Does the selected roster have any hard violations?',
  ]

  const factRows = useMemo(() => answer ? Object.entries(answer.facts || {}) : [], [answer])
  const verdictLabel = (value: string) => {
    const zh: Record<string, string> = { compliant: '合規', not_compliant: '不合規', no_data: '未有資料', unsupported: '暫不支援', needs_detail: '需要更多資料' }
    const en: Record<string, string> = { compliant: 'Compliant', not_compliant: 'Not compliant', no_data: 'No data', unsupported: 'Unsupported', needs_detail: 'Needs detail' }
    return (isZH ? zh : en)[value] || value
  }

  async function submit(nextQuestion?: string) {
    const text = (nextQuestion ?? question).trim()
    if (!text) return
    setQuestion(text)
    setBusy(true)
    setError('')
    setAnswer(null)
    try {
      const result = await api.complianceQa({
        question: text,
        date: date || undefined,
        roster_version_id: rosterVersionId || undefined,
      })
      setAnswer(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not answer this question')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(330px,.85fr)]">
      <section className="rounded-2xl border border-gray-200 bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-gray-900">{isZH ? '問Emma合規問題' : 'Ask Emma about compliance'}</h2>
            <p className="mt-1 max-w-2xl text-[11px] leading-relaxed text-gray-500">
              {isZH ? '規則引擎先決定結論；AI只會把同一份證據解釋成自然語言，不會自行修改合規結果。' : 'The rules engine decides the verdict first. AI may explain the same evidence, but cannot change the compliance result.'}
            </p>
          </div>
          <span className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-[9px] font-semibold text-gray-600">
            {status?.providers?.length ? status.providers.join(' → ') : (isZH ? 'deterministic模式' : 'Deterministic mode')}
          </span>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {prompts.map((prompt) => (
            <button key={prompt} onClick={() => submit(prompt)} disabled={busy} className="rounded-full border border-pink-100 bg-pink-50 px-3 py-1.5 text-[10px] font-medium text-pink-700 hover:border-pink-200 disabled:opacity-50">
              {prompt}
            </button>
          ))}
        </div>

        <label className="mt-4 block text-[10px] font-semibold text-gray-600">
          {isZH ? '問題' : 'Question'}
          <textarea value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} rows={5}
            placeholder={isZH ? '例如：今日早更護士人手比例是否合規？' : 'For example: Does the morning nursing ratio meet requirements today?'}
            className="mt-2 w-full resize-y rounded-xl border border-gray-200 bg-white p-3 text-sm leading-relaxed text-gray-900 outline-none focus:border-pink-300 focus:ring-2 focus:ring-pink-100" />
        </label>
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-[10px] text-gray-400">{isZH ? `日期：${date || '未選'} · 更表版本：${rosterVersionId ? '已選' : '未選'}` : `Date: ${date || 'not selected'} · Roster version: ${rosterVersionId ? 'selected' : 'not selected'}`}</p>
          <button onClick={() => submit()} disabled={busy || !question.trim()} className="rounded-xl px-5 py-2.5 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-40" style={{ background: PINK }}>
            {busy ? (isZH ? '核對證據中…' : 'Checking evidence…') : (isZH ? '提交問題' : 'Ask question')}
          </button>
        </div>
        {error && <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">{error}</div>}
      </section>

      <section className="min-h-[360px] rounded-2xl border border-gray-200 bg-slate-950 p-5 text-white">
        {!answer ? (
          <div className="flex h-full min-h-[320px] flex-col justify-between">
            <div>
              <div className="text-xs font-bold text-white">{isZH ? '回答及證據' : 'Answer and evidence'}</div>
              <p className="mt-3 text-xs leading-relaxed text-slate-400">{isZH ? '選擇上面的例子或輸入問題。系統只會回答已支援的四類檢查：人手比例、違規分鐘、證書提示及更表驗證。' : 'Choose an example or type a question. The current supported checks are staffing ratio, breach minutes, certificate thresholds and roster validation.'}</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-[10px] leading-relaxed text-slate-400">
              {isZH ? '如果問題超出範圍，系統會顯示「暫不支援」，而不是猜答案。' : 'Out-of-scope questions return Unsupported instead of a guessed answer.'}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold ${VERDICT_STYLE[answer.verdict] || VERDICT_STYLE.no_data}`}>{verdictLabel(answer.verdict)}</span>
              <span className="text-[9px] text-slate-400">{answer.intent}</span>
            </div>
            <p className="text-sm leading-7 text-white">{answer.answer}</p>
            {(answer.degraded || !answer.explained) && (
              <div className="rounded-xl border border-amber-400/25 bg-amber-400/10 p-3 text-[10px] leading-relaxed text-amber-200">
                {isZH ? 'AI解釋現時不可用或被安全檢查拒絕；以上答案直接來自deterministic evidence。' : 'AI wording was unavailable or rejected by a safety check. The answer above comes directly from deterministic evidence.'}
              </div>
            )}
            {!!answer.missing.length && <div className="rounded-xl border border-sky-400/20 bg-sky-400/10 p-3 text-[10px] text-sky-200">{isZH ? '尚欠資料：' : 'Missing: '}{answer.missing.join(', ')}</div>}
            <div>
              <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">{isZH ? '證據摘要' : 'Evidence summary'}</div>
              <div className="grid grid-cols-2 gap-2">
                {factRows.map(([key, value]) => (
                  <div key={key} className="rounded-lg border border-white/10 bg-white/5 p-2.5">
                    <div className="truncate text-[9px] text-slate-400">{key}</div>
                    <div className="mt-1 break-words text-[11px] font-semibold text-white">{valueSummary(value)}</div>
                  </div>
                ))}
                {!factRows.length && <div className="col-span-2 text-[10px] text-slate-500">—</div>}
              </div>
            </div>
            <div className="border-t border-white/10 pt-3 text-[9px] text-slate-400">
              {isZH ? '來源：' : 'Provider: '}{answer.provider || 'deterministic'} · {answer.explained ? (isZH ? 'AI已解釋' : 'AI phrasing used') : (isZH ? '原始證據答案' : 'Evidence-only answer')}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
