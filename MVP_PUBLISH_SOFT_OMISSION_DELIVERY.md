# MVP — Demo介面對齊與發佈閘門 Review

更新：2026-10-11深夜。工作分支 `agent/mvp-publish-soft-omit-oct11`，[Draft PR #6](https://github.com/cherry-hei/emma-ai-mvp-frontend-MVP-/pull/6)。程式更新至`66d9e7c`。**沒有合併main、部署MVP或執行DB migration。** Haven的合併／部署授權不適用於MVP。

## 已完成的介面與資料路徑

| 項目 | 本輪結果 |
|---|---|
| 品牌、字體與布局 | 保留原Emma logo、Inter字體，採Demo粉紅／slate卡片、圓角、單語導航與手機布局；未套用Haven機構字典。 |
| 院舍設定 | 側欄下方。更期字典及任務排程為設定分項，沿用org-scoped API及各自RBAC；無持久化契約的院舍資訊不提供假Save。 |
| 新增更次 | Demo式職級／員工／日期／更碼下拉與任務時間列。保存真更格及task assignment；失敗報確切partial-save進度。 |
| 批量排更 | 完整period日期範圍、星期選擇、Mon–Fri捷徑、多選員工／職级／更碼及預覽。既有更格及任務保留。真API逐格保存，尚非原子交易。 |
| 特別事項 | 真facility-event日期、鐘面、備註及職級需求；event指定員工尚缺reviewed backend持久化契約，沒有假Save。 |
| 任務時間 | 拒絕無效日期／HH:mm；跨午夜落翌日；needs_location task需目的地；讀取失敗阻止覆寫。 |
| 規則／草稿／發佈 | 固定Publish、server deterministic review、hard不可Omit、soft逐條確認；修改／切版本清除舊選項。 |
| History／Audit | 同facility及所選period/version真API；Audit保留原權限。報告及Audit下載由server生成，不冒充支持所選version的舊aggregate報告。 |
| 警報／Emma AI | 警報保留原功能；Emma AI是其下方獨立導航，已移除錯誤的警報頁CTA。沒有新增供應商、voice或自動批准。 |
| 工時顯示 | 已保存`paid_minutes`以小時及分鐘顯示，例如435→7 h 15 m；unknown仍為—。內部整分鐘與API欄名不改，未宣稱所有報告格式已改。 |
| 訊息中心 | 沿用同facility provisioned profiles／真正staff姓名與`/messages`；管理端和Staff PWA共用契約，移除假員工／自動回覆。新增router、service與未執行SQL草稿；recipient-only read receipt可重試而不覆寫第一次read-at。 |
| 兩機構 | 同碼可以有不同paid minutes，字典／角色／單位仍由登入機構來源提供；未把Haven更碼、56人或分鐘政策寫入Care Home A/B。 |

## Backend安全與整分鐘

更表及報告共用後端既有`shift_minutes`，不從鐘面猜paid minutes。更格保存要求同facility的draft及period內日期。Task create/update/delete/sync／escort-location沿assignment→shift→真version拒絕published、foreign／missing關係，不能直接task API繞過發佈後鎖。

Grid／report／history有scope及舊請求保護。管理端與Staff App訊息頁的身份切換／送出結果均有guard；草稿依收件人分隔，避免換人後送錯內容。Staff App補了credential generation、token／refresh snapshot與原請求身份保護，舊refresh不還原舊登入或把舊body以新身份replay；這不是宣稱全部cross-tab auth已驗收。

訊息與notification／replacement offer是不同資料。員工願意接更或chat文字不自行批准／發布；替更完整manager approval、rules、roster/task/Audit流程仍須獨立端到端驗收。

## 發佈原子RPC與訊息SQL：均未執行

`20261011000024_publish_soft_omissions.sql`取代舊三參數旁路，核對OWNER、tenant、run/digest、solver hard、每條soft row ID及timestamp；鎖version／validation，狀態、event與Audit需同一交易。沒有RPC即fail closed。尚未執行migration或在DB驗收。

`supabase/migrations/drafts/20261001000025_direct_messages.sql.draft`是從先前review稿選擇性帶入的訊息schema／RLS／trigger／grant，未合併其他PR3內容、未執行。23個SQL statements解析通過不等於RLS／trigger可運作。

DB reviewer須於獲授權隔離合成DB核對schema/enum、RLS/grants、跨org拒絕、雙發佈／concurrent edit、stale policy/census、Audit失敗rollback、published不可改、訊息participant權限與已讀重試。沒有在本輪執行真DB測試。

## 驗證紀錄：集合不同，勿把數字相加

| 驗證 | 結果／界線 |
|---|---|
| 先前完整受控集合快照 | 223 passed、6 skipped；是上一轮selected set，不是全部backend或真DB UAT。 |
| 本輪最新擴展集合 | 194 passed、6 skipped；發佈、Audit、匯入、UI契約、task draft guard、handover與messages。 |
| 本輪focused子集 | 77 passed，與194集合重疊。 |
| 六skip | 舊外部workbook fixtures缺失；不是六個已確認bug、也不表示對NAAC M1的新增收費scope。 |
| 工時小時分鐘helper | 2項通過，unknown不代零。 |
| TypeScript／Next及PWA build | 最終source通過；MVP保持Draft。 |
| 共用mock聊天 | 管理端送→Staff App讀／已讀→回复→管理端讀／已讀通過；不是真DB互通。 |
| 全月批量mock | 十月31日／22平日；一格既有D／task保留、21格空白寫入，含30日；不是atomic。 |
| Staff PWA refresh競態 | 8／8 fake-fetch／storage離線測試通過。 |
| 真org／RLS integration | 沒有可用獲授權隔離DB；之前dummy端點的10項未通過不能算UAT成功。 |

## 仍未達到完整Demo feature parity

Meal／free-text task detail／shift note尚未有已review持久化合約；界面保持不可保存。Event指定員工、leave autofill與revocation是M2相關驗收；NAAC 18-sheet六週Excel是M3相關驗收，manifest不等於exporter。Batch及更次＋多task仍是多步，非原子交易。Cherry現在Codex寫的backend若未push，無法由GitHub核對是否已補齊；需要最新PR／branch，不猜較早Codex分支。

六skip分別為`test_real_workbooks_parse_without_unresolved_cells`的4個case、`test_real_home_a_before_and_after_differ`、`test_real_workbook_opens_read_only_without_mutating_it`。合成replacement tests可先補，但不能冒稱real-source parity，不能刪原六項作假通過。

**UI及可用API已對齊，不代表M1／M2／M3已被接受。** 基本M1合成試用不必以全部M3完成為前提；實際帳戶／兩機構DB隔離及包含的訊息／替更功能仍須驗收。真員工資料／正式服務仍受M4/M5香港環境及證據閘門限制。

## 文件及工程分工

已讀Cherry指定的兩份Google文件，最新fixed-price WBS用於M1–M5範圍，文件不是已確認機構代號／帳戶清單。原兩份資料不構成新增付款或scope批准。本輪不改合同。

Codex應先review最新PR6及Cherry自己的backend Draft，補synthetic fixtures、持久化／atomic契約與離線測試；不要同時改同檔或直接merge/deploy。真正隔離DB執行、RLS、restore／cutover及production IAM需要既有授權、受控環境與可追溯review，不把AI產出的SQL稿當成已運作證據。
