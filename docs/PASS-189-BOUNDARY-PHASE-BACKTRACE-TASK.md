# Pass 189 任務書：Anchor 邊界雙向相位重補與過長小節修復

**狀態**：待實作

---

## 0. 背景與診斷

在 Pass 188 中，`MeasureMapNode` 實作了短小節前向合併，成功將 3 拍小節併入前小節。然而真實音訊回驗顯示 `irregular_measure_count` 依然為 14，且剩餘的不規則小節全數為 **5拍 (5個), 6拍 (4個), 7拍 (2個)** 之過長小節。

經過深入追查，確定問題根本原因為 `SteadyPercussionCountAnchorNode._apply_anchor()` 的單向標號邏輯：
- 舊邏輯從錨點 `base_idx` 開始**往後**重新標號 1-2-3-4 循環。
- 但 `base_idx` **往前**的拍點標號維持原舊相位。
- 當舊相位與新錨點相位存在偏移（相位模 4 不相等）時，兩者交界處的小節即會產生多餘拍數（5, 6, 7 拍）。

---

## 1. 核心修法：錨點雙向相位倒推對齊 (Backward Phase Alignment)

在 `SteadyPercussionCountAnchorNode._apply_anchor()` 內：
除了從 `base_idx` 往後重標號之外，增加**往前倒推重標號**機制：

### 1.1 倒推標號範圍
- 起始點：`base_idx - 1`
- 終點：前一個受保護區段的結束邊界或 `idx = 0`（即遇保護區段停止，不覆蓋已保護相位）。

### 1.2 倒推標號公式
對於 `idx < base_idx` 的拍點：
```python
step_back = base_idx - idx
beats[idx, 1] = ((0 - step_back) % 4) + 1
```
例如：
- `base_idx` 為 Beat 1
- `base_idx - 1` 為 Beat 4
- `base_idx - 2` 為 Beat 3
- `base_idx - 3` 為 Beat 2
- `base_idx - 4` 為 Beat 1 ...依此類推。

---

## 2. 實作細節

修改 `pgm_craft/workflow/beat_tracking_bt.py` 中的 `SteadyPercussionCountAnchorNode._apply_anchor()`：
1. 傳入 `protected_ranges` 或已保護拍點索引遮罩。
2. 先往後重標號（維持現有邏輯）。
3. 增加往前迴圈倒推重標號，遇到受保護時間區間（`protected_ranges`）時提前終止往前重標。
4. 更新傳出的 `protected_start`，使保護範圍正確延伸至有效改動區間。

---

## 3. 驗證計畫

1. **合成測試（雙向相位對齊）**：
   - 合成前半段相位錯位、後半段輸入穩定擊點錨點的 beats 陣列。
   - 驗證 `_apply_anchor` 後，`base_idx` 之前的非保護拍點標號也被連貫倒推修正為 1-2-3-4 循環。
   - 驗證交界處不產生 5/6/7 拍之過長小節。
2. **合成測試（保護區段防護）**：
   - 驗證倒推標號遇到 `protected_ranges` 時正確停止，不覆蓋既有保護相位。
3. **SDD 單元測試**：撰寫 `tests/test_sdd_pass189.py` 驗證上述邏輯。
4. **全套既有單元回歸**：跑 `tests/test_sdd_pass*.py` 與 `test_commercial_beat_quality.py`。
5. **真實音訊管線回驗**：執行 `scratch/run_pass189_default_pipeline_reverify.py`，預期 `irregular_measure_count` 大幅下降（接近 0~2）。

---

## 4. 實作結果

（待填寫）
