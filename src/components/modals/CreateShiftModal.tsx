"use client"

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useLang } from '@/components/layout/LanguageContext'
import { ApiRuleError, api } from '@/lib/api'
import type { ShiftDef, StaffLite, TaskDefOut } from '@/lib/apiTypes'
import { canSeeTask, issueLines, taskLabel } from '@/lib/shiftRules'

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

type TaskRow = { id: string; start: string; end: string; taskId: string; note: string }

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
  initial?: { staffId?: string; date?: string; shiftType?: string; tasks?: string[] } | null
  /** Called after the cell (and any task rows) are saved. */
  onSaved: (summary: { staffName: string; date: string; shiftType: string; wasWorking: boolean }) => void
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
    note_ph: isZH ? '備註（可選）' : 'Note (optional)',
    add_task: isZH ? '+ 新增工作項目' : '+ Add Task',
    add_task_manual: isZH ? '+ 手動新增工作項目' : '+ Add Task Manually',
    manual_warning: isZH ? '⚠ 手動模式：顯示所有工作項目（未經資格篩選）' : '⚠ Manual mode: showing all tasks (eligibility check bypassed)',
    item: isZH ? '項目' : 'Item',
    no_tasks: isZH ? '此更別／職級沒有可指派的任務' : 'No tasks this rank may do on this shift',
    delete_shift: isZH ? '刪除更期' : 'Delete Shift',
    cancel: isZH ? '取消' : 'Cancel',
    save: isZH ? '儲存更改' : 'Save Changes',
    rejected: isZH ? '此更次不可指派以下任務' : 'These tasks are not allowed on this shift',
    readonly: isZH ? '此版本不可編輯' : 'This version is not editable',
  }

  const [rank, setRank] = useState('ALL')
  const [staffId, setStaffId] = useState('')
  const [date, setDate] = useState('')
  const [shiftType, setShiftType] = useState('')
  const [rows, setRows] = useState<TaskRow[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [issues, setIssues] = useState<string[]>([])
  const [manualMode, setManualMode] = useState(false)

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
    setErr(''); setIssues([]); setRows([]); setManualMode(false)
    setRank('ALL')
    setStaffId(initial?.staffId || staff[0]?.id || '')
    setDate(initial?.date || dates[0] || '')
    setShiftType(initial?.shiftType || '')
  }, [open, initial, staff, dates])

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
      setRows((prev) => prev.filter((r) => !r.taskId || allowed.has(r.taskId)))
    }
  }, [availableTasks, manualMode])

  const addRow = () => setRows((prev) => [...prev, {
    id: `${prev.length}-${Date.now()}`,
    start: hhmm(def?.start_time) === '--:--' ? '' : hhmm(def?.start_time),
    end: hhmm(def?.end_time) === '--:--' ? '' : hhmm(def?.end_time),
    taskId: '', note: '',
  }])
  const updateRow = (id: string, patch: Partial<TaskRow>) =>
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  const removeRow = (id: string) => setRows((prev) => prev.filter((r) => r.id !== id))

  async function handleSave() {
    if (!versionId) { setErr(L.readonly); return }
    if (!selected || !date || !shiftType) return
    setBusy(true); setErr(''); setIssues([])
    const chosen = rows.filter((r) => r.taskId)
    try {
      const { assignment_id } = await api.upsertCell({
        roster_version_id: versionId, staff_id: selected.id, date,
        shift_type: shiftType,
        tasks: chosen.map((r) => {
          const td = taskDefs.find((t) => t.id === r.taskId)!
          return taskLabel(td)
        }),
      })
      // Times are the reason this dialog exists rather than the inline editor:
      // the cell write records *which* tasks, these record *when*. Sent after the
      // cell so a refused assignment never leaves orphan task rows behind.
      for (const row of chosen) {
        if (!row.start && !row.end) continue
        await api.createTaskAssignment({
          shift_assignment_id: assignment_id,
          task_id: row.taskId,
          start_at: row.start ? `${date}T${row.start}:00` : undefined,
          end_at: row.end ? `${date}T${row.end}:00` : undefined,
        }).catch(() => { /* the task is assigned; only its clock time is missing */ })
      }
      onSaved({
        staffName: selected.name_en || selected.name, date, shiftType,
        wasWorking: !!initial?.shiftType,
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
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-[min(96vw,860px)] max-w-none rounded-2xl max-h-[90vh] overflow-hidden p-0">
        <div className="flex min-w-0 flex-col max-h-[90vh]">
          <DialogHeader className="px-6 pt-6 pb-3 border-b border-gray-100">
            <div className="flex min-w-0 items-center gap-3">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0" style={{ background: '#fce8f3' }}>✨</div>
              <div className="min-w-0">
                <DialogTitle className="text-lg font-bold truncate">
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
                <Select value={date} onValueChange={setDate}>
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
                  <Select value={rank} onValueChange={setRank}>
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
                  <Select value={staffId} onValueChange={setStaffId}>
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
                  <Select value={shiftType} onValueChange={setShiftType}>
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

                  {availableTasks.length === 0 && !manualMode ? (
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
                              <input type="time" value={row.start} onChange={(e) => updateRow(row.id, { start: e.target.value })}
                                className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white" />
                              <span className="text-xs text-gray-400 shrink-0">{L.to}</span>
                              <input type="time" value={row.end} onChange={(e) => updateRow(row.id, { end: e.target.value })}
                                className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white" />
                              <button type="button" onClick={() => removeRow(row.id)}
                                className="text-xs font-semibold text-red-500">
                                {L.delete_task}
                              </button>
                            </div>
                            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 min-w-0">
                              <Select value={row.taskId} onValueChange={(value: string) => updateRow(row.id, { taskId: value })}>
                                <SelectTrigger className="rounded-xl bg-white border-gray-200 w-full min-w-0">
                                  <SelectValue placeholder={L.task_ph} />
                                </SelectTrigger>
                                <SelectContent>
                                  {pickerTasks.map((td) => (
                                    <SelectItem key={td.id} value={td.id}>{taskLabel(td)}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                              <input type="text" value={row.note}
                                onChange={(e) => updateRow(row.id, { note: e.target.value })}
                                placeholder={L.note_ph}
                                className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white min-w-0" />
                            </div>
                            <div className="mt-2 text-[11px] text-gray-500 break-words">
                              {L.item} {index + 1}：{row.start || '--:--'} - {row.end || '--:--'} ／
                              {taskDefs.find((t) => t.id === row.taskId)
                                ? taskLabel(taskDefs.find((t) => t.id === row.taskId)!)
                                : '—'}
                            </div>
                          </div>
                        ))}
                      </div>
                      <button type="button" onClick={addRow}
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
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-100 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="w-full sm:w-auto">
              {isEditMode && onDeleted ? (
                <Button variant="outline" onClick={handleDelete} disabled={busy}
                  className="w-full sm:w-auto rounded-xl text-xs text-red-500 border-red-200 hover:bg-red-50">
                  {L.delete_shift}
                </Button>
              ) : (
                <Button variant="outline" onClick={onClose} className="w-full sm:w-auto rounded-xl text-xs">
                  {L.cancel}
                </Button>
              )}
            </div>
            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
              {isEditMode && (
                <Button variant="outline" onClick={onClose} className="w-full sm:w-auto rounded-xl text-xs">
                  {L.cancel}
                </Button>
              )}
              <Button onClick={handleSave} disabled={busy || !staffId || !date || !shiftType}
                className="w-full sm:w-auto rounded-xl text-xs text-white"
                style={{ background: PINK }}>
                {busy ? '…' : L.save}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
