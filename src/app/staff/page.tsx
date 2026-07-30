'use client'

import { useEffect, useMemo, useState } from 'react'
import type { Staff } from '@/lib/types'
import { api } from '@/lib/api'
import type { ApiStaff, StaffAiAnalysis, StaffDetail } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

// UI staff = demo shape + optional links to the real API record.
type StaffType = Staff & { apiId?: string; apiStatus?: string }

// Map a backend /staff row to the card shape using REAL fields: certs, rostered
// hours (scheduled vs contracted-for-period), unit, and derived status. id is the
// 1-based index so the demo AVATARS/EXTRA maps still line up as a visual fallback.
function mapApiStaff(rows: ApiStaff[]): StaffType[] {
  return rows.map((s, i) => ({
    id: i + 1,
    apiId: s.id,
    apiStatus: s.status || undefined,
    name: s.name,
    nameEn: s.name_en || s.name,
    role: s.rank,
    ward: s.unit_name || '-',
    floor: '-',
    certs: s.certs ?? [],
    hoursWorked: Math.round(s.scheduled_hours ?? 0),
    hoursTotal: Math.round(s.contracted_period_hours || 160),
    avatar: (s.name_en || s.name).charAt(0),
  }))
}

const API_STATUS: Record<string, { labelZH: string; labelEN: string; color: string; bg: string }> = {
  scheduled: { labelZH: '已排更', labelEN: 'Scheduled', color: '#1d4ed8', bg: '#eff6ff' },
  on_leave:  { labelZH: '休假',   labelEN: 'On Leave',  color: '#be123c', bg: '#fff1f2' },
  available: { labelZH: '可調配', labelEN: 'Available', color: '#15803d', bg: '#f0fdf4' },
}
const DEFAULT_STATUS = { labelZH: '可調配', labelEN: 'Available', color: '#15803d', bg: '#f0fdf4' }

const STATUS: Record<number, { labelZH: string; labelEN: string; color: string; bg: string }> = {
  1: { labelZH: '當值中', labelEN: 'On Shift',   color: '#1d4ed8', bg: '#eff6ff' },
  2: { labelZH: '可調配', labelEN: 'Available',  color: '#15803d', bg: '#f0fdf4' },
  3: { labelZH: '當值中', labelEN: 'On Shift',   color: '#1d4ed8', bg: '#eff6ff' },
  4: { labelZH: '休息',   labelEN: 'Off Duty',   color: '#6b7280', bg: '#f9fafb' },
  5: { labelZH: '可調配', labelEN: 'Available',  color: '#15803d', bg: '#f0fdf4' },
  6: { labelZH: '病假',   labelEN: 'Sick Leave', color: '#be123c', bg: '#fff1f2' },
  7: { labelZH: '當值中', labelEN: 'On Shift',   color: '#1d4ed8', bg: '#eff6ff' },
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

const AVATARS = ['🧑‍⚕️', '👩‍⚕️', '👨‍⚕️', '👩‍⚕️', '🧑‍⚕️', '👩‍⚕️', '👨‍⚕️']
const PINK = '#f28f9e'

function ProfileModal({ staff, idx, onClose }: { staff: StaffType; idx: number; onClose: () => void }) {
  const { lang } = useLang()
  const isZH = lang === 'zh'
  const [tab, setTab] = useState<'ai' | 'history'>('history')
  const [detail, setDetail] = useState<StaffDetail | null>(null)
  const [analysis, setAnalysis] = useState<StaffAiAnalysis | null>(null)
  const [analysisError, setAnalysisError] = useState('')

  useEffect(() => {
    if (!staff.apiId) return
    let cancelled = false
    api.staffDetail(staff.apiId).then(d => { if (!cancelled) setDetail(d) }).catch(() => {})
    api.staffAiAnalysis(staff.apiId)
      .then(a => { if (!cancelled) setAnalysis(a) })
      .catch(e => { if (!cancelled) setAnalysisError(e instanceof Error ? e.message : 'Analysis unavailable') })
    return () => { cancelled = true }
  }, [staff.apiId])

  const pct = staff.hoursTotal ? Math.round((staff.hoursWorked / staff.hoursTotal) * 100) : 0

  // Real rostered shift history from the API (empty until the roster is loaded).
  const SHIFT_HISTORY = (detail?.shift_history ?? []).map(h => ({
    date: h.date,
    shift: h.shift_type ?? '-',
    time: h.start_time && h.end_time ? `${h.start_time} - ${h.end_time}` : '-',
    ward: staff.ward,
    resident: h.tasks?.[0] ?? '-',
  }))

  const L = {
    covers:         isZH ? '緊急補更'        : 'Emergency Covers',
    weekly_load:    isZH ? '本週期時數'      : 'Period Load',
    night_shifts:   isZH ? '夜更次數'        : 'Night Shifts',
    units:          isZH ? '服務單位數'      : 'Units Worked',
    hours_month:    isZH ? '本週期工時'      : 'Hours This Period',
    tab_history:    isZH ? '更表紀錄'        : 'Shift History',
    tab_ai:         isZH ? 'AI 分析'         : 'AI Analysis',
    completed:      isZH ? '已完成'          : 'COMPLETED',
    credentials:    isZH ? '認可資歷'        : 'Verified Credentials',
    ai_skill:       isZH ? 'AI 技能分析'     : 'AI Skill Analysis',
    skill_prog:     isZH ? '技能證據對比'    : 'Evidence by Skill',
    evidence:       isZH ? '證據來源'        : 'EVIDENCE-BACKED',
    gaps:           isZH ? '技能缺口'        : 'Critical Skill Gaps',
    training:       isZH ? '建議培訓'        : 'Recommended Training',
    implicit_title: isZH ? 'AI 隱性技能分析' : 'Implicit Skill Derivation',
    skill_gained:   isZH ? '獲得技能：'      : 'Skill Gained:',
    confirm:        isZH ? '確認調配'        : 'Confirm Assignment',
    contact:        isZH ? '聯絡員工'        : 'Contact Staff',
    explicit:       isZH ? '顯性'            : 'Explicit',
    implicit:       isZH ? '隱性'            : 'Implicit',
    no_analysis:    isZH ? '此員工尚未有可分析的實際資料' : 'No analysable records for this staff member yet',
    loading:        isZH ? '分析載入中…'     : 'Loading analysis…',
    times:          isZH ? '次'              : '×',
  }

  const CREDENTIALS = analysis?.explicit_skills.length
    ? analysis.explicit_skills
    : (detail?.certificates ?? []).map(c => ({
        skill: c.cert_type, status: 'valid' as const, score: 100,
        expiry_date: c.expiry_date, days_left: null,
      }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onClose}>
      <div className="bg-white w-full max-w-2xl rounded-[2.5rem] overflow-hidden shadow-2xl max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}>

        <div className="relative h-48 flex-shrink-0"
          style={{ background: 'linear-gradient(135deg, #fce8f3 0%, #eff6ff 100%)' }}>
          <button onClick={onClose}
            className="absolute top-5 right-5 p-2 bg-white/60 hover:bg-white rounded-full transition-colors z-10 text-gray-600 font-bold w-9 h-9 flex items-center justify-center">
            ✕
          </button>
          <div className="absolute -bottom-16 left-10">
            <div className="relative">
              <div className="w-32 h-32 rounded-[2rem] border-8 border-white bg-pink-50 flex items-center justify-center text-5xl shadow-lg">
                {staff.apiId ? staff.avatar : AVATARS[idx]}
              </div>
              <div className="absolute -bottom-2 -right-2 w-10 h-10 rounded-full bg-emerald-500 flex items-center justify-center border-4 border-white shadow-md text-white text-sm">✓</div>
            </div>
          </div>
        </div>

        <div className="pt-20 px-10 pb-6 overflow-y-auto flex-1">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h2 className="text-2xl font-extrabold text-gray-900">{staff.nameEn}</h2>
              <div className="text-sm text-gray-500 mt-0.5">{staff.name}</div>
              <div className="flex items-center gap-3 mt-2">
                <span className="text-xs font-bold px-3 py-1 rounded-full text-white uppercase tracking-wider" style={{ background: PINK }}>
                  {staff.role}
                </span>
                <span className="text-sm text-gray-500 font-medium">ID: #NGO-{1000 + staff.id * 317}</span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-3xl font-black" style={{ color: '#10b981' }}>
                {analysis?.activity.emergency_covers ?? 0}
              </div>
              <div className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{L.covers}</div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-6">
            {[
              { label: L.weekly_load,  value: `${staff.hoursWorked}h / ${staff.hoursTotal}h` },
              { label: L.night_shifts, value: String(analysis?.activity.night_shifts ?? '-') },
              { label: L.units,        value: String(analysis?.activity.distinct_units ?? '-') },
            ].map(s => (
              <div key={s.label} className="bg-gray-50 p-4 rounded-2xl">
                <div className="text-[10px] font-bold text-gray-400 uppercase mb-1">{s.label}</div>
                <div className="text-lg font-bold text-gray-900">{s.value}</div>
              </div>
            ))}
          </div>

          <div className="mb-6 bg-gray-50 p-4 rounded-2xl">
            <div className="flex justify-between text-xs text-gray-500 mb-2">
              <span>{L.hours_month}</span>
              <span className="font-bold" style={{ color: PINK }}>{staff.hoursWorked}h / {staff.hoursTotal}h</span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: pct >= 100 ? '#dc2626' : pct >= 90 ? '#d97706' : PINK }} />
            </div>
          </div>

          <div className="flex gap-6 border-b border-gray-100 mb-5">
            {[{ key: 'history', label: L.tab_history }, { key: 'ai', label: L.tab_ai }].map(t => (
              <button key={t.key} onClick={() => setTab(t.key as 'ai' | 'history')}
                className="pb-3 text-sm font-bold transition-all relative"
                style={{ color: tab === t.key ? PINK : '#9ca3af' }}>
                {t.label}
                {tab === t.key && <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full" style={{ background: PINK }} />}
              </button>
            ))}
          </div>

          {tab === 'history' ? (
            <div className="space-y-3">
              {SHIFT_HISTORY.length === 0 && (
                <div className="text-xs text-gray-400 text-center py-6">{isZH ? '尚無更表紀錄' : 'No shift history yet'}</div>
              )}
              {SHIFT_HISTORY.map((s, i) => (
                <div key={i} className="bg-gray-50 p-5 rounded-3xl border border-gray-100 hover:border-pink-200 transition-all">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center shadow-sm text-lg">📅</div>
                      <div>
                        <div className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{s.date}</div>
                        <div className="text-sm font-bold text-gray-900">{s.shift}</div>
                      </div>
                    </div>
                    <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-100">
                      {L.completed}
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
                <div className="text-[9px] font-bold text-gray-400 uppercase tracking-widest mb-2">{L.credentials}</div>
                <div className="flex gap-2 flex-wrap">
                  {CREDENTIALS.length === 0 && (
                    <span className="text-[10px] text-gray-400">{isZH ? '尚無證書記錄' : 'No certificates on record'}</span>
                  )}
                  {CREDENTIALS.map(c => (
                    <span key={c.skill}
                      className={`text-[10px] font-bold px-2.5 py-1 rounded-lg border ${
                        c.status === 'expired' ? 'bg-rose-50 border-rose-200 text-rose-600'
                          : c.status === 'expiring' ? 'bg-amber-50 border-amber-200 text-amber-700'
                          : 'bg-gray-50 border-gray-200 text-gray-600'}`}>
                      {c.skill}
                      {c.days_left !== null && c.days_left !== undefined && (
                        <span className="ml-1 font-normal opacity-70">
                          {c.days_left < 0 ? `${-c.days_left}d ago` : `${c.days_left}d`}
                        </span>
                      )}
                    </span>
                  ))}
                </div>
              </div>

              <div className="p-3 rounded-2xl flex items-center gap-3" style={{ background: '#1a1a2e' }}>
                <div className="text-xl">🧠</div>
                <div>
                  <div className="text-xs font-bold text-white">{L.ai_skill}</div>
                  <div className="text-[10px] text-gray-400">
                    {analysis
                      ? `${analysis.activity.working_shifts} shifts · ${analysis.activity.hours}h · ${analysis.activity.tasks_performed} task records`
                      : (isZH ? '隱性與顯性技能分析' : 'Implicit & Explicit Insights')}
                  </div>
                </div>
                <span className="ml-auto text-[9px] font-bold px-2 py-0.5 rounded text-white" style={{ background: PINK }}>
                  {L.evidence}
                </span>
              </div>

              {analysisError && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 p-3 text-[11px] text-rose-700">{analysisError}</div>
              )}
              {!analysis && !analysisError && (
                <div className="text-[11px] text-gray-400">{L.loading}</div>
              )}

              {analysis && analysis.implicit_skills.length > 0 && (
                <div>
                  <div className="flex gap-1.5 mb-2">
                    <span className="text-[9px] font-bold px-2 py-0.5 rounded text-white" style={{ background: PINK }}>{L.explicit.toUpperCase()}</span>
                    <span className="text-[9px] font-bold px-2 py-0.5 rounded bg-purple-600 text-white">{L.implicit.toUpperCase()}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {analysis.implicit_skills.map(s => (
                      <span key={s.skill} className="text-[10px] px-2.5 py-1 rounded-full border font-medium"
                        style={{ borderColor: 'rgba(232,24,122,.3)', color: PINK, background: '#fef6fb' }}>
                        {s.skill} <span className="opacity-60">{s.occurrences}{L.times}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {analysis && analysis.skill_bars.length > 0 && (
                <div className="bg-gray-50 p-4 rounded-2xl">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-xs font-bold text-gray-700">{L.skill_prog}</div>
                    <span className="text-[9px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                      {analysis.activity.working_shifts} shifts
                    </span>
                  </div>
                  {analysis.skill_bars.map(s => (
                    <div key={s.skill} className="mb-3">
                      <div className="flex justify-between text-[10px] mb-1">
                        <span className="font-semibold text-gray-700">{s.skill}</span>
                        <span className="text-gray-400">{L.explicit}: {s.explicit}% · {L.implicit}: {s.implicit}%</span>
                      </div>
                      <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden mb-0.5">
                        <div className="h-full rounded-full" style={{ width: `${s.explicit}%`, background: PINK }} />
                      </div>
                      <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-purple-500" style={{ width: `${s.implicit}%` }} />
                      </div>
                    </div>
                  ))}
                  <p className="text-[9px] text-gray-400 mt-2">{analysis.evidence_note}</p>
                </div>
              )}

              {analysis && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-red-50 border border-red-100 p-3 rounded-2xl">
                    <div className="text-[9px] font-bold text-red-400 uppercase tracking-widest mb-2">{L.gaps}</div>
                    {analysis.gaps.length === 0 && (
                      <div className="text-[10px] text-red-400">{isZH ? '未發現技能缺口' : 'No gaps detected'}</div>
                    )}
                    {analysis.gaps.map(g => (
                      <div key={`${g.kind}-${g.skill}`} className="text-[10px] text-red-600 flex items-start gap-1 mb-1">
                        <span>⚠</span>
                        <span>{g.skill}<span className="text-red-400"> - {g.detail}</span></span>
                      </div>
                    ))}
                  </div>
                  <div className="bg-emerald-50 border border-emerald-100 p-3 rounded-2xl">
                    <div className="text-[9px] font-bold text-emerald-600 uppercase tracking-widest mb-2">{L.training}</div>
                    {analysis.recommended_training.length === 0 && (
                      <div className="text-[10px] text-emerald-600">{isZH ? '暫無建議' : 'Nothing outstanding'}</div>
                    )}
                    {analysis.recommended_training.map(t => (
                      <div key={t.title} className="text-[10px] text-emerald-700 flex items-start gap-1 mb-1">
                        <span>✓</span>
                        <span>{t.title}<span className="text-emerald-600"> - {t.reason}</span></span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {analysis && analysis.events.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">{L.implicit_title}</div>
                    <span className="text-[9px] font-bold px-2 py-0.5 rounded text-white bg-purple-600">FROM ROSTER</span>
                  </div>
                  {analysis.events.map((e, i) => (
                    <div key={`${e.date}-${i}`} className="flex gap-3 p-3 bg-gray-50 rounded-2xl border border-gray-100 mb-2">
                      <div className="text-[10px] font-bold w-12 text-gray-400 flex-shrink-0">{e.date?.slice(5)}</div>
                      <div className="flex-1">
                        <div className="text-xs font-bold text-gray-800">{e.title}</div>
                        <div className="text-[10px] text-gray-500">{e.detail}</div>
                        <div className="text-[9px] font-bold mt-1" style={{ color: PINK }}>{L.skill_gained} {e.skill}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {analysis && analysis.activity.working_shifts === 0 && (
                <div className="text-[11px] text-gray-400">{L.no_analysis}</div>
              )}
            </div>
          )}
        </div>

        <div className="px-10 py-5 border-t border-gray-100 flex gap-3 flex-shrink-0">
          <button className="flex-1 py-3.5 text-white font-bold rounded-2xl shadow-lg transition-transform hover:scale-[1.02]" style={{ background: PINK }}>
            {L.confirm}
          </button>
          <button className="px-8 py-3.5 bg-gray-100 text-gray-600 font-bold rounded-2xl hover:bg-gray-200 transition-colors">
            {L.contact}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function StaffPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'
  const [search, setSearch] = useState('')
  const [filterRole, setFilterRole] = useState<string>('ALL')
  const [selected, setSelected] = useState<{ staff: StaffType; idx: number } | null>(null)

  // Pull the real staff directory from the API; fall back to demo data if the
  // API is unreachable or no dev creds are configured, so the page never breaks.
  // Always real: the directory is the live API record set (null = still loading).
  const [liveStaff, setLiveStaff] = useState<StaffType[] | null>(null)
  useEffect(() => {
    let cancelled = false
    api.listStaff()
      .then((rows) => { if (!cancelled) setLiveStaff(mapApiStaff(rows)) })
      .catch(() => { if (!cancelled) setLiveStaff([]) })
    return () => { cancelled = true }
  }, [])
  const staffList: StaffType[] = useMemo(() => liveStaff ?? [], [liveStaff])
  const roleOptions = ['ALL', ...Array.from(new Set(staffList.map(s => s.role)))]

  const L = {
    title:     isZH ? 'Staff Portfolio 員工檔案'                                       : 'Staff Portfolio',
    subtitle:  isZH ? `${staffList.length} 位員工` : `${staffList.length} staff members`,
    add_staff: isZH ? '＋ 新增員工'                           : '＋ Add Staff',
    search_ph: isZH ? '🔍 搜尋員工...'                        : '🔍 Search staff...',
    skills:    isZH ? '技能'                                  : 'Skills',
    view:      isZH ? '查看檔案 →'                            : 'View Profile →',
  }

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return staffList.filter(s => {
      const matchSearch = s.nameEn.toLowerCase().includes(q) || s.name.includes(search)
      const matchRole = filterRole === 'ALL' || s.role === filterRole
      return matchSearch && matchRole
    })
  }, [search, filterRole, staffList])

  return (
    <div className="p-5 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">{L.title}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{L.subtitle}</p>
        </div>
        <button className="px-4 py-2 text-white text-xs font-semibold rounded-xl" style={{ background: PINK }}>
          {L.add_staff}
        </button>
      </div>

      <div className="flex gap-3 flex-wrap">
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder={L.search_ph}
          className="flex-1 px-4 py-2 border border-gray-200 rounded-xl text-sm bg-gray-50 outline-none focus:border-pink-400" />
        <div className="flex gap-1.5 flex-wrap">
          {roleOptions.map(r => (
            <button key={r} onClick={() => setFilterRole(r)}
              className="px-3 py-2 text-xs font-bold rounded-xl border transition-all"
              style={{
                background:  filterRole === r ? PINK : '#fff',
                color:       filterRole === r ? '#fff' : '#6b7280',
                borderColor: filterRole === r ? PINK : '#e5e7eb',
              }}>
              {r}
            </button>
          ))}
        </div>
      </div>

      {liveStaff === null ? (
        <div className="text-sm text-gray-400 py-12 text-center">…</div>
      ) : filtered.length === 0 ? (
        <div className="text-sm text-gray-400 py-12 text-center">{isZH ? '沒有符合的員工' : 'No matching staff'}</div>
      ) : (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((s, i) => {
          const pct = s.hoursTotal ? Math.round((s.hoursWorked / s.hoursTotal) * 100) : 0
          const status = s.apiStatus
            ? (API_STATUS[s.apiStatus] ?? DEFAULT_STATUS)
            : (STATUS[s.id] ?? DEFAULT_STATUS)
          return (
            <div key={s.id} className="bg-white p-5 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-all group">
              <div className="flex items-start gap-3 mb-4">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl bg-pink-50 border border-pink-100 flex-shrink-0 group-hover:scale-105 transition-transform">
                  {s.apiId ? s.avatar : AVATARS[i]}
                </div>
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900 text-sm group-hover:text-pink-600 transition-colors mb-1">{s.nameEn}</h3>
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider text-white" style={{ background: PINK }}>
                      {s.role}
                    </span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider"
                      style={{ color: status.color, background: status.bg }}>
                      {isZH ? status.labelZH : status.labelEN}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: pct >= 100 ? '#dc2626' : pct >= 90 ? '#d97706' : PINK }} />
                    </div>
                    <span className="text-[10px] font-black" style={{ color: PINK }}>{pct}%</span>
                  </div>
                </div>
              </div>

              <div className="text-[10px] text-gray-400 mb-3">📍 {s.ward} · {s.floor}</div>

              <div>
                <div className="text-[9px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">{L.skills}</div>
                <div className="flex flex-wrap gap-1">
                  {(s.certs.length ? s.certs : (s.apiId ? [] : SKILLS[s.id] || [])).map(sk => (
                    <span key={sk} className="text-[10px] font-semibold text-gray-600 bg-gray-50 px-2 py-0.5 rounded-lg border border-gray-100">{sk}</span>
                  ))}
                </div>
              </div>

              <div className="pt-3 mt-3 border-t border-gray-50 flex justify-between items-center">
                <button onClick={() => setSelected({ staff: s, idx: i })} className="text-xs font-bold hover:underline" style={{ color: PINK }}>
                  {L.view}
                </button>
                <button className="p-2 bg-gray-50 rounded-xl text-gray-400 hover:text-pink-600 hover:bg-pink-50 transition-all">💬</button>
              </div>
            </div>
          )
        })}
      </div>
      )}

      {selected && <ProfileModal staff={selected.staff} idx={selected.idx} onClose={() => setSelected(null)} />}
    </div>
  )
}