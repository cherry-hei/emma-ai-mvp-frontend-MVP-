'use client'

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useLang } from '@/components/layout/LanguageContext'

type TaskRow = {
  id: string
  start: string
  end: string
  task: string
  customTask: string
}

type ShiftFormPayload = {
  date: string
  position: string
  employee: string
  shiftCategory: string
  timeStart: string
  timeEnd: string
  aiToggle: boolean
  shiftType: string
  tasks: { id: string; start: string; end: string; task: string; customTask: string; finalTask: string }[]
}

export interface CreateShiftModalProps {
  open: boolean
  onClose: () => void
  mode: 'create' | 'edit'
  initialShift: { staffId: number; dayIndex: number; shiftType: string; tasks?: string[] } | null
  onSaveChange: (payload: { shiftType: string }) => void
  onDeleteShift: () => void
}

const TASK_OPTIONS_ZH = ['餵藥檢查','傷口護理','病人觀察','口腔餵食','更換尿片','復康訓練','感染控制','文件紀錄','巡房','量度生命表徵']
const TASK_OPTIONS_EN = ['Medication Check','Wound Care','Patient Observation','Oral Feeding','Diaper Change','Rehab Training','Infection Control','Documentation','Ward Round','Vital Signs']

const POSITION_OPTIONS_ZH = [
  { value: 'rn-senior', label: '註冊護士（資深）' },
  { value: 'rn',        label: '註冊護士（RN）' },
  { value: 'en',        label: '登記護士（EN）' },
  { value: 'hw',        label: '健康服務員（HW）' },
  { value: 'pcw',       label: '個人護理員（PCW）' },
  { value: 'pta',       label: '物理治療助理（PTA）' },
  { value: 'cw',        label: '護理員（CW）' },
]

const POSITION_OPTIONS_EN = [
  { value: 'rn-senior', label: 'Senior Registered Nurse' },
  { value: 'rn',        label: 'Registered Nurse (RN)' },
  { value: 'en',        label: 'Enrolled Nurse (EN)' },
  { value: 'hw',        label: 'Health Worker (HW)' },
  { value: 'pcw',       label: 'Personal Care Worker (PCW)' },
  { value: 'pta',       label: 'Physio Therapy Assistant (PTA)' },
  { value: 'cw',        label: 'Care Worker (CW)' },
]

const EMPLOYEE_OPTIONS = [
  { value: 'yu',      label: '余逸詩（RN）',     role: 'rn' },
  { value: 'chan',    label: 'Chan S.M.（RN）',   role: 'rn' },
  { value: 'leung',  label: '梁嘉琪（EN）',       role: 'en' },
  { value: 'wong',   label: '王雅琛（HW）',       role: 'hw' },
  { value: 'jing',   label: '黃靜賢（PCW）',      role: 'pcw' },
  { value: 'sze-kai',label: '黃司琦（PTA）',      role: 'pta' },
  { value: 'ho',     label: '何啟晴（CW）',       role: 'cw' },
]

const SHIFT_OPTIONS_ZH = [
  { value: 'morning',   label: '早更（Regular）' },
  { value: 'afternoon', label: '午更（Regular）' },
  { value: 'night',     label: '夜更（Regular）' },
  { value: 'emergency', label: '緊急補位' },
]

const SHIFT_OPTIONS_EN = [
  { value: 'morning',   label: 'Morning Shift (Regular)' },
  { value: 'afternoon', label: 'Afternoon Shift (Regular)' },
  { value: 'night',     label: 'Night Shift (Regular)' },
  { value: 'emergency', label: 'Emergency Cover' },
]

const SHIFT_TYPE_MAP: Record<string, string> = {
  A: 'morning', B: 'morning', E: 'afternoon', P: 'afternoon',
  'A/N': 'night', AL: 'morning', OFF: 'morning', SLEEP: 'night',
}

function createDefaultTasks(): TaskRow[] {
  return [
    { id: '1', start: '07:00', end: '09:00', task: '餵藥檢查', customTask: '' },
    { id: '2', start: '09:00', end: '11:00', task: '文件紀錄', customTask: '' },
  ]
}

export function CreateShiftModal({ open, onClose, mode = 'create', initialShift, onSaveChange, onDeleteShift }: CreateShiftModalProps) {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const L = {
    title_create:  isZH ? '建立更期與工作安排' : 'Create Shift & Task Plan',
    title_edit:    isZH ? '編輯更期與工作安排' : 'Edit Shift & Task Plan',
    ai_sub:        isZH ? 'AI 智能排更調整' : 'AI Intelligent Scheduling',
    date:          isZH ? '日期' : 'Date',
    position:      isZH ? '選擇職位' : 'Position',
    employee:      isZH ? '指派員工' : 'Assign Staff',
    no_staff:      isZH ? '此職位暫無員工' : 'No staff for this position',
    time_range:    isZH ? '時間範圍' : 'Time Range',
    shift_type:    isZH ? '更別類型' : 'Shift Type',
    task_schedule: isZH ? '工作時間表' : 'Task Schedule',
    adjustable:    isZH ? '可調整時間及工作內容' : 'Adjustable time & tasks',
    to:            isZH ? '至' : 'to',
    delete_task:   isZH ? '刪除' : 'Remove',
    task_ph:       isZH ? '選擇工作內容' : 'Select task',
    custom_ph:     isZH ? '輸入自訂工作內容' : 'Enter custom task',
    extra_ph:      isZH ? '可補充工作內容' : 'Additional notes',
    custom_opt:    isZH ? '其他（自行輸入）' : 'Other (custom)',
    add_task:      isZH ? '+ 新增工作項目' : '+ Add Task',
    item:          isZH ? '項目' : 'Item',
    ai_title:      isZH ? 'Emma AI Task Optimisation' : 'Emma AI Task Optimisation',
    ai_desc:       isZH ? '根據員工能力及更期內容提供 AI 重新編排建議' : 'AI reschedule suggestions based on staff skills',
    delete_shift:  isZH ? '刪除更期' : 'Delete Shift',
    cancel:        isZH ? '取消' : 'Cancel',
    save_ai:       'Save & AI Reschedule Suggestion',
    save:          isZH ? '儲存更改' : 'Save Changes',
  }

  const TASK_OPTIONS   = isZH ? TASK_OPTIONS_ZH   : TASK_OPTIONS_EN
  const POSITION_OPTIONS = isZH ? POSITION_OPTIONS_ZH : POSITION_OPTIONS_EN
  const SHIFT_OPTIONS  = isZH ? SHIFT_OPTIONS_ZH  : SHIFT_OPTIONS_EN

  const [aiToggle, setAiToggle] = useState(true)
  const [date, setDate] = useState('2026-03-19')
  const [position, setPosition] = useState('rn')
  const [employee, setEmployee] = useState('yu')
  const [shiftCategory, setShiftCategory] = useState('morning')
  const [timeStart, setTimeStart] = useState('07:00')
  const [timeEnd, setTimeEnd] = useState('15:00')
  const [tasks, setTasks] = useState<TaskRow[]>(createDefaultTasks())

  useEffect(() => {
    if (!open) return
    if (initialShift) {
      setShiftCategory(SHIFT_TYPE_MAP[initialShift.shiftType] || 'morning')
    } else {
      setShiftCategory('morning')
      setTimeStart('07:00')
      setTimeEnd('15:00')
      setTasks(createDefaultTasks())
    }
  }, [open, initialShift])

  const filteredEmployees = useMemo(() => {
    const normalized = position === 'rn-senior' ? 'rn' : position
    return EMPLOYEE_OPTIONS.filter(item => item.role === normalized)
  }, [position])

  useEffect(() => {
    if (!filteredEmployees.find(item => item.value === employee)) {
      setEmployee(filteredEmployees[0]?.value || '')
    }
  }, [filteredEmployees, employee])

  const buildPayload = (): ShiftFormPayload => ({
    date, position, employee, shiftCategory, timeStart, timeEnd, aiToggle,
    shiftType: initialShift?.shiftType || shiftCategory,
    tasks: tasks.map(t => ({ ...t, finalTask: t.task === '__custom__' ? t.customTask : t.task })),
  })

  const updateTask = (id: string, patch: Partial<TaskRow>) =>
    setTasks(prev => prev.map(row => row.id === id ? { ...row, ...patch } : row))

  const addTaskRow = () =>
    setTasks(prev => [...prev, { id: `${Date.now()}`, start: timeStart, end: timeEnd, task: '', customTask: '' }])

  const removeTaskRow = (id: string) =>
    setTasks(prev => prev.filter(row => row.id !== id))

  const handleSave = () => { onSaveChange(buildPayload()); onClose() }
  const handleDelete = () => { onDeleteShift(); onClose() }
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
                <p className="text-xs font-semibold mt-0.5" style={{ color: '#E8187A' }}>{L.ai_sub}</p>
              </div>
            </div>
          </DialogHeader>

          <div className="min-w-0 px-6 py-4 overflow-y-auto">
            <div className="space-y-4 min-w-0">
              {/* Date */}
              <div>
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.date}</label>
                <input type="date" value={date} onChange={e => setDate(e.target.value)}
                  className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400" />
              </div>

              {/* Position + Employee */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 min-w-0">
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.position}</label>
                  <Select value={position} onValueChange={setPosition}>
                    <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {POSITION_OPTIONS.map(item => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.employee}</label>
                  <Select value={employee} onValueChange={setEmployee}>
                    <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {filteredEmployees.length === 0
                        ? <SelectItem value="no-staff" disabled>{L.no_staff}</SelectItem>
                        : filteredEmployees.map(item => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)
                      }
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Time + Shift Type */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 min-w-0">
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.time_range}</label>
                  <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 mt-1.5">
                    <input type="time" value={timeStart} onChange={e => setTimeStart(e.target.value)}
                      className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50" />
                    <span className="text-xs text-gray-400 shrink-0">{L.to}</span>
                    <input type="time" value={timeEnd} onChange={e => setTimeEnd(e.target.value)}
                      className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50" />
                  </div>
                </div>
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.shift_type}</label>
                  <Select value={shiftCategory} onValueChange={setShiftCategory}>
                    <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SHIFT_OPTIONS.map(item => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Tasks */}
              <div className="min-w-0">
                <div className="flex flex-col gap-2 mb-2 sm:flex-row sm:items-center sm:justify-between">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.task_schedule}</label>
                  <span className="text-[9px] font-bold px-2 py-0.5 rounded w-fit" style={{ background: '#fce8f3', color: '#E8187A' }}>
                    {L.adjustable}
                  </span>
                </div>
                <div className="space-y-2 min-w-0">
                  {tasks.map((row, index) => (
                    <div key={row.id} className="border border-gray-200 rounded-xl p-3 bg-gray-50 min-w-0">
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_1fr_auto] sm:items-center min-w-0">
                        <input type="time" value={row.start} onChange={e => updateTask(row.id, { start: e.target.value })}
                          className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white" />
                        <span className="text-xs text-gray-400 shrink-0">{L.to}</span>
                        <input type="time" value={row.end} onChange={e => updateTask(row.id, { end: e.target.value })}
                          className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white" />
                        <button type="button" onClick={() => removeTaskRow(row.id)}
                          className="text-xs font-semibold text-red-500" disabled={tasks.length === 1}>
                          {L.delete_task}
                        </button>
                      </div>
                      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 min-w-0">
                        <Select value={row.task} onValueChange={value => updateTask(row.id, { task: value })}>
                          <SelectTrigger className="rounded-xl bg-white border-gray-200 w-full min-w-0">
                            <SelectValue placeholder={L.task_ph} />
                          </SelectTrigger>
                          <SelectContent>
                            {TASK_OPTIONS.map(item => <SelectItem key={item} value={item}>{item}</SelectItem>)}
                            <SelectItem value="__custom__">{L.custom_opt}</SelectItem>
                          </SelectContent>
                        </Select>
                        <input type="text" value={row.customTask}
                          onChange={e => updateTask(row.id, { customTask: e.target.value })}
                          placeholder={row.task === '__custom__' ? L.custom_ph : L.extra_ph}
                          className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white min-w-0" />
                      </div>
                      <div className="mt-2 text-[11px] text-gray-500 break-words">
                        {L.item} {index + 1}：{row.start} - {row.end} ／
                        {row.task === '__custom__' ? row.customTask || '—' : row.task || '—'}
                      </div>
                    </div>
                  ))}
                </div>
                <button type="button" onClick={addTaskRow}
                  className="mt-3 text-xs font-semibold" style={{ color: '#E8187A' }}>
                  {L.add_task}
                </button>
              </div>

              {/* AI Toggle */}
              <div className="flex min-w-0 items-center gap-3 p-3 rounded-xl" style={{ background: '#fce8f3' }}>
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0" style={{ background: '#E8187A' }}>🧠</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold">{L.ai_title}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5">{L.ai_desc}</div>
                </div>
                <button type="button" onClick={() => setAiToggle(!aiToggle)}
                  className="w-10 h-6 rounded-full transition-all relative shrink-0"
                  style={{ background: aiToggle ? '#E8187A' : '#d1d5db' }}>
                  <span className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all"
                    style={{ left: aiToggle ? '20px' : '4px' }} />
                </button>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-100 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="w-full sm:w-auto">
              {isEditMode ? (
                <Button variant="outline" onClick={handleDelete}
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
              <Button variant="outline" onClick={handleSave} className="w-full sm:w-auto rounded-xl text-xs">
                {L.save_ai}
              </Button>
              <Button onClick={handleSave}
                className="w-full sm:w-auto rounded-xl text-xs text-white"
                style={{ background: '#E8187A' }}>
                {L.save}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}