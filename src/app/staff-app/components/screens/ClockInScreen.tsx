'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { MyAttendance } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '--:--'
  return new Date(iso).toLocaleTimeString('en-HK', { hour: '2-digit', minute: '2-digit', hour12: false })
}

export default function ClockInScreen() {
  const { t } = useLang()
  const [attendance, setAttendance] = useState<MyAttendance | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showRecent, setShowRecent] = useState(false)

  const load = useCallback(() => api.myAttendance().then(setAttendance)
    .catch((e) => setError(e instanceof Error ? e.message : t('sa_attendance_error'))), [t])

  useEffect(() => { load() }, [load])

  async function clock(eventType: 'clock_in' | 'clock_out') {
    setBusy(true)
    setError('')
    try {
      await api.clock(eventType)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('sa_clock_failed'))
    } finally {
      setBusy(false)
    }
  }

  if (error) {
    return <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
  }
  if (!attendance) {
    return <div className="rounded-2xl bg-white p-6 text-center text-sm text-gray-400">{t('sa_loading')}</div>
  }

  const { today, month, recent } = attendance
  const progress = month.worked_hours > 0 && month.days_worked > 0
    ? Math.min(100, Math.round((month.worked_hours / (month.days_worked * 8)) * 100))
    : 0

  return (
    <div className="space-y-4">
      <section className="rounded-3xl bg-gradient-to-br from-[#e87a8e] to-[#d9657b] p-5 text-white shadow-sm">
        <p className="text-sm text-white/80">{t('sa_today_clock')}</p>
        <h2 className="mt-2 text-2xl font-semibold">
          {today.clocked_in ? fmtTime(today.clock_in_at) : '--:--'}
        </h2>
        <p className="mt-1 text-sm text-white/80">
          {today.clocked_in
            ? (today.clock_out_at
                ? `${t('sa_clocked_out_at')} ${fmtTime(today.clock_out_at)}`
                : `${t('sa_worked_today')} ${Math.round(today.worked_minutes_today / 60 * 10) / 10} ${t('sa_hours_unit')}`)
            : t('sa_not_clocked_in')}
        </p>
      </section>

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-gray-900">{t('sa_month_hours')}</h3>
        <p className="mt-1 text-sm text-gray-500">{month.month_start} → {month.month_end}</p>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-gray-600">{month.worked_hours}h · {month.days_worked} {t('sa_days_unit')}</span>
            <span className="font-semibold text-[#e87a8e]">{progress}%</span>
          </div>
          <div className="h-3 w-full overflow-hidden rounded-full bg-gray-100">
            <div className="h-full rounded-full bg-[#e87a8e]" style={{ width: `${progress}%` }} />
          </div>
        </div>
      </div>

      {today.events.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <h3 className="text-base font-semibold text-gray-900">{t('sa_today_clock_log')}</h3>
          <div className="mt-3 space-y-2">
            {today.events.map((e) => (
              <div key={e.id} className="flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2 text-sm">
                <span className="text-gray-600">{e.event_type === 'clock_in' ? t('sa_clock_in') : t('sa_clock_out')}</span>
                <span className="font-medium text-gray-800">{fmtTime(e.event_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        disabled={busy}
        onClick={() => clock(today.clocked_in && !today.clock_out_at ? 'clock_out' : 'clock_in')}
        className="w-full rounded-2xl bg-[#e87a8e] px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#d9657b] disabled:opacity-50">
        {busy ? '…' : today.clocked_in && !today.clock_out_at ? t('sa_btn_clock_out') : t('sa_btn_clock_in')}
      </button>

      <button
        onClick={() => setShowRecent((v) => !v)}
        className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm font-semibold text-gray-700 transition hover:bg-gray-50">
        {showRecent ? t('sa_hide_log') : t('sa_show_log')}
      </button>

      {showRecent && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          {recent.length === 0 ? (
            <p className="text-sm text-gray-400">{t('sa_no_log')}</p>
          ) : (
            <div className="space-y-2">
              {recent.map((e) => (
                <div key={e.id} className="flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2 text-sm">
                  <span className="text-gray-600">{e.event_type === 'clock_in' ? t('sa_clock_in') : t('sa_clock_out')}</span>
                  <span className="font-medium text-gray-800">{new Date(e.event_at).toLocaleString('en-HK')}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
