# Pass 160 任務書：優化 DownbeatRefineNode 與對齊黑板 Key 讀寫

**狀態**：待處理（尚未實作）
**交接原因**：使用者指示建立 Pass 160 任務書，針對 `DownbeatRefineNode` 與 Stage 3 拍號對齊黑板 Key 進行重構與補強。

---

## 0. 給接手 agent 的快速定位

- 專案根目錄：`D:\Users\666\Desktop\UVR5 音檔\自動節拍器`（工作用 worktree：`.claude\worktrees\barstart-v2-strengthen`，分支 `worktree-barstart-v2-strengthen`）
- 本專案慣例：
  1. 對應 `tests/test_sdd_pass160.py` 撰寫單元測試，包含完整的中文 docstring。
  2. 完成後執行針對性回歸與分批測試套件。
  3. 更新 `docs/BT-BUILD-PROGRESS.md` 變更日誌。
  4. Commit 訊息需包含：`Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`。

---

## 1. 背景與需求

`DownbeatRefineNode` 是 Stage 3 輸出黃金節拍網格 `refined_beats` 的關鍵節點，其結果被 Pass 156/157 建立的 `v1_reference_beat_grid` 直接引用。但在目前架構中存在以下黑板 Key 與相依性問題：
1. **Key 宣告與寫入不一致**：部分下游精修與評分節點（如 `CommercialBeatQualityNode`）僅宣告 `beats` 為輸入，導致 `refined_beats` 更新後下游讀取到舊資料或漏掉技術債。
2. **小節第一拍對齊與眾數重建**：在 BeatNet 模型輸出拍號混亂（例如全被判為 1 拍）時，`DownbeatRefineNode` 需穩定依據眾數重建 downbeat 序列，並確保支援 3/4 拍與 4/4 拍。

---

## 2. 重構與修復細節

### A. 規範黑板 Key 同步
在 `DownbeatRefineNode.execute()` 內：
- 同時設置 `blackboard.set_val("beats", refined_beats)` 與 `blackboard.set_val("refined_beats", refined_beats)`。
- 檢查 `build_beat_refinement_nodes()` 下游節點（如 `CommercialBeatQualityNode` 等 6 個精修節點），確保 `optional_keys` 或 `required_keys` 涵蓋 `refined_beats`。

### B. Downbeat 眾數重建與平滑 Guard
- 保留 `diffs` 拍間距 Outlier 檢測，防止突發爆音/極端點干擾。
- 強化 3/4 (華爾滋) 與 4/4 (標準) 的眾數重建邏輯，確保 `time_signature` 寫入 Blackboard 供 Stage 4/5 重建 MIDI/和弦參考。

---

## 3. 驗證方式

1. 撰寫 `tests/test_sdd_pass160.py`，涵蓋：
   - 驗證 `DownbeatRefineNode` 能成功修復 >30% 異常 downbeat 並重新建立對齊網格。
   - 驗證 3/4 拍音訊能正確檢測出 `time_signature == "3/4"`。
   - 驗證 `beats` 與 `refined_beats` 在 Blackboard 中一致同步。
2. 執行針對性測試：
   ```bash
   python -m pytest tests/test_sdd_pass160.py tests/test_sdd_pass18.py -v
   ```
3. 更新 `docs/BT-BUILD-PROGRESS.md` 並完成 commit & PR 流程。
