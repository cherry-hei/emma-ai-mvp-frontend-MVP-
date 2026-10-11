'use client'

import { useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import type { FacilityEventType, StaffLite } from '@/lib/apiTypes'

const PINK = '#E8187A'
const ICONS: Record<string, string> = {
  hair_cutting: '✂️', cgat: '🩺', pgt: '📋', medication_board_checking: '💊',
  medication_record_checking: '📒', podiatry: '🦶', monthly_weighing: '⚖️',
  visiting: '🏠', meeting_training: '👥',
}

type StaffingRow = { id: string; rank: string; count: string }

export interface CreateEventModalProps {
  isZH: boolean
  defaultDate: string
  /** Dates currently loaded for this authenticated roster period. */
  dates?: string[]
  staffList?: StaffLite[]
  onClose: () => void
  onCreated: (title: string) => void
}

/**
 * Facility events are real server records. The current API persists event type,
 * date/time, title/notes and rank staffing requirements. It deliberately does
 * not pretend to persist per-person attendance: that requires an event-assignee
 * contract and is shown as unavailable rather than silently dropped.
 */
export function CreateEventModal({ isZH, defaultDate, dates = [], staffList = [], onClose, onCreated }: CreateEventModalProps) {
  const [types, setTypes] = useState<FacilityEventType[]>([])
  const [eventType, setEventType] = useState('')
  const [title, setTitle] = useState('')
  const [remark, setRemark] = useState('')
  const [date, setDate] = useState(defaultDate)
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('11:00')
  const ranks = useMemo(() => [...new Set(staffList.map((staff) => staff.rank).filter(Boolean))].sort(), [staffList])
  const [needsEnabled, setNeedsEnabled] = useState(false)
  const [needs, setNeeds] = useState<StaffingRow[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const eventTypes = useMemo(() => types.map((type) => ({ value: type.code, label: isZH ? type.label_zh : type.label_en, icon: ICONS[type.code] ?? '📌' })), [isZH, types])
  const periodDates = useMemo(() => [...new Set(dates)].sort(), [dates])
  const L = {
    title: isZH ? '新增特別事項' : 'Create Special Event',
    subtitle: isZH ? '事件人手需求會交由伺服器規則引擎驗證' : 'Event staffing requirements are validated by the server rules engine',
    type: isZH ? '事件類型' : 'Event type', name: isZH ? '名稱' : 'Name', namePh: isZH ? '例如：感染控制培訓' : 'e.g. Infection-control training',
    note: isZH ? '備註' : 'Notes', date: isZH ? '日期' : 'Date', start: isZH ? '開始' : 'Start', end: isZH ? '結束' : 'End',
    requirements: isZH ? '硬性人手需求（按職級）' : 'Hard staffing requirements (by rank)',
    requirementHelp: isZH ? '儲存至本機構事件記錄；發佈前由伺服器規則檢查決定結果。' : 'Stored on this facility event; the server rule check determines the result before publication.',
    add: isZH ? '＋ 新增職級需求' : '+ Add rank requirement', remove: isZH ? '移除' : 'Remove', count: isZH ? '所需人數' : 'Headcount',
    staff: isZH ? '指定員工' : 'Specific staff',
    staffUnavailable: isZH ? '目前MVP事件API未有已指派員工／hard旗標的持久化合約。為避免假裝已儲存，指定員工選擇已停用；此事件的職級人手需求仍會儲存並由伺服器規則檢查。' : 'The MVP event API has no persisted event-assignee/hard-flag contract. Specific-staff selection is disabled rather than falsely claiming it saved; rank staffing requirements are still persisted and server-validated.',
    noStaff: isZH ? '這個登入機構沒有可用員工職級。' : 'This signed-in organisation has no available staff ranks.',
    cancel: isZH ? '取消' : 'Cancel', save: isZH ? '儲存特別事項' : 'Save special event',
  }

  useEffect(() => {
    let cancelled = false
    api.facilityEventTypes().then((rows) => {
      if (cancelled) return
      setTypes(rows); setEventType((current) => current || rows[0]?.code || '')
    }).catch((cause) => { if (!cancelled) setErr(cause instanceof Error ? cause.message : 'Could not load event types') })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!periodDates.length) return
    setDate((current) => periodDates.includes(current) ? current : (periodDates.includes(defaultDate) ? defaultDate : periodDates[0]))
  }, [defaultDate, periodDates])

  useEffect(() => {
    if (!needs.length && ranks.length) setNeeds([{ id: 'initial', rank: ranks[0], count: '1' }])
  }, [needs.length, ranks])

  function addNeed() { if (needs.length < 8) setNeeds((current) => [...current, { id: `${Date.now()}-${current.length}`, rank: ranks[0] || '', count: '1' }]) }
  function updateNeed(id: string, patch: Partial<StaffingRow>) { setNeeds((current) => current.map((row) => row.id === id ? { ...row, ...patch } : row)) }
  function removeNeed(id: string) { setNeeds((current) => current.filter((row) => row.id !== id)) }

  async function save() {
    if (!eventType || !date) return
    const requirements = needsEnabled ? needs.filter((row) => row.rank && Number(row.count) > 0).map((row) => ({ rank: row.rank, count: Number(row.count), is_additive: true })) : undefined
    if (needsEnabled && !requirements?.length) { setErr(isZH ? '請至少提供一項有效的人手需求。' : 'Provide at least one valid staffing requirement.'); return }
    setBusy(true); setErr('')
    try {
      await api.createFacilityEvent({ event_type: eventType, event_date: date, start_at: startTime ? `${date}T${startTime}:00` : undefined, end_at: endTime ? `${date}T${endTime}:00` : undefined, title: title.trim() || undefined, notes: remark.trim() || undefined, staffing_requirements: requirements })
      onCreated(title.trim() || eventTypes.find((event) => event.value === eventType)?.label || eventType)
    } catch (cause) { setErr(cause instanceof Error ? cause.message : 'Create failed') } finally { setBusy(false) }
  }

  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 backdrop-blur-[2px] sm:items-center sm:p-5" role="dialog" aria-modal="true" aria-label={L.title}>
    <button type="button" className="absolute inset-0 cursor-default" onClick={onClose} aria-label={L.cancel} />
    <section className="relative z-10 flex max-h-[94dvh] w-full max-w-3xl flex-col overflow-hidden rounded-t-[28px] bg-white shadow-2xl sm:max-h-[90vh] sm:rounded-3xl">
      <header className="flex items-start gap-3 border-b border-slate-100 px-4 py-4 sm:px-6"><div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-pink-50 text-xl">📌</div><div className="min-w-0 flex-1"><h2 className="text-lg font-black text-slate-950">{L.title}</h2><p className="mt-1 text-xs font-bold text-pink-600">{L.subtitle}</p></div><button type="button" onClick={onClose} className="rounded-full p-2 text-slate-500 hover:bg-slate-100" aria-label={L.cancel}>×</button></header>
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4 sm:px-6">
        <section><div className="text-[10px] font-black uppercase tracking-wider text-slate-500">{L.type}</div><div className="mt-2 flex flex-wrap gap-2">{eventTypes.map((event) => <button key={event.value} type="button" onClick={() => setEventType(event.value)} className={`rounded-xl border px-3 py-2 text-xs font-bold ${eventType === event.value ? 'border-pink-600 bg-pink-600 text-white' : 'border-slate-200 bg-white text-slate-600'}`}><span className="mr-1">{event.icon}</span>{event.label}</button>)}</div></section>
        <div className="grid gap-3 sm:grid-cols-2"><label className="text-xs font-bold text-slate-600">{L.name}<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={L.namePh} className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-400" /></label><label className="text-xs font-bold text-slate-600">{L.date}{periodDates.length ? <select value={date} onChange={(event) => setDate(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-400">{periodDates.map((value) => <option key={value} value={value}>{value}</option>)}</select> : <input type="date" value={date} onChange={(event) => setDate(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm" />}</label><label className="text-xs font-bold text-slate-600">{L.start}<input type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm" /></label><label className="text-xs font-bold text-slate-600">{L.end}<input type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm" /></label></div>
        <label className="block text-xs font-bold text-slate-600">{L.note}<textarea value={remark} onChange={(event) => setRemark(event.target.value)} className="mt-1.5 min-h-20 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-400" /></label>
        <section className="rounded-2xl border border-pink-100 bg-pink-50/50 p-4"><div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-black text-slate-900">{L.requirements}</h3><p className="mt-1 text-[10px] leading-4 text-slate-600">{L.requirementHelp}</p></div><button type="button" onClick={() => setNeedsEnabled((current) => !current)} className={`h-7 w-12 shrink-0 rounded-full p-1 ${needsEnabled ? 'bg-pink-600' : 'bg-slate-300'}`} aria-pressed={needsEnabled}><span className={`block h-5 w-5 rounded-full bg-white transition-transform ${needsEnabled ? 'translate-x-5' : ''}`} /></button></div>{needsEnabled && <div className="mt-4 space-y-2">{ranks.length ? needs.map((row) => <div key={row.id} className="grid gap-2 sm:grid-cols-[1fr_120px_auto]"><select value={row.rank} onChange={(event) => updateNeed(row.id, { rank: event.target.value })} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">{ranks.map((rank) => <option key={rank} value={rank}>{rank}</option>)}</select><input type="number" min="1" value={row.count} onChange={(event) => updateNeed(row.id, { count: event.target.value })} placeholder={L.count} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" /><button type="button" onClick={() => removeNeed(row.id)} className="text-xs font-bold text-red-600">{L.remove}</button></div>) : <p className="text-xs text-amber-800">{L.noStaff}</p>}{ranks.length > 0 && needs.length < 8 && <button type="button" onClick={addNeed} className="text-xs font-bold text-pink-700">{L.add}</button>}</div>}</section>
        <section className="rounded-2xl border border-amber-200 bg-amber-50 p-4"><h3 className="text-sm font-black text-amber-900">{L.staff}</h3><p className="mt-1 text-[11px] leading-5 text-amber-900">{L.staffUnavailable}</p><div className="mt-3 flex flex-wrap gap-1.5">{staffList.slice(0, 12).map((staff) => <span key={staff.id} className="rounded-full border border-amber-200 bg-white px-2 py-1 text-[10px] text-amber-800 opacity-60">{staff.name_en || staff.name} · {staff.rank}</span>)}</div></section>
        {err && <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">{err}</p>}
      </div>
      <footer className="flex items-center justify-between gap-3 border-t border-slate-100 bg-white px-4 py-4 sm:px-6"><button type="button" onClick={onClose} disabled={busy} className="rounded-xl border border-slate-200 px-4 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50">{L.cancel}</button><button type="button" onClick={() => void save()} disabled={busy || !eventType || !date} className="rounded-xl bg-pink-600 px-5 py-3 text-sm font-black text-white hover:bg-pink-700 disabled:opacity-50">{busy ? '…' : L.save}</button></footer>
    </section>
  </div>
}
