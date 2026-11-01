'use client'

import { useState } from 'react'
import { useLang } from '@/components/layout/LanguageContext'
import { NAAC_UI_ROLES, NAAC_UI_ACTIONS, isNaacUiRole, naacUiAllows, naacUiScope, type NaacUiRole, type NaacUiAction } from '@/lib/naac-ui-policy'

const roles: Record<NaacUiRole, [string, string]> = {
  superintendent: ['Superintendent', '主任'],
  appointed_deputy: ['Appointed deputy (SW1)', '獲委任副手（SW1）'],
  nurse: ['Nurse', '護士'], staff: ['Staff', '職員'],
}
const actions: Record<NaacUiAction, [string, string]> = {
  personal_view: ['Personal view', '個人檢視'], unit_view: ['Unit view', '單位檢視'],
  organisation_view: ['Organisation view', '機構檢視'], batch_generate: ['Batch generation', '批次產生更表'],
  rules_dictionary: ['Rules dictionary', '規則字典'], preliminary_review: ['Preliminary review', '初步審核'],
  reports_excel: ['Reports / Excel', '報告／Excel'], audit: ['Audit', '審計紀錄'],
  staff_role_qualification_management: ['Staff roles and qualifications', '職員角色及資格管理'],
  draft_shift_edit: ['Draft shift editing', '編輯草稿更表'], final_decision: ['Final decision', '最終決定'], publish: ['Publish', '發布'],
}

/** Static review model only. AppShell guards this route via facility.settings. */
export default function NaacAccessPreview() {
  const { lang } = useLang()
  const zh = lang === 'zh'
  const [role, setRole] = useState<NaacUiRole>('superintendent')
  const label = (pair: [string, string]) => pair[zh ? 1 : 0]
  const scope = naacUiScope(role)
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 text-base leading-relaxed text-slate-900 md:p-6">
      <header className="space-y-3 rounded-2xl border border-pink-200 bg-white p-5 shadow-sm">
        <p className="font-semibold text-pink-700">{zh ? '僅供主任審閱 · NAAC 介面預覽' : 'Owner review only · NAAC UI preview'}</p>
        <h1 className="text-2xl font-bold">{zh ? '四種角色的介面政策' : 'Four-role interface policy'}</h1>
        <p>Preview only — does not change signed-in permissions; server-side RBAC/RLS required before rollout</p>
        <p lang="zh-Hant">僅供預覽 — 不會更改登入者權限；推出前必須落實伺服器端 RBAC／RLS。</p>
      </header>
      <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
        <label htmlFor="preview-role" className="block font-semibold">{zh ? '預覽角色（並非目前登入角色）' : 'Preview role (not your signed-in role)'}</label>
        <select id="preview-role" value={role} onChange={event => { if (isNaacUiRole(event.target.value)) setRole(event.target.value) }} className="w-full min-w-0 rounded-lg border border-slate-400 bg-white p-3 text-base focus-visible:outline-pink-600">
          {NAAC_UI_ROLES.map(value => <option key={value} value={value}>{label(roles[value])}</option>)}
        </select>
        <p aria-live="polite">{zh ? '檢視範圍：' : 'View scope: '}{scope === 'organisation' ? (zh ? '機構（包括個人及單位）' : 'Organisation (including personal and unit)') : (zh ? '所屬單位及個人' : 'Assigned unit and personal')}</p>
        <p>{zh ? 'SW1 職銜不等同獲委任副手；角色須於未來部署時明確綁定。護士只可在所屬單位範圍編輯草稿。' : 'An SW1 job title does not appoint a deputy; future deployment requires explicit identity binding. Nurses may edit drafts only within their assigned unit.'}</p>
      </section>
      <section className="space-y-4" aria-labelledby="modules-title">
        <h2 id="modules-title" className="text-xl font-semibold">{zh ? '可見模組及獲准操作（12 項）' : 'Visible modules and allowed actions (12)'}</h2>
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {NAAC_UI_ACTIONS.map(action => {
            const allowed = naacUiAllows(role, action)
            return <li key={action} className="min-w-0 space-y-2 break-words rounded-2xl border border-slate-200 bg-white p-4">
              <h3 className="font-semibold">{label(actions[action])}</h3>
              <p className={allowed ? 'text-pink-700' : 'text-slate-600'}>{allowed ? (zh ? '可見 · 政策允許' : 'Visible · allowed by policy') : (zh ? '實際介面隱藏 · 政策不允許' : 'Hidden in intended UI · denied by policy')}</p>
              <button type="button" disabled className="rounded-lg border border-slate-300 bg-slate-100 px-3 py-2 text-base text-slate-600">{zh ? '僅供審閱 · 操作已停用' : 'Review only · action disabled'}</button>
            </li>
          })}
        </ul>
      </section>
      <footer className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
        <p>{zh ? '職員申請及聊天使用 Staff PWA；本頁不會提交申請或發送訊息。' : 'Staff requests and chat belong in Staff PWA; this page submits no requests or messages.'}</p>
        <p>{zh ? '未接駁真實資料或操作。未授予薪金、成本、歷史、ROI、財務合規、邀請或額外管理權限。' : 'No live data or operations are connected. No salary, cost, history, ROI, financial compliance, invitation or additional administration authority is granted.'}</p>
      </footer>
    </div>
  )
}
