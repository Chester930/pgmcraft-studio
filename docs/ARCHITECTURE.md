# 系統架構

**最後更新：** 2026-07-29 (Stage 3 beat tracking 架構校準)

## 架構風格

PGMCraft Studio 採用節點式音訊工作流，並使用 Behavior Tree 進行流程編排與 Quality Guard 品質估測防禦。

預期架構如下：

```text
輸入來源 (音檔 / Video URL / 資料夾 Batch)
  -> 品質檢測 Guard 節點 (Pass 0: Crowd Noise Filter)
  -> 剝洋蔥迭代分軌 (Pass 1 ~ Pass 4: Trio Peel & Subtract)
  -> 標的式 Sub-Mix 合成 (Rhythm / Harmonic / Structure Sub-Mix)
  -> 聲部導向 MIDI 切分 & Legato 重疊修復 (Piano / Guitar / Vocal)
  -> Blackboard 狀態 & Behavior Tree 廣播
  -> 3 大 DAW Bus 路由 (Rhythm -3dB / Music -6dB / Vocal 0dB)
  -> EBU R128 (-14 LUFS, Peak <= -1.0 dBFS) 預聽檔 & SVG 彩色結構地圖
  -> 工程素材包純淨 ZIP 導出
```


這種設計讓專案能逐步成長。新能力應該先被實作成節點，再接入 Behavior Tree。

## 核心概念

### Node

Node 是一個小型、單責任的工作單位。

範例：

- 判斷輸入是否為 URL
- 下載媒體
- 載入音訊
- 檢查訊號品質
- 執行 beat tracking
- 匯出 MIDI
- 合成 click 音訊
- 寫出報告

節點不應擁有整條流程。節點應從 blackboard 讀取必要值、完成一件明確工作、把結果寫回 blackboard，並回傳執行狀態。

### Blackboard

Blackboard 是節點之間共享的工作流狀態。

常見 key：

- `audio_path`
- `output_dir`
- `y`
- `sr`
- `target_analysis_path`
- `beats`
- `beat_validation`
- `beat_confidence_level`
- `beat_warnings`
- `beat_errors`
- `refined_beats`
- `downbeat_refinement`
- `downbeat_refine_status`
- `downbeat_refine_warnings`
- `downbeat_candidates`
- `measure_map`
- `measure_map_status`
- `measure_map_warnings`
- `estimated_key`
- `chord_progression`
- `click_track`
- `mix_with_click`
- `tempo_map_midi`
- `click_guide_midi`
- `project_package_dir`
- `import_guide`
- `stems`
- `workflow_status`
- `workflow_trace`
- `validate_contracts`
- `contract_validation`
- `beats` / `refined_beats` 會被寫入 `pgm_report.json`，供 reference evaluation 與 DAW 對拍檢查使用
- `beat_precision_diagnostics` 會保存 phase realignment、transient snap、downbeat verifier、tempo smoothing 與 fallback 診斷摘要

主要 key 已在 `docs/BLACKBOARD-CONTRACT.md` 文件化。後續可進一步轉成型別化 schema，降低隱性耦合。

### Behavior Tree

Behavior Tree 決定節點執行順序與 fallback 行為。

目前核心形狀：

```text
Root Sequence
├── Input Acquisition
├── Audio Quality
├── Stem Separation
├── BeatTrackingRoot
│   ├── SynthesizeRhythmTrackNode
│   ├── PrepareInstrumentalTrackNode
│   ├── KickSnarePulseNode
│   ├── TrackA_RhythmBranch
│   │   └── BeatNetFallbackA: BeatNetSingleTrackNode -> LibrosaSingleTrackNode
│   ├── TrackB_InstrumentalBranch
│   │   └── BeatNetFallbackB: BeatNetSingleTrackNode -> LibrosaSingleTrackNode
│   ├── MultiModelBeatEnsembleNode
│   ├── BeatFusionArbitratorNode
│   ├── ReEntryReAnchoringNode
│   ├── BeatValidationNode
│   ├── DownbeatRefineNode
│   ├── OnsetPhaseRealignmentNode
│   ├── MicroTimingTransientSnapNode
│   ├── KickBassDownbeatVerifierNode
│   ├── ViterbiTempoSmoothingNode
│   └── BeatAlignmentVerificationAndFallback
├── Music Analysis
├── Export
└── Package
```

這個結構代表：

- 必要前置步驟依序執行
- 選用 stem separation 可以跳過
- BeatNet 是優先候選；Librosa 是 deterministic fallback
- 節拍分析以 rhythm track 與 instrumental track 雙軌估計，避免只依賴全曲混音或單一鼓軌
- ensemble / fusion 節點只能做候選融合，不應取代可量化的 reference evaluation
- beat validation 會在分析後先判斷是否可繼續輸出
- downbeat refinement 只補強 downbeat 標籤；後續 onset / transient snap 節點才允許在小範圍內移動 timestamp
- Viterbi / tempo smoothing 是 guard，不能把 rubato、變拍號或自由速度素材無條件拉直
- 小節資料模型需要允許同一首歌內出現不同小節長度
- measure map 會保留每一小節自己的 `beat_count`，缺 downbeat 時只能標記為 fallback
- 匯出節點只在分析成功後執行
- `BaseNode.run()` 會記錄 `workflow_trace`，讓執行後可檢查節點順序、狀態與耗時。
- `validate_contracts=True` 時會記錄非阻斷式 `contract_validation`，協助開發時檢查節點 required key。

架構判斷依據：

- BeatNet / BeatNet+：neural beat/downbeat salience + temporal inference 是高精度 tracker 的主流方向。
- librosa / Ellis dynamic programming：適合作為低依賴 fallback，但不應單獨宣稱 downbeat 精準。
- madmom：RNN activation + DBN post-processing 顯示「模型候選 + 時序推論」是成熟設計，但 DBN 假設需要 guard。
- Beat This!：提醒固定 DBN/固定拍號假設會傷害變拍號、rubato 與非典型素材；PGMCraft 的 smoothing 應保守。
- MIREX / mir_eval：最終精度必須以 annotated beats 做 F-measure、CML/AML、Cemgil 等評估。

## 節點分類

### 輸入節點

目的：

- 接收本地檔案或 URL
- 需要時下載媒體
- 驗證可用音訊

候選節點：

- `InputSourceNode`
- `URLDetectNode`
- `MediaDownloadNode`
- `AudioExtractNode`
- `AudioValidateNode`

### 預處理節點

目的：

- 為穩定分析準備音訊

候選節點：

- `AudioLoadNode`
- `SNRGuardNode`
- `DenoiseNode`
- `LoudnessNormalizeNode`
- `PhaseAlignNode`
- `ChunkingNode`

### 分析節點

目的：

- 擷取音樂時間與參考資訊

候選節點：

- `BeatNetNode`
- `LibrosaBeatNode`
- `BeatValidationNode`
- `DownbeatDetectNode`
- `MeasureMapNode`
- `KeyAnalysisNode`
- `ChordAnalysisNode`

### 匯出節點

目的：

- 建立可用於 DAW、練團與 PGM 的素材

候選節點：

- `ClickSynthesisNode`
- `ClickMixNode`
- `MIDIExportNode`
- `MidiClickGuideNode`
- `TempoPlotNode`
- `ReportJsonNode`
- `ReportTextNode`
- `ProjectPackageNode`

### AI 擴充節點

目的：

- 在不破壞 MVP 工作流的前提下，整合選用模型功能

候選節點：

- `StemSeparationNode`
- `InstrumentPresenceGuardNode`
- `MusicTranscriptionNode`
- `PitchTrackingNode`
- `SpeechTranscriptionNode`
- `SpeakerDiarizationNode`

在依賴、模型檔、執行需求與測試完整前，這些節點應維持 optional。

## Guard 與 Fallback 策略

Guard node 用來判斷某個分支是否應該執行。

範例：

- 音訊音量是否足夠
- 某樂器是否可能存在
- 模型前置條件是否滿足
- optional dependency 是否已安裝

Fallback node 用來提供替代方案。

範例：

- BeatNet 失敗後改跑 Librosa
- URL 下載失敗後讓使用者改上傳本地音檔
- 高品質 AI 模型不可用時改走 deterministic fallback

## 第一版公開架構邊界

第一個正式版本的穩定架構邊界應是：

```text
來源輸入 -> Beat/Tempo 分析 -> DAW/PGM 工程素材輸出
```

AI 分軌與 Podcast 工作流在真正完成與測試前，應被記錄為 extension branch。

## 目前實作對照

| 區域 | 目前檔案 | 目前狀態 |
|------|----------|----------|
| GUI | `app.py` | Gradio app，含下載、分軌與 PGM 頁籤 |
| CLI | `pgm_craft/cli.py` | 執行主要 PGM pipeline |
| Pipeline | `pgm_craft/pipeline.py` | 將 Behavior Tree 結果整理成 report，包含完整 beat grid 與精度診斷 |
| Beat Evaluation | `pgm_craft/beat_evaluation.py` | 以 reference annotation 比對 beat/downbeat，輸出 F-measure 與 offset 統計 |
| BT Core | `pgm_craft/workflow/nodes.py` | Sequence、fallback、blackboard 基礎 |
| BT Builder | `pgm_craft/workflow/builder.py` | 定義主要工作流 |
| Audio Nodes | `pgm_craft/workflow/audio_nodes.py` | 下載、載入、節拍、分析、匯出節點 |
| Analysis | `pgm_craft/analyzer.py` | BeatNet 或 Librosa、調性與和弦分析 |
| Export | `pgm_craft/synthesizer.py` | Click WAV 與 MIDI 輸出 |
| Package | `pgm_craft/packager.py` | 建立 DAW/PGM 工程素材包與匯入說明 |
| Stem Separation | `pgm_craft/separator.py` | 目前多為 copy-based placeholder |
| AI Music | `pgm_craft/music_ai.py` | 實驗性 wrapper 與 fallback |
| Podcast | `pgm_craft/podcast_ai.py` | placeholder 輸出 |
| Legacy | `main.py`, `web_app.py`, `beat_tracker.py` | 較早期的 standalone pipeline |

## 設計規則

新增能力時，依序處理：

1. 建立或更新一個聚焦節點
2. 定義必要 blackboard inputs
3. 定義 blackboard outputs
4. 需要時加入 guard 或 fallback
5. 接入 Behavior Tree
6. 測試節點與工作流路徑
7. 更新本文件

## Reference Evaluation

`pgm_report.json` 會保留完整 `beats` 與 `refined_beats`，避免只留下 `total_beats` 而無法客觀比對。CLI 可用以下參數執行 reference-based 驗收：

```bash
pgm-craft --audio song.wav --output outputs/song_eval --reference-beats annotations/beats.txt --reference-downbeats annotations/downbeats.txt
```

評估輸出為 `beat_evaluation.json`。預設 matching tolerance 是 0.07 秒，對齊 MIREX / mir_eval 常用 beat/downbeat F-measure window。這個評估仍不能取代最終人工聽感與 DAW grid 檢查，但它能把半速、雙速、整體 phase shift、downbeat 反相與毫秒偏移用數字暴露出來。
