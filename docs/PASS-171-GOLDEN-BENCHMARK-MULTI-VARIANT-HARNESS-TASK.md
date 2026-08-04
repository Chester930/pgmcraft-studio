# Pass 171 任務書：黃金基準回歸鎖定與多版本並行比較框架 (GoldenBenchmark + Multi-Variant Harness)

**狀態**：基礎設施已實作並測試通過；實測 1 個完整變體後推翻了原始假設（見 2.1、2.2 節）——
真正的落差不在 Pass 168-170 BarStart v2 後處理節點，而更可能在 Stage 3
`BeatNetNode_TrackA` 的原始拍數決定性問題。多版本變體矩陣的目標已改為驗證這個新假設，
待使用者確認是否投入後續運算資源後再繼續（另開 Pass 172 任務書追蹤）。
**目標**：把使用者認定「本週音質最佳」的《World is Mine》click 固化為可回歸比對的黃金基準，
並建立一套能在同一份程式碼上、一次跑出多個 BarStart v2 後處理策略變體的比較框架，
讓使用者用實際聽感 + 客觀指標決定要往哪個方向修正 Pass 168/169/170 造成的回歸，
而不是由 AI 單方面猜測後直接改寫演算法。

---

## 0. 背景與問題

### 0.1 黃金基準的真實身分

2026-07-30 16:30 產出的
`d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\click\barstart_v2_mix_with_click.wav`
被使用者認定為本週音質最佳的一版。追查 `reports/module3_pipeline_report.json` 的
`workflow_trace` 與 `barstart_v2_report` 後發現：

- 這個檔案**不是** BarStart v2 產生的。真正決定輸出的節點鏈是舊版
  `BeatNetNode_TrackA/B → MultiModelBeatEnsembleNode → BeatFusionArbitratorNode →
  PerTrackBeatAnalysisNode → BeatGridSynthesisNode → DownbeatRefineNode →
  BeatGridContinuityRepairNode → DownbeatPhaseConsistencyNode →
  BeatAlignmentVerifierGuardNode/Fallback → CommercialBeatQualityNode`。
- `barstart_v2_report.status == "MERGED_DIAGNOSTIC_ONLY"` 且
  `does_not_replace_module3_click == true`：BarStart v2 當時只是旁路跑診斷，完全沒有影響最終輸出。
- 檔案時間戳（16:30）早於「Promote BarStart v2 for Module 3 click workflow」
  (`3f5827a`, 17:26) —— 也就是 BarStart v2 被扶正為預設決策來源**之前**。

該版 `reports/measure_map.json` 的實際指標：

| 指標 | 數值 |
|---|---|
| 小節數 | 121，**全部工整 4/4** |
| 涵蓋時長 | 完整 175.693469 秒（到 Outro 結尾） |
| 平均 BPM | 164.80（真實曲速約 165） |
| 相鄰小節 BPM 跳動 >35% | 0 次 |

而 pipeline 自己的 `commercial_beat_quality` 卻只打了 68.09/100（`NEEDS_MANUAL_EDIT`，
`workflow_status: FAILURE`）——因為 `anchor_alignment` 是拿 beat grid 去比對 BarStart v2
獨立偵測的 kick 錨點，這版根本沒用 BarStart v2，分數自然對不上。**這個內部分數目前無法
代表使用者聽感認定的品質**，見第 3 節的後續建議。

### 0.2 目前 BarStart v2（Pass 142 之後）在同一首歌的實測回歸

`3f5827a` 之後，`module3_barstart_v2_bt.py` 又疊加了 25 個 Pass（142→170），並在 Pass
141/142 拿掉原本 v1/v2 比較機制、把 BarStart v2 扶正為唯一路徑。用使用者現有的
`scratch/run_comparison_test.py`（Pass 167）與 `scratch/run_pass168_test.py`（Pass 168）
在同一首歌重新產出的 `outputs/comparison_test_pass167|168/.../reports/measure_map.json`
逐小節比對黃金版，量到兩個具體回歸點：

1. **尾奏小節遺失**：黃金版 121 小節 / 175.69 秒；目前只有 119 小節 / 171.39 秒，
   且最後一小節被截斷成只有 3 拍——`FullSongBarStartLoopNode` 在 Outro 附近信心不足、
   提早收尾。
2. **前奏相位偏移**：前 11 小節左右，小節起點系統性地比黃金版早了約 0.35 秒
   （約 1 拍），BPM 波動範圍也比黃金版寬（140.5–187.2 vs 147.7–181.6）。

`FullSongBarStartLoopNode.execute()` 收尾時，無條件依序執行三個新節點：

```python
TwoWayAnchorBacktraceNode().execute(blackboard)   # Pass 168：切分音搶拍反推
GroovePatternPhaseDecoderNode().execute(blackboard)  # Pass 169：反拍相位解碼
BarGridSanityPrunerNode().execute(blackboard)     # Pass 170：Ghost 殘片小節過濾
```

這三個節點都可能是回歸來源之一（或彼此交互放大），但目前沒有任何方式能單獨開關它們、
用實測數據定位，只能靠讀 5800 行程式碼臆測。這正是本 Pass 要解決的問題。

---

## 1. 設計與實作

### 1.1 `barstart_v2_postprocess_flags`：後處理節點旗標開關（已實作）

在不改變任何預設行為的前提下，讓 Pass 168/169/170 三個後處理節點可以被獨立開關：

- `pgm_craft/workflow/module3_barstart_v2_bt.py` — `FullSongBarStartLoopNode.execute()`：
  收尾前讀取 `blackboard.get_val("barstart_v2_postprocess_flags", {})`，
  依 `twoway_backtrace` / `groove_phase_decode` / `sanity_pruner` 三個 key
  （皆預設 `True`，與 Pass 170 行為完全相同）決定是否呼叫對應節點。
- `pgm_craft/workflow/builder.py` — `BTWorkflowEngine.run(..., barstart_v2_postprocess_flags=None)`：
  非 `None` 時寫入 blackboard，沿用既有 `user_meter_selection` / `allow_temporary_bar_delta`
  同款的「optional kwarg → blackboard.set_val」慣例。
- `pgm_craft/pipeline.py` — `PGMCraftEngine.run(..., barstart_v2_postprocess_flags=None)`：
  原樣轉發給 `BTWorkflowEngine.run()`。

呼叫端（例如 harness）只需要：

```python
engine.run(
    audio_path,
    output_dir=variant_dir,
    target_stage="module3",
    barstart_v2_postprocess_flags={"twoway_backtrace": True, "groove_phase_decode": True, "sanity_pruner": False},
)
```

### 1.2 `pgm_craft/golden_benchmark.py`：黃金基準統計與比對（已實作）

- `GOLDEN_WORLD_IS_MINE_STATS`：固化黃金版 `measure_map.json` 的統計數字
  （121 小節 / 175.693469 秒 / 平均 BPM 164.80 / 0 次 BPM 跳動 / 0 個不規則小節）。
- `compute_measure_map_stats(measure_map)`：從任意 `measure_map` 算出同一組指標
  （用每小節 `beat_count` 正規化成「4 拍等值時長」再換算 BPM，避免不規則小節污染平均值）。
- `compare_to_golden(stats, golden=None)`：回傳 candidate 相對黃金基準的差異，
  供 harness 與未來的 `tests/test_sdd_passN.py` 共用，不用兩邊各自重算一套指標。

### 1.3 多版本並行比較 harness（`scratch/run_pass171_variant_matrix.py`）

沿用使用者既有 `scratch/run_comparison_test.py` 的呼叫慣例（`PGMCraftEngine` +
`target_stage`），但做兩個關鍵調整：

1. **`target_stage="module3"` + 分軌重用**：黃金專案的 `stems/` 已經分離過一次，
   Demucs 等模型是整個 pipeline 最貴的部分。Harness 在每個變體資料夾建立
   `<variant_dir>/<project_name>/stems/`（`project_name` 沿用
   `ResolveProjectNameNode` 的同一套清洗規則）symlink（優先）/ junction / 複製
   （逐級 fallback）回黃金專案的 `stems/`，讓 5 個變體不用各自重跑一次分離，
   只重跑 Stage 3 節拍追蹤 + Module 3 BarStart v2 決策層。
2. **變體矩陣**：目前鎖定三個新節點的獨立/組合開關，共 5 個變體：

   | 變體 | twoway_backtrace | groove_phase_decode | sanity_pruner | 用途 |
   |---|---|---|---|---|
   | `v1_current_default` | ✅ | ✅ | ✅ | 現況（Pass 170 行為），對照組 |
   | `v2_no_sanity_pruner` | ✅ | ✅ | ❌ | 懷疑 Pass 170 過度合併/砍掉合法的短小節（尤其尾奏） |
   | `v3_no_groove_phase` | ✅ | ❌ | ✅ | 懷疑 Pass 169 反拍解碼在前奏誤判、造成相位偏移 |
   | `v4_no_twoway_backtrace` | ❌ | ✅ | ✅ | 懷疑 Pass 168 反推邏輯本身引入相位誤差 |
   | `v5_all_disabled` | ❌ | ❌ | ❌ | 最貼近 Pass 167（三個新節點都還沒加上去）的基準線 |

   每個變體輸出到 `outputs/pass171_variants/<variant_name>/`，包含完整
   `click/mix_with_click.wav`（供試聽 A/B）與 `reports/measure_map.json`。

3. **比較報告**：跑完全部變體後，用 `golden_benchmark.compute_measure_map_stats` +
   `compare_to_golden` 對每個變體算指標，寫成
   `outputs/pass171_variants/comparison_report.json` 與終端機表格，欄位包含：
   小節數差、涵蓋時長差、BPM 跳動次數、不規則小節數、與黃金版的平均/最低/最高 BPM 差。

**這一步刻意不自動選出「最佳」變體**——數字只能告訴你哪個變體在指標上更接近黃金版，
無法告訴你哪個聽起來最準。使用者聽過 5 個 `mix_with_click.wav` 後選出的方向，
才是下一個 Pass（172）要正式落地的修正範圍。

---

## 2. 驗證方式

1. `tests/test_sdd_pass171.py`（7 項，已通過）：
   - `compute_measure_map_stats` 對工整 4/4 網格、含不規則小節的網格，數字正確。
   - `compare_to_golden` 對「119 小節 / 171.39 秒」形狀的網格，正確算出 `total_measures: -2`
     且 `total_duration_sec < 0`（即目前 BarStart v2 回歸的可回歸驗證）。
   - `FullSongBarStartLoopNode` 在未指定旗標時，行為與 Pass 170 完全相同
     （三個後處理節點都執行）；指定旗標時，能各自獨立跳過對應節點，且不影響其他兩個。
2. 執行既有回歸測試確認未破壞既有行為：
   `pytest tests/test_sdd_pass168.py tests/test_sdd_pass169.py tests/test_sdd_pass170.py tests/test_module3_bt.py`
   （16 項全通過）。
3. 執行 `scratch/run_pass171_variant_matrix.py` 對《World is Mine》實際跑出 5 個變體，
   產生 `outputs/pass171_variants/comparison_report.json` + 5 份可試聽的 `mix_with_click.wav`。
4. 使用者聽過 5 個變體後，回報偏好方向 → 開新的 Pass 172 任務書，正式把選中的策略
   （例如：放寬 `BarGridSanityPrunerNode` 的 ghost 判定門檻、或替 `GroovePatternPhaseDecoderNode`
   加上前奏低能量段落的信心保護）落地為預設行為，並移除/收斂本 Pass 引入的旗標
   （旗標只是比較工具，不是要長期存在的設定項）。
5. 更新 `docs/BT-BUILD-PROGRESS.md` 並 commit/push/PR。

---

## 2.1 重大修正（實測後推翻原本歸因）

實際跑 `v1_current_default` 變體（耗時 1407 秒）後，檢查其
`module3_pipeline_report.json`：

```json
"barstart_v2_report": {
  "status": "COMPARED_NOT_PROMOTED",
  "replaces_module3_click": false
}
```

**BarStart v2（連同 Pass 168/169/170 三個後處理節點）這次完全沒有被採用**——真正決定
`measure_map.json` / click 音軌的是舊版 `BeatFusionArbitratorNode` 雙軌融合鏈。也就是說
第 1.1 節做的 `barstart_v2_postprocess_flags` 旗標，開關的是一段**跟目前最終輸出無關**
的診斷分支——這個旗標機制本身沒問題（已測試、向下相容），但**不是**這次回歸的真正槓桿，
繼續用它跑變體矩陣不會改變輸出。

進一步從這次完整 log 追查，實際決定 `measure_map` 的鏈是：

```
BeatNetNode_TrackA (477拍) / TrackB (329拍) → MultiModelBeatEnsembleNode (融合536拍候選)
→ BeatFusionArbitratorNode (最終採納 A軌431 + B軌補46 = 477拍)
→ ... → BeatGridSynthesisNode (477 canonical beats) → ... → MeasureMapNode (119小節)
```

477 拍 ÷ 4 ≈ 119 小節，跟這次量到的小節數完全對上；而下游的
`ViterbiTempoSmoothingNode`／`BeatGridContinuityRepairNode`／`OnsetPhaseRealignmentNode`／
`MicroTimingTransientSnapNode` 這些「精修守衛」節點只會微調拍點時間或做極小幅度的
補洞/去重（這次 log 顯示 `BeatGridContinuityRepairNode` 只淨增 1 拍），**不是**造成
119 vs 121（黃金版）落差的主因。**真正的分歧點，落在 `BeatNetNode_TrackA` 本身抓到的
原始拍數（477），以及 `BeatFusionArbitratorNode` 的雙軌仲裁決策**——這條鏈從黃金版
（7/29 提交）到現在同樣疊加了不少 Pass（例如 Pass 163「升級 BeatFusionArbitratorNode
仲裁時間軸記錄與 v1 網格速度慣性約束」），但目前還沒有旗標可以獨立開關這些調整。

**狀態**：截至本次更新，尚未針對這條真正的鏈路建立旗標開關與變體矩陣。每次完整變體
實測成本約 23 分鐘（`target_stage="module3"` 仍會重跑完整分軌），因此先對
`BeatFusionArbitratorNode` 做了一輪靜態比對（不花運算資源），結果見下一節——**這個
靜態比對本身就推翻了「BeatFusionArbitratorNode 邏輯跑掉」的假設，把問題導向一個更根本、
也更難靠改程式碼解決的方向**。

## 2.2 靜態比對結果：融合節點邏輯沒變，真正落差在 BeatNet 原始拍數

把 `BeatFusionArbitratorNode`（`pgm_craft/workflow/beat_tracking_bt.py`）從黃金基準時期
的提交（`793d8ba`，2026-07-29）跟目前 HEAD 逐行比對：

- **核心演算法結構完全沒變**：兩個版本都是「以 A 軌 (`beats_rhythm`，鼓+Bass) 的時間軸為
  骨架，逐拍走訪；A 軌能量夠時原樣採用，能量不足時（無鼓 Intro/Breakdown）用 B 軌候選或
  速度慣性內插取代」——**輸出拍數恆等於 `len(beats_a)`，不會增加也不會減少拍子**。
- 期間唯一的實質變化是 Pass 163：低能量段落內插時，優先參考 `v1_reference_beat_grid`
  的真實步距（而非單純用前 2 拍步距假設等速）——這只影響「內插拍點的時間位置」，
  不影響「拍點總數」。

也就是說，這次實測拿到的 477 拍（119 小節），**477 這個數字是 `BeatNetNode_TrackA`
（Stage 3 dual-track 分析的 A 軌）自己偵測出來的原始拍數**（log: `[BeatNetNode_TrackA]
Tracked 477 beats via BeatNet DBN.`），跟 `BeatFusionArbitratorNode` 之後怎麼仲裁完全
無關——它只是原樣把 477 拍的骨架轉手過去。而黃金版的 `beat_validation.total_beats` 是
485（見 Pass 171 分析初期蒐證），兩者差了約 8 拍 ≈ 2 小節，跟量到的小節數落差完全吻合。

**這把問題導向一個完全不同、也更棘手的方向**：真正的分歧不在任何一個「Pass 141-170
新增的節點」裡，而在於 `BeatNetNode_TrackA` 這次對同一首歌的鼓+Bass 節奏骨幹軌
（`SynthesizeRhythmTrackNode` 合成）偵測出的原始拍數，跟黃金版當時不一樣。可能原因：

1. **Demucs 分軌本身不是逐次一致的**：這次 harness 每個變體都會重新跑一次 Demucs
   （`target_stage="module3"` 不會跳過 Stage 2，見 2.1 節），鼓/貝斯分離結果就算同一首歌
   也可能有極細微差異，餵進 BeatNet 後可能改變它抓到的拍點數。
2. **BeatNet 或其相依套件版本 / 環境在這幾天內有變動**，導致同樣輸入的推論結果不同。
3. 也有可能是這段期間某個 Stage 3「準備階段」節點（`SynthesizeRhythmTrackNode` /
   `PrepareInstrumentalTrackNode` 等）的程式碼改變了餵給 BeatNet 的音訊內容。

**這意味著：靠「開關某個 Pass 新增的節點」這種變體矩陣，很可能量不到真正的差異來源**
——因為問題點在更早的「同一份音訊，BeatNet 這次抓到的拍子比較少」，而不是任何一個
後製節點的邏輯退步。要證實這個假設，下一步該做的實驗是**決定性/一致性檢查**：對「同一份
已經分離好、不再重跑 Demucs 的鼓 stem」跑兩次 `BeatNetNode_TrackA`，看輸出拍數是否穩定
（若不穩定 → 模型/環境本身非決定性，不是哪個 Pass 的錯；若穩定但仍是 477 → 代表分軌內容
本身跟黃金版當時不同，要往 `SynthesizeRhythmTrackNode` 或 Demucs 模型版本去查）。

這已經超出「開關 Pass 168-170 旗標、跑變體矩陣比較」的原始範圍，牽涉到模型/環境層級的
決定性問題，已另開 `docs/PASS-172-STAGE3-BEATNET-DETERMINISM-VERIFICATION-TASK.md` 處理。

**Pass 172 結論先劇透**：用黃金專案本身的節奏骨幹軌重跑兩次 BeatNet，兩次都精確複現
黃金版的 485 拍——證實 BeatNet 本身是決定性的，477 vs 485 的落差其實出在**每次重新分離
出的 drums/bass 音訊內容本身不是逐 byte 相同**（很可能是 Demucs 的 test-time shift
augmentation 沒有被 `enable_deterministic_mode()` 完全覆蓋），不是任何節拍追蹤或
BarStart v2 節點的邏輯問題。詳見該任務書第 3 節。

## 3. 延伸建議（非本 Pass 範圍，留給後續 Pass）

- `commercial_beat_quality` 的 `anchor_alignment` 目前是拿 beat grid 比對 BarStart v2
  自己偵測的 kick 錨點，導致「沒有用 BarStart v2 的舊方法」天生就會被扣分，
  跟聽感脫鉤。建議另外設計一個不依賴 BarStart v2 內部產物的獨立品質指標
  （小節長度一致性、BPM 跳動次數、與已知真實 BPM 的誤差），才能真正對應
  使用者耳朵判斷的「品質最好」。
- 目前 `Module3BarStartV2MergeNode` 已經有「v2 不完整時不促銷」的邏輯
  （見 `tests/test_module3_bt.py::test_module3_barstart_v2_merge_node_compares_but_does_not_promote_when_v2_incomplete`），
  但實測上 Pass 167/168 仍然出現明顯的 BarStart v2 特有回歸痕跡，值得在 Pass 172
  一併確認促銷判斷的門檻是否夠嚴謹。
