# Pass 209 任務書：探測視窗在歌曲尾聲會滑到超出實際長度，產生假的 unresolved span

**狀態**：根因已用真實資料精確定位到確切的函式跟程式碼行，**這是
修復型任務**，不需要再重新診斷，可轉交 Codex CLI 直接執行。

---

## 0. 背景

Pass 208（`docs/PASS-208-BARSTART-V2-POSTPROCESS-GRID-ARTIFACTS-TASK.md`，
commit `262a748`）已由 Codex 修好下游平滑製造網格瑕疵的問題（V2 分數
37.15→65.53），Claude 已獨立覆核確認（30 測試重跑通過、實際 JSON
報告數字核對相符、近乎重複小節跟大跳空隙都已消失）。使用者聽過修好
後的 click 音檔，回報「需要繼續優化處理」。

目前卡住 promotion gate 的是 `unresolved_bar_span_count=6`（見
`scratch/run_pass207_clean_production_verify.py` 最新一次乾淨跑法的
`outputs/pass207_clean_production_verify/.../reports/module3_beat_click_report.json`）。
用 `full_song_loop_report.diagnostic_trace`（Pass 206 加的逐 tick
trace）逐筆核對這 6 個未解析的 tick，發現：

```
tick 85  window.start_time=171.736837  reason=no_candidates
         diagnostic_classification=all_candidates_already_committed
         （合法：這裡真的沒有下一個候選了，是全曲自然結尾附近）
tick 86  window.start_time=174.736837  reason=no_candidates
         diagnostic_classification=no_upstream_candidates
tick 87  window.start_time=178.736837  reason=no_candidates
         diagnostic_classification=no_upstream_candidates
tick 88  window.start_time=183.736837  reason=no_candidates
         diagnostic_classification=no_upstream_candidates
tick 89  window.start_time=189.736837  reason=no_candidates
         diagnostic_classification=no_upstream_candidates
tick 90  window.start_time=196.736837  reason=no_candidates
         diagnostic_classification=no_upstream_candidates
```

歌曲實際長度（`full_song_loop_report.duration_cap_sec`）是
**176.6458 秒**。tick 87-90 的搜尋視窗起點（178.7s、183.7s、189.7s、
196.7s）**全部都已經超出歌曲實際長度**，這幾個 tick 根本不可能找到
任何候選——不是「這段音訊真的沒有證據」，是搜尋視窗本身跑到音訊
範圍外面去了，卻仍然被記錄成 `unresolved_bar_spans` 的一員，永久
擋住 promotion gate 看到 0 個未解析區間。

**這正是 `docs/PASS-203-EVIDENCE-FUSION-THRESHOLD-DIAGNOSIS-TASK.md`
第 5.3 節當初記錄過、但誤判成「正式管線不會受影響」的既有邏輯缺口
——這次用真實資料證實它其實會，只是規模比診斷腳本 monkeypatch
`stall_limit=10000` 時（400 個無效 tick）小很多（這裡只有 4 個），
但依然實際擋住了 promotion gate。**

---

## 1. 根因（已用程式碼跟真實資料確認到精確位置）

`FullSongBarStartLoopNode.execute`（`pgm_craft/workflow/module3_barstart_v2_bt.py:3809`）
已經有一個「到達全曲結尾就提前停止」的檢查（約 3822-3831 行）：

```python
while iterations < self.max_iterations:
    before = self._normalize(blackboard.get_val("committed_bar_starts"))
    if duration_cap is not None and before and before[-1] >= duration_cap - 0.08:
        stop_reason = "reached_audio_duration"
        break
    ...
```

**這個檢查用的是 `committed[-1]`（最後一次成功 commit 的小節時間）**，
但這次卡住的原因不是「最後 commit 時間已經到結尾附近所以理所當然
沒有下一個候選」（tick 85 那種，合理），而是：`RollingProbeWindowNode`
在連續探測失敗時，會把下一次搜尋視窗的起點設成**上一次視窗的
`window_end`**，跟 `committed[-1]` 或 `duration_cap` 完全無關：

```python
# pgm_craft/workflow/module3_barstart_v2_bt.py:344-356
def _next_start_time(self, last_committed: float, previous_window: float, result: dict) -> float:
    status = str(result.get("status", "")).lower()
    if status in {"found", "found_fast", "too_fast"} and result.get("candidate_time") is not None:
        ...
    if status in {"not_found", "failed", "uncertain"}:
        try:
            return max(0.0, float(result.get("window_end")))   # <- 只看上一次視窗的結尾
        except (TypeError, ValueError):
            return last_committed + previous_window
    return last_committed
```

配合 `_adjust_window`（連續失敗每次視窗寬度 +1 秒，上限
`max_window_sec=12.0`），連續幾次探測失敗後，視窗起點會不斷往前滑，
完全不受 `duration_cap` 或 `last_committed` 約束。這次真實資料量到的
滑動軌跡：171.7 → 174.7 → 178.7 → 183.7 → 189.7 → 196.7（歌曲實際
只有到 176.65 秒），完全對得上這段程式碼的行為。

`FullSongBarStartLoopNode` 的「到達結尾」檢查因為只看 `committed[-1]`
（這次卡在 175.183，離 `duration_cap-0.08`＝176.5658 還差一點），永遠
不會因為「視窗本身已經滑到範圍外」而提前停止，於是每個滑到範圍外的
tick 都被當成一次真正的探測失敗，記進 `unresolved_bar_spans`。

---

## 2. 要修什麼

**目標**：一旦搜尋視窗本身已經滑到 `duration_cap` 之後（不是
`committed[-1]`），迴圈要能辨識「這裡已經沒有音訊了」並乾淨停止，
**不要把這種 tick 記錄成 `unresolved_bar_spans`**——因為那不是真的
「這段音訊找不到證據」，是探測範圍本身跑到音訊外面去了。

具體要求：

1. `FullSongBarStartLoopNode.execute` 的迴圈條件（約 3822 行附近）要
   多一個判斷：搜尋視窗自己的 `start_time`（或 `end_time`）如果已經
   達到/超過 `duration_cap`，也要觸發跟 `reached_audio_duration`
   同等的提前停止邏輯——不管 `committed[-1]` 有沒有到那個位置。
   視窗的起點可以從 `blackboard.get_val("active_bar_probe_window", {})`
   讀出來（每個 tick 結束後都會更新這個值，`RollingProbeWindowNode`
   的 `output_keys` 裡有）。
2. **這次真正提前停止的那個 tick（讓視窗第一次滑到超出範圍的那一次）
   不應該被計入 `unresolved_bar_spans`**——因為視窗本身已經不在音訊
   範圍內，探測結果沒有意義，不是真的「找不到證據」。具體做法（哪一種
   由 Codex 判斷，但要達到這個效果）：
   - 選項 A：在動 tick 之前就先檢查視窗起點是否已經超出
     `duration_cap`，超出就直接跳出迴圈，不執行這次 tick（不會產生
     `bar_start_decision_report`，自然不會寫入 `unresolved_bar_spans`）。
   - 選項 B：tick 執行後如果發現這次視窗整個落在 `duration_cap` 之外，
     從 `unresolved_bar_spans` 裡把這筆事後移除。
   - **選項 A 比較乾淨（不浪費這次 tick 的運算，也不需要事後回溯
     修改列表），優先採用選項 A，除非有具體理由做不到。**
3. `RollingProbeWindowNode._next_start_time`（第 344-356 行）本身要不
   要也加上對 `duration_cap` 的約束（例如視窗起點不要超過
   `duration_cap + 某個小容差`），由 Codex 判斷是否必要——**但即使
   不改這個節點，只要 `FullSongBarStartLoopNode` 自己能正確辨識並
   提前停止，就足以解決 promotion gate 被卡住的問題**，不強制要求
   同時改兩個地方，避免不必要的改動範圍擴大。
4. **不要改動 tick 85 那種合理情境的行為**——`committed[-1]` 已經
   接近 `duration_cap` 時的既有 `reached_audio_duration` 檢查要維持
   原樣不動，這次只新增「視窗本身已經跑出範圍」這個額外的停止條件，
   兩者是互補關係，不是互相替代。

---

## 3. 測試要求

新增至少兩個測試（`tests/test_sdd_pass209.py`）：

1. 正面案例：`committed_bar_starts` 最後一筆離 `duration_cap`還有
   一段距離，但探測視窗（透過連續失敗滑動）已經超出 `duration_cap`
   ——驗證迴圈能正確提前停止，且這個/這些超出範圍的 tick **不會**
   出現在最終的 `unresolved_bar_spans` 裡。
2. 負面案例（既有行為不能被破壞）：`committed_bar_starts` 最後一筆
   本身就已經接近 `duration_cap`（tick 85 那種「沒有下一個候選，
   因為已經到結尾」的情境）——確認這個既有的、合理的
   `reached_audio_duration` 行為不受影響。
3. 執行既有回歸測試確認沒有破壞任何東西：
   ```
   C:/Python313/python.exe -m pytest tests/test_sdd_pass209.py tests/test_sdd_pass208.py tests/test_sdd_pass206.py tests/test_sdd_pass205.py tests/test_sdd_pass202.py tests/test_sdd_pass201.py tests/test_module3_bt.py -q
   ```

---

## 4. 真實資料驗證

用 `scratch/run_pass207_clean_production_verify.py`（stems 已有快取，
`outputs/pass203_evidence_fusion_diagnosis/.../stems`，不需要重跑
demucs，一次約 13 分鐘）重新驗證：

1. `unresolved_bar_span_count` 應該從 6 降到接近 1（只剩 tick 85
   那種合理的「已到結尾附近，沒有下一個候選」情境，這個不是這次要
   解決的問題，不強求消失）。
2. 確認 `promotion_gate` 的其他數字（`carried_bar_ratio`、
   `repaired_bar_ratio`、`non_evidence_bar_ratio`、`barstart_v2_score`）
   有沒有連帶變化，如實記錄，不要只挑好看的數字講。
3. **如果修好這個問題後，`unresolved_bar_span_count` 真的降到 0 或
   1，且其他門檻數字都在允許範圍內，`promotion_gate.adoptable` 可能
   會第一次變成 `True`**——如果發生這種情況，不要自動宣稱「BarStart
   V2 已經可以正式採用」，先停下來完整記錄所有數字（包括
   `barstart_v2_score` 對 `original_score` 的差距），交給使用者/
   Claude 決定是否要正式升格，這個決定不在本任務書範圍內。
4. 執行完畢後**才能生成新的 click 音檔**——如果 `unresolved_bar_span_count`
   確實下降，代表歌曲尾聲那幾個小節這次是真的被正確處理了（不再是
   「因為視窗跑出範圍所以放棄」），值得重新聽一次確認尾聲聽感有沒有
   改善。

---

## 5. 完成後

1. 更新 `docs/BT-BUILD-PROGRESS.md`，新增 Pass 209 條目，記錄根因、
   修法、真實資料驗證結果（誠實記錄，包括如果 `promotion_gate` 首次
   變成 `adoptable=True` 這種重大結果）。
2. Commit + push 到 `origin/worktree-pass171-multi-variant-harness`，
   commit message 遵照這個系列的慣例（`fix(pass209): ...`）。
