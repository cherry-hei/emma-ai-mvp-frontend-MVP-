'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { Unit } from '@/lib/apiTypes'

const PINK = '#f28f9e'

// emma_core.constants.Rank / EmploymentType. The API rejects anything else, so
// these are pickers rather than free text.
const RANKS = ['RN', 'EN', 'HW', 'HCA', 'CW', 'PCW', 'AW', 'PTA', 'OTA', 'SW', 'PT', 'OT']
const EMPLOYMENT_TYPES: { value: string; zh: string; en: string }[] = [
  { value: 'local_ft', zh: '本地全職', en: 'Local full-time' },
  { value: 'local_pt', zh: '本地兼職', en: 'Local part-time' },
  { value: 'imported_labor', zh: '輸入勞工', en: 'Imported labour' },
  { value: 'agency', zh: '外援機構', en: 'Agency' },
  { value: 'outsource', zh: '外判', en: 'Outsourced' },
  { value: 'casual', zh: '散工', en: 'Casual' },
]

export interface AddStaffModalProps {
  isZH: boolean
  onClose: () => void
  onCreated: (name: string) => void
}

export function AddStaffModal({ isZH, onClose, onCreated }: AddStaffModalProps) {
  const [units, setUnits] = useState<Unit[]>([])
  const [name, setName] = useState('')
  const [nameEn, setNameEn] = useState('')
  const [rank, setRank] = useState('CW')
  const [employmentType, setEmploymentType] = useState('local_ft')
  const [unitId, setUnitId] = useState('')
  const [contractedHours, setContractedHours] = useState('')
  const [gender, setGender] = useState<'' | 'M' | 'F'>('')
  const [medicationAudited, setMedicationAudited] = useState(false)
  const [isMentor, setIsMentor] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    let cancelled = false
    api.units().then((u) => { if (!cancelled) setUnits(u) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  const L = {
    title: isZH ? '新增員工' : 'Add Staff',
    subtitle: isZH ? '加入員工檔案' : 'Add to the staff directory',
    name: isZH ? '姓名（中文）' : 'Name',
    name_ph: isZH ? '例如：陳大文' : 'e.g. Chan Tai Man',
    name_en: isZH ? '英文姓名' : 'Name (English)',
    name_en_ph: isZH ? '例如：Chan Tai Man' : 'e.g. Chan Tai Man',
    rank: isZH ? '職級' : 'Rank',
    employment: isZH ? '聘用類型' : 'Employment type',
    unit: isZH ? '所屬單位' : 'Unit',
    unit_none: isZH ? '（未指定）' : '(unassigned)',
    hours: isZH ? '每週合約時數' : 'Contracted hours / week',
    hours_ph: isZH ? '例如：44' : 'e.g. 44',
    gender: isZH ? '性別' : 'Gender',
    gender_none: isZH ? '（不填）' : '(not set)',
    male: isZH ? '男' : 'Male',
    female: isZH ? '女' : 'Female',
    medication: isZH ? '已通過藥物審核' : 'Medication-audited',
    medication_hint: isZH ? '可獲派藥物相關任務' : 'May be assigned medication tasks',
    mentor: isZH ? '可帶教新人' : 'Can mentor new staff',
    mentor_hint: isZH ? '新入職員工需導師陪同' : 'New staff need a mentor on duty',
    cancel: isZH ? '取消' : 'Cancel',
    save: isZH ? '新增' : 'Add staff',
    name_required: isZH ? '請輸入姓名' : 'Name is required',
  }

  async function handleSave() {
    if (!name.trim()) { setErr(L.name_required); return }
    setBusy(true); setErr('')
    try {
      const hours = contractedHours.trim() === '' ? undefined : Number(contractedHours)
      await api.createStaff({
        name: name.trim(),
        name_en: nameEn.trim() || undefined,
        rank,
        employment_type: employmentType,
        primary_unit_id: unitId || undefined,
        contracted_hours: Number.isFinite(hours) ? hours : undefined,
        gender: gender || undefined,
        is_audited_for_medication: medicationAudited,
        is_mentor: isMentor,
      })
      onCreated(nameEn.trim() || name.trim())
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  const field = 'mt-1.5 w-full px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:outline-none focus:border-pink-400'
  const label = 'text-[9px] font-bold text-gray-500 uppercase tracking-wider'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onClose}>
      <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}>
        <div className="px-6 pt-6 pb-3 border-b border-gray-100 flex items-center gap-3 flex-shrink-0">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0" style={{ background: '#fce8f3' }}>🧑‍⚕️</div>
          <div className="min-w-0">
            <div className="text-lg font-bold truncate">{L.title}</div>
            <p className="text-xs font-semibold mt-0.5 truncate" style={{ color: PINK }}>{L.subtitle}</p>
          </div>
        </div>

        <div className="px-6 py-4 overflow-y-auto space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={label}>{L.name} *</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder={L.name_ph} className={field} />
            </div>
            <div>
              <label className={label}>{L.name_en}</label>
              <input value={nameEn} onChange={(e) => setNameEn(e.target.value)} placeholder={L.name_en_ph} className={field} />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={label}>{L.rank} *</label>
              <select value={rank} onChange={(e) => setRank(e.target.value)} className={field}>
                {RANKS.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>{L.employment} *</label>
              <select value={employmentType} onChange={(e) => setEmploymentType(e.target.value)} className={field}>
                {EMPLOYMENT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{isZH ? t.zh : t.en}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className={label}>{L.unit}</label>
              <select value={unitId} onChange={(e) => setUnitId(e.target.value)} className={field}>
                <option value="">{L.unit_none}</option>
                {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>{L.hours}</label>
              <input type="number" min={0} max={168} value={contractedHours} placeholder={L.hours_ph}
                onChange={(e) => setContractedHours(e.target.value)} className={field} />
            </div>
            <div>
              <label className={label}>{L.gender}</label>
              <select value={gender} onChange={(e) => setGender(e.target.value as '' | 'M' | 'F')} className={field}>
                <option value="">{L.gender_none}</option>
                <option value="M">{L.male}</option>
                <option value="F">{L.female}</option>
              </select>
            </div>
          </div>

          {[
            { on: medicationAudited, set: setMedicationAudited, title: L.medication, hint: L.medication_hint, icon: '💊' },
            { on: isMentor, set: setIsMentor, title: L.mentor, hint: L.mentor_hint, icon: '🎓' },
          ].map((t) => (
            <div key={t.title} className="flex items-center gap-3 p-3 rounded-xl" style={{ background: '#fce8f3' }}>
              <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0" style={{ background: PINK }}>{t.icon}</div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold">{t.title}</div>
                <div className="text-[10px] text-gray-500 mt-0.5">{t.hint}</div>
              </div>
              <button type="button" onClick={() => t.set(!t.on)}
                className="w-10 h-6 rounded-full transition-all relative shrink-0"
                style={{ background: t.on ? PINK : '#d1d5db' }}>
                <span className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all" style={{ left: t.on ? '20px' : '4px' }} />
              </button>
            </div>
          ))}

          {err && <div className="text-xs text-rose-600">{err}</div>}
        </div>

        <div className="px-6 py-4 border-t border-gray-100 flex gap-2 justify-end flex-shrink-0">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">{L.cancel}</button>
          <button onClick={handleSave} disabled={busy}
            className="px-4 py-1.5 text-xs rounded-lg text-white font-semibold disabled:opacity-60" style={{ background: PINK }}>
            {busy ? '…' : L.save}
          </button>
        </div>
      </div>
    </div>
  )
}
