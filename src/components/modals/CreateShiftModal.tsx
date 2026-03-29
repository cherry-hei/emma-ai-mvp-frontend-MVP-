'use client'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useState } from 'react'

export function CreateShiftModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [aiToggle, setAiToggle] = useState(true)

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg rounded-2xl">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl" style={{background:'#fce8f3'}}>✦</div>
            <div>
              <DialogTitle className="text-lg font-bold">Create Shift &amp; Assignment</DialogTitle>
              <p className="text-xs font-semibold mt-0.5" style={{color:'#f28f9e'}}>AI POWERED ADJUSTMENT</p>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">Date Selection</label>
            <input type="date" defaultValue="2026-03-19" className="mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">Select Position</label>
              <Select defaultValue="rn-senior">
                <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="rn-senior">Registered Nurse (Senior)</SelectItem>
                  <SelectItem value="en">Enrolled Nurse</SelectItem>
                  <SelectItem value="hw">Health Worker</SelectItem>
                  <SelectItem value="pcw">Personal Care Worker</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">Assign Employee</label>
              <Select defaultValue="yu">
                <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="yu">👩 Yu Yat Sze (RN)</SelectItem>
                  <SelectItem value="leung">👩 Leung Ka Kei (EN)</SelectItem>
                  <SelectItem value="chan">👨 Chan S.M. (RN)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">Time Frame</label>
              <div className="flex items-center gap-2 mt-1.5">
                <input type="time" defaultValue="07:00" className="flex-1 px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none" />
                <span className="text-xs text-gray-400">to</span>
                <input type="time" defaultValue="15:00" className="flex-1 px-3 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none" />
              </div>
            </div>
            <div>
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">Shift Category</label>
              <Select defaultValue="morning">
                <SelectTrigger className="mt-1.5 rounded-xl bg-gray-50 border-gray-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="morning">Morning Regular</SelectItem>
                  <SelectItem value="afternoon">Afternoon Regular</SelectItem>
                  <SelectItem value="night">Night Regular</SelectItem>
                  <SelectItem value="emergency">Emergency Cover</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Tasks */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">Task Schedule</label>
              <span className="text-[9px] font-bold px-2 py-0.5 rounded" style={{background:'#fce8f3',color:'#f28f9e'}}>RN SPECIFIC TASKS</span>
            </div>
            {[
              {time:'07:00–09:00', task:'Medication Checking'},
              {time:'09:00–11:00', task:'Audit & Documentation'},
            ].map(({time, task}) => (
              <div key={time} className="flex items-center gap-3 p-3 border border-gray-200 rounded-xl mb-2 bg-gray-50">
                <span className="text-xs font-semibold w-24 flex-shrink-0" style={{color:'#f28f9e'}}>{time}</span>
                <span className="text-sm flex-1">{task}</span>
                <span className="text-gray-400 cursor-pointer">▾</span>
                <span className="text-red-400 cursor-pointer text-xs">🗑</span>
              </div>
            ))}
          </div>

          {/* AI toggle */}
          <div className="flex items-center gap-3 p-3 rounded-xl" style={{background:'#fce8f3'}}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm" style={{background:'#f28f9e'}}>🧠</div>
            <div className="flex-1">
              <div className="text-sm font-semibold">Emma AI Task Optimisation</div>
              <div className="text-[10px] text-gray-500 mt-0.5">Auto-distribute tasks based on staff competency</div>
            </div>
            <button
              onClick={() => setAiToggle(!aiToggle)}
              className="w-10 h-6 rounded-full transition-all relative"
              style={{background: aiToggle ? '#f28f9e' : '#d1d5db'}}
            >
              <span className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all" style={{left: aiToggle ? '20px' : '4px'}}/>
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between mt-5 pt-4 border-t border-gray-100">
          <button className="text-red-500 text-xs font-semibold flex items-center gap-1">🗑 DELETE SHIFT</button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} className="rounded-xl text-xs">CANCEL</Button>
            <Button onClick={onClose} className="rounded-xl text-xs text-white" style={{background:'#f28f9e'}}>SAVE CHANGES</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}