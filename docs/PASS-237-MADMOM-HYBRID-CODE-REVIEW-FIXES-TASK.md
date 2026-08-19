# Pass 237 任務書：修復 Pass236 madmom-primary 混合拼接的三個已驗證瑕疵

**狀態**：Code review 已完成，三個問題都用真實資料實際跑過驗證（不是
推測），可直接轉交 Codex CLI 執行。**這是修復既有 WIP 實作的瑕疵，
不是重新設計——Pass236 任務書定案的架構（opt-in旗標、後製拼接、
madmom自己的小節間距變異係數當弱區段依據）維持不變，範圍只在修
下面三個具體問題。**

---

## 0. 背景：Review 對象

Codex 已依照
[`PASS-236-MADMOM-PRIMARY-SEGMENT-SWAP-TASK.md`](PASS-236-MADMOM-PRIMARY-SEGMENT-SWAP-TASK.md)
寫出 WIP 實作（尚未 commit）：

- `pgm_craft/workflow/madmom_hybrid.py`（新檔，`MadmomPrimarySegmentSpliceNode`
  本體）
- `pgm_craft/workflow/builder.py`（新增 `madmom_hybrid_approved` 參數，
  預設 `None`，確認過不影響現有呼叫端行為）
- `pgm_craft/workflow/module3_bt.py`（把節點接進
  `build_module3_pipeline_tree()`，接在 `Module3BarStartV2MergeNode()`
  之後、export 之前）
- `tests/test_sdd_pass236.py`（5 條測試）
- `scratch/run_pass236_offline_calibration.py`（離線校準腳本，已寫好
  但從沒真正執行到底——輸出檔案 `scratch/pass236_offline_calibration.json`
  在 review 前不存在）

架構方向（opt-in 旗標、後製拼接不逐拍融合、用小節間距 CV 當弱區段
依據）跟 Pass236 任務書一致，是對的。`madmom_hybrid_approved` 預設
關閉這件事也確認過不影響現有 pipeline 輸出。但實際跑程式碼驗證後，
發現三個問題，第一個是會讓整個 Pass236 想解決的問題完全沒被解決的
真實 bug，不是理論風險。

---

## 1.【必須修，最高優先】預設 `cv_threshold` 沒通過任務書自己的校準門檻，
會讓 Outro 弱區段偵測失效

**證據（已實際執行，不是推測）**：

```
$ python scratch/run_pass236_offline_calibration.py
...
selected={"window_bars": 3, "cv_threshold": 0.03, "min_span_bars": 2, ...}
```

掃描 `window_bars∈{3,5,7,9}` × `cv_threshold∈{0.03,0.04,0.05,0.06,0.08,0.10,0.12}`
× `min_span_bars∈{2,3,4}`，能通過「精準只標到Outro、不誤傷
Intro/Verse1/Chorus1」這個任務書第3.1節驗收標準的組合，`cv_threshold`
全部落在 `{0.03, 0.04, 0.05}`——沒有任何一組 `cv_threshold=0.06`（或
更高）的組合合格。

而 `madmom_hybrid.py` 目前寫死的是：

```python
DEFAULT_CV_THRESHOLD = 0.06
```

直接驗證這組預設值在真實資料上的行為：

```
$ python -c "
from pgm_craft.workflow.madmom_hybrid import _run_madmom_dbn, _detect_weak_spans
grid = _run_madmom_dbn('outputs/pass198_default_pipeline_reverify/.../source/....wav', transition_lambda=500)
downbeats = [float(r[0]) for r in grid if abs(float(r[1]) - 1.0) < 1e-6]
print(_detect_weak_spans(downbeats, window_bars=5, cv_threshold=0.06, min_span_bars=2))
"
[]
```

**回傳空陣列。** 也就是說，用目前寫死的預設值，`madmom_hybrid_report`
會是 `status: "NO_WEAK_SPANS"`，Outro 會完全維持原始 madmom 輸出（就
是使用者聽過確認還有問題的那個弱段），完全不會換成 V2 fallback。
Pass236 整份設計要解決的問題，在目前的預設值下**沒有被解決，而且
不會有任何錯誤或警告**——是靜默失效。

23 條既有測試全部通過、沒抓到這個問題，因為唯一用到真實預設值
`(5, 0.06, 2)` 的測試
`test_detect_weak_spans_does_not_use_sparse_density_as_signal` 只驗證
「不誤傷Intro那種稀疏但穩定的段落」，沒有任何測試驗證「這組預設值
真的抓得到Outro」。

**要求**：

1. 依 Pass236任務書第3.1節的校準流程，從上面已經跑出來、真正通過
   「exact_outro_only」驗收的候選組合中選一組正式定案（不是隨便挑
   最寬鬆的邊界值，選的時候要考慮一點margin，不要卡在剛好會被真實
   noise推過門檻的邊緣）。更新 `DEFAULT_WINDOW_BARS`/
   `DEFAULT_CV_THRESHOLD`/`DEFAULT_MIN_SPAN_BARS`。
2. 把完整的校準結果（`scratch/pass236_offline_calibration.json`，
   所有候選組合 + 選定理由）**提交進版本庫留存**，不要再讓校準腳本
   停留在「寫了但沒真正跑完存檔」的狀態。
3. 新增一條回歸測試：用真實 Pass233 madmom 全曲降拍資料（或至少跟
   校準用的同一份），套用**更新後的預設值**，直接斷言 spans 有正確
   標到 Outro 範圍、且不誤傷 Intro/Verse1/Chorus1——取代目前
   `test_detect_weak_spans_does_not_use_sparse_density_as_signal`
   「只驗證一半（不誤傷Intro），沒驗證另一半（真的抓得到Outro）」的
   缺口。

---

## 2.【必須修】音檔來源用錯欄位，且從未驗證過在該欄位上madmom是否
還維持高準確度

**證據**：

- `MadmomPrimarySegmentSpliceNode.execute()` 目前讀
  `blackboard.get_val("madmom_hybrid_audio_path") or blackboard.get_val("audio_path")`。
- `WriteNormalizedWAVNode`（`audio_quality_bt.py:797`）會把 `audio_path`
  改寫成**正規化版（B版，`normalized_wav_path`）**，並且明確在
  docstring 裡把**denoised版（C版，`target_analysis_path`）**標註為
  「供 AI 樂器分離與 Beat tracking 最佳化」用的欄位。
- Pass229-233 驗證出的「近乎完美」數字（Intro 17/17、Verse1 42/42、
  Chorus1 42/42），Pass233 的校準/驗證腳本都是直接讀
  `source/{name}.wav`（等同原始 A 版），**不是**正規化版。
- 專案裡其餘所有分析類節點都遵循讀 `target_analysis_path` 的慣例：
  `beat_tracking_bt.py`、`stem_separation_bt.py`、`audio_nodes.py` 裡
  所有用到音檔做追蹤/分析的節點都是 `target_analysis_path` 優先，
  `audio_path` 頂多當最後備援。`MadmomPrimarySegmentSpliceNode` 是
  唯一沒有遵循這個慣例的節點。

這首測試曲剛好 `leading_silence_sec=0.0`，正規化理論上沒有動到時間
軸，所以現在可能還沒真的出事；但 madmom 在正規化音檔上是否還維持
Pass233那種準確度，**從來沒有實際驗證過**，而且這是一個會默默偏離
專案既有慣例的設計缺口。

**要求**：

1. `MadmomPrimarySegmentSpliceNode` 音檔來源改成優先順序：
   `target_analysis_path` → `denoised_wav_path` →（既有的
   `madmom_hybrid_audio_path` 覆寫旗標依然保留最高優先權，方便手動
   指定）→ `audio_path`（最後備援，不要整個拿掉，避免舊測試裡只塞
   `audio_path` 的情境壞掉）。`optional_keys` 要把
   `target_analysis_path`/`denoised_wav_path` 加進去。
2. 用改好的音檔來源重新跑一次真實 pipeline（`madmom_hybrid_approved=True`），
   確認 Intro/Verse1/Chorus1 逐段跟golden比殘差，維持接近 Pass233
   記錄的近乎完美表現（這是安全底線，不能因為換了音檔輸入就跟著
   退步）。

---

## 3.【必須修】完全沒有處理 `trim_offset_sec`，對有開場靜音的曲目會
造成全曲性的靜默時間偏移

**證據**：

- `SilenceTrimNode`（`audio_quality_bt.py:437`）在
  `leading_silence_sec > 1.5` 時會裁切音檔開頭，並把裁掉的秒數記錄
  在 `trim_offset_sec`，程式碼註解明確寫「記錄 trim_offset_sec 供
  後續 BeatNet 時間補正」——代表這個專案裡任何在裁切後音檔上算出
  時間戳的節點，都被期待要把 `trim_offset_sec` 加回去才能對齊原始
  時間軸（也就是 golden 基準、V2 fallback grid 用的那條時間軸）。
- `MadmomPrimarySegmentSpliceNode` 完全沒有讀取或使用
  `trim_offset_sec`。

這次驗證的曲目 `leading_silence_sec=0.0`，`trim_offset_sec` 剛好是
`0.0`，所以目前沒有實際觸發；但只要換一首開場靜音超過1.5秒的曲子，
madmom 算出來的所有時間戳都會系統性偏移 `trim_offset_sec` 秒，跟
golden/V2 fallback grid 對不齊——而且是全曲性、無聲的錯位，不只
弱區段，因為 madmom 是「主要輸出」，偏移會出現在每一個沒被替換掉
的小節上。

**要求**：

1. `execute()` 裡讀 `blackboard.get_val("trim_offset_sec", 0.0)`，在
   `_run_madmom_dbn()` 算出 grid 之後、進入弱區段偵測/拼接之前，把
   grid 的時間欄位一律加回 `trim_offset_sec`（因為 fallback grid
   本身是相對原始/未裁切時間軸算出來的，必須先對齊再比較/拼接）。
2. 新增測試：用 `monkeypatch` 讓 `_run_madmom_dbn` 回傳一組「模擬
   裁切後時間軸」的假 grid，設定非零 `trim_offset_sec`，驗證最終寫
   進 `beats`/`refined_beats` 的時間戳有正確加回 offset。

---

## 4.（次要，可做可不做，不擋驗收）`_splice_grid` 重複小節去重的
tie-break 註解跟實際行為不符

`_splice_grid()` 裡合併排序後去重複那段程式碼，註解寫「Fallback rows
are appended after madmom rows, so they win ties」，但實際上因為合併
後有重新照時間排序，兩筆時間相近的小節誰在陣列裡「比較後面」，取決
於排序後的相對順序，不一定是fallback。這只在
`duplicate_tolerance_sec`（預設0.03秒）容忍帶內的邊界情況才會出現，
影響很小，Pass236任務書本身也容許邊界不完全對齊。如果順手要修（改
成用一個明確的來源標記去判斷該保留哪筆，而不是依賴排序後的相對
順序），可以做；不修也不影響本任務書驗收。

---

## 5. 驗證流程

沿用 Pass236 任務書規格，這次只驗證「已知瑕疵是否修好」，不擴大
設計範圍：

### 5.1 離線（先做）

1. 重新產生 `scratch/pass236_offline_calibration.json`，確認選定的
   `window_bars`/`cv_threshold`/`min_span_bars` 精準對應 Outro，不
   誤傷 Intro/Verse1/Chorus1。
2. 用第2點修好的音檔來源（`target_analysis_path`）跑一次 Pass233
   同型的直接madmom驗證（逐段跟golden比殘差），確認換了音檔輸入後
   Intro/Verse1/Chorus1 仍接近 17/17、42/42、42/42。

### 5.2 真實 pipeline（離線驗證通過後才做）

用 `madmom_hybrid_approved=True` 跑一次完整 production verify（World
is Mine）：

1. `barstart_v2_score` 三方比較：拼接後結果 vs 純madmom（未拼接）
   vs 現行V2基準 `80.66`——確認拼接後至少不比純madmom差，且Outro有
   實質改善。
2. 逐段跟golden比殘差：Intro/Verse1/Chorus1 維持接近madmom的近乎
   完美表現（**最重要的安全底線**，如果這次修復不小心讓拼接機制
   誤傷這三段，就是失敗，要revert，不能將就）。
3. 確認 `madmom_hybrid_report.status` 是 `APPLIED`，不是
   `NO_WEAK_SPANS`（這正是這次要修的核心問題）。

### 5.3 測試

```
C:/Python313/python.exe -m pytest tests/test_sdd_pass236.py tests/test_sdd_pass202.py tests/test_module3_bt.py -q
```

全部要過，而且第1、3點新增的兩條測試要真的涵蓋這次修的瑕疵本身
（用真實資料/真實情境斷言，不能只是湊小規模合成數字通過）。

---

## 6. 明確排除（沿用 Pass236 任務書既有限制，這次不擴大範圍）

- 不要修改 `BarStartCandidateCommitNode._best_candidate()` 或任何 V2
  內部仲裁邏輯。
- 不要把 `madmom_hybrid_approved` 設成任何呼叫端的預設行為（需要
  使用者另外核准）。
- 不要在這個任務書裡順便重新設計「弱區段判斷依據」本身（用小節間距
  CV 這件事是 Pass236 已經定案的部分，這次只修實作瑕疵，不是重新
  設計判斷邏輯）。
- 不要嘗試修 Pass212 那個 V2 Intro syncopation 誤判的舊 bug。
- 不要在其他曲目做量化驗證（沒有其他曲目的 golden 基準，範圍留給
  之後）。
- 第4點是次要項目，非必要不強制修。

---

## 7. 完成後

1. 更新 `docs/BT-BUILD-PROGRESS.md`，新增 Pass237 條目：完整記錄
   三個問題各自修好後的驗證數字（校準結果、逐段殘差、
   `barstart_v2_score` 三方比較、`madmom_hybrid_report.status`）。
2. 更新使用者記憶檔案（如果是 Claude 執行）。
3. Commit + push 到 `origin/worktree-pass171-multi-variant-harness`，
   commit message 用 `fix(pass237): ...` 前綴。
