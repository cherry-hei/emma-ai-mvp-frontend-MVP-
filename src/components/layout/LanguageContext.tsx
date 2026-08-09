'use client'
import {
  createContext, useCallback, useContext, useEffect, useSyncExternalStore, ReactNode,
} from 'react'

type Lang = 'en' | 'zh'

const STORE_KEY = 'emma_lang'

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
  nav_scheduling:    '排班規則設定',
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
  topnav_scheduling: '排班規則設定',
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

  // ── Staff App (phone) ───────────────────────────────────────────────────────
  // The staff app renders chromeless, without the desktop TopNav, so it carries
  // its own copies of the account menu and language toggle - these keys are what
  // make the toggle mean something once it is there.
  sa_brand:             'Emma AI · 員工手機 App',
  sa_fallback_name:     '員工手機 App',
  sa_loading:           '載入中…',
  sa_load_error_title:  '無法載入員工資料',
  sa_load_error_hint:   '此頁需要以綁定員工紀錄的帳戶登入。',
  sa_account:           '帳戶',
  sa_signed_in_as:      '已登入',
  sa_language:          '語言',
  sa_sign_out:          '登出',
  sa_settings:          '設定',

  // bottom nav
  sa_tab_home:          '首頁',
  sa_tab_tasks:         '工作',
  sa_tab_shift:         '更表',
  sa_tab_clockin:       '打卡',
  sa_tab_profile:       '我的',

  // home
  sa_today:             '今日值班',
  sa_tasks_pending:     '待辦工作',
  sa_hours_progress:    '本週期工時進度',
  sa_hours_unit:        '小時',
  sa_ratio:             '院舍人手比率',
  sa_ratio_items:       '項合規',
  sa_ratio_none:        '未有比率資料',
  sa_today_tasks:       '今日重點工作',
  sa_items_suffix:      '項',
  sa_done:              '已完成',
  sa_pending:           '待處理',
  sa_no_tasks_today:    '今日沒有指定工作',
  sa_today_clock:       '今日打卡',
  sa_clock_in_time:     '上班時間',
  sa_worked:            '已工作',

  // tasks
  sa_task_list:         '今日工作清單',
  sa_task_hint:         '點擊可切換完成狀態',
  sa_update_failed:     '更新失敗',
  sa_completed_at:      '完成於',

  // my shift
  sa_my_roster:         '我的更表',
  sa_days_suffix:       '日',
  sa_today_short:       '今日',
  sa_roster_error:      '無法載入更表',

  // clock in
  sa_clocked_out_at:    '已下班打卡',
  sa_worked_today:      '本日已工作',
  sa_not_clocked_in:    '尚未打卡',
  sa_month_hours:       '本月工時',
  sa_days_unit:         '天',
  sa_today_clock_log:   '今日打卡記錄',
  sa_clock_in:          '上班',
  sa_clock_out:         '下班',
  sa_btn_clock_in:      '上班打卡',
  sa_btn_clock_out:     '下班打卡',
  sa_hide_log:          '隱藏打卡記錄',
  sa_show_log:          '查看打卡記錄',
  sa_no_log:            '尚無打卡記錄',
  sa_attendance_error:  '無法載入打卡記錄',
  sa_clock_failed:      '打卡失敗',

  // profile
  sa_my_details:        '我的資料',
  sa_name_en:           '英文名',
  sa_unit:             '工作單位',
  sa_cycle_scheduled:   '本週期排更工時',
  sa_hours_pct:         '工時進度',
  sa_month_actual:      '本月實際打卡',
  sa_certs:             '專業資格',
  sa_no_certs:          '尚無證書記錄',
  sa_expired:           '已過期',
  sa_mentor:            '導師',
  sa_med_audited:       '藥物審核',
  sa_my_requests:       '我的申請',
  sa_no_requests:       '尚無假期或更期申請',
  sa_profile_error:     '無法載入個人資料',
  sa_status_approved:   '已批准',
  sa_status_rejected:   '已拒絕',
  sa_status_pending:    '待審批',

  // push opt-in
  sa_push_title:        '開啟通知',
  sa_push_body:         '批假結果、更表更新同任務提醒會即時通知你。',
  sa_push_denied:       '通知已被封鎖，請在瀏覽器設定中允許。',
  sa_push_failed:       '暫時無法開啟，請稍後再試。',
  sa_push_working:      '處理中…',
  sa_push_enable:       '開啟',
  sa_push_later:        '稍後',
}

const EN: Record<string, string> = {
  nav_dashboard:     'Dashboard',
  nav_home:          'Home',
  nav_roster:        'Roster',
  nav_scheduling:    'Scheduling Rules',
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
  topnav_scheduling: 'Scheduling Rules',
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

  // ── Staff App (phone) ───────────────────────────────────────────────────────
  sa_brand:             'Emma AI · Staff App',
  sa_fallback_name:     'Staff App',
  sa_loading:           'Loading…',
  sa_load_error_title:  'Cannot load staff data',
  sa_load_error_hint:   'Sign in with a staff-linked account to use the staff app.',
  sa_account:           'Account',
  sa_signed_in_as:      'Signed in as',
  sa_language:          'Language',
  sa_sign_out:          'Sign out',
  sa_settings:          'Settings',

  // bottom nav
  sa_tab_home:          'Home',
  sa_tab_tasks:         'Tasks',
  sa_tab_shift:         'Roster',
  sa_tab_clockin:       'Clock',
  sa_tab_profile:       'Me',

  // home
  sa_today:             'Today',
  sa_tasks_pending:     'To do',
  sa_hours_progress:    'Cycle hours',
  sa_hours_unit:        'hrs',
  sa_ratio:             'Facility staffing ratio',
  sa_ratio_items:       'checks passing',
  sa_ratio_none:        'No ratio data',
  sa_today_tasks:       'Today’s tasks',
  sa_items_suffix:      'open',
  sa_done:              'Done',
  sa_pending:           'Pending',
  sa_no_tasks_today:    'No tasks assigned today',
  sa_today_clock:       'Today’s attendance',
  sa_clock_in_time:     'Clocked in',
  sa_worked:            'Worked',

  // tasks
  sa_task_list:         'Today’s task list',
  sa_task_hint:         'Tap a task to toggle it done',
  sa_update_failed:     'Update failed',
  sa_completed_at:      'done at',

  // my shift
  sa_my_roster:         'My Roster',
  sa_days_suffix:       'days',
  sa_today_short:       'Today',
  sa_roster_error:      'Failed to load roster',

  // clock in
  sa_clocked_out_at:    'Clocked out',
  sa_worked_today:      'Worked today',
  sa_not_clocked_in:    'Not clocked in yet',
  sa_month_hours:       'Hours this month',
  sa_days_unit:         'days',
  sa_today_clock_log:   'Today’s clock records',
  sa_clock_in:          'Clock in',
  sa_clock_out:         'Clock out',
  sa_btn_clock_in:      'Clock in',
  sa_btn_clock_out:     'Clock out',
  sa_hide_log:          'Hide clock history',
  sa_show_log:          'View clock history',
  sa_no_log:            'No clock records yet',
  sa_attendance_error:  'Failed to load attendance',
  sa_clock_failed:      'Clock action failed',

  // profile
  sa_my_details:        'My details',
  sa_name_en:           'English name',
  sa_unit:              'Unit',
  sa_cycle_scheduled:   'Scheduled hours this cycle',
  sa_hours_pct:         'Hours progress',
  sa_month_actual:      'Actually clocked this month',
  sa_certs:             'Certificates',
  sa_no_certs:          'No certificates on record',
  sa_expired:           'Expired',
  sa_mentor:            'Mentor',
  sa_med_audited:       'Med. audited',
  sa_my_requests:       'My requests',
  sa_no_requests:       'No leave or shift-swap requests',
  sa_profile_error:     'Failed to load profile',
  sa_status_approved:   'Approved',
  sa_status_rejected:   'Rejected',
  sa_status_pending:    'Pending',

  // push opt-in
  sa_push_title:        'Turn on notifications',
  sa_push_body:         'Get told when your leave is decided, your roster is published, or a task needs you.',
  sa_push_denied:       'Notifications are blocked for this site - allow them in your browser settings.',
  sa_push_failed:       'Could not turn them on just now.',
  sa_push_working:      'Working…',
  sa_push_enable:       'Turn on',
  sa_push_later:        'Not now',
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

// ── Persisted language, as an external store ─────────────────────────────────
// Module scope so the snapshot/subscribe functions are stable identities, which
// is what useSyncExternalStore needs to avoid resubscribing every render.

const listeners = new Set<() => void>()

// Set once the user picks a language this session. Consulted ahead of
// localStorage so the toggle still works where writes throw (private-mode
// Safari) - there the choice simply does not outlive the tab.
let chosen: Lang | null = null

function readLang(): Lang {
  if (chosen) return chosen
  try {
    const stored = window.localStorage.getItem(STORE_KEY)
    if (stored === 'zh' || stored === 'en') return stored
  } catch {
    // Storage unavailable (private mode, blocked cookies) - fall through.
  }
  return 'en'
}

// Server render has no localStorage, so it always emits the default. Returning a
// primitive keeps the snapshot stable by value, which is what React compares.
function readServerLang(): Lang {
  return 'en'
}

function writeLang(next: Lang) {
  chosen = next
  try {
    window.localStorage.setItem(STORE_KEY, next)
  } catch {
    // Ignored: `chosen` above already carries the choice for this tab.
  }
  listeners.forEach((l) => l())
}

function subscribeLang(onChange: () => void) {
  listeners.add(onChange)
  // Another tab (or the installed app alongside the browser tab) changing the
  // setting should win here too, so drop our session override and re-read.
  const onStorage = (e: StorageEvent) => {
    if (e.key !== STORE_KEY) return
    chosen = null
    onChange()
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(onChange)
    window.removeEventListener('storage', onStorage)
  }
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  // The choice is persisted because the staff app installs to a phone home
  // screen: a toggle that resets on every cold start is not a language setting.
  //
  // Read through useSyncExternalStore rather than a useState + useEffect pair.
  // localStorage is an external store, and the server has none - so it needs a
  // distinct server snapshot ('en') to hydrate against, which this gives us
  // without a setState-in-effect that would paint the default and then flip.
  const lang = useSyncExternalStore(subscribeLang, readLang, readServerLang)
  const setLang = writeLang

  // Keep <html lang> honest for screen readers and for the browser's own
  // translate-this-page offer - machine-translating the page is what turned
  // "Emma AI" into 艾瑪·艾.
  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-HK' : 'en'
  }, [lang])

  // Stable per-language, so screens that build a fallback error message with `t`
  // can list it in their effect deps without re-fetching on every render.
  const t = useCallback(
    (key: string) => ((lang === 'zh' ? ZH[key] : EN[key]) ?? key),
    [lang],
  )

  return (
    <LangContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LangContext.Provider>
  )
}

export const useLang = () => useContext(LangContext)