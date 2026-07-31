'use client'

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useLang } from '@/components/layout/LanguageContext'

type PositionNeedRow = { id: string; position: string; qty: string }
type StaffOption = { value: string; label: string; role: string }
type EventFormPayload = {
  eventType: string; remark: string; date: string; startTime: string; endTime: string
  position: string; selectedStaff: string[]; aiToggle: boolean
  positionNeedsEnabled: boolean; positionNeeds: PositionNeedRow[]
}

interface CreateEventModalProps {
  open: boolean
  onClose: () => void
  onSave?: (payload: EventFormPayload) => void
  onSaveAndAI?: (payload: EventFormPayload) => void
}

const STAFF_OPTIONS: StaffOption[] = [
  { value: 'yu',      label: '余逸詩（RN）',   role: 'rn' },
  { value: 'chan',    label: 'Chan S.M.（RN）', role: 'rn' },
  { value: 'leung',  label: '梁嘉琪（EN）',     role: 'en' },
  { value: 'wong',   label: '王雅琛（HW）',     role: 'hw' },
  { value: 'jing',   label: '黃靜賢（PCW）',    role: 'pcw' },
  { value: 'sze-kai',label: '黃司琦（PTA）',    role: 'pta' },
  { value: 'ho',     label: '何啟晴（CW）',     role: 'cw' },
]

const POSITION_OPTIONS_ZH = [
  { value: 'all', label: '所有職位' },
  { value: 'rn',  label: '註冊護士（RN）' },
  { value: 'en',  label: '登記護士（EN）' },
  { value: 'hw',  label: '健康服務員（HW）' },
  { value: 'pcw', label: '個人護理員（PCW）' },
  { value: 'pta', label: '物理治療助理（PTA）' },
  { value: 'cw',  label: '護理員（CW）' },
]

const POSITION_OPTIONS_EN = [
  { value: 'all', label: 'All Positions' },
  { value: 'rn',  label: 'Registered Nurse (RN)' },
  { value: 'en',  label: 'Enrolled Nurse (EN)' },
  { value: 'hw',  label: 'Health Worker (HW)' },
  { value: 'pcw', label: 'Personal Care Worker (PCW)' },
  { value: 'pta', label: 'Physio Therapy Assistant (PTA)' },
  { value: 'cw',  label: 'Care Worker (CW)' },
]

const EVENT_TYPES_ZH = [
  { value: 'meeting',  label: '會議', icon: '👥' },
  { value: 'training', label: '培訓', icon: '📘' },
  { value: 'lecture',  label: '講座', icon: '🎤' },
  { value: 'visit',    label: '探訪', icon: '🏠' },
  { value: 'haircut',  label: '剪髮', icon: '✂️' },
  { value: 'other',    label: '其他', icon: '📝' },
]

const EVENT_TYPES_EN = [
  { value: 'meeting',  label: 'Meeting',  icon: '👥' },
  { value: 'training', label: 'Training', icon: '📘' },
  { value: 'lecture',  label: 'Seminar',  icon: '🎤' },
  { value: 'visit',    label: 'Visit',    icon: '🏠' },
  { value: 'haircut',  label: 'Haircut',  icon: '✂️' },
  { value: 'other',    label: 'Others',   icon: '📝' },
]

function createDefaultPositionNeeds(): PositionNeedRow[] {
  return [{ id: '1', position: 'rn', qty: '2' }]
}

export function CreateEventModal({ open, onClose, onSave, onSaveAndAI }: CreateEventModalProps) {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const L = {
    title:          isZH ? '建立特殊事件'                       : 'Create Special Event',
    subtitle:       isZH ? 'AI 智能排更調整'                    : 'AI Intelligent Scheduling',
    event_type:     isZH ? '事件類型'                           : 'Event Type',
    remark:         isZH ? '備註'                               : 'Remarks',
    remark_ph:      isZH ? '請輸入備註'                         : 'Enter remarks',
    date:           isZH ? '日期'                               : 'Date',
    time_range:     isZH ? '時間範圍'                           : 'Time Range',
    to:             isZH ? '至'                                 : 'to',
    position:       isZH ? '選擇職位'                           : 'Select Position',
    staff:          isZH ? '員工 Staff'                         : 'Staff',
    staff_ph:       isZH ? '輸入員工姓名搜尋'                   : 'Search staff name',
    staff_hint:     isZH ? '只顯示所選職位員工，可多選 / 全選'   : 'Filtered by position. Multi-select allowed.',
    select_all:     isZH ? '全選員工'                           : 'Select All',
    clear:          isZH ? '清空'                               : 'Clear',
    no_staff:       isZH ? '此職位暫時沒有對應員工'              : 'No staff for this position',
    pos_need_title: isZH ? '輸入不同職系員工所需數量'            : 'Set Required Staff by Position',
    pos_need_sub:   isZH ? '快速設定各職位所需人手'              : 'Quickly configure headcount per role',
    add_pos:        isZH ? '+ 新增職位需求'                     : '+ Add Position Requirement',
    pos_ph:         isZH ? '選擇職位'                           : 'Select Position',
    qty_ph:         isZH ? '所需數量'                           : 'Qty needed',
    remove:         isZH ? '移除'                               : 'Remove',
    ai_title:       'Emma AI Task Optimisation',
    ai_desc:        isZH ? '根據活動規模自動預測排更缺口'         : 'Auto-predict scheduling gaps based on event scale',
    cancel:         isZH ? '取消'                               : 'Cancel',
    save_ai:        'Save & AI Reschedule Suggestion',
    save:           isZH ? '儲存更改'                           : 'Save Changes',
  }

  const EVENT_TYPES     = isZH ? EVENT_TYPES_ZH     : EVENT_TYPES_EN
  const POSITION_OPTIONS = isZH ? POSITION_OPTIONS_ZH : POSITION_OPTIONS_EN

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
    setEventType('meeting'); setRemark(''); setDate('2026-03-19')
    setStartTime('09:00'); setEndTime('11:00'); setPosition('all')
    setStaffKeyword(''); setSelectedStaff([])
    setPositionNeedsEnabled(false); setPositionNeeds(createDefaultPositionNeeds()); setAiToggle(true)
  }, [open])

  const filteredStaff = useMemo(() => STAFF_OPTIONS.filter(item => {
    const matchPosition = position === 'all' ? true : item.role === position
    const matchKeyword = item.label.toLowerCase().includes(staffKeyword.toLowerCase())
    return matchPosition && matchKeyword
  }), [position, staffKeyword])

  const toggleStaff = (value: string) =>
    setSelectedStaff(prev => prev.includes(value) ? prev.filter(i => i !== value) : [...prev, value])

  const selectAllStaff = () => setSelectedStaff(filteredStaff.map(i => i.value))
  const clearAllStaff  = () => setSelectedStaff([])

  const addPositionNeed = () => {
    if (positionNeeds.length >= 8) return
    setPositionNeeds(prev => [...prev, { id: `${Date.now()}`, position: '', qty: '' }])
  }
  const updatePositionNeed = (id: string, patch: Partial<PositionNeedRow>) =>
    setPositionNeeds(prev => prev.map(row => row.id === id ? { ...row, ...patch } : row))
  const removePositionNeed = (id: string) =>
    setPositionNeeds(prev => prev.filter(row => row.id !== id))

  const buildPayload = (): EventFormPayload => ({
    eventType, remark, date, startTime, endTime, position,
    selectedStaff, aiToggle, positionNeedsEnabled, positionNeeds,
  })

  const handleSave     = () => { onSave?.(buildPayload());      onClose() }
  const handleSaveAndAI = () => { onSaveAndAI?.(buildPayload()); onClose() }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-[min(96vw,860px)] max-w-none rounded-2xl max-h-[90vh] overflow-hidden p-0">
        <div className="flex min-w-0 flex-col max-h-[90vh]">
          {/* Header */}
          <DialogHeader className="px-6 pt-6 pb-3 border-b border-gray-100">
            <div className="flex min-w-0 items-center gap-3">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0"
                style={{ background: '#fce8f3' }}>📌</div>
              <div className="min-w-0">
                <DialogTitle className="text-lg font-bold truncate">{L.title}</DialogTitle>
                <p className="text-xs font-semibold mt-0.5 truncate" style={{ color: '#E8187A' }}>{L.subtitle}</p>
              </div>
            </div>
          </DialogHeader>

          {/* Body */}
          <div className="min-w-0 px-6 py-4 overflow-y-auto">
            <div className="space-y-4 min-w-0">

              {/* Event Type */}
              <div className="min-w-0">
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider block mb-2">
                  {L.event_type}
                </label>
                <div className="flex flex-wrap gap-2 min-w-0">
                  {EVENT_TYPES.map(item => (
                    <button key={item.value} type="button" onClick={() => setEventType(item.value)}
                      className="px-3 py-2 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 max-w-full"
                      style={{
                        background: eventType === item.value ? '#E8187A' : '#fff',
                        color: eventType === item.value ? '#fff' : '#6b7280',
                        borderColor: eventType === item.value ? '#E8187A' : '#e5e7eb',
                      }}>
                      <span className="shrink-0">{item.icon}</span>
                      <span className="truncate">{item.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Remark */}
              <div>
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.remark}</label>
                <textarea value={remark} onChange={e => setRemark(e.target.value)}
                  placeholder={L.remark_ph}
                  className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400 min-h-[90px]" />
              </div>

              {/* Date + Time */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 min-w-0">
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.date}</label>
                  <input type="date" value={date} onChange={e => setDate(e.target.value)}
                    className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none" />
                </div>
                <div className="min-w-0">
                  <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.time_range}</label>
                  <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 mt-1.5 min-w-0">
                    <input type="time" value={startTime} onChange={e => setStartTime(e.target.value)}
                      className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50" />
                    <span className="text-xs text-gray-400 shrink-0">{L.to}</span>
                    <input type="time" value={endTime} onChange={e => setEndTime(e.target.value)}
                      className="min-w-0 w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50" />
                  </div>
                </div>
              </div>

              {/* Position */}
              <div>
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.position}</label>
                <Select value={position} onValueChange={value => { setPosition(value); setSelectedStaff([]); setStaffKeyword('') }}>
                  <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200 w-full min-w-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {POSITION_OPTIONS.map(item => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              {/* Staff */}
              <div className="min-w-0">
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider mb-2 block">{L.staff}</label>
                <input type="text" value={staffKeyword} onChange={e => setStaffKeyword(e.target.value)}
                  placeholder={L.staff_ph}
                  className="w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 mb-2" />
                <div className="flex flex-col gap-2 mb-2 sm:flex-row sm:items-center sm:justify-between">
                  <span className="text-[10px] text-gray-500 break-words">{L.staff_hint}</span>
                  <div className="flex items-center gap-3 shrink-0">
                    <button type="button" onClick={selectAllStaff}
                      className="text-[10px] font-semibold" style={{ color: '#E8187A' }}>{L.select_all}</button>
                    <button type="button" onClick={clearAllStaff}
                      className="text-[10px] font-semibold text-gray-500">{L.clear}</button>
                  </div>
                </div>
                <div className="min-w-0 flex gap-2 flex-wrap p-2.5 border border-gray-200 rounded-xl bg-gray-50 items-center min-h-[52px]">
                  {filteredStaff.length === 0 ? (
                    <div className="text-xs text-gray-400">{L.no_staff}</div>
                  ) : (
                    filteredStaff.map(staff => {
                      const active = selectedStaff.includes(staff.value)
                      return (
                        <button key={staff.value} type="button" onClick={() => toggleStaff(staff.value)}
                          className="max-w-full px-2.5 py-1 text-xs rounded-full border"
                          style={{
                            background: active ? '#E8187A' : '#fff',
                            color: active ? '#fff' : '#6b7280',
                            borderColor: active ? '#E8187A' : '#e5e7eb',
                          }}>
                          <span className="block truncate">{staff.label}</span>
                        </button>
                      )
                    })
                  )}
                </div>
              </div>

              {/* Position Needs Toggle */}
              <div className="flex min-w-0 items-center gap-3 p-3 rounded-xl" style={{ background: '#fce8f3' }}>
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0"
                  style={{ background: '#E8187A' }}>🧩</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold break-words">{L.pos_need_title}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5 break-words">{L.pos_need_sub}</div>
                </div>
                <button type="button" onClick={() => setPositionNeedsEnabled(!positionNeedsEnabled)}
                  className="w-10 h-6 rounded-full transition-all relative shrink-0"
                  style={{ background: positionNeedsEnabled ? '#E8187A' : '#d1d5db' }}>
                  <span className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all"
                    style={{ left: positionNeedsEnabled ? '20px' : '4px' }} />
                </button>
              </div>

              {/* Position Needs Rows */}
              {positionNeedsEnabled && (
                <div className="space-y-2 min-w-0">
                  {positionNeeds.map(row => (
                    <div key={row.id} className="grid grid-cols-1 sm:grid-cols-[1fr_110px_auto] gap-2 items-center min-w-0">
                      <Select value={row.position} onValueChange={value => updatePositionNeed(row.id, { position: value })}>
                        <SelectTrigger className="rounded-xl bg-gray-50 border-gray-200 w-full min-w-0">
                          <SelectValue placeholder={L.pos_ph} />
                        </SelectTrigger>
                        <SelectContent>
                          {POSITION_OPTIONS.filter(i => i.value !== 'all').map(item =>
                            <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
                          )}
                        </SelectContent>
                      </Select>
                      <input type="number" value={row.qty}
                        onChange={e => updatePositionNeed(row.id, { qty: e.target.value })}
                        placeholder={L.qty_ph}
                        className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50 min-w-0" />
                      <button type="button" onClick={() => removePositionNeed(row.id)}
                        className="text-xs text-red-500 font-semibold px-2 py-2 sm:py-0 text-left sm:text-center">
                        {L.remove}
                      </button>
                    </div>
                  ))}
                  {positionNeeds.length < 8 && (
                    <button type="button" onClick={addPositionNeed}
                      className="text-xs font-semibold" style={{ color: '#E8187A' }}>
                      {L.add_pos}
                    </button>
                  )}
                </div>
              )}

              {/* AI Toggle */}
              <div className="flex min-w-0 items-center gap-3 p-3 rounded-xl" style={{ background: '#fce8f3' }}>
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0"
                  style={{ background: '#E8187A' }}>🧠</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold break-words">{L.ai_title}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5 break-words">{L.ai_desc}</div>
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
            <Button variant="outline" onClick={onClose} className="w-full sm:w-auto rounded-xl text-xs">
              {L.cancel}
            </Button>
            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
              <Button variant="outline" onClick={handleSaveAndAI} className="w-full sm:w-auto rounded-xl text-xs">
                {L.save_ai}
              </Button>
              <Button onClick={handleSave}
                className="w-full sm:w-auto rounded-xl text-xs text-white font-semibold"
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