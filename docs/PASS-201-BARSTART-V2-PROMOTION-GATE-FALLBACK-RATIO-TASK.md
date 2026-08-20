# Pass 201 任務書：修正 BarStart V2 的 adoptable 判斷，不能只看 unresolved span 是不是 0

**狀態**：根因已確認，修復規格明確，可直接轉交 Codex CLI 執行。
獨立於 Pass 200/202/203，可以先做。

---

## 0. 背景：已確認的安全漏洞

`evaluate_barstart_v2_completeness()`（`pgm_craft/workflow/module3_barstart_v2_bt.py:3332`）
目前的邏輯：

```python
def evaluate_barstart_v2_completeness(*, unresolved_bar_spans=None):
    """
    Earlier versions gated v2 behind either a strict human-acceptance
    promotion gate or an automatic v1-vs-v2 quality-score comparison.
    Both were retired once real listening tests confirmed v2 consistently
    sounds better than v1 -- v2 is now the default output everywhere...
    """
    unresolved_count = len(unresolved_bar_spans or [])
    blockers = ["UNRESOLVED_BAR_SPANS_PRESENT"] if unresolved_count else []
    return {
        "adoptable": not blockers,
        "status": "V2_READY" if not blockers else "V2_INCOMPLETE",
        "blockers": blockers,
        "unresolved_bar_span_count": unresolved_count,
    }
```

**這個函式的前提假設「V2 完成時一定比 v1 好」已經被 Pass 199 的真實
資料推翻**：Pass 199 修好 BarStart V2 的全曲卡死問題後，`unresolved_bar_span_count`
變成 0、`adoptable=True`，被自動判定取代舊方法上線。但獨立驗證
（`docs/PASS-199-BARSTART-V2-FULL-SONG-LOOP-STALL-TASK.md` 第 5 節）
發現：

- 124 個 commit 的小節裡，**106 個（85%）不是靠真正的多來源證據
  判斷，是連續卡住 3 次後直接複製 v1 舊拍點網格充數**（`stall_trace`
  顯示 `CARRIED_V1_GRID` 291 次）。
- 品質分數（`quality_comparison.barstart_v2_score=58.15`）明顯低於
  舊方法（88.47），但完全沒有被納入 `adoptable` 的判斷。
- 使用者實際聽了回報「很穩定但完全沒有照著音樂做即時調整」——這個
  聽感確認了量化發現的問題是真的。

**`unresolved_bar_span_count==0` 不再是「V2 真的解出來了」的可靠
信號**——它可以透過 fallback carry 機制達成，不需要真正的證據判斷。
`evaluate_barstart_v2_completeness` 的判斷需要更新。

---

## 1. 修復規格

### 1.1 新增一個「真實證據比例」訊號

在 `FullSongBarStartLoopNode.execute`（`:3453`）已經有
`stall_recoveries`（靠 fallback carry 補上小節的次數）跟
`committed_bar_count`（最終總小節數）——**這兩個數字已經足夠算出
「這次結果有多少比例是真正的證據判斷、多少比例是複製舊資料」**，
不需要新增資料來源：

```python
genuine_ratio = 1.0 - (stall_recoveries / committed_bar_count) if committed_bar_count else 0.0
```

（注意：`stall_recoveries` 記錄的是「觸發幾次 fallback carry」，不是
「有幾個小節是 carry 出來的」——因為一次 carry 可能補上不只一個小節
（例如 Pass 199 真實案例第一次 recovery 就補了 5 個）。**這個規格
需要先精確定義要用哪種算法**，建議直接讓 `FullSongBarStartLoopNode`
額外記錄「本次 recovery 補上了幾個小節」（`len(provisional)`，已經
在 `stall_trace` 裡有記錄，只是還沒加總），改成：

```python
carried_bar_count = sum(entry.get("provisional_count", 0) for entry in tick_trace if entry.get("stall_count", 0) >= stall_limit)
```

或更直接：在觸發 recovery 合併時直接累加 `len(provisional)` 到一個
`carried_bar_total` 計數器，寫進 `full_song_loop_report`，不要事後
從 `stall_trace` 反推——這樣比較不容易算錯。**這個實作細節由 Codex
決定，只要最終 `full_song_loop_report` 裡有一個誠實反映「多少小節
是複製出來、不是真正判斷出來」的數字即可**。

### 1.2 把這個比例納入 `adoptable` 判斷

`evaluate_barstart_v2_completeness` 新增一個參數（例如
`carried_bar_ratio: float`），當這個比例超過某個門檻（建議先用
**0.5**，也就是「超過一半的小節是複製出來的，就不能算 V2 自己
解決了這首歌」——這個數字沒有像 Pass 197 那樣有真實資料反覆校準過
的精確邊界，先用一個保守值，實作後用真實資料驗證這個門檻合不合理，
不要一開始就假設 0.5 是對的），`adoptable` 應該是 `False`，
`blockers` 新增 `"EXCESSIVE_FALLBACK_CARRY_RATIO"`。

### 1.3 更新過時的 docstring 跟 `notes`

`evaluate_barstart_v2_completeness` 的 docstring、以及
`Module3BarStartV2MergeNode.execute` 裡 `report["notes"]` 的文字
（`module3_bt.py:1128-1134`）都還寫著「real listening tests confirmed
v2 consistently sounds better than v1」——**這個結論已經被 Pass 199
的真實案例推翻，不能繼續留著誤導後續維護者**。改成誠實反映現況：
V2 完成度高（`unresolved_bar_span_count==0`）**加上**真正證據比例夠高
（`carried_bar_ratio` 低於門檻）才會被採用，否則退回 v1。

---

## 2. 安全機制

1. **這個修復不需要真實音檔驗證**（不涉及音訊分析邏輯本身，只是
   在既有數字上加一個判斷門檻），但改完之後**要重跑一次
   `scratch/run_pass198_default_pipeline_reverify.py`（Pass 199 那次
   真實資料的重現），確認這次 `adoptable` 正確判斷為 `False`**（因為
   我們已知這次的 `carried_bar_ratio` 是 85%，遠超過任何合理門檻）。
2. **同時要確認一個「V2 真的表現好」的情境不會被誤傷**——比照
   Pass 200 如果有更好的證據來源、或未來某次真實資料 V2 大部分小節
   都是真正判斷出來的，這個新門檻不應該把它擋下來。可以用合成測試
   模擬「99% 小節都是真正 commit、1% 是 fallback」的情境，確認
   `adoptable` 還是 `True`。

---

## 3. 驗證計畫

1. **合成測試**：
   - 模擬 `carried_bar_ratio` 超過門檻的情境，確認 `adoptable=False`
     且 `blockers` 包含 `EXCESSIVE_FALLBACK_CARRY_RATIO`。
   - 模擬 `carried_bar_ratio` 遠低於門檻、`unresolved_bar_span_count==0`
     的情境，確認 `adoptable=True`（不誤傷真正表現好的情況）。
   - 既有測試（`unresolved_bar_spans` 非空時 `adoptable=False`）要
     維持通過，這個行為不變。
2. **真實資料驗證**：重跑 Pass 199 的真實案例，確認這次
   `barstart_v2_report.status` 變成 `COMPARED_NOT_PROMOTED`（不是
   `PROMOTED_TO_MODULE3_DEFAULT`），管線退回使用 legacy（Pass 198
   階段 A）的結果。
3. **既有測試全跑一次**：`tests/test_module3_bt.py` 全部要維持通過
   （包含 Pass 199 一度弄壞、後來復原的那個靜音音檔安全測試）。
