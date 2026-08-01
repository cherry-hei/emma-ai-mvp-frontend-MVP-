# Emma AI - Chinese (zh-HK) review sheet

Generated from `src/components/layout/LanguageContext.tsx` and `src/lib/vocab.ts` at commit `04ced86`. 62 strings.

**How to review:** add a column or annotate any row whose Chinese is wrong.
Terminology follows the homes' own duty rosters, so where our wording differs
from what staff actually say on the floor, the floor wins.

Two notes on things that are intentional:

- **`Emma AI` is never translated.** It is a product name.
- **Rank/shift/leave codes keep their code in brackets** - `健康護理員（HCA）` -
  so a bilingual floor can still match the label to the paper roster. Codes are
  never shown bare in Chinese: an untranslated `HCA` is what a browser's
  auto-translate rendered as 氫氯噻嗪 (hydrochlorothiazide).


## navigation

| key | English | 中文 |
|---|---|---|
| `nav_dashboard` | Dashboard | 儀表板 |
| `nav_home` | Home | 主頁 |
| `nav_roster` | Roster | 更表 |
| `nav_scheduling` | Task Scheduling | 任務排程 |
| `nav_compliance` | Compliance | 合規 |
| `nav_approval` | Approval | 審批 |
| `nav_personnel` | Staff Portfolio | 員工檔案 |
| `nav_roi` | ROI | 投資回報 |
| `nav_reports` | Reports | 報告 |
| `nav_alert` | Alert Centre | 警報中心 |
| `nav_ai` | AI Insights | AI 洞察 |
| `urgent_alert` | 🚨 Urgent Alert | 🚨 緊急警報 |
| `staff_shortage` | P-shift understaffed - F3 | P更人手不足 - F3 |
| `new_request` | + New Request | + 新增請求 |
| `topnav_roster` | Roster | 更表 |
| `topnav_scheduling` | Task Scheduling | 任務排程 |
| `topnav_staffing` | Staffing | 人手 |
| `topnav_compliance` | Compliance | 合規 |
| `topnav_reports` | Reports | 報告 |
| `search_ph` | Search anything... | 搜尋... |

## roster page

| key | English | 中文 |
|---|---|---|
| `roster_create_shift` | Create Shift | 新增更份 |
| `roster_create_event` | Create Special Event | 新增特別活動 |
| `roster_save` | Save | 儲存 |
| `roster_save_publish` | Save & Publish | 儲存並發佈 |
| `roster_ai_suggest` | AI Suggestion | AI 排更建議 |
| `roster_validate` | Validate | 驗證 |
| `roster_draft` | Draft | 草稿 |
| `roster_published` | Published | 已發佈 |
| `roster_period` | Roster Period | 更表週期 |

## staff portfolio

| key | English | 中文 |
|---|---|---|
| `staff_add` | Add staff | 新增員工 |
| `staff_title` | Staff Portfolio | 員工檔案 |
| `staff_headcount` | Headcount | 在職人數 |
| `staff_certificates` | Certificates | 證書 |
| `staff_cert_expiring` | Expiring soon | 即將到期 |
| `staff_contract` | Contract | 合約 |
| `staff_part_time` | Part-time | 兼職 |

`staff_headcount` stays 在職人數. Cherry's answer made it conditional — 編制人數
if the key also drives the ROI page — and it does not: ROI carries its own labels
and this key is used only on Staff Portfolio, where the number is a count of
active staff.

## ROI staff baseline

ROI is where "headcount" means establishment, so the page now shows all three
numbers and the arithmetic between them is visible on screen.

| English | 中文 | source |
|---|---|---|
| Budgeted headcount | 編制人數 | derived: in post + vacancies (**added 1 Aug**) |
| Headcount (in post) | 在職人數 | counted from the staff table |
| Vacancies | 空缺人數 | entered per rank (was 空缺) |

編制人數 − 在職人數 = 空缺人數, and the salary budget standing against those
vacancies is the money available to hire.

在職 rather than 全職: full-time versus part-time is the separate FT/PT split on
the same card, and a part-timer in post still fills an establishment slot.

## approvals

| key | English | 中文 |
|---|---|---|
| `approve_recommend` | Recommend approve | 建議批准 |
| `approve_reject_rec` | Recommend reject | 建議拒絕 |
| `approve_final` | Approve | 最終批准 |
| `approve_reject` | Reject | 拒絕 |
| `approve_revoke` | Revoke approval | 撤回批准 |
| `approve_reason` | Reason | 理由 |
| `approve_pending` | Pending | 待審批 |

## common

| key | English | 中文 |
|---|---|---|
| `common_loading` | Loading… | 載入中… |
| `common_save` | Save | 儲存 |
| `common_cancel` | Cancel | 取消 |
| `common_close` | Close | 關閉 |
| `common_download` | Download | 下載 |
| `common_search` | Search | 搜尋 |
| `common_total` | Total | 總計 |
| `common_none` | No records | 沒有紀錄 |
| `common_rank` | Rank | 職級 |
| `common_shift` | Shift | 更份 |
| `common_date` | Date | 日期 |
| `common_status` | Status | 狀態 |
| `common_staff` | Staff | 員工 |
| `common_facility` | Facility | 院舍 |
| `common_no_access` | Your role may not view this page | 你的權限不可查看此頁 |

## vocab: ranks

| key | English | 中文 |
|---|---|---|
| `RN` | Registered Nurse | 註冊護士 |

## vocab: shifts

Confirmed by Cherry on 1 Aug 2026: the letter is the label, in both languages.
Both NGOs use the same A/P/N codes with different hours behind them — NAAC's A
shift is 07:15–15:15 and its A230 runs 14:30–22:30 — so "Morning" and 早更 are
not just unidiomatic, they are wrong. The hours come from the facility's own
shift dictionary, never from the name.

| key | English | 中文 | was |
|---|---|---|---|
| `A` | A shift | A更 | ~~Morning / 早更~~ |
| `B` | B shift | B更 | ~~Day / 日更~~ |
| `E` | E shift | E更 | ~~Evening / 黃昏更~~ |
| `P` | P shift | P更 | ~~Afternoon / 午更~~ |
| `N` | N shift | N更 | ~~Night / 夜更~~ |
| `AN` | AN shift | AN更 | ~~Overnight / 通宵更~~ |
| `NO` | Post-night rest | 通宵更後休息 | *added — NAAC's AN → NO → O rest rule* |
| `DO` | Day Off | 例假 | unchanged |
| `OFF` | Off | 休息 | unchanged |
| `SLEEP` | Sleep-in | 留宿 | unchanged |

`NO`, `DO`, `OFF` and `SLEEP` are not letter shift codes, so they keep a
descriptive name.

## vocab: leave

| key | English | 中文 |
|---|---|---|
| `AL` | Annual Leave | 年假 |

## vocab: statuses

| key | English | 中文 |
|---|---|---|
| `pending` | Pending | 待審批 |
