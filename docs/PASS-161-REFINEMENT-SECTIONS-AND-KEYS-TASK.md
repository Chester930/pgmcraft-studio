# Pass 161 任務書：修復 Stage 3 精修守衛鏈 Sections 安全退回與 Key 同步技術債

**狀態**：待處理（尚未實作）
**目標**：修復 Stage 3 精修守衛鏈在段落資訊未產生時的品質對齊退回機制，並全面清理精修節點的 `refined_beats` Key 同步技術債。

---

## 0. 定位與背景

在 Stage 3 節拍追蹤精修鏈（`build_beat_refinement_nodes()`）中：
1. **Sections 恆為空問題**：樂段結構（`sections`）屬於 Stage 4 的產出。Stage 3 中的 `DownbeatPhaseConsistencyNode` 與 `CommercialBeatQualityNode` 在評估 `_score_beat_grid_quality()` 時，因 `sections` 恆為空而無法發揮段落對齊計算。
2. **Key 宣告與同步技術債**：部分精修節點僅宣告/修改 `beats`，未同步更新 `refined_beats`，導致後續讀取 `refined_beats` 的節點拿到舊數據。

---

## 1. 具體修復內容

### A. 樂段對齊 Safe Fallback (`_score_beat_grid_quality`)
* 檔案：`pgm_craft/workflow/beat_tracking_bt.py`
* 函式：`_score_beat_grid_quality()` 與 `DownbeatPhaseConsistencyNode`
* 當 Blackboard 讀取的 `sections` 為空時，自動採用安全的全曲單段落 `[{"name": "Main", "start_time": 0.0}]`，確保段落相位相干性計算不空轉。

### B. 清理 6 個精修節點 Key 宣告與雙向同步
* 檔案：`pgm_craft/workflow/beat_tracking_bt.py` / `audio_nodes.py`
* 針對 `OnsetPhaseRealignmentNode`、`MicroTimingTransientSnapNode`、`ViterbiTempoSmoothingNode`、`BeatGridContinuityRepairNode`、`TempoOscillationDampingNode`、`KickAnchorConsensusSnapNode`：
  - 補齊 `optional_keys` / `required_keys` 涵蓋 `refined_beats`。
  - 在改寫 `beats` 時，同時執行 `blackboard.set_val("refined_beats", beats)` 與 `blackboard.set_val("beats", beats)`。

---

## 2. 驗證方式

1. 撰寫 `tests/test_sdd_pass161.py`：
   - 驗證在沒有 `sections` 輸入下，`_score_beat_grid_quality()` 仍能正常計算品質分數且不拋出例外。
   - 驗證精修節點執行後，`beats` 與 `refined_beats` 保持一致更新。
2. 執行針對性單元測試與回歸套件。
3. 更新 `BT-BUILD-PROGRESS.md` 變更日誌。
