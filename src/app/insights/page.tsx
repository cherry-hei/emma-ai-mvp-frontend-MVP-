'use client'

import { useLang } from '@/components/layout/LanguageContext'
import EmmaAiWorkspace from '@/components/ai/EmmaAiWorkspace'

export default function InsightsPage() {
  const { lang } = useLang()
  return <EmmaAiWorkspace isZH={lang === 'zh'} />
}
