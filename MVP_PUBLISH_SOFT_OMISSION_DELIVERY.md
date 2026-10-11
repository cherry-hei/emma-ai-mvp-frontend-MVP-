# MVP發佈／Soft Omit — Review交付

- 工作樹：`/home/ubuntu/emma-mvp-publish-oct11`
- 分支：`agent/mvp-publish-soft-omit-oct11`
- 基線：`origin/main`，`698b981`
- 本輪為獨立review程式；沒有合併main、執行migration或部署MVP。

## 完成內容

1. 更表上方固定顯示中文「發佈」／英文「Publish」。按下打開規則檢視；最後在drawer按「院長批准並發佈」。
2. OWNER（兼容legacy superintendent）才可批准。API重新檢查RBAC，不接受browser提供的pass/fail。
3. Hard、unknown severity、無完整validation evidence及summary與finding不一致均拒絕發佈；hard沒有Omit。
4. 每條soft finding有server生成的識別碼，須逐條勾Omit。未勾齊、重複或不屬當前snapshot的ID均拒絕。重新檢查、修改或切version清空舊選項。
5. Server發佈時重新deterministic validation，核對使用者已檢視的digest。A/B/C只能選方案再走同一批准路徑，不能直接旁路發佈。
6. 低solver score可能来自soft penalties，不單靠低分阻擋；非零solver hard違規仍阻擋。
7. 新review-only migration：`20261011000024_publish_soft_omissions.sql`。移除舊三參數RPC旁路，改為六參數exact run/digest/OWNER/soft row IDs。鎖period、version及當前validation rows，核對timestamp、actor、tenant、hard/soft數及每條soft。狀態、發佈event與Audit在同一RPC交易寫入。
8. API把server soft fingerprint映射成fresh DB row ID；前端不提交DB row IDs。validation持久化同一fingerprint。
9. 取消無RPC的多次寫入fallback：若未裝新RPC，停止發佈而非留下無Audit的status。
10. 匯入Excel不會代替OWNER批准：即使要求published，亦保留draft並提示到更表workspace審核。避免historical import旁路soft或hard gate。

## 已完成驗證

- **215 passed、6 skipped**：完整Phase5、soft gate、atomic contract、Audit及import離線回歸。6個skip是既有外部workbook fixture缺失，未當作通過。
- TypeScript `npx tsc --noEmit`通過；Next production build通過。
- PostgreSQL `pglast`解析新SQL成功（10 statements）。這只是語法解析，**不是實際執行PL/pgSQL、schema/RLS或transaction驗收**。
- 純mock瀏覽器四組：中文／英文 ×1440桌面／390手機；固定Publish、未勾soft不能批准、全部soft勾後發送正確digest和IDs、全部soft勾後hard仍不能批准。無page errors，已查看手機及桌面截圖。
- 沒有啟動API/DB服務，沒有外部Supabase/Postgres連線或正式secret。mock token無效且僅存在隔離瀏覽器。

## 合併／部署前必要DB Review與UAT

新backend与migration必須當作一個版本協調部署；只部署frontend或backend而未套新RPC，可能因RPC signature不匹配而停止發佈。這是fail-closed，不可為趕上線保留舊旁路。

Kien／DB owner需在隔離合成DB審核及執行：
- canonical OWNER與legacy superintendent成功；scheduler/admin/frontline與null actor拒絕。
- hard / unknown / soft未勾 / 偽造、重複、跨tenant、歷史run IDs拒絕。
- 全soft確認且低score/no hard可以發佈；solver hard非零拒絕。
- concurrent cell edit、validation重跑、同period雙publisher、規則及每日院友數變更後stale檢查。
- event或Audit插入故障使整個發佈交易rollback；原版本仍operative。
- 验证existing published roster immutable、原有RLS與通知只在RPC成功後執行。
- 驗證新migration的依賴、實際欄位、索引及enum相容性，舊function DROP RESTRICT如有dependency應停下而非CASCADE。

## Rollback規劃

套用前備份schema/function definitions及versioned data、記錄migration checksum。若新RPC/後端不匹配，先停發佈入口、回退應用至匹配review版，保留已產生的event/Audit資料；不可盲目把舊三參數旁路恢復為可呼叫。DB owner須先演練reversible DDL及資料還原，不在本輪執行。

## 範圍界線

- 沒有改Haven的職系、工時或Blob。
- 沒有正式帳戶、production IAM/RLS、HK cutover、DNS、通知发送或新AI provider。
- 此修正不代表M1已被接受，也不取代NAAC/SA各自synthetic UAT。
