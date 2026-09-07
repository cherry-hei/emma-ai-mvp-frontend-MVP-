'use client'

// Design: Emma clinical warmth. Reports is the single NAAC output workspace:
// selected roster period in, NAAC-format worksheet previews and XLSX files out.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, downloadReportFile } from '@/lib/api'
import type { GeneratedReport, PeriodOut, ReportRow, VersionOut } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

function pickCurrentPeriod(periods: PeriodOut[]): string {
  if (!periods.length) return ''
  const now = new Date().toISOString().slice(0, 10)
  const current = periods.find((period) => period.period_start <= now && now <= period.period_end)
  if (current) return current.id
  return periods.find((period) => period.period_start <= now)?.id || periods[0].id
}

const NAAC_SHEETS = [
  { id: 'roster_hours', icon: '⏱', en: 'Hours', zh: '工時', descEn: 'Total rostered hours per staff', descZh: '各員工於所選週期的總工時' },
  { id: 'ph_dayoff', icon: '日', en: 'PH & Off', zh: 'PH及休班', descEn: 'Public holidays worked and day-off totals', descZh: '公眾假期出勤及休班日統計' },
  { id: 'do_count', icon: 'DO', en: 'DO shift count', zh: 'DO更次數', descEn: 'Day-off counts and longest work run', descZh: '休班日次數及最長連續工作天' },
  { id: 'ap_shifts', icon: 'A/P', en: 'A/P shifts', zh: 'AP更', descEn: 'A, P and N shift distribution by staff', descZh: '每名員工A更、P更及N更分配' },
  { id: 'night_gender', icon: 'N', en: 'N-shift gender', zh: 'N更男女', descEn: 'Night-shift distribution by gender', descZh: '通宵更按性別分配' },
  { id: 'staffing_ratio', icon: '1:n', en: 'Staffing ratio', zh: '人手比例', descEn: 'Roster-derived statutory coverage results', descZh: '由更表計算的法定人手覆蓋結果' },
]

function ReportPreview({ report, periodId, onClose, isZH }: {
  report: GeneratedReport
  periodId: string
  onClose: () => void
  isZH: boolean
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
            <button onClick={() => downloadReportFile(report.report_type, 'xlsx', periodId)} className="rounded-lg bg-[#E8187A] px-3 py-2 text-[10px] font-bold text-white">
              {isZH ? '下載此分頁 XLSX' : 'Download sheet XLSX'}
            </button>
            <button onClick={onClose} className="px-1 text-lg leading-none text-slate-400" aria-label={isZH ? '關閉' : 'Close'}>×</button>
          </div>
        </div>
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

  useEffect(() => {
    Promise.all([api.rosterPeriods(), api.reports()])
      .then(([periodRows, reportRows]) => {
        setPeriods(periodRows)
        setPeriodId(pickCurrentPeriod(periodRows))
        setRecent(reportRows)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load roster reports'))
  }, [])

  useEffect(() => {
    if (!periodId) { setVersions([]); return }
    api.rosterVersions(periodId).then(setVersions).catch(() => setVersions([]))
  }, [periodId])

  const sourceVersion = useMemo(
    () => versions.find((version) => version.status === 'published') ?? versions.find((version) => version.version_type === 'manual') ?? versions[0],
    [versions],
  )

  const openPreview = useCallback(async (reportType: string) => {
    setBusy(`preview-${reportType}`)
    setError('')
    try {
      setPreview(await api.generateReport(reportType, periodId || undefined))
      api.reports().then(setRecent).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Report preview failed')
    } finally {
      setBusy('')
    }
  }, [periodId])

  async function downloadSheet(reportType: string) {
    setBusy(`download-${reportType}`)
    setError('')
    try {
      await downloadReportFile(reportType, 'xlsx', periodId || undefined)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Report download failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="space-y-5 p-4 md:p-6">
      {preview && <ReportPreview report={preview} periodId={periodId} isZH={isZH} onClose={() => setPreview(null)} />}

      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-950">{isZH ? 'NAAC更表報告' : 'NAAC Roster Reports'}</h1>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-500">
            {isZH ? '直接使用更表工作區的實時資料，產生NAAC原Excel所需的各分頁報告。毋須上載NAAC workbook。' : 'Generate the worksheet reports required by the NAAC source workbook directly from live Roster Workspace data. No workbook upload is required.'}
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
          <select value={periodId} onChange={(event) => setPeriodId(event.target.value)} className="mt-2 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs font-medium normal-case tracking-normal text-slate-700 md:min-w-72">
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
                <button onClick={() => openPreview(sheet.id)} disabled={!periodId || !!busy} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[10px] font-bold text-slate-700 disabled:opacity-40">{busy === `preview-${sheet.id}` ? '…' : (isZH ? '預覽' : 'Preview')}</button>
                <button onClick={() => downloadSheet(sheet.id)} disabled={!periodId || !!busy} className="rounded-lg bg-slate-950 px-3 py-2 text-[10px] font-bold text-white disabled:opacity-40">{busy === `download-${sheet.id}` ? '…' : (isZH ? '下載XLSX' : 'Download XLSX')}</button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-rose-200 bg-gradient-to-r from-rose-50 to-white p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-bold text-slate-900">{isZH ? '完整NAAC六星期Excel' : 'Complete six-week NAAC workbook'}</h2>
            <p className="mt-1 max-w-2xl text-[10px] leading-relaxed text-slate-600">{isZH ? '一個檔案包含第一至第六週及以上報告分頁，版面、公式、繁中標籤、footer及列印設定按NAAC原檔對照。' : 'One workbook containing weeks one to six and the report sheets above, matched to the NAAC source layout, formulas, Chinese labels, footer and print settings.'}</p>
          </div>
          <button disabled className="min-w-52 cursor-not-allowed rounded-xl bg-rose-200 px-4 py-3 text-xs font-bold text-rose-700 opacity-80">
            {isZH ? '等待backend完成正式下載' : 'Awaiting final backend download'}
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
