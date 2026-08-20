# Pass 205 任務書：修正 `quality_regression` 品質倒退閘門在多小節跳躍時的誤判

**狀態**：根因已用真實資料精確定位（見下方第 1 節），**這是一個
修復任務**，交給 Codex CLI 執行。修復前請先讀完第 1-3 節，理解問題
的精確形狀，不要只看標題就動手改參數。

---

## 0. 背景與前置條件

Pass 202 的候選仲裁 bug 已經在本 worktree 由 Claude 直接修復並驗證
（`pgm_craft/workflow/module3_barstart_v2_bt.py`
`BarStartCandidateCommitNode._best_candidate`，`tests/test_sdd_pass202.py`
新增兩個回歸測試）。修復內容與驗證過程完整記錄在
`docs/PASS-203-EVIDENCE-FUSION-THRESHOLD-DIAGNOSIS-TASK.md` 第 6 節，
**執行本任務前請先讀那一節**，不要重複已經做過的仲裁修復。

修好仲裁 bug 後用 `scratch/run_pass203_evidence_fusion_diagnosis.py`
重跑全曲診斷（World is Mine，176 秒），發現一個先前被仲裁 bug 掩蓋
的**第二個問題**：`BarStartCandidateCommitNode.execute` 裡的
`quality_regression` 安全機制，在委員會選出「正確但離上次 commit
有好幾個小節遠」的候選時，幾乎必定拒絕，導致全曲 500 個 tick 只
成功 commit **1 次**（`committed_bar_starts` 從 tick 1 之後就凍結，
再也沒有成長）。這就是本任務要修的問題。

---

## 1. 根因（已用真實資料確認，不要重新診斷，直接讀這裡）

### 1.1 機制位置

`pgm_craft/workflow/module3_barstart_v2_bt.py`：

- `_score_bar_start_list_quality(bars)`（約 881 行）：對一份已
  commit 的小節起點時間列表，計算**相鄰間距**的標準差/平均值
  （`1.0 - std/mean`），間距越不規律分數越低。少於 3 個小節或少於
  2 個有效間距時回傳 `None`（「無意見」）。
- `BarStartCandidateCommitNode.execute`（約 956 行）：每次要 commit
  一個新候選前，先算 `quality_before = _score_bar_start_list_quality(committed)`
  跟 `quality_after = _score_bar_start_list_quality(committed + [候選])`，
  如果 `quality_after < quality_before - self.quality_drop_tolerance`
  （預設 0.15），就拒絕這次 commit，標記為 `quality_regression`，
  `committed` 完全不變。

### 1.2 為什麼會誤判

`_score_bar_start_list_quality` 只看**原始相鄰間距**，不知道「這個
間距之所以大，是因為中間有一個或多個小節因故沒能 commit（被跳過），
不是因為候選本身節奏不穩」。當 `committed` 的既有間距都很緊
（例如穩定 ~1.45 秒一個小節），下一個候選只要離上次 commit 超過
一個小節長度（哪怕剛好是 2 倍、3 倍、……N 倍的整數小節長度，本質上
完全合理），算出來的標準差就會暴增，`quality_after` 崩到接近 0，
必定觸發拒絕。

**已用真實資料（World is Mine 全曲診斷，修好 Pass 202 仲裁 bug 之後
重跑）逐 tick 確認**（`scratch/debug_pass203_evidence_trace.jsonl`，
可重新產生，見第 4 節）：

| tick | 候選時間(s) | 信心 | quality_before | quality_after | 結果 |
|---|---:|---:|---:|---:|---|
| 2 | 6.616259 | 0.94 | 0.9197 | 0.7663 | quality_regression 拒絕 |
| 3 | 12.376236 | 1.00 | 0.9197 | 0.2199 | quality_regression 拒絕 |
| 6 | 32.382177 | 0.72 | 0.9197 | 0.0000 | quality_regression 拒絕 |
| 10 | 70.535193 | 0.72 | 0.9197 | 0.0000 | quality_regression 拒絕 |

`quality_before` 在整個 500-tick 診斷過程中固定在 0.9197 不變——因為
`committed` 從 tick 1 commit 之後，**沒有任何後續候選能通過這個
閘門**，導致列表凍結，形成惡性循環：

1. 某個小節因故沒 commit（正常現象，例如證據被 drum fill/exclusion
   排除、信心不夠等）。
2. 下一個真正正確的候選，離上次 commit 的距離變成 2-3 個小節長。
3. `_score_bar_start_list_quality` 把這個合理的多小節跳躍當成嚴重
   節奏不穩，`quality_after` 崩潰，拒絕 commit。
4. `committed` 沒有成長，`quality_before` 也沒有機會改善，回到步驟
   2，永遠卡住。

### 1.3 這不是「先前就存在的已知問題」，是仲裁 bug 修好後才第一次大量暴露

修 Pass 202 仲裁 bug 之前，`_conflicting_candidates` 把判定範圍限制
在一個 bar duration（約 1.45 秒）以內，仲裁機制常態性選到「跟上次
commit 只差一個小節」的候選（即使信心較低），很少真的產生「跳過
好幾個小節」的候選需要 commit——所以 `quality_regression` 閘門過去
很少被真正考驗到。修好仲裁後，`_best_candidate` 老實選出真正正確、
但可能離上次 commit 有好幾個小節遠的候選，這個閘門的誤判才第一次
大量觸發，把全曲 commit 數從 5 次壓到 1 次。**這代表閘門本身的邏輯
一直都有問題，只是先前被另一個 bug 意外掩蓋。**

---

## 2. 要修什麼：讓品質檢查能分辨「合理的多小節跳躍」與「真正的節奏異常」

### 2.1 目標

修改 `_score_bar_start_list_quality`（或呼叫端的品質比較邏輯），讓
一個新候選只要落在**預期小節長度的合理整數倍**上（即候選跟上次
commit 的間距除以 `expected_bar_duration_sec` 之後，餘數在容許誤差
內），就不應該被當成「節奏不穩」而拒絕，即使間距本身是好幾個小節
長。**同時必須保留原本的保護作用**：一個真正離譜、不落在任何合理
小節倍數上的候選（例如誤判到某個 off-grid 的雜訊敲擊），仍然要能
被這個閘門攔下來。

`BarStartCandidateCommitNode` 已經有 `_expected_bar_duration(blackboard)`
（供 `_conflicting_candidates`/`_phase_consistency_score` 使用）跟
`_phase_consistency_score(candidate_time, committed, expected)`
（算候選相對於已 commit 小節、按小節倍數殘差評分的邏輯）——**這兩個
既有工具很可能就是修這個問題最自然的素材**，不需要另外發明新的
判斷方式。具體怎麼接、要不要直接複用 `_phase_consistency_score`
的殘差計算，由你判斷；但修法必須基於這兩個既有的「小節倍數」概念，
不要憑空發明一個新的容錯規則。

### 2.2 明確要求（驗收標準）

1. **正面案例**：`committed` 間距穩定在 ~1.45 秒，新候選落在
   `上次commit時間 + N × 1.45秒`（N ≥ 2，允許合理殘差誤差）——這種
   候選**不應該**因為 `quality_regression` 被拒絕。
2. **負面案例（既有保護不能被削弱）**：新候選的間距**不是**任何
   合理小節倍數（例如落在 `上次commit + 1.2 × 1.45秒` 這種不上不下
   的位置，代表真正的節奏異常或誤判），**仍然應該**被
   `quality_regression` 攔下來。
3. 修法不能只是「調高/調低 `quality_drop_tolerance` 這個數字」——
   已經用真實資料證明過這類憑感覺調參數的做法在這個系列會出事
   （Pass 197 threshold bug、Pass 198B 級聯），必須是能分辨上述兩種
   案例的**邏輯**修正，不是單純放寬容忍度的數字修正。
4. 保留 `_score_bar_start_list_quality` 對「同一份 committed 列表
   內部前後小節間距是否穩定」的既有判斷能力——這個修正只解決「新
   候選離上次 commit 較遠時的誤判」，不要順便改掉它原本抓真正節奏
   不穩定的能力。

---

## 3. 測試要求

1. 在 `tests/test_module3_bt.py` 或新建 `tests/test_sdd_pass205.py`
   （比照這個系列既有的 SDD 慣例）新增至少兩個測試：
   - 正面案例：`committed` 有穩定間距，新候選落在合理的多小節整數
     倍位置，驗證 `execute()` 結果是 `COMMITTED`（不是
     `quality_regression`）。
   - 負面案例：新候選不落在任何合理小節倍數上，驗證仍然被判定為
     `quality_regression`、`committed` 不變。
2. 執行既有回歸測試確認沒有破壞任何東西：
   ```
   C:/Python313/python.exe -m pytest tests/test_sdd_pass202.py tests/test_sdd_pass201.py tests/test_module3_bt.py tests/test_sdd_pass205.py -q
   ```
3. 用真實資料重新驗證（比照這個系列每一個 Pass 都做過的方式，不要
   只信任 unit test）：重跑
   `scratch/run_pass203_evidence_fusion_diagnosis.py`（stems 快取已經
   在 `outputs/pass203_evidence_fusion_diagnosis_fullsong/` 跟
   `outputs/pass203_evidence_fusion_diagnosis/` 裡，不需要重新跑
   demucs 分離，執行時間約 13 分鐘），確認：
   - 全曲 commit 數明顯高於修復前的 1 次（理想情況：`committed_bar_starts`
     能持續成長，覆蓋全曲，不再凍結）。
   - 用 `pgm_craft.golden_benchmark` 對照這首歌的黃金基準（121
     measures，0 irregular）評估修復後的實際小節序列品質。
   - 如果全曲仍然無法順利推進，**誠實記錄卡在哪裡、為什麼**，不要
     只憑局部改善就宣稱問題解決——這個系列已經連續發生「看起來修好
     了，其實只是把 bug 藏到更深一層」的案例（Pass 199 的 85% 假
     fallback carry 就是活生生的例子），修完這一層之後如果又冒出
     第三個瓶頸，一樣要老實回報，不要隱藏。

---

## 4. 如何重跑全曲診斷腳本

```bash
cd "D:/Users/666/Desktop/UVR5 音檔/自動節拍器/.claude/worktrees/pass171-multi-variant-harness"
C:/Python313/python.exe scratch/run_pass203_evidence_fusion_diagnosis.py
```

輸出：
- `scratch/debug_pass203_evidence_trace.jsonl`（逐 tick 完整候選/
  仲裁/決策紀錄，一行一個 JSON 物件）
- `scratch/pass203_evidence_fusion_diagnosis.md`（統計摘要）

腳本本身已經包含暫時的 instrumentation（`_install_runtime_probe`/
`_install_stall_override`），跑完會自動還原，不會污染正式程式碼路徑
——不需要為了這次驗證再另外加新的埋點。

---

## 5. 完成後

1. 更新 `docs/BT-BUILD-PROGRESS.md`，新增 Pass 205 條目，記錄根因、
   修法、驗證結果（照這個系列既有的敘事風格）。
2. 如果全曲診斷顯示 BarStart V2 已經能穩定推進、品質接近黃金基準，
   在條目裡明確建議 Pass 204 的下一步決策方向；如果仍卡在別的地方，
   一樣要在條目裡誠實記錄，不要美化。
3. Commit + push 到 `origin/worktree-pass171-multi-variant-harness`，
   commit message 遵照這個系列的慣例（`fix(pass205): ...`），列出
   根因、修法、驗證結果三個重點。
