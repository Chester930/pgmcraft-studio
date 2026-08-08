# Pass 191 任務書：_relabel_beat_numbers 保護區段相位連貫性修復

**狀態**：待實作

---

## 0. 背景與根本原因剖析

在 Pass 188~190 的系列修復後，`SteadyPercussionCountAnchorNode` 與 `KickBassDownbeatVerifierNode` 均已能產出連貫相位與正確保護區段。然而真實音訊回驗顯示 `irregular_measure_count` 依然存在 15 個不規則小節（全數為 5, 6, 7 拍過長小節）。

經過深入診斷 `scratch/diagnose_measure_map_labels.py`，發現關鍵根因為 `BeatGridContinuityRepairNode` 在補拍後呼叫的 **`_relabel_beat_numbers()`** 函數存在重大設計缺陷：

### 原有 Bug 寫法 (`beat_tracking_bt.py` Line 176)
```python
relabeled[:, 1] = ((np.arange(len(relabeled)) + first_label - 1) % beats_per_bar) + 1
if protected_ranges:
    for i in range(len(arr)):
        if _time_in_protected_ranges(float(arr[i, 0]), protected_ranges):
            relabeled[i, 1] = arr[i, 1]
```

### 問題危害
`_relabel_beat_numbers` 不管是否有保護區段，直接以 `np.arange(len)` 從全曲 index 0 天真地印上 `1-2-3-4` 循環，事後才強行把保護區段的標號「蓋回」。
當硬套的 `1-2-3-4` 網格與保護區段內錨點的 `1-2-3-4` 網格相位不一致時，保護區段前後的交界處拍號必然產生斷層，導致下游 `MeasureMapNode` 切出 5 拍、6 拍與 7 拍的過長破碎小節！

---

## 1. 核心修法：保護區段相位連貫延伸 (Phase Continuity Relabeling)

重構 `_relabel_beat_numbers()`：
改為單次順向掃描時間軸，前進過程中維護 `last_label`：
1. 若目前拍點屬於受保護區段 (`protected_ranges`)，直接保留其精確標號，並更新 `last_label = arr[i, 1]`。
2. 若目前拍點屬於非保護區段，則順應 `last_label` 連貫延伸下一拍標號 `(last_label % 4) + 1`。

如此一來，非保護區段在離開保護區段時，會自動延續錨點的相位（例如從保護區段結尾的 Beat 4 順暢接續為 Beat 1, 2, 3, 4），實現全曲保護區與非保護區交界處 **0 相位跳躍 (Zero Phase Discontinuity)**！

---

## 2. 驗證計畫

1. **合成測試（保護區段交界無縫銜接）**：
   - 建立中間帶有 `protected_ranges`（標號為 1, 2, 3, 4）的 beats 陣列。
   - 執行修復後的 `_relabel_beat_numbers`，驗證保護區段前的非保護拍與保護區段後的非保護拍均連貫延伸相位，無 5/6/7 拍錯位。
2. **SDD 單元測試**：撰寫 `tests/test_sdd_pass191.py` 驗證修復。
3. **全套既有單元回歸**：跑 `tests/test_sdd_pass*.py` 與 `test_commercial_beat_quality.py`。
4. **真實音訊管線回驗**：執行 `scratch/run_pass191_default_pipeline_reverify.py`，預期 `irregular_measure_count` 的突破性大幅下降！

---

## 3. 實作結果

（待填寫）
