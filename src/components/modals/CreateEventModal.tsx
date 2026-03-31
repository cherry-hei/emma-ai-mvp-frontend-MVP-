'use client'

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

type PositionNeedRow = {
  id: string
  position: string
  qty: string
}

type StaffOption = {
  value: string
  label: string
  role: string
}

type EventFormPayload = {
  eventType: string
  remark: string
  date: string
  startTime: string
  endTime: string
  position: string
  selectedStaff: string[]
  aiToggle: boolean
  positionNeedsEnabled: boolean
  positionNeeds: PositionNeedRow[]
}

interface CreateEventModalProps {
  open: boolean
  onClose: () => void
  onSave?: (payload: EventFormPayload) => void
  onSaveAndAI?: (payload: EventFormPayload) => void
}

const STAFF_OPTIONS: StaffOption[] = [
  { value: 'yu', label: '余逸詩（RN）', role: 'rn' },
  { value: 'chan', label: 'Chan S.M.（RN）', role: 'rn' },
  { value: 'leung', label: '梁嘉琪（EN）', role: 'en' },
  { value: 'wong', label: '王雅琛（HW）', role: 'hw' },
  { value: 'jing', label: '黃靜賢（PCW）', role: 'pcw' },
  { value: 'sze-kai', label: '黃司琦（PTA）', role: 'pta' },
  { value: 'ho', label: '何啟晴（CW）', role: 'cw' },
]

const POSITION_OPTIONS = [
  { value: 'all', label: '所有職位' },
  { value: 'rn', label: '註冊護士（RN）' },
  { value: 'en', label: '登記護士（EN）' },
  { value: 'hw', label: '健康服務員（HW）' },
  { value: 'pcw', label: '個人護理員（PCW）' },
  { value: 'pta', label: '物理治療助理（PTA）' },
  { value: 'cw', label: '護理員（CW）' },
]

const EVENT_TYPES = [
  { value: 'meeting', label: '會議', icon: '👥' },
  { value: 'training', label: '培訓', icon: '📘' },
  { value: 'lecture', label: '講座', icon: '🎤' },
  { value: 'visit', label: '探訪', icon: '🏠' },
  { value: 'haircut', label: '剪髮', icon: '✂️' },
  { value: 'other', label: '其他', icon: '📝' },
]

function createDefaultPositionNeeds(): PositionNeedRow[] {
  return [{ id: '1', position: 'rn', qty: '2' }]
}

export function CreateEventModal({
  open,
  onClose,
  onSave,
  onSaveAndAI,
}: CreateEventModalProps) {
  const [eventType, setEventType] = useState('meeting')
  const [remark, setRemark] = useState('')
  const [date, setDate] = useState('2026-03-19')
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('11:00')
  const [position, setPosition] = useState('all')
  const [staffKeyword, setStaffKeyword] = useState('')
  const [selectedStaff, setSelectedStaff] = useState<string[]>([])
  const [positionNeedsEnabled, setPositionNeedsEnabled] = useState(false)
  const [positionNeeds, setPositionNeeds] = useState<PositionNeedRow[]>(createDefaultPositionNeeds())
  const [aiToggle, setAiToggle] = useState(true)

  useEffect(() => {
    if (!open) return
    setEventType('meeting')
    setRemark('')
    setDate('2026-03-19')
    setStartTime('09:00')
    setEndTime('11:00')
    setPosition('all')
    setStaffKeyword('')
    setSelectedStaff([])
    setPositionNeedsEnabled(false)
    setPositionNeeds(createDefaultPositionNeeds())
    setAiToggle(true)
  }, [open])

  const filteredStaff = useMemo(() => {
    return STAFF_OPTIONS.filter((item) => {
      const matchPosition = position === 'all' ? true : item.role === position
      const matchKeyword = item.label.toLowerCase().includes(staffKeyword.toLowerCase())
      return matchPosition && matchKeyword
    })
  }, [position, staffKeyword])

  const toggleStaff = (value: string) => {
    setSelectedStaff((prev) =>
      prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]
    )
  }

  const selectAllStaff = () => {
    setSelectedStaff(filteredStaff.map((item) => item.value))
  }

  const clearAllStaff = () => {
    setSelectedStaff([])
  }

  const addPositionNeed = () => {
    if (positionNeeds.length >= 8) return
    setPositionNeeds((prev) => [...prev, { id: `${Date.now()}`, position: '', qty: '' }])
  }

  const updatePositionNeed = (id: string, patch: Partial<PositionNeedRow>) => {
    setPositionNeeds((prev) =>
      prev.map((row) => (row.id === id ? { ...row, ...patch } : row))
    )
  }

  const removePositionNeed = (id: string) => {
    setPositionNeeds((prev) => prev.filter((row) => row.id !== id))
  }

  const buildPayload = (): EventFormPayload => {
    return {
      eventType,
      remark,
      date,
      startTime,
      endTime,
      position,
      selectedStaff,
      aiToggle,
      positionNeedsEnabled,
      positionNeeds,
    }
  }

  const handleSave = () => {
    onSave?.(buildPayload())
    onClose()
  }

  const handleSaveAndAI = () => {
    onSaveAndAI?.(buildPayload())
    onClose()
  }

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
                📌
              </div>
              <div className="min-w-0">
                <DialogTitle className="text-lg font-bold truncate">建立特殊事件</DialogTitle>
                <p className="text-xs font-semibold mt-0.5 truncate" style={{ color: '#E8187A' }}>
                  AI 智能排更調整
                </p>
              </div>
            </div>
          </DialogHeader>

          <div className="min-w-0 px-6 py-4 overflow-y-auto">
            <div className="space-y-4 min-w-0">
              <div className="min-w-0">
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider block mb-2">
                  事件類型
                </label>
                <div className="flex flex-wrap gap-2 min-w-0">
                  {EVENT_TYPES.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      onClick={() => setEventType(item.value)}
                      className="px-3 py-2 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 max-w-full"
                      style={{
                        background: eventType === item.value ? '#E8187A' : '#fff',
                        color: eventType === item.value ? '#fff' : '#6b7280',
                        borderColor: eventType === item.value ? '#E8187A' : '#e5e7eb',
                      }}
                    >
                      <span className="shrink-0">{item.icon}</span>
                      <span className="truncate">{item.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">備註</label>
                <textarea
                  value={remark}
                  onChange={(e) => setRemark(e.target.value)}
                  placeholder="請輸入備註"
                  className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400 min-h-[90px]"
                />
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 min-w-0">
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">日期</label>
                  <input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none"
                  />
                </div>

                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">時間範圍</label>
                  <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 mt-1.5 min-w-0">
                    <input
                      type="time"
                      value={startTime}
                      onChange={(e) => setStartTime(e.target.value)}
                      className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50"
                    />
                    <span className="text-xs text-gray-400 shrink-0">至</span>
                    <input
                      type="time"
                      value={endTime}
                      onChange={(e) => setEndTime(e.target.value)}
                      className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50"
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">選擇職位</label>
                <Select
                  value={position}
                  onValueChange={(value) => {
                    setPosition(value)
                    setSelectedStaff([])
                    setStaffKeyword('')
                  }}
                >
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
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider mb-2 block">
                  員工 Staff
                </label>

                <input
                  type="text"
                  value={staffKeyword}
                  onChange={(e) => setStaffKeyword(e.target.value)}
                  placeholder="輸入員工姓名搜尋"
                  className="w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 mb-2"
                />

                <div className="flex flex-col gap-2 mb-2 sm:flex-row sm:items-center sm:justify-between">
                  <span className="text-[10px] text-gray-500 break-words">
                    只顯示所選職位員工，可多選 / 全選
                  </span>
                  <div className="flex items-center gap-3 shrink-0">
                    <button
                      type="button"
                      onClick={selectAllStaff}
                      className="text-[10px] font-semibold"
                      style={{ color: '#E8187A' }}
                    >
                      全選員工
                    </button>
                    <button
                      type="button"
                      onClick={clearAllStaff}
                      className="text-[10px] font-semibold text-gray-500"
                    >
                      清空
                    </button>
                  </div>
                </div>

                <div className="min-w-0 flex gap-2 flex-wrap p-2.5 border border-gray-200 rounded-xl bg-gray-50 items-center min-h-[52px]">
                  {filteredStaff.length === 0 ? (
                    <div className="text-xs text-gray-400">此職位暫時沒有對應員工</div>
                  ) : (
                    filteredStaff.map((staff) => {
                      const active = selectedStaff.includes(staff.value)
                      return (
                        <button
                          key={staff.value}
                          type="button"
                          onClick={() => toggleStaff(staff.value)}
                          className="max-w-full px-2.5 py-1 text-xs rounded-full border"
                          style={{
                            background: active ? '#E8187A' : '#fff',
                            color: active ? '#fff' : '#6b7280',
                            borderColor: active ? '#E8187A' : '#e5e7eb',
                          }}
                        >
                          <span className="block truncate">{staff.label}</span>
                        </button>
                      )
                    })
                  )}
                </div>
              </div>

              <div className="flex min-w-0 items-center gap-3 p-3 rounded-xl" style={{ background: '#fce8f3' }}>
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0"
                  style={{ background: '#E8187A' }}
                >
                  🧩
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold break-words">輸入不同職系員工所需數量</div>
                  <div className="text-[10px] text-gray-500 mt-0.5 break-words">快速設定各職位所需人手</div>
                </div>
                <button
                  type="button"
                  onClick={() => setPositionNeedsEnabled(!positionNeedsEnabled)}
                  className="w-10 h-6 rounded-full transition-all relative shrink-0"
                  style={{ background: positionNeedsEnabled ? '#E8187A' : '#d1d5db' }}
                >
                  <span
                    className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all"
                    style={{ left: positionNeedsEnabled ? '20px' : '4px' }}
                  />
                </button>
              </div>

              {positionNeedsEnabled && (
                <div className="space-y-2 min-w-0">
                  {positionNeeds.map((row) => (
                    <div key={row.id} className="grid grid-cols-1 sm:grid-cols-[1fr_110px_auto] gap-2 items-center min-w-0">
                      <Select
                        value={row.position}
                        onValueChange={(value) => updatePositionNeed(row.id, { position: value })}
                      >
                        <SelectTrigger className="rounded-xl bg-gray-50 border-gray-200 w-full min-w-0">
                          <SelectValue placeholder="選擇職位" />
                        </SelectTrigger>
                        <SelectContent>
                          {POSITION_OPTIONS.filter((item) => item.value !== 'all').map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>

                      <input
                        type="number"
                        value={row.qty}
                        onChange={(e) => updatePositionNeed(row.id, { qty: e.target.value })}
                        placeholder="所需數量"
                        className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50 min-w-0"
                      />

                      <button
                        type="button"
                        onClick={() => removePositionNeed(row.id)}
                        className="text-xs text-red-500 font-semibold px-2 py-2 sm:py-0 text-left sm:text-center"
                      >
                        移除
                      </button>
                    </div>
                  ))}

                  {positionNeeds.length < 8 && (
                    <button
                      type="button"
                      onClick={addPositionNeed}
                      className="text-xs font-semibold"
                      style={{ color: '#E8187A' }}
                    >
                      + 新增職位需求
                    </button>
                  )}
                </div>
              )}

              <div className="flex min-w-0 items-center gap-3 p-3 rounded-xl" style={{ background: '#fce8f3' }}>
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0"
                  style={{ background: '#E8187A' }}
                >
                  🧠
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold break-words">Emma AI Task Optimisation</div>
                  <div className="text-[10px] text-gray-500 mt-0.5 break-words">根據活動規模自動預測排更缺口</div>
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
            <Button variant="outline" onClick={onClose} className="w-full sm:w-auto rounded-xl text-xs">
              Cancel
            </Button>

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
                className="w-full sm:w-auto rounded-xl text-xs text-white font-semibold"
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

