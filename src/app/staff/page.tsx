'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { Staff } from '@/lib/types'
import { api } from '@/lib/api'
import type { ApiStaff, StaffAiAnalysis, StaffDetail } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { canWrite } from '@/lib/permissions'
import { AddStaffModal } from '@/components/staff/AddStaffModal'

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

// The two capability flags the rule engine reads off a staff record. Both are
// editable here rather than only at creation: mentor status is the one a
// superintendent changes most, because it decides whether a new-staff restricted
// duty may be rostered at all (see scheduling.validate - "new_staff_restricted"
// requires a mentor on the shift).
const CAPABILITY_FIELDS = [
  {
    key: 'is_mentor' as const,
    icon: '🎓',
    titleZH: '可帶教新人', titleEN: 'Can mentor new staff',
    hintZH: '新入職員工需導師陪同', hintEN: 'New staff need a mentor on duty',
  },
  {
    key: 'is_audited_for_medication' as const,
    icon: '💊',
    titleZH: '藥物核查資格', titleEN: 'Medication audited',
    hintZH: '可執行藥物相關工作', hintEN: 'May perform medication duties',
  },
]

type CapabilityKey = (typeof CAPABILITY_FIELDS)[number]['key']

function ProfileModal({ staff, idx, canEdit, onClose, onSaved }: {
  staff: StaffType
  idx: number
  canEdit: boolean
  onClose: () => void
  onSaved: (name: string) => void
}) {
  const { lang } = useLang()
  const isZH = lang === 'zh'
  const [tab, setTab] = useState<'ai' | 'history' | 'edit'>('history')
  const [detail, setDetail] = useState<StaffDetail | null>(null)
  const [analysis, setAnalysis] = useState<StaffAiAnalysis | null>(null)
  const [analysisError, setAnalysisError] = useState('')

  // `draft` holds the pending toggle state; null until the record loads, so the
  // switches cannot be flipped against a value we have not read yet. Saving
  // sends only the keys that actually differ from `detail`.
  const [draft, setDraft] = useState<Record<CapabilityKey, boolean> | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [editForm, setEditForm] = useState<{
    name: string; name_en: string; rank: string; employment_type: string
    contracted_hours: number; gender: 'M' | 'F'; status: 'active' | 'inactive'
  } | null>(null)
  const [editSaving, setEditSaving] = useState(false)
  const [editSuccess, setEditSuccess] = useState(false)

  useEffect(() => {
    if (!staff.apiId) return
    let cancelled = false
    api.staffDetail(staff.apiId)
      .then(d => {
        if (cancelled) return
        setDetail(d)
        setDraft({ is_mentor: !!d.is_mentor, is_audited_for_medication: !!d.is_audited_for_medication })
        setEditForm({
          name: d.name || '',
          name_en: d.name_en || '',
          rank: d.rank || '',
          employment_type: d.employment_type || '',
          contracted_hours: d.contracted_hours || 44,
          gender: (d as any).gender || 'F',
          status: (d as any).status === 'inactive' ? 'inactive' : 'active',
        })
      })
      .catch(() => {})
    api.staffAiAnalysis(staff.apiId)
      .then(a => { if (!cancelled) setAnalysis(a) })
      .catch(e => { if (!cancelled) setAnalysisError(e instanceof Error ? e.message : 'Analysis unavailable') })
    return () => { cancelled = true }
  }, [staff.apiId])

  const dirtyKeys = draft && detail
    ? CAPABILITY_FIELDS.map(f => f.key).filter(k => draft[k] !== !!detail[k])
    : []

  async function saveCapabilities() {
    if (!staff.apiId || !draft || dirtyKeys.length === 0) return
    setSaving(true)
    setSaveError('')
    try {
      const patch = Object.fromEntries(dirtyKeys.map(k => [k, draft[k]]))
      const updated = await api.updateStaff(staff.apiId, patch)
      // Re-seed from the row the API returned, so `dirtyKeys` empties and the
      // panel reflects what was actually stored rather than what we sent.
      setDetail(d => (d ? { ...d, ...updated } : d))
      onSaved(staff.nameEn)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

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
    night_shifts:   isZH ? 'N更次數'         : 'N Shifts',
    units:          isZH ? '服務單位數'      : 'Units Worked',
    hours_month:    isZH ? '本週期工時'      : 'Hours This Period',
    tab_history:    isZH ? '更表紀錄'        : 'Shift History',
    tab_ai:         isZH ? 'AI 分析'         : 'AI Analysis',
    tab_edit:       isZH ? '編輯資料'        : 'Edit Profile',
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
    capabilities:   isZH ? '資格與能力'      : 'Capabilities',
    save:           isZH ? '儲存'            : 'Save',
    saving:         isZH ? '儲存中…'         : 'Saving…',
    saved:          isZH ? '已儲存'          : 'Saved',
    unsaved:        isZH ? '尚未儲存'        : 'Unsaved changes',
    readonly:       isZH ? '你的權限不可修改員工資格' : 'Your role may not edit staff capabilities',
  }

  async function saveEditForm() {
    if (!staff.apiId || !editForm) return
    setEditSaving(true)
    setSaveError('')
    try {
      await api.updateStaff(staff.apiId, {
        name: editForm.name,
        name_en: editForm.name_en,
        rank: editForm.rank,
        employment_type: editForm.employment_type,
        contracted_hours: editForm.contracted_hours,
        gender: editForm.gender,
        status: editForm.status,
      })
      setEditSuccess(true)
      onSaved(editForm.name_en || editForm.name)
      setTimeout(() => setEditSuccess(false), 2000)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setEditSaving(false)
    }
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

          {/* Capabilities. Sits above the tabs rather than inside one, because it
              is the only editable thing on this screen - burying a write behind a
              tab labelled "Shift History" or "AI Analysis" is how it went missing. */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">{L.capabilities}</div>
              {canEdit && dirtyKeys.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-semibold text-amber-600">{L.unsaved}</span>
                  <button onClick={saveCapabilities} disabled={saving}
                    className="px-4 py-1.5 text-[11px] rounded-lg text-white font-bold disabled:opacity-60"
                    style={{ background: PINK }}>
                    {saving ? L.saving : L.save}
                  </button>
                </div>
              )}
            </div>

            {draft === null ? (
              <div className="text-[10px] text-gray-400 py-2">…</div>
            ) : (
              <div className="space-y-2">
                {CAPABILITY_FIELDS.map(f => {
                  const on = draft[f.key]
                  return (
                    <div key={f.key} className="flex items-center gap-3 p-3 rounded-xl" style={{ background: '#fce8f3' }}>
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0" style={{ background: PINK }}>
                        {f.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-gray-900">{isZH ? f.titleZH : f.titleEN}</div>
                        <div className="text-[10px] text-gray-500 mt-0.5">{isZH ? f.hintZH : f.hintEN}</div>
                      </div>
                      <button type="button"
                        role="switch"
                        aria-checked={on}
                        aria-label={isZH ? f.titleZH : f.titleEN}
                        disabled={!canEdit}
                        onClick={() => setDraft(d => (d ? { ...d, [f.key]: !d[f.key] } : d))}
                        className="w-10 h-6 rounded-full transition-all relative shrink-0 disabled:cursor-not-allowed disabled:opacity-50"
                        style={{ background: on ? PINK : '#d1d5db' }}>
                        <span className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all"
                          style={{ left: on ? '20px' : '4px' }} />
                      </button>
                    </div>
                  )
                })}
              </div>
            )}

            {!canEdit && <p className="text-[10px] text-gray-400 mt-1.5">{L.readonly}</p>}
            {saveError && <p className="text-[10px] text-rose-600 mt-1.5">{saveError}</p>}
          </div>

          <div className="flex gap-6 border-b border-gray-100 mb-5">
            {[{ key: 'history', label: L.tab_history }, { key: 'ai', label: L.tab_ai }, ...(canEdit ? [{ key: 'edit', label: L.tab_edit }] : [])].map(t => (
              <button key={t.key} onClick={() => setTab(t.key as 'ai' | 'history' | 'edit')}
                className="pb-3 text-sm font-bold transition-all relative"
                style={{ color: tab === t.key ? PINK : '#9ca3af' }}>
                {t.label}
                {tab === t.key && <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full" style={{ background: PINK }} />}
              </button>
            ))}
          </div>

          {tab === 'edit' && editForm ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1 block">
                    {isZH ? '中文姓名' : 'Chinese Name'}
                  </label>
                  <input value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:border-pink-400 focus:outline-none" />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1 block">
                    {isZH ? '英文姓名' : 'English Name'}
                  </label>
                  <input value={editForm.name_en} onChange={e => setEditForm({ ...editForm, name_en: e.target.value })}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:border-pink-400 focus:outline-none" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1 block">
                    {isZH ? '職級' : 'Rank'}
                  </label>
                  <select value={editForm.rank} onChange={e => setEditForm({ ...editForm, rank: e.target.value })}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:border-pink-400 focus:outline-none bg-white">
                    <option value="RN">RN (Registered Nurse)</option>
                    <option value="EN">EN (Enrolled Nurse)</option>
                    <option value="HW">HW (Health Worker)</option>
                    <option value="PCW">PCW (Personal Care Worker)</option>
                    <option value="CW">CW (Care Worker)</option>
                    <option value="ASST">ASST (Assistant)</option>
                    <option value="PT">PT (Physiotherapist)</option>
                    <option value="OT">OT (Occupational Therapist)</option>
                    <option value="SW">SW (Social Worker)</option>
                    <option value="ADMIN">ADMIN (Administrative)</option>
                    <option value="COOK">COOK (Kitchen Staff)</option>
                    <option value="DRIVER">DRIVER</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1 block">
                    {isZH ? '僱用類型' : 'Employment Type'}
                  </label>
                  <select value={editForm.employment_type} onChange={e => setEditForm({ ...editForm, employment_type: e.target.value })}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:border-pink-400 focus:outline-none bg-white">
                    <option value="full_time">{isZH ? '全職' : 'Full-time'}</option>
                    <option value="part_time">{isZH ? '兼職' : 'Part-time'}</option>
                    <option value="contract">{isZH ? '合約' : 'Contract'}</option>
                    <option value="agency">{isZH ? '外判' : 'Agency'}</option>
                    <option value="imported">{isZH ? '外勞' : 'Imported Worker'}</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1 block">
                    {isZH ? '合約時數/週' : 'Hours/Week'}
                  </label>
                  <input type="number" value={editForm.contracted_hours}
                    onChange={e => setEditForm({ ...editForm, contracted_hours: Number(e.target.value) })}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:border-pink-400 focus:outline-none" />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1 block">
                    {isZH ? '性別' : 'Gender'}
                  </label>
                  <select value={editForm.gender} onChange={e => setEditForm({ ...editForm, gender: e.target.value as 'M' | 'F' })}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:border-pink-400 focus:outline-none bg-white">
                    <option value="F">{isZH ? '女' : 'Female'}</option>
                    <option value="M">{isZH ? '男' : 'Male'}</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1 block">
                    {isZH ? '狀態' : 'Status'}
                  </label>
                  <select value={editForm.status} onChange={e => setEditForm({ ...editForm, status: e.target.value as 'active' | 'inactive' })}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:border-pink-400 focus:outline-none bg-white">
                    <option value="active">{isZH ? '在職' : 'Active'}</option>
                    <option value="inactive">{isZH ? '離職' : 'Inactive'}</option>
                  </select>
                </div>
              </div>

              {saveError && <p className="text-xs text-rose-600">{saveError}</p>}

              <button onClick={saveEditForm} disabled={editSaving}
                className="w-full py-3 text-white font-bold rounded-xl transition-all disabled:opacity-60"
                style={{ background: editSuccess ? '#10b981' : PINK }}>
                {editSaving ? (isZH ? '儲存中…' : 'Saving…') : editSuccess ? (isZH ? '✓ 已儲存' : '✓ Saved') : (isZH ? '儲存修改' : 'Save Changes')}
              </button>
            </div>
          ) : tab === 'history' ? (
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
  const { user } = useAuth()
  const [search, setSearch] = useState('')
  const [filterRole, setFilterRole] = useState<string>('ALL')
  const [selected, setSelected] = useState<{ staff: StaffType; idx: number } | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [notice, setNotice] = useState('')
  // Per the RBAC matrix, OWNER and ADMIN_CLERK may write a staff profile; the
  // API enforces it too, so this only avoids offering a door that won't open.
  const canWriteStaff = canWrite(user?.role, 'staff.profile_write')

  // Pull the real staff directory from the API; fall back to demo data if the
  // API is unreachable or no dev creds are configured, so the page never breaks.
  // Always real: the directory is the live API record set (null = still loading).
  const [liveStaff, setLiveStaff] = useState<StaffType[] | null>(null)
  const reloadStaff = useCallback(
    () => api.listStaff().then((rows) => setLiveStaff(mapApiStaff(rows))),
    [],
  )
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
        <div className="flex items-center gap-3">
          {notice && <span className="text-xs font-medium text-emerald-600">{notice}</span>}
          {canWriteStaff && (
            <button onClick={() => setAddOpen(true)}
              className="px-4 py-2 text-white text-xs font-semibold rounded-xl" style={{ background: PINK }}>
              {L.add_staff}
            </button>
          )}
        </div>
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
                  {/* The name is a second door to the same detail panel as
                      "View Profile" below - clicking a person's name is the
                      first thing anyone tries. */}
                  <button type="button" onClick={() => setSelected({ staff: s, idx: i })}
                    className="block text-left font-bold text-gray-900 text-sm group-hover:text-pink-600 hover:underline transition-colors mb-1">
                    {s.nameEn}
                  </button>
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

      {selected && (
        <ProfileModal
          staff={selected.staff}
          idx={selected.idx}
          canEdit={canWriteStaff}
          onClose={() => setSelected(null)}
          onSaved={(name) => {
            setNotice(isZH ? `已更新 ${name}` : `${name} updated`)
            window.setTimeout(() => setNotice(''), 3000)
            // The card grid shows nothing capability-related today, but the
            // directory read is what other screens' rule checks derive from, so
            // keep it in step with what was just written.
            reloadStaff().catch(() => {})
          }}
        />
      )}

      {addOpen && (
        <AddStaffModal
          isZH={isZH}
          onClose={() => setAddOpen(false)}
          onCreated={(name) => {
            setAddOpen(false)
            setNotice(isZH ? `已新增 ${name}` : `${name} added`)
            window.setTimeout(() => setNotice(''), 3000)
            reloadStaff().catch(() => {})
          }}
        />
      )}
    </div>
  )
}
