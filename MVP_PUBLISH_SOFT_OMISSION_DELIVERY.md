# MVP — Demo介面對齊與發佈閘門 Review

更新：2026-10-11。工作分支 `agent/mvp-publish-soft-omit-oct11`，PR [#6](https://github.com/cherry-hei/emma-ai-mvp-frontend-MVP-/pull/6)。**保持Draft，沒有合併main、部署MVP或執行DB migration。** Haven的合併／部署授權不適用於MVP。

## 已完成的介面與資料路徑

| 項目 | 本輪結果 |
|---|---|
| 品牌、字體與布局 | 保留原Emma logo、Inter字體，採Demo的粉紅／slate卡片、圓角、單語導航與手機布局；未套用Haven的機構字典。 |
| 院舍設定 | 側欄最底、Emma AI下面。更期代號字典及任務排程成為設定分項，沿用原機構scoped API及各自RBAC；舊直接URL仍受保護。原設定頁的本地假Save已移除，院舍資料沒有寫入合約的部分保持唯讀。 |
| 新增更次 | Demo式職級／員工／日期／更碼下拉和任務時間列。保存真正更格與task assignment；半途失敗顯示確切進度及未確認任務，不能假稱全部已保存。 |
| 批量排更 | Demo式職級、多選員工／星期、更碼及預覽；沿用真正更格API逐格保存，失敗保留已成功格並報進度。尚不是原子批量交易。 |
| 特別事項 | Demo式活動、日期、鐘面、備註及職級需求；保存真facility-event記錄。指定員工尚缺後端持久化合約，沒有做假選項／假Save。 |
| 任務時間 | 無效日期／HH:mm拒絕；跨午夜end落翌日；needs_location task要填目的地；讀取失敗阻止覆寫；陪診要求透過既有TaskDef欄位傳至界面。 |
| 檢查、草稿與發布 | 保留固定Publish按鈕、server deterministic check、drawer批准、hard不可Omit、soft逐條確認。重新检查／修改／切版本清除舊soft選項。 |
| 儲存／發佈清單 | 改讀同院舍、所選period/version的真history API，不用本機假記錄。詳細Audit仍沿用原audit_log權限。 |
| 下載更表／Audit | 更表頁取消原直接匯出，跳報告頁並帶period/version。backend校驗所選版本確屬同period、同facility；報告及Audit CSV由真server生成。period-only報告不偽裝支援特定version。 |
| 警報／Emma AI | 警報頁加入Demo式Emma AI入口，使用原有incident／deterministic evidence介面；沒有新增供應商／voice或自動批准。 |
| 兩機構 | 後端字典按登入org读取；同一D碼在兩個離線fixture可有不同paid minutes。沒有把Haven更碼、56人、職位或規則寫入Care Home A/B。 |

## 已補的backend安全與精確計算

更表格、報告工時都共用後端現有 `shift_minutes`，不以界面鐘面猜paid minutes。所有更格保存要求同院舍的draft版本及該period內日期。Task create/update/delete/sync及escort-location也由assignment→shift→version取得真正draft狀態；published版本及foreign/missing關係拒絕，不能由獨立task API繞過發布後鎖。

報告、grid、history請求加入scope檢查，舊period或舊登入請求不能覆寫新登入界面。登入refresh以credential generation及token snapshot分組；tenant切換／logout後晚到refresh不能還原舊session，也不能把舊請求以新身份replay。

## 發佈原子RPC：保留未執行Review稿

`20261011000024_publish_soft_omissions.sql` 仍是**未執行migration**。它取代舊三參數旁路，核對OWNER、tenant、最新run/digest、solver hard、每條soft row ID及timestamp，鎖定當前version／validation；狀態、publish event及Audit需同一交易。新API只發server映射的fresh row IDs。沒有新RPC就停止發布，不能降級為無Audit的多次write。Excel匯入也不能代替OWNER批准。

實際DB owner須核對schema/enum、RLS、grant與依賴，於隔離合成DB執行並測試concurrent edit／double publisher、stale policy/census、cross-tenant拒絕、event或Audit失敗rollback及published不可改。這些尚未驗收，不可把SQL語法解析或mock當成RLS／交易已完成。

## 本輪驗證

| 驗證 | 結果／界線 |
|---|---|
| 受控backend安全集合 | **223 passed、6 skipped**。6項skip為既有外部workbook fixture缺失。包含發布、Audit、匯入、UI資料契約、task draft guard、handover及Phase4；不是所有backend測試或真DB UAT。 |
| 真API.ts refresh-race模擬 | concurrent dedupe、tenant switch、token rotation及logout全通過。 |
| frontend時間helper | 3項通過；包含跨午夜及無效時間。 |
| TypeScript／Next build | 最終source通過。 |
| 純mock瀏覽器 | 中文／英文 ×1440桌面／390手機：hard／soft發布門檻、新增task payload／跨午夜、批量預覽格數及event職級需求保存均通過，無page errors。 |
| SQL | 上輪pglast解析成功；未執行PL/pgSQL／schema／RLS／交易。 |
| 真org／RLS integration tests | 本輪沒有可用隔離DB；以test.invalid dummy設定試跑的10項因無服務失敗，未當作通過。重新選定純離線集合後取得223 passed。沒有實際客戶或正式資料庫操作。 |

## 尚未達到完全功能相同：不能隱瞞的接受缺口

MVP的meal／free-text task detail／shift note尚沒有已review的持久化合約；界面明示不可保存並停用。Event指定員工也是未完成M2合約。批量及更次＋多task仍為多步保存而非單一交易，已提供partial-save實況但不等於atomic parity。原期內aggregate報告、NAAC 18-sheet六週Excel和manager/staff leave autofill仍須各自原里程碑的實際backend／DB驗收，不能用同款按鈕代替功能完成。

上述缺口代表**UI與可用API已對齊，但不能稱全部Demo feature已完整移植或M1/M2/M3已接受**。要在保留Draft的下一次工程review補齊持久化schema、API、audit、rollback及兩org UAT後，才可接受完整功能對齊。

## 兩份指定文件的核對

已讀[2026-09-18 Addendum／WBS比較](https://docs.google.com/document/d/1VUSm-9im783yB4YsyYDZ7CpV70ZvzSa7/edit)及[2026-10-07 Fixed Price WBS M1–M5](https://docs.google.com/document/d/1iZ0D-tDGvv5WEUKXZGmqq5_Bu-JkVpQC/edit)。最新fixed-price用於範圍對照，舊比較稿不取代新授權。文件要求org-scoped retrieval、M2指定staff／leave autofill、M3 NAAC18sheet、M4/M5香港環境及隔離／還原證據；文件不是Care Home A/B已確認active codes、職位或帳戶清單，不能從WBS猜機構資料。本輪不改合同或付款定義。
