'use client'
import { useState } from 'react'
import { STAFF, ROSTER, DAYS } from '@/lib/data'
import { KPIStrip } from '@/components/roster/KPIStrip'
import { StaffCell } from '@/components/roster/StaffCell'
import { ShiftCell } from '@/components/roster/ShiftCell'
import { CreateShiftModal } from '@/components/modals/CreateShiftModal'
import { CreateEventModal } from '@/components/modals/CreateEventModal'


export default function RosterPage() {
  const [view, setView] = useState<'week' | 'month'>('week')
  const [shiftOpen, setShiftOpen] = useState(false)
  const [eventOpen, setEventOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [weekOffset, setWeekOffset] = useState(0)


  const handleAI = () => {
    setAiLoading(true)
    setTimeout(() => setAiLoading(false), 1800)
  }


  const baseDate = new Date(2026, 2, 23)
  baseDate.setDate(baseDate.getDate() + weekOffset * 7)
  const endDate = new Date(baseDate)
  endDate.setDate(endDate.getDate() + 6)
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  const dateLabel = `${months[baseDate.getMonth()]} ${baseDate.getDate()} — ${months[endDate.getMonth()]} ${endDate.getDate()}, ${endDate.getFullYear()}`


  return (
    <div className="flex flex-col h-full overflow-hidden">


      {/* Toolbar */}
      <div className="bg-white border-b border-gray-200 px-5 py-3 flex-shrink-0 space-y-2.5">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-900">Weekly Roster 更表</h1>
          <button className="flex items-center gap-2 px-3 py-1.5 border border-gray-200 rounded-lg text-[13px] font-medium hover:bg-gray-50">
            🏠 Haven Elderly Home
            <span className="text-gray-400 text-xs">▾</span>
          </button>
          <div className="ml-auto flex items-center gap-2.5">
            <div className="flex border border-gray-200 rounded-lg overflow-hidden">
              {(['week','month'] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className="px-3.5 py-1.5 text-xs font-medium transition-all capitalize"
                  style={{ background: view === v ? '#1a1a2e' : '#fff', color: view === v ? '#fff' : '#6b7280' }}
                >
                  {v === 'week' ? 'Week' : 'Month'}
                </button>
              ))}
            </div>
            <button
              onClick={handleAI}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-white text-xs font-semibold rounded-lg transition-colors"
              style={{ background: aiLoading ? '#c8156a' : '#E8187A' }}
            >
              {aiLoading ? '✦ 計算中...' : '✦ AI排更建議'}
            </button>
          </div>
        </div>


        <div className="flex items-center gap-2">
          <button onClick={() => setWeekOffset(o => o - 1)} className="w-7 h-7 rounded-md border border-gray-200 flex items-center justify-center text-gray-500 hover:bg-gray-50 text-sm">‹</button>
          <div className="flex items-center gap-2 px-3 py-1.5 border border-gray-200 rounded-lg bg-white">
            <span className="text-[13px] font-semibold text-gray-900">{dateLabel}</span>
            <span className="text-gray-400">📅</span>
          </div>
          <button onClick={() => setWeekOffset(o => o + 1)} className="w-7 h-7 rounded-md border border-gray-200 flex items-center justify-center text-gray-500 hover:bg-gray-50 text-sm">›</button>


          <div className="ml-auto flex gap-2">
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-pink-200 rounded-lg text-pink-600 hover:bg-pink-50 transition-colors">
              ⬇ Download Schedule
            </button>
            <button
              onClick={() => setShiftOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              ＋ Create Shift
            </button>
            <button
              onClick={() => setEventOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              ✦ Create Special Event
            </button>
            <button
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white rounded-lg transition-colors"
              style={{ background: '#E8187A' }}
              onMouseEnter={e => (e.currentTarget.style.background='#c8156a')}
              onMouseLeave={e => (e.currentTarget.style.background='#E8187A')}
            >
              ✓ Publish Change
            </button>
          </div>
        </div>
      </div>


      {/* Shift legend */}
      <div className="flex items-center gap-5 px-5 py-2 bg-white border-b border-gray-200 flex-shrink-0">
        {[
          {color:'#3b82f6',label:'A SHIFT (07:00–15:00)'},
          {color:'#10b981',label:'P SHIFT (15:00–23:00)'},
          {color:'#8b5cf6',label:'N SHIFT (23:00–07:00)'},
        ].map(({color,label}) => (
          <div key={label} className="flex items-center gap-1.5 text-[10px] text-gray-500">
            <div className="w-2 h-2 rounded-full" style={{background:color}}/>
            {label}
          </div>
        ))}
      </div>


      {/* KPI Strip */}
      <KPIStrip />


      {/* Table */}
      <div className="flex-1 overflow-auto px-5 py-3">
        {view === 'week' ? (
          <table className="w-full border-collapse bg-white rounded-xl border border-gray-200" style={{borderRadius:'12px',overflow:'hidden'}}>
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-3.5 py-2.5 text-[10px] font-semibold text-gray-500 border-r border-gray-200 w-52">STAFF MEMBER</th>
                {DAYS.map((d, i) => (
                  <th key={d} className="px-2 py-2.5 text-center border-r border-gray-100 last:border-r-0 min-w-24">
                    <div className="text-[9px] text-gray-400 tracking-wide">{d.split(' ')[0]}</div>
                    <div className={`text-[15px] font-bold ${i === 3 ? 'text-pink-600' : 'text-gray-800'}`}>{d.split(' ')[1]}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROSTER.map(row => {
                const staff = STAFF.find(s => s.id === row.staffId)!
                return (
                  <tr key={row.staffId} className="border-t border-gray-100 hover:bg-pink-50/30 transition-colors">
                    <StaffCell staff={staff} />
                    {row.days.map((shift, idx) => <ShiftCell key={idx} shift={shift} />)}
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div className="overflow-x-auto">
            <table className="border-collapse bg-white rounded-xl border border-gray-200 text-[10px]" style={{minWidth:'1100px'}}>
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-3 py-2 text-[9px] font-semibold text-gray-500 border-r border-gray-200 w-36">員工</th>
                  {Array.from({length:31},(_,i) => (
                    <th key={i} className="px-0.5 py-2 text-[9px] text-gray-400 text-center border-r border-gray-100 w-8">{i+1}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {STAFF.map(s => {
                  const shiftTypes = ['A','P','N','R','R','A','P','P','N','A','R','P','A','N','R','A','P','A','N','R','A','P','N','A','R','P','A','N','R','A','P']
                  return (
                    <tr key={s.id} className="border-t border-gray-100 hover:bg-pink-50/20">
                      <td className="px-2.5 py-1.5 border-r border-gray-200 bg-gray-50">
                        <div className="font-semibold text-gray-900 truncate">{s.nameEn.split(' ').slice(-1)[0]}</div>
                        <div className="text-gray-400 text-[8px]">{s.role} · {s.floor}</div>
                      </td>
                      {shiftTypes.map((t,i) => {
                        const cfg:{[k:string]:{bg:string,color:string}} = {
                          A:{bg:'#eff6ff',color:'#1d4ed8'},
                          P:{bg:'#f0fdf4',color:'#15803d'},
                          N:{bg:'#faf5ff',color:'#7e22ce'},
                          R:{bg:'#f9fafb',color:'#9ca3af'},
                        }
                        const c = cfg[t] || cfg.R
                        return (
                          <td key={i} className="px-0.5 py-1 text-center border-r border-gray-50">
                            <span className="inline-block w-4 h-4 rounded text-[8px] font-bold leading-4 text-center" style={{background:c.bg,color:c.color}}>{t}</span>
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>


       {/* Modals */}
      <CreateShiftModal open={shiftOpen} onClose={() => setShiftOpen(false)} />
      <CreateEventModal open={eventOpen} onClose={() => setEventOpen(false)} />
    </div>
  )
}