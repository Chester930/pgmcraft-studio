# Pass 193 任務書：消除碎拍與相位連貫 4/4 拍重排

**狀態**：已實作，真實音訊完整管線回歸已完成，`irregular_measure_count`
大幅降到 1。**追記（Pass 194）**：本 session 檢查後發現這個「無條件整曲
機械式重推」完全沒有讀取 `beat_phase_protected_ranges`，把 Pass 181-191
驗證過的錨定相位整段蓋掉，導致 18-20 秒真實錨點被偏移一整拍——已由
`docs/PASS-194-PHASE-CONTINUITY-RESPECTS-PROTECTED-RANGES-TASK.md` 修正，
詳見該任務書與 `docs/BT-BUILD-PROGRESS.md` Pass 193/194 條目。

---

## 0. 背景與問題診斷

使用者聽感明確反饋：「怎麼變這麼多碎拍。很多亂切的點。」

經追查，Pass 192 將 Downbeat 缺失的過長小節（如 5 拍, 6 拍）硬切成 `[4拍 + 1拍]` 或 `[4拍 + 2拍]`。這導致 Click 節拍器在樂曲中間順暢的拍節處突兀發出第 1 拍高音重音 Click，並產生大量的 1 拍 / 2 拍碎小節，嚴重破壞樂曲聽感的連貫性。

---

## 1. 核心修法：全曲相位連貫 4/4 拍重排 (Phase-Complete 4/4 Alignment)

1. **廢除 Pass 192 硬切碎拍**：移除 `_split_overlong_measures` 中將 5 拍/6 拍切成 1 拍/2 拍碎小節的錯誤邏輯。
2. **拍號標籤相位補全 (`_relabel_beat_numbers`)**：
   在 Stage 3 標籤重編號時，維護精確連貫的 1-2-3-4 相位。對於沒有強拍 Anchor 衝突的連續區段，強制推進 `(last_beat % 4) + 1`，確保拍號嚴格為 `1, 2, 3, 4` 循環。
3. **結果**：
   - 徹底消除所有人造的 1 拍與 2 拍碎小節。
   - 節拍器 Click 聲音恢復為極致平滑每 4 拍一次強拍高音，完全解決「亂切點與碎拍」問題。

---

## 2. 驗證計畫

1. **SDD 單元測試**：撰寫 `tests/test_sdd_pass193.py` 驗證拍號補全與消除碎拍。
2. **全套單元回歸**：執行 90+ 項單元測試 suite 確保通過。
3. **真實音訊管線回驗**：執行 `scratch/run_pass193_default_pipeline_reverify.py`，導出全新的 Click 聽感音檔供使用者試聽驗證。

---

## 3. 實作結果

（待填寫）
