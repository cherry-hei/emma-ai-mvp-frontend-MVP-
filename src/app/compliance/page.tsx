'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import type { ApiStaff, PeriodOut, RatioResult, Unit, ViolationOut } from '@/lib/apiTypes'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

type Tab = 'ratio' | 'residents' | 'certs' | 'audit' /* agency removed for MVP */

// Employment types the backend treats as external cover (emma_core.services.compliance.EXTERNAL_TYPES).
const EXTERNAL_EMPLOYMENT_TYPES = new Set(['local_pt', 'agency', 'outsource', 'casual'])

function AuditBadge({ s }: { s: 'ok' | 'warn' | 'over' }) {
  const cls: Record<string, string> = {
    ok: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    warn: 'bg-amber-50 text-amber-700 border-amber-200',
    over: 'bg-red-50 text-red-700 border-red-200',
  }
  const sym: Record<string, string> = { ok: '✓', warn: '⚠', over: '✗' }
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${cls[s]}`}>{sym[s]}</span>
  )
}

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
  const [violations, setViolations] = useState<ViolationOut[]>([])
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
    tabAgency: isZH ? '外判規則' : 'Agency Rules', tabAudit: isZH ? '審計核對' : 'Audit Checklist',
    ptCapTitle: isZH ? 'PT/外判人手上限 (≤FT/2)' : 'PT/Agency Cap (≤FT/2)',
    colRole: isZH ? '職位' : 'Role', colFt: isZH ? '長工 (FT)' : 'Full-time (FT)',
    colOutsourced: isZH ? '外判/兼職' : 'Outsourced/PT', colTotal: isZH ? '總數' : 'Total',
    colPtCap: isZH ? 'PT上限 (≤FT/2)' : 'PT Cap (≤FT/2)',
    auditOk: isZH ? '通過' : 'Pass', auditWarn: isZH ? '待處理' : 'Pending', auditOver: isZH ? '違規' : 'Breach',
    colCategory: isZH ? '類別' : 'Category', colIssue: isZH ? '問題' : 'Issue', colFreq: isZH ? '頻次' : 'Freq',
    noAuditItems: isZH ? '本週期尚無審計項目' : 'No audit items for this period',
    catRatio: isZH ? '人手比例' : 'Staffing ratio', catCert: isZH ? '員工證書' : 'Certification',
  }
  const certExpiringDetail = (n: number) => (isZH ? `${n} 張證書於30天內到期` : `${n} certificate(s) expiring within 30 days`)
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

  useEffect(() => {
    if (!versionId) { setViolations([]); return }
    api.validateRoster(versionId).then((v) => setViolations(v.violations)).catch(() => setViolations([]))
  }, [versionId])

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

  // Full-time vs outsourced/part-time headcount per rank, so a PT/agency cap
  // (≤ FT/2, Cap.459A s.113) can be checked against the real roster composition.
  const ptCapRows = useMemo(() => {
    const byRank = new Map<string, { ft: number; pt: number }>()
    staff.forEach((s) => {
      const row = byRank.get(s.rank) ?? { ft: 0, pt: 0 }
      if (EXTERNAL_EMPLOYMENT_TYPES.has(s.employment_type)) row.pt += 1
      else row.ft += 1
      byRank.set(s.rank, row)
    })
    return Array.from(byRank.entries()).map(([rank, { ft, pt }]) => {
      const cap = Math.floor(ft / 2)
      return { rank, ft, pt, total: ft + pt, cap, ok: pt <= cap }
    }).sort((a, b) => a.rank.localeCompare(b.rank))
  }, [staff])

  const expiringCertCount = useMemo(
    () => certRows.filter((c) => c.days !== null && c.days <= 30).length,
    [certRows],
  )

  const auditRows = useMemo(() => {
    const rows: { category: string; issue: string; freq: number; status: 'ok' | 'warn' | 'over' }[] = []
    ratios.forEach((r) => rows.push({
      category: r.label, issue: `${r.actual}/${r.required}`, freq: 1,
      status: r.passes ? 'ok' : 'over',
    }))
    // The full validation run repeats the same rule violation once per affected
    // day/window, so group by (rule, message) and show the occurrence count
    // instead of dumping every row — Cap.459A checklist reads as a summary.
    const byViolation = new Map<string, { status: 'warn' | 'over'; freq: number }>()
    violations.forEach((v) => {
      const key = `${v.rule_code}::${v.message ?? ''}`
      const entry = byViolation.get(key)
      if (entry) entry.freq += 1
      else byViolation.set(key, { status: v.severity === 'hard' ? 'over' : 'warn', freq: 1 })
    })
    violations.forEach((v) => {
      const key = `${v.rule_code}::${v.message ?? ''}`
      if (!byViolation.has(key)) return
      const entry = byViolation.get(key)!
      rows.push({ category: v.rule_code, issue: v.message ?? v.rule_code, freq: entry.freq, status: entry.status })
      byViolation.delete(key)
    })
    rows.push({
      category: T.catCert, issue: certExpiringDetail(expiringCertCount),
      freq: expiringCertCount, status: expiringCertCount > 0 ? 'warn' : 'ok',
    })
    return rows
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ratios, violations, expiringCertCount, isZH])

  const auditOkCount = auditRows.filter((r) => r.status === 'ok').length
  const auditWarnCount = auditRows.filter((r) => r.status === 'warn').length
  const auditOverCount = auditRows.filter((r) => r.status === 'over').length

  const AGENCY_RULES = isZH ? [
    { icon: '📋', title: '50%上限', desc: 'PT/外判人數不得超過同職級長工人數的50%（Cap.459A s.113）' },
    { icon: '🕐', title: '更次要求', desc: '更次時段需符合本院已登記的更表定義' },
    { icon: '📅', title: '合約期限', desc: '外判合約最長4個月，需提前續約' },
    { icon: '👥', title: '人數限制', desc: '每更外判/兼職人數不得超過該職級PT上限' },
    { icon: '🔍', title: '審計要求', desc: '每季需保留外判人手審核記錄' },
    { icon: '⏰', title: '通知時限', desc: '外判需提前確認，緊急情況除外' },
  ] : [
    { icon: '📋', title: '50% Cap', desc: 'PT/agency headcount cannot exceed 50% of full-time in the same rank (Cap.459A s.113)' },
    { icon: '🕐', title: 'Shift Hours', desc: 'Shift windows must match this facility\'s registered shift definitions' },
    { icon: '📅', title: 'Contract Limit', desc: 'Max 4-month agency contracts, must renew in advance' },
    { icon: '👥', title: 'Count Limit', desc: 'PT/agency headcount per shift must stay within that rank\'s PT cap' },
    { icon: '🔍', title: 'Audit Record', desc: 'Agency staffing audit records must be kept each quarter' },
    { icon: '⏰', title: 'Notice Period', desc: 'Advance confirmation required for agency cover, except emergencies' },
  ]

  const TABS: { id: Tab; label: string }[] = [
    { id: 'ratio', label: T.ratio }, { id: 'residents', label: T.residents }, { id: 'certs', label: T.certs },
    { id: 'audit', label: T.tabAudit }, /* agency tab removed for MVP */
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
                    <td className="px-3 py-2.5 font-semibold text-gray-700">{r.label === 'RN' ? 'Nurse (RN/EN)' : r.label === '護士' ? '護士 (RN/EN)' : r.label}</td>
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
                  <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-400">-</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <div className="px-3 pt-3 text-xs font-semibold text-gray-700">{T.ptCapTitle}</div>
            <table className="w-full text-xs mt-2">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-left text-[10px] text-gray-500 uppercase">
                  <th className="px-3 py-2.5">{T.colRole}</th><th className="px-3 py-2.5">{T.colFt}</th>
                  <th className="px-3 py-2.5">{T.colOutsourced}</th><th className="px-3 py-2.5">{T.colTotal}</th>
                  <th className="px-3 py-2.5">{T.colPtCap}</th><th className="px-3 py-2.5">{T.status}</th>
                </tr>
              </thead>
              <tbody>
                {ptCapRows.map((row) => (
                  <tr key={row.rank} className="border-b border-gray-50">
                    <td className="px-3 py-2.5 font-semibold text-gray-700">{row.rank}</td>
                    <td className="px-3 py-2.5 text-gray-600">{row.ft}</td>
                    <td className="px-3 py-2.5 text-gray-600">{row.pt}</td>
                    <td className="px-3 py-2.5 font-bold text-gray-800">{row.total}</td>
                    <td className="px-3 py-2.5 text-gray-500">{row.cap}</td>
                    <td className="px-3 py-2.5"><AuditBadge s={row.ok ? 'ok' : 'over'} /></td>
                  </tr>
                ))}
                {ptCapRows.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-400">-</td></tr>
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
            {units.length === 0 && <div className="text-sm text-gray-400">-</div>}
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
                    <td className="px-3 py-2.5 text-gray-600">{c.expiry ?? '-'}</td>
                    <td className="px-3 py-2.5 font-bold tabular-nums" style={{ color: st.color }}>{c.days ?? '-'}</td>
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

      {/* AGENCY RULES */}
      {false && tab === 'agency' && ( /* HIDDEN for MVP */
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {AGENCY_RULES.map((rule) => (
              <div key={rule.title} className="rounded-xl border border-gray-100 bg-gray-50 p-4 flex gap-3">
                <span className="text-xl flex-shrink-0">{rule.icon}</span>
                <div>
                  <div className="text-xs font-semibold text-gray-800 mb-1">{rule.title}</div>
                  <div className="text-[11px] text-gray-500 leading-relaxed">{rule.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AUDIT CHECKLIST */}
      {!loading && tab === 'audit' && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: T.auditOk, count: auditOkCount, cls: 'bg-emerald-50 border-emerald-200', color: '#10b981' },
              { label: T.auditWarn, count: auditWarnCount, cls: 'bg-amber-50 border-amber-200', color: '#f59e0b' },
              { label: T.auditOver, count: auditOverCount, cls: 'bg-red-50 border-red-200', color: '#ef4444' },
            ].map((s) => (
              <div key={s.label} className={`rounded-xl border p-4 text-center ${s.cls}`}>
                <div className="text-2xl font-bold tabular-nums" style={{ color: s.color }}>{s.count}</div>
                <div className="text-[11px] font-semibold mt-1" style={{ color: s.color }}>{s.label}</div>
              </div>
            ))}
          </div>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-left text-[10px] text-gray-500 uppercase">
                  <th className="px-3 py-2.5">{T.colCategory}</th><th className="px-3 py-2.5">{T.colIssue}</th>
                  <th className="px-3 py-2.5">{T.colFreq}</th><th className="px-3 py-2.5">{T.status}</th>
                </tr>
              </thead>
              <tbody>
                {auditRows.map((a, i) => (
                  <tr key={i} className="border-b border-gray-50">
                    <td className="px-3 py-2.5 font-semibold text-gray-800">{a.category}</td>
                    <td className="px-3 py-2.5 text-gray-600">{a.issue}</td>
                    <td className="px-3 py-2.5 text-gray-500">{a.freq || '-'}</td>
                    <td className="px-3 py-2.5"><AuditBadge s={a.status} /></td>
                  </tr>
                ))}
                {auditRows.length === 0 && (
                  <tr><td colSpan={4} className="px-3 py-6 text-center text-gray-400">{T.noAuditItems}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
