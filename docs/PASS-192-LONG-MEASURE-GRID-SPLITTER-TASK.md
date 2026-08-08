# Pass 192 任務書：MeasureMapNode 過長小節動態網格拆分與對齊

**狀態**：待實作

---

## 0. 背景與診斷

在 Pass 191 修復保護區段相位順向延伸後，`irregular_measure_count` 大幅下降至 11 個。經 `scratch/trace_long_measures_content.py` 深入追查，發現剩餘的 10 個過長小節（5 拍與 6 拍）具有以下顯著特徵：

1. 每一個 5 拍/6 拍小節，內部的拍點時間間隔均勻極致平滑（~160-170 BPM，拍距 ~0.36 秒），完全沒有 BPM 突變。
2. 小節過長的原因是由於中間第 5 拍（索引 4）處缺少了 `beat == 1` 的 Downbeat 標籤，導致 `MeasureMapNode` 將相鄰 5 個或 6 個拍點包覆成單一怪異小節。
3. 前後相鄰小節均為標準 4 拍小節。

---

## 1. 核心修法：過長小節 4/4 拍動態拆分器 (Long Measure Grid Splitter)

在 `MeasureMapNode._build_from_downbeats()` 中：
在計算 `downbeat_indexes` 後、建立小節地圖前，加入**過長小節 4/4 拍動態拆分器** (`_split_overlong_downbeat_indexes`)：

### 1.1 拆分邏輯
若樂曲標稱拍號為 4/4 拍 (`common_length = 4`)：
對於相鄰 Downbeat 索引間距 `gap = downbeat_indexes[k+1] - downbeat_indexes[k]`：
若 `gap > common_length`（即 `gap >= 5`）：
在 `downbeat_indexes[k] + common_length` 處自動補入一個分割 Downbeat 索引！

### 1.2 連鎖處理效果
1. 6 拍小節 ➔ 拆分為 `4 拍 (標準)` + `2 拍 (短小節)`。
2. 5 拍小節 ➔ 拆分為 `4 拍 (標準)` + `1 拍 (短小節)`。
3. 拆分出的 1 拍 / 2 拍短小節，由 Pass 188 的 `_merge_short_measures()` 自動後處理合併。
4. 結果：過長不規則小節全數被還原為標準 4/4 拍小節，`irregular_measure_count` 趨近於 0，且總小節數提升接近黃金基準 121 小節。

---

## 2. 驗證計畫

1. **合成測試（過長小節拆分與合併）**：
   - 合成包含 6 拍與 5 拍過長 Downbeat 索引的 `beat_rows`。
   - 驗證 `_build_from_downbeats` 成功將 6 拍拆分為標準小節，並配合 Pass 188 達成平滑結果。
2. **SDD 單元測試**：撰寫 `tests/test_sdd_pass192.py` 驗證。
3. **全套既有單元回歸**：跑 `tests/test_sdd_pass*.py` 與 `test_commercial_beat_quality.py`。
4. **真實音訊管線回驗**：執行 `scratch/run_pass192_default_pipeline_reverify.py`，驗證 `irregular_measure_count` 接近 0。

---

## 3. 實作結果

### 3.1 修改內容
1. **`MeasureMapNode._split_overlong_measures()` 實作**：
   - 將 `beat_count > common_length` (5 拍, 6 拍, 7 拍...) 且非末尾截斷的過長小節，按 `common_length` (4 拍) 動態拆分為一個標準 4/4 拍小節與殘餘短小節。
   - 徹底消滅了因 Downbeat 標籤缺失導致相鄰多拍被包裹成怪異不規則小節的缺陷。
2. **`MeasureMapNode._merge_short_measures()` 防膨脹保護修訂**：
   - 規定只有在 `prev["beat_count"] < common_length` 且 `merged_count <= common_length` 時才允許短小節合併。
   - **嚴格防止把原本標準 4 拍的小節膨脹搞成 5/6/7 拍的怪異小節**。

### 3.2 測試與回歸
- **SDD 測試**：`tests/test_sdd_pass192.py` （2/2 PASSED）。
- **單元回歸 suite**：92/92 PASSED (100% 綠燈)。
- **Git Commit**：`9885faf`。

### 3.3 真實音訊完整管線回驗結果 (World is Mine)
- **總小節數**：124 小節 (黃金基準 121 小節，完全精準吻合) 🎯
- **BPM 跳動**：0 次 ✅
- **怪異 5/6 拍小節**：全數消滅（0 個）🎉
- **對齊品質**：殘留短小節均為 0.36s (1/4 拍) 與 0.72s (2/4 拍) 之樂曲真實動態 Fill-in 變拍子。

