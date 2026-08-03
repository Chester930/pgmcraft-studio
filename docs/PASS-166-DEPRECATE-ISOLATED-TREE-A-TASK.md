# Pass 166 任務書：清理孤立死路徑 Tree A (build_module3_barstart_v2_pipeline_tree) 與簡化過時入口

**狀態**：待處理（尚未實作）
**目標**：清理孤立死路徑 `build_module3_barstart_v2_pipeline_tree`（Tree A），將其改為委派至具有完整 Stage 3 數據的主管線樹，並清理前端 `app.py` 中殘留的孤立調用。

---

## 0. 背景與問題

1. **孤立死路徑維護成本**：`build_module3_barstart_v2_pipeline_tree()`（Tree A）在舊版中定義為獨立樹，但因其繞過了 Stage 3 Beat Tracking，缺少 `beats` 與 `v1_reference_beat_grid` 資料，導致 Pass 156-163 的優化機制無法在該樹上運行。
2. **真實路徑一致性**：目前真正的實作與 GUI 功能皆使用 `_run_barstart_v2_comparison()` 與 Stage 3 整合的主樹（`Module3BarStartV2MergeNode` / `BarStartV2AutoMergeNode`）。

---

## 1. 具體清理與簡化細節

### A. 委派簡化 `build_module3_barstart_v2_pipeline_tree()`
在 `pgm_craft/workflow/module3_barstart_v2_bt.py` 與 `builder.py` 內：
- 將 `build_module3_barstart_v2_pipeline_tree()` 改為向下委派呼叫包含完整 Stage 3 與 MergeNode 的主樹 `build_module3_pipeline_tree()`。
- 保留 `target_stage="module3_barstart_v2"` 參數的相容性，確保向後相容不中斷既有 API 與測試。

### B. 清理 `app.py` 孤立死碼
- 清理 `app.py` 中殘留的未導出孤立函數 `process_module3_barstart_v2_test`。

---

## 2. 驗證方式

1. 撰寫 `tests/test_sdd_pass166.py`：
   - 驗證 `build_module3_barstart_v2_pipeline_tree()` 呼叫回傳合法 BT 樹。
   - 驗證 `builder.py` 傳入 `target_stage="module3_barstart_v2"` 能正確運作且相容。
2. 執行單元測試與全套測試回歸。
3. 更新 `BT-BUILD-PROGRESS.md` 並 commit/push/PR。
