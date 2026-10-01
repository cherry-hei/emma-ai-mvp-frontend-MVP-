'use client'

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { apiFetch } from '@/lib/api'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { normaliseRole } from '@/lib/permissions'

interface WindowState {
  enabled: boolean
  opens_at: string | null
  closes_at: string | null
  target_start: string | null
  target_end: string | null
  status: 'open' | 'scheduled' | 'expired' | 'closed'
}

function hkInput(iso: string | null) {
  if (!iso) return ''
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Hong_Kong', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(iso))
  const p = Object.fromEntries(parts.map(item => [item.type, item.value]))
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}
const toISO = (value: string) => new Date(`${value}:00+08:00`).toISOString()

export function DutyWindowPanel() {
  const { lang } = useLang()
  const zh = lang === 'zh'
  const { user } = useAuth()
  const owner = normaliseRole(user?.role) === 'OWNER'
  const [current, setCurrent] = useState<WindowState | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [opens, setOpens] = useState('')
  const [closes, setCloses] = useState('')
  const [targetStart, setTargetStart] = useState('')
  const [targetEnd, setTargetEnd] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const refresh = useCallback(async () => {
    try {
      const value = await apiFetch<WindowState>('/request-windows/duty')
      setCurrent(value)
      setEnabled(value.enabled)
      setOpens(hkInput(value.opens_at))
      setCloses(hkInput(value.closes_at))
      setTargetStart(value.target_start || '')
      setTargetEnd(value.target_end || '')
      setError('')
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load request window') }
  }, [])
  useEffect(() => { void refresh() }, [refresh])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!owner || busy) return
    if (enabled && (!opens || !closes || !targetStart || !targetEnd || opens >= closes || targetStart > targetEnd)) {
      setError(zh ? '請填妥香港時間的開放起訖及目標更期起訖。' : 'Complete valid Hong Kong opening times and target roster dates.')
      return
    }
    setBusy(true); setMessage('')
    try {
      const payload = {
        enabled,
        opens_at: opens ? toISO(opens) : null,
        closes_at: closes ? toISO(closes) : null,
        target_start: targetStart || null,
        target_end: targetEnd || null,
      }
      await apiFetch<WindowState>('/request-windows/duty', { method: 'POST', body: JSON.stringify(payload) })
      await refresh()
      setMessage(zh ? '已由後端儲存；員工端讀取同一窗口。' : 'Saved by backend; staff app reads the same window.')
    } catch (e) { setError(e instanceof Error ? e.message : 'Save failed') }
    finally { setBusy(false) }
  }

  return <section className="rounded-xl border border-border bg-card p-4 text-sm" aria-label={zh ? '指定更期申請期' : 'Duty request window'}>
    <h2 className="font-semibold">{zh ? '開放指定更期／休息日申請' : 'Open duty / day-off requests'}</h2>
    <p className="mt-1 text-xs text-muted-foreground">{zh ? '僅 OWNER 可設定；此窗口不會阻止病假／緊急病假。未設定時員工指定更次申請預設關閉。' : 'OWNER only. This window never blocks sick or emergency leave. Duty requests default closed until configured.'}</p>
    <p className="mt-2 text-xs">{zh ? '現況' : 'Status'}: <strong>{current?.status || (error ? (zh ? '未知' : 'Unknown') : '...')}</strong>
      {current?.target_start && ` · ${current.target_start} → ${current.target_end}`}</p>
    {error && <p role="alert" className="my-2 rounded-lg bg-rose-50 p-2 text-xs text-rose-800 dark:bg-rose-950 dark:text-rose-100">{error} · {zh ? '未儲存新設定' : 'New setting not saved'}</p>}
    {message && <p role="status" className="my-2 text-xs text-emerald-700 dark:text-emerald-200">{message}</p>}
    {owner && <form onSubmit={save} className="mt-3 space-y-3">
      <label className="flex items-center gap-2"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />{zh ? '開啟（只在指定時間內生效）' : 'Enable (only effective during specified times)'}</label>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        <label>{zh ? '開始（香港時間）' : 'Opens (Hong Kong time)'}<input type="datetime-local" value={opens} onChange={e => setOpens(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background p-2" /></label>
        <label>{zh ? '截止（香港時間）' : 'Closes (Hong Kong time)'}<input type="datetime-local" value={closes} onChange={e => setCloses(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background p-2" /></label>
        <label>{zh ? '目標更表開始' : 'Roster from'}<input type="date" value={targetStart} onChange={e => setTargetStart(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background p-2" /></label>
        <label>{zh ? '目標更表結束' : 'Roster to'}<input type="date" value={targetEnd} onChange={e => setTargetEnd(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background p-2" /></label>
      </div>
      <button disabled={busy} type="submit" className="rounded-lg bg-pink-600 px-4 py-2 font-semibold text-white disabled:opacity-40">{busy ? (zh ? '保存中…' : 'Saving…') : (zh ? '保存開放期' : 'Save request window')}</button>
    </form>}
  </section>
}
