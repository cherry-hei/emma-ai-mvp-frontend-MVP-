'use client'

// Design: Emma clinical warmth. This is the single roster workspace for
// generate → edit → deterministic rule check → manager publish.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiRuleError, api, optimizeAndPoll } from '@/lib/api'
import type {
  OptionScoreOut, PeriodOut, RosterCell, RosterGrid, RosterOption, RuleIssue,
  ShiftDef, TaskDefOut, ValidationOut, VersionOut,
} from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'
import { CreateShiftModal } from '@/components/modals/CreateShiftModal'
import { canSeeTask, reasonText } from '@/lib/shiftRules'
import { AiOptionsModal } from './AiOptionsModal'
import { CreateEventModal } from './CreateEventModal'
import { BatchCreateShiftModal } from '@/components/modals/BatchCreateShiftModal'

const PINK = '#E8187A'

// Which period the scheduler was last working on. Without this the board reopens
// on `periods[0]`, and `list_periods` orders by `period_start desc` - so a home
// that has planned a future cycle lands on that empty cycle every time and the
// current period's saved draft reads as "my edits are gone". The draft was never
// lost; the board was simply pointed at a different period.
const PERIOD_KEY = 'emma.roster.periodId'
const LOG_KEY = 'emma.roster.saveLog'

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/**
 * Last period the user chose, if it still exists; else the period containing
 * today; else the most recent one that has already started; else the newest.
 *
 * The fallbacks matter on a fresh browser (or after the remembered period is
 * deleted): "the cycle we are living in" is the one a scheduler means by
 * "the roster", not the furthest-out one that happens to sort first.
 */
function pickPeriod(ps: PeriodOut[]): string {
  if (!ps.length) return ''
  let remembered: string | null = null
  try { remembered = window.localStorage.getItem(PERIOD_KEY) } catch { /* private mode */ }
  if (remembered && ps.some((p) => p.id === remembered)) return remembered
  const now = today()
  const current = ps.find((p) => p.period_start <= now && now <= p.period_end)
  if (current) return current.id
  // `ps` is already newest-first by period_start, so the first one that has
  // started is the most recent past period.
  const started = ps.find((p) => p.period_start <= now)
  return (started ?? ps[0]).id
}

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
  wasWorking?: boolean
}

type SaveItem = {
  id: string
  type: 'create' | 'edit' | 'delete' | 'event'
  title: string
  subtitle: string
  createdAt: string
}

type FocusedCell = { staffId: string; date: string } | null

type ViolationGroup = {
  key: string
  ruleCode: string
  items: NonNullable<ValidationOut['violations']>
}

type RatioGroup = {
  key: string
  label: string
  rank?: string | null
  items: NonNullable<ValidationOut['ratio_checks']>
}

function groupViolations(items: NonNullable<ValidationOut['violations']>): ViolationGroup[] {
  const grouped = new Map<string, ViolationGroup>()
  items.forEach((item) => {
    const key = item.rule_code || 'unclassified_rule'
    const existing = grouped.get(key)
    if (existing) existing.items.push(item)
    else grouped.set(key, { key, ruleCode: key, items: [item] })
  })
  return [...grouped.values()].sort((a, b) => b.items.length - a.items.length || a.ruleCode.localeCompare(b.ruleCode))
}

function groupRatios(items: NonNullable<ValidationOut['ratio_checks']>): RatioGroup[] {
  const grouped = new Map<string, RatioGroup>()
  items.forEach((item) => {
    const key = `${item.label}|${item.rank || ''}`
    const existing = grouped.get(key)
    if (existing) existing.items.push(item)
    else grouped.set(key, { key, label: item.label, rank: item.rank, items: [item] })
  })
  return [...grouped.values()].sort((a, b) => b.items.length - a.items.length || a.label.localeCompare(b.label))
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
  const [ruleReviewOpen, setRuleReviewOpen] = useState(false)
  const [focusedCell, setFocusedCell] = useState<FocusedCell>(null)
  const [expandedRuleGroups, setExpandedRuleGroups] = useState<Set<string>>(new Set())

  const [aiOpen, setAiOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiOptions, setAiOptions] = useState<RosterOption[] | null>(null)
  const [aiStatus, setAiStatus] = useState('')
  const [aiError, setAiError] = useState('')
  const [publishingId, setPublishingId] = useState('')
  const [publishedIds, setPublishedIds] = useState<Set<string>>(new Set())
  const [publishError, setPublishError] = useState('')
  const [createEventOpen, setCreateEventOpen] = useState(false)
  const [createShiftOpen, setCreateShiftOpen] = useState(false)
  const [batchShiftOpen, setBatchShiftOpen] = useState(false)
  const [pendingLog, setPendingLog] = useState<SaveItem[]>([])
  const [publishedLog, setPublishedLog] = useState<SaveItem[]>([])
  const [showSaveList, setShowSaveList] = useState(false)
  const [showPublishList, setShowPublishList] = useState(false)
  const [filterRank, setFilterRank] = useState('ALL')
  const [filterFloor, setFilterFloor] = useState('ALL')
  const [filterSearch, setFilterSearch] = useState('')
  const gridRequestRef = useRef(0)
  const validationRequestRef = useRef(0)
  // Which period's logs are currently in state, so the writer below never saves
  // an empty initial state over a stored list before the reader has run.
  const logsHydrated = useRef('')

  const T = {
    period: isZH ? '週期' : 'Period', newPeriod: isZH ? '＋ 新週期' : '＋ New period',
    version: isZH ? '版本' : 'Version', manual: isZH ? '手動' : 'Manual',
    ai: isZH ? '生成更表方案' : 'Generate roster options', aiBusy: isZH ? '生成中…' : 'Generating…',
    validate: isZH ? '執行規則檢查' : 'Run rule checks', saveDraft: isZH ? '儲存草稿' : 'Save draft',
    publish: isZH ? '批准並發佈' : 'Approve & publish', staff: isZH ? '員工' : 'Staff',
    filterRank: isZH ? '職級' : 'Rank',
    filterFloor: isZH ? '樓層/單位' : 'Floor/Unit',
    filterSearch: isZH ? '搜尋員工…' : 'Search staff…',
    allRanks: isZH ? '所有職級' : 'All Ranks',
    allFloors: isZH ? '所有樓層' : 'All Floors',
    totalHrs: isZH ? '總時數' : 'Total Hrs',
    exportRoster: isZH ? '📥 匯出更表' : '📥 Export Roster',
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
    batchCreate: isZH ? '📋 批量排更' : '📋 Batch Create',
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
      .then((ps) => { setPeriods(ps); setPeriodId((prev) => prev || pickPeriod(ps)) })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load periods'))
  }, [])

  // Remember the choice so leaving the page - or signing out and back in -
  // returns to the same period rather than to whichever one sorts first.
  useEffect(() => {
    if (!periodId) return
    try { window.localStorage.setItem(PERIOD_KEY, periodId) } catch { /* private mode */ }
  }, [periodId])

  // The save/publish lists are a per-period record of what this scheduler has
  // changed since the last publish. They outlive a page navigation for the same
  // reason the period does: a list that empties itself looks like lost work.
  useEffect(() => {
    if (!periodId) return
    let stored: { pending?: SaveItem[]; published?: SaveItem[] } = {}
    try { stored = JSON.parse(window.localStorage.getItem(`${LOG_KEY}:${periodId}`) || '{}') } catch { /* ignore */ }
    setPendingLog(Array.isArray(stored.pending) ? stored.pending : [])
    setPublishedLog(Array.isArray(stored.published) ? stored.published : [])
    logsHydrated.current = periodId
  }, [periodId])

  useEffect(() => {
    if (!periodId || logsHydrated.current !== periodId) return
    try {
      window.localStorage.setItem(`${LOG_KEY}:${periodId}`, JSON.stringify({
        pending: pendingLog.slice(0, 100), published: publishedLog.slice(0, 100),
      }))
    } catch { /* quota or private mode - the lists are a convenience, not a record */ }
  }, [periodId, pendingLog, publishedLog])

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

  const blockingViolations = useMemo(
    () => (validation?.violations ?? []).filter((item) => !item.resolved && item.severity.toLowerCase() === 'hard'),
    [validation],
  )
  const warningViolations = useMemo(
    () => (validation?.violations ?? []).filter((item) => !item.resolved && item.severity.toLowerCase() !== 'hard'),
    [validation],
  )
  const failingRatios = useMemo(
    () => (validation?.ratio_checks ?? []).filter((item) => !item.passes),
    [validation],
  )
  const blockingCount = validation?.hard_violation_count ?? 0
  const warningCount = warningViolations.length + failingRatios.length
  const passingCheckCount = (validation?.ratio_checks ?? []).filter((item) => item.passes).length
  const blockingGroups = useMemo(() => groupViolations(blockingViolations), [blockingViolations])
  const warningGroups = useMemo(() => groupViolations(warningViolations), [warningViolations])
  const ratioGroups = useMemo(() => groupRatios(failingRatios), [failingRatios])

  const issueCountByCell = useMemo(() => {
    const counts = new Map<string, number>()
    ;(validation?.violations ?? []).forEach((item) => {
      if (!item.resolved && item.staff_id && item.date) {
        const key = `${item.staff_id}|${item.date}`
        counts.set(key, (counts.get(key) ?? 0) + 1)
      }
    })
    return counts
  }, [validation])

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
    if (!validation || blockingCount > 0) {
      setRuleReviewOpen(true)
      return
    }
    if (warningCount > 0 && !window.confirm(isZH
      ? `現時有${warningCount}項警告。規則引擎沒有阻止發佈；是否由院長確認後繼續？`
      : `There are ${warningCount} warnings. The rules engine does not block publishing; continue with manager confirmation?`)) return
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

  // "➕ Create Shift" opens the full dialog - staff, day, shift type and a task
  // schedule with times. Clicking a cell still opens the quick inline editor
  // below; that one is for changing a code in two clicks, this one is for
  // planning a shift's work.
  function handleCreateShift() {
    if (!grid?.rows.length || !columns.length) return
    setCreateShiftOpen(true)
  }

  function handleEventCreated(title: string) {
    setCreateEventOpen(false)
    logChange('event', T.actionEvent, title)
    loadGrid(periodId, versionId)
  }

  function focusIssue(staffId?: string | null, date?: string | null) {
    if (!staffId || !date) return
    const row = grid?.rows.find((item) => item.staff.id === staffId)
    if (row) {
      setFilterRank('ALL')
      setFilterFloor('ALL')
      setFilterSearch(row.staff.name_en || row.staff.name || row.staff.rank)
    }
    setFocusedCell({ staffId, date })
    setRuleReviewOpen(false)
    window.setTimeout(() => document.getElementById(`roster-cell-${staffId}-${date}`)?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' }), 80)
  }

  function explainRule(rule: string, date?: string | null) {
    const params = new URLSearchParams({ mode: 'compliance', rule })
    if (activeVersionId) params.set('roster_version_id', activeVersionId)
    if (date) params.set('date', date.slice(0, 10))
    params.set('question', isZH
      ? `請根據deterministic evidence解釋更表規則 ${rule} 的結果、影響及需要處理的步驟。`
      : `Explain roster rule ${rule}, its impact and the next action using deterministic evidence only.`)
    window.location.assign(`/insights?${params.toString()}`)
  }

  function toggleRuleGroup(key: string) {
    setExpandedRuleGroups((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // ── render ───────────────────────────────────────────────────────────────
  const periodLabel = grid?.period_start && grid?.period_end ? `${grid.period_start} → ${grid.period_end}` : ''

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="bg-white border-b border-gray-200 px-5 py-3 flex-shrink-0 space-y-2.5">
        <div className="flex items-center gap-3 flex-wrap">
          <div>
            <h1 className="text-xl font-bold text-gray-900">{isZH ? '更表工作區' : 'Roster Workspace'}</h1>
            <p className="mt-0.5 text-[10px] text-gray-400">{isZH ? '生成方案 → 編輯更表 → 規則檢查 → 院長批准發佈' : 'Generate options → edit roster → run rule checks → manager approval'}</p>
          </div>

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

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label={isZH ? '更表工作流程' : 'Roster workflow'}>
          {[
            isZH ? '1 生成方案' : '1 Generate',
            isZH ? '2 選擇及編輯' : '2 Select & edit',
            isZH ? '3 規則檢查' : '3 Rule check',
            isZH ? '4 批准發佈' : '4 Approve',
          ].map((step, index) => (
            <div key={step} className={`rounded-lg border px-3 py-2 text-[10px] font-semibold ${index === 2 && validation ? (validation.passes ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-rose-200 bg-rose-50 text-rose-700') : 'border-slate-200 bg-slate-50 text-slate-600'}`}>
              {step}
            </div>
          ))}
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
            <button onClick={() => setBatchShiftOpen(true)} disabled={!editable || !grid?.rows.length}
              className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
              {T.batchCreate}
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
              title={blockingCount > 0 ? (isZH ? '先檢視及處理blocking rules' : 'Review and resolve blocking rules first') : undefined}
              className="text-xs px-3 py-1.5 rounded-lg text-white font-semibold disabled:opacity-50"
              style={{ background: blockingCount > 0 ? '#475569' : PINK }}>
              {busy === 'publish' ? '…' : blockingCount > 0 ? (isZH ? '發佈前檢視規則' : 'Review rules before publishing') : T.publish}
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

        {/* Filter bar */}
        {grid && grid.rows.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <select value={filterRank} onChange={(e) => setFilterRank(e.target.value)}
              className="text-xs px-2.5 py-1.5 border border-gray-200 rounded-lg bg-white">
              <option value="ALL">{T.allRanks}</option>
              {Array.from(new Set(grid.rows.map((r) => r.staff.rank))).sort().map((rank) => (
                <option key={rank} value={rank}>{rank}</option>
              ))}
            </select>
            <select value={filterFloor} onChange={(e) => setFilterFloor(e.target.value)}
              className="text-xs px-2.5 py-1.5 border border-gray-200 rounded-lg bg-white">
              <option value="ALL">{T.allFloors}</option>
              {Array.from(new Set(grid.rows.map((r) => r.staff.unit_name).filter(Boolean))).sort().map((unit) => (
                <option key={unit} value={unit!}>{unit}</option>
              ))}
            </select>
            <input type="text" value={filterSearch} onChange={(e) => setFilterSearch(e.target.value)}
              placeholder={T.filterSearch}
              className="text-xs px-2.5 py-1.5 border border-gray-200 rounded-lg bg-white w-40" />
            <button onClick={() => { setFilterRank('ALL'); setFilterFloor('ALL'); setFilterSearch('') }}
              className="text-[10px] text-gray-400 hover:text-gray-600">✕ Clear</button>
            <div className="ml-auto">
              <button onClick={() => window.open(`/api/export/roster?period_id=${periodId}`, '_blank')}
                disabled={!periodId}
                className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
                {T.exportRoster}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Compact validation status: details live in an overlay so the roster grid keeps its height. */}
      {validation && (
        <div className="flex-shrink-0 border-b border-gray-200 bg-white px-5 py-2" aria-live="polite">
          <div className="flex min-h-8 flex-wrap items-center gap-2 text-xs">
            <span className={`font-bold ${blockingCount > 0 ? 'text-rose-700' : warningCount > 0 ? 'text-amber-700' : 'text-emerald-700'}`}>
              {blockingCount > 0
                ? (isZH ? '此草稿需要檢視' : 'This draft needs review')
                : warningCount > 0
                  ? (isZH ? '可以發佈，但請先檢視警告' : 'Publishable with warnings to review')
                  : (isZH ? '已準備好發佈' : 'Ready to publish')}
            </span>
            <span className="text-[10px] text-gray-400">{validation.method}</span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${blockingCount ? 'bg-rose-100 text-rose-700' : 'bg-gray-100 text-gray-500'}`}>
              {isZH ? '阻塞規則' : 'Blocking rules'} {blockingGroups.length}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${warningCount ? 'bg-amber-100 text-amber-800' : 'bg-gray-100 text-gray-500'}`}>
              {isZH ? '警告類別' : 'Warning groups'} {warningGroups.length + ratioGroups.length}
            </span>
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
              {isZH ? '通過檢查' : 'Checks passed'} {passingCheckCount}
            </span>
            <button onClick={() => setRuleReviewOpen(true)} className="ml-auto rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:bg-slate-50">
              {isZH ? '檢視規則' : 'Review rules'}
            </button>
          </div>
        </div>
      )}

      {ruleReviewOpen && validation && (
        <div className="fixed inset-0 z-[70] flex items-end justify-end md:items-stretch" role="dialog" aria-modal="true" aria-label={isZH ? '規則檢視' : 'Rule review'}>
          <button className="absolute inset-0 bg-slate-950/25 backdrop-blur-[1px]" onClick={() => setRuleReviewOpen(false)} aria-label={isZH ? '關閉規則檢視' : 'Close rule review'} />
          <aside className="relative flex max-h-[84vh] w-full flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-2xl md:max-h-none md:max-w-md md:rounded-none md:rounded-l-2xl">
            <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
              <div>
                <h2 className="text-base font-black text-slate-950">{isZH ? '更表規則檢視' : 'Roster rule review'}</h2>
                <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{isZH ? '規則引擎決定結果；Emma AI只可解釋同一份證據。' : 'The rules engine decides the result; Emma AI can only explain the same evidence.'}</p>
              </div>
              <button onClick={() => setRuleReviewOpen(false)} className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-500 hover:bg-slate-50">✕</button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
              <section>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-black uppercase tracking-wide text-rose-700">{isZH ? '必須處理' : 'Blocking'}</h3>
                  <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-700">{blockingCount}</span>
                </div>
                <div className="space-y-2">
                  {blockingGroups.map((group) => {
                    const first = group.items[0]
                    const expanded = expandedRuleGroups.has(`hard:${group.key}`)
                    const dates = [...new Set(group.items.map((item) => item.date).filter(Boolean))]
                    const located = group.items.find((item) => item.staff_id && item.date)
                    return (
                      <article key={group.key} className="rounded-xl border border-rose-200 bg-rose-50/60 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <div className="text-xs font-bold text-slate-900">{group.ruleCode}</div>
                              <span className="rounded-full bg-white px-2 py-0.5 text-[9px] font-bold text-rose-700">{group.items.length} {isZH ? '項結果' : 'results'}</span>
                            </div>
                            <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{first?.message || (isZH ? '規則引擎未有返回詳細說明。' : 'No detailed message was returned by the rules engine.')}</p>
                            <p className="mt-2 text-[10px] text-slate-500">{dates.length ? `${dates.length} ${isZH ? '個日期' : 'dates'} · ${dates[0]}${dates.length > 1 ? ` → ${dates[dates.length - 1]}` : ''}` : (isZH ? '未有日期資料' : 'Date unavailable')}</p>
                          </div>
                          <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[9px] font-bold text-rose-700">HARD</span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {located && <button onClick={() => focusIssue(located.staff_id, located.date)} className="rounded-lg bg-slate-950 px-3 py-1.5 text-[10px] font-bold text-white">{isZH ? '顯示首個受影響更次' : 'Show first affected shift'}</button>}
                          <button onClick={() => explainRule(group.ruleCode, first?.date)} className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-[10px] font-bold text-rose-700">{isZH ? '由Emma AI解釋' : 'Explain in Emma AI'}</button>
                          <button onClick={() => toggleRuleGroup(`hard:${group.key}`)} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-600">{expanded ? (isZH ? '收起例子' : 'Hide examples') : (isZH ? '查看例子' : 'View examples')}</button>
                        </div>
                        {expanded && (
                          <div className="mt-3 space-y-1.5 border-t border-rose-100 pt-3">
                            {group.items.slice(0, 6).map((item, index) => (
                              <div key={`${item.rule_code}-${index}`} className="rounded-lg bg-white/75 px-2.5 py-2 text-[10px] text-slate-600">
                                <b>{item.date || (isZH ? '日期未有提供' : 'Date unavailable')}</b>{item.message ? ` · ${item.message}` : ''}
                              </div>
                            ))}
                            {group.items.length > 6 && <p className="text-[10px] text-rose-600">{isZH ? `只顯示首6項；尚有${group.items.length - 6}項。` : `Showing the first 6; ${group.items.length - 6} more results remain.`}</p>}
                          </div>
                        )}
                      </article>
                    )
                  })}
                  {blockingGroups.length === 0 && blockingCount > 0 && <div className="rounded-xl border border-dashed border-rose-200 p-3 text-[11px] text-rose-700">{isZH ? `規則引擎報告${blockingCount}項阻塞，但未返回逐項資料。請重新執行規則檢查或查看validation evidence。` : `The rules engine reports ${blockingCount} blockers but returned no item-level data. Run the checks again or review the validation evidence.`}</div>}
                  {blockingCount === 0 && <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-3 text-[11px] text-emerald-700">{isZH ? '沒有阻塞發佈的規則。' : 'No rules are blocking publication.'}</div>}
                </div>
              </section>

              <section>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-black uppercase tracking-wide text-amber-700">{isZH ? '需要檢視' : 'Warnings'}</h3>
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">{warningCount}</span>
                </div>
                <div className="space-y-2">
                  {warningGroups.map((group) => {
                    const first = group.items[0]
                    return (
                      <article key={group.key} className="rounded-xl border border-amber-200 bg-amber-50/60 p-3">
                        <div className="flex flex-wrap items-center gap-2"><div className="text-xs font-bold text-slate-900">{group.ruleCode}</div><span className="rounded-full bg-white px-2 py-0.5 text-[9px] font-bold text-amber-800">{group.items.length} {isZH ? '項結果' : 'results'}</span></div>
                        <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{first?.message || (isZH ? '需要院長檢視。' : 'Manager review is required.')}</p>
                        <button onClick={() => explainRule(group.ruleCode, first?.date)} className="mt-3 rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-[10px] font-bold text-amber-800">{isZH ? '由Emma AI解釋' : 'Explain in Emma AI'}</button>
                      </article>
                    )
                  })}
                  {ratioGroups.map((group) => {
                    const first = group.items[0]
                    const largestGap = Math.max(...group.items.map((item) => Math.max(item.required - item.actual, 0)))
                    const expanded = expandedRuleGroups.has(`ratio:${group.key}`)
                    return (
                      <article key={group.key} className="rounded-xl border border-amber-200 bg-amber-50/60 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="flex flex-wrap items-center gap-2"><div className="text-xs font-bold text-slate-900">{group.label}</div><span className="rounded-full bg-white px-2 py-0.5 text-[9px] font-bold text-amber-800">{group.items.length} {isZH ? '個時段' : 'windows'}</span></div>
                            <p className="mt-1 text-[11px] text-slate-600">{group.rank ? `${group.rank} · ` : ''}{isZH ? '最大人手缺口' : 'Largest staffing gap'}: {largestGap}</p>
                            <p className="mt-1 text-[10px] text-slate-500">{first?.window_start} → {group.items[group.items.length - 1]?.window_end}</p>
                          </div>
                          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[9px] font-bold text-amber-800">RATIO</span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button onClick={() => explainRule(group.label, first?.window_start)} className="rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-[10px] font-bold text-amber-800">{isZH ? '由Emma AI解釋' : 'Explain in Emma AI'}</button>
                          <button onClick={() => toggleRuleGroup(`ratio:${group.key}`)} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-600">{expanded ? (isZH ? '收起時段' : 'Hide windows') : (isZH ? '查看時段' : 'View windows')}</button>
                        </div>
                        {expanded && <div className="mt-3 space-y-1.5 border-t border-amber-100 pt-3">{group.items.slice(0, 6).map((item, index) => <div key={`${item.label}-${index}`} className="rounded-lg bg-white/75 px-2.5 py-2 text-[10px] text-slate-600"><b>{item.window_start}</b> · {isZH ? '實際／要求' : 'Actual／required'} {item.actual}／{item.required}</div>)}{group.items.length > 6 && <p className="text-[10px] text-amber-700">{isZH ? `只顯示首6個時段；尚有${group.items.length - 6}個。` : `Showing the first 6 windows; ${group.items.length - 6} more remain.`}</p>}</div>}
                      </article>
                    )
                  })}
                  {warningCount === 0 && <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-3 text-[11px] text-emerald-700">{isZH ? '沒有需要院長檢視的警告。' : 'No warnings require manager review.'}</div>}
                </div>
              </section>
            </div>
          </aside>
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
                <th className="px-1 py-1.5 text-center border-r border-gray-200 min-w-[44px] bg-gray-50">
                  <div className="text-[8px] text-gray-400">{T.totalHrs}</div>
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
              {grid.rows
                .filter((row) => {
                  if (filterRank !== 'ALL' && row.staff.rank !== filterRank) return false
                  if (filterFloor !== 'ALL' && row.staff.unit_name !== filterFloor) return false
                  if (filterSearch) {
                    const q = filterSearch.toLowerCase()
                    const name = (row.staff.name_en || row.staff.name || '').toLowerCase()
                    if (!name.includes(q) && !row.staff.rank.toLowerCase().includes(q)) return false
                  }
                  return true
                })
                .map((row) => {
                const workedHrs = columns.reduce((sum, iso) => {
                  const cell = cellLookup.get(row.staff.id)?.get(iso)
                  if (!cell?.shift_type) return sum
                  const sDef = shiftDefs.find((d) => d.shift_type === cell.shift_type)
                  if (!sDef?.is_working) return sum
                  return sum + (sDef.paid_minutes ?? 480) / 60
                }, 0)
                return (
                <tr key={row.staff.id} className="border-t border-gray-100">
                  <td className="px-3 py-2 border-r border-gray-200 sticky left-0 bg-white z-10 w-44 min-w-44">
                    <div className="text-[12px] font-semibold text-gray-900 truncate">{row.staff.name_en || row.staff.name}</div>
                    <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
                      <span className="font-bold text-gray-500">{row.staff.rank}</span>
                      {row.staff.unit_name && <span className="truncate">· {row.staff.unit_name}</span>}
                    </div>
                  </td>
                  <td className="px-1 py-2 border-r border-gray-200 text-center">
                    <div className="text-[10px] font-bold text-gray-600">{workedHrs.toFixed(1)}</div>
                  </td>
                  {columns.map((iso) => {
                    const cell = cellLookup.get(row.staff.id)?.get(iso)
                    const st = cell?.shift_type
                    const style = st ? (SHIFT_STYLE[st] ?? DEFAULT_STYLE) : null
                    return (
                      <td key={iso} id={`roster-cell-${row.staff.id}-${iso}`}
                        onClick={() => editable && (setCellIssues([]), setEditing({
                          staffId: row.staff.id, staffName: row.staff.name_en || row.staff.name,
                          staffRank: row.staff.rank,
                          date: iso, shiftType: st ?? '', tasks: cell?.tasks ?? [],
                          wasWorking: !!st,
                        }))}
                        className={`relative border-r border-gray-100 p-1 align-top ${editable ? 'cursor-pointer hover:bg-pink-50/40' : ''} ${focusedCell?.staffId === row.staff.id && focusedCell.date === iso ? 'bg-rose-50 ring-2 ring-inset ring-[#E8187A]' : ''}`}>
                        {(issueCountByCell.get(`${row.staff.id}|${iso}`) ?? 0) > 0 && (
                          <span className="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-white" title={isZH ? '此更次有規則提示' : 'This shift has a rule alert'} />
                        )}
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
                )})}
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
            <div className="text-sm font-bold text-gray-900">{T.edit}</div>

            <div className="text-xs text-gray-500 mb-4">{editing.staffName} · {editing.date}</div>

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

      {batchShiftOpen && grid && (
        <BatchCreateShiftModal
          open={batchShiftOpen}
          onClose={() => setBatchShiftOpen(false)}
          staff={grid.rows.map((r) => r.staff)}
          shiftDefs={shiftDefs}
          dates={columns}
          onBatchCreated={(count) => { flash(`${count} shifts created`); void loadGrid(periodId, versionId) }}
        />
      )}

      {createShiftOpen && grid && (
        <CreateShiftModal
          open={createShiftOpen}
          onClose={() => setCreateShiftOpen(false)}
          versionId={activeVersionId}
          staff={grid.rows.map((r) => r.staff)}
          dates={columns}
          shiftDefs={shiftDefs}
          taskDefs={taskDefs}
          onSaved={({ staffName, date, shiftType, wasWorking }) => {
            logChange(wasWorking ? 'edit' : 'create',
                      wasWorking ? T.actionEdit : T.actionCreate,
                      `${staffName} · ${date} · ${shiftType}`)
            loadGrid(periodId, versionId)
          }}
        />
      )}

      {createEventOpen && (
        <CreateEventModal
          isZH={isZH}
          defaultDate={columns[0] ?? new Date().toISOString().slice(0, 10)}
          staffList={grid?.rows.map((r) => r.staff) ?? []}
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
