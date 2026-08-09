"use client"

import { useState, useMemo } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useLang } from '@/components/layout/LanguageContext'
import type { ShiftDef, StaffLite } from '@/lib/apiTypes'

const PINK = '#E8187A'
const WEEKDAYS_EN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const WEEKDAYS_ZH = ['一', '二', '三', '四', '五', '六', '日']

export interface BatchCreateShiftModalProps {
  open: boolean
  onClose: () => void
  staff: StaffLite[]
  shiftDefs: ShiftDef[]
  dates: string[]
  onBatchCreated: (count: number) => void
}

export function BatchCreateShiftModal({
  open, onClose, staff, shiftDefs, dates, onBatchCreated,
}: BatchCreateShiftModalProps) {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const L = {
    title: isZH ? '批量建立更期' : 'Batch Create Shifts',
    subtitle: isZH ? '為多名員工快速排更' : 'Quickly assign shifts to multiple staff',
    selectStaff: isZH ? '選擇員工（可多選）' : 'Select Staff (multi-select)',
    selectShift: isZH ? '更別類型' : 'Shift Type',
    selectDays: isZH ? '適用日期（星期幾）' : 'Apply to Days',
    preview: isZH ? '預覽' : 'Preview',
    assignments: isZH ? '個排班' : ' assignments',
    cancel: isZH ? '取消' : 'Cancel',
    create: isZH ? '批量建立' : 'Create All',
    rank: isZH ? '職級' : 'Rank',
    allRanks: isZH ? '所有職級' : 'All Ranks',
    noStaff: isZH ? '請先選擇員工' : 'Select staff first',
  }

  const [selectedStaffIds, setSelectedStaffIds] = useState<string[]>([])
  const [shiftType, setShiftType] = useState('')
  const [selectedDays, setSelectedDays] = useState<number[]>([0, 1, 2, 3, 4]) // Mon-Fri default
  const [rankFilter, setRankFilter] = useState('ALL')
  const [busy, setBusy] = useState(false)

  const ranks = useMemo(() => ['ALL', ...Array.from(new Set(staff.map(s => s.rank))).sort()], [staff])
  const filteredStaff = useMemo(
    () => rankFilter === 'ALL' ? staff : staff.filter(s => s.rank === rankFilter),
    [staff, rankFilter]
  )

  const weekdays = isZH ? WEEKDAYS_ZH : WEEKDAYS_EN

  const toggleDay = (day: number) => {
    setSelectedDays(prev => prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day])
  }

  const toggleStaff = (id: string) => {
    setSelectedStaffIds(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id])
  }

  const selectAllFiltered = () => {
    const ids = filteredStaff.map(s => s.id)
    setSelectedStaffIds(prev => {
      const allSelected = ids.every(id => prev.includes(id))
      if (allSelected) return prev.filter(id => !ids.includes(id))
      return [...new Set([...prev, ...ids])]
    })
  }

  // Calculate how many assignments this will create
  const matchingDates = useMemo(() => {
    return dates.filter(iso => {
      const d = new Date(`${iso}T00:00:00Z`)
      const dow = d.getUTCDay()
      // Convert JS day (0=Sun) to our format (0=Mon)
      const adjusted = dow === 0 ? 6 : dow - 1
      return selectedDays.includes(adjusted)
    })
  }, [dates, selectedDays])

  const totalAssignments = selectedStaffIds.length * matchingDates.length

  async function handleCreate() {
    if (!shiftType || selectedStaffIds.length === 0 || matchingDates.length === 0) return
    setBusy(true)
    // In production this would call the API for each assignment
    // For now we simulate the batch operation
    onBatchCreated(totalAssignments)
    setBusy(false)
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-[min(96vw,700px)] max-w-none rounded-2xl max-h-[90vh] overflow-hidden p-0">
        <div className="flex flex-col max-h-[90vh]">
          <DialogHeader className="px-6 pt-6 pb-3 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0" style={{ background: '#fce8f3' }}>📋</div>
              <div>
                <DialogTitle className="text-lg font-bold">{L.title}</DialogTitle>
                <p className="text-xs font-semibold mt-0.5" style={{ color: PINK }}>{L.subtitle}</p>
              </div>
            </div>
          </DialogHeader>

          <div className="px-6 py-4 overflow-y-auto space-y-4">
            {/* Shift type selection */}
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.selectShift}</label>
              <Select value={shiftType} onValueChange={setShiftType}>
                <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200">
                  <SelectValue placeholder={L.selectShift} />
                </SelectTrigger>
                <SelectContent>
                  {shiftDefs.filter(sd => sd.is_working).map(sd => (
                    <SelectItem key={sd.id} value={sd.shift_type}>
                      {sd.shift_type}{sd.label ? ` · ${sd.label}` : ''} ({sd.start_time?.slice(0,5) || '?'}-{sd.end_time?.slice(0,5) || '?'})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Day selection */}
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.selectDays}</label>
              <div className="flex gap-2 mt-1.5">
                {weekdays.map((day, i) => (
                  <button key={i} type="button" onClick={() => toggleDay(i)}
                    className="w-9 h-9 rounded-lg text-xs font-bold border transition-all"
                    style={{
                      background: selectedDays.includes(i) ? PINK : '#fff',
                      color: selectedDays.includes(i) ? '#fff' : '#6b7280',
                      borderColor: selectedDays.includes(i) ? PINK : '#e5e7eb',
                    }}>
                    {day}
                  </button>
                ))}
              </div>
            </div>

            {/* Staff selection */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">{L.selectStaff}</label>
                <div className="flex items-center gap-2">
                  <select value={rankFilter} onChange={e => setRankFilter(e.target.value)}
                    className="text-[10px] px-2 py-1 border border-gray-200 rounded-lg bg-white">
                    {ranks.map(r => <option key={r} value={r}>{r === 'ALL' ? L.allRanks : r}</option>)}
                  </select>
                  <button type="button" onClick={selectAllFiltered}
                    className="text-[10px] font-semibold" style={{ color: PINK }}>
                    {isZH ? '全選/取消' : 'Toggle All'}
                  </button>
                </div>
              </div>
              <div className="max-h-48 overflow-y-auto border border-gray-200 rounded-xl p-2 space-y-1">
                {filteredStaff.map(s => (
                  <label key={s.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input type="checkbox" checked={selectedStaffIds.includes(s.id)}
                      onChange={() => toggleStaff(s.id)} className="rounded border-gray-300" />
                    <span className="text-xs font-medium">{s.name_en || s.name}</span>
                    <span className="text-[10px] text-gray-400">({s.rank})</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Preview */}
            {totalAssignments > 0 && (
              <div className="rounded-xl p-3 text-center" style={{ background: '#fce8f3' }}>
                <div className="text-sm font-bold" style={{ color: PINK }}>
                  {L.preview}: {totalAssignments}{L.assignments}
                </div>
                <div className="text-[10px] text-gray-500 mt-1">
                  {selectedStaffIds.length} {isZH ? '名員工' : 'staff'} × {matchingDates.length} {isZH ? '日' : 'days'}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
            <Button variant="outline" onClick={onClose} className="rounded-xl text-xs">{L.cancel}</Button>
            <Button onClick={handleCreate} disabled={busy || !shiftType || totalAssignments === 0}
              className="rounded-xl text-xs text-white" style={{ background: PINK }}>
              {busy ? '…' : `${L.create} (${totalAssignments})`}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
