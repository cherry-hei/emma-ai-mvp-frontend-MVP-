'use client'

import { useMemo, useState } from 'react'
import { STAFF } from '@/lib/data'

type StaffType = (typeof STAFF)[number]

const ROLE_OPTIONS = ['ALL', 'RN', 'EN', 'HW', 'CW', 'PTA', 'PCW', 'AW'] as const

const STATUS: Record<number, { label: string; color: string; bg: string }> = {
  1: { label: 'On Shift', color: '#1d4ed8', bg: '#eff6ff' },
  2: { label: 'Available', color: '#15803d', bg: '#f0fdf4' },
  3: { label: 'On Shift', color: '#1d4ed8', bg: '#eff6ff' },
  4: { label: 'Off Duty', color: '#6b7280', bg: '#f9fafb' },
  5: { label: 'Available', color: '#15803d', bg: '#f0fdf4' },
  6: { label: 'Sick Leave', color: '#be123c', bg: '#fff1f2' },
  7: { label: 'On Shift', color: '#1d4ed8', bg: '#eff6ff' },
}

const SKILLS: Record<number, string[]> = {
  1: ['ACLS', 'Triage', 'BLS', 'Emergency'],
  2: ['First Aid', 'Manual Hand.', 'Wound Care'],
  3: ['Elder Care', 'Vitals', 'AOM'],
  4: ['Personal Care', 'Oral Feeding'],
  5: ['Rehab Tech', 'Physio Support'],
  6: ['Bathing', 'Transfer', 'Night Care'],
  7: ['Infection Ctrl', 'Facility-wide'],
}

const EXTRA: Record<number, { proximity: string; experience: string; weeklyH: string; compatibility: number }> = {
  1: { proximity: '0.8km', experience: '6.0 Years', weeklyH: '40h / 44h', compatibility: 95 },
  2: { proximity: '2.1km', experience: '3.5 Years', weeklyH: '30h / 44h', compatibility: 84 },
  3: { proximity: '1.5km', experience: '5.0 Years', weeklyH: '37h / 44h', compatibility: 91 },
  4: { proximity: '3.2km', experience: '2.0 Years', weeklyH: '24h / 44h', compatibility: 72 },
  5: { proximity: '1.0km', experience: '4.5 Years', weeklyH: '32h / 44h', compatibility: 88 },
  6: { proximity: '0.5km', experience: '7.0 Years', weeklyH: '33h / 44h', compatibility: 79 },
  7: { proximity: '1.2km', experience: '8.5 Years', weeklyH: '40h / 44h', compatibility: 98 },
}

const SHIFT_HISTORY = [
  { date: '2026-03-20', shift: 'AM Shift', time: '09:00 - 17:00', ward: 'Ward A', resident: 'Lee K.F.' },
  { date: '2026-03-18', shift: 'PM Shift', time: '14:00 - 22:00', ward: 'Ward B', resident: 'Cheung M.H.' },
  { date: '2026-03-15', shift: 'Night Shift', time: '22:00 - 07:00', ward: 'Ward A', resident: 'Wong S.L.' },
]

const AVATARS = ['🧑‍⚕️', '👩‍⚕️', '👨‍⚕️', '👩‍⚕️', '🧑‍⚕️', '👩‍⚕️', '👨‍⚕️']
const PINK = '#f28f9e'

function ProfileModal({
  staff,
  idx,
  onClose,
}: {
  staff: StaffType
  idx: number
  onClose: () => void
}) {
  const [tab, setTab] = useState<'ai' | 'history'>('history')
  const extra = EXTRA[staff.id]
  const pct = Math.round((staff.hoursWorked / staff.hoursTotal) * 100)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-2xl rounded-[2.5rem] overflow-hidden shadow-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="relative h-48 flex-shrink-0"
          style={{ background: 'linear-gradient(135deg, #fce8f3 0%, #eff6ff 100%)' }}
        >
          <button
            onClick={onClose}
            className="absolute top-5 right-5 p-2 bg-white/60 hover:bg-white rounded-full transition-colors z-10 text-gray-600 font-bold w-9 h-9 flex items-center justify-center"
          >
            ✕
          </button>

          <div className="absolute -bottom-16 left-10">
            <div className="relative">
              <div className="w-32 h-32 rounded-[2rem] border-8 border-white bg-pink-50 flex items-center justify-center text-5xl shadow-lg">
                {AVATARS[idx]}
              </div>
              <div className="absolute -bottom-2 -right-2 w-10 h-10 rounded-full bg-emerald-500 flex items-center justify-center border-4 border-white shadow-md text-white text-sm">
                ✓
              </div>
            </div>
          </div>
        </div>

        <div className="pt-20 px-10 pb-6 overflow-y-auto flex-1">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h2 className="text-2xl font-extrabold text-gray-900">{staff.nameEn}</h2>
              <div className="text-sm text-gray-500 mt-0.5">{staff.name}</div>
              <div className="flex items-center gap-3 mt-2">
                <span
                  className="text-xs font-bold px-3 py-1 rounded-full text-white uppercase tracking-wider"
                  style={{ background: PINK }}
                >
                  {staff.role}
                </span>
                <span className="text-sm text-gray-500 font-medium">ID: #NGO-{1000 + staff.id * 317}</span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-3xl font-black" style={{ color: '#10b981' }}>
                {extra.compatibility}%
              </div>
              <div className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Compatibility</div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-6">
            {[
              { label: 'Weekly Load', value: extra.weeklyH },
              { label: 'Proximity', value: extra.proximity },
              { label: 'Experience', value: extra.experience },
            ].map((s) => (
              <div key={s.label} className="bg-gray-50 p-4 rounded-2xl">
                <div className="text-[10px] font-bold text-gray-400 uppercase mb-1">{s.label}</div>
                <div className="text-lg font-bold text-gray-900">{s.value}</div>
              </div>
            ))}
          </div>

          <div className="mb-6 bg-gray-50 p-4 rounded-2xl">
            <div className="flex justify-between text-xs text-gray-500 mb-2">
              <span>Hours This Month</span>
              <span className="font-bold" style={{ color: PINK }}>
                {staff.hoursWorked}h / {staff.hoursTotal}h
              </span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${pct}%`,
                  background: pct >= 100 ? '#dc2626' : pct >= 90 ? '#d97706' : PINK,
                }}
              />
            </div>
          </div>

          <div className="flex gap-6 border-b border-gray-100 mb-5">
            {[
              { key: 'ai', label: 'AI Analysis' },
              { key: 'history', label: 'Shift History' },
            ].map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key as 'ai' | 'history')}
                className="pb-3 text-sm font-bold transition-all relative"
                style={{ color: tab === t.key ? PINK : '#9ca3af' }}
              >
                {t.label}
                {tab === t.key && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full" style={{ background: PINK }} />
                )}
              </button>
            ))}
          </div>

          {tab === 'history' ? (
            <div className="space-y-3">
              {SHIFT_HISTORY.map((s, i) => (
                <div key={i} className="bg-gray-50 p-5 rounded-3xl border border-gray-100 hover:border-pink-200 transition-all">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center shadow-sm text-lg">
                        📅
                      </div>
                      <div>
                        <div className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{s.date}</div>
                        <div className="text-sm font-bold text-gray-900">{s.shift}</div>
                      </div>
                    </div>
                    <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-100">
                      COMPLETED
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-xs text-gray-600">
                    <div>🕐 {s.time}</div>
                    <div>📍 {s.ward}</div>
                    <div>👥 {s.resident}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="text-[9px] font-bold text-gray-400 uppercase tracking-widest mb-2">
                  Verified Credentials
                </div>
                <div className="flex gap-2 flex-wrap">
                  {['ALS', 'Wound Care', 'Team Leader', 'Advanced Life Support'].map((c) => (
                    <span key={c} className="text-[10px] font-bold px-2.5 py-1 rounded-lg bg-gray-50 border border-gray-200 text-gray-600">
                      {c}
                    </span>
                  ))}
                </div>
              </div>

              <div className="p-3 rounded-2xl flex items-center gap-3" style={{ background: '#1a1a2e' }}>
                <div className="text-xl">🧠</div>
                <div>
                  <div className="text-xs font-bold text-white">AI Skill Analysis</div>
                  <div className="text-[10px] text-gray-400">Implicit & Explicit Insights · EMMA AI V2.1</div>
                </div>
                <span className="ml-auto text-[9px] font-bold px-2 py-0.5 rounded text-white" style={{ background: PINK }}>
                  SKILL RADAR
                </span>
              </div>

              <div>
                <div className="flex gap-1.5 mb-2">
                  <span className="text-[9px] font-bold px-2 py-0.5 rounded text-white" style={{ background: PINK }}>
                    EXPLICIT
                  </span>
                  <span className="text-[9px] font-bold px-2 py-0.5 rounded bg-purple-600 text-white">
                    IMPLICIT
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {['Critical Care', 'Team Leadership', 'Emergency Response', 'Wound Care', 'Patient Comm'].map((s) => (
                    <span
                      key={s}
                      className="text-[10px] px-2.5 py-1 rounded-full border font-medium"
                      style={{ borderColor: 'rgba(232,24,122,.3)', color: PINK, background: '#fef6fb' }}
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>

              <div className="bg-gray-50 p-4 rounded-2xl">
                <div className="flex items-center justify-between mb-3">
                  <div className="text-xs font-bold text-gray-700">Skill Progression (Q1)</div>
                  <span className="text-[9px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                    ↑ TRENDING UP
                  </span>
                </div>
                {[
                  { skill: 'Critical Care', explicit: 85, implicit: 92 },
                  { skill: 'Team Leadership', explicit: 70, implicit: 88 },
                  { skill: 'Emergency Response', explicit: 90, implicit: 94 },
                ].map((s) => (
                  <div key={s.skill} className="mb-3">
                    <div className="flex justify-between text-[10px] mb-1">
                      <span className="font-semibold text-gray-700">{s.skill}</span>
                      <span className="text-gray-400">
                        Explicit: {s.explicit}% · Implicit: {s.implicit}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden mb-0.5">
                      <div className="h-full rounded-full" style={{ width: `${s.explicit}%`, background: PINK }} />
                    </div>
                    <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div className="h-full rounded-full bg-purple-500" style={{ width: `${s.implicit}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-red-50 border border-red-100 p-3 rounded-2xl">
                  <div className="text-[9px] font-bold text-red-400 uppercase tracking-widest mb-2">
                    Critical Skill Gaps
                  </div>
                  {['Advanced Pediatric Life Support', 'Digital Health Records (V2)'].map((g) => (
                    <div key={g} className="text-[10px] text-red-600 flex items-start gap-1 mb-1">
                      <span>⚠</span>
                      {g}
                    </div>
                  ))}
                </div>
                <div className="bg-emerald-50 border border-emerald-100 p-3 rounded-2xl">
                  <div className="text-[9px] font-bold text-emerald-600 uppercase tracking-widest mb-2">
                    Recommended Training
                  </div>
                  {['Leadership Mentorship (Level 2)', 'Specialized Wound Care Cert'].map((t) => (
                    <div key={t} className="text-[10px] text-emerald-700 flex items-start gap-1 mb-1">
                      <span>✓</span>
                      {t}
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="flex items-center gap-2 mb-2">
                  <div className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">
                    Implicit Skill Derivation
                  </div>
                  <span className="text-[9px] font-bold px-2 py-0.5 rounded text-white bg-purple-600">
                    AI DERIVED
                  </span>
                </div>
                {[
                  { date: '03/15', title: 'Cardiac Arrest Response', desc: 'Successful Resuscitation', skill: 'Crisis Leadership' },
                  { date: '02/28', title: 'Ward B Overflow Management', desc: 'Maintained 1:8 Ratio', skill: 'Resource Optimization' },
                ].map((e) => (
                  <div key={e.date} className="flex gap-3 p-3 bg-gray-50 rounded-2xl border border-gray-100 mb-2">
                    <div className="text-[10px] font-bold w-8 text-gray-400 flex-shrink-0">{e.date}</div>
                    <div className="flex-1">
                      <div className="text-xs font-bold text-gray-800">{e.title}</div>
                      <div className="text-[10px] text-gray-500">{e.desc}</div>
                      <div className="text-[9px] font-bold mt-1" style={{ color: PINK }}>
                        Skill Gained: {e.skill}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="px-10 py-5 border-t border-gray-100 flex gap-3 flex-shrink-0">
          <button
            className="flex-1 py-3.5 text-white font-bold rounded-2xl shadow-lg transition-transform hover:scale-[1.02]"
            style={{ background: PINK }}
          >
            Confirm Assignment
          </button>
          <button className="px-8 py-3.5 bg-gray-100 text-gray-600 font-bold rounded-2xl hover:bg-gray-200 transition-colors">
            Contact Staff
          </button>
        </div>
      </div>
    </div>
  )
}

export default function StaffPage() {
  const [search, setSearch] = useState('')
  const [filterRole, setFilterRole] = useState<(typeof ROLE_OPTIONS)[number]>('ALL')
  const [selected, setSelected] = useState<{ staff: StaffType; idx: number } | null>(null)

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return STAFF.filter((s) => {
      const matchSearch = s.nameEn.toLowerCase().includes(q) || s.name.includes(search)
      const matchRole = filterRole === 'ALL' || s.role === filterRole
      return matchSearch && matchRole
    })
  }, [search, filterRole])

  return (
    <div className="p-5 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Staff Directory 員工目錄</h1>
          <p className="text-xs text-gray-500 mt-0.5">{STAFF.length} staff members · Haven Elderly Home</p>
        </div>
        <button className="px-4 py-2 text-white text-xs font-semibold rounded-xl" style={{ background: PINK }}>
          ＋ Add Staff
        </button>
      </div>

      <div className="flex gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="🔍 Search staff..."
          className="flex-1 px-4 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50 outline-none focus:border-pink-400"
        />
        <div className="flex gap-1.5 flex-wrap">
          {ROLE_OPTIONS.map((r) => (
            <button
              key={r}
              onClick={() => setFilterRole(r)}
              className="px-3 py-2 text-xs font-bold rounded-xl border transition-all"
              style={{
                background: filterRole === r ? PINK : '#fff',
                color: filterRole === r ? '#fff' : '#6b7280',
                borderColor: filterRole === r ? PINK : '#e5e7eb',
              }}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((s, i) => {
          const pct = Math.round((s.hoursWorked / s.hoursTotal) * 100)
          const status = STATUS[s.id]
          return (
            <div key={s.id} className="bg-white p-5 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-all group">
              <div className="flex items-start gap-3 mb-4">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl bg-pink-50 border border-pink-100 flex-shrink-0 group-hover:scale-105 transition-transform">
                  {AVATARS[i]}
                </div>
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900 text-sm group-hover:text-pink-600 transition-colors mb-1">
                    {s.nameEn}
                  </h3>
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider text-white" style={{ background: PINK }}>
                      {s.role}
                    </span>
                    <span
                      className="text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider"
                      style={{ color: status.color, background: status.bg }}
                    >
                      {status.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${pct}%`,
                          background: pct >= 100 ? '#dc2626' : pct >= 90 ? '#d97706' : PINK,
                        }}
                      />
                    </div>
                    <span className="text-[10px] font-black" style={{ color: PINK }}>
                      {pct}%
                    </span>
                  </div>
                </div>
              </div>

              <div className="text-[10px] text-gray-400 mb-3">
                📍 {s.ward} · {s.floor}
              </div>

              <div>
                <div className="text-[9px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">Skills</div>
                <div className="flex flex-wrap gap-1">
                  {(SKILLS[s.id] || []).map((sk) => (
                    <span key={sk} className="text-[10px] font-semibold text-gray-600 bg-gray-50 px-2 py-0.5 rounded-lg border border-gray-100">
                      {sk}
                    </span>
                  ))}
                </div>
              </div>

              <div className="pt-3 mt-3 border-t border-gray-50 flex justify-between items-center">
                <button onClick={() => setSelected({ staff: s, idx: i })} className="text-xs font-bold hover:underline" style={{ color: PINK }}>
                  View Profile →
                </button>
                <button className="p-2 bg-gray-50 rounded-xl text-gray-400 hover:text-pink-600 hover:bg-pink-50 transition-all">
                  💬
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {selected && <ProfileModal staff={selected.staff} idx={selected.idx} onClose={() => setSelected(null)} />}
    </div>
  )
}