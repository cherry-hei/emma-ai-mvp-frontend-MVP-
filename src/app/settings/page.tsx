'use client'

/**
 * Settings is the institutional home for configuration-related work. The two
 * data-backed child modules are embedded rather than duplicated or linked away.
 * Their own feature grants are checked here as well as at their legacy routes.
 */
import { useState } from 'react'
import ShiftCodesPage from '@/app/shift-codes/page'
import SchedulingPage from '@/app/scheduling/page'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'
import { useLang } from '@/components/layout/LanguageContext'
import { canRead, type Feature } from '@/lib/permissions'

type SettingsSection = 'institution' | 'shift-dictionary' | 'task-scheduling'

type SectionDefinition = {
  id: SettingsSection
  feature?: Feature
  icon: string
  zh: string
  en: string
  descriptionZh: string
  descriptionEn: string
}

const SECTIONS: readonly SectionDefinition[] = [
  {
    id: 'institution', feature: 'facility.settings', icon: '⌂', zh: '院舍資料', en: 'Institution',
    descriptionZh: '目前登入院舍及帳戶範圍', descriptionEn: 'Signed-in facility and account scope',
  },
  {
    id: 'shift-dictionary', feature: 'roster.view', icon: '⌘', zh: '更期代號字典', en: 'Shift Dictionary',
    descriptionZh: '院舍適用的更期代號及定義', descriptionEn: 'Shift codes and definitions for this facility',
  },
  {
    id: 'task-scheduling', feature: 'task_codes', icon: '◫', zh: '任務排程規則', en: 'Task Scheduling',
    descriptionZh: '活動人手、員工資格及樓層最低人手', descriptionEn: 'Event staffing, qualifications and floor coverage',
  },
]

function InstitutionPanel({ isZH }: { isZH: boolean }) {
  const { user } = useAuth()
  const facilityName = user?.facilityName || (isZH ? '已登入院舍' : 'Signed-in facility')
  const role = roleLabel(user?.role, isZH) || (isZH ? '未提供角色' : 'Role unavailable')

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_16px_36px_-32px_rgba(15,23,42,0.35)] md:p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-50 text-lg text-[#E8187A]" aria-hidden>⌂</div>
          <div>
            <h2 className="text-sm font-bold text-slate-900">{facilityName}</h2>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
              {isZH ? '院舍身分由已登入帳戶提供；不以示範院舍、NAAC或預設機構代碼取代。' : 'Facility identity is supplied by the signed-in account; it is never replaced with a demo home, NAAC, or a default organisation code.'}
            </p>
          </div>
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl bg-slate-50 px-3 py-3">
            <dt className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">{isZH ? '院舍名稱' : 'Facility name'}</dt>
            <dd className="mt-1 break-words text-xs font-semibold text-slate-700">{facilityName}</dd>
          </div>
          <div className="rounded-xl bg-slate-50 px-3 py-3">
            <dt className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">{isZH ? '帳戶角色' : 'Account role'}</dt>
            <dd className="mt-1 text-xs font-semibold text-slate-700">{role}</dd>
          </div>
          <div className="rounded-xl bg-slate-50 px-3 py-3 sm:col-span-2">
            <dt className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">{isZH ? '院舍識別碼' : 'Facility identifier'}</dt>
            <dd className="mt-1 break-all text-xs font-semibold text-slate-700">{user?.facilityId || (isZH ? '帳戶未提供' : 'Not provided by account')}</dd>
          </div>
        </dl>
      </section>

      <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[11px] leading-relaxed text-amber-900">
        <span className="font-bold">{isZH ? '資料限制：' : 'Data boundary: '}</span>
        {isZH
          ? '目前前端沒有可審核的院舍檔案寫入合約，因此本頁不顯示本地「儲存」按鈕或假設已更新。更期與任務設定使用各自現有、受權限保護的API。'
          : 'There is no reviewed facility-profile write contract in the current frontend, so this page does not show a local “Save” control or imply an update. Shift and task settings use their existing permission-protected APIs.'}
      </section>
    </div>
  )
}

export default function SettingsPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const isZH = lang === 'zh'
  const [section, setSection] = useState<SettingsSection>(canRead(user?.role, 'facility.settings') ? 'institution' : 'shift-dictionary')
  const active = SECTIONS.find((item) => item.id === section) ?? SECTIONS[0]
  const permitted = (item: SectionDefinition) => !item.feature || canRead(user?.role, item.feature)

  return (
    <div className="min-h-full bg-[linear-gradient(180deg,#fff_0%,#f8fafc_100%)] p-4 md:p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <header>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#E8187A]">Emma AI</p>
          <h1 className="mt-1 text-xl font-bold tracking-tight text-slate-950">{isZH ? '院舍設定' : 'Facility Settings'}</h1>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-500">
            {isZH ? '機構資料、更期代號與任務排程集中管理。每個分項仍按其原有功能權限決定可否檢視。' : 'Manage institution context, shift definitions and task scheduling in one place. Each section retains its original feature permission.'}
          </p>
        </header>

        <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
          <nav className="h-fit rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_16px_36px_-32px_rgba(15,23,42,0.35)]" aria-label={isZH ? '設定分項' : 'Settings sections'}>
            {SECTIONS.map((item) => {
              const allowed = permitted(item)
              const selected = item.id === section
              return (
                <button
                  key={item.id}
                  type="button"
                  disabled={!allowed}
                  onClick={() => setSection(item.id)}
                  className="mb-1 flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition last:mb-0 disabled:cursor-not-allowed disabled:opacity-45"
                  style={{ background: selected ? '#fff0f6' : 'transparent', color: selected ? '#E8187A' : '#475569' }}
                >
                  <span className="mt-0.5 text-sm" aria-hidden>{item.icon}</span>
                  <span className="min-w-0">
                    <span className="block text-xs font-bold">{isZH ? item.zh : item.en}</span>
                    <span className="mt-0.5 block text-[10px] leading-relaxed text-slate-400">{isZH ? item.descriptionZh : item.descriptionEn}</span>
                  </span>
                </button>
              )
            })}
          </nav>

          <section className="min-w-0">
            {!permitted(active) ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
                {isZH ? '你的帳戶沒有此設定分項的原有功能權限。' : 'Your account does not have the original feature permission for this settings section.'}
              </div>
            ) : section === 'institution' ? <InstitutionPanel isZH={isZH} />
              : section === 'shift-dictionary' ? <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_16px_36px_-32px_rgba(15,23,42,0.35)]"><ShiftCodesPage /></div>
              : <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_16px_36px_-32px_rgba(15,23,42,0.35)]"><SchedulingPage /></div>}
          </section>
        </div>
      </div>
    </div>
  )
}
