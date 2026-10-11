"use client"

import { useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useLang } from '@/components/layout/LanguageContext'
import { api } from '@/lib/api'
import type { ShiftDef, StaffLite } from '@/lib/apiTypes'

const PINK = '#E8187A'
const WEEKDAYS_EN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const WEEKDAYS_ZH = ['一', '二', '三', '四', '五', '六', '日']

export interface BatchCreateShiftModalProps {
  open: boolean
  onClose: () => void
  /** The manual draft. There is no batch endpoint / atomic replacement contract yet. */
  versionId: string
  staff: StaffLite[]
  shiftDefs: ShiftDef[]
  dates: string[]
  onBatchCreated: (summary: { saved: number; requested: number; partial: boolean }) => void
}

/**
 * This client intentionally does not pretend that N individual `/shifts` writes
 * are atomic. On a server failure it stays open with the exact saved/requested
 * count, so a scheduler can review the persisted grid before retrying.
 */
export function BatchCreateShiftModal({
  open, onClose, versionId, staff, shiftDefs, dates, onBatchCreated,
}: BatchCreateShiftModalProps) {
  const { lang } = useLang()
  const isZH = lang === 'zh'
  const L = {
    title: isZH ? '批量建立更期' : 'Batch Create Shifts',
    subtitle: isZH ? '為多名員工快速排更' : 'Quickly assign shifts to multiple staff',
    selectStaff: isZH ? '選擇員工（可多選）' : 'Select Staff (multi-select)',
    selectShift: isZH ? '更別類型' : 'Shift type',
    selectDays: isZH ? '適用日期（星期幾）' : 'Apply to days',
    preview: isZH ? '預覽' : 'Preview', assignments: isZH ? '個員工日期格' : ' staff-date cells',
    cancel: isZH ? '取消' : 'Cancel', create: isZH ? '逐格建立' : 'Create each cell',
    rank: isZH ? '職級' : 'Rank', allRanks: isZH ? '所有職級' : 'All ranks',
    noStaff: isZH ? '請先選擇員工' : 'Select staff first',
    warning: isZH ? '目前MVP沒有原子批量排更合約。系統會逐格寫入；如任何一格被伺服器拒絕，已成功的格會保留，本視窗會顯示確實進度，絕不當作全部已儲存。' : 'The MVP has no atomic batch-scheduling contract. Cells are written one at a time; if the server rejects one, successful earlier cells remain and this dialog reports the exact progress—never a false “all saved”.',
    partial: (saved: number, total: number) => isZH ? `已儲存 ${saved}/${total} 格；其餘未確認。請先查看更表再重試。` : `Saved ${saved}/${total} cells; the remainder is unconfirmed. Review the roster before retrying.`,
    done: (saved: number) => isZH ? `已儲存 ${saved} 格。` : `Saved ${saved} cells.`,
  }
  const [selectedStaffIds, setSelectedStaffIds] = useState<string[]>([])
  const [shiftType, setShiftType] = useState('')
  const [selectedDays, setSelectedDays] = useState<number[]>([0, 1, 2, 3, 4])
  const [rankFilter, setRankFilter] = useState('ALL')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState('')

  const ranks = useMemo(() => ['ALL', ...Array.from(new Set(staff.map((item) => item.rank))).sort()], [staff])
  const filteredStaff = useMemo(() => rankFilter === 'ALL' ? staff : staff.filter((item) => item.rank === rankFilter), [staff, rankFilter])
  const matchingDates = useMemo(() => dates.filter((iso) => {
    const day = new Date(`${iso}T00:00:00Z`).getUTCDay()
    return selectedDays.includes(day === 0 ? 6 : day - 1)
  }), [dates, selectedDays])
  const totalAssignments = selectedStaffIds.length * matchingDates.length
  const weekdays = isZH ? WEEKDAYS_ZH : WEEKDAYS_EN
  const toggleDay = (day: number) => setSelectedDays((current) => current.includes(day) ? current.filter((item) => item !== day) : [...current, day].sort())
  const toggleStaff = (id: string) => setSelectedStaffIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  const selectAllFiltered = () => {
    const ids = filteredStaff.map((item) => item.id)
    setSelectedStaffIds((current) => ids.every((id) => current.includes(id)) ? current.filter((id) => !ids.includes(id)) : [...new Set([...current, ...ids])])
  }

  async function handleCreate() {
    if (!versionId || !shiftType || !selectedStaffIds.length || !matchingDates.length) return
    const work = selectedStaffIds.flatMap((staffId) => matchingDates.map((date) => ({ staffId, date })))
    setBusy(true); setResult('')
    let saved = 0
    try {
      for (const item of work) {
        await api.upsertCell({ roster_version_id: versionId, staff_id: item.staffId, date: item.date, shift_type: shiftType, tasks: [] })
        saved += 1
      }
      onBatchCreated({ saved, requested: work.length, partial: false })
      onClose()
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Save failed'
      setResult(`${L.partial(saved, work.length)} ${message}`)
      onBatchCreated({ saved, requested: work.length, partial: true })
    } finally { setBusy(false) }
  }

  return <Dialog open={open} onOpenChange={(next) => { if (!next && !busy) onClose() }}>
    <DialogContent className="w-[min(96vw,700px)] max-w-none rounded-2xl max-h-[90vh] overflow-hidden p-0">
      <div className="flex flex-col max-h-[90vh]">
        <DialogHeader className="px-6 pt-6 pb-3 border-b border-gray-100"><div className="flex items-center gap-3"><div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0" style={{ background: '#fce8f3' }}>📋</div><div><DialogTitle className="text-lg font-bold">{L.title}</DialogTitle><p className="text-xs font-semibold mt-0.5" style={{ color: PINK }}>{L.subtitle}</p></div></div></DialogHeader>
        <div className="px-6 py-4 overflow-y-auto space-y-4">
          <label className="block text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.selectShift}<Select value={shiftType} onValueChange={setShiftType}><SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200"><SelectValue placeholder={L.selectShift} /></SelectTrigger><SelectContent>{shiftDefs.map((item) => <SelectItem key={item.id} value={item.shift_type}>{item.shift_type}{item.label ? ` · ${item.label}` : ''} ({item.start_time?.slice(0, 5) || '?'}–{item.end_time?.slice(0, 5) || '?'})</SelectItem>)}</SelectContent></Select></label>
          <div><div className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.selectDays}</div><div className="flex gap-2 mt-1.5">{weekdays.map((day, index) => <button key={day} type="button" onClick={() => toggleDay(index)} className="w-9 h-9 rounded-lg text-xs font-bold border" style={{ background: selectedDays.includes(index) ? PINK : '#fff', color: selectedDays.includes(index) ? '#fff' : '#6b7280', borderColor: selectedDays.includes(index) ? PINK : '#e5e7eb' }}>{day}</button>)}</div></div>
          <div><div className="flex items-center justify-between mb-1.5"><span className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.selectStaff}</span><div className="flex items-center gap-2"><select value={rankFilter} onChange={(event) => setRankFilter(event.target.value)} className="text-[10px] px-2 py-1 border border-gray-200 rounded-lg bg-white">{ranks.map((rank) => <option key={rank} value={rank}>{rank === 'ALL' ? L.allRanks : rank}</option>)}</select><button type="button" onClick={selectAllFiltered} className="text-[10px] font-semibold" style={{ color: PINK }}>{isZH ? '全選／取消' : 'Toggle all'}</button></div></div><div className="max-h-48 overflow-y-auto border border-gray-200 rounded-xl p-2 space-y-1">{filteredStaff.map((item) => <label key={item.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-50 cursor-pointer"><input type="checkbox" checked={selectedStaffIds.includes(item.id)} onChange={() => toggleStaff(item.id)} className="rounded border-gray-300" /><span className="text-xs font-medium">{item.name_en || item.name}</span><span className="text-[10px] text-gray-400">({item.rank})</span></label>)}</div></div>
          {totalAssignments > 0 && <div className="rounded-xl p-3 text-center" style={{ background: '#fce8f3' }}><div className="text-sm font-bold" style={{ color: PINK }}>{L.preview}: {totalAssignments}{L.assignments}</div><div className="text-[10px] text-gray-500 mt-1">{selectedStaffIds.length} {isZH ? '名員工' : 'staff'} × {matchingDates.length} {isZH ? '日' : 'days'}</div></div>}
          <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] leading-5 text-amber-900">{L.warning}</p>
          {result && <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">{result}</p>}
        </div>
        <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between"><Button variant="outline" onClick={onClose} disabled={busy} className="rounded-xl text-xs">{L.cancel}</Button><Button onClick={handleCreate} disabled={busy || !versionId || !shiftType || totalAssignments === 0} className="rounded-xl text-xs text-white" style={{ background: PINK }}>{busy ? '…' : `${L.create} (${totalAssignments})`}</Button></div>
      </div>
    </DialogContent>
  </Dialog>
}
