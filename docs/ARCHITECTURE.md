# 系統架構

**最後更新：** 2026-07-22

## 架構風格

PGMCraft Studio 採用節點式音訊工作流，並使用 Behavior Tree 進行流程編排。

預期架構如下：

```text
輸入來源
  -> 工作流節點
  -> Blackboard 狀態
  -> Behavior Tree 編排
  -> 工程素材包輸出
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
- `stems`

隨著專案成熟，這些 key 應該文件化或型別化，降低隱性耦合。

### Behavior Tree

Behavior Tree 決定節點執行順序與 fallback 行為。

目前核心形狀：

```text
Root Sequence
├── VideoURLDownloadNode
├── AudioLoadNode
├── DemucsStemNode
├── Fallback: BeatTrackingSelector
│   ├── BeatNetNode
│   └── LibrosaBeatNode
├── BeatValidationNode
├── DownbeatRefineNode
├── MeasureMapNode
├── KeyChordAnalysisNode
├── ClickSynthesisNode
└── MIDIExportNode
```

這個結構代表：

- 必要前置步驟依序執行
- 選用 stem separation 可以跳過
- BeatNet 是優先方案
- Librosa 是 fallback
- beat validation 會在分析後先判斷是否可繼續輸出
- downbeat refinement 只能補強 downbeat 標籤，不應移動 beat timestamp
- 小節資料模型需要允許同一首歌內出現不同小節長度
- measure map 會保留每一小節自己的 `beat_count`，缺 downbeat 時只能標記為 fallback
- 匯出節點只在分析成功後執行

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
| Pipeline | `pgm_craft/pipeline.py` | 將 Behavior Tree 結果整理成 report |
| BT Core | `pgm_craft/workflow/nodes.py` | Sequence、fallback、blackboard 基礎 |
| BT Builder | `pgm_craft/workflow/builder.py` | 定義主要工作流 |
| Audio Nodes | `pgm_craft/workflow/audio_nodes.py` | 下載、載入、節拍、分析、匯出節點 |
| Analysis | `pgm_craft/analyzer.py` | BeatNet 或 Librosa、調性與和弦分析 |
| Export | `pgm_craft/synthesizer.py` | Click WAV 與 MIDI 輸出 |
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
