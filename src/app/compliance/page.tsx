'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import type { ApiStaff, PeriodOut, RatioResult, Unit } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

type Tab = 'ratio' | 'residents' | 'certs'

function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null
  const today = new Date()
  const t0 = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  const [y, m, d] = iso.split('-').map(Number)
  return Math.round((Date.UTC(y, m - 1, d) - t0) / 86_400_000)
}

function certStatus(days: number | null): { key: string; color: string; bg: string } {
  if (days === null) return { key: 'unknown', color: '#64748b', bg: '#f1f5f9' }
  if (days < 0) return { key: 'expired', color: '#be123c', bg: '#fff1f2' }
  if (days <= 30) return { key: 'expiring', color: '#c2410c', bg: '#fff7ed' }
  if (days <= 60) return { key: 'soon', color: '#a16207', bg: '#fefce8' }
  return { key: 'ok', color: '#15803d', bg: '#f0fdf4' }
}

export default function CompliancePage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  const [periods, setPeriods] = useState<PeriodOut[]>([])
  const [periodId, setPeriodId] = useState('')
  const [versionId, setVersionId] = useState('')
  const [date, setDate] = useState('')
  const [tab, setTab] = useState<Tab>('ratio')

  const [ratios, setRatios] = useState<RatioResult[]>([])
  const [units, setUnits] = useState<Unit[]>([])
  const [draftCounts, setDraftCounts] = useState<Record<string, number>>({})
  const [staff, setStaff] = useState<ApiStaff[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const T = {
    title: isZH ? '合規監察' : 'Compliance', sub: isZH ? 'SWD 人手比例 · Cap.459A' : 'SWD staffing ratio · Cap.459A',
    date: isZH ? '日期' : 'Date', period: isZH ? '週期' : 'Period',
    ratio: isZH ? '人手比例' : 'Staffing Ratio', residents: isZH ? '住客人數' : 'Residents',
    certs: isZH ? '員工證書' : 'Certifications',
    window: isZH ? '時段/職級' : 'Window / Rank', req: isZH ? '要求' : 'Required',
    act: isZH ? '實際' : 'Actual', res: isZH ? '住客' : 'Residents', status: isZH ? '狀態' : 'Status',
    pass: isZH ? '合規' : 'Pass', fail: isZH ? '不足' : 'Short',
    passing: isZH ? '合規' : 'passing', failing: isZH ? '不合規' : 'failing',
    unit: isZH ? '單位' : 'Unit', count: isZH ? '人數' : 'Count', total: isZH ? '總數' : 'Total',
    save: isZH ? '儲存' : 'Save', saved: isZH ? '已儲存' : 'Saved',
    staffName: isZH ? '員工' : 'Staff', cert: isZH ? '證書' : 'Certificate',
    expiry: isZH ? '到期日' : 'Expiry', daysLeft: isZH ? '剩餘天數' : 'Days left',
    noCerts: isZH ? '尚無證書資料' : 'No certificate records',
    st_unknown: isZH ? '未設定' : 'No expiry', st_expired: isZH ? '已過期' : 'Expired',
    st_expiring: isZH ? '即將到期' : 'Expiring', st_soon: isZH ? '注意' : 'Soon', st_ok: isZH ? '有效' : 'Valid',
  }
  const stLabel = (k: string) => (T as Record<string, string>)[`st_${k}`] ?? k

  // periods → default current → manual version + default date
  useEffect(() => {
    api.rosterPeriods().then((ps) => {
      setPeriods(ps)
      const today = new Date().toISOString().slice(0, 10)
      const cur = ps.find((p) => p.period_start <= today && p.period_end >= today) ?? ps[0]
      if (cur) { setPeriodId(cur.id); setDate((d) => d || cur.period_start) }
    }).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load periods'))
    api.units().then(setUnits).catch(() => {})
    api.listStaff().then(setStaff).catch(() => {})
  }, [])

  useEffect(() => {
    if (!periodId) return
    api.rosterVersions(periodId)
      .then((vs) => setVersionId(vs.find((v) => v.version_type === 'manual')?.id ?? ''))
      .catch(() => setVersionId(''))
  }, [periodId])

  const loadDay = useCallback(async (d: string, vid: string) => {
    if (!d) return
    setLoading(true); setError('')
    try {
      const [r, c] = await Promise.all([
        api.complianceRatio(d, vid || undefined),
        api.residentCounts(d),
      ])
      setRatios(r)
      const draft: Record<string, number> = {}
      c.forEach((row) => { if (row.unit_id) draft[row.unit_id] = row.resident_count })
      setDraftCounts(draft)
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load compliance') } finally { setLoading(false) }
  }, [])

  useEffect(() => { if (date) loadDay(date, versionId) }, [date, versionId, loadDay])

  const ratioSummary = useMemo(() => ({
    pass: ratios.filter((r) => r.passes).length, fail: ratios.filter((r) => !r.passes).length,
  }), [ratios])
  const residentTotal = useMemo(
    () => Object.values(draftCounts).reduce((a, b) => a + (Number(b) || 0), 0),
    [draftCounts],
  )

  async function saveCount(unitId: string) {
    setError('')
    try {
      await api.setResidentCount({ date, unit_id: unitId, care_level: 'general', count: Number(draftCounts[unitId]) || 0 })
      setNotice(T.saved); window.setTimeout(() => setNotice(''), 1800)
      await loadDay(date, versionId)
    } catch (e) { setError(e instanceof Error ? e.message : 'Save failed') }
  }

  const certRows = useMemo(() =>
    staff.flatMap((s) => (s.certificates ?? []).map((c) => ({
      staff: s.name_en || s.name, rank: s.rank, cert: c.cert_type,
      expiry: c.expiry_date ?? null, days: daysUntil(c.expiry_date),
    }))).sort((a, b) => (a.days ?? 1e9) - (b.days ?? 1e9)),
    [staff],
  )

  const TABS: { id: Tab; label: string }[] = [
    { id: 'ratio', label: T.ratio }, { id: 'residents', label: T.residents }, { id: 'certs', label: T.certs },
  ]

  return (
    <div className="p-5 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{T.title}</h1>
          <p className="text-xs text-gray-500 mt-0.5">{T.sub}</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">{T.period}</label>
          <select value={periodId} onChange={(e) => setPeriodId(e.target.value)}
            className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white max-w-[190px]">
            {periods.map((p) => <option key={p.id} value={p.id}>{p.period_start} → {p.period_end}</option>)}
          </select>
          <label className="text-xs text-gray-500">{T.date}</label>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
            className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white" />
        </div>
      </div>

      <div className="flex items-center gap-3 min-h-[16px]">
        {notice && <span className="text-[11px] font-medium text-emerald-600">{notice}</span>}
        {error && <span className="text-[11px] font-medium text-rose-600">{error}</span>}
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className="px-4 py-2 text-xs font-semibold border-b-2 transition-all"
            style={{ borderBottomColor: tab === t.id ? PINK : 'transparent', color: tab === t.id ? PINK : '#6b7280' }}>
            {t.label}
          </button>
        ))}
      </div>

      {loading && <div className="text-sm text-gray-400 py-6 text-center">…</div>}

      {/* RATIO */}
      {!loading && tab === 'ratio' && (
        <div className="space-y-3">
          <div className="flex gap-3">
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2">
              <div className="text-xl font-bold text-emerald-700">{ratioSummary.pass}</div>
              <div className="text-[10px] text-emerald-600 uppercase">{T.passing}</div>
            </div>
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2">
              <div className="text-xl font-bold text-rose-700">{ratioSummary.fail}</div>
              <div className="text-[10px] text-rose-600 uppercase">{T.failing}</div>
            </div>
          </div>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-left text-[10px] text-gray-500 uppercase">
                  <th className="px-3 py-2.5">{T.window}</th><th className="px-3 py-2.5">{T.res}</th>
                  <th className="px-3 py-2.5">{T.req}</th><th className="px-3 py-2.5">{T.act}</th>
                  <th className="px-3 py-2.5">{T.status}</th>
                </tr>
              </thead>
              <tbody>
                {ratios.map((r, i) => (
                  <tr key={i} className="border-b border-gray-50">
                    <td className="px-3 py-2.5 font-semibold text-gray-700">{r.label}</td>
                    <td className="px-3 py-2.5 text-gray-600">{r.residents}</td>
                    <td className="px-3 py-2.5 text-gray-600">{r.required}</td>
                    <td className="px-3 py-2.5 font-bold text-gray-800">{r.actual}</td>
                    <td className="px-3 py-2.5">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border"
                        style={r.passes
                          ? { color: '#15803d', background: '#f0fdf4', borderColor: '#bbf7d0' }
                          : { color: '#be123c', background: '#fff1f2', borderColor: '#fecdd3' }}>
                        {r.passes ? `✓ ${T.pass}` : `✗ ${T.fail}`}
                      </span>
                    </td>
                  </tr>
                ))}
                {ratios.length === 0 && (
                  <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-400">—</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* RESIDENTS */}
      {!loading && tab === 'residents' && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 max-w-lg">
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-semibold text-gray-700">{date}</div>
            <div className="text-xs text-gray-500">{T.total}: <span className="font-bold text-gray-900">{residentTotal}</span></div>
          </div>
          <div className="space-y-2">
            {units.map((u) => (
              <div key={u.id} className="flex items-center gap-3">
                <span className="text-sm text-gray-700 flex-1">{u.name}</span>
                <input type="number" value={draftCounts[u.id] ?? 0}
                  onChange={(e) => setDraftCounts((p) => ({ ...p, [u.id]: Number(e.target.value) }))}
                  className="w-24 rounded-lg border border-gray-200 px-2 py-1 text-sm text-right" />
                <button onClick={() => saveCount(u.id)}
                  className="text-xs px-3 py-1 rounded-lg text-white font-semibold" style={{ background: PINK }}>{T.save}</button>
              </div>
            ))}
            {units.length === 0 && <div className="text-sm text-gray-400">—</div>}
          </div>
        </div>
      )}

      {/* CERTIFICATIONS */}
      {!loading && tab === 'certs' && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100 text-left text-[10px] text-gray-500 uppercase">
                <th className="px-3 py-2.5">{T.staffName}</th><th className="px-3 py-2.5">{T.cert}</th>
                <th className="px-3 py-2.5">{T.expiry}</th><th className="px-3 py-2.5">{T.daysLeft}</th>
                <th className="px-3 py-2.5">{T.status}</th>
              </tr>
            </thead>
            <tbody>
              {certRows.map((c, i) => {
                const st = certStatus(c.days)
                return (
                  <tr key={i} className="border-b border-gray-50">
                    <td className="px-3 py-2.5 font-semibold text-gray-800">{c.staff}
                      <span className="ml-1.5 text-[9px] font-bold text-gray-400">{c.rank}</span></td>
                    <td className="px-3 py-2.5 text-gray-600">{c.cert}</td>
                    <td className="px-3 py-2.5 text-gray-600">{c.expiry ?? '—'}</td>
                    <td className="px-3 py-2.5 font-bold tabular-nums" style={{ color: st.color }}>{c.days ?? '—'}</td>
                    <td className="px-3 py-2.5">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full" style={{ color: st.color, background: st.bg }}>
                        {stLabel(st.key)}
                      </span>
                    </td>
                  </tr>
                )
              })}
              {certRows.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-400">{T.noCerts}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
