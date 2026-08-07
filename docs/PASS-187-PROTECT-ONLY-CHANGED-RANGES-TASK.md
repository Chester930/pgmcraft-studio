# Pass 187 任務書：只保護「真的改動過標號」的區段，不保護無效區段

**狀態**：已實作，單元測試與真實資料量化驗證皆已通過（見第 4 節）。真實
音訊完整管線回歸（確認對 `irregular_measure_count` 的最終影響）進行中。

---

## 0. 背景

使用者實際試聽 Pass 186 的真實完整管線輸出後回報：「有很多不完整的小節。
沒有走完四拍，就又突然跳下一個小節。節拍錯亂問題」。

追查（比對這次真實輸出的 14 個不規則小節位置跟 37 個保護區段邊界）確認：
**11 個**不規則小節都落在保護區段邊界附近（距離都在一個拍距內），另外 3 個
跟這次改動無關（既有問題，含收尾截斷）。`irregular_measure_count` 從
Pass 185 之前的基準 1，先跳到 Pass 185 的 12，Pass 186 又惡化到 14——
保護區段越多，交界處衝突就越多。

進一步查證：這次 37 個「套用」的錨點裡，實際比對套用前後的標號，
**26 個（70%）套用前後標號完全沒變**——也就是說，這個候選段的局部證據
剛好跟「不特別保護、讓它自然被下游重新編號」算出來的結果一樣，保護它完全
沒有實際效益，卻還是被列進 `beat_phase_protected_ranges`，平白多了一個
交界處風險。只有 11 個是真的改動了標號（這才是真正需要保護的）。

---

## 1. 修法：只有「套用後真的改動了標號」的區段，才列入保護清單

在 `SteadyPercussionCountAnchorNode.execute()` 裡，套用每個候選錨點之後，
比對套用前後這段範圍內的標號有沒有變化，只有真的變了才加進
`protected_ranges`：

```python
new_beats = beats.copy()
applied = []
protected_ranges = list(blackboard.get_val("beat_phase_protected_ranges", []) or [])
for k, (stem_key, run) in enumerate(accepted):
    next_start = accepted[k + 1][1]["start_time"] if k + 1 < len(accepted) else float("inf")
    before_labels = new_beats[:, 1].copy()  # 套用這個錨點之前的標號快照
    result, prot_start, prot_end = self._apply_anchor(new_beats, timestamps, run, next_start)
    if result is not None:
        new_beats = result
        applied.append({...})  # 不變
        if prot_start is not None and prot_end is not None:
            touched_mask = (timestamps >= prot_start) & (timestamps <= prot_end)
            actually_changed = bool(np.any(new_beats[touched_mask, 1] != before_labels[touched_mask]))
            if actually_changed:
                protected_ranges.append((prot_start, prot_end))
```

**注意**：`applied` 清單（`steady_percussion_anchor_report` 裡的紀錄）維持
不變，還是所有成功套用的候選都要記錄——這樣才看得出「這次找到並嘗試套用
了幾段」。只有 `protected_ranges`（真正影響下游保護行為的清單）要過濾，
兩者要分開，不要混在一起。

`before_labels` 要用「套用這一個錨點之前」的快照，不是整個迴圈開始前的
快照——因為前一個錨點的套用結果，可能已經改變了這個區域的標號，要跟
「這一步真正的改動」比較，不是跟最原始的輸入比較。

---

## 2. 驗證計畫

1. **合成測試（無效保護被過濾掉）**：合成一個候選段，其局部證據算出來的
   標號剛好跟該區段原本的標號一樣（沒有實際改動），驗證這段不會被列進
   `beat_phase_protected_ranges`（雖然還是會出現在 `applied` 清單裡）。
2. **合成測試（真的改動的區段依然保護）**：合成一個候選段，套用後標號
   真的變了，驗證這段依然正確列入 `beat_phase_protected_ranges`，且
   Pass 185 既有的保護行為（下游 5 個節點尊重這段）依然生效。
3. **既有測試全跑一次**：`tests/test_sdd_pass181/182/183/184/185/186.py`
   全部要維持通過——特別注意 `test_sdd_pass185.py` 裡驗證保護機制生效的
   測試，那些測試場景本身應該是「真的改動過標號」的案例，不受這次過濾
   影響；如果因為這次修改而意外壞掉，要檢查是不是測試場景本身剛好是
   無效保護（那樣的話測試需要調整成真的會改動標號的場景，不是程式邏輯
   有錯）。
4. **既有 Stage 3 回歸測試全跑一次**：`test_commercial_beat_quality`、
   `test_sdd_pass23/28/42/87/102/103/104/120/121/124/141/144/178/179/180`、
   `test_module3_bt`。
5. **真實資料量化驗證**：直接對真實資料重跑，確認保護區段數量從 37 大幅
   下降（預期接近 11，實際數字可能因為 Pass 187 本身也會影響後續 dedup/
   套用順序而略有不同，記錄實際數字，不要假設一定剛好是 11）。
6. **真實音訊完整管線回歸（需使用者同意才執行，成本較高）**：確認
   `irregular_measure_count` 這次真的下降，且 18-20 秒的重音位置依然
   正確（不能因為減少保護區段就把好不容易修好的目標區段也濾掉）。

---

## 3. 範圍界定

- 只改 `SteadyPercussionCountAnchorNode.execute()` 收集 `protected_ranges`
  的邏輯，不動 `_apply_anchor`、`_find_steady_runs`、`_dedupe_overlaps`、
  `_confirmed_by_whole_track`（Pass 186 剛修過）本身。
- 不改 Pass 185 新增的下游 5 個節點尊重保護區段的邏輯——它們的行為（尊重
  `beat_phase_protected_ranges` 清單）不用變，這次只是讓清單本身更精簡、
  更準確。
- 這次修完後，如果真實資料驗證顯示 `irregular_measure_count` 依然偏高
  （例如還是比基準 1 高出不少），代表光靠篩選還不夠，交界處平滑化本身
  可能還是需要處理——但那是另一個獨立評估後才決定要不要做的後續工作，
  不預先排進這次任務。

---

## 4. 實作結果

### 4.1 修改內容

`SteadyPercussionCountAnchorNode.execute()` 的套用迴圈裡，每次呼叫
`_apply_anchor()` 之前先快照 `before_labels`，套用後比對這段範圍
（`prot_start` 到 `prot_end`）內的標號有沒有真的改變，只有真的改變才把
這段加進 `protected_ranges`。`applied` 清單（含 `steady_percussion_
anchor_report`）維持不變，還是記錄所有成功套用的候選，跟 `protected_
ranges`（真正影響下游保護行為的清單）分開。

### 4.2 測試結果

新增 `tests/test_sdd_pass187.py`（3 項全過，過程中修正了 2 個測試場景本身
的索引選錯問題，不是程式邏輯有誤）：

1. `test_noop_anchor_not_protected`——候選段套用後標號沒有實際改動，確認
   不列入 `beat_phase_protected_ranges`（但依然出現在 `applied`）。
2. `test_real_change_anchor_still_protected`——候選段套用後標號真的改變，
   確認正確列入保護清單，且 `BeatGridContinuityRepairNode` 觸發全曲重編號
   時，這段依然不被覆蓋（Pass 185 的保護機制沒有被破壞）。
3. `test_mixed_scenario_only_changed_range_protected`——一個無效候選 +
   一個真的改動的候選，確認只有後者進保護清單。

既有回歸測試（`C:/Python313/python.exe`）：`test_commercial_beat_quality`、
`test_sdd_pass23/28/42/87/102/103/104/120/121/124/141/144/178/179/180/
181/182/183/184/185/186`、`test_module3_bt`，加上新增的 `test_sdd_pass187`，
共 120 項全數通過。

### 4.3 真實資料量化驗證

直接對真實 `beats`（從 Pass 186 真實跑法留下的 `measure_map.json` 還原）
重跑 `SteadyPercussionCountAnchorNode`：

- `applied` 依然是 37（找到並嘗試套用的候選數量不變）。
- `protected_ranges` 從 37 降到 **15**（降了 59%），跟第 0 節分析的「26
  個無效保護」量級一致（因為套用順序是累積的，後面錨點的「套用前」快照
  已經包含前面錨點的改動，實際篩選結果跟單獨逐一比對的 26/37 略有差異，
  但同一個數量級）。
- 18.567528s-21.804354s（涵蓋原本的目標區段 18-20 秒）依然在保護清單內，
  確認篩選沒有把真正需要保護的區段也濾掉。

### 4.4 尚未完成

第 2 節第 6 點要求的真實音訊完整管線回歸——確認 `irregular_measure_count`
（Pass 186 真實跑法是 14）這次真的下降，且 18-20 秒的重音位置依然正確。
正在執行中。
