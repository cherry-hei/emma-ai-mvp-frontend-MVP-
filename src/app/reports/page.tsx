'use client'

// Design: Emma clinical warmth. Reports is the single NAAC output workspace:
// selected roster period in, NAAC-format worksheet previews and XLSX files out.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, downloadReportFile, downloadNaacWorkbook } from '@/lib/api'
import type { GeneratedReport, PeriodOut, ReportRow, VersionOut } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'

const PINK = '#E8187A'

function pickCurrentPeriod(periods: PeriodOut[]): string {
  if (!periods.length) return ''
  const now = new Date().toISOString().slice(0, 10)
  const current = periods.find((period) => period.period_start <= now && now <= period.period_end)
  if (current) return current.id
  return periods.find((period) => period.period_start <= now)?.id || periods[0].id
}

const NAAC_SHEETS = [
  { id: 'roster_hours', icon: '⏱', en: 'Hours', zh: '工時', descEn: 'Total rostered hours per staff', descZh: '各員工於所選週期的總工時', available: true },
  { id: 'ph_dayoff', icon: '日', en: 'PH & Off', zh: 'PH及休班', descEn: 'Public holidays worked and day-off totals', descZh: '公眾假期出勤及休班日統計', available: true },
  { id: 'do_count', icon: 'DO', en: 'DO shift count', zh: 'DO更次數', descEn: 'Day-off counts and longest work run', descZh: '休班日次數及最長連續工作天', available: true },
  { id: 'ap_shifts', icon: 'A/P', en: 'A/P shifts', zh: 'AP更', descEn: 'A, P and N shift distribution by staff', descZh: '每名員工A更、P更及N更分配', available: true },
  { id: 'c_shift_gender', icon: 'C', en: 'C-shift gender', zh: 'C更男女', descEn: 'C-shift distribution by gender', descZh: 'C更按性別分配', available: false },
  { id: 'night_gender', icon: 'N', en: 'N-shift gender', zh: 'N更男女', descEn: 'Night-shift distribution by gender', descZh: '通宵更按性別分配', available: true },
]

function ReportPreview({ report, onDownload, onClose, isZH, busy, error }: {
  report: GeneratedReport
  onDownload: () => void
  onClose: () => void
  isZH: boolean
  busy: boolean
  error: string
}) {
  const { columns, rows } = report.payload
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-3 md:p-6">
      <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 md:px-5">
          <div>
            <div className="text-sm font-bold text-slate-900">{report.title}</div>
            <div className="mt-0.5 text-[10px] text-slate-400">{report.row_count} {isZH ? '行 · 來源：所選更表週期' : 'rows · Source: selected roster period'}</div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onDownload} disabled={busy} className="rounded-lg bg-[#E8187A] px-3 py-2 text-[10px] font-bold text-white disabled:opacity-50">
              {isZH ? '下載此分頁 XLSX' : 'Download sheet XLSX'}
            </button>
            <button onClick={onClose} className="px-1 text-lg leading-none text-slate-400" aria-label={isZH ? '關閉' : 'Close'}>×</button>
          </div>
        </div>
        {error && <div role="alert" className="px-4 py-3 text-xs text-rose-700">{error}</div>}
        <div className="overflow-auto p-4">
          <table className="w-full text-[11px]">
            <thead><tr className="border-b border-slate-200">{columns.map((column) => <th key={column.key} className="whitespace-nowrap px-2 py-2 text-left text-[9px] font-bold uppercase text-slate-400">{column.label}</th>)}</tr></thead>
            <tbody>{rows.map((row, index) => <tr key={index} className="border-b border-slate-50">{columns.map((column) => <td key={column.key} className="whitespace-nowrap px-2 py-1.5 text-slate-700">{String(row[column.key] ?? '')}</td>)}</tr>)}</tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default function ReportsPage() {
  const { user } = useAuth()
  if (!user) return null
  return <ReportsWorkspace key={`${user.userId}:${user.facilityId ?? ''}:${user.role ?? ''}`} />
}

function ReportsWorkspace() {
  const router = useRouter()
  const { lang } = useLang()
  const isZH = lang === 'zh'
  const [periods, setPeriods] = useState<PeriodOut[]>([])
  const [periodId, setPeriodId] = useState('')
  const [versions, setVersions] = useState<VersionOut[]>([])
  const [recent, setRecent] = useState<ReportRow[]>([])
  const [preview, setPreview] = useState<GeneratedReport | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const request = useRef(0)
  const currentPeriod = useRef(periodId)
  const activeDownload = useRef<AbortController | null>(null)
  const mounted = useRef(true)
  currentPeriod.current = periodId

  function isCurrent(id: number, period: string) {
    return mounted.current && request.current === id && currentPeriod.current === period
  }

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      request.current += 1
      activeDownload.current?.abort()
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([api.rosterPeriods(), api.reports()])
      .then(([periodRows, reportRows]) => {
        if (cancelled) return
        setPeriods(periodRows)
        setPeriodId(pickCurrentPeriod(periodRows))
        setRecent(reportRows)
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load roster reports') })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    request.current += 1
    activeDownload.current?.abort()
    setVersions([])
    setPreview(null)
    setBusy('')
    setError('')
    if (periodId) {
      api.rosterVersions(periodId)
        .then(rows => { if (!cancelled) setVersions(rows) })
        .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load roster versions') })
    }
    return () => { cancelled = true }
  }, [periodId])

  const sourceVersion = useMemo(
    () => versions.find((version) => version.status === 'published') ?? versions.find((version) => version.version_type === 'manual') ?? versions[0],
    [versions],
  )

  async function openPreview(reportType: string) {
    if (!periodId) return
    const id = ++request.current
    setBusy(`preview-${reportType}`)
    setError('')
    try {
      const report = await api.generateReport(reportType, periodId)
      if (!isCurrent(id, periodId)) return
      setPreview(report)
      api.reports().then(rows => { if (isCurrent(id, periodId)) setRecent(rows) }).catch(() => {})
    } catch (e) {
      if (isCurrent(id, periodId)) setError(e instanceof Error ? e.message : 'Report preview failed')
    } finally {
      if (isCurrent(id, periodId)) setBusy('')
    }
  }

  async function downloadSheet(reportType: string) {
    await runDownload(`download-${reportType}`, signal => downloadReportFile(reportType, 'xlsx', periodId, signal))
  }

  async function downloadWorkbook() {
    await runDownload('workbook', signal => downloadNaacWorkbook(periodId, signal))
  }

  async function runDownload(label: string, download: (signal: AbortSignal) => Promise<void>) {
    if (!periodId) return
    const id = ++request.current
    activeDownload.current?.abort()
    const controller = new AbortController()
    activeDownload.current = controller
    setBusy(label)
    setError('')
    try { await download(controller.signal) }
    catch (e) { if (isCurrent(id, periodId)) setError(e instanceof Error ? e.message : 'Report download failed') }
    finally { if (isCurrent(id, periodId)) setBusy('') }
  }

  function closePreview() {
    request.current += 1
    activeDownload.current?.abort()
    setPreview(null)
    setBusy('')
    setError('')
  }

  function changePeriod(value: string) {
    request.current += 1
    activeDownload.current?.abort()
    setPreview(null)
    setVersions([])
    setBusy('')
    setError('')
    setPeriodId(value)
  }

  return (
    <div className="space-y-5 p-4 md:p-6">
      {preview && <ReportPreview report={preview} isZH={isZH} onClose={closePreview}
        onDownload={() => downloadSheet(preview.report_type)} busy={!!busy} error={error} />}

      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-950">{isZH ? 'NAAC更表報告' : 'NAAC Roster Reports'}</h1>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-500">
            {isZH ? '使用所選更表週期產生報告。完整NAAC工作簿須先配置已確認的Excel範本。' : 'Generate reports from the selected roster period. The full NAAC workbook requires its approved Excel template to be configured.'}
          </p>
        </div>
        <button onClick={() => router.push('/roster')} className="w-fit rounded-xl border border-rose-200 bg-white px-4 py-2 text-xs font-bold text-[#E8187A] hover:bg-rose-50">
          {isZH ? '返回更表工作區' : 'Open Roster Workspace'}
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">{error}</div>}
      <section className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-[1fr_auto] md:items-end md:p-5">
        <label className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
          {isZH ? '更表週期' : 'Roster period'}
          <select value={periodId} onChange={(event) => changePeriod(event.target.value)} className="mt-2 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs font-medium normal-case tracking-normal text-slate-700 md:min-w-72">
            {!periods.length && <option value="">{isZH ? '未有更表週期' : 'No roster period'}</option>}
            {periods.map((period) => <option key={period.id} value={period.id}>{period.period_start} → {period.period_end} · {period.status}</option>)}
          </select>
        </label>
        <div className="rounded-xl bg-slate-50 px-4 py-3 text-[10px] text-slate-500">
          <div className="font-bold uppercase tracking-wider text-slate-400">{isZH ? '資料來源' : 'Source roster'}</div>
          <div className="mt-1 font-semibold text-slate-700">{sourceVersion ? `${sourceVersion.version_type} · ${sourceVersion.status}` : (isZH ? '等待更表版本' : 'Waiting for roster version')}</div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 md:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-slate-900">{isZH ? 'NAAC Excel分頁' : 'NAAC Excel worksheets'}</h2>
            <p className="mt-1 text-[10px] text-slate-500">{isZH ? '每張卡代表完整NAAC workbook中的一個報告分頁。' : 'Each card represents one report worksheet in the complete NAAC workbook.'}</p>
          </div>
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[9px] font-bold text-emerald-700">{isZH ? '由Roster實時產生' : 'Roster-derived'}</span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {NAAC_SHEETS.map((sheet) => (
            <article key={sheet.id} className="flex min-h-40 flex-col rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
              <div className="flex items-start gap-3">
                <span className="flex h-10 min-w-10 items-center justify-center rounded-xl bg-white px-2 text-xs font-black text-[#E8187A] shadow-sm">{sheet.icon}</span>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">{isZH ? sheet.zh : sheet.en}</h3>
                  <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{isZH ? sheet.descZh : sheet.descEn}</p>
                </div>
              </div>
              <div className="mt-auto grid grid-cols-2 gap-2 pt-4">
                <button onClick={() => openPreview(sheet.id)} disabled={!sheet.available || !periodId || !!busy} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[10px] font-bold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40">{busy === `preview-${sheet.id}` ? '…' : sheet.available ? (isZH ? '預覽' : 'Preview') : (isZH ? '尚欠backend' : 'Backend pending')}</button>
                <button onClick={() => downloadSheet(sheet.id)} disabled={!sheet.available || !periodId || !!busy} className="rounded-lg bg-slate-950 px-3 py-2 text-[10px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">{busy === `download-${sheet.id}` ? '…' : sheet.available ? (isZH ? '下載XLSX' : 'Download XLSX') : (isZH ? '未可下載' : 'Unavailable')}</button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-rose-200 bg-gradient-to-r from-rose-50 to-white p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-bold text-slate-900">{isZH ? '完整NAAC六星期Excel' : 'Complete six-week NAAC workbook'}</h2>
            <p className="mt-1 max-w-2xl text-[10px] leading-relaxed text-slate-600">{isZH ? '下載所選六星期週期的18分頁工作簿。須先配置已確認的NAAC Excel範本及欄位對應。' : 'Download the 18-sheet workbook for the selected six-week period. The approved NAAC Excel template and cell mapping must be configured first.'}</p>
          </div>
          <button onClick={downloadWorkbook} disabled={!periodId || !!busy} className="min-w-52 rounded-xl bg-[#E8187A] px-4 py-3 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-50">
            {busy === 'workbook' ? (isZH ? '下載中…' : 'Downloading…') : (isZH ? '下載完整 NAAC 工作簿' : 'Download full NAAC workbook')}
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-bold text-slate-900">{isZH ? '最近生成' : 'Recently generated'}</h2>
        {!recent.length ? <p className="mt-3 text-[11px] text-slate-400">{isZH ? '尚未生成報告' : 'No reports generated yet'}</p> : (
          <div className="mt-3 divide-y divide-slate-100">
            {recent.slice(0, 8).map((row) => <div key={row.id} className="flex flex-col gap-1 py-2 text-[11px] sm:flex-row sm:items-center sm:justify-between"><span className="font-medium text-slate-700">{row.title}</span><span className="text-slate-400">{row.row_count} {isZH ? '行' : 'rows'} · {(row.created_at || '').slice(0, 16).replace('T', ' ')}</span></div>)}
          </div>
        )}
      </section>
    </div>
  )
}
