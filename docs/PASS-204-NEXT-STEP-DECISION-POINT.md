# PASS-204 任務書：完成真實資料補齊後的下一步決策

**狀態**：決策任務書已完成，但目前停在資料前置條件門檻。
**本任務不是立即修 code 的任務**；必須先補齊指定音檔並重新完成
PASS-200 與 PASS-203，才能依本文件的決策矩陣選出下一個實作方向。

---

## 0. 本任務為什麼現在才成立

PASS-201 與 PASS-202 已完成低風險的結構性修正：

- PASS-201 將 fallback carry 小節比例納入 BarStart V2 adoption gate。
- PASS-202 加入多來源候選共識聚合與相位一致性仲裁。

但這兩個修正不能回答兩個更根本的問題：

1. `beat_this` 是否真的在已知困難段落優於現有 Stage 3 結果？
2. 現有證據融合的 0.7 門檻，是因為信心公式偏保守，還是因為證據來源本身幾乎沒有觸發？

這兩題分別由 PASS-200 與 PASS-203 的真實資料回答。沒有這兩份資料，
直接決定 PASS-204 要整合模型、調參數、修來源 bug，或放棄 BarStart V2，
都會重新犯下 PASS-197～199 已經暴露過的「先猜方向再看資料」問題。

---

## 1. 目前已知結果與阻塞

### 1.1 PASS-200

已建立並執行獨立比較腳本：

`scratch/run_pass200_beat_this_baseline.py`

目前結果：

- 狀態：`BLOCKED_MISSING_INPUT`。
- 缺少指定的 World is Mine 原始 WAV。
- `beat_this` 尚未安裝在獨立評估環境。
- 因此沒有產生任何 `beat_this` beat/downbeat 結果，也不能對已知問題點下結論。

報告：

`scratch/pass200_beat_this_comparison_report.json`

### 1.2 PASS-203

已建立即時 wrapper：

`scratch/run_pass203_evidence_fusion_diagnosis.py`

此 wrapper 會在 runtime 暫時包裝 `BarStartCandidateCommitNode.execute`，
逐 tick 記錄完整候選、來源、信心、門檻與 commit 結果，並在 `finally`
中還原 wrapper，不會把 debug instrumentation 留在 production module。

目前結果：

- 狀態：`BLOCKED`。
- 因同一個指定 WAV 不存在，沒有執行 `target_stage="module3"`。
- 因此不能判定問題是「普遍差一點點」、某個來源不觸發，或全曲證據不足。

報告：

`scratch/pass203_evidence_fusion_diagnosis.md`

---

## 2. 明確前置條件

PASS-204 在以下條件全部滿足前不得進入方向實作：

1. 提供指定原始 WAV，或由使用者明確指定等價的同一首歌來源檔案。
2. WAV 必須能被 PASS-200 與 PASS-203 讀取，且長度與既有 World is Mine 基準相符。
3. 在獨立環境安裝 `beat_this`，不得升級、降級或覆蓋現有 madmom/BeatNet pipeline 依賴。
4. PASS-200 產出所有已知問題點的逐點比較資料。
5. PASS-203 產出完整逐 tick JSONL trace 與診斷報告。
6. 使用者確認 PASS-200/203 報告中的具體發現可作為方向依據。

---

## 3. 補齊資料後的執行順序

### 3.1 重新執行 PASS-200

使用：

```text
C:/Python313/python.exe scratch/run_pass200_beat_this_baseline.py
```

必須確認：

- `baseline.status == "COMPLETED"`。
- `beats` 與 `downbeats` 均非空。
- 8.041s、22.883s、35.300s、77.803s、80.020s、93.802s、97.197s、108.652s、153.467s 與 18～20s control section 都有逐點比較結果。
- `overall_comparison` 同時包含 golden、existing pipeline、beat_this 三方統計。

### 3.2 重新執行 PASS-203

使用：

```text
C:/Python313/python.exe scratch/run_pass203_evidence_fusion_diagnosis.py
```

必須確認：

- trace 至少涵蓋完整 `target_stage="module3"` 執行。
- 每個 tick 有 active window、全部候選、來源、confidence、threshold、best candidate 與 commit 結果。
- instrumentation 在 pipeline 結束後已還原。
- 報告包含無候選 tick、低於門檻 tick、各來源觸發率與代表性個案。

---

## 4. 決策矩陣

PASS-204 只允許依照實測資料選擇下列其中一個分支。

### 分支 A：`beat_this` 明顯改善

成立條件：

- 在一個以上已知困難點，`beat_this` 相對現有 pipeline 有明確改善；
- 改善以毫秒、拍數或 downbeat 命中率量化；
- 18～20s clean control section 沒有退步；
- 不是只靠 total measures 接近 golden 就宣稱改善。

下一步：

- 另開「beat_this 作為獨立證據來源或 Stage 3 替代候選」任務書。
- 先做 offline/A-B 比較與 feature flag，不直接取代 production default。
- 明確定義 fallback、模型下載失敗與 CPU 執行成本。

### 分支 B：`beat_this` 差不多或更差

成立條件：

- 已知問題點沒有一致改善，或 control section 退步；
- aggregate 統計沒有轉化為逐點改善。

下一步：

- 暫不整合 `beat_this`。
- 以 PASS-203 的來源觸發率與 confidence gap 結果決定後續方向。

### 分支 C：PASS-203 顯示普遍只差一點點

成立條件：

- 多數有候選但未 commit 的 tick，其 best confidence 集中在 threshold 下方小幅差距；
- 至少一個具體來源在多數 tick 穩定觸發；
- 沒有先發現更優先的候選選錯或資料格式 bug。

下一步：

- 另開針對指定 evidence source 的 calibration 任務書。
- 任務書必須列出原始 confidence 分布、目標門檻與真實資料驗證案例。
- PASS-204 本身不直接改 `base_confidence` 或 threshold。

### 分支 D：PASS-203 顯示某個來源幾乎不觸發

成立條件：

- 某來源在完整歌曲只產生極少候選或完全沒有候選；
- trace 能定位到來源節點、輸入 blackboard key 或 stem 的具體缺口。

下一步：

- 另開該來源的 production bug 修復任務書。
- 必須先用合成資料驗證節點本身，再用同一首真實音檔回驗。

### 分支 E：全曲普遍沒有證據

成立條件：

- no-candidate tick 廣泛分布，不只集中在 8.041s、97.197s 等已知弱證據段落；
- 各來源觸發率普遍低，調整單一 confidence 公式無法解釋問題。

下一步：

- 暫停繼續堆疊 BarStart V2 局部規則。
- 提供「重新評估整條 BarStart V2 路線」的決策報告，由使用者決定是否繼續投資。

---

## 5. 安全限制

1. PASS-204 不得因 aggregate measure count 接近 golden 就直接選擇分支 A。
2. PASS-204 不得在 PASS-200/203 blocked 時自行推論哪個來源有 bug。
3. 不得在本任務直接修改 confidence 公式、模型權重、Stage 3 default 或 production fallback 策略。
4. `beat_this` 只能在獨立環境安裝與執行，不得污染現有 pipeline 依賴。
5. 所有診斷 instrumentation 必須在執行結束後還原。
6. PASS-201/202 的修正必須先通過既有測試，再用真實資料回驗；不得用 synthetic pass 取代 real-data verification。

---

## 6. 交付物與完成定義

PASS-204 完成前，必須有：

1. 完成的 PASS-200 JSON 報告。
2. 完成的 PASS-203 JSONL trace 與診斷報告。
3. 使用者確認的決策分支：A、B、C、D 或 E。
4. 一份新的後續實作任務書，明確指定程式位置、輸入輸出、安全機制與驗證計畫。
5. PASS-204 自己不把後續實作混入同一個變更。

### 目前狀態

目前只能標記為：

```text
PASS-204: BLOCKED_WAITING_FOR_SOURCE_AUDIO_AND_REAL_PASS-200-PASS-203_RESULTS
```

在指定 WAV 補齊並重新執行兩份報告後，才能把上述決策矩陣中的一個分支正式選定。
