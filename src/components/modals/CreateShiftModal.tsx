"use client"

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useLang } from '@/components/layout/LanguageContext'
import { ApiRuleError, api } from '@/lib/api'
import type { ShiftDef, StaffLite, TaskDefOut } from '@/lib/apiTypes'
import { canSeeTask, issueLines, taskLabel } from '@/lib/shiftRules'
import { taskDateTimes, type TaskTimeValidationError } from '@/lib/roster-ui'
import {
  hydrateTaskTimingRows,
  persistTaskTimings,
  type TaskTimingRow,
} from '@/lib/task-schedule'

/**
 * Create or edit one roster cell, with a per-task time schedule (spec 3.1).
 *
 * Every list here comes from the API - staff from the roster grid, ranks from
 * those staff, shift types from `/shift-definitions`, tasks from
 * `/task-definitions` filtered by the same eligibility rule the server enforces.
 * The layout is unchanged; only the data behind it is. The previous version
 * shipped a hardcoded NAAC staff roll and a NAAC shift dictionary, which meant
 * the picker offered names and codes the other home does not have.
 *
 * Times are shown, not edited: the shift's hours belong to the facility's shift
 * definition, and the API derives them from `shift_type`. An editable field the
 * write ignores would be a lie about what was saved. Task rows carry their own
 * times, and those are real - they post to `/task-assignments`.
 */

type TaskRow = TaskTimingRow & { note: string }

function taskRowsWithNotes(rows: TaskTimingRow[]): TaskRow[] {
  return rows.map((row) => ({ ...row, note: '' }))
}

function taskRowSignature(shiftType: string, rows: TaskRow[]): string {
  return JSON.stringify({
    shiftType,
    tasks: rows
      .filter((row) => row.taskId || row.taskLabel)
      .map((row) => row.taskLabel),
  })
}

export interface CreateShiftModalProps {
  open: boolean
  onClose: () => void
  mode?: 'create' | 'edit'
  /** The manual draft being edited. Writes are refused without it. */
  versionId: string
  staff: StaffLite[]
  dates: string[]
  shiftDefs: ShiftDef[]
  taskDefs: TaskDefOut[]
  /** Pre-selection when opened from a cell. */
  initial?: {
    staffId?: string; date?: string; shiftType?: string; tasks?: string[]
    /** Existing grid assignment for a reopen; never manufactured by the modal. */
    assignmentId?: string | null
  } | null
  /** Called only once the cell and every requested task time are saved. */
  onSaved: (summary: {
    staffName: string; date: string; shiftType: string; wasWorking: boolean
    taskTiming: { requested: number; saved: number; failedLabels: string[] }
  }) => void
  onDeleted?: (summary: { staffName: string; date: string }) => void
}

const PINK = '#E8187A'

function hhmm(value?: string | null): string {
  return value ? value.slice(0, 5) : '--:--'
}

export function CreateShiftModal({
  open, onClose, mode = 'create', versionId, staff, dates, shiftDefs, taskDefs,
  initial, onSaved, onDeleted,
}: CreateShiftModalProps) {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const L = {
    title_create: isZH ? '建立更期與工作安排' : 'Create Shift & Task Plan',
    title_edit: isZH ? '編輯更期與工作安排' : 'Edit Shift & Task Plan',
    ai_sub: isZH ? '排更與工作分配' : 'Shift & task assignment',
    date: isZH ? '日期' : 'Date',
    position: isZH ? '職級' : 'Rank',
    all_positions: isZH ? '所有職級' : 'All ranks',
    employee: isZH ? '指派員工' : 'Assign Staff',
    no_staff: isZH ? '此職級暫無員工' : 'No staff at this rank',
    time_range: isZH ? '時間範圍' : 'Time Range',
    time_note: isZH ? '由更別定義，不可個別修改' : 'set by the shift definition',
    shift_type: isZH ? '更別類型' : 'Shift Type',
    pick_shift: isZH ? '請選擇更別' : 'Select a shift type',
    task_schedule: isZH ? '工作時間表' : 'Task Schedule',
    adjustable: isZH ? '可調整時間及工作內容' : 'Adjustable time & tasks',
    to: isZH ? '至' : 'to',
    delete_task: isZH ? '刪除' : 'Remove',
    task_ph: isZH ? '選擇工作內容' : 'Select task',
    note_ph: isZH ? '工作備註：後端未提供保存合約' : 'Task notes: saving is not supported by the current API',
    add_task: isZH ? '+ 新增工作項目' : '+ Add Task',
    add_task_manual: isZH ? '+ 手動新增工作項目' : '+ Add Task Manually',
    manual_warning: isZH ? '手動模式：顯示所有工作項目；伺服器儲存前仍會核對資格。' : 'Manual mode shows all tasks; the server still validates eligibility before saving.',
    item: isZH ? '項目' : 'Item',
    no_tasks: isZH ? '此更別／職級沒有可指派的任務' : 'No tasks this rank may do on this shift',
    delete_shift: isZH ? '刪除更期' : 'Delete Shift',
    cancel: isZH ? '取消' : 'Cancel',
    save: isZH ? '儲存更改' : 'Save Changes',
    rejected: isZH ? '此更次不可指派以下任務' : 'These tasks are not allowed on this shift',
    readonly: isZH ? '此版本不可編輯' : 'This version is not editable',
    loading_times: isZH ? '正在讀取已儲存的工作時間…' : 'Loading saved task times…',
    time_saved: isZH ? '時間已儲存' : 'Time saved',
    time_failed: isZH ? '時間未儲存' : 'Time not saved',
    time_not_recorded: isZH ? '尚未記錄工作時間；此工作可維持為無時間安排。' : 'No task time is recorded; this task may remain label-only.',
    time_incomplete: isZH ? '請先修正所有未儲存的工作時間，然後重試。' : 'Fix each unsaved task time, then retry.',
    retry_failed: isZH ? '重試未儲存時間' : 'Retry unsaved time(s)',
  }

  const [rank, setRank] = useState('ALL')
  const [staffId, setStaffId] = useState('')
  const [date, setDate] = useState('')
  const [shiftType, setShiftType] = useState('')
  const [rows, setRows] = useState<TaskRow[]>([])
  const [busy, setBusy] = useState(false)
  const [loadingTimes, setLoadingTimes] = useState(false)
  const [hydrationFailed, setHydrationFailed] = useState(false)
  const [err, setErr] = useState('')
  const [issues, setIssues] = useState<string[]>([])
  const [manualMode, setManualMode] = useState(false)
  // Once a cell succeeds this ID is retained for task-only retries. It ensures a
  // retry never writes the roster cell a second time.
  const [shiftAssignmentId, setShiftAssignmentId] = useState<string | null>(null)
  const [savedCellSignature, setSavedCellSignature] = useState('')

  const ranks = useMemo(
    () => ['ALL', ...Array.from(new Set(staff.map((s) => s.rank))).sort()],
    [staff],
  )
  const visibleStaff = useMemo(
    () => (rank === 'ALL' ? staff : staff.filter((s) => s.rank === rank)),
    [staff, rank],
  )
  const selected = staff.find((s) => s.id === staffId) ?? null
  const def = shiftDefs.find((d) => d.shift_type === shiftType) ?? null
  const hasFailedTiming = rows.some((row) => row.timingStatus === 'failed')

  // Only tasks this rank may do on this shift - the same rule the server applies,
  // so the picker cannot offer something the write would refuse.
  const availableTasks = useMemo(() => {
    if (!selected || !shiftType) return []
    return taskDefs.filter((td) => canSeeTask(selected.rank, td, shiftType, shiftDefs))
  }, [selected, shiftType, taskDefs, shiftDefs])

  // All tasks (for manual mode when no eligible tasks found)
  const allTasks = useMemo(() => taskDefs, [taskDefs])

  // The tasks to show in the picker: eligible tasks normally, all tasks in manual mode
  const pickerTasks = manualMode ? allTasks : availableTasks

  useEffect(() => {
    if (!open) return
    let active = true
    const initialTasks = initial?.tasks ?? []
    const initialRows: TaskRow[] = initialTasks.map((label, index) => {
      const definition = taskDefs.find((task) => taskLabel(task) === label)
      return {
        id: `task-label-${index}-${label}`,
        taskId: definition?.id || '',
        taskLabel: label,
        start: '', end: '', note: '', timingStatus: 'idle',
      }
    })
    setErr(''); setIssues([]); setRows(initialRows); setManualMode(false); setHydrationFailed(false)
    setRank('ALL')
    setStaffId(initial?.staffId || staff[0]?.id || '')
    setDate(initial?.date || dates[0] || '')
    setShiftType(initial?.shiftType || '')
    setShiftAssignmentId(initial?.assignmentId || null)
    setSavedCellSignature(taskRowSignature(initial?.shiftType || '', initialRows))

    if (!initial?.assignmentId) {
      setLoadingTimes(false)
      return () => { active = false }
    }

    setLoadingTimes(true)
    // This is a read-only reopen hydration. It never retries or creates a task.
    api.taskAssignments({ shiftAssignmentId: initial.assignmentId })
      .then((assignments) => {
        if (!active) return
        const hydrated = taskRowsWithNotes(hydrateTaskTimingRows(
          initialTasks,
          taskDefs.map((task) => ({ id: task.id, label: taskLabel(task) })),
          assignments,
        ))
        setRows(hydrated)
        setSavedCellSignature(taskRowSignature(initial?.shiftType || '', hydrated))
      })
      .catch((error) => {
        if (active) {
          setHydrationFailed(true)
          setErr(error instanceof Error ? error.message : 'Failed to load saved task times')
        }
      })
      .finally(() => { if (active) setLoadingTimes(false) })
    return () => { active = false }
  }, [open, initial?.assignmentId, initial?.date, initial?.shiftType, initial?.staffId, initial?.tasks, staff, dates, taskDefs])

  // A rank filter that hides the selected person would leave the form pointing
  // at somebody the list no longer shows.
  useEffect(() => {
    if (staffId && !visibleStaff.some((s) => s.id === staffId)) {
      setStaffId(visibleStaff[0]?.id || '')
    }
  }, [visibleStaff, staffId])

  // Changing the shift changes which tasks are legal, so rows that are no longer
  // offered are dropped rather than left to be rejected on save.
  useEffect(() => {
    if (!manualMode) {
      const allowed = new Set(availableTasks.map((t) => t.id))
      // A persisted or failed row remains visible even if eligibility changed
      // since it was saved. Hiding it would conceal a task time that needs
      // recovery; the server remains the authority on any later write.
      setRows((prev) => prev.filter((r) => !r.taskId || allowed.has(r.taskId) || r.timingStatus !== 'idle'))
    }
  }, [availableTasks, manualMode])

  const addRow = () => setRows((prev) => [...prev, {
    id: `${prev.length}-${Date.now()}`,
    start: hhmm(def?.start_time) === '--:--' ? '' : hhmm(def?.start_time),
    end: hhmm(def?.end_time) === '--:--' ? '' : hhmm(def?.end_time),
    taskId: '', taskLabel: '', note: '', timingStatus: 'idle',
  }])
  const updateRow = (id: string, patch: Partial<TaskRow>) =>
    setRows((prev) => prev.map((row) => {
      if (row.id !== id) return row
      const changesTiming = (patch.start !== undefined && patch.start !== row.start)
        || (patch.end !== undefined && patch.end !== row.end)
        || (patch.taskId !== undefined && patch.taskId !== row.taskId)
        || (patch.taskLabel !== undefined && patch.taskLabel !== row.taskLabel)
      // A changed clock must be written again; a stale saved marker would make
      // the recovery helper skip the new value. Persisted task identities stay
      // locked in the UI because renaming them safely needs backend deletion.
      return changesTiming
        ? { ...row, ...patch, timingStatus: 'idle', timingError: undefined, timingAdvisory: undefined }
        : { ...row, ...patch }
    }))
  const removeRow = (id: string) => setRows((prev) => prev.filter((r) => r.id !== id))

  const chooseStaff = (nextStaffId: string) => {
    if (nextStaffId !== staffId) {
      // Switching cell in the form is an explicit new target. The old assignment
      // ID must not be used to write times against a different staff/date cell.
      setShiftAssignmentId(null); setSavedCellSignature(''); setRows([])
    }
    setStaffId(nextStaffId)
  }
  const chooseDate = (nextDate: string) => {
    if (nextDate !== date) {
      setShiftAssignmentId(null); setSavedCellSignature(''); setRows([])
    }
    setDate(nextDate)
  }

  const timeError = (error: TaskTimeValidationError): string => {
    if (error === 'incomplete_time') return isZH ? '工作開始及結束時間必須一併填寫。' : 'Task start and end times must be entered together.'
    if (error === 'invalid_time') return isZH ? '工作時間必須是有效的24小時制時間。' : 'Task times must use valid 24-hour times.'
    return isZH ? '工作日期無效。' : 'The task date is invalid.'
  }

  async function handleSave() {
    if (!versionId) { setErr(L.readonly); return }
    if (!selected || !date || !shiftType) return
    // A GET error is not evidence of an empty schedule. Do not overwrite a
    // recoverable existing assignment until its task state can be read.
    if (hydrationFailed) return
    setBusy(true); setErr(''); setIssues([])
    const chosen = rows.filter((row) => row.taskId || row.taskLabel)
    const invalid = chosen.find((row) => {
      const timing = taskDateTimes(date, row.start, row.end)
      return !timing.ok
    })
    if (invalid) {
      const timing = taskDateTimes(date, invalid.start, invalid.end)
      if (!timing.ok) {
        setRows((current) => current.map((row) => row.id === invalid.id
          ? { ...row, timingStatus: 'failed', timingError: timeError(timing.error) }
          : row))
        setErr(timeError(timing.error))
        setBusy(false)
        return
      }
    }
    try {
      const signature = taskRowSignature(shiftType, chosen)
      let assignmentId = shiftAssignmentId
      // The initial cell write must happen before time rows, but a retained ID
      // prevents a partial-time retry from writing it again. A changed cell is an
      // explicit new edit, not a hidden retry, and therefore legitimately upserts.
      if (!assignmentId || signature !== savedCellSignature) {
        const result = await api.upsertCell({
          roster_version_id: versionId, staff_id: selected.id, date,
          shift_type: shiftType, tasks: chosen.map((row) => row.taskLabel),
        })
        assignmentId = result.assignment_id
        setShiftAssignmentId(assignmentId)
        setSavedCellSignature(signature)
      }

      // `set_cell` deletes and recreates the underlying assignment. If a cell
      // label change required that API call, every prior timing belongs to the
      // removed assignment and must be written to its replacement as well.
      const rowsForTiming = signature !== savedCellSignature
        ? rows.map((row) => row.timingStatus === 'saved'
          ? { ...row, timingStatus: 'idle' as const, timingError: undefined }
          : row)
        : rows
      const result = await persistTaskTimings({
        shiftAssignmentId: assignmentId,
        rows: rowsForTiming,
        timeFor: (row) => taskDateTimes(date, row.start, row.end),
        upsert: api.createTaskAssignment,
      })
      const nextRows = result.rows.map((row) => ({
        ...row,
        note: rows.find((existing) => existing.id === row.id)?.note || '',
      }))
      setRows(nextRows)
      if (!result.complete) {
        setErr(L.time_incomplete)
        return
      }
      onSaved({
        staffName: selected.name_en || selected.name, date, shiftType,
        wasWorking: !!initial?.shiftType,
        taskTiming: { requested: result.attempted, saved: result.saved, failedLabels: [] },
      })
      onClose()
    } catch (e) {
      // An eligibility refusal is a list of fixable reasons, so the dialog stays
      // open and shows them rather than closing on a one-liner.
      if (e instanceof ApiRuleError) setIssues(issueLines(e.issues, isZH))
      else setErr(e instanceof Error ? e.message : 'Save failed')
    } finally { setBusy(false) }
  }

  async function handleDelete() {
    if (!selected || !date || !versionId) return
    setBusy(true); setErr('')
    try {
      await api.clearCell(versionId, selected.id, date)
      onDeleted?.({ staffName: selected.name_en || selected.name, date })
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Delete failed')
    } finally { setBusy(false) }
  }

  const isEditMode = mode === 'edit'

  return (
    // Busy-close guard remains: if (!next && !busy) onClose() applies when no
    // partial task-time recovery must stay visible.
    <Dialog open={open} onOpenChange={(next) => { if (!next && !busy && !hasFailedTiming) onClose() }}>
      <DialogContent className="w-[min(96vw,860px)] max-w-none rounded-2xl max-h-[90vh] overflow-hidden p-0">
        <div className="flex min-w-0 flex-col max-h-[90vh]">
          <DialogHeader className="px-6 pt-6 pb-3 border-b border-gray-100">
            <div className="flex min-w-0 items-center gap-3">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0" style={{ background: '#fce8f3' }}>✨</div>
              <div className="min-w-0">
                <DialogTitle className="text-lg font-bold break-words">
                  {isEditMode ? L.title_edit : L.title_create}
                </DialogTitle>
                <p className="text-xs font-semibold mt-0.5" style={{ color: PINK }}>{L.ai_sub}</p>
              </div>
            </div>
          </DialogHeader>

          <div className="min-w-0 px-6 py-4 overflow-y-auto">
            <div className="space-y-4 min-w-0">
              {/* Date - constrained to the period being edited */}
              <div>
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.date}</label>
                <Select value={date} onValueChange={chooseDate} disabled={busy || loadingTimes || hasFailedTiming}>
                  <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {dates.map((iso) => <SelectItem key={iso} value={iso}>{iso}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              {/* Rank filter + staff */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 min-w-0">
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.position}</label>
                  <Select value={rank} onValueChange={setRank} disabled={busy || loadingTimes || hasFailedTiming}>
                    <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ranks.map((r) => (
                        <SelectItem key={r} value={r}>{r === 'ALL' ? L.all_positions : r}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.employee}</label>
                  <Select value={staffId} onValueChange={chooseStaff} disabled={busy || loadingTimes || hasFailedTiming}>
                    <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {visibleStaff.length === 0
                        ? <SelectItem value="none" disabled>{L.no_staff}</SelectItem>
                        : visibleStaff.map((s) => (
                          <SelectItem key={s.id} value={s.id}>
                            {(s.name_en || s.name)}（{s.rank}）
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Shift type + its hours */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 min-w-0">
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.shift_type}</label>
                  <Select value={shiftType} onValueChange={setShiftType} disabled={busy || loadingTimes || hasFailedTiming}>
                    <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full">
                      <SelectValue placeholder={L.pick_shift} />
                    </SelectTrigger>
                    <SelectContent>
                      {shiftDefs.map((sd) => (
                        <SelectItem key={sd.id} value={sd.shift_type}>
                          {sd.shift_type}{sd.label ? ` · ${sd.label}` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.time_range}</label>
                  <div className="mt-1.5 px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 text-gray-700">
                    {def
                      ? `${hhmm(def.start_time)} ${L.to} ${hhmm(def.end_time)}${def.cross_midnight ? ' ⏭' : ''}`
                      : '—'}
                  </div>
                  <div className="text-[10px] text-gray-400 mt-1">{L.time_note}</div>
                </div>
              </div>

              {/* Task schedule - only when the shift is a working one */}
             {def?.is_working && (
               <div className="min-w-0">
                 <div className="flex flex-col gap-2 mb-2 sm:flex-row sm:items-center sm:justify-between">
                   <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.task_schedule}</label>
                   <span className="text-[9px] font-bold px-2 py-0.5 rounded w-fit" style={{ background: '#fce8f3', color: PINK }}>
                     {L.adjustable}
                   </span>
                 </div>

                  {availableTasks.length === 0 && !manualMode && rows.length === 0 ? (
                    <div className="text-[11px] text-gray-400 border border-dashed border-gray-200 rounded-xl p-3 text-center space-y-2">
                      {L.no_tasks}
                      {allTasks.length > 0 && (
                        <button type="button" onClick={() => setManualMode(true)}
                          className="block mx-auto mt-2 text-xs font-semibold px-3 py-1.5 rounded-lg border border-pink-200 hover:bg-pink-50 transition-colors"
                          style={{ color: PINK }}>
                          {L.add_task_manual}
                        </button>
                      )}
                    </div>
                  ) : (
                    <>
                      {manualMode && (
                        <div className="text-[10px] px-3 py-2 rounded-lg mb-2 border border-amber-200" style={{ background: '#fffbeb', color: '#92400e' }}>
                          {L.manual_warning}
                        </div>
                      )}
                      <div className="space-y-2 min-w-0">
                        {rows.map((row, index) => (
                          <div key={row.id} className="border border-gray-200 rounded-xl p-3 bg-gray-50 min-w-0">
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_1fr_auto] sm:items-center min-w-0">
                              <input type="time" value={row.start} disabled={busy} onChange={(e) => updateRow(row.id, { start: e.target.value })}
                                className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white disabled:bg-gray-100" />
                              <span className="text-xs text-gray-400 shrink-0">{L.to}</span>
                              <input type="time" value={row.end} disabled={busy} onChange={(e) => updateRow(row.id, { end: e.target.value })}
                                className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white disabled:bg-gray-100" />
                              <button type="button" onClick={() => removeRow(row.id)} disabled={busy || row.taskIdentityLocked || row.timingStatus !== 'idle'}
                                className="text-xs font-semibold text-red-500 disabled:opacity-40">
                                {L.delete_task}
                              </button>
                            </div>
                            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 min-w-0">
                              <Select value={row.taskId} onValueChange={(value: string) => {
                                const task = taskDefs.find((item) => item.id === value)
                                updateRow(row.id, {
                                  taskId: value, taskLabel: task ? taskLabel(task) : '',
                                  timingStatus: 'idle', timingError: undefined, timingAdvisory: undefined,
                                })
                              }} disabled={busy || row.taskIdentityLocked}>
                                <SelectTrigger className="rounded-xl bg-white border-gray-200 w-full min-w-0">
                                  <SelectValue placeholder={L.task_ph} />
                                </SelectTrigger>
                                <SelectContent>
                                  {pickerTasks.map((td) => (
                                    <SelectItem key={td.id} value={td.id}>{taskLabel(td)}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                              <input type="text" value={row.note} disabled
                                title={L.note_ph}
                                onChange={(e) => updateRow(row.id, { note: e.target.value })}
                                placeholder={L.note_ph}
                                className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white min-w-0" />
                            </div>
                            <div className="mt-2 text-[11px] text-gray-500 break-words">
                              {L.item} {index + 1}：{row.start || '--:--'} - {row.end || '--:--'} ／
                              {row.taskLabel || (taskDefs.find((t) => t.id === row.taskId)
                                ? taskLabel(taskDefs.find((t) => t.id === row.taskId)!) : '—')}
                            </div>
                            {row.timingStatus === 'saved' && (
                              <div className="mt-1 text-[10px] font-semibold text-emerald-700">{L.time_saved}</div>
                            )}
                            {row.timingStatus === 'failed' && (
                              <div className="mt-1 text-[10px] font-semibold text-rose-600">
                                {L.time_failed}{row.timingError ? `: ${row.timingError}` : ''}
                              </div>
                            )}
                            {row.timingStatus === 'idle' && row.timingAdvisory && (
                              <div className="mt-1 text-[10px] font-semibold text-amber-700">
                                {L.time_not_recorded}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                      <button type="button" onClick={addRow} disabled={busy}
                        className="mt-3 text-xs font-semibold" style={{ color: PINK }}>
                        {L.add_task}
                      </button>
                    </>
                  )}
                </div>
              )}

              {issues.length > 0 && (
                <div className="rounded-xl border p-3" style={{ background: '#fff1f2', borderColor: '#fecdd3' }}>
                  <div className="text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: '#be123c' }}>
                    {L.rejected}
                  </div>
                  <ul className="space-y-1">
                    {issues.map((line, i) => (
                      <li key={i} className="text-[11px]" style={{ color: '#9f1239' }}>{line}</li>
                    ))}
                  </ul>
                </div>
              )}
              {err && <div className="text-xs text-rose-600">{err}</div>}
              {loadingTimes && <div className="text-xs text-gray-500">{L.loading_times}</div>}
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-100 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="w-full sm:w-auto">
              {isEditMode && onDeleted ? (
                <Button variant="outline" onClick={handleDelete} disabled={busy || hasFailedTiming}
                  className="w-full sm:w-auto rounded-xl text-xs text-red-500 border-red-200 hover:bg-red-50">
                  {L.delete_shift}
                </Button>
              ) : (
                <Button variant="outline" onClick={onClose} disabled={busy || hasFailedTiming} className="w-full sm:w-auto rounded-xl text-xs">
                  {L.cancel}
                </Button>
              )}
            </div>
            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
              {isEditMode && (
                <Button variant="outline" onClick={onClose} disabled={busy || hasFailedTiming} className="w-full sm:w-auto rounded-xl text-xs">
                  {L.cancel}
                </Button>
              )}
              <Button onClick={handleSave} disabled={busy || loadingTimes || hydrationFailed || !staffId || !date || !shiftType}
                className="w-full sm:w-auto rounded-xl text-xs text-white"
                style={{ background: PINK }}>
                {busy ? '…' : rows.some((row) => row.timingStatus === 'failed') ? L.retry_failed : L.save}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
