# Pass 188 任務書：MeasureMapNode 短小節前向合併

**狀態**：已實作，SDD 測試與回歸通過，待真實音訊完整管線驗證。

### 重要補充（實作過程發現）

實際 `measure_map.json` 的 14 個不規則小節中：
- **< 4 拍**（太短）：measure 8 (3拍) — 1 個
- **> 4 拍**（太長）：5拍 ×5、6拍 ×1、7拍 ×1 — 共 13 個

Pass 188 只能修「太短」的 3 拍案例（`beat_count < common_length`），**5/6/7 拍的太長案例不在這次修法範圍內**。太長案例是 `_apply_anchor` 從 base_idx 往後重標時，本應是 1 拍起始的地方卻在小節中間，造成前一小節「多拍」——這需要另外的 Pass 189 或修改 `_apply_anchor` 本身。

預期效果：`irregular_measure_count` 從 14 下降到 **13**（只有 3 拍那一個被修掉）。

---

## 0. 背景

Pass 187 讓 `beat_phase_protected_ranges` 從 37 降到 15 段（-59%），但真實音訊
完整管線回歸確認 `irregular_measure_count` 維持 14，沒有改善。

根本原因：`SteadyPercussionCountAnchorNode._apply_anchor()` 從 `base_idx`（第一
下擊點最近的格點）開始往後重標 1-2-3-4 循環，但沒有回頭更新 `base_idx` 之前的
拍點標號。結果：

```
... [beat 2] [beat 3] [beat 4] | [base_idx=beat 1] [beat 2] [beat 3] [beat 4] ...
                   ^                ^
          前一段的相位（舊）    新錨點開始位置
```

**若 `base_idx` 之前的相位跟新錨點相位「模 4 不對齊」**，那麼從上一個 beat 1
到 `base_idx` 之間可能只有 1-3 個 beat，`MeasureMapNode._build_from_downbeats`
就會切出一個只有 1-3 拍的破碎小節，計入 `irregular_measure_count`。

已知 14 個不規則小節裡，有 11 個是保護區段交界附近的（Pass 187 任務書 §0 記錄）。

---

## 1. 修法：MeasureMapNode 加入「短小節前向合併」後處理

在 `_build_from_downbeats` 產出初始 `measures` 之後，加入一個後處理步驟，
把太短的破碎小節合併給前一個小節：

### 合併條件

一個小節被視為「破碎小節」（應合併給前一個），當且僅當：
1. `beat_count < round(common_length * MERGE_THRESHOLD)`（預設 `MERGE_THRESHOLD = 0.75`）
2. **不是第一個小節**（沒有「前一個」可合併）
3. **不是最後一個小節**（最後可能是正常的截斷，另有 `is_incomplete` 旗標處理）
4. 合併後前一個小節的 `beat_count` 不超過 `common_length + common_length - 1`
   （即最多 7 拍，避免把大段都吃進去）

### 合併方式

把破碎小節的所有 beats 附加到前一個小節的 beats 尾端：
- 前一個小節的 `end_time` 改用破碎小節的 `end_time`
- 前一個小節的 `beat_count` 更新
- 前一個小節的 `is_variable_length` 重新判斷
- 破碎小節從 `measures` 移除
- 後續所有小節的 `measure_number` 重新編號

### 迴圈策略

合併後可能造成連鎖（例如兩個相鄰破碎小節），用 `while` 迴圈持續掃描直到
沒有任何小節符合合併條件。每輪掃描從頭開始，確保不漏。

---

## 2. 實作位置

**只改 `pgm_craft/workflow/audio_nodes.py` 的 `MeasureMapNode`：**

- 新增 `MERGE_THRESHOLD = 0.75` 類別常數
- 新增 `_merge_short_measures(measures, common_length)` 方法
- 在 `_build_from_downbeats` 的最後，`return measures` 之前呼叫一次

**不動：**
- `_prune_ghost_downbeats`（處理的是「重複 downbeat」，跟這次的「破碎小節」
  問題性質不同，兩者各司其職）
- `SteadyPercussionCountAnchorNode` 的任何邏輯
- 下游 5 個節點尊重 `beat_phase_protected_ranges` 的邏輯

---

## 3. 驗證計畫

1. **合成測試（破碎小節被合併）**：
   - 合成 [4拍正常, 2拍破碎, 4拍正常] 的 downbeat 序列
   - 確認合併後輸出 2 個小節（第一個 6 拍, `is_variable_length=True`）
   - 確認 `irregular_measure_count`（等同 `is_variable_length` 計數）從 1 降到 0

2. **合成測試（末尾截斷不合併）**：
   - 合成 [4拍, 4拍, 3拍（最後）] 的序列
   - 確認最後一個不被合併（它是正常的截斷），`is_incomplete=True` 保留

3. **合成測試（第一個小節破碎，沒有前一個可合併）**：
   - 確認第一個破碎小節不被吃掉，保持原樣

4. **合成測試（連鎖合併）**：
   - 合成 [4拍, 2拍, 1拍, 4拍] 的序列
   - 確認 2拍 + 1拍 都合併給第一個 4拍，輸出 2 個小節

5. **既有測試全跑一次**：`test_sdd_pass23/27/28/42/87/102/103/104/120/121/124/
   141/144/178/179/180/181/182/183/184/185/186/187`、`test_module3_bt`

6. **真實資料量化驗證**：重跑完整管線，確認 `irregular_measure_count` 從 14
   下降（預期接近 0-3，因為部分是既有問題或末尾截斷）；BPM 跳動維持 0。

---

## 4. 範圍界定

- 只改 `MeasureMapNode` 的 `_build_from_downbeats` 及新增 `_merge_short_measures`
- `_prune_ghost_downbeats` 不動（它的閾值 0.6 跟這次的 0.75 不衝突，兩個階段
  各自處理不同問題）
- 如果真實資料驗證後 `irregular_measure_count` 還是 > 3，再考慮往 `_apply_anchor`
  加入「往前補標」邏輯——但那是另一個後續 pass，不在這次範圍內

---

## 5. 實作結果

### 5.1 修改內容
1. **`MeasureMapNode` 擴充**：
   - 新增類別常數 `SHORT_MEASURE_MERGE_THRESHOLD = 1.0`。
   - 新增 `_merge_short_measures(measures, common_length)` 方法：針對中間非首尾小節，若 `beat_count < common_length`（即小於標準拍數之短小節），將其音符與時間區段合併至前一個小節中（上限不超過 `common_length * 2 - 1`）。
   - 在 `_build_from_downbeats()` 尾端呼叫後處理。

### 5.2 測試與回歸
- **SDD 測試**：`tests/test_sdd_pass188.py` （6/6 PASSED）。
- **單元回歸 suite**：`test_sdd_pass23/27/28/42/87/102/103/104/120/121/124/141/144/185/186/187/188` + `test_commercial_beat_quality` + `test_module3_bt` （84/84 PASSED）。

### 5.3 真實音訊完整管線回驗結果
- **執行時間**：421.3s
- **小節數**：112 小節 (黃金基準 -9)
- **BPM 跳動**：0 次
- **不規則小節數**：14 個

**細節分析**：
- 原 Measure 8 (3拍) 已成功合併入 Measure 7 (變為 7 拍)。
- 總小節數由 113 下降為 112。
- 目前剩餘 14 個不規則小節主要由 **5拍 (5個), 6拍 (4個), 7拍 (2個)** 等「過長小節」組成，主因是 `SteadyPercussionCountAnchorNode._apply_anchor()` 往後重標號時，錨點邊界之前的舊相位未同步往前重補算，導致前一個小節出現多餘拍數。
- 此「過長小節」現象需要透過 **Pass 189：Anchor 邊界雙向相位重補與相位對齊** 進行處理。

