'use client'

import { useState } from 'react'
import { api } from '@/lib/api'

const PINK = '#E8187A'

const EVENT_TYPES_ZH = [
  { value: 'meeting', label: '會議', icon: '👥' },
  { value: 'training', label: '培訓', icon: '📘' },
  { value: 'lecture', label: '講座', icon: '🎤' },
  { value: 'visit', label: '探訪', icon: '🏠' },
  { value: 'haircut', label: '剪髮', icon: '✂️' },
  { value: 'other', label: '其他', icon: '📝' },
]
const EVENT_TYPES_EN = [
  { value: 'meeting', label: 'Meeting', icon: '👥' },
  { value: 'training', label: 'Training', icon: '📘' },
  { value: 'lecture', label: 'Seminar', icon: '🎤' },
  { value: 'visit', label: 'Visit', icon: '🏠' },
  { value: 'haircut', label: 'Haircut', icon: '✂️' },
  { value: 'other', label: 'Others', icon: '📝' },
]

// Care ranks recognised by the backend (emma_core.constants.CARE_RANKS).
const RANKS = ['RN', 'EN', 'HW', 'HCA', 'CW', 'PCW', 'AW']

type StaffingRow = { id: string; rank: string; count: string }

export interface CreateEventModalProps {
  isZH: boolean
  defaultDate: string
  onClose: () => void
  onCreated: (title: string) => void
}

export function CreateEventModal({ isZH, defaultDate, onClose, onCreated }: CreateEventModalProps) {
  const EVENT_TYPES = isZH ? EVENT_TYPES_ZH : EVENT_TYPES_EN
  const L = {
    title: isZH ? '建立特殊事件' : 'Create Special Event',
    subtitle: isZH ? 'AI 智能排更調整' : 'AI Intelligent Scheduling',
    event_type: isZH ? '事件類型' : 'Event Type',
    event_title: isZH ? '標題' : 'Title',
    title_ph: isZH ? '例如：季度大掃除' : 'e.g. Quarterly deep clean',
    remark: isZH ? '備註' : 'Remarks',
    remark_ph: isZH ? '請輸入備註' : 'Enter remarks',
    date: isZH ? '日期' : 'Date',
    time_range: isZH ? '時間範圍' : 'Time Range',
    to: isZH ? '至' : 'to',
    pos_need_title: isZH ? '輸入不同職級員工所需數量' : 'Set Required Staff by Rank',
    pos_need_sub: isZH ? '快速設定各職級所需人手' : 'Quickly configure headcount per rank',
    add_pos: isZH ? '+ 新增職級需求' : '+ Add Rank Requirement',
    qty_ph: isZH ? '所需數量' : 'Qty needed',
    remove: isZH ? '移除' : 'Remove',
    cancel: isZH ? '取消' : 'Cancel',
    save: isZH ? '儲存更改' : 'Save Changes',
  }

  const [eventType, setEventType] = useState('meeting')
  const [title, setTitle] = useState('')
  const [remark, setRemark] = useState('')
  const [date, setDate] = useState(defaultDate)
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('11:00')
  const [needsEnabled, setNeedsEnabled] = useState(false)
  const [needs, setNeeds] = useState<StaffingRow[]>([{ id: '1', rank: 'RN', count: '1' }])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const addNeed = () => needs.length < 8 && setNeeds((prev) => [
    ...prev, { id: `${prev.length + 1}-${prev.length}`, rank: 'CW', count: '1' },
  ])
  const updateNeed = (id: string, patch: Partial<StaffingRow>) =>
    setNeeds((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  const removeNeed = (id: string) => setNeeds((prev) => prev.filter((r) => r.id !== id))

  async function handleSave() {
    setBusy(true); setErr('')
    try {
      await api.createFacilityEvent({
        event_type: eventType,
        event_date: date,
        start_at: startTime ? `${date}T${startTime}:00` : undefined,
        end_at: endTime ? `${date}T${endTime}:00` : undefined,
        title: title || undefined,
        notes: remark || undefined,
        staffing_requirements: needsEnabled
          ? needs.filter((r) => r.rank && Number(r.count) > 0).map((r) => ({ rank: r.rank, count: Number(r.count) }))
          : undefined,
      })
      onCreated(title || EVENT_TYPES.find((e) => e.value === eventType)?.label || eventType)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onClose}>
      <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-6 pt-6 pb-3 border-b border-gray-100 flex items-center gap-3 flex-shrink-0">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0" style={{ background: '#fce8f3' }}>📌</div>
          <div className="min-w-0">
            <div className="text-lg font-bold truncate">{L.title}</div>
            <p className="text-xs font-semibold mt-0.5 truncate" style={{ color: PINK }}>{L.subtitle}</p>
          </div>
        </div>

        <div className="px-6 py-4 overflow-y-auto space-y-4">
          <div>
            <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider block mb-2">{L.event_type}</label>
            <div className="flex flex-wrap gap-2">
              {EVENT_TYPES.map((item) => (
                <button key={item.value} type="button" onClick={() => setEventType(item.value)}
                  className="px-3 py-2 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5"
                  style={{
                    background: eventType === item.value ? PINK : '#fff',
                    color: eventType === item.value ? '#fff' : '#6b7280',
                    borderColor: eventType === item.value ? PINK : '#e5e7eb',
                  }}>
                  <span>{item.icon}</span><span>{item.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.event_title}</label>
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={L.title_ph}
              className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400" />
          </div>

          <div>
            <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.remark}</label>
            <textarea value={remark} onChange={(e) => setRemark(e.target.value)} placeholder={L.remark_ph}
              className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400 min-h-[70px]" />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.date}</label>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50" />
            </div>
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.time_range}</label>
              <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 mt-1.5">
                <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50" />
                <span className="text-xs text-gray-400">{L.to}</span>
                <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50" />
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3 rounded-xl" style={{ background: '#fce8f3' }}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0" style={{ background: PINK }}>🧩</div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold">{L.pos_need_title}</div>
              <div className="text-[10px] text-gray-500 mt-0.5">{L.pos_need_sub}</div>
            </div>
            <button type="button" onClick={() => setNeedsEnabled(!needsEnabled)}
              className="w-10 h-6 rounded-full transition-all relative shrink-0"
              style={{ background: needsEnabled ? PINK : '#d1d5db' }}>
              <span className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all" style={{ left: needsEnabled ? '20px' : '4px' }} />
            </button>
          </div>

          {needsEnabled && (
            <div className="space-y-2">
              {needs.map((row) => (
                <div key={row.id} className="grid grid-cols-[1fr_110px_auto] gap-2 items-center">
                  <select value={row.rank} onChange={(e) => updateNeed(row.id, { rank: e.target.value })}
                    className="rounded-xl bg-gray-50 border border-gray-200 px-3 py-2 text-sm">
                    {RANKS.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <input type="number" value={row.count} onChange={(e) => updateNeed(row.id, { count: e.target.value })}
                    placeholder={L.qty_ph} className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50" />
                  <button type="button" onClick={() => removeNeed(row.id)} className="text-xs text-red-500 font-semibold">{L.remove}</button>
                </div>
              ))}
              {needs.length < 8 && (
                <button type="button" onClick={addNeed} className="text-xs font-semibold" style={{ color: PINK }}>{L.add_pos}</button>
              )}
            </div>
          )}

          {err && <div className="text-xs text-rose-600">{err}</div>}
        </div>

        <div className="px-6 py-4 border-t border-gray-100 flex gap-2 justify-end flex-shrink-0">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">{L.cancel}</button>
          <button onClick={handleSave} disabled={busy}
            className="px-4 py-1.5 text-xs rounded-lg text-white font-semibold disabled:opacity-60" style={{ background: PINK }}>
            {busy ? '…' : L.save}
          </button>
        </div>
      </div>
    </div>
  )
}
