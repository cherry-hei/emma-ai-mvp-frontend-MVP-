'use client'

import type { RosterOption } from '@/lib/apiTypes'

const PINK = '#E8187A'
const PUBLISH_THRESHOLD = 60

type PlanMeta = { title: string; desc: string }

function planMeta(isZH: boolean): Record<string, PlanMeta> {
  return {
    A: { title: isZH ? '成本優化' : 'Cost-Optimized', desc: isZH ? '減少外判及超時' : 'Minimize agency & overtime' },
    B: { title: isZH ? '員工滿意度' : 'Staff-Satisfaction', desc: isZH ? '尊重員工請求及休假' : 'Honor requests & days off' },
    C: { title: isZH ? '平衡方案' : 'Balanced', desc: isZH ? '推薦的折衷方案' : 'Recommended middle ground' },
  }
}

const STATUS_COLOR: Record<string, string> = {
  optimal: '#15803d', feasible: '#b45309', infeasible: '#be123c', unknown: '#6b7280',
}

export interface AiOptionsModalProps {
  options: RosterOption[] | null
  loading: boolean
  status: string
  error: string
  periodLabel?: string
  isZH: boolean
  onSelect: (versionId: string) => void
  onClose: () => void
}

export function AiOptionsModal({
  options, loading, status, error, periodLabel, isZH, onSelect, onClose,
}: AiOptionsModalProps) {
  const meta = planMeta(isZH)
  const L = {
    title: isZH ? '🤖 AI 更表方案 (A/B/C)' : '🤖 AI Roster Options (A/B/C)',
    generating: isZH ? '正在生成三個方案…' : 'Generating three options…',
    score: isZH ? '合規分數' : 'Constraint score',
    violations: isZH ? '硬性違規' : 'Hard violations',
    agency: isZH ? '外判' : 'Agency',
    ot: isZH ? '超時' : 'OT',
    gap: isZH ? '人手缺口' : 'Coverage gap',
    select: isZH ? '選擇並檢視規則' : 'Select & review rules',
    notPublishable: isZH ? '不可選擇' : 'Not selectable',
    qualityWarning: isZH ? '低分反映soft取捨；選擇後須逐項檢視及確認當前soft例外。' : 'Low score reflects soft trade-offs; review and acknowledge each current soft finding after selection.',
    close: isZH ? '關閉' : 'Close',
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,0,0,0.45)' }} onClick={onClose}>
      <div className="bg-white w-full max-w-4xl rounded-3xl shadow-2xl overflow-hidden max-h-[88vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}>
        <div className="px-7 py-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-gray-900">{L.title}</h2>
            {periodLabel && <div className="text-[11px] text-gray-400 mt-0.5">{periodLabel}</div>}
          </div>
          <button onClick={onClose}
            className="w-8 h-8 rounded-full bg-gray-100 hover:bg-gray-200 text-gray-600 font-bold">✕</button>
        </div>

        <div className="p-7 overflow-y-auto">
          {loading ? (
            <div className="py-16 text-center">
              <div className="inline-block w-10 h-10 border-4 border-gray-200 rounded-full animate-spin"
                style={{ borderTopColor: PINK }} />
              <div className="mt-4 text-sm text-gray-600">{L.generating}</div>
              <div className="mt-1 text-xs text-gray-400 uppercase tracking-widest">{status}</div>
            </div>
          ) : error ? (
            <div className="py-12 text-center text-sm text-rose-600">{error}</div>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {(options ?? []).map((o) => {
                const m = meta[o.plan_mode] ?? { title: o.plan_mode, desc: '' }
                const lowQuality = o.constraint_score < PUBLISH_THRESHOLD
                const selectable = !!o.roster_version_id && o.hard_violation_count === 0 && o.status !== 'infeasible'
                const scoreColor = o.hard_violation_count > 0 ? '#be123c' : lowQuality ? '#b45309' : '#15803d'
                return (
                  <div key={o.plan_mode}
                    className="rounded-2xl border border-gray-200 p-5 flex flex-col"
                    style={o.plan_mode === 'C' ? { borderColor: PINK, boxShadow: `0 0 0 1px ${PINK}` } : undefined}>
                    <div className="flex items-center justify-between">
                      <div className="text-xs font-black tracking-widest text-gray-400">{o.plan_mode}</div>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full text-white"
                        style={{ background: STATUS_COLOR[o.status] ?? '#6b7280' }}>
                        {o.status}
                      </span>
                    </div>
                    <div className="mt-1 text-sm font-bold text-gray-900">{m.title}</div>
                    <div className="text-[11px] text-gray-500 mb-3">{m.desc}</div>

                    <div className="flex items-end gap-1">
                      <span className="text-3xl font-black" style={{ color: scoreColor }}>{o.constraint_score}</span>
                      <span className="text-[10px] text-gray-400 mb-1.5 uppercase">{L.score}</span>
                    </div>
                    <div className="text-[11px] text-gray-500 mb-3">
                      {L.violations}: <span className="font-bold text-gray-800">{o.hard_violation_count}</span>
                    </div>

                    <div className="grid grid-cols-3 gap-2 mb-4">
                      {[
                        { k: L.agency, v: o.kpi.agency_count },
                        { k: L.ot, v: `${o.kpi.ot_hours}h` },
                        { k: L.gap, v: o.kpi.coverage_gap },
                      ].map((s) => (
                        <div key={s.k} className="bg-gray-50 rounded-xl p-2 text-center">
                          <div className="text-sm font-bold text-gray-900">{s.v}</div>
                          <div className="text-[9px] text-gray-400 uppercase">{s.k}</div>
                        </div>
                      ))}
                    </div>

                    {o.infeasible_reasons.length > 0 && (
                      <div className="text-[10px] text-rose-500 mb-3">
                        {o.infeasible_reasons.slice(0, 2).join('; ')}
                      </div>
                    )}
                    {lowQuality && o.hard_violation_count === 0 && (
                      <div className="text-[10px] text-amber-700 mb-3">{L.qualityWarning}</div>
                    )}

                    <button
                      disabled={!selectable}
                      onClick={() => o.roster_version_id && onSelect(o.roster_version_id)}
                      className="mt-auto py-2.5 rounded-xl text-xs font-bold text-white transition-colors disabled:cursor-not-allowed"
                      style={{ background: selectable ? PINK : '#d1d5db' }}>
                      {selectable ? L.select : L.notPublishable}
                    </button>
                  </div>
                )
              })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
