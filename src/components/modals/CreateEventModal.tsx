'use client'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useState } from 'react'
import { STAFF } from '@/lib/data'

export function CreateEventModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [eventType, setEventType] = useState('leave')

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg rounded-2xl">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl" style={{background:'#fce8f3'}}>📅</div>
            <div>
              <DialogTitle className="text-lg font-bold">Create Special Event</DialogTitle>
              <p className="text-xs font-semibold mt-0.5" style={{color:'#f28f9e'}}>LEAVE & TRAINING</p>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">員工 Staff</label>
            <select className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400">
              {STAFF.map(s => (
                <option key={s.id}>{s.name} ({s.role}) — {s.ward}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">事件類型 Event Type</label>
            <div className="mt-1.5 grid grid-cols-3 gap-2">
              {[
                {value:'leave',     label:'年假',  icon:'🌴'},
                {value:'sick',      label:'病假',  icon:'🏥'},
                {value:'training',  label:'培訓',  icon:'📚'},
                {value:'meeting',   label:'會議',  icon:'💼'},
                {value:'emergency', label:'緊急',  icon:'🚨'},
                {value:'other',     label:'其他',  icon:'📌'},
              ].map(t => (
                <button
                  key={t.value}
                  onClick={() => setEventType(t.value)}
                  className="py-2 rounded-xl text-xs font-medium border transition-all"
                  style={{
                    background:   eventType === t.value ? '#fce8f3' : '#F9FAFB',
                    color:        eventType === t.value ? '#f28f9e' : '#6B7280',
                    borderColor:  eventType === t.value ? '#f28f9e' : '#E5E7EB',
                  }}
                >
                  {t.icon} {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">開始日期</label>
              <input type="date" className="mt-1.5 w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400" />
            </div>
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">結束日期</label>
              <input type="date" className="mt-1.5 w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400" />
            </div>
          </div>

          <div>
            <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">備註 Note</label>
            <textarea
              className="mt-1.5 w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400 resize-none"
              rows={2}
              placeholder="額外備註..."
            />
          </div>
        </div>

        <div className="flex gap-2 justify-end mt-5 pt-4 border-t border-gray-100">
          <Button variant="outline" onClick={onClose} className="rounded-xl text-xs">CANCEL</Button>
          <Button onClick={onClose} className="rounded-xl text-xs text-white" style={{background:'#f28f9e'}}>CONFIRM</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}