"use client"

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useLang } from '@/components/layout/LanguageContext'
import { ApiRuleError, api } from '@/lib/api'
import type { ShiftDef, StaffLite, TaskAssignment, TaskDefOut } from '@/lib/apiTypes'
import { taskDateTimes, type TaskTimeValidationError } from '@/lib/roster-ui'
import { canSeeTask, issueLines, taskLabel } from '@/lib/shiftRules'

/**
 * Full cell editor backed only by the authenticated organisation's dictionaries.
 *
 * The current MVP contract stores shift code plus task labels/time rows. It does
 * not have assignment fields for post/workstation, meal, free-text notes, or
 * task detail/category segments. Those controls stay visibly disabled instead
 * of presenting a value that would be silently discarded on save.
 */
type TaskRow = {
  id: string; taskId: string; label: string; start: string; end: string
  escortLocation: string; immutable?: boolean
}

export type OccupiedRosterCell = { staffId: string; date: string; assignmentId?: string | null }

export interface CreateShiftModalProps {
  open: boolean
  onClose: () => void
  mode?: 'create' | 'edit'
  versionId: string
  staff: StaffLite[]
  dates: string[]
  shiftDefs: ShiftDef[]
  taskDefs: TaskDefOut[]
  /** Existing assignments from the authoritative grid; create never replaces one blindly. */
  occupiedCells?: OccupiedRosterCell[]
  initial?: {
    staffId?: string; date?: string; shiftType?: string; tasks?: string[]; assignmentId?: string | null
  } | null
  onSaved: (summary: { staffName: string; date: string; shiftType: string; wasWorking: boolean }) => void
  onDeleted?: (summary: { staffName: string; date: string }) => void
}

const PINK = '#E8187A'

function hhmm(value?: string | null): string { return value ? value.slice(0, 5) : '--:--' }
function taskTime(value?: string | null): string { return value?.slice(11, 16) || '' }

function missingLabels(expected: string[], actual: string[]): string[] {
  const remaining = new Map<string, number>()
  expected.forEach((label) => remaining.set(label, (remaining.get(label) ?? 0) + 1))
  actual.forEach((label) => remaining.set(label, Math.max(0, (remaining.get(label) ?? 0) - 1)))
  return [...remaining].flatMap(([label, count]) => Array.from({ length: count }, () => label))
}

function timeValidationText(error: TaskTimeValidationError, isZH: boolean): string {
  if (error === 'invalid_date') return isZH ? '日期格式無效，不能儲存工作時段。' : 'The date is invalid, so task timings cannot be saved.'
  if (error === 'incomplete_time') return isZH ? '每個工作時段必須同時有開始及結束時間。' : 'A task timing needs both a start and an end time.'
  return isZH ? '工作時間格式無效。' : 'A task time is invalid.'
}

export function CreateShiftModal({
  open, onClose, mode = 'create', versionId, staff, dates, shiftDefs, taskDefs, occupiedCells = [], initial, onSaved, onDeleted,
}: CreateShiftModalProps) {
  const { lang } = useLang()
  const isZH = lang === 'zh'
  const L = {
    create: isZH ? '建立更期與工作安排' : 'Create Shift & Task Plan',
    edit: isZH ? '編輯更期與工作安排' : 'Edit Shift & Task Plan',
    subtitle: isZH ? '排更與工作分配' : 'Shift & task assignment',
    rank: isZH ? '職級' : 'Rank', allRanks: isZH ? '所有職級' : 'All ranks',
    staff: isZH ? '指派員工' : 'Assign staff', date: isZH ? '日期' : 'Date',
    shift: isZH ? '更別類型' : 'Shift type', chooseShift: isZH ? '請選擇更別' : 'Select a shift type',
    post: isZH ? '崗位／工作站' : 'Post / workstation', meal: isZH ? '用膳時段' : 'Meal window',
    time: isZH ? '固定時間範圍' : 'Fixed time range', fixed: isZH ? '由機構更別字典固定，不能個別修改' : 'Fixed by the facility shift dictionary; not individually editable',
    taskSchedule: isZH ? '工作時間表' : 'Task schedule', taskHelp: isZH ? '每個已選任務可保存一個開始／結束時間。' : 'Each selected task can persist one start/end time.',
    category: isZH ? '任務類別' : 'Task category', detail: isZH ? '詳細內容' : 'Detail',
    addTask: isZH ? '＋ 新增工作項目' : '+ Add task', remove: isZH ? '刪除' : 'Remove', to: isZH ? '至' : 'to',
    note: isZH ? '備註／假期原因' : 'Notes / leave reason',
    unsupported: isZH ? '目前MVP API未提供此欄位的儲存合約；已停用，避免顯示為已儲存。' : 'The current MVP API has no persistence contract for this field. It is disabled to avoid claiming it was saved.',
    duplicate: isZH ? '同一任務目前只能保存一個時段。' : 'The current API can save one time range per task.',
    unresolvedTask: isZH ? '此既有任務沒有可重建的本機構task_id。為防止更新更次時遺失任務，儲存已停用；請先由資料管理員修正任務字典／合約。' : 'An existing task has no organisation task_id that can be reconstructed. Save is blocked to prevent losing it when the shift is replaced; correct the task dictionary/contract first.',
    missingAssignment: isZH ? '此更次缺少task assignment識別碼，未能讀取及保留既有任務；儲存已停用。' : 'This shift lacks the task-assignment identifier needed to load and preserve existing tasks. Save is blocked.',
    incompleteLoad: isZH ? '伺服器返回的任務列少於此格原有任務；為防止儲存時遺失任務，儲存已停用。' : 'The server returned fewer task rows than this cell originally had. Save is blocked to prevent task loss.',
    occupied: isZH ? '此員工及日期已有更次。請在原有格子編輯，不能用新增更次覆寫。' : 'This staff/date already has a shift. Edit the existing cell instead of overwriting it from Create Shift.',
    destination: isZH ? '目的地代碼' : 'Escort destination code',
    immutable: isZH ? '未識別的既有任務（不可修改）' : 'Unrecognised existing task (read-only)',
    noTasks: isZH ? '此員工／更別沒有可指派的任務。' : 'No task is available for this staff member and shift.',
    delete: isZH ? '刪除更期' : 'Delete shift', cancel: isZH ? '取消' : 'Cancel', save: isZH ? '儲存更改' : 'Save changes',
    rejected: isZH ? '此更次不可指派以下任務' : 'These tasks are not allowed on this shift',
    partial: isZH ? '更別及任務類別已寫入，但只有部分任務時段完成。視窗保持開啟；請修正後重新儲存，不能視為全部成功。' : 'The shift and task categories were saved, but only some task timings completed. This window remains open; fix and save again—do not treat this as fully saved.',
    loading: isZH ? '正在讀取已儲存任務時段…' : 'Loading saved task timings…',
  }

  const [rank, setRank] = useState('ALL')
  const [staffId, setStaffId] = useState('')
  const [date, setDate] = useState('')
  const [shiftType, setShiftType] = useState('')
  const [rows, setRows] = useState<TaskRow[]>([])
  const [loadingTasks, setLoadingTasks] = useState(false)
  const [taskLoadProblem, setTaskLoadProblem] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [issues, setIssues] = useState<string[]>([])

  const ranks = useMemo(() => ['ALL', ...Array.from(new Set(staff.map((item) => item.rank))).sort()], [staff])
  const visibleStaff = useMemo(() => rank === 'ALL' ? staff : staff.filter((item) => item.rank === rank), [rank, staff])
  const selected = staff.find((item) => item.id === staffId) ?? null
  const definition = shiftDefs.find((item) => item.shift_type === shiftType) ?? null
  const editingCell = mode === 'edit'
  const occupiedCell = !editingCell
    ? occupiedCells.find((cell) => cell.staffId === staffId && cell.date === date)
    : undefined
  const availableTasks = useMemo(() => {
    if (!selected || !shiftType) return []
    return taskDefs.filter((item) => canSeeTask(selected.rank, item, shiftType, shiftDefs))
  }, [selected, shiftType, taskDefs, shiftDefs])
  useEffect(() => {
    if (!open) return
    setErr(''); setIssues([]); setRank('ALL')
    setStaffId(initial?.staffId || staff[0]?.id || '')
    setDate(initial?.date || dates[0] || '')
    setShiftType(initial?.shiftType || '')
    setRows([])
    setTaskLoadProblem(mode === 'edit' && !initial?.assignmentId ? L.missingAssignment : '')
    if (mode === 'edit' && !initial?.assignmentId) setErr(L.missingAssignment)
    setLoadingTasks(false)
  }, [open, initial, staff, dates, mode, L.missingAssignment])

  useEffect(() => {
    if (staffId && !visibleStaff.some((item) => item.id === staffId)) setStaffId(visibleStaff[0]?.id || '')
  }, [staffId, visibleStaff])

  useEffect(() => {
    if (!open || !initial?.assignmentId) return
    let cancelled = false
    setLoadingTasks(true)
    setTaskLoadProblem('')
    api.taskAssignments({ shiftAssignmentId: initial.assignmentId })
      .then((items) => {
        if (cancelled) return
        const missing = missingLabels(initial?.tasks ?? [], items.map((item) => item.task_label))
        setRows(items.map((item: TaskAssignment, index) => ({
          id: item.id || `${index}-${Date.now()}`,
          taskId: (() => {
            const task = (item.task_id && taskDefs.find((candidate) => candidate.id === item.task_id))
              || taskDefs.find((candidate) => taskLabel(candidate) === item.task_label)
            return task && taskLabel(task) === item.task_label ? task.id : ''
          })(),
          label: item.task_label,
          start: taskTime(item.start_at), end: taskTime(item.end_at),
          escortLocation: item.escort_location || '',
          immutable: !taskDefs.some((task) => task.id === item.task_id && taskLabel(task) === item.task_label)
            && !taskDefs.some((task) => !item.task_id && taskLabel(task) === item.task_label),
        })))
        if (missing.length) {
          const message = `${L.incompleteLoad} (${missing.join(', ')})`
          setTaskLoadProblem(message)
          setErr(message)
        }
      })
      .catch((cause) => {
        if (cancelled) return
        const message = cause instanceof Error ? cause.message : 'Could not load task timings'
        setTaskLoadProblem(message)
        setErr(message)
      })
      .finally(() => { if (!cancelled) setLoadingTasks(false) })
    return () => { cancelled = true }
  }, [open, initial?.assignmentId, taskDefs])

  useEffect(() => {
    if (!open || initial?.assignmentId || !initial?.tasks?.length || !taskDefs.length) return
    setRows(initial.tasks.flatMap((label, index) => {
      const found = taskDefs.find((task) => taskLabel(task) === label)
      return [{ id: `${index}-${label}`, taskId: found?.id || '', label, start: '', end: '', escortLocation: '', immutable: !found }]
    }))
  }, [open, initial?.assignmentId, initial?.tasks, taskDefs])

  const changeRow = (id: string, patch: Partial<TaskRow>) => setRows((current) => current.map((row) => row.id === id ? { ...row, ...patch } : row))
  const addRow = () => setRows((current) => [...current, {
    id: `${Date.now()}-${current.length}`, taskId: '', label: '',
    start: hhmm(definition?.start_time) === '--:--' ? '' : hhmm(definition?.start_time),
    end: hhmm(definition?.end_time) === '--:--' ? '' : hhmm(definition?.end_time),
    escortLocation: '',
  }])
  const removeRow = (id: string) => setRows((current) => current.filter((row) => row.id !== id || row.immutable))

  async function handleSave() {
    if (!versionId || !selected || !date || !shiftType || loadingTasks || taskLoadProblem) return
    if (occupiedCell) { setErr(L.occupied); return }
    const chosen = rows.filter((row) => row.taskId || row.label)
    if (chosen.some((row) => !row.taskId)) { setErr(L.unresolvedTask); return }
    if (chosen.some(row => taskDefs.find(task => task.id === row.taskId)?.needs_location && !row.escortLocation.trim())) { setErr(isZH ? '陪診任務必須填寫目的地代碼。' : 'Escort tasks require a destination code.'); return }
    const labels = chosen.map((row) => row.label || taskLabel(taskDefs.find((task) => task.id === row.taskId)!))
    if (new Set(labels).size !== labels.length) { setErr(L.duplicate); return }
    const timedRows = chosen.map((row) => ({ row, timing: taskDateTimes(date, row.start, row.end) }))
    const invalidTiming = timedRows.find((item) => !item.timing.ok)
    if (invalidTiming && !invalidTiming.timing.ok) {
      setErr(timeValidationText(invalidTiming.timing.error, isZH))
      return
    }
    setBusy(true); setErr(''); setIssues([])
    try {
      const { assignment_id } = await api.upsertCell({
        roster_version_id: versionId, staff_id: selected.id, date, shift_type: shiftType, tasks: labels,
      })
      let finished = 0
      for (const { row, timing } of timedRows) {
        try {
          await api.createTaskAssignment({
            shift_assignment_id: assignment_id, task_id: row.taskId,
            start_at: timing.ok ? timing.startAt : undefined, end_at: timing.ok ? timing.endAt : undefined,
            escort_location: row.escortLocation || undefined,
          })
          finished += 1
        } catch (cause) {
          const unconfirmed = chosen.slice(finished).map(item => item.label).join(', ')
          const notice = isZH ? `以下任務的自訂時段未確認，伺服器可能已建立預設時段：${unconfirmed}。` : `Custom timings are unconfirmed for these tasks; default timings may already exist on the server: ${unconfirmed}.`
          setErr(`${L.partial} (${finished}/${chosen.length}) ${notice} ${cause instanceof Error ? cause.message : ''}`.trim())
          return
        }
      }
      onSaved({ staffName: selected.name_en || selected.name, date, shiftType, wasWorking: !!initial?.shiftType })
      onClose()
    } catch (cause) {
      if (cause instanceof ApiRuleError) setIssues(issueLines(cause.issues, isZH))
      else setErr(cause instanceof Error ? cause.message : 'Save failed')
    } finally { setBusy(false) }
  }

  async function handleDelete() {
    if (!selected || !date || !versionId) return
    setBusy(true); setErr('')
    try {
      await api.clearCell(versionId, selected.id, date)
      onDeleted?.({ staffName: selected.name_en || selected.name, date })
      onClose()
    } catch (cause) { setErr(cause instanceof Error ? cause.message : 'Delete failed') } finally { setBusy(false) }
  }

  const disabledField = 'mt-1.5 w-full rounded-xl border border-slate-200 bg-slate-100 px-3 py-2.5 text-sm text-slate-400 cursor-not-allowed'
  const inputClass = 'mt-1.5 w-full rounded-xl border border-slate-200 bg-gray-50 px-3 py-2.5 text-sm outline-none focus:border-pink-400'

  return <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
    <DialogContent className="w-[min(96vw,860px)] max-w-none rounded-2xl max-h-[90vh] overflow-hidden p-0">
      <div className="flex min-w-0 flex-col max-h-[90vh]">
        <DialogHeader className="px-6 pt-6 pb-3 border-b border-gray-100">
          <div className="flex min-w-0 items-center gap-3"><div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0" style={{ background: '#fce8f3' }}>✨</div><div className="min-w-0"><DialogTitle className="text-lg font-bold truncate">{mode === 'edit' ? L.edit : L.create}</DialogTitle><p className="text-xs font-semibold mt-0.5" style={{ color: PINK }}>{L.subtitle}</p></div></div>
        </DialogHeader>
        <div className="min-w-0 px-6 py-4 overflow-y-auto">
          <div className="space-y-4 min-w-0">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.rank}<Select value={rank} onValueChange={setRank} disabled={editingCell}><SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full"><SelectValue /></SelectTrigger><SelectContent>{ranks.map((value) => <SelectItem key={value} value={value}>{value === 'ALL' ? L.allRanks : value}</SelectItem>)}</SelectContent></Select></label>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.staff}<Select value={staffId} onValueChange={setStaffId} disabled={editingCell}><SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full"><SelectValue /></SelectTrigger><SelectContent>{visibleStaff.map((item) => <SelectItem key={item.id} value={item.id}>{item.name_en || item.name}（{item.rank}）</SelectItem>)}</SelectContent></Select></label>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.date}<Select value={date} onValueChange={setDate} disabled={editingCell}><SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full"><SelectValue /></SelectTrigger><SelectContent>{dates.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></label>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.shift}<Select value={shiftType} onValueChange={setShiftType}><SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full"><SelectValue placeholder={L.chooseShift} /></SelectTrigger><SelectContent>{shiftDefs.map((item) => <SelectItem key={item.id} value={item.shift_type}>{item.shift_type}{item.label ? ` · ${item.label}` : ''}</SelectItem>)}</SelectContent></Select></label>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2"><label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.post}<input disabled value="" placeholder={L.unsupported} className={disabledField} /></label><label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.time}<div className="mt-1.5 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm text-gray-700">{definition ? `${hhmm(definition.start_time)} ${L.to} ${hhmm(definition.end_time)}${definition.cross_midnight ? ' ⏭' : ''}` : '—'}</div><p className="mt-1 text-[10px] text-gray-400">{L.fixed}</p></label></div>
            <label className="block text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.meal}<input disabled value="" placeholder={L.unsupported} className={disabledField} /></label>
            {definition?.is_working && <section><div className="flex flex-wrap items-start justify-between gap-2"><div><div className="flex items-center gap-2"><h3 className="text-sm font-bold text-gray-900">{L.taskSchedule}</h3><span className="rounded bg-pink-50 px-2 py-0.5 text-[9px] font-bold" style={{ color: PINK }}>{isZH ? '可保存時段' : 'timing persisted'}</span></div><p className="mt-1 text-[10px] text-gray-500">{L.taskHelp}</p></div><button type="button" onClick={addRow} className="rounded-xl border border-pink-200 bg-pink-50 px-3 py-2 text-xs font-semibold" style={{ color: PINK }}>{L.addTask}</button></div>
              {loadingTasks ? <p className="mt-3 text-xs text-gray-400">{L.loading}</p> : availableTasks.length === 0 && rows.length === 0 ? <p className="mt-3 rounded-xl border border-dashed border-gray-200 p-3 text-xs text-gray-400">{L.noTasks}</p> : <div className="mt-3 space-y-3">{rows.map((row, index) => <div key={row.id} className="rounded-xl border border-gray-200 bg-gray-50 p-3"><div className="flex items-center justify-between gap-2"><span className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{isZH ? '項目' : 'Item'} {index + 1}</span>{row.immutable ? <span className="text-[10px] font-semibold text-amber-700">{L.immutable}</span> : <button type="button" onClick={() => removeRow(row.id)} className="text-xs font-semibold text-red-500">{L.remove}</button>}</div><div className="mt-2 grid grid-cols-[1fr_auto_1fr] items-center gap-2"><input type="time" disabled={row.immutable} value={row.start} onChange={(event) => changeRow(row.id, { start: event.target.value })} className={inputClass} /><span className="text-xs text-gray-400">{L.to}</span><input type="time" disabled={row.immutable} value={row.end} onChange={(event) => changeRow(row.id, { end: event.target.value })} className={inputClass} /></div><div className="mt-2 grid gap-2 sm:grid-cols-2">{row.taskId ? <Select value={row.taskId} disabled={row.immutable} onValueChange={(value) => { const task = taskDefs.find((item) => item.id === value); changeRow(row.id, { taskId: value, label: task ? taskLabel(task) : row.label }) }}><SelectTrigger className="rounded-xl bg-white border-gray-200 w-full"><SelectValue placeholder={L.category} /></SelectTrigger><SelectContent>{availableTasks.some((task) => task.id === row.taskId) ? null : <SelectItem value={row.taskId}>{row.label || row.taskId}</SelectItem>}{availableTasks.map((task) => <SelectItem key={task.id} value={task.id}>{taskLabel(task)}</SelectItem>)}</SelectContent></Select> : row.label ? <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800" title={L.unresolvedTask}>{row.label}</div> : <Select value="__choose_task__" onValueChange={(value) => { if (value === '__choose_task__') return; const task = taskDefs.find((item) => item.id === value); if (task) changeRow(row.id, { taskId: value, label: taskLabel(task) }) }}><SelectTrigger className="rounded-xl bg-white border-gray-200 w-full"><SelectValue placeholder={L.category} /></SelectTrigger><SelectContent><SelectItem value="__choose_task__" disabled>{L.category}</SelectItem>{availableTasks.map((task) => <SelectItem key={task.id} value={task.id}>{taskLabel(task)}</SelectItem>)}</SelectContent></Select>}<input disabled value="" placeholder={`${L.detail} · ${L.unsupported}`} className="w-full rounded-xl border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-400 cursor-not-allowed" /></div>{(row.escortLocation || taskDefs.find(task => task.id === row.taskId)?.needs_location) && <label className="mt-2 block text-[9px] font-bold uppercase tracking-wider text-gray-500">{L.destination}<input value={row.escortLocation} disabled={row.immutable} onChange={(event) => changeRow(row.id, { escortLocation: event.target.value })} className={inputClass} /></label>}</div>)}</div>}</section>}
            <label className="block text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.note}<input disabled value="" placeholder={L.unsupported} className={disabledField} /></label>
            <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] leading-5 text-amber-900">{L.unsupported}</p>
            {occupiedCell && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">{L.occupied}</div>}
            {issues.length > 0 && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wider text-rose-700">{L.rejected}</div><ul className="mt-1 space-y-1">{issues.map((line, index) => <li key={index} className="text-[11px] text-rose-800">{line}</li>)}</ul></div>}
            {err && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">{err}</div>}
          </div>
        </div>
        <div className="px-6 py-4 border-t border-gray-100 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><div>{mode === 'edit' && onDeleted ? <Button variant="outline" onClick={handleDelete} disabled={busy} className="rounded-xl text-xs text-red-500 border-red-200">{L.delete}</Button> : <Button variant="outline" onClick={onClose} disabled={busy} className="rounded-xl text-xs">{L.cancel}</Button>}</div><div className="flex gap-2"><Button variant="outline" onClick={onClose} disabled={busy} className="rounded-xl text-xs">{L.cancel}</Button><Button onClick={handleSave} disabled={busy || loadingTasks || !!taskLoadProblem || !!occupiedCell || !staffId || !date || !shiftType} className="rounded-xl text-xs text-white" style={{ background: PINK }}>{busy ? '…' : L.save}</Button></div></div>
      </div>
    </DialogContent>
  </Dialog>
}
