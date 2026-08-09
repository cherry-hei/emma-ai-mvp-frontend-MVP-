'use client'

// Settings page: Facility Configuration, Constraint Toggles, Staff Constraints,
// Special Events, Imported Worker Rules, and Personal Preferences.
// Follows the same pattern as scheduling/page.tsx.

import { useState } from 'react'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { canWrite } from '@/lib/permissions'

const PINK = '#E8187A'
const CARD = 'rounded-lg border bg-white'
const CARD_STYLE = { borderColor: '#e5e7eb' }
const INPUT = 'border rounded px-2 py-1.5 text-[11px] w-full'
const INPUT_STYLE = { borderColor: '#e5e7eb' }

type Tab = 'facility' | 'constraints' | 'staff_hard' | 'events' | 'imported' | 'preferences'

// ─── Demo Data ──────────────────────────────────────────────────────────────

interface FacilityConfig {
  facilityName: string
  orgCode: string
  residentCount: number
  dailyResidentCount: number
  lastResidentUpdate: string
  swdRatioDisplay: string
  swdLicenseNo: string
  careLevel: string
  specificHoursStart: string
  specificHoursEnd: string
  specificHoursEffective: string
  specificHoursExpiry: string
}

interface ConstraintToggle {
  id: string
  label_zh: string
  label_en: string
  description_zh: string
  description_en: string
  category: 'hard' | 'soft'
  isHard: boolean
  canToggle: boolean
}

interface StaffHardConstraint {
  id: string
  staffName: string
  type: string
  typeLabel_zh: string
  typeLabel_en: string
  detail: string
  effectiveFrom: string
  effectiveTo: string
}

interface ImportedWorkerRule {
  id: string
  staffName: string
  shiftDuration: number
  restBetweenShifts: number
  monthlyDaysOff: number
  contractStart: string
  contractEnd: string
}

const DEMO_FACILITY: FacilityConfig = {
  facilityName: '鄰舍輔導會大興宿舍',
  orgCode: 'NAAC',
  residentCount: 60,
  swdLicenseNo: 'L0312',
  careLevel: 'moderate',
  specificHoursStart: '07:00',
  specificHoursEnd: '23:00',
  specificHoursEffective: '2024-06-16',
  specificHoursExpiry: '2028-06-15',
}

const DEMO_TOGGLES: ConstraintToggle[] = [
  { id: '1', label_zh: '護士/保健員在場', label_en: 'Nurse/HW on-site', description_zh: '特定鐘點時段內必須有護士或保健員在場及當值', description_en: 'Nurse or Health Worker must be present during specified hours', category: 'hard', isHard: true, canToggle: false },
  { id: '2', label_zh: '護理員最低人數（高峰）', label_en: 'Min CW (peak)', description_zh: '高峰時段護理員最低當值人數', description_en: 'Minimum care workers on duty during peak hours', category: 'hard', isHard: true, canToggle: false },
  { id: '3', label_zh: '護理員最低人數（非高峰）', label_en: 'Min CW (off-peak)', description_zh: '非高峰時段護理員最低當值人數', description_en: 'Minimum care workers on duty during off-peak hours', category: 'hard', isHard: true, canToggle: false },
  { id: '4', label_zh: '夜更最低人數', label_en: 'Night minimum', description_zh: '夜間必須最少2名員工當值', description_en: 'At least 2 staff on night duty', category: 'hard', isHard: true, canToggle: false },
  { id: '5', label_zh: '24/7 最少1人在場', label_en: '24/7 minimum 1', description_zh: '任何時間最少1名員工在場及當值', description_en: 'At least 1 staff present at all times', category: 'hard', isHard: true, canToggle: false },
  { id: '6', label_zh: '每週工時上限', label_en: 'Weekly hours cap', description_zh: '前線員工每週不超過49小時', description_en: 'Frontline staff max 49h/week', category: 'hard', isHard: true, canToggle: false },
  { id: '7', label_zh: '更與更之間休息', label_en: 'Inter-shift rest', description_zh: '兩更之間最少8小時休息', description_en: 'Minimum 8h rest between shifts', category: 'hard', isHard: true, canToggle: false },
  { id: '8', label_zh: '每月例假', label_en: 'Monthly days off', description_zh: '每月最少4日例假', description_en: 'At least 4 days off per month', category: 'hard', isHard: true, canToggle: false },
  { id: '9', label_zh: '特別活動額外人手', label_en: 'Event extra staffing', description_zh: '特別活動（外出等）必須多1名CW', description_en: 'Special events require +1 CW', category: 'soft', isHard: true, canToggle: true },
  { id: '10', label_zh: '新人配導師', label_en: 'Mentor pairing', description_zh: '新入職員工必須與導師同更', description_en: 'New staff must be paired with mentor', category: 'soft', isHard: true, canToggle: true },
  { id: '11', label_zh: '藥物更資格', label_en: 'Medication shift', description_zh: '藥物更必須由合格員工執行', description_en: 'Medication shifts require qualified staff', category: 'soft', isHard: true, canToggle: true },
  { id: '12', label_zh: '連續工作日上限', label_en: 'Max consecutive days', description_zh: '連續工作不超過6日', description_en: 'No more than 6 consecutive working days', category: 'soft', isHard: true, canToggle: true },
  { id: '13', label_zh: '當值主管平均分配', label_en: 'Supervisor quota balance', description_zh: '盡量平均分配當值主管次數', description_en: 'Balance duty supervisor assignments', category: 'soft', isHard: false, canToggle: true },
  { id: '14', label_zh: '個人偏好更期', label_en: 'Personal shift preference', description_zh: '盡量滿足員工偏好嘅更期', description_en: 'Try to accommodate staff shift preferences', category: 'soft', isHard: false, canToggle: true },
]

const DEMO_STAFF_HARD: StaffHardConstraint[] = [
  { id: '1', staffName: '王美玲', type: 'no_night', typeLabel_zh: '不做夜更', typeLabel_en: 'No night shift', detail: '健康原因，醫生證明', effectiveFrom: '2026-01-01', effectiveTo: '2026-12-31' },
  { id: '2', staffName: '李志雄', type: 'fixed_off', typeLabel_zh: '固定休息日', typeLabel_en: 'Fixed day off', detail: '逢星期日休息（宗教原因）', effectiveFrom: '2026-01-01', effectiveTo: '2027-12-31' },
  { id: '3', staffName: '陳小芳', type: 'max_hours', typeLabel_zh: '工時限制', typeLabel_en: 'Hours restriction', detail: '每週不超過40小時（兼職合約）', effectiveFrom: '2026-06-01', effectiveTo: '2026-12-31' },
]

const DEMO_IMPORTED: ImportedWorkerRule[] = [
  { id: '1', staffName: '阮氏花', shiftDuration: 12, restBetweenShifts: 12, monthlyDaysOff: 4, contractStart: '2026-03-01', contractEnd: '2028-02-28' },
  { id: '2', staffName: '陳文明', shiftDuration: 12, restBetweenShifts: 12, monthlyDaysOff: 4, contractStart: '2026-05-15', contractEnd: '2028-05-14' },
]

// ─── Main Component ─────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const isZH = lang === 'zh'
  const editable = canWrite(user?.role, 'settings')

  const [tab, setTab] = useState<Tab>('facility')
  const [facility, setFacility] = useState<FacilityConfig>(DEMO_FACILITY)
  const [toggles, setToggles] = useState<ConstraintToggle[]>(DEMO_TOGGLES)
  const [staffHard, setStaffHard] = useState<StaffHardConstraint[]>(DEMO_STAFF_HARD)
  const [imported, setImported] = useState<ImportedWorkerRule[]>(DEMO_IMPORTED)
  const [notice, setNotice] = useState('')

  const T = {
    title: isZH ? '院舍設定' : 'Facility Settings',
    sub: isZH ? '院舍配置 · 排班規則 · 員工限制 · 外勞管理' : 'Configuration · Constraints · Staff rules · Imported workers',
    facility: isZH ? '院舍配置' : 'Facility',
    constraints: isZH ? '排班規則' : 'Constraints',
    staffHard: isZH ? '員工限制' : 'Staff Rules',
    events: isZH ? '特別活動' : 'Events',
    imported: isZH ? '外勞管理' : 'Imported',
    preferences: isZH ? '個人偏好' : 'Preferences',
    save: isZH ? '儲存' : 'Save',
    add: isZH ? '新增' : 'Add',
    remove: isZH ? '刪除' : 'Remove',
    saved: isZH ? '已儲存' : 'Saved',
    hard: 'Hard',
    soft: 'Soft',
    enforce: isZH ? '強制執行' : 'Enforce',
    tryBest: isZH ? '盡量滿足' : 'Try best',
    locked: isZH ? '（法規要求，不可更改）' : '(Regulatory, cannot change)',
    toggleable: isZH ? '可切換' : 'Toggleable',
  }

  const TABS: Array<{ key: Tab; label: string }> = [
    { key: 'facility', label: T.facility },
    { key: 'constraints', label: T.constraints },
    { key: 'staffHard', label: T.staffHard },
    { key: 'imported', label: T.imported },
  ]

  return (
    <div className="p-5 space-y-4">
      <header>
        <h1 className="text-lg font-bold text-gray-800">{T.title}</h1>
        <p className="text-[11px] text-gray-400">{T.sub}</p>
      </header>

      {notice && (
        <div className="rounded-lg border px-3 py-2 text-[11px]"
             style={{ background: '#f0fdf4', borderColor: '#bbf7d0', color: '#15803d' }}>
          {notice}
        </div>
      )}

      <div className="flex gap-1 border-b" style={{ borderColor: '#e5e7eb' }}>
        {TABS.map(({ key, label }) => (
          <button key={key} onClick={() => setTab(key)}
            className="px-3 py-2 text-[11px] border-b-2 -mb-px transition-colors"
            style={{
              color: tab === key ? PINK : '#6b7280',
              borderBottomColor: tab === key ? PINK : 'transparent',
              fontWeight: tab === key ? 600 : 400,
            }}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'facility' && (
        <FacilityTab config={facility} setConfig={setFacility}
                     editable={editable} T={T} isZH={isZH}
                     onSave={() => setNotice(T.saved)} />
      )}
      {tab === 'constraints' && (
        <ConstraintTogglesTab toggles={toggles} setToggles={setToggles}
                              editable={editable} T={T} isZH={isZH}
                              onSave={() => setNotice(T.saved)} />
      )}
      {tab === 'staffHard' && (
        <StaffHardTab items={staffHard} setItems={setStaffHard}
                      editable={editable} T={T} isZH={isZH}
                      onSave={() => setNotice(T.saved)} />
      )}
      {tab === 'imported' && (
        <ImportedTab items={imported} setItems={setImported}
                     editable={editable} T={T} isZH={isZH}
                     onSave={() => setNotice(T.saved)} />
      )}
    </div>
  )
}

type Labels = Record<string, string>

// ─── Facility Configuration Tab ─────────────────────────────────────────────

function FacilityTab({ config, setConfig, editable, T, isZH, onSave }: {
  config: FacilityConfig; setConfig: (c: FacilityConfig) => void
  editable: boolean; T: Labels; isZH: boolean; onSave: () => void
}) {
  const update = (key: keyof FacilityConfig, value: string | number) =>
    setConfig({ ...config, [key]: value })

  return (
    <div className="space-y-4">
      {/* Basic Info */}
      <div className={`${CARD} p-4 space-y-3`} style={CARD_STYLE}>
        <h3 className="text-[12px] font-semibold text-gray-700">
          {isZH ? '基本資料' : 'Basic Information'}
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? '院舍名稱' : 'Facility Name'}</div>
            <input className={INPUT} style={INPUT_STYLE} value={config.facilityName}
                   disabled={!editable}
                   onChange={(e) => update('facilityName', e.target.value)} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? '機構代碼' : 'Org Code'}</div>
            <input className={INPUT} style={INPUT_STYLE} value={config.orgCode}
                   disabled={!editable}
                   onChange={(e) => update('orgCode', e.target.value)} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? '住客人數' : 'Resident Count'}</div>
            <input type="number" className={INPUT} style={INPUT_STYLE}
                   value={config.residentCount} disabled={!editable}
                   onChange={(e) => update('residentCount', parseInt(e.target.value) || 0)} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? 'SWD 牌照號碼' : 'SWD License No.'}</div>
            <input className={INPUT} style={INPUT_STYLE} value={config.swdLicenseNo}
                   disabled={!editable}
                   onChange={(e) => update('swdLicenseNo', e.target.value)} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? '照顧級別' : 'Care Level'}</div>
            <select className={INPUT} style={INPUT_STYLE} value={config.careLevel}
                    disabled={!editable}
                    onChange={(e) => update('careLevel', e.target.value)}>
              <option value="low">{isZH ? '低度照顧' : 'Low care'}</option>
              <option value="moderate">{isZH ? '中度照顧' : 'Moderate care'}</option>
              <option value="high">{isZH ? '高度照顧' : 'High care'}</option>
            </select>
          </label>
        </div>
      </div>

      {/* Specific Hours (特定鐘點) */}
      <div className={`${CARD} p-4 space-y-3`} style={CARD_STYLE}>
        <h3 className="text-[12px] font-semibold text-gray-700">
          {isZH ? '特定鐘點設定' : 'Specified Hours Configuration'}
        </h3>
        <p className="text-[10px] text-gray-400">
          {isZH ? '根據 SWD 實務守則，院舍須在特定鐘點時段內維持法定人手比例。' : 'Per SWD Code of Practice, facility must maintain statutory staffing ratio during specified hours.'}
        </p>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? '開始時間' : 'Start Time'}</div>
            <input type="time" className={INPUT} style={INPUT_STYLE}
                   value={config.specificHoursStart} disabled={!editable}
                   onChange={(e) => update('specificHoursStart', e.target.value)} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? '結束時間' : 'End Time'}</div>
            <input type="time" className={INPUT} style={INPUT_STYLE}
                   value={config.specificHoursEnd} disabled={!editable}
                   onChange={(e) => update('specificHoursEnd', e.target.value)} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? '簽署生效日期' : 'Effective Date'}</div>
            <input type="date" className={INPUT} style={INPUT_STYLE}
                   value={config.specificHoursEffective} disabled={!editable}
                   onChange={(e) => update('specificHoursEffective', e.target.value)} />
          </label>
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? '終止日期' : 'Expiry Date'}</div>
            <input type="date" className={INPUT} style={INPUT_STYLE}
                   value={config.specificHoursExpiry} disabled={!editable}
                   onChange={(e) => update('specificHoursExpiry', e.target.value)} />
          </label>
        </div>
      </div>

      {editable && (
        <button onClick={onSave}
          className="px-4 py-2 rounded text-[11px] text-white"
          style={{ background: PINK }}>
          {T.save}
        </button>
      )}
    </div>
  )
}

// ─── Constraint Toggles Tab ─────────────────────────────────────────────────

function ConstraintTogglesTab({ toggles, setToggles, editable, T, isZH, onSave }: {
  toggles: ConstraintToggle[]; setToggles: (t: ConstraintToggle[]) => void
  editable: boolean; T: Labels; isZH: boolean; onSave: () => void
}) {
  const handleToggle = (id: string) => {
    setToggles(toggles.map((t) =>
      t.id === id && t.canToggle ? { ...t, isHard: !t.isHard } : t
    ))
  }

  const hardCount = toggles.filter((t) => t.isHard).length
  const softCount = toggles.filter((t) => !t.isHard).length

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex gap-3">
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: '#dc2626' }} />
          <span className="text-[10px] text-gray-600">Hard: {hardCount}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: '#9ca3af' }} />
          <span className="text-[10px] text-gray-600">Soft: {softCount}</span>
        </div>
      </div>

      {/* Toggles List */}
      <div className={CARD} style={CARD_STYLE}>
        <table className="w-full text-[11px]">
          <thead className="text-gray-400" style={{ background: '#f9fafb' }}>
            <tr>
              <th className="text-left px-3 py-2">{isZH ? '規則' : 'Rule'}</th>
              <th className="text-left px-3 py-2">{isZH ? '說明' : 'Description'}</th>
              <th className="text-center px-3 py-2">{isZH ? '類型' : 'Type'}</th>
              <th className="text-center px-3 py-2">{isZH ? '狀態' : 'Status'}</th>
            </tr>
          </thead>
          <tbody>
            {toggles.map((t) => (
              <tr key={t.id} className="border-t" style={{ borderColor: '#f3f4f6' }}>
                <td className="px-3 py-2.5 text-gray-700 font-medium">
                  {isZH ? t.label_zh : t.label_en}
                </td>
                <td className="px-3 py-2.5 text-gray-500 max-w-[200px]">
                  {isZH ? t.description_zh : t.description_en}
                </td>
                <td className="px-3 py-2.5 text-center">
                  <span className="inline-block px-2 py-0.5 rounded text-[9px] font-semibold"
                    style={{
                      background: t.isHard ? '#fef2f2' : '#f3f4f6',
                      color: t.isHard ? '#dc2626' : '#6b7280',
                    }}>
                    {t.isHard ? T.hard : T.soft}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-center">
                  {t.canToggle ? (
                    <button
                      onClick={() => editable && handleToggle(t.id)}
                      disabled={!editable}
                      className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
                      style={{ background: t.isHard ? PINK : '#d1d5db' }}
                    >
                      <span className="inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform"
                        style={{ transform: t.isHard ? 'translateX(18px)' : 'translateX(3px)' }} />
                    </button>
                  ) : (
                    <span className="text-[9px] text-gray-400">🔒 {T.locked}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="text-[10px] text-gray-400">
        {isZH
          ? '🔒 = 法規要求，不可更改為 Soft。可切換項目由院長決定是否強制執行。'
          : '🔒 = Regulatory requirement, cannot be changed to Soft. Toggleable items can be set by superintendent.'}
      </div>

      {editable && (
        <button onClick={onSave}
          className="px-4 py-2 rounded text-[11px] text-white"
          style={{ background: PINK }}>
          {T.save}
        </button>
      )}
    </div>
  )
}

// ─── Staff Hard Constraints Tab ─────────────────────────────────────────────

function StaffHardTab({ items, setItems, editable, T, isZH, onSave }: {
  items: StaffHardConstraint[]; setItems: (i: StaffHardConstraint[]) => void
  editable: boolean; T: Labels; isZH: boolean; onSave: () => void
}) {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ staffName: '', type: 'no_night', detail: '', from: '', to: '' })

  const TYPES = [
    { value: 'no_night', zh: '不做夜更', en: 'No night shift' },
    { value: 'fixed_off', zh: '固定休息日', en: 'Fixed day off' },
    { value: 'max_hours', zh: '工時限制', en: 'Hours restriction' },
    { value: 'no_consecutive', zh: '不連續上班', en: 'No consecutive shifts' },
    { value: 'specific_unit', zh: '指定樓層', en: 'Specific unit only' },
    { value: 'medical', zh: '醫療限制', en: 'Medical restriction' },
    { value: 'custom', zh: '其他', en: 'Other' },
  ]

  const handleAdd = () => {
    if (!form.staffName || !form.detail) return
    const typeObj = TYPES.find((t) => t.value === form.type)!
    const newItem: StaffHardConstraint = {
      id: Date.now().toString(),
      staffName: form.staffName,
      type: form.type,
      typeLabel_zh: typeObj.zh,
      typeLabel_en: typeObj.en,
      detail: form.detail,
      effectiveFrom: form.from,
      effectiveTo: form.to,
    }
    setItems([...items, newItem])
    setForm({ staffName: '', type: 'no_night', detail: '', from: '', to: '' })
    setShowForm(false)
  }

  const handleRemove = (id: string) => {
    setItems(items.filter((i) => i.id !== id))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[10px] text-gray-400">
          {isZH
            ? '個人硬性限制：排班引擎必須遵守，不會違反。院長/Scheduler 可自行新增。'
            : 'Personal hard restrictions: the engine must respect these. Superintendent/Scheduler can add.'}
        </p>
        {editable && (
          <button onClick={() => setShowForm(!showForm)}
            className="px-3 py-1.5 rounded text-[11px] text-white"
            style={{ background: PINK }}>
            {T.add}
          </button>
        )}
      </div>

      {/* Add Form */}
      {showForm && (
        <div className={`${CARD} p-3 space-y-2`} style={CARD_STYLE}>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '員工姓名' : 'Staff Name'}</div>
              <input className={INPUT} style={INPUT_STYLE} value={form.staffName}
                     onChange={(e) => setForm({ ...form, staffName: e.target.value })} />
            </label>
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '限制類型' : 'Type'}</div>
              <select className={INPUT} style={INPUT_STYLE} value={form.type}
                      onChange={(e) => setForm({ ...form, type: e.target.value })}>
                {TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{isZH ? t.zh : t.en}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="text-[10px] text-gray-500">
            <div className="mb-1">{isZH ? '詳細說明' : 'Detail'}</div>
            <input className={INPUT} style={INPUT_STYLE} value={form.detail}
                   onChange={(e) => setForm({ ...form, detail: e.target.value })} />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '生效日期' : 'From'}</div>
              <input type="date" className={INPUT} style={INPUT_STYLE} value={form.from}
                     onChange={(e) => setForm({ ...form, from: e.target.value })} />
            </label>
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '到期日期' : 'Until'}</div>
              <input type="date" className={INPUT} style={INPUT_STYLE} value={form.to}
                     onChange={(e) => setForm({ ...form, to: e.target.value })} />
            </label>
          </div>
          <div className="flex gap-2">
            <button onClick={handleAdd}
              className="px-3 py-1.5 rounded text-[11px] text-white"
              style={{ background: PINK }}>
              {isZH ? '確認新增' : 'Confirm'}
            </button>
            <button onClick={() => setShowForm(false)}
              className="px-3 py-1.5 rounded text-[11px] border text-gray-600"
              style={{ borderColor: '#e5e7eb' }}>
              {isZH ? '取消' : 'Cancel'}
            </button>
          </div>
        </div>
      )}

      {/* List */}
      <div className={CARD} style={CARD_STYLE}>
        {items.length === 0 ? (
          <div className="p-4 text-[11px] text-gray-400">
            {isZH ? '尚無個人限制' : 'No personal restrictions configured'}
          </div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-gray-400" style={{ background: '#f9fafb' }}>
              <tr>
                <th className="text-left px-3 py-2">{isZH ? '員工' : 'Staff'}</th>
                <th className="text-left px-3 py-2">{isZH ? '類型' : 'Type'}</th>
                <th className="text-left px-3 py-2">{isZH ? '說明' : 'Detail'}</th>
                <th className="text-left px-3 py-2">{isZH ? '有效期' : 'Period'}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t" style={{ borderColor: '#f3f4f6' }}>
                  <td className="px-3 py-2.5 text-gray-700 font-medium">{item.staffName}</td>
                  <td className="px-3 py-2.5">
                    <span className="inline-block px-2 py-0.5 rounded text-[9px]"
                      style={{ background: '#fef2f2', color: '#dc2626' }}>
                      {isZH ? item.typeLabel_zh : item.typeLabel_en}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-gray-500">{item.detail}</td>
                  <td className="px-3 py-2.5 text-gray-400">
                    {item.effectiveFrom} ~ {item.effectiveTo}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    {editable && (
                      <button className="text-[10px] text-gray-400 hover:text-rose-600"
                        onClick={() => handleRemove(item.id)}>
                        {T.remove}
                      </button>
                    )}
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

// ─── Imported Workers Tab ───────────────────────────────────────────────────

function ImportedTab({ items, setItems, editable, T, isZH, onSave }: {
  items: ImportedWorkerRule[]; setItems: (i: ImportedWorkerRule[]) => void
  editable: boolean; T: Labels; isZH: boolean; onSave: () => void
}) {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    staffName: '', shiftDuration: '12', restBetweenShifts: '12',
    monthlyDaysOff: '4', contractStart: '', contractEnd: '',
  })

  const handleAdd = () => {
    if (!form.staffName) return
    const newItem: ImportedWorkerRule = {
      id: Date.now().toString(),
      staffName: form.staffName,
      shiftDuration: parseInt(form.shiftDuration),
      restBetweenShifts: parseInt(form.restBetweenShifts),
      monthlyDaysOff: parseInt(form.monthlyDaysOff),
      contractStart: form.contractStart,
      contractEnd: form.contractEnd,
    }
    setItems([...items, newItem])
    setForm({ staffName: '', shiftDuration: '12', restBetweenShifts: '12', monthlyDaysOff: '4', contractStart: '', contractEnd: '' })
    setShowForm(false)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] text-gray-400">
            {isZH
              ? '外勞（Imported Staff）規則：每更12小時、更與更之間12小時休息、每月4日假。'
              : 'Imported worker rules: 12h shifts, 12h rest between shifts, 4 days off/month.'}
          </p>
          <p className="text-[10px] text-gray-400 mt-0.5">
            {isZH
              ? '⚠️ 以上為 Hard Constraint，排班引擎必須遵守。'
              : '⚠️ These are Hard Constraints the engine must respect.'}
          </p>
        </div>
        {editable && (
          <button onClick={() => setShowForm(!showForm)}
            className="px-3 py-1.5 rounded text-[11px] text-white shrink-0"
            style={{ background: PINK }}>
            {T.add}
          </button>
        )}
      </div>

      {/* Add Form */}
      {showForm && (
        <div className={`${CARD} p-3 space-y-2`} style={CARD_STYLE}>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '員工姓名' : 'Staff Name'}</div>
              <input className={INPUT} style={INPUT_STYLE} value={form.staffName}
                     onChange={(e) => setForm({ ...form, staffName: e.target.value })} />
            </label>
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '每更時數' : 'Shift Duration (h)'}</div>
              <input type="number" className={INPUT} style={INPUT_STYLE} value={form.shiftDuration}
                     onChange={(e) => setForm({ ...form, shiftDuration: e.target.value })} />
            </label>
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '更間休息（小時）' : 'Rest Between (h)'}</div>
              <input type="number" className={INPUT} style={INPUT_STYLE} value={form.restBetweenShifts}
                     onChange={(e) => setForm({ ...form, restBetweenShifts: e.target.value })} />
            </label>
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '每月假日' : 'Monthly Days Off'}</div>
              <input type="number" className={INPUT} style={INPUT_STYLE} value={form.monthlyDaysOff}
                     onChange={(e) => setForm({ ...form, monthlyDaysOff: e.target.value })} />
            </label>
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '合約開始' : 'Contract Start'}</div>
              <input type="date" className={INPUT} style={INPUT_STYLE} value={form.contractStart}
                     onChange={(e) => setForm({ ...form, contractStart: e.target.value })} />
            </label>
            <label className="text-[10px] text-gray-500">
              <div className="mb-1">{isZH ? '合約結束' : 'Contract End'}</div>
              <input type="date" className={INPUT} style={INPUT_STYLE} value={form.contractEnd}
                     onChange={(e) => setForm({ ...form, contractEnd: e.target.value })} />
            </label>
          </div>
          <div className="flex gap-2">
            <button onClick={handleAdd}
              className="px-3 py-1.5 rounded text-[11px] text-white"
              style={{ background: PINK }}>
              {isZH ? '確認新增' : 'Confirm'}
            </button>
            <button onClick={() => setShowForm(false)}
              className="px-3 py-1.5 rounded text-[11px] border text-gray-600"
              style={{ borderColor: '#e5e7eb' }}>
              {isZH ? '取消' : 'Cancel'}
            </button>
          </div>
        </div>
      )}

      {/* List */}
      <div className={CARD} style={CARD_STYLE}>
        {items.length === 0 ? (
          <div className="p-4 text-[11px] text-gray-400">
            {isZH ? '尚無外勞紀錄' : 'No imported workers configured'}
          </div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-gray-400" style={{ background: '#f9fafb' }}>
              <tr>
                <th className="text-left px-3 py-2">{isZH ? '員工' : 'Staff'}</th>
                <th className="text-center px-3 py-2">{isZH ? '每更' : 'Shift'}</th>
                <th className="text-center px-3 py-2">{isZH ? '休息' : 'Rest'}</th>
                <th className="text-center px-3 py-2">{isZH ? '月假' : 'Off/mo'}</th>
                <th className="text-left px-3 py-2">{isZH ? '合約期' : 'Contract'}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t" style={{ borderColor: '#f3f4f6' }}>
                  <td className="px-3 py-2.5 text-gray-700 font-medium">{item.staffName}</td>
                  <td className="px-3 py-2.5 text-center text-gray-600">{item.shiftDuration}h</td>
                  <td className="px-3 py-2.5 text-center text-gray-600">{item.restBetweenShifts}h</td>
                  <td className="px-3 py-2.5 text-center text-gray-600">{item.monthlyDaysOff}{isZH ? '日' : 'd'}</td>
                  <td className="px-3 py-2.5 text-gray-400">
                    {item.contractStart} ~ {item.contractEnd}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    {editable && (
                      <button className="text-[10px] text-gray-400 hover:text-rose-600"
                        onClick={() => setItems(items.filter((i) => i.id !== item.id))}>
                        {T.remove}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editable && (
        <button onClick={onSave}
          className="px-4 py-2 rounded text-[11px] text-white"
          style={{ background: PINK }}>
          {T.save}
        </button>
      )}
    </div>
  )
}

