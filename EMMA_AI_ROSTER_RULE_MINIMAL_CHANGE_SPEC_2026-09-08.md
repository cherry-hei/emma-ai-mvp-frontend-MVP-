# Emma AI與Roster Rule UX最小改動規格

**Date:** 2026-09-08  
**Scope constraint:** 除Emma AI入口辨識、Roster deterministic rule-check及其必要context handoff外，其餘頁面與功能不變。NAAC工作只做吻合度核對，不把未完成backend包裝成已完成。

## 1. Emma AI入口

現行`/insights`及雙模式workspace仍完整存在。手機toolbar只顯示「✦」而把`Emma AI`文字隱藏至`lg` breakpoint，容易被理解為頁面消失。修正為所有viewport均顯示清晰的**Emma AI**文字標籤，click仍進入`/insights`；不重建、不複製頁面，也不把Q&A重新放入Compliance。

`/insights`保留兩個模式：**Compliance Q&A**及**Emergency SL Replacement Suggestion**。若由Roster的rule review進入，query string只帶入非敏感的`mode=compliance`、`date`、`rule`及`roster_version_id` context；workspace預設選中Compliance模式，並讓問題欄以該deterministic issue作起點。AI不會改寫severity、pass／fail或publish gate。

## 2. Roster deterministic rule-check

現有inline chips改成一條不超過約48px的compact status strip，使用業務語言而不是generic system error：

| 狀態 | 顯示 | 行為 |
|---|---|---|
| Ready to publish | 綠色，0 blocking | 可繼續publish；保留最新validation時間／method |
| Needs attention | 玫瑰色＋琥珀色count | Blocking必須處理；Warnings可review；提供Review rules |
| Checking | 中性loading | 暫停publish，避免使用舊結果 |

Strip只顯示**Blocking、Warnings、Advisory**數量及`Review rules`按鈕，不直接展開多條長訊息。Grid高度因此不再被問題chips壓縮。

`Review rules`打開右側／手機bottom drawer，按severity分組：

- **Blocking:** `validation.violations`中hard／未resolved項目；必須在publish前解決。
- **Warnings:** 未通過的`ratio_checks`及soft violations；展示actual／required、rank與時間窗。
- **Advisory:** 已通過或只供參考的validation metadata，不預設展開。

每項只使用backend真實fields：rule code、message、staff ID／date／unit（如有）、rank、window、actual及required。沒有context時顯示「location unavailable」，不虛構staff或日期。可行時提供`Filter roster`／`Open cell`；所有項目均可提供`Explain in Emma AI`，只帶入非敏感rule context。

Publish按鈕在`hard_violation_count > 0`時disabled，並提供可讀原因；在沒有hard violations但有warnings時可publish，但publish動作需再次顯示最新validation摘要供manager確認。這與deterministic authority及manager final approval一致。

## 3. NAAC XLSX核對

現有backend每次生成一個generic single-sheet XLSX；官方NAAC workbook是多worksheet、固定六週版面與衍生報告。現階段不能聲稱100%吻合。核對報告需逐項比較：worksheet名稱／順序、used range、合併格、欄寬列高、cell values／formulas、number formats、styles、凍結窗格、print area／orientation／paper size／fit-to-page、headers／footers、圖片／drawing及defined names。

Frontend繼續誠實顯示各現有generic report download；完整六週workbook保持disabled，直到backend交付及golden-file comparison通過。核對本身不改Reports頁其他UI。

## References

[1]: https://docs.oracle.com/en/cloud/saas/readiness/hcm/24b/wosc-24b/24B-workforce-scheduling-wn-f32299.htm "Oracle — Validate Workforce Schedule Introduction"
[2]: https://www.rosterelf.com/support/knowledge-base/scheduling-and-rostering/roster-warnings "RosterElf — Understand roster warnings"
[3]: https://www.sprinklr.com/help/articles/schedule-scenarios/alerts-in-schedule-scenarios/686539f620753412ba1b101b "Sprinklr — Alerts in Schedule Scenarios"
[4]: https://tcpsoftware.com/products/humanity/compliance/ "Humanity Schedule — Compliance and conflict management"
