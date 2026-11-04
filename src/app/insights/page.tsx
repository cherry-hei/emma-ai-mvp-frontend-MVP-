'use client'

import { useLang } from '@/components/layout/LanguageContext'
import EmmaAiWorkspace from '@/components/ai/EmmaAiWorkspace'
import { useAuth } from '@/components/layout/AuthContext'

export default function InsightsPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const scope = user ? `${user.userId}:${user.facilityId ?? ''}:${user.role ?? ''}` : 'anonymous'
  return <EmmaAiWorkspace key={scope} isZH={lang === 'zh'} />
}
