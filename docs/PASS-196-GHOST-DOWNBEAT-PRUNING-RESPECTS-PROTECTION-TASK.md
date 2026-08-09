# Pass 196 任務書：`_prune_ghost_downbeats` 不該剔除受保護的錨定 downbeat

**狀態**：已實作，單元測試通過、真實音訊完整管線回歸已完成，確認是真正
的修復（見第 4 節）。

**實作過程中發現範圍比原訂計畫大**：只修 `_prune_ghost_downbeats` 還不
夠——`_prune_ghost_downbeats` 保住了受保護的 downbeat 索引之後，緊接著
執行的 `_merge_short_measures`（Pass 188/192）會把兩個相鄰的短小節（例如
被保護區段切出來的 2 拍 + 2 拍）自動合併成一個 4 拍小節，合併時
`_measure_entry` 一樣是用位置重新編號——等於在下一步又把 Pass 196 剛
救回來的證據洗掉一次。因此這次一併修改 `_merge_short_measures`，見下方
第 1.2 節。

---

## 0. 背景與問題診斷

Pass 195 追查發現，Pass 194 遺留的 9 個不規則小節（8.041s/21.458s/
32.382s/77.803s/81.446s/93.802s/97.197s/108.652s/152.023s）跟
`_ensure_44_phase_continuity`（Pass 193-195 這整條線索）完全無關。真正
決定小節分界的是 `_prune_ghost_downbeats`（**Pass 170** 就存在的機制，
比整條 Pass 181-195 的工作都早）：

```python
common_step = statistics.median(gaps)   # 通常是 4（大部分小節 4 拍）
ghost_threshold = 0.6 * common_step     # 通常是 2.4
# 相鄰 downbeat 間距（陣列位置差）< threshold 就視為 ghost，剔除後一個
```

以 77.803s 為例，`MeasureMapNode` 收到的原始拍點陣列（`_ensure_44_
phase_continuity` 修復之前）本身就是：

```
76.367→1, 76.737→2, 77.096→3, 77.45→4,
77.803→1, 78.18→2,
78.542→1, 78.889→2, 79.266→3, 79.672→4,
80.02→1, ...
```

77.803 和 78.542 都被標成 `beat==1`，只間隔 2 個位置——低於 2.4 的門檻，
`_prune_ghost_downbeats` 直接把 78.542 剔除，兩段合併成一個 6 拍怪異
小節。

**這次追查新發現的關鍵事實**：這兩個位置**都不是雜訊**。核對這次真實
跑法的 `beat_phase_protected_ranges`（`SteadyPercussionCountAnchorNode`
建立），發現裡面剛好有兩個緊鄰的保護區段：

```
[76.36, 78.52]
[78.52, 82.16]
```

77.803s 落在第一個保護區段內（`SteadyPercussionCountAnchorNode` 對這段
穩定擊點驗證過的錨定 beat-1）；78.542s 落在第二個保護區段內（另一段
穩定擊點各自驗證過的錨定 beat-1）。這兩個 downbeat **都是真實證據驗證
過的錨點**，只是剛好落在同一首歌裡兩個彼此很接近、各自獨立建立的保護
區段交界處——不是同一個重音被偵測兩次的雜訊。`_prune_ghost_downbeats`
完全不知道有 `beat_phase_protected_ranges` 這回事，純粹用陣列位置間距
判斷，把後面那個真實、受保護的錨點當雜訊剔除掉了。

Pass 170 建立這個機制時，Stage 3 還沒有 `SteadyPercussionCountAnchorNode`
（Pass 181 才引入）這種會針對局部證據建立密集保護錨點的節點，當時「兩個
離得很近的 downbeat 幾乎一定是雜訊」的假設是合理的。但現在 Stage 3 已經
會針對真實鼓點證據建立多達 30 幾段保護區段（這次真實跑法是 33 段，
幾乎涵蓋大半首歌），近距離 downbeat 候選不再能簡單當雜訊處理。

---

## 1. 修法：`_prune_ghost_downbeats` 永遠不剔除受保護的 downbeat

1. 把 `beat_phase_protected_ranges` 貫穿到 `_build_from_downbeats` 與
   `_prune_ghost_downbeats`：
   ```python
   def _build_from_downbeats(self, beat_rows, downbeat_indexes, source="downbeat", protected_ranges=None):
       downbeat_indexes = self._prune_ghost_downbeats(beat_rows, downbeat_indexes, protected_ranges)
       ...
   ```
2. `_prune_ghost_downbeats` 判斷是否剔除某個 downbeat 之前，先檢查它的
   時間是否落在保護區段內——落在保護區段內的 downbeat（不管間距多近）
   永遠不剔除：
   ```python
   def _prune_ghost_downbeats(self, beat_rows, downbeat_indexes, protected_ranges=None):
       protected_ranges = protected_ranges or []

       def _is_protected(t):
           return any(p_start <= t <= p_end for p_start, p_end in protected_ranges)

       ...
       pruned = [downbeat_indexes[0]]
       for i in range(1, len(downbeat_indexes)):
           idx = downbeat_indexes[i]
           gap = idx - pruned[-1]
           t = float(beat_rows[idx]["time"])
           if gap >= ghost_threshold or _is_protected(t):
               pruned.append(idx)
           # 否則視為 ghost，跳過（除非受保護）
       return pruned
   ```
3. `build_measure_map()` → `_build_from_downbeats()` 的呼叫點要把已經
   讀到的 `protected_ranges` 傳進去（`build_measure_map` 已經在 Pass 194
   時取得這個參數，只是還沒傳給 `_build_from_downbeats`）。

這樣修改後，77.803s/78.542s 這種情況會產生兩個真的很短（各 2 拍）的
相鄰小節，而不是被靜默合併成 6 拍怪異小節。

### 1.2 `_merge_short_measures` 也要尊重保護區段（實作中發現，範圍擴大）

`_prune_ghost_downbeats` 保住 78.542 這個 downbeat 索引之後，
`_build_from_downbeats` 緊接著呼叫 `_merge_short_measures`（Pass
188/192）——它會看到兩個相鄰的短小節（各 2 拍），因為「前一個也是短
小節，合併後 2+2=4 不超過 common_length」符合防膨脹保護的合併條件，
自動把它們合併成一個 4 拍小節。合併時一樣是用陣列位置重新編號
（`_measure_entry` 的行為），78.542 又會被洗成合併小節的「第 3 拍」，
等於 Pass 196 在 `_prune_ghost_downbeats` 救回來的證據，下一步又被吃掉
一次。

修法：`_merge_short_measures` 增加 `protected_ranges` 參數，合併前檢查
「即將被吞併、往後接到前一個小節的那個短小節（`m`）」自己的起點是不是
受保護的 downbeat——如果是，不合併，保留它自己獨立成一個小節：

```python
def _merge_short_measures(self, measures, common_length, protected_ranges=None):
    protected_ranges = protected_ranges or []

    def _is_protected(t):
        return any(p_start <= t <= p_end for p_start, p_end in protected_ranges)

    ...
    while i < len(measures):
        m = measures[i]
        if m.get("is_incomplete"):
            i += 1
            continue
        if _is_protected(m["start_time"]):   # Pass 196 新增
            i += 1
            continue
        if m["beat_count"] < common_length:
            ...
```

`_build_from_downbeats` 呼叫 `_merge_short_measures` 時要把
`protected_ranges` 傳進去。這樣修改後，77.803s/78.542s 這種情況最終會
變成兩個各自獨立的 2 拍小節（`is_variable_length=True`），而不是被
merge 或 ghost-pruning 任何一層吃掉——反映的是「這裡真的有兩個緊鄰的
驗證過重音」的真實情況，Click 打點會分別落在 77.803s 和 78.542s 上，
不再是資料被吃掉的假象。

---

## 2. 驗證計畫

1. **合成測試（保護區段內的 downbeat 不被剔除）**：合成一個場景，兩個
   downbeat 間距小於 ghost 門檻，但都落在各自的保護區段內，驗證兩個都
   保留、不合併成一個怪異的大小節。
2. **合成測試（沒有保護區段時，既有 ghost-pruning 行為不變）**：向後
   相容——沒有 `protected_ranges` 時，行為跟 Pass 170 原本設計完全一樣。
3. **合成測試（只有一個受保護、另一個不受保護）**：驗證只有真的落在
   保護區段內的那個會被保留，另一個沒有證據支持的還是照舊被當雜訊剔除。
4. **既有測試全跑一次**：`tests/test_sdd_pass188/192/193/194/195.py`、
   `tests/test_bt_workflow.py` 全部要維持通過。
5. **真實資料量化驗證**：重跑
   `scratch/run_pass195_default_pipeline_reverify.py`（或新建
   `run_pass196_...`），確認：
   - 9 個問題點附近的 `beat_phase_protected_ranges` 錨點是否不再被
     ghost-pruning 吃掉（直接核對這些位置在最終 `measure_map.json`
     裡的標號）。
   - `irregular_measure_count`、`total_measures` 的變化（不預設一定
     會下降——可能只是把一個 6 拍怪異小節換成一個更小、但更準確的
     2 拍小節，仍然算 `is_variable_length=True`，但 Click 打點的位置
     會更準確）。
   - 請使用者實際試聽這幾個位置，確認 Click 重音是否真的落在正確的
     擊點上（這次的重點是「準確度」，不是單純把不規則小節數字壓低）。

---

## 3. 範圍界定

- 改 `_prune_ghost_downbeats`、`_merge_short_measures` 與其呼叫鏈
  （`_build_from_downbeats`、`build_measure_map`）——這兩個都要尊重
  `beat_phase_protected_ranges`，才能真正保住受保護的錨點（只修
  ghost-pruning 不夠，見第 1.2 節）。不動 `_ensure_44_phase_continuity`
  （Pass 195 已經是正確的設計，保留）。
- 不主動決定要不要進一步合併/處理這次修復後可能出現的真的很短的保護
  小節——先如實呈現真實資料的樣貌，再視真實試聽結果決定是否需要後續
  任務。
- 不假設這次修法會讓 `irregular_measure_count` 數字變好看——這個指標
  在整個 Pass 187-195 的過程裡已經證實不完全可靠（Pass 193 用犧牲準確度
  換來漂亮數字的教訓），這次以「錨點證據有沒有被正確保留」為主要驗證
  依據，數字變化只是參考。

---

## 4. 實作結果

### 4.1 修改內容

`_prune_ghost_downbeats` 與 `_merge_short_measures` 都新增
`protected_ranges` 參數，`_build_from_downbeats` 一路貫穿。受保護的
downbeat 永遠不被 ghost-pruning 剔除；即將被吞併進前一個小節的短小節，
如果自己的起點是受保護的 downbeat，也不合併。

### 4.2 單元測試

新增 `tests/test_sdd_pass196.py`（3 項全過）：兩個間距很近但都受保護的
downbeat 都保留、沒有保護區段時既有行為不變（向後相容）、只有一個受
保護時只保留那一個。既有 `tests/test_sdd_pass170/188/192/193/194.py`、
`tests/test_bt_workflow.py` 共 38 項全數通過。

### 4.3 真實資料驗證：確認是真正的修復

重跑 `scratch/run_pass196_default_pipeline_reverify.py`。以深入分析過的
77.803s 為例：

- **修復前**（Pass 194/195）：`measure=53, beat_count=6` —— 一個吃掉
  78.542 這個真實受保護錨點的怪異大小節，78.542 被錯標成「beat 3」。
- **修復後**（Pass 196）：拆成兩個正確的小節——
  `measure=56 [(1,77.803),(2,78.180)]` +
  `measure=57 [(1,78.542),(2,78.889),(3,79.266),(4,79.672)]`。78.542
  正確標成「beat 1」，Click 會在這兩個真實驗證過的重音位置各自正確
  打點。

Pass 194 遺留的 9 個問題點，**7 個**出現同樣的修復模式（21.458s→拆成
1 拍孤立小節 + 正常 4 拍、32.382s、77.803s、81.446s、93.802s、
108.652s、152.023s）；**2 個**（8.041s、97.197s）這次沒有被拆開，依然
是 5 拍怪異小節——代表這兩處的成因跟保護區段衝突無關，是別的問題
（留待後續視聽感驗證結果決定是否需要繼續追查）。

18-20 秒目標區段依然正確（beat-1 在 18.568s/20.011s）。整體數字：
**122 小節**（差黃金基準 **+1**，第一次這麼接近，且是真實而非造假的
結果）、`bpm_jump_count` 維持 0、`irregular_measure_count` 11（數字本身
沒有下降，但組成完全不同——不再是少數幾個被吃掉證據的大型怪異小節，
而是多個真實反映「這裡有兩個緊鄰驗證過重音」的小型精確小節）。

### 4.4 尚待確認

請使用者實際試聽這次的 Click 音檔，確認：
1. 77.803s / 78.542s（以及其餘 6 個同類位置）附近的重音是否確實各自
   落在正確的擊點上，聽起來是否比之前更準確、更不突兀。
2. 8.041s / 97.197s 這兩個未被這次修法解決的位置，聽起來的問題有多
   明顯——決定是否需要另開任務追查。
