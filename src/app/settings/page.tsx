'use client'

import Link from 'next/link'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { ROUTES, ROUTE_FEATURE, canOpenRoute } from '@/components/layout/navRoutes'

/** Route to settings backed by the current organisation-scoped API.
 * The previous screen kept restrictions in React memory and said "Saved" even
 * though the scheduling engine never received those values.
 */
export default function SettingsPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const zh = lang === 'zh'
  const links = [
    {
      path: ROUTES.scheduling,
      feature: ROUTE_FEATURE[ROUTES.scheduling],
      title: zh ? '排班規則與營運配置' : 'Scheduling rules & operations',
      details: zh ? '活動人手、員工資格及樓層最低人數；由院舍專屬後端讀取及儲存。' : 'Event staffing, qualifications and floor minimums; read and saved through the facility-scoped API.',
    },
    {
      path: '/shift-codes',
      feature: ROUTE_FEATURE['/shift-codes'],
      title: zh ? '更期代號字典' : 'Shift code dictionary',
      details: zh ? '顯示目前登入機構的代號、時間及工時；此頁現時唯讀，匯入仍需確認來源。' : 'View the signed-in organisation’s codes, times and paid hours. Read-only here; imported mappings still need confirmation.',
    },
  ]

  return (
    <main className="mx-auto max-w-4xl space-y-5 p-5 md:p-8">
      <header>
        <h1 className="text-xl font-bold text-slate-900">{zh ? '設定' : 'Settings'}</h1>
        <p className="mt-1 text-sm text-slate-600">{zh ? '使用有後端資料來源的機構設定；未啟用的選項不會當成已套用。' : 'Organisation-scoped settings with a backend source; unavailable controls are not presented as active.'}</p>
      </header>

      <div className="grid gap-3 md:grid-cols-2">
        {links.filter(item => canOpenRoute(user?.role, item.feature)).map(item => (
          <Link key={item.path} href={item.path}
            className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-colors hover:border-pink-300 hover:bg-pink-50/30 focus-visible:outline-2 focus-visible:outline-pink-500">
            <h2 className="font-bold text-slate-900">{item.title} <span aria-hidden="true" className="text-pink-600">→</span></h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{item.details}</p>
          </Link>
        ))}
      </div>

      <aside className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-950">
        <strong>{zh ? '尚未接入規則引擎：' : 'Not yet connected to the rules engine: '}</strong>
        {zh ? '通用「強制執行／盡量滿足」切換、個別員工硬性限制、外勞設定及個人偏好，原有示範表單並無持久化。待機構確認規則、權限及後端儲存／驗證後，才可啟用。' : 'Universal Enforce/Try-best toggles, individual staff restrictions, imported-worker settings and preferences were previously demo-only and not persisted. Enable only after the organisation confirms rules, permissions and backend validation.'}
      </aside>
    </main>
  )
}
