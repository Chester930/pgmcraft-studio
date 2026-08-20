# Pass 211 任務書：全曲尾聲（單側參考）用「往前推估小節數＋均分補齊」處理

**狀態**：這是使用者明確下達的政策決定（不是 Claude/Codex 自行判斷），
根因跟既有可重用機制都已定位，屬於修復/擴充型任務，可轉交 Codex CLI
直接執行。

---

## 0. 背景

Pass 210（`docs/PASS-210-BARSTART-V2-UNRESOLVED-SPAN-RECONCILIATION-TASK.md`，
commit `1274205`）已把 `unresolved_bar_span_count` 從 4 修正到 **1**
（Claude 已獨立覆核：36 測試重跑通過、JSON 報告數字核對相符）。剩下
唯一的 blocker 是全曲尾聲 **172.6909s-176.6458s**（約 3.95 秒）完全
沒有 commit 任何小節——Pass 210 第 2 節已用
`SteadyPercussionCountAnchorNode` 的既有 onset 偵測方法查證：這段
有零散 onset（kick 37、snare 13、hi-hat 26、whole drums 17），但四條
stem 都沒有偵測到連續穩定拍脈，不足以用現有的「找到一個高信心候選」
邏輯直接 commit。

使用者看過這個事實後，明確下達政策：**任何階段只要證據不足，就用
「往前參考＋往後參考、決定小節數、然後均分補齊」處理**。這正好對應
到 codebase 裡已經存在、但目前只用在「有前後兩端可以對齊」情境的
機制：

- `InterveningBarCountEstimatorNode`（`module3_barstart_v2_bt.py:731`）：
  給定 `reliable_bar_anchors`（往前參考的最後一個錨點）跟
  `lookahead_bar_candidates`（往後參考的下一個錨點），估計中間該有
  幾個小節（N-1/N/N+1 探索，取跟兩端距離誤差最小的那個）。
- `BidirectionalBarAlignmentNode`（`module3_barstart_v2_bt.py:794`）：
  用估出來的小節數做前向/後向投影，驗證相位誤差在容差內才真的產生
  候選、均勻分佈在兩個錨點之間。

**這兩個節點的問題是：都需要 `next_item`（往後參考的下一個錨點）
才能運作**——全曲尾聲**沒有「下一個錨點」**（已經是全曲結尾，沒有
後續小節），所以這套「雙向參考」機制結構上完全用不上，這就是 Pass
210 卡住的根本原因。`BarGridContinuityRepairNode`（Pass 208 已處理過
的下游插值節點）也是同樣的限制——它只處理「兩個已知小節之間的
gap」，沒有處理「最後一個小節之後、到全曲結尾之間」這種只有單側
參考的情況。

---

## 1. 要做什麼：單側參考版本的「推估小節數＋均分補齊」

### 1.1 設計方向

新增一個節點（或擴充 `BarGridContinuityRepairNode`，由 Codex 判斷
哪種比較乾淨），在全曲 loop 收工、且最後一個 committed 小節跟
`duration_cap` 之間有明顯落差時：

1. **往前參考**：用最近幾個已 commit 小節的間距，估計目前的
   `expected_bar_duration`（可以直接重用
   `BarStartCandidateCommitNode._expected_bar_duration`，或用最後
   N 個小節間距的中位數——由 Codex 判斷哪個在尾聲這種可能有
   ritardando/漸慢的情境下更穩健，兩者都要在任務書完成後的報告裡
   說明選了哪個、為什麼）。
2. **沒有往後參考**：`duration_cap`（`NoDrumPhaseCarryNode._audio_duration_cap`
   算出來的全曲實際長度）就是唯一的「終點」，取代原本雙向機制裡
   「下一個錨點」的角色。
3. **決定小節數**：`remaining = duration_cap - last_committed`，
   `count = max(1, round(remaining / expected_bar_duration))`——**不要
   無條件複製 `InterveningBarCountEstimatorNode` 的 N-1/N/N+1 探索**
   （那個機制原本是拿「跟下一個錨點的距離誤差」當篩選依據，尾聲沒有
   下一個錨點可以比對誤差，直接用 `round()` 最接近整數小節數即可）。
4. **均分補齊**：`count` 個小節平均分佈在 `last_committed` 到
   `duration_cap` 之間（`step = remaining / count`），不是用固定的
   `expected_bar_duration` 步長往前放（這正是 Pass 208 診斷出
   `BarGridContinuityRepairNode` 用固定步長插入、最後一段留下不合理
   餘數間距的同一種錯誤，這次不要重蹈覆轍——**均分**指的是把整段
   `remaining` 除以 `count`，每一段長度相等，不是每段都用
   `expected_bar_duration` 然後看剩多少算多少）。

### 1.2 必須做到的透明度要求（不能悄悄把外推小節當成真實證據）

**這是延伸/補足既有的推估機制，不是新發明一種可以無限信任的證據
來源**——延伸出來的小節必須清楚標記，讓下游（尤其是 promotion
gate）知道這幾個小節是外推出來的，不是逐拍證據判斷出來的：

1. 這幾個小節的 `evidence_sources` 要標成類似
   `["tail_extrapolation"]`（不要跟真實的 `drums`/`bass`/`v1_grid`
   等證據來源混在一起，參考 `BidirectionalBarAlignmentNode` 現有
   對 `bidirectional_alignment`/`lookahead_drum` 的標法）。
2. `full_song_loop_report`（或最終匯出報告）要新增一個欄位記錄「這次
   跑法有沒有觸發尾聲外推、外推了幾個小節」，比照 Pass 208 加的
   `bar_grid_repair_report.inserted_bar_count` 模式。
3. `evaluate_barstart_v2_completeness`（`module3_barstart_v2_bt.py`，
   Pass 208 已經在算 `repaired_bar_ratio`/`non_evidence_bar_ratio`）
   要把尾聲外推的小節數也併入 `non_evidence_bar_ratio` 的分子——
   **這幾個小節終究不是逐拍證據判斷出來的，邏輯上跟
   `BarGridContinuityRepairNode` 插入的小節是同一類**，不應該被
   promotion gate 當成跟真正 commit 的小節一樣可信。
4. **這個外推機制只能是最後手段**：只在全曲 loop 已經走完正常的
   探測/仲裁/quality-regression 流程、確認這段真的沒有足夠證據
   commit（比照 Pass 210 已經驗證過的「六個證據來源全部零候選」）
   之後才觸發，不要提早介入、搶在正常證據判斷之前就用外推頂替。

### 1.3 明確要求

1. 修完後用 `scratch/run_pass207_clean_production_verify.py` 重新
   驗證，`unresolved_bar_span_count` 應該降到 **0**。
2. **`promotion_gate.adoptable` 這次很可能第一次變成 `True`**——
   如果發生，**不要自動宣稱 BarStart V2 已經可以正式取代舊方法**，
   完整記錄所有數字（`barstart_v2_score` 對 `original_score` 的
   差距、`non_evidence_bar_ratio` 最終數值、尾聲外推了幾個小節）
   交給使用者/Claude 決定是否要真的升格，這個決定不在本任務書範圍
   內。
3. 檢查外推出來的尾聲小節時間，跟 Pass 210 已經量到的
   `175.685s`（黃金基準最後 downbeat 附近的 kick onset）做一次交叉
   比對——如果外推結果剛好跟這個真實 onset 對得上（容差內），是一個
   很好的佐證；如果對不上，如實記錄，不用勉強解釋。

---

## 2. 測試要求

新增至少 3 個測試（`tests/test_sdd_pass211.py`）：

1. 合成案例：`committed_bar_starts` 有穩定間距，`duration_cap` 比
   最後一個小節多出約 2.5-3 倍的 `expected_bar_duration`——驗證
   外推正確算出小節數、均分補齊（每段間距相等，不是「先放整的、
   剩一段零頭」）。
2. 驗證外推出來的小節 `evidence_sources` 標記正確
   （`tail_extrapolation`），且被 `evaluate_barstart_v2_completeness`
   的 `non_evidence_bar_ratio` 正確計入。
3. 負面案例：`duration_cap` 跟最後一個小節之間的落差小於半個
   `expected_bar_duration`（代表本來就已經到結尾，不需要外推）——
   驗證不會硬塞一個不必要的小節進去。
4. 執行既有回歸測試確認沒有破壞任何東西：
   ```
   C:/Python313/python.exe -m pytest tests/test_sdd_pass211.py tests/test_sdd_pass210.py tests/test_sdd_pass209.py tests/test_sdd_pass208.py tests/test_sdd_pass206.py tests/test_sdd_pass205.py tests/test_sdd_pass202.py tests/test_sdd_pass201.py tests/test_module3_bt.py -q
   ```

---

## 3. 完成後

1. 更新 `docs/BT-BUILD-PROGRESS.md`，新增 Pass 211 條目，記錄設計
   細節（選了哪種 `expected_bar_duration` 估法、外推出幾個小節、
   跟黃金基準 onset 的交叉比對結果）跟真實資料驗證結果（誠實記錄，
   包括 `promotion_gate.adoptable` 是否第一次變成 `True`）。
2. Commit + push 到 `origin/worktree-pass171-multi-variant-harness`，
   commit message 遵照這個系列的慣例（`feat(pass211): ...`，這次是
   新增外推能力，不是單純修 bug，用 `feat` 前綴）。
3. **不要在這個任務書範圍內生成新的 click 音檔並直接告訴使用者
   「可以取代舊方法了」**——照舊做法生成 provisional 音檔給使用者
   聽即可，正式升格的決定留到下一輪。
