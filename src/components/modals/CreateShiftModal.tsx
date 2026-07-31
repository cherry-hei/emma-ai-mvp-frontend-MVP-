"use client"

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
  initialShift: { staffId: number; dayIndex: number; shiftType: string; tasks?: string[]; mealCode?: string; note?: string } | null
  onSaveChange: (payload: { shiftType: string }) => void
  onDeleteShift: () => void
}

/* ---------- NAAC大興宿舍 Position & Staff Options ---------- */

const TASK_OPTIONS_ZH = ['派藥','協助給藥','約束紀錄','清潔飯堂','清潔宿舍','清洗廁所','清洗床單搽藥','肌能運動','陪診','到訪服務','外出活動','廚房工作','文件紀錄','其他']
const TASK_OPTIONS_EN = ['Medication','Assist Medication','Restraint Record','Clean Canteen','Clean Hostel','Clean Washrooms','Laundry & Ointment','Exercise Training','Escort Clinic','Visiting Service','Outing Activity','Kitchen Work','Documentation','Other']

const POSITION_OPTIONS_ZH = [
  { value: 'hm',   label: '主任' },
  { value: 'sw',   label: '社工' },
  { value: 'en',   label: '護士' },
  { value: 'hw',   label: '保健員' },
  { value: 'aw',   label: '家舍導師' },
  { value: 'aaw',  label: '助理活動工作員' },
  { value: 'pt',   label: '物理治療師' },
  { value: 'clerk',label: '文員' },
  { value: 'cw',   label: '助理員' },
  { value: 'cook', label: '廚師' },
  { value: 'ka',   label: '廚房助理' },
  { value: 'wm',   label: '工友' },
  { value: 'relief', label: '替假' },
]

const POSITION_OPTIONS_EN = [
  { value: 'hm',   label: 'Home Manager' },
  { value: 'sw',   label: 'Social Worker' },
  { value: 'en',   label: 'Enrolled Nurse' },
  { value: 'hw',   label: 'Health Worker' },
  { value: 'aw',   label: 'Activity Worker (HP)' },
  { value: 'aaw',  label: 'Asst. Activity Worker' },
  { value: 'pt',   label: 'Physiotherapist' },
  { value: 'clerk',label: 'Clerk' },
  { value: 'cw',   label: 'Care Worker (WA)' },
  { value: 'cook', label: 'Cook' },
  { value: 'ka',   label: 'Kitchen Assistant' },
  { value: 'wm',   label: 'Workman' },
  { value: 'relief', label: 'Relief Staff' },
]

const EMPLOYEE_OPTIONS = [
  { value: 'hm-main',  label: '主任（馬）',       role: 'hm' },
  { value: 'sw1',      label: '社工 1 副主任（李）', role: 'sw' },
  { value: 'sw2',      label: '社工 2（范）',      role: 'sw' },
  { value: 'sw3',      label: '社工 3（鄧）',      role: 'sw' },
  { value: 'en1',      label: '護士1（芝）',       role: 'en' },
  { value: 'en2',      label: '護士2（余）',       role: 'en' },
  { value: 'en3',      label: '護士3',            role: 'en' },
  { value: 'hw1',      label: '保健員 1（芹）',    role: 'hw' },
  { value: 'hw2',      label: '保健員 2（誠）',    role: 'hw' },
  { value: 'aw1',      label: '家舍導師 1（媚）',  role: 'aw' },
  { value: 'aw2',      label: '家舍導師 2（姜）',  role: 'aw' },
  { value: 'aw3',      label: '家舍導師 3（潘）',  role: 'aw' },
  { value: 'aw4',      label: '家舍導師 4（黎）',  role: 'aw' },
  { value: 'aw5',      label: '家舍導師 5（姬）',  role: 'aw' },
  { value: 'aw6',      label: '家舍導師 6（卉）',  role: 'aw' },
  { value: 'aaw1',     label: '助理活動工作員（邱）', role: 'aaw' },
  { value: 'pt1',      label: '物理治療師（賢）',  role: 'pt' },
  { value: 'clerk1',   label: '文員（鄧）',        role: 'clerk' },
  { value: 'cw1',      label: '助理員 1（蔡）',    role: 'cw' },
  { value: 'cw2',      label: '助理員 2（梅）',    role: 'cw' },
  { value: 'cw3',      label: '助理員 3（裕）',    role: 'cw' },
  { value: 'cw4',      label: '助理員 4（花）',    role: 'cw' },
  { value: 'cw5',      label: '助理員 5（儀）',    role: 'cw' },
  { value: 'cw6',      label: '助理員 6（周）',    role: 'cw' },
  { value: 'cw7',      label: '助理員 7（彩）',    role: 'cw' },
  { value: 'cw8',      label: '助理員 8（慧）',    role: 'cw' },
  { value: 'cw9',      label: '助理員 9（高）',    role: 'cw' },
  { value: 'cw10',     label: '助理員 10（紅）',   role: 'cw' },
  { value: 'cw11',     label: '助理員 11',         role: 'cw' },
  { value: 'cw12',     label: '助理員 12（郭）',   role: 'cw' },
  { value: 'cw13',     label: '助理員 13（雄）',   role: 'cw' },
  { value: 'cw14',     label: '助理員 14',         role: 'cw' },
  { value: 'cook1',    label: '廚師 1（和）',      role: 'cook' },
  { value: 'cook2',    label: '廚師 2（殷）',      role: 'cook' },
  { value: 'ka1',      label: '廚房助理（董）',    role: 'ka' },
  { value: 'wm1',      label: '工友 1（孫）',      role: 'wm' },
  { value: 'wm2',      label: '工友 2（津）',      role: 'wm' },
  { value: 'relief1',  label: '替假 1',            role: 'relief' },
  { value: 'relief2',  label: '替假 2',            role: 'relief' },
  { value: 'relief3',  label: '替假 3',            role: 'relief' },
  { value: 'relief4',  label: '替假 4',            role: 'relief' },
]

/* ---------- Shift Type Options (from NAAC shift codes) ---------- */

const SHIFT_OPTIONS_ZH = [
  { value: 'A',   label: 'A更（早更 8小時）' },
  { value: 'B',   label: 'B更（早更 9小時）' },
  { value: 'G',   label: 'G更（早更 7小時）' },
  { value: 'P',   label: 'P更（下午更 10pm下班）' },
  { value: 'N',   label: 'N更（通宵更 9小時）' },
  { value: 'K',   label: 'K更（通宵更 10小時）' },
  { value: 'AN',  label: 'A/N更（早+通宵 17小時）' },
  { value: 'AL',  label: 'AL（年假）' },
  { value: 'SL',  label: 'SL（病假）' },
  { value: 'PH',  label: 'PH（公眾假期）' },
  { value: 'CL',  label: 'CL（補假）' },
  { value: 'OFF', label: 'O（休班日）' },
]

const SHIFT_OPTIONS_EN = [
  { value: 'A',   label: 'A Shift (Day 8h)' },
  { value: 'B',   label: 'B Shift (Day 9h)' },
  { value: 'G',   label: 'G Shift (Day 7h)' },
  { value: 'P',   label: 'P Shift (Afternoon till 10pm)' },
  { value: 'N',   label: 'N Shift (Night 9h)' },
  { value: 'K',   label: 'K Shift (Night 10h)' },
  { value: 'AN',  label: 'A/N Shift (Day+Night 17h)' },
  { value: 'AL',  label: 'AL (Annual Leave)' },
  { value: 'SL',  label: 'SL (Sick Leave)' },
  { value: 'PH',  label: 'PH (Public Holiday)' },
  { value: 'CL',  label: 'CL (Compensatory Leave)' },
  { value: 'OFF', label: 'O (Day Off)' },
]

const SHIFT_TYPE_MAP: Record<string, string> = {
  A: 'A', B: 'B', E: 'A', G: 'A', P: 'P', N: 'N', K: 'N',
  AN: 'AN', AL: 'AL', SL: 'SL', CL: 'CL', OFF: 'OFF', SLEEP: 'OFF',
  O: 'OFF', PH: 'PH', NO: 'OFF', BDL: 'AL', FFL: 'AL',
}

/** Determine if a shiftCode represents an off/leave day */
function isOffDay(code: string | undefined): boolean {
  if (!code) return true
  const c = code.toUpperCase()
  if (c === 'O' || c === 'O,' || c === 'PH' || c === 'NO') return true
  if (c.startsWith('AL') || c.startsWith('SL') || c.startsWith('CL') || c.startsWith('BDL') || c.startsWith('FFL')) return true
  return false
}

/* ---------- Shift time defaults ---------- */
const SHIFT_TIME_DEFAULTS: Record<string, { start: string; end: string }> = {
  A:   { start: '07:00', end: '15:00' },
  B:   { start: '07:00', end: '16:00' },
  G:   { start: '07:00', end: '14:00' },
  P:   { start: '14:00', end: '22:00' },
  N:   { start: '22:00', end: '07:00' },
  K:   { start: '22:00', end: '08:00' },
  AN:  { start: '07:00', end: '07:00' },
  AL:  { start: '00:00', end: '00:00' },
  SL:  { start: '00:00', end: '00:00' },
  PH:  { start: '00:00', end: '00:00' },
  CL:  { start: '00:00', end: '00:00' },
  OFF: { start: '00:00', end: '00:00' },
}

function createDefaultTasks(): TaskRow[] {
  return [
    { id: '1', start: '07:00', end: '09:00', task: '派藥', customTask: '' },
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
  const [date, setDate] = useState('2026-06-08')
  const [position, setPosition] = useState('cw')
  const [employee, setEmployee] = useState('cw1')
  const [shiftCategory, setShiftCategory] = useState('A')
  const [timeStart, setTimeStart] = useState('07:00')
  const [timeEnd, setTimeEnd] = useState('15:00')
  const [tasks, setTasks] = useState<TaskRow[]>(createDefaultTasks())
  const [note, setNote] = useState('')
  const [mealCode, setMealCode] = useState('')

  useEffect(() => {
    if (!open) return
    if (initialShift) {
      // Check if it's an off day using the raw shiftType from the roster
      const rawCode = initialShift.shiftType
      if (isOffDay(rawCode)) {
        // Map to the appropriate off category
        if (rawCode === 'PH') setShiftCategory('PH')
        else if (rawCode.startsWith('AL')) setShiftCategory('AL')
        else if (rawCode.startsWith('SL')) setShiftCategory('SL')
        else if (rawCode.startsWith('CL') || rawCode === 'CL-8') setShiftCategory('CL')
        else if (rawCode.startsWith('BDL') || rawCode.startsWith('FFL')) setShiftCategory('AL')
        else setShiftCategory('OFF')
      } else {
        const mapped = SHIFT_TYPE_MAP[initialShift.shiftType] || 'A'
        setShiftCategory(mapped)
      }
      const cat = isOffDay(rawCode) ? 'OFF' : (SHIFT_TYPE_MAP[rawCode] || 'A')
      const times = SHIFT_TIME_DEFAULTS[cat] || SHIFT_TIME_DEFAULTS.A
      setTimeStart(times.start)
      setTimeEnd(times.end)
      setNote(initialShift.note || '')
      setMealCode(initialShift.mealCode || '')
    } else {
      setShiftCategory('A')
      setTimeStart('07:00')
      setTimeEnd('15:00')
      setTasks(createDefaultTasks())
      setNote('')
      setMealCode('')
    }
  }, [open, initialShift])

  // Update time when shift category changes
  useEffect(() => {
    const times = SHIFT_TIME_DEFAULTS[shiftCategory]
    if (times) {
      setTimeStart(times.start)
      setTimeEnd(times.end)
    }
  }, [shiftCategory])

  const filteredEmployees = useMemo(() => {
    return EMPLOYEE_OPTIONS.filter(item => item.role === position)
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

              {/* Tasks - hidden for OFF/PH/AL/CL/SL days */}
              {!['OFF', 'AL', 'SL', 'PH', 'CL', 'O', 'NO'].includes(shiftCategory) && !isOffDay(initialShift?.shiftType) && (
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
              )}

              {/* Meal & Rest Time Blocks - only for working days */}
              {mealCode && (
                <div className="rounded-xl border border-orange-200 bg-orange-50 p-3">
                  <div className="text-[9px] font-bold text-orange-700 uppercase tracking-wider mb-1">
                    {isZH ? '🍽 用膳時間（已鎖定）' : '🍽 Meal Time (Blocked)'}
                  </div>
                  <div className="text-xs text-orange-800 font-semibold">
                    {mealCode.startsWith('>') ? `${mealCode.slice(1)}pm 後用膳` : mealCode.startsWith('<') ? `${mealCode.slice(1)}pm 前用膳` : mealCode}
                  </div>
                  <div className="text-[10px] text-orange-600 mt-1">
                    {isZH ? '此時段不可安排其他工作' : 'Cannot assign tasks during this period'}
                  </div>
                </div>
              )}

              {/* Note (for OFF/PH days) */}
              <div>
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">
                  {isZH ? '備註 / 假期原因' : 'Note / Holiday Reason'}
                </label>
                <input
                  type="text"
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder={isZH ? '例如：補1/5、法定假期' : 'e.g. Compensatory for 1/5'}
                  className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400"
                />
              </div>

              {/* AI Toggle - hidden for OFF/PH/AL/CL/SL days */}
              {!['OFF', 'AL', 'SL', 'PH', 'CL', 'O', 'NO'].includes(shiftCategory) && !isOffDay(initialShift?.shiftType) && (
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
              )}
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
