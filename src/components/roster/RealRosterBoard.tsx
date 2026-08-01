'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiRuleError, api, optimizeAndPoll } from '@/lib/api'
import type {
  OptionScoreOut, PeriodOut, RosterCell, RosterGrid, RosterOption, RuleIssue,
  ShiftDef, TaskDefOut, ValidationOut, VersionOut,
} from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'
import { AiOptionsModal } from './AiOptionsModal'
import { CreateEventModal } from './CreateEventModal'

const PINK = '#E8187A'

// Cell colors mirror emma_core.constants.SHIFT_STYLE (backend), with a neutral default.
const SHIFT_STYLE: Record<string, { bg: string; fg: string }> = {
  A: { bg: '#DBEAFE', fg: '#1E40AF' }, B: { bg: '#CFFAFE', fg: '#155E75' },
  E: { bg: '#CCFBF1', fg: '#115E59' }, P: { bg: '#FEF3C7', fg: '#92400E' },
  N: { bg: '#E0E7FF', fg: '#3730A3' }, AN: { bg: '#EDE9FE', fg: '#5B21B6' },
  '7A': { bg: '#DBEAFE', fg: '#1E40AF' }, '9A': { bg: '#CFFAFE', fg: '#155E75' },
  '7P': { bg: '#E0E7FF', fg: '#3730A3' },
  AL: { bg: '#DCFCE7', fg: '#166534' }, SLEEP: { bg: '#F5F3FF', fg: '#6D28D9' },
  OFF: { bg: '#F1F5F9', fg: '#64748B' }, DO: { bg: '#F1F5F9', fg: '#64748B' },
}
const DEFAULT_STYLE = { bg: '#F1F5F9', fg: '#475569' }

// UTC-based to stay timezone-agnostic: parsing a bare date as local time and then
// calling toISOString() would roll the day back on UTC+ machines.
function eachDate(start: string, end: string): string[] {
  const out: string[] = []
  const [ys, ms, ds] = start.split('-').map(Number)
  const [ye, me, de] = end.split('-').map(Number)
  let t = Date.UTC(ys, ms - 1, ds)
  const last = Date.UTC(ye, me - 1, de)
  for (let i = 0; t <= last && i < 400; i++) {
    out.push(new Date(t).toISOString().slice(0, 10))
    t += 86_400_000
  }
  return out
}

function dayLabel(iso: string, isZH: boolean) {
  const d = new Date(`${iso}T00:00:00Z`)
  const dow = d.getUTCDay()
  const wd = (isZH ? ['日', '一', '二', '三', '四', '五', '六'] : ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'])[dow]
  return { wd, dm: `${d.getUTCDate()}/${d.getUTCMonth() + 1}`, weekend: dow === 0 || dow === 6 }
}

type EditState = {
  staffId: string
  staffName: string
  staffRank: string
  date: string
  shiftType: string
  tasks: string[]
  isNew?: boolean
  wasWorking?: boolean
}

type SaveItem = {
  id: string
  type: 'create' | 'edit' | 'delete' | 'event'
  title: string
  subtitle: string
  createdAt: string
}

// Turn one machine reason into something a manager can act on. Anything the UI
// has no wording for still shows its reason code rather than being swallowed —
// a silent rejection is worse than an ugly one.
function reasonText(issue: RuleIssue, isZH: boolean): string {
  switch (issue.reason) {
    case 'rank':
      return isZH
        ? `職級不符（需 ${issue.required}，實為 ${issue.actual}）`
        : `wrong rank — needs ${issue.required}, this is ${issue.actual}`
    case 'shift_type':
      return isZH
        ? `更別不符（此任務屬 ${issue.required} 更）`
        : `wrong shift — that code belongs to the ${issue.required} shift`
    case 'medication_audit':
      return isZH ? '未通過藥物審核' : 'not medication-audited'
    case 'unaudited_external':
      return isZH
        ? `未審核外援僅可做 ${issue.allowed_task_codes?.join(' / ')}`
        : `unaudited external staff may only do ${issue.allowed_task_codes?.join(' / ')}`
    case 'qualification_all_of':
      return isZH
        ? `缺少資格：${issue.missing?.join('、')}`
        : `missing qualification: ${issue.missing?.join(', ')}`
    case 'qualification_any_of':
      return isZH ? '缺少任一必要資格' : 'missing one of the required qualifications'
    case 'qualification_none_of':
      return isZH
        ? `資格互斥：${issue.blocked?.join('、')}`
        : `blocked by qualification: ${issue.blocked?.join(', ')}`
    case 'new_staff_restricted':
      return isZH ? '新入職員工需導師陪同' : 'new staff need a mentor for this duty'
    case 'unknown_task':
      return isZH ? '任務不在任務字典內' : 'not in the task dictionary'
    case 'unit':
    case 'shift_unit':
      return isZH ? '單位不符' : 'wrong unit'
    default:
      return issue.message || issue.reason || (isZH ? '不符合規則' : 'not allowed')
  }
}

function toMinutes(hhmm?: string | null): number | null {
  if (!hhmm) return null
  const [h, m] = hhmm.slice(0, 5).split(':').map(Number)
  return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null
}

/**
 * Mirrors `shift_type_matches` on the server.
 *
 * A split shift (A/N) is two duty windows, so a morning code genuinely belongs
 * on that cell. Filtering it out of the picker would hide a duty the rules
 * accept — the manager would think it was forbidden rather than simply absent.
 */
function shiftCovers(required: string | null | undefined, shiftType: string,
                     defs: ShiftDef[]): boolean {
  if (!required || required === shiftType) return true
  const actual = defs.find((d) => d.shift_type === shiftType)
  if (!actual?.segments?.length) return false
  const target = defs.find((d) => d.shift_type === required)
  const start = toMinutes(target?.start_time)
  const end = toMinutes(target?.end_time)
  if (start === null || end === null) return false
  return actual.segments.some((seg) => {
    const segStart = toMinutes(seg.start)
    if (segStart === null) return false
    // The window may wrap past midnight, in which case it is two spans.
    return end <= start
      ? segStart >= start || segStart < end
      : segStart >= start && segStart < end
  })
}

function canSeeTask(actualRank: string, task: TaskDefOut, shiftType: string,
                    defs: ShiftDef[]): boolean {
  if (!shiftCovers(task.shift_type, shiftType, defs)) return false
  if (!task.required_rank || task.required_rank === actualRank) return true
  return new Set([actualRank, task.required_rank]).size === 2
    && [actualRank, task.required_rank].every((rank) => rank === 'CW' || rank === 'HCA')
}

export function RealRosterBoard() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const [periods, setPeriods] = useState<PeriodOut[]>([])
  const [periodId, setPeriodId] = useState('')
  const [versions, setVersions] = useState<VersionOut[]>([])
  const [versionId, setVersionId] = useState('') // '' = default (latest manual)
  const [grid, setGrid] = useState<RosterGrid | null>(null)
  const [shiftDefs, setShiftDefs] = useState<ShiftDef[]>([])
  const [taskDefs, setTaskDefs] = useState<TaskDefOut[]>([])
  const [scores, setScores] = useState<Record<string, OptionScoreOut>>({})

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [editing, setEditing] = useState<EditState | null>(null)
  const [cellIssues, setCellIssues] = useState<RuleIssue[]>([])
  const [newPeriodOpen, setNewPeriodOpen] = useState(false)
  const [validation, setValidation] = useState<ValidationOut | null>(null)

  const [aiOpen, setAiOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiOptions, setAiOptions] = useState<RosterOption[] | null>(null)
  const [aiStatus, setAiStatus] = useState('')
  const [aiError, setAiError] = useState('')
  const [publishingId, setPublishingId] = useState('')
  const [publishedIds, setPublishedIds] = useState<Set<string>>(new Set())
  const [publishError, setPublishError] = useState('')
  const [createEventOpen, setCreateEventOpen] = useState(false)
  const [pendingLog, setPendingLog] = useState<SaveItem[]>([])
  const [publishedLog, setPublishedLog] = useState<SaveItem[]>([])
  const [showSaveList, setShowSaveList] = useState(false)
  const [showPublishList, setShowPublishList] = useState(false)
  const gridRequestRef = useRef(0)
  const validationRequestRef = useRef(0)

  const T = {
    period: isZH ? '週期' : 'Period', newPeriod: isZH ? '＋ 新週期' : '＋ New period',
    version: isZH ? '版本' : 'Version', manual: isZH ? '手動' : 'Manual',
    ai: isZH ? '🤖 AI 更表建議' : '🤖 AI Roster Suggest', aiBusy: isZH ? '🤖 生成中…' : '🤖 Generating…',
    validate: isZH ? '驗證' : 'Validate', saveDraft: isZH ? '儲存草稿' : 'Save draft',
    publish: isZH ? '發佈' : 'Publish', staff: isZH ? '員工' : 'Staff',
    empty: isZH ? '此週期尚無更表資料。點擊格子開始編輯。' : 'No shifts yet. Click a cell to start editing.',
    noPeriods: isZH ? '尚無更表週期，請先建立一個。' : 'No roster periods yet - create one to begin.',
    readonly: isZH ? '（唯讀 - 已發佈或 AI 方案）' : '(read-only - published or AI option)',
    edit: isZH ? '編輯更次' : 'Edit shift', clear: isZH ? '清除' : 'Clear',
    save: isZH ? '儲存' : 'Save', cancel: isZH ? '取消' : 'Cancel', tasks: isZH ? '任務' : 'Tasks',
    passes: isZH ? '通過' : 'Passes', fails: isZH ? '不通過' : 'Fails',
    start: isZH ? '開始日期' : 'Start', end: isZH ? '結束日期' : 'End', create: isZH ? '建立' : 'Create',
    cycle: isZH ? '週期類型' : 'Cycle',
    rejected: isZH ? '此更次不可指派以下任務' : 'These tasks are not allowed on this shift',
    createShift: isZH ? '➕ 新增更次' : '➕ Create Shift',
    createEvent: isZH ? '📅 新增特別事項' : '📅 Create Special Event',
    saveList: isZH ? '儲存清單' : 'Save List',
    publishList: isZH ? '發佈記錄' : 'Publish List',
    saveListTitle: isZH ? '儲存清單' : 'Save List',
    saveListEmpty: isZH ? '暫無未發佈的更改' : 'No unpublished changes',
    publishListTitle: isZH ? '發佈記錄' : 'Publish List',
    publishListEmpty: isZH ? '暫無發佈記錄' : 'No published records yet',
    actionEdit: isZH ? '編輯更次' : 'Edit shift',
    actionCreate: isZH ? '新增更次' : 'New shift',
    actionDelete: isZH ? '刪除更次' : 'Delete shift',
    actionEvent: isZH ? '新增特別事項' : 'New special event',
    staffLabel: isZH ? '員工' : 'Staff',
    dateLabel: isZH ? '日期' : 'Date',
  }

  const flash = (m: string) => { setNotice(m); setError(''); window.setTimeout(() => setNotice(''), 2500) }

  const formatNow = () => new Date().toLocaleTimeString(isZH ? 'zh-HK' : 'en-HK', { hour: '2-digit', minute: '2-digit' })
  const logChange = (type: SaveItem['type'], title: string, subtitle: string) => {
    setPendingLog((prev) => [{ id: `${prev.length}-${Date.now()}`, type, title, subtitle, createdAt: formatNow() }, ...prev])
  }

  // ── loaders ──────────────────────────────────────────────────────────────
  useEffect(() => () => {
    gridRequestRef.current += 1
    validationRequestRef.current += 1
  }, [])

  useEffect(() => {
    api.shiftDefinitions().then(setShiftDefs).catch(() => {})
    api.taskDefinitions().then(setTaskDefs).catch(() => {})
  }, [])

  useEffect(() => {
    api.rosterPeriods()
      .then((ps) => { setPeriods(ps); setPeriodId((prev) => prev || (ps[0]?.id ?? '')) })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load periods'))
  }, [])

  const loadVersions = useCallback(async (pid: string) => {
    const vs = await api.rosterVersions(pid)
    setVersions(vs)
    try {
      const cmp = await api.compareOptions(pid)
      const map: Record<string, OptionScoreOut> = {}
      cmp.options.forEach((o) => { map[o.roster_version_id] = o })
      setScores(map)
    } catch { setScores({}) }
  }, [])

  useEffect(() => {
    if (!periodId) return
    setVersionId('')
    loadVersions(periodId).catch(() => {})
  }, [periodId, loadVersions])

  const validateVersion = useCallback(async (vid: string) => {
    const requestId = ++validationRequestRef.current
    try {
      const result = await api.validateRoster(vid)
      if (requestId === validationRequestRef.current) setValidation(result)
      return result
    } catch (e) {
      // A newer version or manual re-check supersedes this request.
      if (requestId !== validationRequestRef.current) return null
      throw e
    }
  }, [])

  const loadGrid = useCallback(async (pid: string, vid: string) => {
    const requestId = ++gridRequestRef.current
    // The next grid owns the validation strip; invalidate any older response.
    validationRequestRef.current += 1
    setLoading(true); setError(''); setValidation(null)
    try {
      const nextGrid = await api.rosterGrid(pid, vid ? { versionId: vid } : undefined)
      if (requestId !== gridRequestRef.current) return
      setGrid(nextGrid)
      setLoading(false)
      if (nextGrid.version_id) {
        try {
          await validateVersion(nextGrid.version_id)
        } catch (e) {
          if (requestId === gridRequestRef.current) {
            setError(e instanceof Error ? e.message : 'Validation failed')
          }
        }
      }
    } catch (e) {
      if (requestId === gridRequestRef.current) {
        setError(e instanceof Error ? e.message : 'Failed to load roster')
      }
    } finally {
      if (requestId === gridRequestRef.current) setLoading(false)
    }
  }, [validateVersion])

  useEffect(() => { if (periodId) loadGrid(periodId, versionId) }, [periodId, versionId, loadGrid])

  // ── derived ──────────────────────────────────────────────────────────────
  const currentVersion = useMemo(
    () => (versionId ? versions.find((v) => v.id === versionId) : versions.find((v) => v.version_type === 'manual')) ?? null,
    [versions, versionId],
  )
  const activeVersionId = grid?.version_id ?? currentVersion?.id ?? ''
  // Only the manual draft is hand-editable; A/B/C solver options are read-only
  // results you publish, and published/archived versions are locked.
  const editable = currentVersion?.version_type === 'manual' && currentVersion?.status === 'draft'

  const columns = useMemo(() => {
    if (grid?.period_start && grid?.period_end) return eachDate(grid.period_start, grid.period_end)
    return grid?.dates ?? []
  }, [grid])

  // staffId → (date → cell)
  const cellLookup = useMemo(() => {
    const m = new Map<string, Map<string, RosterCell>>()
    grid?.rows.forEach((r) => {
      const byDate = new Map<string, RosterCell>()
      r.cells.forEach((c) => byDate.set(c.date, c))
      m.set(r.staff.id, byDate)
    })
    return m
  }, [grid])

  const eventsByDate = useMemo(() => {
    const grouped = new Map<string, NonNullable<RosterGrid['events']>>()
    grid?.events.forEach((event) => {
      grouped.set(event.event_date, [...(grouped.get(event.event_date) ?? []), event])
    })
    return grouped
  }, [grid])

  // ── actions ──────────────────────────────────────────────────────────────
  const refresh = useCallback(async () => {
    await Promise.all([loadVersions(periodId), loadGrid(periodId, versionId)])
  }, [periodId, versionId, loadVersions, loadGrid])

  async function saveCell() {
    if (!editing || !activeVersionId) return
    setBusy('cell')
    setCellIssues([])
    try {
      if (!editing.shiftType) await api.clearCell(activeVersionId, editing.staffId, editing.date)
      else await api.upsertCell({
        roster_version_id: activeVersionId, staff_id: editing.staffId,
        date: editing.date, shift_type: editing.shiftType, tasks: editing.tasks,
      })
      const label = !editing.shiftType
        ? T.actionDelete
        : editing.wasWorking ? T.actionEdit : T.actionCreate
      logChange(
        !editing.shiftType ? 'delete' : editing.wasWorking ? 'edit' : 'create',
        label,
        `${editing.staffName} · ${editing.date}${editing.shiftType ? ` · ${editing.shiftType}` : ''}`,
      )
      setEditing(null)
      await loadGrid(periodId, versionId)
    } catch (e) {
      // An eligibility refusal is a list of fixable reasons, so keep the dialog
      // open and show them against the labels instead of closing on a one-liner.
      if (e instanceof ApiRuleError) setCellIssues(e.issues)
      else setError(e instanceof Error ? e.message : 'Save failed')
    } finally { setBusy('') }
  }

  async function handleValidate() {
    if (!activeVersionId) return
    setBusy('validate'); setError('')
    try { await validateVersion(activeVersionId) }
    catch (e) { setError(e instanceof Error ? e.message : 'Validation failed') } finally { setBusy('') }
  }

  async function handleSaveDraft() {
    if (!activeVersionId) return
    setBusy('save')
    try {
      await api.saveDraft(activeVersionId)
      try { await validateVersion(activeVersionId) } catch { /* draft remains saved */ }
      flash(isZH ? '已儲存草稿' : 'Draft saved')
    }
    catch (e) { setError(e instanceof Error ? e.message : 'Save failed') } finally { setBusy('') }
  }

  async function handlePublish() {
    if (!activeVersionId) return
    setBusy('publish'); setError('')
    try {
      await api.publish(activeVersionId)
      flash(isZH ? '已發佈' : 'Published')
      setPublishedLog((prev) => [...pendingLog, ...prev])
      setPendingLog([])
      await refresh()
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Publish failed'
      try { await validateVersion(activeVersionId) } catch { /* preserve the publish error */ }
      setError(message)
    } finally { setBusy('') }
  }

  async function handleAI() {
    if (aiLoading || !periodId) return
    setAiOpen(true); setAiError(''); setPublishError(''); setAiOptions(null)
    setAiLoading(true); setAiStatus('pending')
    try {
      const options = await optimizeAndPoll(periodId, { onStatus: setAiStatus })
      setAiOptions(options)
      await loadVersions(periodId) // A/B/C versions now exist → tabs + score badges
    } catch (e) {
      setAiError(e instanceof Error ? e.message : 'Optimization failed')
    } finally { setAiLoading(false) }
  }

  async function handlePublishOption(vid: string) {
    setPublishingId(vid); setPublishError('')
    try {
      await api.publish(vid)
      setPublishedIds((prev) => new Set(prev).add(vid))
      await refresh()
    } catch (e) { setPublishError(e instanceof Error ? e.message : 'Publish failed') } finally { setPublishingId('') }
  }

  function handleCreateShift() {
    if (!grid?.rows.length || !columns.length) return
    const first = grid.rows[0].staff
    setCellIssues([])
    setEditing({
      staffId: first.id, staffName: first.name_en || first.name, staffRank: first.rank,
      date: columns[0], shiftType: '', tasks: [], isNew: true, wasWorking: false,
    })
  }

  function handleEventCreated(title: string) {
    setCreateEventOpen(false)
    logChange('event', T.actionEvent, title)
    loadGrid(periodId, versionId)
  }

  // ── render ───────────────────────────────────────────────────────────────
  const periodLabel = grid?.period_start && grid?.period_end ? `${grid.period_start} → ${grid.period_end}` : ''

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="bg-white border-b border-gray-200 px-5 py-3 flex-shrink-0 space-y-2.5">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-bold text-gray-900">{isZH ? '更表' : 'Roster'}</h1>

          <label className="text-xs text-gray-500">{T.period}</label>
          <select
            value={periodId}
            onChange={(e) => setPeriodId(e.target.value)}
            className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white max-w-[220px]"
          >
            {periods.map((p) => (
              <option key={p.id} value={p.id}>{p.period_start} → {p.period_end} · {p.status}</option>
            ))}
          </select>
          <button onClick={() => setNewPeriodOpen(true)}
            className="text-xs px-2.5 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50">{T.newPeriod}</button>

          <div className="ml-auto flex items-center gap-2">
            <button onClick={handleAI} disabled={aiLoading || !periodId}
              className="px-3.5 py-1.5 text-white text-xs font-semibold rounded-lg disabled:opacity-60"
              style={{ background: PINK }}>{aiLoading ? T.aiBusy : T.ai}</button>
          </div>
        </div>

        {/* Version tabs + actions */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500">{T.version}:</span>
          {versions.map((v) => {
            const sc = scores[v.id]
            const active = v.id === activeVersionId
            const label = v.version_type === 'manual' ? T.manual : v.version_type
            return (
              <button key={v.id} onClick={() => setVersionId(v.id)}
                className="px-2.5 py-1 rounded-lg text-xs font-medium border transition-all flex items-center gap-1.5"
                style={{
                  borderColor: active ? PINK : '#e5e7eb',
                  background: active ? '#fff0f5' : '#fff',
                  color: active ? PINK : '#6b7280',
                }}>
                <span>{label}</span>
                <span className="text-[9px] px-1 rounded"
                  style={{ background: v.status === 'published' ? '#dcfce7' : '#f1f5f9', color: v.status === 'published' ? '#166534' : '#64748b' }}>
                  {v.status}
                </span>
                {sc && <span className="text-[9px] font-bold" style={{ color: sc.publishable ? '#15803d' : '#be123c' }}>· {sc.constraint_score}</span>}
              </button>
            )
          })}

          <div className="ml-auto flex items-center gap-2 flex-wrap">
            <button onClick={handleCreateShift} disabled={!editable || !grid?.rows.length}
              className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
              {T.createShift}
            </button>
            <button onClick={() => setCreateEventOpen(true)} disabled={!periodId}
              className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
              {T.createEvent}
            </button>
            <button onClick={handleValidate} disabled={!activeVersionId || busy === 'validate'}
              className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
              {busy === 'validate' ? '…' : T.validate}
            </button>
            <button onClick={handleSaveDraft} disabled={!editable || busy === 'save'}
              className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
              {busy === 'save' ? '…' : T.saveDraft}
            </button>
            <button onClick={handlePublish} disabled={!activeVersionId || busy === 'publish'}
              className="text-xs px-3 py-1.5 rounded-lg text-white font-semibold disabled:opacity-50"
              style={{ background: PINK }}>
              {busy === 'publish' ? '…' : T.publish}
            </button>
            <button onClick={() => setShowSaveList((v) => !v)}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-700 font-semibold hover:bg-gray-50">
              {T.saveList} ({pendingLog.length})
            </button>
            <button onClick={() => setShowPublishList((v) => !v)}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-700 font-semibold hover:bg-gray-50">
              {T.publishList} ({publishedLog.length})
            </button>
          </div>
        </div>

        {/* status line */}
        <div className="flex items-center gap-3 min-h-[16px]">
          {periodLabel && <span className="text-[11px] text-gray-400">{periodLabel}</span>}
          {!editable && currentVersion && <span className="text-[11px] text-amber-600">{T.readonly}</span>}
          {notice && <span className="text-[11px] font-medium text-emerald-600">{notice}</span>}
          {error && <span className="text-[11px] font-medium text-rose-600">{error}</span>}
        </div>
      </div>

      {/* Validation panel */}
      {validation && (
        <div className="px-5 py-2 border-b border-gray-200 bg-white flex-shrink-0">
          <div className="flex items-center gap-2 flex-wrap text-xs">
            <span className="font-semibold" style={{ color: validation.passes ? '#15803d' : '#be123c' }}>
              {validation.passes ? `✓ ${T.passes}` : `✗ ${T.fails}`}
            </span>
            <span className="text-gray-400">· {validation.method}</span>
            {validation.hard_violation_count > 0 && (
              <span className="text-rose-600">· {validation.hard_violation_count} {isZH ? '違規' : 'violations'}</span>
            )}
            {validation.violations.slice(0, 4).map((v, i) => (
              <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-rose-50 text-rose-600 border border-rose-100">
                {v.rule_code}{v.message ? `: ${v.message}` : ''}
              </span>
            ))}
            {validation.ratio_checks.filter((c) => !c.passes).slice(0, 4).map((c, i) => (
              <span key={`r${i}`} className="text-[10px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-100">
                {c.label} - {c.actual}/{c.required}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Grid + save/publish list panel */}
      <div className={`grid gap-0 flex-1 min-h-0 ${showSaveList || showPublishList ? 'grid-cols-1 xl:grid-cols-[1fr_340px]' : 'grid-cols-1'}`}>
      <div className="min-w-0 flex-1 overflow-auto px-5 py-3">
        {!periodId ? (
          <div className="text-sm text-gray-400 p-8 text-center">{T.noPeriods}</div>
        ) : loading ? (
          <div className="text-sm text-gray-400 p-8 text-center">…</div>
        ) : grid && grid.rows.length ? (
          <table className="border-collapse bg-white rounded-xl border border-gray-200">
            <thead className="sticky top-0 z-10">
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-3 py-2 text-[10px] font-semibold text-gray-500 border-r border-gray-200 sticky left-0 bg-gray-50 z-20 w-44 min-w-44">
                  {T.staff}
                </th>
                {columns.map((iso) => {
                  const d = dayLabel(iso, isZH)
                  const dayEvents = eventsByDate.get(iso) ?? []
                  return (
                    <th key={iso} className={`px-1 py-1.5 text-center border-r border-gray-100 min-w-[54px] ${d.weekend ? 'bg-pink-50' : 'bg-gray-50'}`}>
                      <div className="text-[8px] text-gray-400">{d.wd}</div>
                      <div className="text-[11px] font-bold text-gray-700">{d.dm}</div>
                      {dayEvents.length > 0 && (
                        <div
                          className="mx-auto mt-0.5 h-1.5 w-1.5 rounded-full bg-amber-400"
                          title={dayEvents.map((event) => event.title || event.event_type).join(', ')}
                        />
                      )}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {grid.rows.map((row) => (
                <tr key={row.staff.id} className="border-t border-gray-100">
                  <td className="px-3 py-2 border-r border-gray-200 sticky left-0 bg-white z-10 w-44 min-w-44">
                    <div className="text-[12px] font-semibold text-gray-900 truncate">{row.staff.name_en || row.staff.name}</div>
                    <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
                      <span className="font-bold text-gray-500">{row.staff.rank}</span>
                      {row.staff.unit_name && <span className="truncate">· {row.staff.unit_name}</span>}
                    </div>
                  </td>
                  {columns.map((iso) => {
                    const cell = cellLookup.get(row.staff.id)?.get(iso)
                    const st = cell?.shift_type
                    const style = st ? (SHIFT_STYLE[st] ?? DEFAULT_STYLE) : null
                    return (
                      <td key={iso}
                        onClick={() => editable && (setCellIssues([]), setEditing({
                          staffId: row.staff.id, staffName: row.staff.name_en || row.staff.name,
                          staffRank: row.staff.rank,
                          date: iso, shiftType: st ?? '', tasks: cell?.tasks ?? [],
                          wasWorking: !!st,
                        }))}
                        className={`border-r border-gray-100 p-1 align-top ${editable ? 'cursor-pointer hover:bg-pink-50/40' : ''}`}>
                        {st ? (
                          <div className="rounded px-1 py-0.5 text-[9px] font-bold text-center"
                            style={{ background: style!.bg, color: style!.fg }}>{st}</div>
                        ) : (
                          <div className="h-4" />
                        )}
                        {cell?.tasks?.slice(0, 2).map((t) => (
                          <div key={t} className="text-[7px] text-gray-400 leading-tight truncate">• {t}</div>
                        ))}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-sm text-gray-400 p-8 text-center">{T.empty}</div>
        )}
      </div>

      {(showSaveList || showPublishList) && (
        <div className="border-l border-gray-200 bg-white overflow-auto xl:min-w-[340px]">
          {showSaveList && (
            <div className="p-4 border-b border-gray-100">
              <h3 className="text-sm font-bold text-gray-900 mb-2">{T.saveListTitle}</h3>
              <div className="space-y-2 max-h-96 overflow-auto">
                {pendingLog.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-gray-200 p-4 text-xs text-gray-400 text-center">
                    {T.saveListEmpty}
                  </div>
                ) : (
                  pendingLog.map((item) => (
                    <div key={item.id} className="rounded-xl border border-pink-100 bg-pink-50/50 p-3">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-semibold" style={{ color: PINK }}>{item.title}</span>
                        <span className="text-[10px] text-gray-400">{item.createdAt}</span>
                      </div>
                      <div className="text-[11px] text-gray-600">{item.subtitle}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {showPublishList && (
            <div className="p-4">
              <h3 className="text-sm font-bold text-gray-900 mb-2">{T.publishListTitle}</h3>
              <div className="space-y-2 max-h-96 overflow-auto">
                {publishedLog.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-gray-200 p-4 text-xs text-gray-400 text-center">
                    {T.publishListEmpty}
                  </div>
                ) : (
                  publishedLog.map((item) => (
                    <div key={item.id} className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-semibold text-emerald-700">{item.title}</span>
                        <span className="text-[10px] text-gray-400">{item.createdAt}</span>
                      </div>
                      <div className="text-[11px] text-gray-600">{item.subtitle}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      )}
      </div>

      {/* Cell editor */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6" style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={() => setEditing(null)}>
          <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
            <div className="text-sm font-bold text-gray-900">{editing.isNew ? T.createShift : T.edit}</div>

            {editing.isNew ? (
              <div className="grid grid-cols-2 gap-2 mb-4 mt-2">
                <label className="block">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{T.staffLabel}</span>
                  <select
                    value={editing.staffId}
                    onChange={(e) => {
                      const s = grid?.rows.find((r) => r.staff.id === e.target.value)?.staff
                      if (!s) return
                      const cell = cellLookup.get(s.id)?.get(editing.date)
                      setEditing({
                        ...editing, staffId: s.id, staffName: s.name_en || s.name, staffRank: s.rank,
                        shiftType: cell?.shift_type ?? '', tasks: cell?.tasks ?? [], wasWorking: !!cell?.shift_type,
                      })
                    }}
                    className="w-full mt-1 px-2 py-1.5 rounded-lg border border-gray-200 text-xs bg-white">
                    {grid?.rows.map((r) => (
                      <option key={r.staff.id} value={r.staff.id}>{r.staff.name_en || r.staff.name}</option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{T.dateLabel}</span>
                  <select
                    value={editing.date}
                    onChange={(e) => {
                      const cell = cellLookup.get(editing.staffId)?.get(e.target.value)
                      setEditing({
                        ...editing, date: e.target.value,
                        shiftType: cell?.shift_type ?? '', tasks: cell?.tasks ?? [], wasWorking: !!cell?.shift_type,
                      })
                    }}
                    className="w-full mt-1 px-2 py-1.5 rounded-lg border border-gray-200 text-xs bg-white">
                    {columns.map((iso) => <option key={iso} value={iso}>{iso}</option>)}
                  </select>
                </label>
              </div>
            ) : (
              <div className="text-xs text-gray-500 mb-4">{editing.staffName} · {editing.date}</div>
            )}

            <div className="flex flex-wrap gap-1.5 mb-4">
              {shiftDefs.map((sd) => {
                const sel = editing.shiftType === sd.shift_type
                const style = SHIFT_STYLE[sd.shift_type] ?? DEFAULT_STYLE
                return (
                  <button key={sd.id} onClick={() => setEditing({
                    ...editing, shiftType: sel ? '' : sd.shift_type, tasks: [],
                  })}
                    className="px-2.5 py-1 rounded-lg text-xs font-bold border-2 transition-all"
                    style={{ background: style.bg, color: style.fg, borderColor: sel ? PINK : 'transparent' }}
                    title={sd.label ?? sd.shift_type}>
                    {sd.shift_type}
                  </button>
                )
              })}
            </div>

            {taskDefs.length > 0 && editing.shiftType && (
              <div className="mb-4">
                <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1.5">{T.tasks}</div>
                <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                  {taskDefs.filter((td) => canSeeTask(
                    editing.staffRank, td, editing.shiftType, shiftDefs,
                  )).map((td) => {
                    const label = td.task_name || td.task_code
                    const on = editing.tasks.includes(label)
                    return (
                      <button key={td.id}
                        onClick={() => setEditing({
                          ...editing,
                          tasks: on ? editing.tasks.filter((t) => t !== label) : [...editing.tasks, label],
                        })}
                        className="px-2 py-0.5 rounded-full text-[10px] border transition-all"
                        style={{ borderColor: on ? PINK : '#e5e7eb', background: on ? '#fff0f5' : '#fff', color: on ? PINK : '#6b7280' }}>
                        {label}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {cellIssues.length > 0 && (
              <div className="mb-4 rounded-lg border p-2.5"
                   style={{ background: '#fff1f2', borderColor: '#fecdd3' }}>
                <div className="text-[10px] font-bold uppercase tracking-wider mb-1"
                     style={{ color: '#be123c' }}>
                  {T.rejected}
                </div>
                <ul className="space-y-1">
                  {cellIssues.map((issue, i) => (
                    <li key={i} className="text-[11px]" style={{ color: '#9f1239' }}>
                      {issue.task_label && (
                        <span className="font-semibold">{issue.task_label}: </span>
                      )}
                      {(issue.issues?.length ? issue.issues : [issue])
                        .map((r) => reasonText(r, isZH))
                        .join(' · ')}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <button onClick={() => setEditing({ ...editing, shiftType: '', tasks: [] })}
                className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50">{T.clear}</button>
              <button onClick={() => setEditing(null)}
                className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">{T.cancel}</button>
              <button onClick={saveCell} disabled={busy === 'cell'}
                className="px-4 py-1.5 text-xs rounded-lg text-white font-semibold disabled:opacity-60" style={{ background: PINK }}>
                {busy === 'cell' ? '…' : T.save}
              </button>
            </div>
          </div>
        </div>
      )}

      {newPeriodOpen && (
        <NewPeriodModal
          isZH={isZH}
          onClose={() => setNewPeriodOpen(false)}
          onCreated={(pid) => { setNewPeriodOpen(false); setPeriodId(pid); api.rosterPeriods().then(setPeriods).catch(() => {}) }}
        />
      )}

      {aiOpen && (
        <AiOptionsModal
          options={aiOptions} loading={aiLoading} status={aiStatus} error={aiError}
          publishError={publishError} periodLabel={periodLabel} isZH={isZH}
          publishingId={publishingId} publishedIds={publishedIds}
          onPublish={handlePublishOption} onClose={() => setAiOpen(false)}
        />
      )}

      {createEventOpen && (
        <CreateEventModal
          isZH={isZH}
          defaultDate={columns[0] ?? new Date().toISOString().slice(0, 10)}
          onClose={() => setCreateEventOpen(false)}
          onCreated={handleEventCreated}
        />
      )}
    </div>
  )
}

function NewPeriodModal({ isZH, onClose, onCreated }: {
  isZH: boolean; onClose: () => void; onCreated: (periodId: string) => void
}) {
  const today = new Date().toISOString().slice(0, 10)
  const plus = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
  const [start, setStart] = useState(today)
  const [end, setEnd] = useState(plus(27))
  const [cycle, setCycle] = useState('28day')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function create() {
    setBusy(true); setErr('')
    try {
      const res = await api.createPeriod({ period_start: start, period_end: end, cycle_type: cycle, create_manual_version: true })
      onCreated(res.period.id)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Create failed'); setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onClose}>
      <div className="bg-white w-full max-w-sm rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="text-sm font-bold text-gray-900 mb-4">{isZH ? '新增更表週期' : 'New roster period'}</div>
        <div className="space-y-3">
          <label className="block">
            <span className="text-[11px] font-semibold text-gray-500">{isZH ? '開始日期' : 'Start'}</span>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-200 text-sm" />
          </label>
          <label className="block">
            <span className="text-[11px] font-semibold text-gray-500">{isZH ? '結束日期' : 'End'}</span>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-200 text-sm" />
          </label>
          <label className="block">
            <span className="text-[11px] font-semibold text-gray-500">{isZH ? '週期類型' : 'Cycle'}</span>
            <select value={cycle} onChange={(e) => setCycle(e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-200 text-sm bg-white">
              <option value="28day">28day</option>
              <option value="natural_month">natural_month</option>
            </select>
          </label>
          {err && <div className="text-xs text-rose-600">{err}</div>}
        </div>
        <div className="flex gap-2 justify-end mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">
            {isZH ? '取消' : 'Cancel'}
          </button>
          <button onClick={create} disabled={busy}
            className="px-4 py-1.5 text-xs rounded-lg text-white font-semibold disabled:opacity-60" style={{ background: PINK }}>
            {busy ? '…' : (isZH ? '建立' : 'Create')}
          </button>
        </div>
      </div>
    </div>
  )
}
