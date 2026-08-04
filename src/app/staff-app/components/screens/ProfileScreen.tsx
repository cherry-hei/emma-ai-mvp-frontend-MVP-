'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { LeaveRequest, MyProfile } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'

function certTone(daysLeft: number | null | undefined) {
  if (daysLeft === null || daysLeft === undefined) return 'border-gray-200 bg-gray-50 text-gray-500'
  if (daysLeft < 0) return 'border-rose-200 bg-rose-50 text-rose-600'
  if (daysLeft <= 90) return 'border-amber-200 bg-amber-50 text-amber-700'
  return 'border-[#f3c7cf] bg-[#fdecef] text-[#e87a8e]'
}

// Language + sign-out, rendered on the "Me" tab as well as in the header menu.
// The header is one tap from anywhere, but a phone user looking for either of
// these looks under their profile first, so both places carry them.
function SettingsCard() {
  const { lang, setLang, t } = useLang()
  const { user, signOut } = useAuth()
  const isZH = lang === 'zh'

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <h4 className="text-sm font-semibold text-gray-900">{t('sa_settings')}</h4>

      <div className="mt-3 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-3">
        <p className="text-sm font-medium text-gray-800">{t('sa_language')}</p>
        <div className="flex overflow-hidden rounded-lg border border-gray-200 bg-white">
          {(['en', 'zh'] as const).map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => setLang(code)}
              aria-pressed={lang === code}
              className="px-3 py-1.5 text-xs font-semibold transition-colors"
              style={{
                background: lang === code ? '#fdecef' : '#fff',
                color: lang === code ? '#e87a8e' : '#6b7280',
              }}
            >
              {code === 'en' ? 'English' : '中文'}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 rounded-xl bg-gray-50 px-3 py-3">
        <p className="text-xs text-gray-400">{t('sa_signed_in_as')}</p>
        <p className="truncate text-sm font-medium text-gray-800">{user?.email ?? '-'}</p>
        {(user?.facilityName || user?.role) && (
          <p className="mt-0.5 truncate text-xs text-gray-500">
            {user?.facilityName}
            {user?.role ? ` · ${roleLabel(user.role, isZH)}` : ''}
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={signOut}
        className="mt-3 w-full rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-600 transition hover:bg-rose-100"
      >
        {t('sa_sign_out')}
      </button>
    </div>
  )
}

export default function ProfileScreen() {
  const { t } = useLang()
  const [profile, setProfile] = useState<MyProfile | null>(null)
  const [leave, setLeave] = useState<LeaveRequest[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.myProfile().then(setProfile)
      .catch((e) => setError(e instanceof Error ? e.message : t('sa_profile_error')))
    api.leaveRequests().then(setLeave).catch(() => {})
  }, [t])

  // The settings card rides along on both failure paths on purpose: a profile
  // that will not load is one of the likeliest reasons to want to sign out.
  if (error) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
        <SettingsCard />
      </div>
    )
  }
  if (!profile) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl bg-white p-6 text-center text-sm text-gray-400">{t('sa_loading')}</div>
        <SettingsCard />
      </div>
    )
  }

  const initial = (profile.name || profile.name_en || '?').slice(0, 1)

  return (
    <div className="space-y-4">
      <div className="rounded-3xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#e87a8e] text-2xl font-bold text-white">
            {initial}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900">{profile.name}</h3>
            <p className="text-sm text-gray-500">
              {[profile.rank, profile.unit_name, profile.employment_type].filter(Boolean).join(' · ')}
            </p>
            <div className="mt-1 flex gap-1.5">
              {profile.is_mentor && (
                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-600">{t('sa_mentor')}</span>
              )}
              {profile.is_audited_for_medication && (
                <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-600">{t('sa_med_audited')}</span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h4 className="text-sm font-semibold text-gray-900">{t('sa_my_details')}</h4>
        <div className="mt-3 space-y-3">
          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">{t('sa_name_en')}</p>
            <p className="text-sm font-medium text-gray-800">{profile.name_en ?? '-'}</p>
          </div>

          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">{t('sa_unit')}</p>
            <p className="text-sm font-medium text-gray-800">{profile.unit_name ?? '-'}</p>
          </div>

          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">{t('sa_cycle_scheduled')}</p>
            <p className="text-sm font-medium text-gray-800">
              {profile.hours.scheduled_hours} / {profile.hours.contracted_hours} {t('sa_hours_unit')}
            </p>
          </div>

          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs text-gray-400">{t('sa_hours_pct')}</p>
              <p className="text-xs font-semibold text-[#e87a8e]">{profile.hours.pct}%</p>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-gray-200">
              <div className="h-full rounded-full bg-[#e87a8e]"
                style={{ width: `${Math.min(profile.hours.pct, 100)}%` }} />
            </div>
          </div>

          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">{t('sa_month_actual')}</p>
            <p className="text-sm font-medium text-gray-800">
              {profile.attendance_month.worked_hours}h · {profile.attendance_month.days_worked} {t('sa_days_unit')}
            </p>
          </div>

          <div className="rounded-xl bg-gray-50 px-3 py-3">
            <p className="text-xs text-gray-400">{t('sa_certs')}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {profile.certificates.length === 0 && <span className="text-xs text-gray-400">{t('sa_no_certs')}</span>}
              {profile.certificates.map((c) => (
                <span key={c.cert_type}
                  className={`rounded-full border px-2.5 py-1 text-xs font-medium ${certTone(c.days_left)}`}>
                  {c.cert_type}
                  {c.days_left !== null && c.days_left !== undefined && (
                    <span className="ml-1 opacity-70">
                      {c.days_left < 0 ? `${t('sa_expired')} ${-c.days_left}d` : `${c.days_left}d`}
                    </span>
                  )}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h4 className="text-sm font-semibold text-gray-900">{t('sa_my_requests')}</h4>
        {leave.length === 0 ? (
          <p className="mt-2 text-xs text-gray-400">{t('sa_no_requests')}</p>
        ) : (
          <div className="mt-2 space-y-2">
            {leave.slice(0, 6).map((r) => (
              <div key={r.id} className="flex items-center justify-between border-b border-gray-50 py-2 text-xs last:border-0">
                <div>
                  <p className="font-medium text-gray-800">{r.leave_type}</p>
                  <p className="text-gray-400">
                    {r.date_start}{r.date_end !== r.date_start ? ` – ${r.date_end}` : ''}
                  </p>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  r.status === 'approved' ? 'bg-emerald-50 text-emerald-600'
                    : r.status === 'rejected' ? 'bg-rose-50 text-rose-600'
                    : 'bg-blue-50 text-blue-600'
                }`}>
                  {r.status === 'approved' ? t('sa_status_approved')
                    : r.status === 'rejected' ? t('sa_status_rejected')
                    : t('sa_status_pending')}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <SettingsCard />
    </div>
  )
}
