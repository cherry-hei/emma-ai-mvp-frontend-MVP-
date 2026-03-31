'use client'

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

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
  tasks: {
    id: string
    start: string
    end: string
    task: string
    customTask: string
    finalTask: string
  }[]
}

type InitialTask = {
  id?: string
  start?: string
  end?: string
  task?: string
  customTask?: string
}

type InitialData = {
  date?: string
  position?: string
  employee?: string
  shiftCategory?: string
  timeStart?: string
  timeEnd?: string
  tasks?: InitialTask[]
}

interface CreateShiftModalProps {
  open: boolean
  onClose: () => void
  onSave?: (payload: ShiftFormPayload) => void
  onSaveAndAI?: (payload: ShiftFormPayload) => void
  onDelete?: () => void
  mode?: 'create' | 'edit'
  initialData?: InitialData
}

const TASK_OPTIONS = [
  '餵藥檢查',
  '傷口護理',
  '病人觀察',
  '口腔餵食',
  '更換尿片',
  '復康訓練',
  '感染控制',
  '文件紀錄',
  '巡房',
  '量度生命表徵',
]

const POSITION_OPTIONS = [
  { value: 'rn-senior', label: '註冊護士（資深）' },
  { value: 'rn', label: '註冊護士（RN）' },
  { value: 'en', label: '登記護士（EN）' },
  { value: 'hw', label: '健康服務員（HW）' },
  { value: 'pcw', label: '個人護理員（PCW）' },
  { value: 'pta', label: '物理治療助理（PTA）' },
  { value: 'cw', label: '護理員（CW）' },
]

const EMPLOYEE_OPTIONS = [
  { value: 'yu', label: '余逸詩（RN）', role: 'rn' },
  { value: 'chan', label: 'Chan S.M.（RN）', role: 'rn' },
  { value: 'leung', label: '梁嘉琪（EN）', role: 'en' },
  { value: 'wong', label: '王雅琛（HW）', role: 'hw' },
  { value: 'jing', label: '黃靜賢（PCW）', role: 'pcw' },
  { value: 'sze-kai', label: '黃司琦（PTA）', role: 'pta' },
  { value: 'ho', label: '何啟晴（CW）', role: 'cw' },
]

const SHIFT_OPTIONS = [
  { value: 'morning', label: '早更（Regular）' },
  { value: 'afternoon', label: '午更（Regular）' },
  { value: 'night', label: '夜更（Regular）' },
  { value: 'emergency', label: '緊急補位' },
]

function createDefaultTasks(): TaskRow[] {
  return [
    {
      id: '1',
      start: '07:00',
      end: '09:00',
      task: '餵藥檢查',
      customTask: '',
    },
    {
      id: '2',
      start: '09:00',
      end: '11:00',
      task: '文件紀錄',
      customTask: '',
    },
  ]
}

export function CreateShiftModal({
  open,
  onClose,
  onSave,
  onSaveAndAI,
  onDelete,
  mode = 'create',
  initialData,
}: CreateShiftModalProps) {
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

    setAiToggle(true)
    setDate(initialData?.date || '2026-03-19')
    setPosition(initialData?.position || 'rn')
    setEmployee(initialData?.employee || 'yu')
    setShiftCategory(initialData?.shiftCategory || 'morning')
    setTimeStart(initialData?.timeStart || '07:00')
    setTimeEnd(initialData?.timeEnd || '15:00')

    if (initialData?.tasks && initialData.tasks.length > 0) {
      setTasks(
        initialData.tasks.map((t, index) => ({
          id: t.id || `${Date.now()}-${index}`,
          start: t.start || '07:00',
          end: t.end || '09:00',
          task: t.task || '',
          customTask: t.customTask || '',
        }))
      )
    } else {
      setTasks(createDefaultTasks())
    }
  }, [open, initialData])

  const filteredEmployees = useMemo(() => {
    const normalized = position === 'rn-senior' ? 'rn' : position
    return EMPLOYEE_OPTIONS.filter((item) => item.role === normalized)
  }, [position])

  useEffect(() => {
    if (!filteredEmployees.find((item) => item.value === employee)) {
      setEmployee(filteredEmployees[0]?.value || '')
    }
  }, [filteredEmployees, employee])

  const title = useMemo(() => {
    return mode === 'edit' ? '編輯更期與工作安排' : '建立更期與工作安排'
  }, [mode])

  const buildPayload = (): ShiftFormPayload => {
    return {
      date,
      position,
      employee,
      shiftCategory,
      timeStart,
      timeEnd,
      aiToggle,
      tasks: tasks.map((t) => ({
        ...t,
        finalTask: t.task === '__custom__' ? t.customTask : t.task,
      })),
    }
  }

  const updateTask = (id: string, patch: Partial<TaskRow>) => {
    setTasks((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)))
  }

  const addTaskRow = () => {
    setTasks((prev) => [
      ...prev,
      {
        id: `${Date.now()}`,
        start: timeStart,
        end: timeEnd,
        task: '',
        customTask: '',
      },
    ])
  }

  const removeTaskRow = (id: string) => {
    setTasks((prev) => prev.filter((row) => row.id !== id))
  }

  const handleSave = () => {
    onSave?.(buildPayload())
    onClose()
  }

  const handleSaveAndAI = () => {
    onSaveAndAI?.(buildPayload())
    onClose()
  }

  const handleDelete = () => {
    onDelete?.()
    onClose()
  }

  const isEditMode = mode === 'edit'

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-[min(96vw,860px)] max-w-none rounded-2xl max-h-[90vh] overflow-hidden p-0">
        <div className="flex min-w-0 flex-col max-h-[90vh]">
          <DialogHeader className="px-6 pt-6 pb-3 border-b border-gray-100">
            <div className="flex min-w-0 items-center gap-3">
              <div
                className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0"
                style={{ background: '#fce8f3' }}
              >
                ✨
              </div>
              <div className="min-w-0">
                <DialogTitle className="text-lg font-bold truncate">{title}</DialogTitle>
                <p className="text-xs font-semibold mt-0.5 truncate" style={{ color: '#E8187A' }}>
                  AI 智能排更調整
                </p>
              </div>
            </div>
          </DialogHeader>

          <div className="min-w-0 px-6 py-4 overflow-y-auto">
            <div className="space-y-4 min-w-0">
              <div>
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">日期</label>
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400"
                />
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 min-w-0">
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">選擇職位</label>
                  <Select value={position} onValueChange={setPosition}>
                    <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full min-w-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {POSITION_OPTIONS.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">指派員工</label>
                  <Select value={employee} onValueChange={setEmployee}>
                    <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full min-w-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {filteredEmployees.length === 0 ? (
                        <SelectItem value="no-staff" disabled>
                          此職位暫無員工
                        </SelectItem>
                      ) : (
                        filteredEmployees.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 min-w-0">
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">時間範圍</label>
                  <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 mt-1.5 min-w-0">
                    <input
                      type="time"
                      value={timeStart}
                      onChange={(e) => setTimeStart(e.target.value)}
                      className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none"
                    />
                    <span className="text-xs text-gray-400 shrink-0">至</span>
                    <input
                      type="time"
                      value={timeEnd}
                      onChange={(e) => setTimeEnd(e.target.value)}
                      className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">更別類型</label>
                  <Select value={shiftCategory} onValueChange={setShiftCategory}>
                    <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full min-w-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SHIFT_OPTIONS.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="min-w-0">
                <div className="flex flex-col gap-2 mb-2 sm:flex-row sm:items-center sm:justify-between">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">工作時間表</label>
                  <span
                    className="text-[9px] font-bold px-2 py-0.5 rounded w-fit"
                    style={{ background: '#fce8f3', color: '#E8187A' }}
                  >
                    可調整時間及工作內容
                  </span>
                </div>

                <div className="space-y-2 min-w-0">
                  {tasks.map((row, index) => (
                    <div
                      key={row.id}
                      className="border border-gray-200 rounded-xl p-3 bg-gray-50 min-w-0"
                    >
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_1fr_auto] sm:items-center min-w-0">
                        <input
                          type="time"
                          value={row.start}
                          onChange={(e) => updateTask(row.id, { start: e.target.value })}
                          className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white"
                        />
                        <span className="text-xs text-gray-400 shrink-0">至</span>
                        <input
                          type="time"
                          value={row.end}
                          onChange={(e) => updateTask(row.id, { end: e.target.value })}
                          className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white"
                        />
                        <button
                          type="button"
                          onClick={() => removeTaskRow(row.id)}
                          className="text-xs font-semibold text-red-500 text-left sm:text-center"
                          disabled={tasks.length === 1}
                        >
                          刪除
                        </button>
                      </div>

                      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 min-w-0">
                        <div className="min-w-0">
                          <Select
                            value={row.task}
                            onValueChange={(value) => updateTask(row.id, { task: value })}
                          >
                            <SelectTrigger className="rounded-xl bg-white border-gray-200 w-full min-w-0">
                              <SelectValue placeholder="選擇工作內容" />
                            </SelectTrigger>
                            <SelectContent>
                              {TASK_OPTIONS.map((item) => (
                                <SelectItem key={item} value={item}>
                                  {item}
                                </SelectItem>
                              ))}
                              <SelectItem value="__custom__">其他（自行輸入）</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>

                        <input
                          type="text"
                          value={row.customTask}
                          onChange={(e) => updateTask(row.id, { customTask: e.target.value })}
                          placeholder={row.task === '__custom__' ? '輸入自訂工作內容' : '可補充工作內容'}
                          className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-white min-w-0"
                        />
                      </div>

                      <div className="mt-2 text-[11px] text-gray-500 break-words">
                        項目 {index + 1}：{row.start} - {row.end} ／
                        {row.task === '__custom__'
                          ? row.customTask || '未填寫自訂內容'
                          : row.task || '未選擇工作內容'}
                      </div>
                    </div>
                  ))}
                </div>

                <button
                  type="button"
                  onClick={addTaskRow}
                  className="mt-3 text-xs font-semibold"
                  style={{ color: '#E8187A' }}
                >
                  + 新增工作項目
                </button>
              </div>

              <div className="flex min-w-0 items-center gap-3 p-3 rounded-xl" style={{ background: '#fce8f3' }}>
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0"
                  style={{ background: '#E8187A' }}
                >
                  🧠
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold break-words">Emma AI Task Optimisation</div>
                  <div className="text-[10px] text-gray-500 mt-0.5 break-words">
                    根據員工能力及更期內容提供 AI 重新編排建議
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setAiToggle(!aiToggle)}
                  className="w-10 h-6 rounded-full transition-all relative shrink-0"
                  style={{ background: aiToggle ? '#E8187A' : '#d1d5db' }}
                >
                  <span
                    className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all"
                    style={{ left: aiToggle ? '20px' : '4px' }}
                  />
                </button>
              </div>
            </div>
          </div>

          <div className="px-6 py-4 border-t border-gray-100 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="w-full sm:w-auto">
              {isEditMode && onDelete ? (
                <Button
                  variant="outline"
                  onClick={handleDelete}
                  className="w-full sm:w-auto rounded-xl text-xs text-red-500 border-red-200 hover:bg-red-50"
                >
                  Delete
                </Button>
              ) : (
                <Button variant="outline" onClick={onClose} className="w-full sm:w-auto rounded-xl text-xs">
                  Cancel
                </Button>
              )}
            </div>

            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
              <Button
                variant="outline"
                onClick={handleSaveAndAI}
                className="w-full sm:w-auto rounded-xl text-xs"
              >
                Save & AI Reschule Suggestion
              </Button>

              <Button
                onClick={handleSave}
                className="w-full sm:w-auto rounded-xl text-xs text-white"
                style={{ background: '#E8187A' }}
              >
                Save Changes
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

