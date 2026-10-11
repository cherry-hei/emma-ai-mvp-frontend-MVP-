'use client'

// Design: Emma clinical warmth. This is the single roster workspace for
// generate → edit → deterministic rule check → manager publish.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiRuleError, api, downloadRosterAudit, optimizeAndPoll } from '@/lib/api'
import type {
  OptionScoreOut, PeriodOut, RosterCell, RosterGrid, RosterOption, RuleIssue,
  ShiftDef, TaskDefOut, ValidationOut, VersionOut,
} from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { canDecide } from '@/lib/permissions'
import { CreateShiftModal } from '@/components/modals/CreateShiftModal'
import { addUtcDays, datesForRosterView, type RosterViewMode } from '@/lib/roster-ui'
import { formatHoursMinutes } from '@/lib/format-hours'
import { AiOptionsModal } from './AiOptionsModal'
import { CreateEventModal } from './CreateEventModal'
import { BatchCreateShiftModal } from '@/components/modals/BatchCreateShiftModal'

const PINK = '#E8187A'

// Which period the scheduler was last working on. Without this the board reopens
// on `periods[0]`, and `list_periods` orders by `period_start desc` - so a home
// that has planned a future cycle lands on that empty cycle every time and the
// current period's saved draft reads as "my edits are gone". The draft was never
// lost; the board was simply pointed at a different period.
const PERIOD_KEY_PREFIX = 'emma.roster.periodId'

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
function pickPeriod(ps: PeriodOut[], remembered: string | null): string {
  if (!ps.length) return ''
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

type EditorInitial = {
  staffId?: string
  date?: string
  shiftType?: string
  tasks?: string[]
  assignmentId?: string | null
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
  const { user } = useAuth()
  const isZH = lang === 'zh'
  // The API derives tenancy from the bearer token. This key is only for client
  // state isolation: a cached Home A grid must never briefly survive a switch to
  // Home B (nor should two users share a remembered period in one browser).
  const scopeKey = `${user?.userId ?? 'anonymous'}:${user?.facilityId ?? 'no-facility'}`
  const periodStorageKey = `${PERIOD_KEY_PREFIX}:${encodeURIComponent(user?.userId ?? 'anonymous')}:${encodeURIComponent(user?.facilityId ?? 'no-facility')}`

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
  const [editorInitial, setEditorInitial] = useState<EditorInitial | null>(null)
  const [cellIssues, setCellIssues] = useState<RuleIssue[]>([])
  const [newPeriodOpen, setNewPeriodOpen] = useState(false)
  const [validation, setValidation] = useState<ValidationOut | null>(null)
  // These IDs are issued by the server for individual current soft findings.
  // The server re-validates and verifies them again before the atomic publish.
  const [softOmissionIds, setSoftOmissionIds] = useState<Set<string>>(new Set())
  const [ruleReviewOpen, setRuleReviewOpen] = useState(false)
  const [ruleReviewMode, setRuleReviewMode] = useState<'all' | 'soft'>('all')
  const [focusedCell, setFocusedCell] = useState<FocusedCell>(null)
  const [expandedRuleGroups, setExpandedRuleGroups] = useState<Set<string>>(new Set())

  const [aiOpen, setAiOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiOptions, setAiOptions] = useState<RosterOption[] | null>(null)
  const [aiStatus, setAiStatus] = useState('')
  const [aiError, setAiError] = useState('')
  const [createEventOpen, setCreateEventOpen] = useState(false)
  const [createShiftOpen, setCreateShiftOpen] = useState(false)
  const [batchShiftOpen, setBatchShiftOpen] = useState(false)
  const [history, setHistory] = useState<Awaited<ReturnType<typeof api.rosterHistory>> | null>(null)
  const [historyError, setHistoryError] = useState('')
  const [historyLoading, setHistoryLoading] = useState(false)
  const [showSaveList, setShowSaveList] = useState(false)
  const [showPublishList, setShowPublishList] = useState(false)
  const [viewMode, setViewMode] = useState<RosterViewMode>('week')
  const [focusDate, setFocusDate] = useState('')
  const [selectedStaffId, setSelectedStaffId] = useState('')
  const [filterRank, setFilterRank] = useState('ALL')
  const [filterFloor, setFilterFloor] = useState('ALL')
  const [filterSearch, setFilterSearch] = useState('')
  const gridRequestRef = useRef(0)
  const validationRequestRef = useRef(0)
  const versionsRequestRef = useRef(0)
  const historyRequestRef = useRef(0)
  const scopeRequestRef = useRef(0)
  const activeScopeRef = useRef(scopeKey)
  const activePeriodRef = useRef(periodId)
  // Ref updates during render are intentional: an old promise may settle before
  // the cleanup effect below runs, so the current scope and period must be
  // observable now.
  activeScopeRef.current = scopeKey
  activePeriodRef.current = periodId
  const mayPublish = canDecide(user?.role, 'roster.publish')

  const T = {
    period: isZH ? '週期' : 'Period', newPeriod: isZH ? '＋ 新週期' : '＋ New period',
    version: isZH ? '版本' : 'Version', manual: isZH ? '手動' : 'Manual',
    ai: isZH ? '生成更表方案' : 'Generate roster options', aiBusy: isZH ? '生成中…' : 'Generating…',
    validate: isZH ? '執行規則檢查' : 'Run rule checks', saveDraft: isZH ? '儲存草稿' : 'Save draft',
    prePublishReview: isZH ? '發佈前檢視' : 'Pre-publish review',
    softReport: isZH ? 'Soft報告模式' : 'Soft report mode',
    reload: isZH ? '重新載入更表' : 'Reload roster',
    downloadAudit: isZH ? '下載Audit' : 'Download audit',
    publish: isZH ? '發佈' : 'Publish', staff: isZH ? '員工' : 'Staff',
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
    publishList: isZH ? '發佈記錄' : 'Publish history',
    saveListTitle: isZH ? '儲存清單' : 'Save List',
    saveListEmpty: isZH ? '暫無未發佈的更改' : 'No unpublished changes',
    publishListTitle: isZH ? '發佈記錄' : 'Publish history',
    publishListEmpty: isZH ? '暫無發佈記錄' : 'No published records yet',
    actionEdit: isZH ? '編輯更次' : 'Edit shift',
    actionCreate: isZH ? '新增更次' : 'New shift',
    actionDelete: isZH ? '刪除更次' : 'Delete shift',
    actionEvent: isZH ? '新增特別事項' : 'New special event',
  }

  const flash = (m: string) => { setNotice(m); setError(''); window.setTimeout(() => setNotice(''), 2500) }


  // ── loaders ──────────────────────────────────────────────────────────────
  useEffect(() => () => {
    gridRequestRef.current += 1
    validationRequestRef.current += 1
    versionsRequestRef.current += 1
    historyRequestRef.current += 1
    scopeRequestRef.current += 1
  }, [])

  useEffect(() => {
    const requestId = ++scopeRequestRef.current
    // Invalidate every in-flight result before clearing. The API already scopes
    // to the token; no facility id is ever added to client requests.
    gridRequestRef.current += 1
    validationRequestRef.current += 1
    versionsRequestRef.current += 1
    historyRequestRef.current += 1
    activePeriodRef.current = ''
    setPeriods([])
    setPeriodId('')
    setVersions([])
    setVersionId('')
    setGrid(null)
    setShiftDefs([])
    setTaskDefs([])
    setScores({})
    setLoading(false)
    setError('')
    setNotice('')
    setBusy('')
    setEditorInitial(null)
    setCellIssues([])
    setNewPeriodOpen(false)
    setValidation(null)
    setSoftOmissionIds(new Set())
    setRuleReviewOpen(false)
    setRuleReviewMode('all')
    setFocusedCell(null)
    setExpandedRuleGroups(new Set())
    setAiOpen(false)
    setAiLoading(false)
    setAiOptions(null)
    setAiStatus('')
    setAiError('')
    setCreateEventOpen(false)
    setCreateShiftOpen(false)
    setBatchShiftOpen(false)
    setHistory(null)
    setHistoryError('')
    setHistoryLoading(false)
    setShowSaveList(false)
    setShowPublishList(false)
    setViewMode('week')
    setFocusDate('')
    setSelectedStaffId('')
    setFilterRank('ALL')
    setFilterFloor('ALL')
    setFilterSearch('')

    if (!user?.userId) return

    void (async () => {
      const [shifts, tasks, periodResult] = await Promise.allSettled([
        api.shiftDefinitions(),
        api.taskDefinitions(),
        api.rosterPeriods(),
      ])
      if (requestId !== scopeRequestRef.current || activeScopeRef.current !== scopeKey) return
      setShiftDefs(shifts.status === 'fulfilled' ? shifts.value : [])
      setTaskDefs(tasks.status === 'fulfilled' ? tasks.value : [])
      if (periodResult.status === 'fulfilled') {
        let remembered: string | null = null
        try { remembered = window.localStorage.getItem(periodStorageKey) } catch { /* private mode */ }
        setPeriods(periodResult.value)
        setPeriodId(pickPeriod(periodResult.value, remembered))
      } else {
        setError(periodResult.reason instanceof Error ? periodResult.reason.message : 'Failed to load periods')
      }
    })()
  }, [periodStorageKey, scopeKey, user?.userId])

  // Remember the choice so leaving the page - or signing out and back in -
  // returns to the same period rather than to whichever one sorts first.
  useEffect(() => {
    if (!periodId || !user?.userId) return
    try { window.localStorage.setItem(periodStorageKey, periodId) } catch { /* private mode */ }
  }, [periodId, periodStorageKey, user?.userId])

  const loadVersions = useCallback(async (pid: string) => {
    const requestId = ++versionsRequestRef.current
    try {
      const vs = await api.rosterVersions(pid)
      if (requestId !== versionsRequestRef.current || activeScopeRef.current !== scopeKey || activePeriodRef.current !== pid) return
      setVersions(vs)
      const cmp = await api.compareOptions(pid)
      if (requestId !== versionsRequestRef.current || activeScopeRef.current !== scopeKey || activePeriodRef.current !== pid) return
      const map: Record<string, OptionScoreOut> = {}
      cmp.options.forEach((o) => { map[o.roster_version_id] = o })
      setScores(map)
    } catch (cause) {
      if (requestId !== versionsRequestRef.current || activeScopeRef.current !== scopeKey || activePeriodRef.current !== pid) return
      setVersions([])
      setScores({})
      throw cause
    }
  }, [scopeKey])

  useEffect(() => {
    versionsRequestRef.current += 1
    setVersions([])
    setScores({})
    setVersionId('')
    if (!periodId) return
    loadVersions(periodId).catch(() => {})
  }, [periodId, loadVersions])

  const validateVersion = useCallback(async (vid: string) => {
    const requestId = ++validationRequestRef.current
    const requestedPeriodId = activePeriodRef.current
    try {
      const result = await api.validateRoster(vid)
      if (requestId === validationRequestRef.current && activeScopeRef.current === scopeKey && activePeriodRef.current === requestedPeriodId) {
        setValidation(result)
        // Every re-check is a new snapshot. Do not silently carry an earlier
        // checkbox into it, even if the finding fingerprint happens to match:
        // the OWNER must re-review and explicitly acknowledge each current row.
        setSoftOmissionIds(new Set())
      }
      return result
    } catch (e) {
      // A newer version or manual re-check supersedes this request.
      if (requestId !== validationRequestRef.current || activeScopeRef.current !== scopeKey || activePeriodRef.current !== requestedPeriodId) return null
      throw e
    }
  }, [scopeKey])

  const loadGrid = useCallback(async (pid: string, vid: string) => {
    const requestId = ++gridRequestRef.current
    // The next grid owns the validation strip; invalidate any older response.
    validationRequestRef.current += 1
    // Do not leave a previous period/version editable while a replacement is
    // loading or after a failed request.
    setGrid(null); setLoading(true); setError(''); setValidation(null); setSoftOmissionIds(new Set())
    try {
      const nextGrid = await api.rosterGrid(pid, vid ? { versionId: vid } : undefined)
      if (requestId !== gridRequestRef.current || activeScopeRef.current !== scopeKey || activePeriodRef.current !== pid) return
      setGrid(nextGrid)
      setLoading(false)
      if (nextGrid.version_id) {
        try {
          await validateVersion(nextGrid.version_id)
        } catch (e) {
          if (requestId === gridRequestRef.current && activeScopeRef.current === scopeKey && activePeriodRef.current === pid) {
            setError(e instanceof Error ? e.message : 'Validation failed')
          }
        }
      }
    } catch (e) {
      if (requestId === gridRequestRef.current && activeScopeRef.current === scopeKey && activePeriodRef.current === pid) {
        setGrid(null)
        setError(e instanceof Error ? e.message : 'Failed to load roster')
      }
    } finally {
      if (requestId === gridRequestRef.current && activeScopeRef.current === scopeKey && activePeriodRef.current === pid) setLoading(false)
    }
  }, [scopeKey, validateVersion])

  useEffect(() => { if (periodId) loadGrid(periodId, versionId) }, [periodId, versionId, loadGrid])

  // All three view modes are derived from the same authenticated roster grid;
  // changing the view never reads a demo roster or a cross-facility dictionary.
  useEffect(() => {
    if (!grid?.dates.length) return
    setFocusDate((current) => grid.dates.includes(current) ? current : grid.dates[0])
    setSelectedStaffId((current) => grid.rows.some((row) => row.staff.id === current) ? current : (grid.rows[0]?.staff.id || ''))
  }, [grid])


  // ── derived ──────────────────────────────────────────────────────────────
  const currentVersion = useMemo(
    () => (versionId ? versions.find((v) => v.id === versionId) : versions.find((v) => v.version_type === 'manual')) ?? null,
    [versions, versionId],
  )
  const activeVersionId = grid?.version_id ?? currentVersion?.id ?? ''

  const loadHistory = useCallback(async () => {
    if (!periodId) return
    const requestId = ++historyRequestRef.current
    const requestedPeriodId = periodId
    setHistoryLoading(true); setHistoryError('')
    try {
      const nextHistory = await api.rosterHistory(requestedPeriodId, activeVersionId || undefined)
      if (requestId !== historyRequestRef.current || activeScopeRef.current !== scopeKey || activePeriodRef.current !== requestedPeriodId) return
      setHistory(nextHistory)
    }
    catch (cause) {
      if (requestId !== historyRequestRef.current || activeScopeRef.current !== scopeKey || activePeriodRef.current !== requestedPeriodId) return
      setHistory(null)
      setHistoryError(cause instanceof Error ? cause.message : (isZH ? '未能讀取伺服器Audit記錄' : 'Could not read server audit records'))
    } finally {
      if (requestId === historyRequestRef.current && activeScopeRef.current === scopeKey && activePeriodRef.current === requestedPeriodId) setHistoryLoading(false)
    }
  // The helper is an authenticated scoped read. It replaces the old localStorage convenience list.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodId, activeVersionId, isZH, scopeKey])

  useEffect(() => { void loadHistory() }, [loadHistory])

  // Only the manual draft is hand-editable; A/B/C solver options are read-only
  // results you publish, and published/archived versions are locked.
  const editable = currentVersion?.version_type === 'manual' && currentVersion?.status === 'draft'

  const blockingViolations = useMemo(
    // Unknown severity is deliberately a block, never a warning that can be
    // omitted. The final server gate applies the same fail-closed posture.
    () => (validation?.violations ?? []).filter((item) => !item.resolved && item.severity.toLowerCase() !== 'soft'),
    [validation],
  )
  const warningViolations = useMemo(
    () => (validation?.violations ?? []).filter((item) => !item.resolved && item.severity.toLowerCase() === 'soft'),
    [validation],
  )
  const failingRatios = useMemo(
    () => (validation?.ratio_checks ?? []).filter((item) => !item.passes),
    [validation],
  )
  const blockingCount = Math.max(validation?.hard_violation_count ?? 0, blockingViolations.length)
  // Ratio failures also produce deterministic hard violations (`swd_ratio`),
  // hence they are never counted as soft omissions.
  const warningCount = warningViolations.length
  const softOmittableViolations = useMemo(
    () => warningViolations.filter((item) => !!item.omission_id),
    [warningViolations],
  )
  // `omission_id` is server evidence, not optional UI decoration. A soft row
  // without it cannot be individually acknowledged, so do not let the browser
  // present a permissive Publish action while the server will (correctly) deny.
  const hasUnacknowledgeableSoftViolation = warningViolations.some((item) => !item.omission_id)
  const allSoftOmissionsSelected = softOmittableViolations.length === softOmissionIds.size
    && softOmittableViolations.every((item) => softOmissionIds.has(item.omission_id!))
  const softAcknowledgementsComplete = !hasUnacknowledgeableSoftViolation && allSoftOmissionsSelected
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

  const periodColumns = useMemo(() => {
    if (grid?.period_start && grid?.period_end) return eachDate(grid.period_start, grid.period_end)
    return grid?.dates ?? []
  }, [grid])
  const columns = useMemo(
    () => datesForRosterView(periodColumns, focusDate || periodColumns[0] || '', viewMode),
    [focusDate, periodColumns, viewMode],
  )
  const shownRows = useMemo(() => {
    const rows = grid?.rows ?? []
    return viewMode === 'staff' ? rows.filter((row) => row.staff.id === selectedStaffId) : rows
  }, [grid?.rows, selectedStaffId, viewMode])
  const currentDateRange = columns.length ? `${columns[0]} → ${columns[columns.length - 1]}` : ''
  const moveView = (direction: -1 | 1) => {
    if (!focusDate) return
    setFocusDate((value) => addUtcDays(value, direction * (viewMode === 'month' ? 31 : 7)))
  }

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
    await Promise.all([loadVersions(periodId), loadGrid(periodId, versionId), loadHistory()])
  }, [periodId, versionId, loadVersions, loadGrid, loadHistory])

  async function handleValidate() {
    if (!activeVersionId) return
    setValidation(null); setSoftOmissionIds(new Set())
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

  async function handleDownloadAudit() {
    if (!periodId) return
    setBusy('audit'); setError('')
    try {
      await downloadRosterAudit(periodId, activeVersionId || undefined)
      flash(isZH ? 'Audit下載已開始' : 'Audit download started')
    } catch (e) {
      setError(e instanceof Error ? e.message : (isZH ? 'Audit下載失敗' : 'Audit download failed'))
    } finally { setBusy('') }
  }

  async function handlePublish() {
    if (!activeVersionId) return
    if (!mayPublish) {
      setError(isZH ? '只有院長可批准及發佈更表。' : 'Only the superintendent may approve and publish a roster.')
      return
    }
    // This is a usability preflight only. The server always repeats the
    // deterministic validation immediately before its atomic publication RPC.
    if (!validation || !validation.validation_run_id || !validation.input_digest || blockingCount > 0) {
      setRuleReviewOpen(true)
      return
    }
    if (!softAcknowledgementsComplete) {
      setError(hasUnacknowledgeableSoftViolation
        ? (isZH ? '規則檢查缺少soft例外識別碼；請重新執行檢查。' : 'The rule check is missing a soft-exception identifier; run the checks again.')
        : (isZH ? '請逐項剔選所有soft違規後才可發佈。' : 'Tick every soft violation individually before publishing.'))
      setRuleReviewOpen(true)
      return
    }
    setBusy('publish'); setError('')
    try {
      const published = await api.publish(
        activeVersionId,
        [...softOmissionIds],
        validation.input_digest,
      )
      flash(published.omitted_soft_violation_ids.length
        ? (isZH ? `已發佈；已審批${published.omitted_soft_violation_ids.length}項soft例外。` : `Published with ${published.omitted_soft_violation_ids.length} approved soft omission(s).`)
        : (isZH ? '已發佈' : 'Published'))
      setRuleReviewOpen(false)
      await refresh()
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Publish failed'
      setValidation(null); setSoftOmissionIds(new Set())
      try { await validateVersion(activeVersionId) } catch { /* preserve the publish error */ }
      setError(message)
    } finally { setBusy('') }
  }

  async function handleAI() {
    if (aiLoading || !periodId) return
    setAiOpen(true); setAiError(''); setAiOptions(null)
    setAiLoading(true); setAiStatus('pending')
    try {
      const options = await optimizeAndPoll(periodId, { onStatus: setAiStatus })
      setAiOptions(options)
      await loadVersions(periodId) // A/B/C versions now exist → tabs + score badges
    } catch (e) {
      setAiError(e instanceof Error ? e.message : 'Optimization failed')
    } finally { setAiLoading(false) }
  }

  function handlePublishOption(vid: string) {
    // Solver options must use the identical fresh validation and omission flow;
    // selecting one never invokes a client-only direct publish path.
    setVersionId(vid)
    setAiOpen(false)
    flash(isZH
      ? '已選擇方案；請完成規則檢視後在上方發佈。'
      : 'Option selected. Complete rule review, then publish from the fixed control above.')
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

  function toggleSoftOmission(omissionId: string) {
    setSoftOmissionIds((current) => {
      const next = new Set(current)
      if (next.has(omissionId)) next.delete(omissionId)
      else next.add(omissionId)
      return next
    })
  }

  // ── render ───────────────────────────────────────────────────────────────
  const periodLabel = grid?.period_start && grid?.period_end ? `${grid.period_start} → ${grid.period_end}` : ''

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="sticky top-0 z-40 bg-white border-b border-gray-200 px-5 py-3 flex-shrink-0 space-y-2.5">
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

        <div className="flex flex-col gap-2 border-t border-slate-100 pt-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-xl bg-slate-100 p-1">
              {([
                ['week', isZH ? '全體週表' : 'All-staff week'],
                ['month', isZH ? '全體月表' : 'All-staff month'],
                ['staff', isZH ? '單一員工' : 'Single staff'],
              ] as Array<[RosterViewMode, string]>).map(([mode, label]) => <button key={mode} type="button" onClick={() => setViewMode(mode)} className={`rounded-lg px-3 py-1.5 text-[10px] font-bold ${viewMode === mode ? 'bg-white text-pink-700 shadow-sm' : 'text-slate-500'}`}>{label}</button>)}
            </div>
            <button type="button" onClick={() => moveView(-1)} className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600">‹</button>
            <input type="date" value={focusDate} min={periodColumns[0]} max={periodColumns[periodColumns.length - 1]} onChange={(event) => setFocusDate(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px]" />
            <button type="button" onClick={() => moveView(1)} className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600">›</button>
            <span className="text-[10px] font-semibold text-slate-500">{currentDateRange}</span>
          </div>
          {viewMode === 'staff' && <select value={selectedStaffId} onChange={(event) => setSelectedStaffId(event.target.value)} className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700"><option value="">{isZH ? '選擇員工' : 'Select staff'}</option>{grid?.rows.map((row) => <option key={row.staff.id} value={row.staff.id}>{row.staff.name_en || row.staff.name} · {row.staff.rank}</option>)}</select>}
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
            <button onClick={() => { setRuleReviewMode('all'); setRuleReviewOpen(true); if (!validation) void handleValidate() }} disabled={!activeVersionId || !!busy}
              title={blockingCount > 0
                ? (isZH ? '硬規則已強制執行；必須先處理。' : 'Hard rules are enforced and must be resolved first.')
                : undefined}
              className="text-xs px-3 py-1.5 border border-slate-300 rounded-lg bg-white text-slate-700 font-semibold hover:bg-slate-50 disabled:opacity-50">
              {T.prePublishReview}
            </button>
            <button onClick={() => { setRuleReviewMode('soft'); setRuleReviewOpen(true); if (!validation) void handleValidate() }} disabled={!activeVersionId || !!busy}
              title={isZH ? '只顯示本次伺服器規則檢查的soft例外；不是另一個檢查或略過機制。' : 'Shows only soft findings from this server rule-check snapshot; it is not a second check or an override.'}
              className="text-xs px-3 py-1.5 border border-amber-200 rounded-lg bg-amber-50 text-amber-800 font-semibold hover:bg-amber-100 disabled:opacity-50">
              {T.softReport} ({warningCount})
            </button>
            <span title={isZH ? '硬規則由伺服器在發佈前再次強制核對。' : 'The server enforces hard rules again immediately before publication.'}
              className={`rounded-lg border px-2.5 py-1.5 text-[10px] font-bold ${blockingCount > 0 ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
              {isZH ? (blockingCount > 0 ? `硬規則強制 · ${blockingCount}` : '硬規則已強制') : (blockingCount > 0 ? `Hard enforced · ${blockingCount}` : 'Hard enforced')}
            </span>
            <button onClick={() => { setRuleReviewMode('all'); setRuleReviewOpen(true); if (!validation) void handleValidate() }} disabled={!activeVersionId || !!busy || !mayPublish}
              title={!mayPublish
                ? (isZH ? '只有院長可批准及發佈；伺服器會再次核對權限。' : 'Only the superintendent may approve and publish; the server verifies this again.')
                : blockingCount > 0 ? (isZH ? '先檢視及處理blocking rules' : 'Review and resolve blocking rules first')
                  : !softAcknowledgementsComplete ? (hasUnacknowledgeableSoftViolation
                    ? (isZH ? '請重新執行規則檢查。' : 'Run the rule checks again.')
                    : (isZH ? '請逐項剔選所有soft違規。' : 'Tick every soft violation individually.')) : undefined}
              className="text-xs px-3 py-1.5 rounded-lg text-white font-semibold disabled:opacity-50"
              style={{ background: !mayPublish || blockingCount > 0 || !softAcknowledgementsComplete ? '#475569' : PINK }}>
              {busy === 'publish' ? '…' : T.publish}
            </button>
            <button onClick={() => setShowSaveList((v) => !v)}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-700 font-semibold hover:bg-gray-50">
              {T.saveList} ({history?.changes.length ?? 0})
            </button>
            <button onClick={() => setShowPublishList((v) => !v)}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-700 font-semibold hover:bg-gray-50">
              {T.publishList} ({history?.publish_events.length ?? 0})
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
            <div className="ml-auto flex flex-wrap gap-2">
              <button onClick={() => window.location.assign(`/reports?period_id=${encodeURIComponent(periodId)}${activeVersionId ? `&version_id=${encodeURIComponent(activeVersionId)}` : ''}`)} disabled={!periodId}
                className="text-xs px-3 py-1.5 border border-pink-200 rounded-lg bg-white text-pink-700 hover:bg-pink-50 disabled:opacity-50">
                {isZH ? '下載更表' : 'Download roster'}
              </button>
              <button onClick={() => void handleDownloadAudit()} disabled={!periodId || busy === 'audit'}
                className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
                {busy === 'audit' ? '…' : T.downloadAudit}
              </button>
              <button onClick={() => void refresh()} disabled={!periodId || !!busy || loading}
                title={isZH ? '重新從目前登入帳戶的伺服器範圍讀取；不會刪除、更改或假裝重設草稿。' : 'Re-reads the current signed-in server scope; it does not delete, change, or pretend to reset a draft.'}
                className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                {T.reload}
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
            <button onClick={() => { setRuleReviewMode('all'); setRuleReviewOpen(true) }} className="ml-auto rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:bg-slate-50">
              {isZH ? '規則摘要' : 'Rule summary'}
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
                <h2 className="text-base font-black text-slate-950">{ruleReviewMode === 'soft' ? (isZH ? 'Soft例外報告' : 'Soft findings report') : (isZH ? '更表規則摘要' : 'Roster rule summary')}</h2>
                <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{ruleReviewMode === 'soft'
                  ? (isZH ? '只顯示目前伺服器規則檢查的soft例外；硬規則仍會在發佈前強制核對。' : 'Only current server rule-check soft findings are shown; hard rules remain enforced before publication.')
                  : (isZH ? '規則引擎決定結果；Emma AI只可解釋同一份證據。' : 'The rules engine decides the result; Emma AI can only explain the same evidence.')}</p>
              </div>
              <button onClick={() => setRuleReviewOpen(false)} className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-500 hover:bg-slate-50">✕</button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
              {ruleReviewMode === 'all' && <section>
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
              </section>}

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
                        <div className="mt-3 space-y-2 border-t border-amber-100 pt-3">
                          {group.items.map((item, index) => {
                            const omissionId = item.omission_id
                            const checked = !!omissionId && softOmissionIds.has(omissionId)
                            return (
                              <label key={omissionId || `${item.rule_code}-${index}`} className={`flex gap-2 rounded-lg border px-2.5 py-2 text-[10px] ${checked ? 'border-amber-300 bg-amber-100/60' : 'border-amber-100 bg-white/80'}`}>
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  disabled={!mayPublish || !omissionId}
                                  onChange={() => omissionId && toggleSoftOmission(omissionId)}
                                  className="mt-0.5 h-3.5 w-3.5 accent-[#E8187A]"
                                />
                                <span className="min-w-0 text-slate-600">
                                  <b className="text-slate-800">{item.date || (isZH ? '未有日期' : 'Date unavailable')}</b>{item.message ? ` · ${item.message}` : ''}
                                  <span className="mt-0.5 block text-[9px] text-amber-800">{isZH ? '略過／Omit 此soft例外；發佈時伺服器會重新核對。' : 'Omit this soft exception; the server re-checks it at publish.'}</span>
                                </span>
                              </label>
                            )
                          })}
                        </div>
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
            <footer className="shrink-0 border-t border-slate-200 bg-white p-4">
              <p className="mb-2 text-xs text-slate-600">{blockingCount > 0 ? (isZH ? '硬規則必須先處理，不能略過。' : 'Hard rules must be resolved and cannot be omitted.') : !softAcknowledgementsComplete ? (isZH ? '剩餘soft警告請逐項勾選略過。' : 'Select Omit for each remaining soft warning.') : ''}</p>
              {ruleReviewMode === 'soft' ? <button type="button" onClick={() => setRuleReviewMode('all')} className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50">{isZH ? '查看完整規則摘要' : 'View full rule summary'}</button> : <button type="button" onClick={() => void handlePublish()} disabled={!mayPublish || !!busy || !validation?.passes || !validation?.validation_run_id || !validation?.input_digest || blockingCount > 0 || !softAcknowledgementsComplete} className="w-full rounded-xl bg-[#E8187A] px-4 py-3 text-sm font-bold text-white disabled:opacity-40">{busy === 'publish' ? '…' : (isZH ? '院長批准並發佈' : 'Approve and publish')}</button>}
            </footer>
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
              {shownRows
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
                const paid = columns.map((iso) => cellLookup.get(row.staff.id)?.get(iso)?.paid_minutes)
                const hasUnknownPaidMinutes = columns.some((iso) => {
                  const cell = cellLookup.get(row.staff.id)?.get(iso)
                  return !!cell?.is_working && cell.paid_minutes == null
                })
                const paidMinutes = paid.reduce<number>((sum, value) => sum + (typeof value === 'number' ? value : 0), 0)
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
                    <div className="text-[10px] font-bold text-gray-600" title={hasUnknownPaidMinutes ? (isZH ? '部分在職更次沒有持久化paid_minutes；總時數保持未知，未以時鐘時間估算。' : 'Some working cells lack persisted paid_minutes; the total remains unknown and is not estimated from clock times.') : undefined}>{hasUnknownPaidMinutes ? '—' : formatHoursMinutes(paidMinutes, isZH ? 'zh' : 'en')}</div>
                  </td>
                  {columns.map((iso) => {
                    const cell = cellLookup.get(row.staff.id)?.get(iso)
                    const st = cell?.shift_type
                    const style = st ? (SHIFT_STYLE[st] ?? DEFAULT_STYLE) : null
                    return (
                      <td key={iso} id={`roster-cell-${row.staff.id}-${iso}`}
                        onClick={() => editable && setEditorInitial({
                          staffId: row.staff.id, date: iso, shiftType: st ?? '',
                          tasks: cell?.tasks ?? [], assignmentId: cell?.assignment_id,
                        })}
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
        <aside className="border-l border-gray-200 bg-white overflow-auto xl:min-w-[340px]" aria-live="polite">
          <div className="flex items-center justify-between border-b border-gray-100 p-4"><h3 className="text-sm font-bold text-gray-900">{isZH ? '伺服器記錄' : 'Server records'}</h3><button onClick={() => void loadHistory()} disabled={historyLoading} className="text-[10px] font-semibold text-pink-700">{historyLoading ? '…' : (isZH ? '重新整理' : 'Refresh')}</button></div>
          {historyError && <p className="m-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">{historyError}</p>}
          {!historyLoading && !history && !historyError && <p className="p-4 text-xs text-gray-400">{isZH ? '未有可顯示的正式伺服器記錄。' : 'No formal server records are available.'}</p>}
          {showSaveList && <section className="p-4 border-b border-gray-100"><h4 className="text-xs font-bold text-gray-800 mb-2">{T.saveListTitle} ({history?.changes.length ?? 0})</h4>{history && !history.can_read_audit ? <p className="text-xs text-amber-700">{isZH ? '此帳戶沒有讀取Audit記錄的權限。' : 'This account cannot read audit records.'}</p> : <div className="space-y-2">{history?.changes.length ? history.changes.map((item) => <article key={item.id} className="rounded-xl border border-pink-100 bg-pink-50/50 p-3"><div className="flex items-start justify-between gap-2"><b className="text-xs text-pink-700">{item.action}</b><time className="text-[9px] text-gray-400">{new Date(item.created_at).toLocaleString(isZH ? 'zh-HK' : 'en-HK')}</time></div><p className="mt-1 text-[10px] text-gray-600 break-all">{item.entity_table}{item.entity_id ? ` · ${item.entity_id}` : ''}</p></article>) : <p className="rounded-xl border border-dashed border-gray-200 p-3 text-xs text-gray-400 text-center">{T.saveListEmpty}</p>}</div>}</section>}
          {showPublishList && <section className="p-4"><h4 className="text-xs font-bold text-gray-800 mb-2">{T.publishListTitle} ({history?.publish_events.length ?? 0})</h4><div className="space-y-2">{history?.publish_events.length ? history.publish_events.map((item) => <article key={item.id} className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3"><div className="flex items-start justify-between gap-2"><b className="text-xs text-emerald-700">{item.event_type}</b><time className="text-[9px] text-gray-400">{new Date(item.created_at).toLocaleString(isZH ? 'zh-HK' : 'en-HK')}</time></div><p className="mt-1 text-[10px] text-gray-600 break-all">{item.roster_version_id}</p></article>) : <p className="rounded-xl border border-dashed border-gray-200 p-3 text-xs text-gray-400 text-center">{T.publishListEmpty}</p>}</div></section>}
        </aside>
      )}
      </div>

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
          periodLabel={periodLabel} isZH={isZH}
          onSelect={handlePublishOption} onClose={() => setAiOpen(false)}
        />
      )}

      {batchShiftOpen && grid && (
        <BatchCreateShiftModal
          open={batchShiftOpen}
          onClose={() => setBatchShiftOpen(false)}
          versionId={activeVersionId}
          staff={grid.rows.map((r) => r.staff)}
          shiftDefs={shiftDefs}
          dates={periodColumns}
          occupiedCells={grid.rows.flatMap((row) => row.cells
            .filter((cell) => !!cell.assignment_id || !!cell.shift_type || cell.tasks.length > 0)
            .map((cell) => ({ staffId: row.staff.id, date: cell.date, tasks: cell.tasks })))}
          onBatchCreated={({ saved, requested, skipped, partial }) => {
            const skippedText = skipped ? (isZH ? `；略過${skipped}格現有更次` : `; ${skipped} existing cell(s) skipped`) : ''
            flash(partial
              ? (isZH ? `批量排更部分完成：${saved}/${requested}${skippedText}` : `Batch partly saved: ${saved}/${requested}${skippedText}`)
              : (isZH ? `已儲存${saved}格${skippedText}` : `${saved} cells saved${skippedText}`))
            void Promise.all([loadGrid(periodId, versionId), loadHistory()])
          }}
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
          occupiedCells={grid.rows.flatMap((row) => row.cells
            .filter((cell) => !!cell.assignment_id)
            .map((cell) => ({ staffId: row.staff.id, date: cell.date, assignmentId: cell.assignment_id })))}
          onSaved={() => { void Promise.all([loadGrid(periodId, versionId), loadHistory()]) }}
        />
      )}

      {editorInitial && grid && (
        <CreateShiftModal
          open={!!editorInitial}
          mode={editorInitial.shiftType ? 'edit' : 'create'}
          onClose={() => setEditorInitial(null)}
          versionId={activeVersionId}
          staff={grid.rows.map((row) => row.staff)} dates={periodColumns} shiftDefs={shiftDefs} taskDefs={taskDefs}
          occupiedCells={grid.rows.flatMap((row) => row.cells
            .filter((cell) => !!cell.assignment_id)
            .map((cell) => ({ staffId: row.staff.id, date: cell.date, assignmentId: cell.assignment_id })))}
          initial={editorInitial}
          onSaved={() => { setEditorInitial(null); void Promise.all([loadGrid(periodId, versionId), loadHistory()]) }}
          onDeleted={() => { setEditorInitial(null); void Promise.all([loadGrid(periodId, versionId), loadHistory()]) }}
        />
      )}

      {createEventOpen && (
        <CreateEventModal
          isZH={isZH}
          defaultDate={columns[0] ?? new Date().toISOString().slice(0, 10)}
          dates={periodColumns}
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
