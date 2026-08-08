# Pass 190 任務書：KickBassDownbeatVerifierNode 180度反相網格連貫性修復

**狀態**：待實作

---

## 0. 背景與診斷

在 Pass 189 實作倒推對齊後，單元測試成功，但真實音訊完整管線回驗顯示 `irregular_measure_count` 依然為 15 個。

經深度追查 `beat_tracking_bt.py` 發現在下游執行的 **`KickBassDownbeatVerifierNode`** (Pass 168 / madmom Downbeat Guard) 在觸發強拍 180 度反相修復 (`ROTATED`) 時，存在重大 Bug：
```python
# 舊有 Bug 程式碼：
fixed_beats[:, 1] = 0  # 👈 直接將整軌標號清空為 0
for idx in beat3_indices:
    if idx not in protected_labels:
        fixed_beats[idx, 1] = 1  # 👈 只寫入 beat = 1，其餘 2, 3, 4 拍標籤全部遺失為 0！
```

### 問題危害
1. 非保護區段中的 2, 3, 4 拍標籤全部被清空為 0，破壞了上游 `SteadyPercussionCountAnchorNode` 所產生的連貫 4/4 拍網格。
2. `MeasureMapNode` 在依據 `beat == 1` 切割小節時，保護區段與非保護區段交界處因為中間標號缺失，切出了 5 拍、6 拍與 7 拍的過長破碎小節！

---

## 1. 核心修法：180度旋轉時完整保留拍號網格連貫性

修改 `KickBassDownbeatVerifierNode.execute()` 在旋轉反相時的標號邏輯：
對於非保護區段 (`idx not in protected_labels`) 的拍點：
不用 `fixed_beats[:, 1] = 0`，而是將舊標號進行 180 度 (+2 拍) 旋轉位移：
```python
old_label = int(beats[i, 1])
# 若舊標號有效 (1..4)，將其平移 2 拍：3 變 1, 4 變 2, 1 變 3, 2 變 4
if old_label in (1, 2, 3, 4):
    fixed_beats[i, 1] = ((old_label - 1 + 2) % 4) + 1
else:
    # 若原本無標號，預設給予 offset
    fixed_beats[i, 1] = 1
```

對於保護區段 (`i in protected_labels`) 的拍點：
完整保留其 `protected_labels[i]`，絕對不改動。

---

## 2. 驗證計畫

1. **合成測試（旋轉反相時保留 1-2-3-4 拍號連貫性）**：
   - 合成 Beat 3 比 Beat 1 大聲的音訊與包含 `protected_ranges` 的 beats 陣列。
   - 驗證 `KickBassDownbeatVerifierNode` 觸發 `ROTATED` 時，非保護區段原 Beat 3 變 Beat 1，而原本的 Beat 4 變 Beat 2, Beat 1 變 Beat 3, Beat 2 變 Beat 4。
   - 驗證標號無任何 0 遺失。
2. **SDD 單元測試**：撰寫 `tests/test_sdd_pass190.py` 驗證修復。
3. **全套既有單元回歸**：跑 `tests/test_sdd_pass*.py` 與 `test_commercial_beat_quality.py`。
4. **真實音訊管線回驗**：執行 `scratch/run_pass190_default_pipeline_reverify.py`，驗證 `irregular_measure_count` 的顯著下降。

---

## 3. 實作結果

（待填寫）
