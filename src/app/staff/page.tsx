'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '@/lib/api'
import type { ApiStaff, StaffDetail, StaffQualification } from '@/lib/apiTypes'
import { useAuth } from '@/components/layout/AuthContext'
import { useLang } from '@/components/layout/LanguageContext'
import { canWrite } from '@/lib/permissions'
import { AddStaffModal } from '@/components/staff/AddStaffModal'
import {
  knownStatusLabel,
  matchesStaffDirectoryFilter,
  sourceHours,
  staffInitials,
  toStaffDirectoryCard,
  type StaffDirectoryCard,
} from '@/components/staff/staff-view-model'

const PINK = '#E87891'

type Copy = {
  title: string
  people: string
  facility: string
  add: string
  refresh: string
  search: string
  allRoles: string
  role: string
  roleCode: string
  employment: string
  unit: string
  status: string
  notProvided: string
  loading: string
  loadError: string
  retry: string
  empty: string
  certificates: string
  noCertificates: string
  scheduled: string
  contracted: string
  view: string
  close: string
  profile: string
  profileLoading: string
  profileLoadError: string
  sourceId: string
  periodInformation: string
  capabilities: string
  medicationAudited: string
  mentor: string
  yes: string
  no: string
  qualificationRecords: string
  noQualifications: string
  qualificationsUnavailable: string
  active: string
  inactive: string
  effective: string
  expires: string
  noDate: string
  rosterHistory: string
  noHistory: string
  historyUnavailable: string
  shift: string
  time: string
  tasks: string
  skillsTitle: string
  skillsUnavailable: string
  skillsHint: string
}

function copyFor(isZH: boolean): Copy {
  return isZH ? {
    title: '員工檔案', people: '位員工', facility: '院舍', add: '新增員工', refresh: '重新整理',
    search: '搜尋姓名、職級、單位或聘用類型…', allRoles: '所有職級', role: '職級', roleCode: '職級代碼',
    employment: '聘用類型', unit: '所屬單位', status: '狀態', notProvided: '未提供',
    loading: '正在載入員工檔案…', loadError: '未能載入員工檔案。不會以示範資料代替缺失資料。', retry: '重試',
    empty: '沒有符合條件的員工。', certificates: '證書記錄', noCertificates: '未有證書記錄。',
    scheduled: '本期已排工時', contracted: '本期合約工時', view: '查看檔案', close: '關閉',
    profile: '員工檔案', profileLoading: '正在重新整理員工檔案…',
    profileLoadError: '未能重新整理詳細檔案；下方只顯示已載入的目錄資料。', sourceId: '員工記錄 ID',
    periodInformation: '本期更表資料', capabilities: '已記錄資格', medicationAudited: '藥物核查資格', mentor: '可帶教新人',
    yes: '是', no: '否', qualificationRecords: '資格記錄', noQualifications: '未有資格記錄。',
    qualificationsUnavailable: '資格記錄暫時未能載入。', active: '有效', inactive: '非有效',
    effective: '生效日期', expires: '到期日期', noDate: '未記錄', rosterHistory: '更表紀錄',
    noHistory: '未有更表紀錄。', historyUnavailable: '更表紀錄在詳細資料可用後才會顯示。', shift: '更別', time: '時段', tasks: '任務',
    skillsTitle: '技能及發展評估',
    skillsUnavailable: '未評估／暫未提供',
    skillsHint: '目前 MVP API 未提供可儲存的管理人員技能評估記錄；不會以證書、資格、更表或 AI 推斷分數代替。',
  } : {
    title: 'Staff Portfolio', people: 'staff members', facility: 'Facility', add: 'Add staff', refresh: 'Refresh',
    search: 'Search name, role, unit or employment type…', allRoles: 'All role codes', role: 'Role', roleCode: 'Role code',
    employment: 'Employment type', unit: 'Unit', status: 'Status', notProvided: 'Not provided',
    loading: 'Loading staff records…', loadError: 'Staff records could not be loaded. Missing data is not replaced with demo records.', retry: 'Retry',
    empty: 'No matching staff.', certificates: 'Certificates on record', noCertificates: 'No certificates on record.',
    scheduled: 'Rostered this period', contracted: 'Contracted this period', view: 'View profile', close: 'Close',
    profile: 'Staff profile', profileLoading: 'Refreshing staff profile…',
    profileLoadError: 'The detailed profile could not be refreshed; only the loaded directory record is shown below.', sourceId: 'Staff record ID',
    periodInformation: 'Current roster-period data', capabilities: 'Recorded capabilities', medicationAudited: 'Medication audited', mentor: 'Can mentor new staff',
    yes: 'Yes', no: 'No', qualificationRecords: 'Qualification records', noQualifications: 'No qualification records returned.',
    qualificationsUnavailable: 'Qualification records are temporarily unavailable.', active: 'Active', inactive: 'Inactive',
    effective: 'Effective from', expires: 'Expires', noDate: 'Not recorded', rosterHistory: 'Shift history',
    noHistory: 'No shift history returned.', historyUnavailable: 'Shift history is available after the detailed profile loads.', shift: 'Shift', time: 'Time', tasks: 'Tasks',
    skillsTitle: 'Skills & development assessment',
    skillsUnavailable: 'Not assessed / unavailable',
    skillsHint: 'The current MVP API has no persisted manager skill-assessment record. Certificates, qualifications, roster history and AI output are not substituted as scores.',
  }
}

function StatusBadge({ status, isZH }: { status: string | null; isZH: boolean }) {
  if (!status) return null
  const tone = status === 'on_leave'
    ? 'border-rose-100 bg-rose-50 text-rose-700'
    : status === 'scheduled'
      ? 'border-blue-100 bg-blue-50 text-blue-700'
      : status === 'available'
        ? 'border-emerald-100 bg-emerald-50 text-emerald-700'
        : 'border-slate-200 bg-slate-50 text-slate-600'
  return <span className={`max-w-full break-words rounded-full border px-2.5 py-1 text-[11px] font-semibold emma-reflow-text ${tone}`}>{knownStatusLabel(status, isZH)}</span>
}

function Field({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded-2xl border border-slate-100 bg-slate-50 p-3">
    <dt className="break-words text-xs font-semibold text-slate-500 emma-reflow-text">{label}</dt>
    <dd className="mt-1 break-words text-sm font-bold text-slate-900 emma-reflow-text">{value}</dd>
  </div>
}

function CertificateList({ certificates, empty }: { certificates: string[]; empty: string }) {
  if (certificates.length === 0) return <p className="text-xs text-slate-500">{empty}</p>
  return <div className="flex flex-wrap gap-2 emma-reflow-wrap">
    {certificates.map((certificate) => <span key={certificate} className="max-w-full break-words rounded-lg border border-pink-100 bg-pink-50 px-2.5 py-1 text-xs font-semibold text-pink-700 emma-reflow-text">{certificate}</span>)}
  </div>
}

function StaffProfilePanel({ staff, onClose }: { staff: ApiStaff; onClose: () => void }) {
  const { lang } = useLang()
  const isZH = lang === 'zh'
  const copy = copyFor(isZH)
  const [detail, setDetail] = useState<StaffDetail | null>(null)
  const [qualifications, setQualifications] = useState<StaffQualification[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailError, setDetailError] = useState(false)
  const [qualificationError, setQualificationError] = useState(false)

  useEffect(() => {
    let cancelled = false
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    setLoading(true)
    setDetail(null)
    setQualifications(null)
    setDetailError(false)
    setQualificationError(false)

    void api.staffDetail(staff.id)
      .then((result) => { if (!cancelled) setDetail(result) })
      .catch(() => { if (!cancelled) setDetailError(true) })
      .finally(() => { if (!cancelled) setLoading(false) })

    void api.staffQualifications({ staffId: staff.id })
      .then((result) => { if (!cancelled) setQualifications(result) })
      .catch(() => { if (!cancelled) setQualificationError(true) })

    return () => {
      cancelled = true
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [onClose, staff.id])

  const source = detail ?? staff
  const card = toStaffDirectoryCard(source)
  const certificates = Array.isArray(source.certificates) && source.certificates.length > 0
    ? source.certificates.map((certificate) => certificate.cert_type).filter(Boolean)
    : card.certificates

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-3 sm:p-6" onMouseDown={onClose}>
    <section role="dialog" aria-modal="true" aria-labelledby="staff-profile-title" className="flex max-h-[calc(100dvh-1.5rem)] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-pink-100 bg-white shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-pink-100 bg-gradient-to-r from-pink-50 via-white to-rose-50 px-5 py-5 sm:px-8 emma-reflow-wrap">
        <div className="flex min-w-0 items-start gap-3">
          <div aria-hidden className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-pink-100 bg-white text-base font-black text-pink-600 shadow-sm">{staffInitials(card)}</div>
          <div className="min-w-0">
            <p className="text-xs font-bold tracking-wide text-pink-700">Emma AI · {copy.profile}</p>
            <h2 id="staff-profile-title" className="mt-1 break-words text-xl font-extrabold text-slate-950 emma-reflow-text">{card.primaryName}</h2>
            {card.secondaryName && <p className="mt-1 break-words text-sm text-slate-600 emma-reflow-text">{card.secondaryName}</p>}
            <div className="mt-2 flex flex-wrap items-center gap-2 emma-reflow-wrap">
              <span className="max-w-full break-words rounded-full bg-pink-600 px-2.5 py-1 text-[11px] font-bold text-white emma-reflow-text">{card.roleCode}</span>
              <StatusBadge status={card.status} isZH={isZH} />
            </div>
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label={copy.close} className="flex min-h-10 min-w-10 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white px-2 text-xl font-semibold text-slate-600 transition-colors hover:bg-pink-50">×</button>
      </header>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-5 sm:p-8">
        {loading && <p role="status" className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">{copy.profileLoading}</p>}
        {detailError && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm leading-6 text-amber-800">{copy.profileLoadError}</p>}

        <section aria-labelledby="staff-core-record" className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 emma-reflow-wrap">
            <h3 id="staff-core-record" className="text-base font-bold text-slate-900">{copy.profile}</h3>
            <span className="max-w-full break-all text-xs text-slate-500 emma-reflow-text">{copy.sourceId}: {card.id}</span>
          </div>
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 emma-reflow-stack">
            <Field label={copy.roleCode} value={card.roleCode} />
            <Field label={copy.employment} value={card.employmentType || copy.notProvided} />
            <Field label={copy.unit} value={card.unitName ?? copy.notProvided} />
            <Field label={copy.status} value={card.status ? knownStatusLabel(card.status, isZH) : copy.notProvided} />
          </dl>
        </section>

        <section aria-labelledby="staff-period-record" className="space-y-3">
          <h3 id="staff-period-record" className="text-base font-bold text-slate-900">{copy.periodInformation}</h3>
          <p className="text-xs leading-5 text-slate-500">{isZH ? '只顯示 API 回傳的目前更表期資料；不會推算月度結算。' : 'Only current roster-period values returned by the API are shown; no monthly accounting is inferred.'}</p>
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 emma-reflow-stack">
            <Field label={copy.scheduled} value={sourceHours(card.scheduledHours, copy.notProvided)} />
            <Field label={copy.contracted} value={sourceHours(card.contractedPeriodHours, copy.notProvided)} />
          </dl>
        </section>

        <section aria-labelledby="staff-credentials-record" className="space-y-3">
          <h3 id="staff-credentials-record" className="text-base font-bold text-slate-900">{copy.certificates}</h3>
          <CertificateList certificates={certificates} empty={copy.noCertificates} />
        </section>

        <section aria-labelledby="staff-capability-record" className="space-y-3">
          <h3 id="staff-capability-record" className="text-base font-bold text-slate-900">{copy.capabilities}</h3>
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 emma-reflow-stack">
            <Field label={copy.medicationAudited} value={source.is_audited_for_medication ? copy.yes : copy.no} />
            <Field label={copy.mentor} value={source.is_mentor ? copy.yes : copy.no} />
          </dl>
        </section>

        <section aria-labelledby="staff-qualification-record" className="space-y-3">
          <h3 id="staff-qualification-record" className="text-base font-bold text-slate-900">{copy.qualificationRecords}</h3>
          {qualificationError && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">{copy.qualificationsUnavailable}</p>}
          {qualifications && qualifications.length === 0 && <p className="text-xs text-slate-500">{copy.noQualifications}</p>}
          {qualifications && qualifications.length > 0 && <div className="space-y-2">
            {qualifications.map((qualification) => <article key={qualification.id} className="rounded-2xl border border-slate-200 bg-white p-3">
              <div className="flex flex-wrap items-start justify-between gap-2 emma-reflow-wrap">
                <h4 className="min-w-0 break-words text-sm font-bold text-slate-800 emma-reflow-text">{qualification.qualification_type}</h4>
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${qualification.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>{qualification.is_active ? copy.active : copy.inactive}</span>
              </div>
              <dl className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 emma-reflow-stack">
                <Field label={copy.effective} value={qualification.effective_from ?? copy.noDate} />
                <Field label={copy.expires} value={qualification.expiry_date ?? copy.noDate} />
              </dl>
            </article>)}
          </div>}
        </section>

        <section aria-labelledby="staff-skills-record" className="rounded-2xl border border-pink-100 bg-pink-50/70 p-4">
          <div className="flex flex-wrap items-start justify-between gap-2 emma-reflow-wrap">
            <div className="min-w-0">
              <h3 id="staff-skills-record" className="break-words text-base font-bold text-slate-900 emma-reflow-text">{copy.skillsTitle}</h3>
              <p className="mt-1 break-words text-xs leading-5 text-slate-600 emma-reflow-text">{copy.skillsHint}</p>
            </div>
            <span className="max-w-full break-words rounded-full border border-pink-100 bg-white px-2.5 py-1 text-xs font-semibold text-pink-700 emma-reflow-text">{copy.skillsUnavailable}</span>
          </div>
        </section>

        <section aria-labelledby="staff-history-record" className="space-y-3">
          <h3 id="staff-history-record" className="text-base font-bold text-slate-900">{copy.rosterHistory}</h3>
          {!detail && !detailError && <p className="text-xs text-slate-500">{copy.historyUnavailable}</p>}
          {detail && detail.shift_history.length === 0 && <p className="text-xs text-slate-500">{copy.noHistory}</p>}
          {detail && detail.shift_history.length > 0 && <div className="space-y-2">
            {detail.shift_history.map((history, index) => <article key={`${history.date}-${history.shift_type ?? 'none'}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-3">
              <div className="flex flex-wrap items-start justify-between gap-3 emma-reflow-wrap">
                <div className="min-w-0"><p className="text-xs font-semibold text-slate-500">{history.date}</p><p className="mt-1 break-words text-sm font-bold text-slate-900 emma-reflow-text">{copy.shift}: {history.shift_type ?? copy.notProvided}</p></div>
                <p className="max-w-full break-words text-xs text-slate-600 emma-reflow-text">{copy.time}: {history.start_time && history.end_time ? `${history.start_time} – ${history.end_time}` : copy.notProvided}</p>
              </div>
              {history.tasks.length > 0 && <p className="mt-2 break-words text-xs leading-5 text-slate-600 emma-reflow-text">{copy.tasks}: {history.tasks.join(', ')}</p>}
            </article>)}
          </div>}
          {detailError && <p className="text-xs text-slate-500">{copy.historyUnavailable}</p>}
        </section>
      </div>

      <footer className="flex shrink-0 justify-end border-t border-slate-200 px-5 py-4 sm:px-8"><button type="button" onClick={onClose} className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-pink-50">{copy.close}</button></footer>
    </section>
  </div>
}

function StaffCard({ card, isZH, copy, onSelect }: { card: StaffDirectoryCard; isZH: boolean; copy: Copy; onSelect: () => void }) {
  return <article data-staff-id={card.id} className="group min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:border-pink-200 hover:shadow-md">
    <div className="flex items-start gap-3">
      <div aria-hidden className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-pink-100 bg-pink-50 text-sm font-black text-pink-600 transition-transform group-hover:scale-105">{staffInitials(card)}</div>
      <div className="min-w-0 flex-1">
        <button type="button" onClick={onSelect} className="block max-w-full break-words text-left text-sm font-bold text-slate-950 transition-colors hover:text-pink-700 hover:underline emma-reflow-text">{card.primaryName}</button>
        {card.secondaryName && <p className="mt-1 break-words text-xs text-slate-500 emma-reflow-text">{card.secondaryName}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-2 emma-reflow-wrap">
          <span className="max-w-full break-words rounded-full bg-pink-600 px-2.5 py-1 text-[11px] font-bold text-white emma-reflow-text">{card.roleCode}</span>
          <StatusBadge status={card.status} isZH={isZH} />
        </div>
      </div>
    </div>

    <dl className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 emma-reflow-stack">
      <Field label={copy.unit} value={card.unitName ?? copy.notProvided} />
      <Field label={copy.employment} value={card.employmentType || copy.notProvided} />
      <Field label={copy.scheduled} value={sourceHours(card.scheduledHours, copy.notProvided)} />
      <Field label={copy.contracted} value={sourceHours(card.contractedPeriodHours, copy.notProvided)} />
    </dl>

    <div className="mt-4 border-t border-slate-100 pt-3">
      <p className="mb-2 text-xs font-bold text-slate-600">{copy.certificates}</p>
      <CertificateList certificates={card.certificates} empty={copy.noCertificates} />
    </div>

    <div className="mt-4 border-t border-slate-100 pt-3"><button type="button" onClick={onSelect} className="text-sm font-bold text-pink-700 hover:underline">{copy.view} →</button></div>
  </article>
}

export default function StaffPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const isZH = lang === 'zh'
  const copy = copyFor(isZH)
  const [staffRows, setStaffRows] = useState<ApiStaff[] | null>(null)
  const [directoryError, setDirectoryError] = useState(false)
  const [search, setSearch] = useState('')
  const [roleCode, setRoleCode] = useState('ALL')
  const [selected, setSelected] = useState<ApiStaff | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const requestSequence = useRef(0)
  const canWriteStaff = canWrite(user?.role, 'staff.profile_write')

  const reloadStaff = useCallback(async () => {
    const sequence = ++requestSequence.current
    setStaffRows(null)
    setDirectoryError(false)
    try {
      const rows = await api.listStaff()
      if (sequence === requestSequence.current) setStaffRows(rows)
    } catch {
      if (sequence === requestSequence.current) {
        setStaffRows([])
        setDirectoryError(true)
      }
    }
  }, [])

  useEffect(() => {
    void reloadStaff()
    return () => { requestSequence.current += 1 }
  }, [reloadStaff, user?.facilityId, user?.userId])

  const cards = useMemo(() => (staffRows ?? []).map(toStaffDirectoryCard), [staffRows])
  const roleCodes = useMemo(() => Array.from(new Set(cards.map((card) => card.roleCode))).sort(), [cards])
  const filteredCards = useMemo(
    () => cards.filter((card) => matchesStaffDirectoryFilter(card, search, roleCode)),
    [cards, search, roleCode],
  )

  useEffect(() => {
    if (roleCode !== 'ALL' && !roleCodes.includes(roleCode)) setRoleCode('ALL')
  }, [roleCode, roleCodes])

  const selectedCurrentRow = selected && staffRows?.find((row) => row.id === selected.id)

  return <div className="min-w-0 space-y-5 p-4 sm:p-5">
    <header className="flex flex-wrap items-start justify-between gap-4 emma-reflow-wrap">
      <div className="flex min-w-0 items-center gap-3">
        <img src="/icons/emma-badge.png" width={48} height={48} alt="Emma AI" className="h-12 w-12 shrink-0 rounded-2xl border border-pink-100 bg-white object-contain shadow-sm" />
        <div className="min-w-0">
          <p className="text-xs font-bold tracking-wide text-pink-700">Emma AI</p>
          <h1 className="break-words text-xl font-extrabold text-slate-950 emma-reflow-text">{copy.title}</h1>
          <p className="mt-1 break-words text-xs text-slate-500 emma-reflow-text">{staffRows ? `${staffRows.length} ${copy.people}` : copy.loading}{user?.facilityName ? ` · ${copy.facility}: ${user.facilityName}` : ''}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 emma-reflow-wrap">
        {notice && <p role="status" className="max-w-full break-words text-xs font-semibold text-emerald-700 emma-reflow-text">{notice}</p>}
        <button type="button" onClick={() => void reloadStaff()} className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-semibold text-pink-700 transition-colors hover:bg-pink-50">{copy.refresh}</button>
        {canWriteStaff && <button type="button" onClick={() => setAddOpen(true)} className="rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:brightness-95" style={{ background: PINK }}>{copy.add}</button>}
      </div>
    </header>

    <section aria-label={copy.title} className="space-y-3 rounded-2xl border border-pink-100 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row emma-reflow-wrap">
        <label className="min-w-0 flex-1"><span className="sr-only">{copy.search}</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={copy.search} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-pink-400 focus:bg-white focus:ring-2 focus:ring-pink-100" /></label>
        <label className="min-w-0 sm:max-w-xs"><span className="sr-only">{copy.role}</span><select aria-label={copy.role} value={roleCode} onChange={(event) => setRoleCode(event.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition-colors focus:border-pink-400 focus:ring-2 focus:ring-pink-100"><option value="ALL">{copy.allRoles}</option>{roleCodes.map((role) => <option key={role} value={role}>{role}</option>)}</select></label>
      </div>
    </section>

    {directoryError && <div role="alert" className="rounded-2xl border border-rose-100 bg-rose-50 p-4 text-sm text-rose-800"><p>{copy.loadError}</p><button type="button" onClick={() => void reloadStaff()} className="mt-3 rounded-xl border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-100">{copy.retry}</button></div>}
    {!directoryError && staffRows === null && <p role="status" className="rounded-2xl bg-white p-8 text-center text-sm text-slate-500 shadow-sm">{copy.loading}</p>}
    {!directoryError && staffRows !== null && filteredCards.length === 0 && <p className="rounded-2xl bg-white p-8 text-center text-sm text-slate-500 shadow-sm">{copy.empty}</p>}
    {!directoryError && filteredCards.length > 0 && <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 emma-reflow-stack">
      {filteredCards.map((card) => {
        const source = staffRows?.find((row) => row.id === card.id)
        return source ? <StaffCard key={card.id} card={card} isZH={isZH} copy={copy} onSelect={() => setSelected(source)} /> : null
      })}
    </div>}

    {selectedCurrentRow && <StaffProfilePanel key={selectedCurrentRow.id} staff={selectedCurrentRow} onClose={() => setSelected(null)} />}
    {addOpen && <AddStaffModal isZH={isZH} onClose={() => setAddOpen(false)} onCreated={(name) => {
      setAddOpen(false)
      setNotice(isZH ? `已新增 ${name}` : `${name} added`)
      window.setTimeout(() => setNotice(''), 3_000)
      void reloadStaff()
    }} />}
  </div>
}
