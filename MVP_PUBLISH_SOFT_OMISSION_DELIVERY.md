# MVP Publish / Soft Omission 交付紀錄

**分支：** `agent/mvp-publish-soft-omit-oct11`
**基準：** `origin/main` / `698b981`
**範圍：** 固定 Publish 控制、OWNER-only 發佈、伺服器 hard gate、逐項 soft exception checkbox、stale snapshot 拒絕。

## 已完成

- 排班工作區的工具列維持 sticky；Publish 只有一個固定入口。AI A/B/C 視窗只能「選擇並檢視規則」，不能旁路直接發佈。
- Publish 按鈕依介面語言顯示 **「發佈」** 或 **「Publish」**；前端以 canonical `OWNER` 與 legacy `superintendent` 對齊的 RBAC mirror 做 UX gate，後端仍為唯一權限裁決。
- `POST /rosters/{version_id}/publish` 改由 `require_decide(Feature.ROSTER_PUBLISH)` 保護，只有 OWNER（含 legacy superintendent 正規化）可通過 API gate。
- 每一次 `/validate-roster` 回傳的 soft finding 都有 server-derived `omission_id`。規則檢視 drawer 逐條 checkbox；沒有 omission ID 的 soft row 會 fail closed，不能發佈。
- 每次重新 validation 或切換 grid 都會清空既有勾選。Publish request 同時送出已勾選 ID 與使用者實際覆核的 `validation_input_digest`；伺服器立即重算並比較 digest，stale snapshot 以 `409 stale_validation` 拒絕。
- 伺服器 publish gate 拒絕：hard/未知 severity、已 resolved 或缺 resolved state、缺 validation run/digest、hard/soft summary 與 finding rows 不一致、未知/重複/未勾齊 soft ID。
- `soft_violation_count` 加入 validation API contract；它和 `hard_violation_count` 都必須與 fresh finding rows 一致。
- solver 的 `constraint_score` 公式包含 agency、OT、fairness 等 **soft trade-off**；route 的應用層 gate 改為僅拒絕 `hard_violation_count != 0`。低品質分數在 AI 選項中是 warning，仍要走 fresh validation + 逐項 soft acknowledgement。
- 保留 existing service-role atomic publish RPC 呼叫；沒有新 migration、沒有 production 操作、沒有外部資料庫/API 呼叫。

## 已驗證（全部使用離線 fixture）

測試命令一律以以下 synthetic config 執行：

```bash
APP_ENV=test \
SUPABASE_URL=https://test.invalid \
SUPABASE_ANON_KEY=test-anon-key \
SUPABASE_SERVICE_ROLE_KEY=test-service-role-key \
DATABASE_URL=postgresql://test:test@127.0.0.1:1/test
```

- focused publish gate：`tests/test_publish_soft_omission.py`
- publish/RBAC/service escalation：`tests/test_phase5_api_security.py`
- Phase 5 security regression：`tests/test_phase5_security.py`
- focused 結果：`18 passed`；加上專門 Phase 5 security regression：`31 passed`。
- 完整 Phase 5 離線集合：`pytest -q tests/test_phase5_*.py` → `127 passed`（3 個既有 deprecation warning，無失敗）。
- frontend：`npm ci --no-audit --no-fund` 成功；`npx tsc --noEmit` 成功；`node_modules/.bin/next build` 成功（20/20 static pages）。

沒有啟動 API server、沒有連到 Supabase、沒有連到 Postgres，也沒有使用真實 token、secret 或 seed data。

## DB / UAT 限制（必須在合併或部署前處理）

1. **不能在本工作範圍內修 DB migration。** 現有已部署的 `publish_roster_version` RPC 仍把 `roster_option_scores.constraint_score < 60` 視為拒絕條件；但該分數公式含 soft penalty。即使 API 層已正確把 soft 視為可逐項 acknowledge，低於 60 的 generated option 仍可能被資料庫 atomic RPC 拒絕。要令「所有 soft 勾選後可發佈」真正適用於低分 generated option，必須在經核准的後續 DB change 中把 RPC gate 改成真正 hard-only evidence（且同步 migration review / rollback / UAT）。**本工作依要求沒有新增或改寫 migration。**
2. 同一 RPC 的 `p_created_by` profile role allow-list 目前只列 legacy `superintendent/admin/scheduler`，未列 canonical `OWNER`。API RBAC 已正確授權 canonical OWNER，但在 canonical role 已落庫的環境，RPC 可能以 42501 拒絕。這也是既有 DB contract，需後續核准的 DB/RBAC compatibility 修正；不能以 client token、偽造 actor 或移除 audit actor 繞過。
3. 真實 UAT 必須在**隔離 test Supabase 專案**進行，至少涵蓋：legacy superintendent 與 canonical OWNER、hard fail、每一 soft checkbox、未勾 soft、digest stale（編輯或規則變更後）、同週期併發 publish、以及低 score / soft-only generated option 的 RPC 行為。不得以 production 或真憑證驗證。
4. 前端沒有 browser E2E runner/受控 mock route；本次以 TypeScript compile/build 與純離線 API/gate fixtures 驗證。若需視覺／點擊 UAT，應另建只回傳合成 validation JSON 的 local mock，而不是連 live backend。

## 不在本次範圍

- 沒有 migration、schema/RLS/RPC 修改。
- 沒有 production deploy、seed、外部資料庫/API、真憑證或真 token。
- 沒有合併其他 PR 或修改 parent 管理的 Haven。
