'use client'

/**
 * Facility reports are always bound to one roster period and, where selected,
 * one version from that same period. Query values are treated as requests, not
 * authority: unrecognised or cross-period values show an error rather than
 * silently drifting to a different roster.
 */
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { api, downloadReportFile, downloadRosterAudit } from '@/lib/api'
import type { GeneratedReport, PeriodOut, ReportRow, RosterHistory, VersionOut } from '@/lib/apiTypes'
import { useAuth } from '@/components/layout/AuthContext'
import { useLang } from '@/components/layout/LanguageContext'
import { canRead } from '@/lib/permissions'

const PINK = '#E8187A'

type ReportScope = 'version' | 'period'

type ReportSheet = {
  id: string
  icon: string
  en: string
  zh: string
  descEn: string
  descZh: string
  scope: ReportScope
}

type PreviewState = {
  report: GeneratedReport
  periodId: string
  versionId: string
  reportScope: ReportScope
  scopeKey: string
  sourceKey: string
}

// These report IDs are intentionally constrained to the currently reviewed
// backend contract. Period aggregates are kept separate: the server rejects a
// selected version for those reports, so sending it would misstate their scope.
const REPORT_SHEETS: readonly ReportSheet[] = [
  { id: 'roster_hours', icon: '⏱', en: 'Roster Hours', zh: '更表工時', descEn: 'Rostered hours by staff for the selected roster version', descZh: '所選更表版本內各員工的編排工時', scope: 'version' },
  { id: 'ph_dayoff', icon: '日', en: 'Public Holiday & Off', zh: '公眾假期及休班', descEn: 'Public-holiday work and day-off totals in the selected version', descZh: '所選版本中的公眾假期出勤及休班日統計', scope: 'version' },
  { id: 'do_count', icon: 'DO', en: 'Day-off Count', zh: '休班日統計', descEn: 'Day-off counts and longest work run in the selected version', descZh: '所選版本中的休班日次數及最長連續工作天', scope: 'version' },
  { id: 'ap_shifts', icon: 'A/P', en: 'Shift Distribution', zh: '更別分配', descEn: 'Shift distribution by staff in the selected version', descZh: '所選版本中每名員工的更別分配', scope: 'version' },
  { id: 'night_gender', icon: 'N', en: 'Night-shift Distribution', zh: '夜更分配', descEn: 'Night-shift distribution in the selected version', descZh: '所選版本中的夜更分配', scope: 'version' },
  { id: 'staff_register', icon: '⌂', en: 'Staff Register', zh: '員工名冊', descEn: 'Staff register associated with the selected roster version', descZh: '與所選更表版本相關的員工名冊', scope: 'version' },
  { id: 'staffing_ratio', icon: '⇄', en: 'Staffing Ratio', zh: '人手比例', descEn: 'Version-specific staffing ratio evidence', descZh: '版本特定的人手比例證據', scope: 'version' },
  { id: 'roster_export', icon: '⇩', en: 'Roster Export', zh: '更表匯出', descEn: 'Version-specific roster export', descZh: '版本特定的更表匯出', scope: 'version' },
  { id: 'monthly_staffing_compliance', icon: '▦', en: 'Monthly Staffing Compliance', zh: '每月人手合規', descEn: 'Period aggregate only; it does not describe a selected draft/version', descZh: '只限週期匯總；不代表所選草稿或版本', scope: 'period' },
  { id: 'compliance_summary', icon: '✓', en: 'Compliance Summary', zh: '合規摘要', descEn: 'Period aggregate only; it does not describe a selected draft/version', descZh: '只限週期匯總；不代表所選草稿或版本', scope: 'period' },
]

function defaultPeriodId(periods: PeriodOut[]): string {
  if (!periods.length) return ''
  const now = new Date().toISOString().slice(0, 10)
  return periods.find((period) => period.period_start <= now && now <= period.period_end)?.id ?? periods[0].id
}

function versionLabel(version: VersionOut): string {
  return [version.label || version.version_type, version.status].filter(Boolean).join(' · ')
}

function ReportPreview({ report, periodId, versionId, reportScope, onClose, isZH }: {
  report: GeneratedReport
  periodId: string
  versionId: string
  reportScope: ReportScope
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
            <div className="mt-0.5 text-[10px] text-slate-400">
              {report.row_count} {reportScope === 'version'
                ? (isZH ? '行 · 來源：所選更表週期及版本' : 'rows · Source: selected roster period and version')
                : (isZH ? '行 · 來源：所選更表週期匯總' : 'rows · Source: selected roster-period aggregate')}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => downloadReportFile(report.report_type, 'xlsx', periodId, reportScope === 'version' ? versionId || undefined : undefined)} className="rounded-lg bg-[#E8187A] px-3 py-2 text-[10px] font-bold text-white">
              {isZH ? '下載此分頁 XLSX' : 'Download sheet XLSX'}
            </button>
            <button type="button" onClick={onClose} className="px-1 text-lg leading-none text-slate-400" aria-label={isZH ? '關閉' : 'Close'}>×</button>
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

function ReportsContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { lang } = useLang()
  const { user } = useAuth()
  const isZH = lang === 'zh'
  const [periods, setPeriods] = useState<PeriodOut[]>([])
  const [periodId, setPeriodId] = useState('')
  const [versions, setVersions] = useState<VersionOut[]>([])
  const [versionId, setVersionId] = useState('')
  // A user may intentionally clear version selection to run period aggregates.
  // This differs from an initial unscoped visit, which may select a preferred
  // version; do not silently reverse the explicit aggregate choice.
  const [aggregateMode, setAggregateMode] = useState(false)
  const [recent, setRecent] = useState<ReportRow[]>([])
  const [history, setHistory] = useState<RosterHistory | null>(null)
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const requestedPeriodId = searchParams.get('period_id') || ''
  const requestedVersionId = searchParams.get('version_id') || ''
  const auditAllowed = canRead(user?.role, 'audit_log')
  // The same browser tab can change home after sign-out/sign-in or after the
  // cached session is verified. Never let rows fetched under the old token paint
  // in the newly authenticated home while a new request is still in flight.
  const scopeKey = user ? `${user.userId}:${user.facilityId ?? ''}` : ''
  const sourceKey = `${scopeKey}|${periodId}|${versionId}`
  const [renderedScopeKey, setRenderedScopeKey] = useState<string | null>(null)
  const scopeRef = useRef(scopeKey)
  const sourceKeyRef = useRef(sourceKey)
  const bootstrapRequestRef = useRef(0)
  const versionsRequestRef = useRef(0)
  const historyRequestRef = useRef(0)
  const recentRequestRef = useRef(0)
  const previewRequestRef = useRef(0)

  const writeScope = useCallback((nextPeriodId: string, nextVersionId: string) => {
    const params = new URLSearchParams()
    if (nextPeriodId) params.set('period_id', nextPeriodId)
    if (nextVersionId) params.set('version_id', nextVersionId)
    router.replace(`/reports${params.size ? `?${params.toString()}` : ''}`)
  }, [router])

  // Clear every server-derived value before accepting data from the next session.
  // `renderedScopeKey` also makes the intervening render a loading state, rather
  // than briefly rendering the previous facility's records.
  useEffect(() => {
    scopeRef.current = scopeKey
    bootstrapRequestRef.current += 1
    versionsRequestRef.current += 1
    historyRequestRef.current += 1
    recentRequestRef.current += 1
    previewRequestRef.current += 1
    setPeriods([])
    setPeriodId('')
    setVersions([])
    setVersionId('')
    setAggregateMode(false)
    setRecent([])
    setHistory(null)
    setPreview(null)
    setBusy('')
    setError('')
    setRenderedScopeKey(scopeKey)
  }, [scopeKey])

  // A period/version change supersedes both an open preview and every pending
  // preview generation. The preview itself carries this key as a final render
  // guard, so an old response can never acquire the new selector's download IDs.
  useEffect(() => {
    sourceKeyRef.current = sourceKey
    previewRequestRef.current += 1
    setPreview((current) => current?.sourceKey === sourceKey ? current : null)
    setBusy('')
  }, [sourceKey])

  useEffect(() => {
    let cancelled = false
    const requestScope = scopeKey
    const requestId = ++bootstrapRequestRef.current
    if (!requestScope) return () => { cancelled = true }
    Promise.all([api.rosterPeriods(), api.reports()])
      .then(([periodRows, reportRows]) => {
        if (cancelled || scopeRef.current !== requestScope || requestId !== bootstrapRequestRef.current) return
        setPeriods(periodRows)
        setRecent(reportRows)
        if (requestedPeriodId) {
          if (periodRows.some((period) => period.id === requestedPeriodId)) setPeriodId(requestedPeriodId)
          else {
            setPeriodId('')
            setVersions([])
            setVersionId('')
            setError(isZH ? '要求的更表週期不存在或不屬於目前院舍；沒有改用另一週期。' : 'The requested roster period does not exist or is outside this facility; another period was not selected.')
          }
        } else {
          setPeriodId(defaultPeriodId(periodRows))
        }
      })
      .catch((e) => {
        if (!cancelled && scopeRef.current === requestScope && requestId === bootstrapRequestRef.current) {
          setError(e instanceof Error ? e.message : 'Failed to load roster reports')
        }
      })
    return () => { cancelled = true }
  }, [isZH, requestedPeriodId, scopeKey])

  useEffect(() => {
    let cancelled = false
    const requestScope = scopeKey
    const requestId = ++versionsRequestRef.current
    if (!requestScope) return () => { cancelled = true }
    if (!periodId) {
      setVersions([])
      setVersionId('')
      setHistory(null)
      return () => { cancelled = true }
    }
    setVersions([])
    setVersionId('')
    setHistory(null)
    api.rosterVersions(periodId)
      .then((rows) => {
        if (cancelled || scopeRef.current !== requestScope || requestId !== versionsRequestRef.current) return
        const samePeriod = rows.filter((version) => !version.period_id || version.period_id === periodId)
        setVersions(samePeriod)
        if (requestedVersionId) {
          const requested = samePeriod.find((version) => version.id === requestedVersionId)
          if (requested) setVersionId(requested.id)
          else setError(isZH ? '要求的更表版本不存在或不屬於所選週期；沒有改用另一版本。' : 'The requested roster version does not exist or is outside the selected period; another version was not selected.')
        } else if (aggregateMode) {
          setVersionId('')
        } else {
          const preferred = samePeriod.find((version) => version.status === 'published') ?? samePeriod.find((version) => version.version_type === 'manual') ?? samePeriod[0]
          setVersionId(preferred?.id || '')
        }
      })
      .catch(() => {
        if (!cancelled && scopeRef.current === requestScope && requestId === versionsRequestRef.current) {
          setError(isZH ? '無法載入所選週期的更表版本。' : 'Could not load roster versions for the selected period.')
        }
      })
    return () => { cancelled = true }
  }, [aggregateMode, isZH, periodId, requestedVersionId, scopeKey])

  useEffect(() => {
    let cancelled = false
    const requestScope = scopeKey
    const requestSource = sourceKey
    const requestId = ++historyRequestRef.current
    if (!requestScope || !periodId) return () => { cancelled = true }
    api.rosterHistory(periodId, versionId || undefined)
      .then((result) => {
        if (!cancelled && scopeRef.current === requestScope && sourceKeyRef.current === requestSource && requestId === historyRequestRef.current) {
          setHistory(result)
        }
      })
      .catch(() => {
        if (!cancelled && scopeRef.current === requestScope && sourceKeyRef.current === requestSource && requestId === historyRequestRef.current) {
          setHistory(null)
        }
      })
    return () => { cancelled = true }
  }, [periodId, scopeKey, sourceKey, versionId])

  const sourceVersion = useMemo(() => versions.find((version) => version.id === versionId), [versionId, versions])
  const periodReady = Boolean(periodId)
  const versionScopeReady = Boolean(periodId && versionId)

  const changePeriod = (nextPeriodId: string) => {
    setError('')
    previewRequestRef.current += 1
    setPreview(null)
    setPeriodId(nextPeriodId)
    setVersionId('')
    setAggregateMode(false)
    writeScope(nextPeriodId, '')
  }
  const changeVersion = (nextVersionId: string) => {
    setError('')
    previewRequestRef.current += 1
    setPreview(null)
    setVersionId(nextVersionId)
    setAggregateMode(!nextVersionId)
    writeScope(periodId, nextVersionId)
  }

  const canRun = (scope: ReportScope) => scope === 'version' ? versionScopeReady : periodReady && !versionId

  const openPreview = useCallback(async (reportType: string, scope: ReportScope) => {
    if (!(scope === 'version' ? versionScopeReady : periodReady && !versionId)) return
    const requestScope = scopeKey
    const requestSource = sourceKey
    const requestPeriodId = periodId
    const requestVersionId = scope === 'version' ? versionId : ''
    const requestId = ++previewRequestRef.current
    const stillCurrent = () => (
      scopeRef.current === requestScope
      && sourceKeyRef.current === requestSource
      && previewRequestRef.current === requestId
    )
    setBusy(`preview-${reportType}`)
    setError('')
    try {
      const report = await api.generateReport(reportType, requestPeriodId, requestVersionId || undefined)
      if (!stillCurrent()) return
      setPreview({
        report, periodId: requestPeriodId, versionId: requestVersionId,
        reportScope: scope, scopeKey: requestScope, sourceKey: requestSource,
      })
      const recentRequestId = ++recentRequestRef.current
      const reportRows = await api.reports()
      if (stillCurrent() && recentRequestRef.current === recentRequestId) setRecent(reportRows)
    } catch (e) {
      if (stillCurrent()) setError(e instanceof Error ? e.message : 'Report preview failed')
    } finally {
      if (stillCurrent()) setBusy('')
    }
  }, [periodId, periodReady, scopeKey, sourceKey, versionId, versionScopeReady])

  async function downloadSheet(reportType: string, scope: ReportScope) {
    if (!canRun(scope)) return
    const requestScope = scopeKey
    const requestSource = sourceKey
    setBusy(`download-${reportType}`)
    setError('')
    try {
      await downloadReportFile(reportType, 'xlsx', periodId, scope === 'version' ? versionId : undefined)
    } catch (e) {
      if (scopeRef.current === requestScope && sourceKeyRef.current === requestSource) {
        setError(e instanceof Error ? e.message : 'Report download failed')
      }
    } finally {
      if (scopeRef.current === requestScope && sourceKeyRef.current === requestSource) setBusy('')
    }
  }

  async function downloadAudit() {
    if (!versionScopeReady || !auditAllowed) return
    const requestScope = scopeKey
    const requestSource = sourceKey
    setBusy('audit')
    setError('')
    try {
      await downloadRosterAudit(periodId, versionId)
    } catch (e) {
      if (scopeRef.current === requestScope && sourceKeyRef.current === requestSource) {
        setError(e instanceof Error ? e.message : 'Audit download failed')
      }
    } finally {
      if (scopeRef.current === requestScope && sourceKeyRef.current === requestSource) setBusy('')
    }
  }

  const activePreview = preview && preview.scopeKey === scopeKey && preview.sourceKey === sourceKey ? preview : null
  const scopeReady = Boolean(scopeKey) && renderedScopeKey === scopeKey
  if (!scopeReady) return <div className="p-6 text-xs text-slate-400">Loading reports…</div>

  return (
    <div className="space-y-5 p-4 md:p-6">
      {activePreview && <ReportPreview report={activePreview.report} periodId={activePreview.periodId} versionId={activePreview.versionId} reportScope={activePreview.reportScope} isZH={isZH} onClose={() => setPreview(null)} />}

      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#E8187A]">Emma AI</p>
          <h1 className="mt-1 text-xl font-bold text-slate-950">{isZH ? '院舍更表報告' : 'Facility Roster Reports'}</h1>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-500">
            {isZH ? '以所選更表週期及版本產生目前後端支援的報告。報告可用性由院舍資料及後端合約決定。' : 'Generate reports supported by the current backend for the selected roster period and version. Availability depends on facility data and the backend contract.'}
          </p>
        </div>
        <button type="button" onClick={() => router.push('/roster')} className="w-fit rounded-xl border border-rose-200 bg-white px-4 py-2 text-xs font-bold text-[#E8187A] hover:bg-rose-50">
          {isZH ? '返回更表工作區' : 'Open Roster Workspace'}
        </button>
      </header>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">{error}</div>}

      <section className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-2 md:p-5 xl:grid-cols-[1fr_1fr_auto] xl:items-end">
        <label className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
          {isZH ? '更表週期' : 'Roster period'}
          <select value={periodId} onChange={(event) => changePeriod(event.target.value)} className="mt-2 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs font-medium normal-case tracking-normal text-slate-700">
            {!periods.length && <option value="">{isZH ? '未有更表週期' : 'No roster period'}</option>}
            {periods.map((period) => <option key={period.id} value={period.id}>{period.period_start} → {period.period_end} · {period.status}</option>)}
          </select>
        </label>
        <label className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
          {isZH ? '更表版本' : 'Roster version'}
          <select value={versionId} onChange={(event) => changeVersion(event.target.value)} disabled={!periodId || !versions.length} className="mt-2 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs font-medium normal-case tracking-normal text-slate-700 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400">
            <option value="">{versions.length ? (isZH ? '週期匯總（不選版本）' : 'Period aggregate (no version)') : (isZH ? '未有此週期的版本' : 'No versions for this period')}</option>
            {versions.map((version) => <option key={version.id} value={version.id}>{versionLabel(version)}</option>)}
          </select>
        </label>
        <div className="rounded-xl bg-slate-50 px-4 py-3 text-[10px] text-slate-500">
          <div className="font-bold uppercase tracking-wider text-slate-400">{isZH ? '報告範圍' : 'Report scope'}</div>
          <div className="mt-1 font-semibold text-slate-700">{sourceVersion ? versionLabel(sourceVersion) : (isZH ? '請先選擇同一週期的版本' : 'Choose a version in this period')}</div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 md:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-slate-900">{isZH ? '可用報告分頁' : 'Available report worksheets'}</h2>
            <p className="mt-1 text-[10px] text-slate-500">{isZH ? '版本報告會帶上目前週期和版本；週期匯總則必須明確取消版本選擇，絕不假裝反映草稿。' : 'Version reports carry the current period and version. Period aggregates require an explicit no-version selection and never claim to reflect a draft.'}</p>
          </div>
          <span className="rounded-full bg-rose-50 px-2.5 py-1 text-[9px] font-bold text-[#E8187A]">{versionId ? (isZH ? '版本已鎖定範圍' : 'Version-scoped') : (isZH ? '週期匯總範圍' : 'Period aggregate')}</span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {REPORT_SHEETS.map((sheet) => (
            <article key={sheet.id} className="flex min-h-40 flex-col rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
              <div className="flex items-start gap-3">
                <span className="flex h-10 min-w-10 items-center justify-center rounded-xl bg-white px-2 text-xs font-black text-[#E8187A] shadow-sm">{sheet.icon}</span>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">{isZH ? sheet.zh : sheet.en}</h3>
                  <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{isZH ? sheet.descZh : sheet.descEn}</p>
                </div>
              </div>
              {sheet.scope === 'period' && versionId && (
                <p className="mt-auto pt-4 text-[10px] leading-relaxed text-amber-700">
                  {isZH ? '此報告只支援週期匯總。請在版本選單選擇「週期匯總（不選版本）」；如需所選版本的人手證據，請使用「人手比例」。' : 'This report is period-aggregate only. Choose “Period aggregate (no version)”; for selected-version staffing evidence, use Staffing Ratio.'}
                </p>
              )}
              <div className={`${sheet.scope === 'period' && versionId ? 'pt-2' : 'mt-auto pt-4'} grid grid-cols-2 gap-2`}>
                <button type="button" onClick={() => openPreview(sheet.id, sheet.scope)} disabled={!canRun(sheet.scope) || !!busy} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[10px] font-bold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40">{busy === `preview-${sheet.id}` ? '…' : (isZH ? '預覽' : 'Preview')}</button>
                <button type="button" onClick={() => downloadSheet(sheet.id, sheet.scope)} disabled={!canRun(sheet.scope) || !!busy} className="rounded-lg bg-slate-950 px-3 py-2 text-[10px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">{busy === `download-${sheet.id}` ? '…' : (isZH ? '下載 XLSX' : 'Download XLSX')}</button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 md:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-bold text-slate-900">{isZH ? '更表歷史與審計' : 'Roster history & audit'}</h2>
            <p className="mt-1 max-w-2xl text-[10px] leading-relaxed text-slate-500">
              {history?.can_read_audit
                ? (isZH ? `${history.changes.length} 項可讀變更及 ${history.publish_events.length} 項發佈事件屬於目前範圍${history.truncated ? '（列表已截斷）' : ''}。下載為同一伺服器範圍的審計CSV。` : `${history.changes.length} readable changes and ${history.publish_events.length} publish events are in the current scope${history.truncated ? ' (list truncated)' : ''}. Download is the same server-scoped audit CSV.`)
                : (isZH ? `${history?.publish_events.length ?? 0} 項發佈事件在目前範圍可見。詳細變更及CSV下載只限擁有審計日誌權限的帳戶。` : `${history?.publish_events.length ?? 0} publish events are visible in the current scope. Detailed changes and CSV download are limited to accounts with audit-log permission.`)}
            </p>
          </div>
          {auditAllowed && (
            <button type="button" onClick={downloadAudit} disabled={!versionScopeReady || !!busy || history?.can_read_audit === false} className="w-fit rounded-xl bg-[#E8187A] px-4 py-2.5 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">
              {busy === 'audit' ? '…' : (isZH ? '下載審計 CSV' : 'Download audit CSV')}
            </button>
          )}
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


export default function ReportsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-xs text-slate-400">Loading reports…</div>}>
      <ReportsContent />
    </Suspense>
  )
}
