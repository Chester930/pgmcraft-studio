# Pass 163 任務書：升級 BeatFusionArbitratorNode 仲裁時間軸記錄與 v1 網格慣性約束

**狀態**：待處理（尚未實作）
**目標**：升級 Stage 3 雙軌融合仲裁節點 `BeatFusionArbitratorNode`，在鼓軌低能量（無鼓/Breakdown 段落）切換 B 軌時提供時間軸詳細記錄，並整合 Pass 156/157 `v1_reference_beat_grid` 作為速度慣性約束。

---

## 0. 背景與問題

1. **仲裁明細遺失**：目前 `beat_fusion_report` 僅記錄全曲採納 A 軌與 B 軌的總拍數，未記載具體切換的時間區段（Spans），無法提供排錯診斷與 UI 視覺化。
2. **無鼓段落速度漂移風險**：當 A 軌（Drums+Bass）能量過低且 B 軌拍點偏離過大時，現有邏輯僅依據前 2 拍的步距做固定等速內插；遇到非等速漸慢/漸快段落易累積誤差。

---

## 1. 具體升級細節

### A. 新增仲裁時間軸記錄 (`track_b_spans`)
在 `BeatFusionArbitratorNode.execute()` 內：
- 追蹤並收集從 A 軌切換至 B 軌（或慣性內插）的連續時間區段。
- 在 `beat_fusion_report` 內寫入 `track_b_spans` 陣列（包含 `start_time`, `end_time`, `beat_count`, `reason`）。

### B. 慣性內插參考 `v1_reference_beat_grid`
- 當進行速度慣性內插且 Blackboard 存在 `v1_reference_beat_grid` 時，優先提取該時間區段內 v1 網格的真實步距作為內插依據，而非硬性假設前 2 拍等速。

---

## 2. 驗證方式

1. 撰寫 `tests/test_sdd_pass163.py`：
   - 驗證 `BeatFusionArbitratorNode` 產出的 `beat_fusion_report` 包含 `track_b_spans` 且記錄正確的時間區段。
   - 驗證在存在 `v1_reference_beat_grid` 時，慣性內插會優先參考 v1 步距。
2. 執行單元測試與回歸測試。
3. 更新 `BT-BUILD-PROGRESS.md` 並 commit/push。
