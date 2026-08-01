'use client'
import { createContext, useContext, useState, ReactNode } from 'react'

type Lang = 'en' | 'zh'

// Hong Kong Traditional Chinese. Terminology follows the homes' own duty rosters
// (see src/lib/vocab.ts for rank/shift/leave codes).
//
// "Emma AI" is a product name and is never translated - transliterating it to
// 艾瑪·艾 was one symptom of a page being machine-translated by the browser
// rather than by us.
const ZH: Record<string, string> = {
  nav_dashboard:     '儀表板',
  nav_home:          '主頁',
  nav_roster:        '更表',
  nav_scheduling:    '任務排程',
  nav_compliance:    '合規',
  nav_approval:      '審批',
  nav_personnel:     '員工檔案',
  nav_roi:           '投資回報',
  nav_reports:       '報告',
  nav_alert:         '警報中心',
  nav_ai:            'AI 洞察',
  urgent_alert:      '🚨 緊急警報',
  staff_shortage:    'P更人手不足 - F3',
  new_request:       '+ 新增請求',
  topnav_roster:     '更表',
  topnav_scheduling: '任務排程',
  topnav_staffing:   '人手',
  topnav_compliance: '合規',
  topnav_reports:    '報告',
  search_ph:         '搜尋...',

  // roster page
  roster_create_shift:  '新增更份',
  roster_create_event:  '新增特別活動',
  roster_save:          '儲存',
  roster_save_publish:  '儲存並發佈',
  roster_ai_suggest:    'AI 排更建議',
  roster_validate:      '驗證',
  roster_draft:         '草稿',
  roster_published:     '已發佈',
  roster_period:        '更表週期',

  // staff portfolio
  staff_add:            '新增員工',
  staff_title:          '員工檔案',
  staff_headcount:      '在職人數',
  staff_certificates:   '證書',
  staff_cert_expiring:  '即將到期',
  staff_contract:       '合約',
  staff_part_time:      '兼職',

  // approvals
  approve_recommend:    '建議批准',
  approve_reject_rec:   '建議拒絕',
  approve_final:        '最終批准',
  approve_reject:       '拒絕',
  approve_revoke:       '撤回批准',
  approve_reason:       '理由',
  approve_pending:      '待審批',

  // common
  common_loading:       '載入中…',
  common_save:          '儲存',
  common_cancel:        '取消',
  common_close:         '關閉',
  common_download:      '下載',
  common_search:        '搜尋',
  common_total:         '總計',
  common_none:          '沒有紀錄',
  common_rank:          '職級',
  common_shift:         '更份',
  common_date:          '日期',
  common_status:        '狀態',
  common_staff:         '員工',
  common_facility:      '院舍',
  common_no_access:     '你的權限不可查看此頁',
}

const EN: Record<string, string> = {
  nav_dashboard:     'Dashboard',
  nav_home:          'Home',
  nav_roster:        'Roster',
  nav_scheduling:    'Task Scheduling',
  nav_compliance:    'Compliance',
  nav_approval:      'Approval',
  nav_personnel:     'Staff Portfolio',
  nav_roi:           'ROI',
  nav_reports:       'Reports',
  nav_alert:         'Alert Centre',
  nav_ai:            'AI Insights',
  urgent_alert:      '🚨 Urgent Alert',
  staff_shortage:    'P-shift understaffed - F3',
  new_request:       '+ New Request',
  topnav_roster:     'Roster',
  topnav_scheduling: 'Task Scheduling',
  topnav_staffing:   'Staffing',
  topnav_compliance: 'Compliance',
  topnav_reports:    'Reports',
  search_ph:         'Search anything...',

  // roster page
  roster_create_shift:  'Create Shift',
  roster_create_event:  'Create Special Event',
  roster_save:          'Save',
  roster_save_publish:  'Save & Publish',
  roster_ai_suggest:    'AI Suggestion',
  roster_validate:      'Validate',
  roster_draft:         'Draft',
  roster_published:     'Published',
  roster_period:        'Roster Period',

  // staff portfolio
  staff_add:            'Add staff',
  staff_title:          'Staff Portfolio',
  staff_headcount:      'Headcount',
  staff_certificates:   'Certificates',
  staff_cert_expiring:  'Expiring soon',
  staff_contract:       'Contract',
  staff_part_time:      'Part-time',

  // approvals
  approve_recommend:    'Recommend approve',
  approve_reject_rec:   'Recommend reject',
  approve_final:        'Approve',
  approve_reject:       'Reject',
  approve_revoke:       'Revoke approval',
  approve_reason:       'Reason',
  approve_pending:      'Pending',

  // common
  common_loading:       'Loading…',
  common_save:          'Save',
  common_cancel:        'Cancel',
  common_close:         'Close',
  common_download:      'Download',
  common_search:        'Search',
  common_total:         'Total',
  common_none:          'No records',
  common_rank:          'Rank',
  common_shift:         'Shift',
  common_date:          'Date',
  common_status:        'Status',
  common_staff:         'Staff',
  common_facility:      'Facility',
  common_no_access:     'Your role may not view this page',
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