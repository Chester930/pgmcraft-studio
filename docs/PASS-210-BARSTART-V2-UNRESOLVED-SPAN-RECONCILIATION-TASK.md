# Pass 210 任務書：`unresolved_bar_span_count` 該算「歷史失敗次數」還是「最終序列真的還缺幾段」

**狀態**：根因已用真實資料精確定位，第 1 節是修復型（機械式、可以
直接動手改），第 2 節是「先確認事實，再決定要不要處理」——先用
既有工具做一次真實資料核對，不要假設。可轉交 Codex CLI 依序執行。

---

## 0. 背景

Pass 209（`docs/PASS-209-BARSTART-V2-PROBE-WINDOW-PAST-DURATION-TASK.md`，
commit `7724dcd`）已由 Codex 修好探測視窗滑出全曲長度的問題，Claude
已獨立覆核確認（32 測試重跑通過、JSON 報告數字核對相符、親自重算
116 個小節的間距分布，確認近乎重複小節跟大跳空隙已經**完全歸零**，
V2 分數 65.53→73.14）。使用者聽過後回報「寫下個任務書」，繼續處理
剩下卡住 promotion gate 的問題。

目前 `unresolved_bar_span_count=4`。用 Pass 206 的逐 tick trace 逐筆
核對這 4 個，發現其中**只有 1 個是真的、最終網格裡還缺的段落**：

```
tick 49（window 100.333424-102.333424s）：confidence_below_threshold
  ——這次探測失敗，但最終 committed_bar_starts 裡 100.3057s 到
  101.8487s 之間間距 1.543 秒（正常小節長度），代表後來別的 tick
  已經把這裡補上了，只是這次失敗的紀錄從沒被清掉。
tick 61（window 117.66712-119.66712s）：confidence_below_threshold
  ——同上，最終網格裡 117.2787s 到 118.8217s 間距 1.543 秒，也是
  後來被補上、舊紀錄沒清掉。
tick 99（window 171.736837-173.736837s）：no_candidates /
  all_candidates_already_committed
  ——這次唯一的候選本身就是已經 commit 過的重複項，代表「這裡沒有
  新的小節要加」，根本不是「找不到證據」，語意上不該算未解析。
tick 100（window 173.736837-176.736837s）：no_candidates /
  no_upstream_candidates
  ——六個證據來源（drum/drum_bass/chord/melody/v1_grid/beat_this）
  全部回報零候選。這是**唯一一個最終網格裡真的沒有任何小節、而且
  當下探測也真的什麼都找不到的段落**：最後一個 committed 小節在
  172.6909s，全曲實際長度 176.6458s，中間約 3.95 秒完全空白。
```

---

## 1. 修復型：`unresolved_bar_spans` 要能反映「最終網格是否真的還缺」，不是「歷史上失敗過幾次」

### 1.1 要修什麼

**(a) `all_candidates_already_committed` 分類的 tick 不應該被記錄成
unresolved span。**

在 `BarStartCandidateCommitNode.execute`（`pgm_craft/workflow/module3_barstart_v2_bt.py`，
`no_candidates`/`confidence_below_threshold` 兩個分支都會 append 進
`unresolved_bar_spans` 的地方，約 1032-1050 行附近），`diagnostic_classification`
（Pass 206 加的，`_classify_decision` 方法）已經能分辨
`all_candidates_already_committed`（唯一候選是重複項，沒有新東西
要加）跟真正的 `no_upstream_candidates`/`best_candidate_below_threshold`
（真的沒找到或信心不夠）。**只有後兩種才是真正的「未解析」，前者
語意上是「這裡不需要新小節」，不應該進 `unresolved_bar_spans`。**

**(b) `confidence_below_threshold` 造成的 unresolved span，如果之後
被鄰近的成功 commit 覆蓋掉了，要能被回收/清除。**

`FullSongBarStartLoopNode.execute` 收工前（`final = self._normalize(...)`
那一行之後，加在回傳 `loop_report` 之前），對這時候還留著的
`unresolved_bar_spans`，逐一檢查：這個 span 的時間範圍，在**最終**
`committed_bar_starts` 裡，是不是已經被前後兩個相鄰小節、以接近
`expected_bar_duration`（可以重用 `_expected_bar_duration`/
`_phase_consistency_score` 已有的小節倍數殘差邏輯，跟 Pass 205/208
用的是同一套工具）的間距覆蓋掉了。如果是，代表這個 span 事後已經
被填上了，從 `unresolved_bar_spans` 移除；如果不是（前後間距明顯
大於一個正常小節長度，或這個 span 本來就在全曲結尾之後沒有任何後續
小節），保留。

**這兩個改動都是機械式的、根因已完全確認，不需要再重新診斷。**

### 1.2 明確要求

1. 修完後，用 `scratch/run_pass207_clean_production_verify.py` 重新
   驗證，`unresolved_bar_span_count` 應該從 4 降到 **1**（只剩 tick
   100 那個真正的尾聲缺口）——如果數字對不上，先確認是不是漏掉某個
   分類，不要為了湊出「1」去调整判斷邏輯的容差。
2. **不要動到 `confidence_below_threshold`/`no_upstream_candidates`
   本身的判斷邏輯**——這次只處理「事後回收」跟「語意上不該算未解析
   的分類要排除」，不要碰信心門檻或候選篩選的任何參數。
3. 保留 `unresolved_bar_spans` 完整歷史紀錄的另一份副本（例如寫進
   `full_song_loop_report` 底下一個新欄位，如
   `all_probe_failures_ever`），方便之後除錯回溯——只是不要讓這份
   歷史紀錄直接拿去餵 promotion gate 的判斷。

### 1.3 測試要求

新增至少 3 個測試（`tests/test_sdd_pass210.py`）：

1. `all_candidates_already_committed` 分類的 tick 不會被加進
   `unresolved_bar_spans`。
2. 一個 `confidence_below_threshold` 造成的 span，如果最終
   `committed_bar_starts` 已經在附近有正常間距的小節，驗證這個 span
   會從 `unresolved_bar_spans` 移除。
3. 一個真正沒被填上（前後間距遠大於一個小節，或已經是全曲結尾之後
   沒有任何後續小節）的 span，驗證仍然保留在 `unresolved_bar_spans`
   裡，不會被誤清掉。

```
C:/Python313/python.exe -m pytest tests/test_sdd_pass210.py tests/test_sdd_pass209.py tests/test_sdd_pass208.py tests/test_sdd_pass206.py tests/test_sdd_pass205.py tests/test_sdd_pass202.py tests/test_sdd_pass201.py tests/test_module3_bt.py -q
```

---

## 2. 先查清楚事實：尾聲 172.69s-176.65s 這段音訊，到底有沒有可辨識的小節脈動？

**不要直接動手處理這個缺口，先確認它是「真的沒有節奏內容」還是
「證據判斷邏輯的盲點」，兩者的正確處理方式完全不同。**

### 2.1 要做的事

1. 用這個系列已經驗證過的方法（`SteadyPercussionCountAnchorNode`
   自己的 `_detect_onsets`/`_find_steady_runs` 邏輯，或參考
   `scratch/verify_pass198_promotions_against_steady_runs.py` 的既有
   範本），對 172.69s-176.65s 這段音訊獨立跑一次 onset 偵測，不透過
   BarStart V2 的證據鏈，直接看這段原始音訊有沒有規律的鼓點/貝斯
   節奏。
2. 對照現有的**舊方法（`MeasureMapNode`）在同一段時間怎麼處理**——
   舊方法的 `measure_map.json`（`outputs/pass198_default_pipeline_reverify/.../reports/measure_map.json`
   或黃金基準 `d:\Users\666\Music\2\...\reports\measure_map.json`）
   在 172.69s 之後到全曲結尾之間，有沒有標出小節/downbeat？如果有，
   那些時間點附近有沒有對應得上的真實 onset？
3. 對照歌曲的黃金基準：黃金基準全曲長度是 175.693469 秒
   （`GOLDEN_WORLD_IS_MINE_STATS`），比這次量到的 `duration_cap_sec`
   176.6458 秒還短——這個約 1 秒的差異本身要先搞清楚是怎麼回事（是
   音檔本身長度不同、還是靜音尾段被算進去、或黃金基準本來就沒把
   最後的淡出算進最後一個小節）。

### 2.2 依查出來的結果決定下一步（不在本任務書內直接實作）

- **如果這段真的是無節奏內容**（純淡出/靜音/殘響尾巴，沒有真實
  onset）：BarStart V2 在這裡保持「不 commit」是正確行為，不應該
  硬湊一個假的小節出來。這種情況下，promotion gate 的
  `UNRESOLVED_BAR_SPANS_PRESENT` blocker 邏輯本身可能需要調整成
  「允許全曲結尾之後、找不到任何真實 onset 佐證的殘留段落例外」，
  但**這是一個需要使用者/Claude 明確決定的政策問題，不是 Codex
  可以自己判斷後直接動手改的**，查完事實回報就好，等下一份任務書
  再處理這個決定。
- **如果這段其實有規律的鼓點/貝斯節奏，只是六個證據來源都沒抓到**：
  這是一個新的、獨立的證據缺口，需要另開任務書深入調查是哪個具體
  環節漏掉了（類似 Pass 203 最初的調查方法），不要在這份任務書裡
  順手猜一個修法上去。

### 2.3 交付物

一份簡短的事實報告（可以直接寫進 `docs/BT-BUILD-PROGRESS.md` 的
Pass 210 條目，不需要獨立文件），至少要回答：
1. 172.69s-176.65s 這段有沒有偵測到規律 onset？
2. 舊方法在這段做了什麼？
3. 176.6458s（`duration_cap_sec`）跟黃金基準 175.693469s 的落差是
   什麼原因造成的？

---

## 3. 完成後

1. 更新 `docs/BT-BUILD-PROGRESS.md`，新增 Pass 210 條目，記錄第 1
   節的修法跟驗證結果、第 2 節查到的事實（不需要在這個條目裡下
   最終決定，如實記錄查到什麼就好）。
2. Commit + push 到 `origin/worktree-pass171-multi-variant-harness`，
   commit message 遵照這個系列的慣例（`fix(pass210): ...`）。
3. 如果第 2 節查出來是「真的沒有節奏內容」，在條目最後明確建議：
   下一步需要使用者/Claude 決定 promotion gate 的
   `UNRESOLVED_BAR_SPANS_PRESENT` 判斷邏輯要不要為這種情況放寬，
   附上第 2 節查到的具體證據（onset 偵測結果、舊方法的處理方式），
   讓決策有真實資料可以依據，不要留白等下一輪才查。
