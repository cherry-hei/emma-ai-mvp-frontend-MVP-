'use client'

import { useLang } from '@/components/layout/LanguageContext'

export default function InsightsPage() {
  const { lang } = useLang()
  const isZH = lang === 'zh'

  return (
    <div className="p-5 space-y-4">
      <div>
        <h1 className="text-lg font-bold text-gray-900">{isZH ? 'AI 洞察' : 'AI Insights'}</h1>
        <p className="text-xs text-gray-500 mt-0.5">
          {isZH ? '跨頁面的 AI 分析摘要（開發中）' : 'Cross-page AI analysis summary (in development)'}
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
        <div className="text-3xl mb-2">🤖</div>
        <div className="text-sm font-semibold text-gray-700">
          {isZH ? '此功能尚未建立' : 'This feature has not been built yet'}
        </div>
        <p className="text-xs text-gray-400 mt-2 max-w-md mx-auto">
          {isZH
            ? 'Cherry 的原始設計包含此導覽項目，但 frontend-main 本身亦未有對應頁面。目前的 Emma AI 分析已分散於各頁面（儀表板、警報中心、合規監察）；此頁面待範圍確認後建立。'
            : "Cherry's design includes this nav item, but frontend-main itself has no page behind it either. Emma AI's analysis currently lives on the individual pages (Dashboard, Alert Centre, Compliance); this page is a placeholder until the feature is scoped."}
        </p>
      </div>
    </div>
  )
}
