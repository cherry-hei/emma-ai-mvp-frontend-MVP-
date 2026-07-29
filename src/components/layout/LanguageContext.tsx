'use client'
import { createContext, useContext, useState, ReactNode } from 'react'

type Lang = 'en' | 'zh'

const ZH: Record<string, string> = {
  nav_dashboard:     '儀表板',
  nav_home:          '主頁',
  nav_roster:        '更表',
  nav_compliance:    '合規',
  nav_approval:      '審批',
  nav_personnel:     '員工檔案',
  nav_roi:           'ROI',
  nav_reports:       '報告',
  nav_alert:         '警報',
  nav_ai:            'AI 洞察',
  urgent_alert:      '🚨 緊急警報',
  staff_shortage:    'P更人手不足 — F3',
  new_request:       '+ 新增請求',
  topnav_roster:     '更表',
  topnav_scheduling: '任務排程',
  topnav_staffing:   '人手',
  topnav_compliance: '合規',
  topnav_reports:    '報告',
  search_ph:         '搜尋...',
}

const EN: Record<string, string> = {
  nav_dashboard:     'Dashboard',
  nav_home:          'Home',
  nav_roster:        'Roster',
  nav_compliance:    'Compliance',
  nav_approval:      'Approval',
  nav_personnel:     'Staff Portfolio',
  nav_roi:           'ROI',
  nav_reports:       'Reports',
  nav_alert:         'Alert',
  nav_ai:            'AI Insights',
  urgent_alert:      '🚨 Urgent Alert',
  staff_shortage:    'P-shift understaffed — F3',
  new_request:       '+ New Request',
  topnav_roster:     'Roster',
  topnav_scheduling: 'Task Scheduling',
  topnav_staffing:   'Staffing',
  topnav_compliance: 'Compliance',
  topnav_reports:    'Reports',
  search_ph:         'Search anything...',
}

interface LangCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: string) => string
}

const LangContext = createContext<LangCtx>({
  lang: 'en',
  setLang: () => {},
  t: (k) => k,
})

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>('en')
  const t = (key: string) => (lang === 'zh' ? ZH[key] : EN[key]) ?? key
  return (
    <LangContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LangContext.Provider>
  )
}

export const useLang = () => useContext(LangContext)