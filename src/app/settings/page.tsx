'use client'

import Link from 'next/link'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { canRead } from '@/lib/permissions'

/** Navigation only. Each destination keeps its API and server permission checks. */
export default function SettingsPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const isZH = lang === 'zh'
  const items = [
    {
      href: '/scheduling', visible: canRead(user?.role, 'task_codes'),
      title: isZH ? '工作規則、資格及活動' : 'Task Rules, Qualifications & Events',
      description: isZH ? '管理現有MVP的工作資格、活動及單位人手規則；讀寫仍由後端核對權限。' : 'Open the existing MVP qualification, event and unit staffing controls. The backend still enforces read/write permissions.',
    },
    {
      href: '/shift-codes', visible: canRead(user?.role, 'roster.view'),
      title: isZH ? '更期代號字典' : 'Shift Code Dictionary',
      description: isZH ? '查看目前登入機構的更碼、工作時段及已確認工時；不使用博愛Demo字典。' : 'Read shift codes, time ranges and credited hours from the signed-in organisation, not the PoKoi demo.',
    },
  ].filter(item => item.visible)
  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 md:p-6">
      <header className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">{isZH ? '設定' : 'Settings'}</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">{isZH ? '設定分項沿用目前MVP的真實API。文字大小及語言可在頂部帳戶工具列調整。' : 'These settings use the existing MVP API. Change text size and language from the account toolbar.'}</p>
      </header>
      <div className="emma-reflow-stack grid grid-cols-1 gap-4 md:grid-cols-2">
        {items.map(item => <Link key={item.href} href={item.href} className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-colors hover:border-pink-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-300">
          <h2 className="break-words text-lg font-semibold text-slate-900">{item.title}</h2>
          <p className="mt-2 break-words text-sm leading-relaxed text-slate-500">{item.description}</p>
          <span className="mt-4 block text-sm font-semibold text-pink-600">{isZH ? '開啟設定' : 'Open settings'}</span>
        </Link>)}
      </div>
      <p className="text-sm leading-relaxed text-slate-500">{isZH ? '其他院舍設定尚未完成API接駁；不會顯示虛構院舍數值或將未保存的設定標示為已儲存。' : 'Other facility settings are not yet integrated. No sample facility values or false saved confirmation are shown.'}</p>
    </div>
  )
}
