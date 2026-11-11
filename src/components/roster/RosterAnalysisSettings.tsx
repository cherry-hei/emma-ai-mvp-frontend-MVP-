'use client'

import { useEffect, useRef, useState } from 'react'
import { api, type RosterAnalysisConfig } from '@/lib/api'

export function RosterAnalysisSettings({ isZH, onSaved, onClose }: {
  isZH: boolean; onSaved: (config: RosterAnalysisConfig) => void; onClose: () => void
}) {
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const operation = useRef(0)
  useEffect(() => () => { operation.current += 1 }, [])
  async function readFile(file?: File) {
    const current = ++operation.current
    setProfile(null); setConfirmed(false); setError('')
    if (!file) return
    try {
      if (file.size > 512_000) throw new Error(isZH ? '設定檔超過大小上限。' : 'Configuration file exceeds the size limit.')
      const value: unknown = JSON.parse(await file.text())
      if (current !== operation.current) return
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Expected an analysis configuration object.')
      const next = value as Record<string, unknown>
      if (next.schema_version !== 1 || typeof next.label !== 'string' || !Array.isArray(next.codes) || !Array.isArray(next.roles) || !Array.isArray(next.demand)) throw new Error(isZH ? '設定檔缺少代號、職位或需求資料。' : 'The file needs codes, roles and demand.')
      setProfile(next); setRevision(v => v+1)
    } catch (e) { if (current === operation.current) setError(e instanceof Error ? e.message : 'Invalid configuration') }
  }
  async function save() {
    if (!profile || !confirmed || busy) return
    const current = ++operation.current
    setBusy(true); setError('')
    try {
      const result = await api.saveRosterAnalysis({ ...profile, status: 'confirmed' })
      if (current !== operation.current) return
      if (!result?.id || result.config_json?.status !== 'confirmed') throw new Error('The server did not confirm the saved configuration.')
      onSaved(result)
    } catch (e) { if (current === operation.current) setError(e instanceof Error ? e.message : 'Save failed') }
    finally { if (current === operation.current) setBusy(false) }
  }
  return <section className="rounded-xl border border-pink-100 bg-pink-50/30 p-4 space-y-3" aria-label={isZH ? '院舍分析設定' : 'Facility analysis settings'}>
    <div className="flex justify-between gap-4">
      <h2 className="font-semibold text-sm">{isZH ? '院舍分析設定' : 'Facility analysis settings'}</h2>
      <button type="button" onClick={onClose} disabled={busy} className="text-xs underline">{isZH ? '關閉' : 'Close'}</button>
    </div>
    <p className="text-xs text-slate-600">{isZH ? '匯入分析流程產生的設定檔，核對代號、職位工時及需求後儲存。歷史模式仍須人手確認；不會自動批准更表或假期。' : 'Import the analysis configuration and review codes, role hours and demand before saving. Historical patterns require human confirmation; this does not approve rosters or leave.'}</p>
    <label className="block text-xs">{isZH ? '分析設定檔（JSON）' : 'Analysis configuration (JSON)'}
      <input type="file" accept=".json,application/json" disabled={busy} onChange={e => void readFile(e.target.files?.[0])} className="block mt-1" />
    </label>
    {profile && <div key={revision} className="space-y-2">
      <p className="text-sm font-semibold">{String(profile.label)}</p>
      <p className="text-xs">{(profile.codes as unknown[]).length} {isZH ? '個更碼' : 'codes'} · {(profile.roles as unknown[]).length} {isZH ? '個職位' : 'roles'} · {(profile.demand as unknown[]).length} {isZH ? '項需求' : 'demand rows'}</p>
      <details className="text-xs"><summary className="cursor-pointer">{isZH ? '查看完整設定及來源' : 'Review full settings and sources'}</summary>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap bg-white p-3">{JSON.stringify(profile, null, 2)}</pre>
      </details>
      <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />
        {isZH ? '我已核對此院舍的設定及來源，同意用於生成待覆核草稿。' : 'I reviewed this facility’s settings and sources for draft generation.'}
      </label>
    </div>}
    {error && <p role="alert" className="text-xs text-rose-700">{error}</p>}
    <button type="button" disabled={!confirmed || !profile || busy} onClick={() => void save()} className="rounded-lg bg-pink-600 text-white px-3 py-2 text-xs disabled:opacity-40">{busy ? '…' : isZH ? '確認並儲存設定版本' : 'Confirm and save version'}</button>
  </section>
}
