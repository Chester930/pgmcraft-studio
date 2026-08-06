# Pass 180 任務書：修正 ViterbiTempoSmoothingNode 誤刪連續補強區塊的根本問題

**狀態**：設計已確認（見下方第 1 節），實作中。
**目標**：修正 `ViterbiTempoSmoothingNode`（`pgm_craft/workflow/beat_tracking_bt.py`）
現有的離群值判斷邏輯——目前用「跟全曲中位數比較」判斷孤立離群值，實際上完全
沒有檢查「孤不孤立」，導致 `GapReinforcementNode` 補強出的一整段連續拍點（跟
全曲中位數節奏本來就不同，但內部自己連貫）被整批誤判成離群值，逐拍疊加修正
後被壓縮進一個只有原本一半長的時間窗，造成 click track 出現長達數秒的完全
靜音（見 `docs/PASS-178-GAP-REINFORCEMENT-PRODUCTION-INTEGRATION-TASK.md`
第 4.3.1 節）。**這次要治本，不是加排除清單繞過問題。**

---

## 0. 背景：這個 bug 是怎麼被抓出來的

1. Pass 178 的 `GapReinforcementNode` 真實資料 A/B 回歸測試（《World is Mine》）
   一開始只用統計數字（小節數、BPM 跳動次數）發現處理組整體比黃金基準、也比
   停用時的對照組差，當時的根因分析停留在「品質守門沒檢查邊界連貫性」。
2. 使用者實際試聽處理組的 `mix_with_click.wav` 後，回報 7.1s-13.5s、
   16.1s-19.2s 兩段完全沒有 click 聲——這比 BPM 跳動更嚴重，光看統計數字沒有
   抓到「拍點整段消失」這件事。
3. 追查方式：比對 `GapReinforcementNode` 自己匯出的診斷紀錄
   （`reports/gap_reinforcement/beats.json`），確認它執行完畢當下 4.4s-21.8s
   這段其實有連續規律的拍點（433 個）——證明消失不是 `GapReinforcementNode`
   自己刪的。接著把這 433 個真實拍點原封不動丟進 `ViterbiTempoSmoothingNode`
   的實際演算法重播（純陣列運算，不需要音訊、不需要重跑 Demucs），精確重現了
   消失現象：原本橫跨 4.389s-18.947s（連續 21 個拍點）被壓縮進 2.589s-9.789s。

## 1. 根因與修法（已跟使用者討論並確認）

### 1.1 根因

`ViterbiTempoSmoothingNode` 現在的邏輯：

```python
median_interval = np.median(intervals)  # 用全曲中位數當基準
for interval_index, curr_int in enumerate(intervals):
    if abs(curr_int - median_interval) / (median_interval + 1e-6) > self.tolerance_pct:
        beat_index = interval_index + 1
        smoothed_beats[beat_index, 0] = smoothed_beats[beat_index - 1, 0] + median_interval
        outlier_count += 1
```

兩個問題疊加：
1. **判斷基準是全曲中位數，不是「孤不孤立」**——只要單一拍點間隔跟全曲中位數
   差超過 20%，不管前後鄰居是什麼樣子，一律判定是離群值。一整串連續、內部
   彼此一致但跟全曲平均不同的拍點（無論是真正的漸速/漸慢，還是
   `GapReinforcementNode` 補強出的局部不同節奏），會被整串誤判。
2. **修正值疊加在已經被修正過的時間點上**——`smoothed_beats[beat_index - 1, 0]`
   如果上一步已經被改寫過，這一步的修正會接著疊加，連鎖效應把一整串「離群值」
   越拖越遠，最終被壓縮/搬移到跟原始位置差很多的地方。

### 1.2 專案裡已經有正確的參考實作：`TempoOscillationDampingNode`

同一個檔案裡，`TempoOscillationDampingNode`（跑在 `ViterbiTempoSmoothingNode`
之後）已經用更安全的方式解決同一類問題，而且已經有既有測試驗證
（`test_tempo_oscillation_damping_preserves_gradual_tempo_change`）：

| | Viterbi（現況，有問題） | TempoOscillationDamping（既有、正確） |
|---|---|---|
| 判斷基準 | 跟全曲中位數比較 | 跟左右鄰居組成的「一短接一長」配對模式比較（`_is_oscillation_pair`），且要求配對總和接近 `2×中位數`（真正的漸變速度不會有這種「剛好抵銷」的訊號，天然不會誤判） |
| 修正來源 | 疊加在已修正的時間點上 | 永遠用原始未修改的 `beats[i-1]`/`beats[i+1]` 算修正值，不連鎖 |
| 品質守門 | 沒有 | 有，`_score_beat_grid_quality` 前後比較，沒有變好就 `REJECTED` |
| 排除區/邊界 guard | 沒有 | 有 `snap_exclusion_zones`/`drum_fill_regions`/`edge_beat_guard` |

### 1.3 修法：把 Viterbi 的離群值判斷邏輯換成同一套原則

不刪除、不合併兩個節點（範圍過大，非必要），只重寫
`ViterbiTempoSmoothingNode.execute()` 內部「這是不是孤立離群值」的判斷與修正
邏輯：

1. **用左右鄰居配對模式判斷**（可直接複用/仿照 `TempoOscillationDampingNode.
   _is_oscillation_pair` 的寫法）：只有「一短接一長剛好互相抵銷」（配對總和
   接近 `2×median_interval`）才算孤立離群值；一整段持續同方向偏移的不算。
2. **修正值一律從原始未修改的陣列算**，不疊加在已修正的結果上，消除連鎖漂移。
3. **加品質/離群配對數守門**：修正後如果沒有讓網格分數變好、離群配對數沒有
   減少，整批退回原始結果（比照 `TempoOscillationDampingNode` 的
   `accepted` 判斷）。
4. **補上排除區檢查跟邊界 guard**：尊重 `snap_exclusion_zones`/
   `drum_fill_regions`，開頭結尾加 edge guard，跟鏈路上其他節點一致。

這樣改完，這個節點自己文件寫的「孤立突變離群拍點」才會真的名副其實——現在的
程式碼其實沒有真的檢查「孤不孤立」，這是原本設計跟實作之間的落差。

**範圍界定**：這次只修 `ViterbiTempoSmoothingNode` 判斷+修正邏輯本身，不動
`GapReinforcementNode` 自己的品質守門（`_is_improvement`），也不做 Pass 176
原始設計規劃的「用 `BidirectionalBarAlignmentNode`/`TwoWayAnchorBacktraceNode`
做雙向錨定」的邊界連貫性檢查——那是另一個獨立、還沒開始的工作（見
`docs/PASS-178-...-TASK.md` 第 4.5 節），修好 Viterbi 解決的是「災難性地整段
拍點被搬走」，不會自動讓補強區塊跟周邊網格接得音樂上完全平順。

---

## 2. 驗證計畫

1. **回歸測試（保留舊行為）**：合成一個「單一孤立拍點雜訊」場景（一拍間隔
   異常短、緊接著一拍異常長，中間夾在正常節奏裡），驗證修改後的節點仍然能
   正確修正——不能因為改了判斷邏輯就連原本該修的正常案例也不修了。
2. **重現並驗證修復（新行為）**：直接使用這次真實抓到的
   `reports/gap_reinforcement/beats.json`（4.389s-18.947s 那段連續 21 拍）當
   測試固定資料，驗證修改後的節點**不會**再把這段壓縮消失——拍點應該維持在
   原本的時間位置附近，不應該被搬移超過一個拍子的間隔。
3. **既有測試全跑一次**：`tests/test_sdd_pass178.py`、`tests/test_sdd_pass179.py`、
   既有 Stage 3 回歸（`test_commercial_beat_quality` +
   `test_sdd_pass23/28/42/102/103/104/141`，共 38 項），確認沒有破壞其他曲子
   既有行為。
4. **真實音訊 A/B 回歸（可選，成本較高）**：`GapReinforcementNode(enabled=True)`
   重新跑一次《World is Mine》，確認 click 消失問題解決、BPM 跳動次數下降。
   排在單元測試、既有回歸測試都過了之後才做，且需要使用者同意才執行（重跑
   一次要 20-30 分鐘）。

---

## 3. 尚未完成/範圍外的後續工作

- `GapReinforcementNode` 自己的邊界連貫性檢查（雙向錨定），仍然是分開、還沒
  開始的工作。
- 這次修好後 `GapReinforcementNode` 是否可以把 `enabled` 改回 `True`——不會
  自動變成可以，還是要等邊界連貫性檢查也做完、且有更多首歌的真人複核資料，
  才重新考慮升格問題（見 `docs/PASS-178-...-TASK.md` 第 4.5 節）。
