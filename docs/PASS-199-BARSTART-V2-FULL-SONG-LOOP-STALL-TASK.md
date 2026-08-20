# Pass 199 任務書：修好 BarStart V2 全曲迴圈的卡死問題

**狀態**：Codex 已依規格實作，解決了原本的卡死問題，但獨立驗證+
使用者實際聽感發現「修好卡死」不等於「修好」——85% 的小節其實是
複製 v1 舊網格充數，不是 V2 自己的證據判斷，且破壞了一個既有安全
測試、品質分數不升反降。**目前建議不要採用這次的 V2 結果，先退回
Pass 197+198 階段 A 的舊方法**。完整發現見第 5 節追記。跟 Pass
194-198 是不同的子系統（`module3_barstart_v2_bt.py`，不是
`audio_nodes.py` 的 `MeasureMapNode`）。

---

## 0. 背景：為什麼要查 BarStart V2

Pass 198 追到最後（見 `docs/PASS-198-INTRA-BAR-DOWNBEAT-PROMOTION-TASK.md`
第 9.3 節）確認：用 `MeasureMapNode`（Stage 4）層級的 relabel/插值後處理，
**不可能安全達成使用者要求的 `irregular_measure_count=0`**——部分
小節本來就真實偵測到 5-6 個 onset 確認過的拍點，relabel 只能把「多
出來的那一拍」往下一小節推，問題不會消失。

使用者接著問：「有沒有辦法明確知道某一拍一定是小節第一拍」，並舉例
「過門後第一下鼓點」。調查後發現專案裡**已經有一套完全不同、更完整
的子系統在做這件事**：`pgm_craft/workflow/module3_barstart_v2_bt.py`
（BarStart V2，~3530 行、約 20 個節點），核心設計正是「收集多來源
證據（鼓組間距、鼓+貝斯共振、和絃/旋律切點、既有拍點網格、雙向對齊）
確認高信心小節起點，一個一個 commit，中間空隙靠備援機制補上」——
跟使用者描述的「先確認、再依序補齊」架構完全一致。

真實資料回驗顯示 BarStart V2 對這首歌只成功跑了前 8 個小節（到
10.4 秒）就整個卡死放棄，之後全曲改用舊方法（`module3_beat_click_report.json`
的 `barstart_v2_report`）：

```
committed_bar_starts: [0.0, 1.595521, 3.083979, 4.572437, 5.997654, 7.422756, 8.911213, 10.434276]
full_song_loop_report: {"status": "COMPLETED", "iterations": 7, "committed_bar_count": 8,
                         "stall_recoveries": 1, "stop_reason": "stalled_no_recovery", "unresolved_span_count": 6}
promotion_gate: {"adoptable": false, "blockers": ["UNRESOLVED_BAR_SPANS_PRESENT"]}
notes: ["BarStart v2 is the default click grid whenever it completes with no unresolved bar spans
         -- confirmed via real listening tests to consistently sound better than v1, ..."]
```

**這條線值得追**：BarStart V2 完整跑完時，已經用真實聽感驗證過比
舊方法（也就是我們整個 Pass 178-198 系列在修的東西）聽起來更好。如果
能讓它對這首歌跑完不卡住，很可能一次解決我們追了好幾輪的問題，而不是
繼續在 `MeasureMapNode` 上打補丁。

---

## 1. 確定根因（用即時 instrumentation 直接量測，不是推測）

在 `NoDrumPhaseCarryNode.execute`（`module3_barstart_v2_bt.py:451`）跟
`FullSongBarStartLoopNode.execute`（同檔 `:3418`）暫時加了 debug 埋點
（用完已還原，不在目前的 diff 裡），對真實資料重新跑一次管線，抓到
完整的逐 tick 記錄：

```
iter=1 committed: 2→3 bars (0.0, 2.0, 3.702585)
iter=2,3: 卡住不動（3 bars，最後一個在 3.702585s）
iter=4: 連續卡 3 次，觸發第一次 recovery，用 provisional=[5.191043, 6.616259,
        8.041361, 9.836122, 11.359184] 補上 5 個小節（用的是真實 v1 拍點網格，
        數值精確——這 5 個時間點都是我們整個 Pass 194-198 系列一直在處理的
        同一批真實拍點，這次的 recovery 本身是正確、可信的）
iter=5,6,7: 卡在 8 bars（最後一個 11.359184s）不動
iter=7: 連續卡 3 次，第二次 recovery 嘗試，但這次 provisional=[]（空的）
        → stop_reason = "stalled_no_recovery"，永久放棄
```

同時記錄的 `NoDrumPhaseCarryNode` 內部狀態，7 次呼叫裡**`next_anchor`
從頭到尾都是同一個值 `12.376236`，`bar_duration` 全部是 `2.0`**：

```
{"previous": 11.359184, "next_anchor": 12.376236, "bar_duration": 2.0,
 "status": "NO_SPAN", "provisional_count": 0, "committed_len": 8, "anchors_len": 8}
```

### 1.1 根因 A：`tempo_bpm` / `bar_duration_sec` 全專案從來沒有被設定過

`bar_duration=2.0` 這個數字不是這首歌的真實拍距（這首歌是 ~164 BPM，
真實拍距 ~1.46 秒／小節，跟我們整個 Pass 194-198 系列一直在用的
`beat_sec≈0.365` 完全一致），**它是 `NoDrumPhaseCarryNode._bar_duration`
（`:594`）寫死的 fallback 值**：

```python
bpm = float(blackboard.get_val("tempo_bpm", 120.0))   # <- 120.0 fallback
beats_per_bar = int((blackboard.get_val("meter_profile", {}) or {}).get("beats_per_bar", 4))
return 60.0 / bpm * beats_per_bar   # 60/120*4 = 2.0，剛好對上觀察到的數字
```

全專案 grep 確認：

```
grep -rn 'set_val("tempo_bpm"' pgm_craft/   → 沒有任何結果
grep -rn 'set_val("bar_duration_sec"' pgm_craft/   → 沒有任何結果
```

**`tempo_bpm` 和 `bar_duration_sec` 這兩個被多個節點宣告為
`optional_keys` 依賴的黑板欄位，全專案沒有任何一個節點真正寫入過**——
`_bar_duration` 永遠拿到預設值 120 BPM，不管這首歌實際速度是多少。
這個 bug 平常被「有真實拍點網格資料時優先用網格」的邏輯（`_v1_grid_times_in_span`）
蓋掉，只有在網格資料在特定窄縫隙裡也拿不到東西時，才會真正跑到用
`bar_duration` 直接算的那條路徑，暴露出這個從來沒被抓到的 bug。

### 1.2 根因 B：`_next_anchor` 沒有檢查候選是否真的差整數個小節

`next_anchor=12.376236` 從 `lookahead_bar_candidates` 選出來
（`NoDrumPhaseCarryNode._next_anchor`，`:582`），選法是「信心最高、
同分取時間較晚」，**完全沒有檢查這個候選跟 `previous`（11.359184）
之間的間距是否構成合理的整數個小節**。

`11.359184` 到 `12.376236` 只差 **1.017052 秒**——不到 3 拍
（`1.017/0.365≈2.79` 拍），連一個小節的長度都不到，明顯不是下一個
真正的小節起點（真正的下一個小節，比對我們自己這個系列一直在用的
拍點資料，應該在 ~12.765s 附近，`11.359+4*0.365≈12.82`，相差不遠）。

這個候選是從 `LookaheadDrumAnchorSearchNode`（`:682`）產生的——它對
每個未來鼓組事件時間，套用一組位移 `[0.0, -0.5, 0.5, -1.0, 1.0]` 秒
產生候選（用意是處理「這個鼓點可能剛好是重音、也可能提前/延後半拍
到一拍」的情況），每個候選信心 `base_confidence - abs(offset)*0.08`。
**這個節點只看「哪個候選信心最高」，同樣沒有檢查候選是否構成合理的
小節間距**——如果掃到的某個鼓點剛好信心很高但其實不是重音（例如
只是一個普通鼓點或雜訊），就會被選中、把後面的推算邏輯卡死。

### 1.3 兩個根因疊加，缺一不可：只修一個不會通

在 `NoDrumPhaseCarryNode.execute`（`:501`）的 `CARRIED` 分支：

```python
current = previous + bar_duration        # 11.359 + 2.0 = 13.359
while current < next_anchor - self.tolerance_sec:   # 13.359 < 12.376-0.08=12.296？不成立
    provisional.append(round(current, 6))
    current += bar_duration
status = "CARRIED" if provisional else "NO_SPAN"    # 迴圈一次都沒進，NO_SPAN
```

用錯的 `bar_duration=2.0` 算，`13.359` 已經超過 `next_anchor`，迴圈
一次都不會執行，直接回報 `NO_SPAN`。**但就算把 `bar_duration` 修成
正確的 ~1.46，`previous+1.46=12.82` 一樣超過 `next_anchor=12.376`
（因為 12.376 這個候選本身間距就只有 1.017 秒，比任何合理的小節長度
都短）**——只修根因 A 不會讓這個卡點通過，因為根因 B 的壞候選本身
就擋在那裡。**兩個根因都要修**：根因 B 修好之後，`next_anchor` 會
正確地跳過 12.376236 這個壞候選、找到更遠處（~12.8s 附近）真正合理
的候選；根因 A 修好之後，`bar_duration` 才會用正確的拍距去判斷「多遠
算合理」，兩者互相依賴。

---

## 2. 修復規格（給 Codex 的明確指示）

### 2.1 根因 A：計算並設定真正的 `tempo_bpm`/`bar_duration_sec`

在 BarStart V2 的 tick 迴圈開始執行前（`FullSongBarStartLoopNode.execute`
一開始，或更早——只要保證在第一次 tick 之前執行過一次即可），從
`v1_reference_beat_grid`（或 blackboard 上既有的 `refined_beats`／`beats`，
跟 `pgm_craft/workflow/audio_nodes.py` 的 `MeasureMapNode._reconcile_close_downbeats`
算 `beat_sec` 用的是同一個資料來源）算出這首歌真實的拍距，寫入
`bar_duration_sec`（`= 4 * robust_median_beat_diff`）跟/或 `tempo_bpm`
（`= 60 / robust_median_beat_diff`），讓 `_bar_duration()` 的
`blackboard.get_val("bar_duration_sec")` 分支能拿到正確值，不再落到
120 BPM 的預設。

**穩健估計方式**：沿用這個系列已經驗證過的做法——對 `v1_reference_beat_grid`
（或等效的原始拍點陣列）取相鄰時間差，過濾掉 `<=0` 的異常值，取
median，不要用單一相鄰間距（容易被單一雜訊拍點污染）。

### 2.2 根因 B：`_next_anchor` 加上「是否構成合理小節間距」的檢查

`NoDrumPhaseCarryNode._next_anchor`（`:582`）選候選時，除了現有的
「信心、時間」排序，**加上一個過濾條件**：候選時間與 `previous` 的
差距，除以（修好根因 A 後的）`bar_duration`，應該落在「某個 >=1 的
整數附近」（容差比照這個系列已經驗證過的安全邊界——`Pass 197A` 用
過 `CONFLICT_DISTANCE_BEATS_MAX=3.0`拍當「太近」的安全邊界，這裡的
判斷方向相反（要排除「太近、構不成一個小節」的候選），建議：
`round((candidate_time - previous) / bar_duration) < 1` 時視為不合理，
排除這個候選，繼續看排序中的下一個候選；如果所有候選都不合理，
`next_anchor` 回傳 `None`（沿用既有的「找不到候選」語意，讓
`NoDrumPhaseCarryNode` 走無 lookahead 的 fallback 分支，而不是被一個
壞候選卡死）。

**同樣的檢查建議也加到 `LookaheadDrumAnchorSearchNode`**
（`module3_barstart_v2_bt.py:682`）本身，在信心排序之前先過濾掉跟
`committed_bar_starts` 最後一個時間點差距小於（修正後）`bar_duration`
的候選——這是更上游、更根本的位置，如果這裡先過濾乾淨，
`NoDrumPhaseCarryNode` 那邊的過濾就是雙重保險，不是唯一防線。

---

## 3. 安全機制（沿用整個系列的教訓）

1. **這兩個修正都要用真實資料重新驗證**，不能只看程式邏輯合理就
   相信——這個系列已經連續三次證明「看起來合理的門檻/邏輯，實際在
   長序列真實資料上會暴露沒預料到的邊界情況」（Pass 197 threshold
   bug、Pass 198B 級聯 bug，現在這是第三次，只是這次是在動工前就
   用即時 instrumentation 抓到，比前兩次先斬後奏好）。
2. **修完後要確認 BarStart V2 真的能跑完整首歌不再卡死**
   （`full_song_loop_report.status` 應該是 `COMPLETED`、
   `stop_reason` 應該是 `reached_audio_duration`、
   `unresolved_bar_span_count` 應該趨近 0），而不是只解決這一個
   卡點又在別處卡住——**同樣的兩個根因（tempo_bpm 沒設定、候選沒
   驗證間距）很可能在全曲其他地方也會發作，不是只有 10.4 秒這一處**，
   修完後要看全曲有沒有其他新的卡點出現，不能只驗證這一個位置。
3. **如果 BarStart V2 這次真的跑完全曲、`promotion_gate.adoptable=true`
   而被拿去取代舊方法**，一定要重新做這個系列一直在做的「用鼓組
   onset 量化核對 click 準不準」驗證（`scratch/analyze_pass19{6,7,8}_click_accuracy.py`
   系列腳本可以直接沿用），而且**一定要請使用者實際聽過**——不能只
   看 `unresolved_bar_span_count=0` 這個數字就當作修好了，這正是
   Pass 193 教訓的核心。

---

## 4. 驗證計畫

1. **既有測試全跑一次**：BarStart V2 應該已經有自己的單元測試
   （Pass 105-171 期間陸續建立），修改後要跑過，不能破壞既有行為。
2. **合成測試（根因 A）**：驗證 `bar_duration_sec`/`tempo_bpm` 在
   給定已知拍點網格時，算出來的值符合預期（例如給一組間距均勻
   0.365s 的合成拍點，預期算出 `bar_duration_sec≈1.46`，不是
   120 BPM 的預設 2.0）。
3. **合成測試（根因 B）**：重現本任務書第 1.2 節的真實案例模式
   （`previous=11.359184`、有一個過近的候選 `12.376236` 跟一個
   合理的候選 `~12.8`），驗證 `_next_anchor` 正確跳過過近候選、
   選中合理候選。
4. **真實資料完整驗證**：重跑
   `scratch/run_pass198_default_pipeline_reverify.py`（或衍生新
   腳本），確認 `barstart_v2_report.full_song_loop_report.status`
   變成 `COMPLETED`、`unresolved_bar_span_count` 趨近 0，且**逐一
   核對全曲有沒有出現新的卡點**（不是只看第 10.4 秒這一處）。
5. **如果 BarStart V2 真的被 promote 取代舊方法**：用 onset 量化
   核對 click 準確度，並整理清楚的前後對照供使用者實際試聽確認。

---

## 5. 追記：Codex 實作後獨立驗證，發現「修好卡死」不等於「修好」

Codex 依照第 2 節規格實作完成（commit 前），真實資料回驗：
`committed_bar_count=124`、`stop_reason=reached_audio_duration`、
`unresolved_span_count=0`、`promotion_gate.adoptable=true`，已經被
自動採用取代舊方法。使用者實際聽了輸出的
`barstart_v2_mix_with_click.wav` 後回報：**「V2 模型很穩定，但就是
完全沒有照著音樂做即時調整，一直穩定的進行」**。

獨立驗證後確認這個聽感是對的，而且比聽起來嚴重：

### 5.1 `stall_trace` 顯示 124 個小節裡 106 個（85%）不是真正的證據判斷

```python
Counter({'CARRIED_V1_GRID': 291, 'CARRIED_NEXT_ANCHOR_FALLBACK': 18,
         'CARRIED': 3, 'CARRIED_FALLBACK_V1_GRID': 3, 'CARRIED_FALLBACK_NO_LOOKAHEAD': 3})
# stall_recoveries: 106 / committed_bar_count: 124 / iterations: 319
```

**只有 18 個小節是 `BarStartCandidateCommitNode` 真的靠多來源證據
（鼓組/貝斯/和絃）獨立判斷出來的，其餘 106 個（85%）都是連續卡住
3 次之後，直接把 `v1_reference_beat_grid`（也就是我們整個 Pass
194-198 系列一直在處理的同一份 Stage 3 拍點資料）複製過來充數**。
這正是為什麼使用者覺得「聽起來很穩定但沒有跟著音樂走」——它幾乎
不是在即時聽音樂做判斷，是在抄同一份舊資料，看起來自洽是因為抄的
東西本來就是同一個來源，不是因為 V2 自己的證據邏輯真的運作起來。

### 5.2 修復本身破壞了一個既有的安全測試

`tests/test_module3_bt.py::test_module3_barstart_v2_merge_node_compares_but_does_not_promote_when_v2_incomplete`
**現在會失敗**：這個測試給完全靜音的音檔（只提供合成的 `beats`
陣列，沒有真實鼓/貝斯/和絃證據），驗證「V2 應該老實回報解不出來、
不能冒充完成」（`barstart_v2_promoted_to_main is False`）。修復後
這個測試斷言 `True is False` 失敗——**因為新的 `_initialize_timing`
會從合成的 `beats` 陣列算出 `bar_duration_sec`，讓 `CARRIED_V1_GRID`
分支足以「走完」整個靜音音檔、回報 `unresolved_span_count=0`，即使
完全沒有真實音訊證據**。這證明第 5.1 節的問題不只是「這首歌剛好
這樣」，是修復本身讓「完成」這個判斷標準變得可以被純粹的資料延續
騙過去，不需要真正的證據。

### 5.3 品質分數不升反降，但自動採用邏輯完全忽略分數

```python
quality_comparison: {'original_score': 88.47, 'barstart_v2_score': 58.15, 'v2_scores_higher': False}
```

分數比上一輪（62.2，見第 0 節）還低、遠低於舊方法（88.47），但因為
`barstart_v2_report.notes` 記載的政策是「只要沒有 unresolved span
就直接採用，不再比較分數」，這次還是被自動判定
`promotion_gate.adoptable=true` 而上線——**這個政策本身現在看來有
問題：分數大幅下降理應是一個警訊，不該被完全忽略**。

### 5.4 結論與建議：這次不算修好，先不要採用 V2 的結果

修復本身（第 2 節規格：算對 `bar_duration_sec`、過濾不合理候選）
**方向沒有錯**，也確實解決了原本卡死的問題，但暴露出更根本的缺口：
**`BarStartCandidateCommitNode` 的多來源證據判斷，對這首歌絕大多數
小節根本達不到 0.7 的 commit 門檻**（`default_threshold=0.7`，見
`:962-973`），導致幾乎每個 tick 都卡住 3 次、幾乎全靠複製 v1 網格
撐過去。真正該追的問題是**「為什麼獨立證據融合幾乎每次都不夠格」**，
不是「怎麼讓卡住後的恢復機制更寬鬆」——第 2 節的修復把後者做得太
成功，反而讓前者的缺陷被隱藏起來（`unresolved_span_count=0` 看起來
很漂亮，實際上是用複製舊資料換來的）。

**建議**：
1. 先不要讓這次的 V2 結果保持 promoted 狀態——先退回使用舊方法
   （Pass 197 + 198 階段 A 的結果：114 小節、10 不規則、已知每個
   不規則小節的具體原因，是誠實、已驗證的結果）。
2. 修好第 5.2 節破壞的安全測試（不能讓完全沒有真實證據的靜音音檔
   被判定為「完成」）。
3. `promotion_gate` 的自動採用邏輯應該把品質分數納入考量，不能只看
   `unresolved_span_count==0`；至少當分數明顯低於舊方法時應該拒絕
   自動採用、交給人工確認。
4. 如果還要繼續往 BarStart V2 這條路走，核心工作是研究
   `DrumEvidenceBarSearchNode`/`DrumBassEvidenceBarSearchNode`/
   `ChordTrackPKNode` 等證據來源，對這首歌為什麼絕大多數小節都湊
   不到 0.7 分——這是比第 2 節大很多的題目（可能是信心公式本身
   偏低、可能是證據來源彼此沒有適當加成、可能是這首歌的音色特性
   不利於這套證據邏輯），需要另開任務書，不建議直接讓 Codex 憑
   猜測調參數（這個系列已經連續好幾次證明調參數不看真實資料驗證
   會出事）。
