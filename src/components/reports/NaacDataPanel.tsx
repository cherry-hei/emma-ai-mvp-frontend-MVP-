'use client'

// Design: Emma clinical warmth — operational controls are explicit, destructive
// writes require a second confirmation, and residency gates are impossible to miss.
import { useEffect, useMemo, useState } from 'react'
import { api, downloadReportFile } from '@/lib/api'
import type { ImportJob, PeriodOut } from '@/lib/apiTypes'

const PINK = '#E8187A'

export default function NaacDataPanel({ isZH }: { isZH: boolean }) {
  const [periods, setPeriods] = useState<PeriodOut[]>([])
  const [periodId, setPeriodId] = useState('')
  const [layouts, setLayouts] = useState<string[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [variant, setVariant] = useState<'before' | 'after'>('after')
  const [syntheticConfirmed, setSyntheticConfirmed] = useState(false)
  const [result, setResult] = useState<ImportJob | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.rosterPeriods().then((rows) => {
      setPeriods(rows)
      setPeriodId(rows[0]?.id || '')
    }).catch(() => {})
    api.importLayouts().then((rows) => setLayouts(rows.map((row) => row.layout))).catch(() => {})
  }, [])

  const issues = result?.issues || []
  const blocking = useMemo(() => issues.filter((issue) => ['error', 'fatal'].includes((issue.severity || '').toLowerCase())), [issues])
  const warnings = useMemo(() => issues.filter((issue) => (issue.severity || '').toLowerCase() === 'warning'), [issues])

  async function runImport(mode: 'validate' | 'commit') {
    if (!file || !syntheticConfirmed) return
    if (mode === 'commit' && !window.confirm(isZH ? '確認把這份synthetic／Care Home B workbook寫入draft roster？真實NAAC資料目前禁止上載。' : 'Commit this synthetic／Care Home B workbook as a draft roster? Real NAAC data is currently prohibited.')) return
    setBusy(mode)
    setError('')
    try {
      setResult(await api.importRosterExcel(file, mode, {
        variant,
        versionLabel: `UI ${mode} — ${file.name}`,
        replacePeriod: true,
      }))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Workbook processing failed')
    } finally {
      setBusy('')
    }
  }

  async function downloadCurrent(reportType: string, fmt: 'xlsx' | 'pdf') {
    setBusy(`${reportType}-${fmt}`)
    setError('')
    try {
      await downloadReportFile(reportType, fmt, periodId || undefined)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-bold text-slate-900">{isZH ? 'NAAC資料交換' : 'NAAC data exchange'}</h2>
            <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[9px] font-bold text-amber-700">{isZH ? '香港資料閘門未通過' : 'HK data gate pending'}</span>
          </div>
          <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-slate-500">
            {isZH ? '介面已接validate-first workbook API及現有報告下載。現時只可使用synthetic／Care Home B資料；真實NAAC姓名、更表、假期或帳戶不可上載。' : 'This UI uses the live validate-first workbook API and existing report downloads. Synthetic／Care Home B data only; do not upload real NAAC names, rosters, leave or accounts.'}
          </p>
        </div>
        <div className="text-right text-[9px] text-slate-400">{isZH ? `已識別layouts：${layouts.join(', ') || '讀取中'}` : `Recognised layouts: ${layouts.join(', ') || 'loading'}`}</div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <h3 className="text-xs font-bold text-slate-800">{isZH ? 'A.2 Workbook Import' : 'A.2 workbook import'}</h3>
          <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{isZH ? '先Validate，顯示所有錯誤；只有無blocking error時才可寫入draft。' : 'Validate first and display every issue. Commit to a draft only when there is no blocking error.'}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_130px]">
            <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null) }} className="min-w-0 rounded-lg border border-slate-200 bg-white p-2 text-[10px] text-slate-600" />
            <select value={variant} onChange={(e) => setVariant(e.target.value as 'before' | 'after')} className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-[10px] text-slate-600">
              <option value="after">After sheet</option>
              <option value="before">Before sheet</option>
            </select>
          </div>
          <label className="mt-3 flex items-start gap-2 rounded-lg border border-rose-100 bg-rose-50 p-3 text-[10px] leading-relaxed text-rose-700">
            <input type="checkbox" checked={syntheticConfirmed} onChange={(e) => setSyntheticConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 accent-rose-600" />
            <span>{isZH ? '我確認這份檔案只含synthetic／Care Home B測試資料，沒有真實NAAC個人資料。' : 'I confirm this file contains synthetic／Care Home B test data only and no real NAAC personal data.'}</span>
          </label>
          <div className="mt-3 flex gap-2">
            <button onClick={() => runImport('validate')} disabled={!file || !syntheticConfirmed || !!busy} className="flex-1 rounded-lg border border-pink-200 bg-white px-3 py-2 text-[10px] font-bold text-pink-700 disabled:opacity-40">{busy === 'validate' ? '…' : (isZH ? '1. 驗證檔案' : '1. Validate')}</button>
            <button onClick={() => runImport('commit')} disabled={!file || !syntheticConfirmed || !result || result.mode !== 'validate' || blocking.length > 0 || !!busy} className="flex-1 rounded-lg px-3 py-2 text-[10px] font-bold text-white disabled:opacity-40" style={{ background: PINK }}>{busy === 'commit' ? '…' : (isZH ? '2. 寫入Draft' : '2. Commit draft')}</button>
          </div>
          {error && <div className="mt-3 rounded-lg border border-rose-200 bg-white p-3 text-[10px] text-rose-700">{error}</div>}
          {result && (
            <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-[10px] text-slate-600">
              <div className="flex flex-wrap items-center gap-2"><b>{result.status}</b><span>·</span><span>{result.source_layout || 'layout —'}</span><span>·</span><span>{blocking.length} errors</span><span>·</span><span>{warnings.length} warnings</span></div>
              {issues.slice(0, 5).map((issue, i) => <div key={issue.id || `${issue.code}-${i}`} className="mt-1 text-slate-500">{issue.severity || 'info'} · {issue.sheet || '—'} {issue.cell_ref || ''} · {issue.message || issue.code}</div>)}
              {issues.length > 5 && <div className="mt-1 text-slate-400">+ {issues.length - 5} more</div>}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <h3 className="text-xs font-bold text-slate-800">{isZH ? 'NAAC Export' : 'NAAC export'}</h3>
          <label className="mt-3 block text-[9px] font-semibold uppercase tracking-wider text-slate-400">{isZH ? '更表週期' : 'Roster period'}
            <select value={periodId} onChange={(e) => setPeriodId(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[10px] normal-case text-slate-700">
              {!periods.length && <option value="">{isZH ? '未有週期' : 'No period'}</option>}
              {periods.map((period) => <option key={period.id} value={period.id}>{period.period_start} → {period.period_end}</option>)}
            </select>
          </label>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button onClick={() => downloadCurrent('roster_hours', 'xlsx')} disabled={!periodId || !!busy} className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[10px] font-semibold text-slate-700 disabled:opacity-40">{isZH ? '下載現有工時 XLSX' : 'Download hours XLSX'}</button>
            <button onClick={() => downloadCurrent('staffing_ratio', 'pdf')} disabled={!periodId || !!busy} className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[10px] font-semibold text-slate-700 disabled:opacity-40">{isZH ? '下載比例 PDF' : 'Download ratio PDF'}</button>
          </div>
          <div className="mt-3 rounded-xl border border-dashed border-amber-300 bg-amber-50 p-4">
            <div className="text-[10px] font-bold text-amber-800">{isZH ? '最終NAAC六星期多工作表格式：等待backend golden-file mapping' : 'Final NAAC six-week multi-sheet workbook: awaiting backend golden-file mapping'}</div>
            <p className="mt-1 text-[10px] leading-relaxed text-amber-700">{isZH ? '現有generic報告不可冒充NAAC最終Export。Kien完成22h contract、footer、繁中、formula、print layout及sample diff後，此位置會開放正式下載。' : 'The generic reports above are not the final NAAC export. This download unlocks only after the backend delivers the 22h contract, footer, Chinese labels, formulas, print layout and golden-file diff.'}</p>
            <button disabled className="mt-3 w-full cursor-not-allowed rounded-lg bg-amber-200 px-3 py-2 text-[10px] font-bold text-amber-700 opacity-70">{isZH ? '正式NAAC Export 尚未可用' : 'Final NAAC export not yet available'}</button>
          </div>
        </div>
      </div>
    </section>
  )
}
