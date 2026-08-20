# Pass 208 任務書：修好乾淨全曲驗證後暴露的兩個下游網格瑕疵

**狀態**：第 1 節（近乎重複小節/大跳空隙）是**診斷型任務**——精確的
症狀跟數據已經用真實資料量測出來，但還沒定位到是哪個節點造成的，
**不要用猜的直接動手改**，先加暫時 instrumentation 找到真正的節點，
比照 Pass 198B/199/203 已經驗證過的方法。第 2 節（`carried_bar_ratio`
閘門盲點）根因已完全確認，**是修復型任務**，可以直接動手改。可轉交
Codex CLI 依序執行。

---

## 0. 背景

Pass 205（`docs/PASS-203-EVIDENCE-FUSION-THRESHOLD-DIAGNOSIS-TASK.md`
第 6 節、`docs/PASS-205-BARSTART-V2-QUALITY-REGRESSION-GATE-TASK.md`）
已由 Codex 修好並驗證——`quality_regression` 閘門不再誤判合理的多
小節跳躍。但 Codex 用來驗證的那次全曲跑法（透過
`scratch/run_pass203_evidence_fusion_diagnosis.py`），這個腳本會把
`FullSongBarStartLoopNode.__init__` monkeypatch 成 `stall_limit=10000`
——這個 monkeypatch 對整個 Python 行程生效，**連帶影響了同一行程裡
「真正的」`_run_barstart_v2_comparison` 呼叫**，導致回報的
「V2 分數 37.15、404 個未解析區間」這組數字裡，有 400 個其實是搜尋
視窗滑到超出全曲 176.65 秒實際長度之後的無效 tick（這是 Pass 203
任務書第 5.3 節就記錄過的既有邏輯缺口），不是真的證據缺口。

**已用 `scratch/run_pass207_clean_production_verify.py`（不套用任何
monkeypatch，`stall_limit` 用正式管線預設值 3）重新驗證過**，乾淨
數據如下：

- Loop 本身表現很好：104 次 tick 裡 96 次成功 commit，只有 8 個真的
  未解析（`unresolved_span_count=8`，不是 404）、`carried_bar_ratio=0.02`
  （2%，遠低於 0.5 門檻）。
- 但最終匯出的 `committed_bar_starts`（118 個小節起點，經過
  `BarGridContinuityRepairNode`/`BarStartTempoSmoothingNode` 等下游
  節點處理後）本身仍然很不規則：**BPM 跳動次數 50/117 段（43%）**，
  遠高於現行舊方法（`MeasureMapNode`）的 0 次。
- `barstart_v2_score` 依然只有 37.15（舊方法 88.47），現在確認這不是
  因為 loop 沒跑完，是因為**下游修復/平滑節點鏈本身在製造新的不規則
  間距**——這是這次要修的問題。

---

## 1. 診斷型：定位是哪個下游節點在製造近乎重複的小節跟大跳空隙

### 1.1 已用真實資料確認的具體症狀

用 `scratch/run_pass207_clean_production_verify.py` 的輸出
（`outputs/pass207_clean_production_verify/.../reports/module3_beat_click_report.json`
的 `barstart_v2_report.committed_bar_starts`，118 個小節起點）逐段
量測，發現兩類問題：

**(a) 近乎重複的小節**（間距遠小於預期小節長度 ~1.4529 秒）：

```
索引 83：126.536058 → 126.5598      間距 0.023742 秒（換算 BPM 破萬）
索引 15：24.734332 → 24.947929      間距 0.213597 秒
索引 35/63/71/77/79/84/88/92/96/110：間距固定為 0.237339... 秒（同一數值
                                     在全曲重複出現超過 10 次，不是隨機
                                     雜訊，是某個節點的確定性行為）
索引 107/109：間距 0.498421/0.498422 秒
```

**(b) 遠超一個小節長度的大跳空隙**：

```
索引 112：169.296179 → 177.016678   間距 7.720499 秒（~5.3 個小節長）
索引 105：158.985900 → 165.162300   間距 6.176400 秒（~4.25 個小節長）
索引 64/72：間距 3.301797 秒（~2.27 個小節長）
索引 68/76/81/95：間距 3.088200 秒（~2.13 個小節長）
索引 80/86/89/93：間距 2.850860/2.850861 秒（~1.96 個小節長）
```

### 1.2 已排除、但還沒定位到確切節點

比對 loop 自己收工時的清單（`full_song_loop_report.loop_committed_bar_starts`，
99 個小節起點）跟最終匯出清單（118 個），**用四捨五入到毫秒比對後，
有 83 個最終小節起點在 loop 自己的清單裡找不到完全對應值**——遠多於
`BarGridContinuityRepairNode` 自己回報的「補 19 個小節」，代表下游
不只是「插入新小節」，還有大量既有小節的時間被**微調過**（平滑/相位
修正），不是單純插入。這代表問題不能只怪
`BarGridContinuityRepairNode` 一個節點，需要實際 instrumentation 才能
分清楚。

真正介於 loop 收工跟最終匯出之間的節點鏈（依執行順序，讀
`pgm_craft/workflow/module3_barstart_v2_bt.py`
`FullSongBarStartLoopNode.execute`（約 3808-3824 行）跟
`pgm_craft/workflow/module3_bt.py` `_run_barstart_v2_comparison`
的 `v2_core`（約 964-984 行）確認）：

```
FullSongBarStartLoopNode 自己的後處理（loop 收工前）：
  1. TwoWayAnchorBacktraceNode      （Pass 168：雙向錨點反推）
  2. GroovePatternPhaseDecoderNode  （Pass 169：鼓型拍位解碼）
  3. BarGridSanityPrunerNode        （Pass 170：過濾 < 0.6×median 的 Ghost 小節）
──────（此時 = loop_committed_bar_starts，99 個小節）──────
_run_barstart_v2_comparison 的 v2_core（loop 之後才跑）：
  4. BarGridContinuityRepairNode    （插入跳過的小節、移除近重複、抑制震盪）
  5. BarStartTempoSmoothingNode ×2  （局部中位數平滑，跑兩次）
  6. MeterAwareBeatGridNode         （幾何細分成拍）
  7. KickBassDownbeatVerifierNode   （修正強拍反相）
──────（此時 = 最終 committed_bar_starts，118 個小節）──────
```

### 1.3 要做的診斷

在 `_run_barstart_v2_comparison`（`module3_bt.py:964`）跟
`FullSongBarStartLoopNode.execute` 的後處理段落，加暫時的 debug
instrumentation（用完要還原，比照 Pass 198B/199/203 的既有做法），在
上述 7 個節點**各自執行前後**都快照一次 `committed_bar_starts`
（連同節點名稱、小節數量），輸出成結構化 trace（比照
`scratch/debug_pass203_evidence_trace.jsonl` 的模式）。

用 `scratch/run_pass207_clean_production_verify.py` 當基礎（stems 已
有快取，`outputs/pass203_evidence_fusion_diagnosis/.../stems`，不需要
重跑 demucs）重新跑一次，加上這個 instrumentation，然後：

1. 對第 1.1 節列出的每一個「近乎重複」跟「大跳空隙」的具體索引/時間
   點，回答：是哪一個節點的執行前後快照，第一次讓這個間距出現的？
2. 特別注意 0.237339... 秒這個在全曲重複出現超過 10 次的固定數值——
   如果同一個節點的同一段邏輯在很多地方都產生完全相同的殘餘間距，
   很可能是 `BarGridContinuityRepairNode` 用「固定 median_interval
   步長插入」導致的餘數效應（讀該節點 `pgm_craft/workflow/module3_barstart_v2_bt.py:2753-2770`
   的 Pass A 迴圈：插入邏輯用 `median_interval` 的整數倍步長填補缺口，
   但插入完最後一步到原始候選 `t` 之間的餘數間距完全沒有被檢查是否
   合理，也沒有機會被同一輪的「近重複」判斷抓到——因為那個判斷只比較
   *下一個原始候選* 跟 *目前 repaired 清單最後一個元素*，插入產生的
   中繼小節從來沒被拿來跟 `t` 的間距做過品質檢查）——**這是一個合理
   的假設方向，但要先用實際 instrumentation 驗證，不要沒驗證就當
   結論直接動手改**。
3. 對大跳空隙（尤其是 index 105/112 這兩個 6-7.7 秒的），同樣的問題：
   是 loop 自己收工時就已經有這個大跳（代表 99 個小節裡本來就有這個
   空隙，只是小於 `unresolved_span_count=8` 的判定標準？），還是
   `BarGridSanityPrunerNode` 把中間某個小節當 Ghost 殘片移除掉之後
   才產生的？

### 1.4 修復方向（診斷完成後才能定案，這裡只列可能方向供參考）

- 如果確認是 `BarGridContinuityRepairNode` 的插入餘數問題：插入時應該
  用「均分整段 gap」而不是「固定 median_interval 步長」（例如
  `steps` 個小節應該平均分配 `gap` 的長度，讓每一段的間距都接近
  `gap/steps`，而不是前面幾段用 `median_interval`、最後一段用剩下的
  任意餘數）。
- 如果是 `BarStartTempoSmoothingNode` 的局部平滑造成漂移：檢查是否
  有一個既有的評論提到的保護機制（「A bar-start with a real kick/snare
  hit nearby is never moved」）在這個具體案例失效。
- **不要在診斷完成前就假設是哪一個，先用 instrumentation 資料決定**。

---

## 2. 修復型：`carried_bar_ratio` 閘門沒有算到 `BarGridContinuityRepairNode` 的插入

### 2.1 根因（已確認）

Pass 201（`evaluate_barstart_v2_completeness`）引入的
`carried_bar_ratio` 閘門，只統計 `FullSongBarStartLoopNode` 自己的
stall-recovery fallback carry 機制（`carried_bar_count`，這次乾淨跑法
只有 2 個，比例 2%）。但 `BarGridContinuityRepairNode` 在 loop 收工
**之後**另外插入的小節（這次乾淨跑法是 19 個，佔最終 118 個小節的
16.1%）完全沒有被這個閘門看見——`bar_grid_repair_report`（記錄
`inserted_bar_count`）目前只寫回**隔離的 v2_blackboard 副本**，從沒
被 `_run_barstart_v2_comparison` 的回傳值收進去，`promotion_gate`/
`quality_comparison` 完全看不到這個數字。

這次乾淨跑法的 16.1% 還在 0.5 門檻以下，不影響目前「不採用」的結論，
但**這個閘門本身有盲點**：如果換一首證據更稀疏的歌，
`BarGridContinuityRepairNode` 插入比例可能遠高於 16%，卻完全不會被
`carried_bar_ratio` 閘門攔下來，形成第二種「看起來完成、其實大半是
插值湊出來」的風險（跟 Pass 199 的 85% fallback carry 是同一類問題，
只是換了一個節點在做）。

### 2.2 要修什麼

1. `_run_barstart_v2_comparison`（`module3_bt.py:906`）的回傳 dict
   要把 `v2_blackboard.get_val("bar_grid_repair_report", {})` 也收
   進去（跟現有的 `full_song_loop_report`/`state_consistency` 同一
   層級），讓下游看得到。
2. `evaluate_barstart_v2_completeness` 或 promotion gate 的計算，要把
   `bar_grid_repair_report.inserted_bar_count` 併入「非真實證據小節」
   的統計——可以直接擴充現有的 `carried_bar_ratio` 定義（分子加上
   `inserted_bar_count`），或者新增一個獨立的
   `repaired_bar_ratio`/`non_evidence_bar_ratio` 欄位，跟
   `carried_bar_ratio` 一樣套用同一個 0.5 門檻邏輯（哪一種做法比較
   合理，由 Codex 判斷，但兩者都要能在 promotion gate 的
   `blockers`/`unresolved` 訊息裡清楚反映出「這個小節數字裡有多少比例
   是插值出來的，不是真的證據判斷」）。
3. `Module3BarStartV2SummaryNode` 已經有 `bar_grid_repair_report` 這個
   required_keys/output（前一輪 Pass 206 加的，`module3_barstart_v2_bt.py:3283-3330`
   附近），但那是給 `Module3BarStartV2SummaryNode` 自己內部流程用的、
   跟 `_run_barstart_v2_comparison`（AB 比較用的隔離副本）是兩條不同
   路徑，**這次要修的是 `_run_barstart_v2_comparison` 這條路徑**，不要
   搞混。

### 2.3 測試要求

新增至少一個測試（`tests/test_sdd_pass208.py`），驗證：
`bar_grid_repair_report.inserted_bar_count` 顯著（例如超過某個小比例）
時，即使 `carried_bar_ratio`（loop 自己的 fallback carry）低於門檻，
擴充後的閘門邏輯仍然要能正確反映「這批小節有相當比例是插值」，不能
讓 promotion gate 誤以為完全是真實證據判斷出來的。

---

## 3. 驗證方式

用 `scratch/run_pass207_clean_production_verify.py`（stems 已有快取，
不需要重跑 demucs，一次約 13 分鐘）重新驗證：

1. 第 1 節修好後，重新量測 118 個小節的間距分布，確認 BPM 跳動次數
   （目前 50/117，43%）有明顯下降，近乎重複的小節（間距 < 0.5 秒）
   消失。
2. 第 2 節修好後，確認 `promotion_gate` 的回報訊息能正確反映
   `BarGridContinuityRepairNode` 插入比例，不再是完全看不見的盲點。
3. 兩者都修好後，重新比較 `barstart_v2_score` 對 `original_score`
   （88.47）的差距是否明顯縮小——**如果修完這兩個問題分數還是遠低於
   88.47，要誠實記錄還缺什麼，不要為了讓數字好看而放寬評分標準**。
4. 執行既有測試套件確認沒有破壞任何東西：
   ```
   C:/Python313/python.exe -m pytest tests/test_sdd_pass205.py tests/test_sdd_pass206.py tests/test_sdd_pass208.py tests/test_sdd_pass202.py tests/test_sdd_pass201.py tests/test_module3_bt.py -q
   ```

---

## 4. 完成後

1. 更新 `docs/BT-BUILD-PROGRESS.md`，新增 Pass 208 條目，記錄第 1 節
   最終定位到的節點、根因、修法，跟第 2 節的閘門擴充內容。
2. **修好後才能生成新的 click 音檔給使用者聽**——目前已經生成過的
   幾個 click 音檔（`pass203_evidence_fusion_diagnosis_fullsong` 跟
   `pass207_clean_production_verify` 兩個目錄下的）都還不是修好後的
   版本，不要拿舊的去給使用者聽，避免造成誤判。
3. Commit + push 到 `origin/worktree-pass171-multi-variant-harness`，
   commit message 遵照這個系列的慣例（`fix(pass208): ...`）。
