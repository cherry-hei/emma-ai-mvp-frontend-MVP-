'use client'

// Phase 4 operations: the three data sets the task, event and floor rules read.
// Until this screen existed the rules were real but unreachable — a manager
// could not record that someone is medication-audited, could not book an event
// with its extra staffing, and could not state a floor minimum at all. Those
// tables were seed-only, which meant the checks either never fired or fired
// forever with no way to correct them.

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import type {
  ApiStaff, FacilityEvent, FacilityEventType, FloorRule, StaffQualification, Unit,
} from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

type Tab = 'events' | 'qualifications' | 'floors'

// The event-type list comes from GET /facility-events/types (task 4.2). It used
// to be a hardcoded copy here, which is exactly the drift Cherry asked to close
// on 1 Aug: "I don't want the frontend hardcoding a list that drifts from your
// validation. One endpoint, single source of truth." The copy had already gone
// stale — the server accepts nine types and this list agreed only because the
// server's alias table was quietly absorbing the difference.

const QUALIFICATIONS = [
  { value: 'medication_audited', zh: '藥物審核合格', en: 'Medication audited' },
  { value: 'mentor', zh: '導師', en: 'Mentor' },
  { value: 'new_staff', zh: '新入職', en: 'New staff' },
]

const WEEKDAYS = [
  { value: 0, zh: '一', en: 'Mon' }, { value: 1, zh: '二', en: 'Tue' },
  { value: 2, zh: '三', en: 'Wed' }, { value: 3, zh: '四', en: 'Thu' },
  { value: 4, zh: '五', en: 'Fri' }, { value: 5, zh: '六', en: 'Sat' },
  { value: 6, zh: '日', en: 'Sun' },
]

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

export default function SchedulingPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const [tab, setTab] = useState<Tab>('events')
  const [units, setUnits] = useState<Unit[]>([])
  const [staff, setStaff] = useState<ApiStaff[]>([])
  const [events, setEvents] = useState<FacilityEvent[]>([])
  const [quals, setQuals] = useState<StaffQualification[]>([])
  const [rules, setRules] = useState<FloorRule[]>([])
  const [eventTypes, setEventTypes] = useState<FacilityEventType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const T = {
    title: isZH ? '任務排程設定' : 'Scheduling Rules',
    sub: isZH ? '任務資格 · 活動人手 · 樓層最低人手' : 'Event staffing · qualifications · floor minimums',
    events: isZH ? '活動' : 'Events',
    quals: isZH ? '員工資格' : 'Qualifications',
    floors: isZH ? '樓層人手' : 'Floor coverage',
    add: isZH ? '新增' : 'Add',
    remove: isZH ? '刪除' : 'Remove',
    none: isZH ? '尚無資料' : 'Nothing configured yet',
    date: isZH ? '日期' : 'Date',
    type: isZH ? '類型' : 'Type',
    title_: isZH ? '標題' : 'Title',
    unit: isZH ? '單位' : 'Unit',
    allUnits: isZH ? '全院舍' : 'Whole facility',
    requirement: isZH ? '人手需求' : 'Staffing requirement',
    additive: isZH ? '額外人手' : 'Extra head',
    concurrent: isZH ? '同時執行' : 'Concurrent duty',
    templated: isZH ? '有預設需求' : 'has a default requirement',
    manual: isZH ? '需自行填寫' : 'manager-entered',
    staffName: isZH ? '員工' : 'Staff',
    qualification: isZH ? '資格' : 'Qualification',
    from: isZH ? '生效日' : 'From',
    expiry: isZH ? '到期日' : 'Expires',
    active: isZH ? '生效中' : 'Active',
    rank: isZH ? '職級' : 'Rank',
    window: isZH ? '時段' : 'Window',
    minCount: isZH ? '最低人數' : 'Minimum',
    weekdays: isZH ? '適用星期' : 'Days',
    everyDay: isZH ? '每日' : 'Every day',
    shiftTypes: isZH ? '限定更別' : 'Shift codes',
    composition: isZH ? '7A 組合條件' : '7A composition condition',
    optional: isZH ? '選填' : 'optional',
  }

  // `initial` only: after a save, keep the table on screen while it reloads.
  // Swapping the whole tab for a spinner on every add/remove makes a working
  // page look like it reset.
  const refresh = useCallback(async (initial = false) => {
    if (initial) setLoading(true)
    setError('')
    try {
      const [u, s, e, q, r, t] = await Promise.all([
        api.units(), api.listStaff(), api.facilityEvents(),
        api.staffQualifications(), api.floorRules(),
        api.facilityEventTypes(),
      ])
      setUnits(u); setStaff(s); setEvents(e); setQuals(q); setRules(r)
      setEventTypes(t)
    } catch (e) {
      setError(errText(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh(true) }, [refresh])

  const run = useCallback(async (action: () => Promise<unknown>, done: string) => {
    setError(''); setNotice('')
    try {
      await action()
      setNotice(done)
      await refresh()
    } catch (e) {
      setError(errText(e))
    }
  }, [refresh])

  const staffName = useMemo(() => {
    const m = new Map(staff.map((s) => [s.id, s.name_en || s.name]))
    return (id: string) => m.get(id) ?? id
  }, [staff])

  const unitName = useMemo(() => {
    const m = new Map(units.map((u) => [u.id, u.name]))
    return (id?: string | null) => (id ? m.get(id) ?? id : T.allUnits)
  }, [units, T.allUnits])

  const TABS: Array<{ key: Tab; label: string; count: number }> = [
    { key: 'events', label: T.events, count: events.length },
    { key: 'qualifications', label: T.quals, count: quals.length },
    { key: 'floors', label: T.floors, count: rules.length },
  ]

  return (
    <div className="p-5 space-y-4">
      <header>
        <h1 className="text-lg font-bold text-gray-800">{T.title}</h1>
        <p className="text-[11px] text-gray-400">{T.sub}</p>
      </header>

      {error && (
        <div className="rounded-lg border px-3 py-2 text-[11px]"
             style={{ background: '#fff1f2', borderColor: '#fecdd3', color: '#be123c' }}>
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border px-3 py-2 text-[11px]"
             style={{ background: '#f0fdf4', borderColor: '#bbf7d0', color: '#15803d' }}>
          {notice}
        </div>
      )}

      <div className="flex gap-1 border-b" style={{ borderColor: '#e5e7eb' }}>
        {TABS.map(({ key, label, count }) => (
          <button key={key} onClick={() => setTab(key)}
            className="px-3 py-2 text-[11px] border-b-2 -mb-px transition-colors"
            style={{
              color: tab === key ? PINK : '#6b7280',
              borderBottomColor: tab === key ? PINK : 'transparent',
              fontWeight: tab === key ? 600 : 400,
            }}>
            {label} <span className="text-gray-300">({count})</span>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-[11px] text-gray-400">…</div>
      ) : tab === 'events' ? (
        <EventsTab events={events} units={units} eventTypes={eventTypes} T={T}
                   isZH={isZH} unitName={unitName} run={run} />
      ) : tab === 'qualifications' ? (
        <QualificationsTab quals={quals} staff={staff} T={T} isZH={isZH}
                           staffName={staffName} run={run} />
      ) : (
        <FloorRulesTab rules={rules} units={units} T={T} isZH={isZH}
                       unitName={unitName} run={run} />
      )}
    </div>
  )
}

type Labels = Record<string, string>
type Run = (action: () => Promise<unknown>, done: string) => Promise<void>

const CARD = 'rounded-lg border bg-white'
const CARD_STYLE = { borderColor: '#e5e7eb' }
const INPUT = 'border rounded px-2 py-1 text-[11px]'
const INPUT_STYLE = { borderColor: '#e5e7eb' }

function AddButton({ label, onClick, busy }: {
  label: string; onClick: () => void; busy?: boolean
}) {
  return (
    <button onClick={onClick} disabled={busy}
      className="px-3 py-1.5 rounded text-[11px] text-white disabled:opacity-50"
      style={{ background: PINK }}>
      {label}
    </button>
  )
}

// ── events ──────────────────────────────────────────────────────────────────
function EventsTab({ events, units, eventTypes, T, isZH, unitName, run }: {
  events: FacilityEvent[]; units: Unit[]; eventTypes: FacilityEventType[]
  T: Labels; isZH: boolean
  unitName: (id?: string | null) => string; run: Run
}) {
  const today = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({
    event_type: '', event_date: today, title: '', unit_id: '',
  })
  const [extra, setExtra] = useState<Array<{ rank: string; count: number; is_additive: boolean }>>([])
  // No hardcoded default: the first type is whatever the server publishes. A
  // literal 'hair_cutting' here would be a tenth copy of the list to keep in
  // step, and would post a type this facility might not have.
  const selected = form.event_type || eventTypes[0]?.code || ''
  const chosen = eventTypes.find((e) => e.code === selected)

  const submit = () => run(async () => {
    await api.createFacilityEvent({
      event_type: selected,
      event_date: form.event_date,
      title: form.title || undefined,
      unit_id: form.unit_id || undefined,
      // Templated types fill themselves in; sending an empty list would mean
      // "this event needs nobody", which is a different claim.
      staffing_requirements: extra.length ? extra : undefined,
    })
    setExtra([])
    setForm((f) => ({ ...f, title: '' }))
  }, isZH ? '活動已新增' : 'Event added')

  return (
    <div className="space-y-3">
      <div className={`${CARD} p-3 space-y-2`} style={CARD_STYLE}>
        <div className="flex flex-wrap gap-2 items-end">
          <label className="text-[10px] text-gray-500">
            <div>{T.type}</div>
            <select className={INPUT} style={INPUT_STYLE} value={selected}
                    onChange={(e) => setForm({ ...form, event_type: e.target.value })}>
              {eventTypes.map((e) => (
                <option key={e.code} value={e.code}>
                  {isZH ? e.label_zh : e.label_en}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.date}</div>
            <input type="date" className={INPUT} style={INPUT_STYLE} value={form.event_date}
                   onChange={(e) => setForm({ ...form, event_date: e.target.value })} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.title_}</div>
            <input className={INPUT} style={INPUT_STYLE} value={form.title}
                   onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.unit}</div>
            <select className={INPUT} style={INPUT_STYLE} value={form.unit_id}
                    onChange={(e) => setForm({ ...form, unit_id: e.target.value })}>
              <option value="">{T.allUnits}</option>
              {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </label>
          <AddButton label={T.add} onClick={submit} />
        </div>

        <div className="text-[10px] text-gray-400">
          {chosen?.templated ? `· ${T.templated}` : `· ${T.manual}`}
        </div>

        {!chosen?.templated && (
          <RequirementEditor rows={extra} setRows={setExtra} T={T} isZH={isZH} />
        )}
      </div>

      <div className={CARD} style={CARD_STYLE}>
        {events.length === 0 ? (
          <div className="p-4 text-[11px] text-gray-400">{T.none}</div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-gray-400" style={{ background: '#f9fafb' }}>
              <tr>
                <th className="text-left px-3 py-2">{T.date}</th>
                <th className="text-left px-3 py-2">{T.type}</th>
                <th className="text-left px-3 py-2">{T.title_}</th>
                <th className="text-left px-3 py-2">{T.unit}</th>
                <th className="text-left px-3 py-2">{T.requirement}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t" style={{ borderColor: '#f3f4f6' }}>
                  <td className="px-3 py-2 text-gray-700">{e.event_date}</td>
                  <td className="px-3 py-2 text-gray-500">{e.event_type}</td>
                  <td className="px-3 py-2 text-gray-700">{e.title || '—'}</td>
                  <td className="px-3 py-2 text-gray-500">{unitName(e.unit_id)}</td>
                  <td className="px-3 py-2">
                    {e.staffing_requirements.length === 0 ? (
                      <span className="text-gray-300">—</span>
                    ) : e.staffing_requirements.map((r) => (
                      <span key={r.id} className="inline-block mr-1 px-1.5 py-0.5 rounded"
                        style={{
                          background: r.is_additive ? '#fff0f5' : '#f1f5f9',
                          color: r.is_additive ? PINK : '#475569',
                        }}>
                        {r.count}× {r.rank} · {r.is_additive ? T.additive : T.concurrent}
                      </span>
                    ))}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button className="text-[10px] text-gray-400 hover:text-rose-600"
                      onClick={() => run(() => api.deleteFacilityEvent(e.id),
                                          isZH ? '活動已刪除' : 'Event removed')}>
                      {T.remove}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function RequirementEditor({ rows, setRows, T, isZH }: {
  rows: Array<{ rank: string; count: number; is_additive: boolean }>
  setRows: (r: Array<{ rank: string; count: number; is_additive: boolean }>) => void
  T: Labels; isZH: boolean
}) {
  return (
    <div className="space-y-1">
      {rows.map((row, i) => (
        <div key={i} className="flex gap-2 items-center">
          <input className={`${INPUT} w-24`} style={INPUT_STYLE} value={row.rank}
                 placeholder="RN / CW|HCA"
                 onChange={(e) => setRows(rows.map((r, j) =>
                   j === i ? { ...r, rank: e.target.value } : r))} />
          <input type="number" min={1} className={`${INPUT} w-16`} style={INPUT_STYLE}
                 value={row.count}
                 onChange={(e) => setRows(rows.map((r, j) =>
                   j === i ? { ...r, count: Number(e.target.value) } : r))} />
          <label className="text-[10px] text-gray-500 flex items-center gap-1">
            <input type="checkbox" checked={row.is_additive}
                   onChange={(e) => setRows(rows.map((r, j) =>
                     j === i ? { ...r, is_additive: e.target.checked } : r))} />
            {T.additive}
          </label>
          <button className="text-[10px] text-gray-400 hover:text-rose-600"
                  onClick={() => setRows(rows.filter((_, j) => j !== i))}>
            {T.remove}
          </button>
        </div>
      ))}
      <button className="text-[10px]" style={{ color: PINK }}
              onClick={() => setRows([...rows, { rank: 'RN', count: 1, is_additive: true }])}>
        + {isZH ? '新增需求' : 'Add requirement'}
      </button>
    </div>
  )
}

// ── qualifications ──────────────────────────────────────────────────────────
function QualificationsTab({ quals, staff, T, isZH, staffName, run }: {
  quals: StaffQualification[]; staff: ApiStaff[]; T: Labels; isZH: boolean
  staffName: (id: string) => string; run: Run
}) {
  const [form, setForm] = useState({
    staff_id: '', qualification_type: 'medication_audited',
    effective_from: '', expiry_date: '',
  })

  const submit = () => run(async () => {
    await api.createStaffQualification({
      staff_id: form.staff_id || staff[0]?.id,
      qualification_type: form.qualification_type,
      effective_from: form.effective_from || undefined,
      expiry_date: form.expiry_date || undefined,
    })
  }, isZH ? '資格已記錄' : 'Qualification recorded')

  return (
    <div className="space-y-3">
      <div className={`${CARD} p-3`} style={CARD_STYLE}>
        <div className="flex flex-wrap gap-2 items-end">
          <label className="text-[10px] text-gray-500">
            <div>{T.staffName}</div>
            <select className={INPUT} style={INPUT_STYLE} value={form.staff_id}
                    onChange={(e) => setForm({ ...form, staff_id: e.target.value })}>
              <option value="">{isZH ? '請選擇' : 'Select…'}</option>
              {staff.map((s) => (
                <option key={s.id} value={s.id}>{s.name_en || s.name} · {s.rank}</option>
              ))}
            </select>
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.qualification}</div>
            <select className={INPUT} style={INPUT_STYLE} value={form.qualification_type}
                    onChange={(e) => setForm({ ...form, qualification_type: e.target.value })}>
              {QUALIFICATIONS.map((q) => (
                <option key={q.value} value={q.value}>{isZH ? q.zh : q.en}</option>
              ))}
            </select>
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.from} <span className="text-gray-300">({T.optional})</span></div>
            <input type="date" className={INPUT} style={INPUT_STYLE} value={form.effective_from}
                   onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.expiry} <span className="text-gray-300">({T.optional})</span></div>
            <input type="date" className={INPUT} style={INPUT_STYLE} value={form.expiry_date}
                   onChange={(e) => setForm({ ...form, expiry_date: e.target.value })} />
          </label>
          <AddButton label={T.add} onClick={submit} busy={!form.staff_id && !staff.length} />
        </div>
      </div>

      <div className={CARD} style={CARD_STYLE}>
        {quals.length === 0 ? (
          <div className="p-4 text-[11px] text-gray-400">{T.none}</div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-gray-400" style={{ background: '#f9fafb' }}>
              <tr>
                <th className="text-left px-3 py-2">{T.staffName}</th>
                <th className="text-left px-3 py-2">{T.qualification}</th>
                <th className="text-left px-3 py-2">{T.from}</th>
                <th className="text-left px-3 py-2">{T.expiry}</th>
                <th className="text-left px-3 py-2">{T.active}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {quals.map((q) => (
                <tr key={q.id} className="border-t" style={{ borderColor: '#f3f4f6' }}>
                  <td className="px-3 py-2 text-gray-700">{staffName(q.staff_id)}</td>
                  <td className="px-3 py-2 text-gray-500">{q.qualification_type}</td>
                  <td className="px-3 py-2 text-gray-500">{q.effective_from || '—'}</td>
                  <td className="px-3 py-2 text-gray-500">{q.expiry_date || '—'}</td>
                  <td className="px-3 py-2">
                    <input type="checkbox" checked={q.is_active}
                      onChange={(e) => run(
                        () => api.updateStaffQualification(q.id, { is_active: e.target.checked }),
                        isZH ? '已更新' : 'Updated')} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button className="text-[10px] text-gray-400 hover:text-rose-600"
                      onClick={() => run(() => api.deleteStaffQualification(q.id),
                                          isZH ? '資格已刪除' : 'Qualification removed')}>
                      {T.remove}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── floor coverage ──────────────────────────────────────────────────────────
function FloorRulesTab({ rules, units, T, isZH, unitName, run }: {
  rules: FloorRule[]; units: Unit[]; T: Labels; isZH: boolean
  unitName: (id?: string | null) => string; run: Run
}) {
  const [form, setForm] = useState({
    unit_id: '', time_window_start: '07:00', time_window_end: '17:00',
    rank: 'HCA', min_count: 3, weekdays: [] as number[], shiftTypes: '',
  })

  const submit = () => run(async () => {
    await api.createFloorRule({
      unit_id: form.unit_id || units[0]?.id,
      time_window_start: form.time_window_start,
      time_window_end: form.time_window_end,
      rank: form.rank,
      min_count: Number(form.min_count),
      condition_json: {
        ...(form.weekdays.length ? { weekdays: [...form.weekdays].sort() } : {}),
        ...(form.shiftTypes.trim()
          ? { required_shift_types: form.shiftTypes.split(',').map((s) => s.trim()).filter(Boolean) }
          : {}),
      },
    })
  }, isZH ? '規則已新增' : 'Rule added')

  const toggleDay = (d: number) => setForm((f) => ({
    ...f,
    weekdays: f.weekdays.includes(d) ? f.weekdays.filter((x) => x !== d) : [...f.weekdays, d],
  }))

  return (
    <div className="space-y-3">
      <div className={`${CARD} p-3 space-y-2`} style={CARD_STYLE}>
        <div className="flex flex-wrap gap-2 items-end">
          <label className="text-[10px] text-gray-500">
            <div>{T.unit}</div>
            <select className={INPUT} style={INPUT_STYLE} value={form.unit_id}
                    onChange={(e) => setForm({ ...form, unit_id: e.target.value })}>
              {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.window}</div>
            <div className="flex items-center gap-1">
              <input type="time" className={INPUT} style={INPUT_STYLE}
                     value={form.time_window_start}
                     onChange={(e) => setForm({ ...form, time_window_start: e.target.value })} />
              <span className="text-gray-300">–</span>
              <input type="time" className={INPUT} style={INPUT_STYLE}
                     value={form.time_window_end}
                     onChange={(e) => setForm({ ...form, time_window_end: e.target.value })} />
            </div>
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.rank}</div>
            <input className={`${INPUT} w-24`} style={INPUT_STYLE} value={form.rank}
                   placeholder="HCA / CW|HCA"
                   onChange={(e) => setForm({ ...form, rank: e.target.value })} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.minCount}</div>
            <input type="number" min={0} className={`${INPUT} w-16`} style={INPUT_STYLE}
                   value={form.min_count}
                   onChange={(e) => setForm({ ...form, min_count: Number(e.target.value) })} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div>{T.shiftTypes} <span className="text-gray-300">({T.optional})</span></div>
            <input className={`${INPUT} w-28`} style={INPUT_STYLE} value={form.shiftTypes}
                   placeholder="7A, 7P"
                   onChange={(e) => setForm({ ...form, shiftTypes: e.target.value })} />
          </label>
          <AddButton label={T.add} onClick={submit} busy={!units.length} />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500">{T.weekdays}</span>
          {WEEKDAYS.map((d) => (
            <button key={d.value} onClick={() => toggleDay(d.value)}
              className="px-1.5 py-0.5 rounded text-[10px] border"
              style={{
                borderColor: form.weekdays.includes(d.value) ? PINK : '#e5e7eb',
                color: form.weekdays.includes(d.value) ? PINK : '#9ca3af',
                background: form.weekdays.includes(d.value) ? '#fff0f5' : 'transparent',
              }}>
              {isZH ? d.zh : d.en}
            </button>
          ))}
          {form.weekdays.length === 0 && (
            <span className="text-[10px] text-gray-300">{T.everyDay}</span>
          )}
        </div>
      </div>

      <div className={CARD} style={CARD_STYLE}>
        {rules.length === 0 ? (
          <div className="p-4 text-[11px] text-gray-400">{T.none}</div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-gray-400" style={{ background: '#f9fafb' }}>
              <tr>
                <th className="text-left px-3 py-2">{T.unit}</th>
                <th className="text-left px-3 py-2">{T.window}</th>
                <th className="text-left px-3 py-2">{T.rank}</th>
                <th className="text-left px-3 py-2">{T.minCount}</th>
                <th className="text-left px-3 py-2">{T.weekdays}</th>
                <th className="text-left px-3 py-2">{T.shiftTypes}</th>
                <th className="text-left px-3 py-2">{T.active}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => {
                const days = r.condition_json.weekdays
                const composed = r.condition_json.when_7a_composition
                return (
                  <tr key={r.id} className="border-t" style={{ borderColor: '#f3f4f6' }}>
                    <td className="px-3 py-2 text-gray-700">
                      {unitName(r.unit_id)}
                      {composed && (
                        <div className="text-[9px] text-gray-400">
                          {T.composition}: {Object.entries(composed)
                            .map(([k, v]) => `${v}× ${k}`).join(' + ')}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-gray-500">
                      {r.time_window_start.slice(0, 5)}–{r.time_window_end.slice(0, 5)}
                    </td>
                    <td className="px-3 py-2 text-gray-700">{r.rank}</td>
                    <td className="px-3 py-2 font-semibold" style={{ color: PINK }}>
                      {r.min_count}
                    </td>
                    <td className="px-3 py-2 text-gray-500">
                      {days?.length
                        ? days.map((d) => (isZH ? WEEKDAYS[d].zh : WEEKDAYS[d].en)).join(' ')
                        : T.everyDay}
                    </td>
                    <td className="px-3 py-2 text-gray-500">
                      {r.condition_json.required_shift_types?.join(', ') || '—'}
                    </td>
                    <td className="px-3 py-2">
                      <input type="checkbox" checked={r.active}
                        onChange={(e) => run(
                          () => api.updateFloorRule(r.id, { active: e.target.checked }),
                          isZH ? '已更新' : 'Updated')} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button className="text-[10px] text-gray-400 hover:text-rose-600"
                        onClick={() => run(() => api.deleteFloorRule(r.id),
                                            isZH ? '規則已刪除' : 'Rule removed')}>
                        {T.remove}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
