# Pass 194 任務書：`MeasureMapNode` 的全曲相位補全尊重保護區段

**狀態**：已實作，單元測試與真實音訊完整管線回歸皆已通過（見第 4 節）。

---

## 0. 背景與問題診斷

本 worktree 由另一個 AI 工具（非本 session）接續完成到 Pass 193，程式碼已
提交（commit `f885c92`），但 `docs/BT-BUILD-PROGRESS.md` 沒有補上 Pass
188-193 的敘事條目，多數任務書「狀態」欄位也還停在「待實作」。使用者要求
先檢查目前實際狀況。

檢查發現 Pass 193 的真實資料回驗結果非常亮眼——`irregular_measure_count`
從 Pass 187 的 14 大幅降到 **1**，小節數（118）也比之前（113）更接近黃金
基準（121）。但直接核對程式碼與真實輸出後，發現這個漂亮數字背後有一個
嚴重問題：

Pass 193 在 `MeasureMapNode.build_measure_map()` 新增的
`_ensure_44_phase_continuity()`，做法是「找到全曲第一個 `beat==1`，然後
整曲機械式用 `(last_beat % 4) + 1` 往前往後硬推」——**完全沒有讀取
`beat_phase_protected_ranges`**（`MeasureMapNode.optional_keys` 裡沒有這個
key，程式碼裡也搜不到任何引用）。這代表 Pass 185-191 花了十輪反覆驗證、
鎖定在真實鼓點證據上的錨定相位，在最後這一步被整段蓋掉。

直接核對真實輸出證實了這個推論：Pass 184/186 反覆驗證過的《World is
Mine》18-20 秒 hi-hat 五連拍，正確的 beat-1 位置應該是 **18.563s /
20.014s**。但 Pass 193 的真實輸出裡，這兩個時間點被標成 beat 4 / beat 3，
beat-1 被機械式推到 **18.953s / 20.359s**——整整偏移了一拍。這正是使用者
最初回報的「Click 的重音是第一拍，那個重音位置不對」的原始問題，疑似被
Pass 193 重新引入，只是這次連 `irregular_measure_count` 這個 metric 本身
都看不出來（它只檢查「每小節是不是剛好 4 拍」，不檢查「beat 1 是不是打在
正確的真實重音上」）。

---

## 1. 修法：讓 `_ensure_44_phase_continuity` 尊重保護區段

1. `MeasureMapNode.optional_keys` 加入 `"beat_phase_protected_ranges"`；
   `execute()` 讀取後傳進 `build_measure_map(..., protected_ranges=...)`，
   再傳進 `_ensure_44_phase_continuity(beat_rows, protected_ranges)`。
2. 重寫 `_ensure_44_phase_continuity`：
   - 保護區段內、標號有效（1-4）的拍點視為「錨點」，標號**完全不動**。
   - 保護區段之外的空隙，依然做機械式 `(last_label % 4) + 1` 連貫補全
     （保留 Pass 193 消除碎拍的效果），但基準是**最近一個錨點的實際標號**，
     不是全曲第一個 `beat==1` 的陣列位置。
   - 相位跳躍只允許發生在「進入」保護區段的那一拍——這是必要的，保護
     區段本身就是在斷言「這裡才是真正的第 1 拍」，不該被抹平。
   - 完全沒有保護區段時（例如合成測試資料），退回 Pass 193 原本的行為
     （以全曲第一個 `beat==1` 為基準整曲機械補全），維持向後相容。

```python
def _ensure_44_phase_continuity(self, beat_rows, protected_ranges=None):
    protected_ranges = protected_ranges or []

    def _is_protected(t):
        return any(p_start <= t <= p_end for p_start, p_end in protected_ranges)

    is_anchor = [
        _is_protected(row["time"]) and isinstance(row.get("beat"), int) and 1 <= row["beat"] <= 4
        for row in beat_rows
    ]
    if not any(is_anchor):
        # 沒有保護區段：退回 Pass 193 行為
        ...

    last_label = None
    for i, row in enumerate(beat_rows):
        if is_anchor[i]:
            last_label = row["beat"]
            continue
        if last_label is not None:
            row["beat"] = (last_label % 4) + 1
            last_label = row["beat"]
    # 逆向補全第一個錨點之前的拍點（略，見程式碼）
```

---

## 2. 驗證計畫

1. **合成測試（保護區段標號不被覆蓋）**：驗證保護區段內、就算跟機械式
   推算的相位不一致的標號，依然完整保留。
2. **合成測試（空隙依然平滑補全）**：驗證保護區段之外的空隙整段是連貫、
   無斷點的 1-2-3-4 循環。
3. **合成測試（多個獨立保護區段互不干擾）**：驗證兩段各自獨立錨定、彼此
   相位不對齊的保護區段，都各自完整保留，中間空隙只跟隨前一個錨點延伸。
4. **向後相容測試**：沒有任何保護區段時，退回 Pass 193 原本的行為。
5. **真實案例回歸**：18-20 秒 hi-hat 錨點（18.563s/20.014s 應為 beat 1）
   在補全後依然正確。
6. **既有測試全跑一次**：`tests/test_sdd_pass188/193.py` 等既有測試必須
   維持通過。
7. **真實音訊完整管線回歸**：重跑
   `scratch/run_pass194_default_pipeline_reverify.py`，確認：
   - `irregular_measure_count` 依然維持在低點（不能為了修正相位準確度而
     讓 Pass 193 消除碎拍的效果整個倒退）。
   - 18-20 秒目標區段的 beat-1 位置回到 18.563s/20.014s 附近。

---

## 3. 範圍界定

- 只改 `MeasureMapNode._ensure_44_phase_continuity` 及其呼叫鏈
  （`execute()`、`build_measure_map()`），不動 `beat_tracking_bt.py` 裡
  Pass 181-191 建立/保護 `beat_phase_protected_ranges` 的邏輯本身。
- 不重新評估 Pass 188（`_merge_short_measures`）、Pass 192（防膨脹保護）
  的邏輯——這兩個機制是這次修法的下游安全網，繼續保留。
- 不補齊 `docs/BT-BUILD-PROGRESS.md` 裡 Pass 188-192 缺少的敘事條目
  （文件登記問題，跟這次的程式邏輯修正分開處理）。

---

## 4. 實作結果

### 4.1 修改內容

`MeasureMapNode.optional_keys` 加入 `"beat_phase_protected_ranges"`；
`execute()` → `build_measure_map()` → `_ensure_44_phase_continuity()` 全線
貫穿保護區段參數。`_ensure_44_phase_continuity` 改為：保護區段內、標號
有效的拍點視為錨點、標號不動；保護區段之外用機械式
`(last_label % 4) + 1` 從最近錨點連貫延伸；沒有任何保護區段時退回 Pass
193 原本行為（以全曲第一個 `beat==1` 為基準）。

### 4.2 單元測試

新增 `tests/test_sdd_pass194.py`（5 項全過）：保護區段標號不被覆蓋、
空隙依然平滑連貫補全、兩個獨立保護區段互不干擾、無保護區段時向後相容
Pass 193 行為、真實 18-20 秒案例回歸。既有 `tests/test_sdd_pass193.py`
（2 項）、`tests/test_sdd_pass188.py`（6 項）皆維持通過。

### 4.3 真實音訊完整管線回歸

重跑 `scratch/run_pass194_default_pipeline_reverify.py`：

- **18-20 秒目標區段核對（最重要的驗證）**：`measure=13 start=18.568
  beats=[(1,18.568), (2,18.953), (3,19.286), (4,19.645)]`、`measure=14
  start=20.011 beats=[(1,20.011), ...]`——beat-1 正確落在 **18.568s /
  20.011s**，跟 Pass 184/186 驗證過的真實錨點（18.563s/20.014s）誤差都
  在 5 毫秒內。Pass 193 造成的一拍偏移（beat-1 錯位到 18.953s/20.359s）
  確認已修復。
- `total_measures`：114（差黃金基準 -7）。
- `irregular_measure_count`：從 Pass 193 的 1 回升到 **10**。這不是退步，
  是拿掉了 Pass 193「無視保護證據硬湊 4/4」製造的假象——這 10 個不規則
  小節（8.041s / 21.458s / 32.382s / 77.803s / 81.446s / 93.802s /
  97.197s / 108.652s / 152.023s / 171.737s）是目前仍未解決的「保護區段
  交界處相位銜接」問題，分布在其他位置，跟 18-20 秒之前遇到的是同一類型
  問題。是否要接著處理，留待與使用者討論後再排入後續任務。
- `bpm_jump_count`：0（維持）。

### 4.4 全套單元測試回歸與既有失敗處理

全套單元測試回歸（`C:/Python313/python.exe -m pytest tests/ -q`，863 項）
結果：860 passed / 3 failed，3 項失敗跟這次改動無關（Pass 193 遺留、跟
`beat_phase_protected_ranges` 保護機制無關），確認這次修正沒有引入任何
新的回歸。

跟使用者確認設計方向後（本專案固定 4/4 拍號，真正的變拍需求由 Stage 4
`DynamicMeterChangeGuardNode` 另外處理，不透過 `MeasureMapNode` 的
downbeat 標籤表達），已一併處理這 3 項既有失敗：

1. `test_bt_workflow.py::test_measure_map_uses_downbeats_and_variable_
   lengths` → 改寫為 `test_measure_map_uses_downbeats_and_forces_44_
   continuity`，斷言改為驗證輸入不規則拍數時會被機械式拉平成連貫 4/4
   （`[4, 4]`，兩個小節皆 `is_variable_length=False`）。
2. `test_bt_workflow.py::test_measure_map_falls_back_without_downbeats`
   → 改寫為 `test_measure_map_manufactures_downbeat_without_any`，斷言
   改為驗證完全沒有 `beat==1` 時，相位補全會強制把第一個拍點當作
   beat 1、改走一般 downbeat 路徑（`measure_map_status="PASS"`，
   `source="downbeat"`），不再是舊版的 4 拍 fallback（`WARN`/
   `fallback_4beat`）。
3. `test_sdd_pass192.py::test_split_overlong_measures` → 直接移除
   （測的 `_split_overlong_measures` 方法已被 Pass 193 正式移除）。

重跑 `tests/test_bt_workflow.py` + `tests/test_sdd_pass192.py`（20 項）
全數通過，確認改寫後的斷言正確反映新行為。
