# Blackboard Contract v1.2.0

**最後更新：** 2026-07-23 (v1.2.0)

本文件記錄 PGMCraft Studio 主要 Behavior Tree 工作流的 blackboard key 契約。v1.2.0 新增 `PodcastSpeechNode`、`InstrumentPresenceNode`、`HybridPitchNode` 的 Key 契約，並更新 `DAWProfileRegistry` 的 `daw_profile` 選項。

## 契約欄位

每個主要節點可宣告：

- `required_keys`：節點執行前預期存在的 key
- `optional_keys`：節點可使用但不一定需要存在的 key
- `output_keys`：節點可能寫入的 key

這些欄位用於文件、測試與後續 GUI/debug 顯示。節點實際邏輯仍以目前 `execute()` 行為為準。

## Optional Validation

若 blackboard 中的 `validate_contracts` 為 `True`，`BaseNode.run()` 會在節點執行前檢查 `required_keys` 是否存在，並將結果追加到 `contract_validation`。

可透過 `BTWorkflowEngine.run(..., validate_contracts=True)` 或 `PGMCraftEngine(validate_contracts=True)` 啟用。

此檢查在 v1 為非阻斷式：

- 缺少 required key 時，`contract_validation.status` 會是 `WARN`。
- 節點仍會照原本 `execute()` 行為執行。
- 若節點本身因缺 key 或其他原因失敗，仍由原本節點邏輯回傳 `FAILURE` 或丟出例外。
- `PGMCraftEngine` 只有在存在 validation 結果時，才會將 `contract_validation` 寫入 `pgm_report.json`。

## Workflow Entry Keys

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `audio_path` | `str` | CLI / GUI / `BTWorkflowEngine` | 本地音檔路徑或 URL；若 URL 下載成功會被改寫成 WAV 路徑 |
| `output_dir` | `str` | CLI / GUI / `BTWorkflowEngine` | 產出目錄 |
| `enable_stem` | `bool` | CLI / GUI / `BTWorkflowEngine` | 是否啟用 experimental 分軌 |
| `demix_steps` | `list[str]` | optional caller | 分軌步驟，未提供時使用節點預設 |
| `validate_contracts` | `bool` | optional caller / `BTWorkflowEngine` | 是否啟用非阻斷式 contract validation |

## Audio Preparation Keys

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `downloaded_video_path` | `str or None` | `VideoURLDownloadNode` | URL 下載後的影片檔路徑 |
| `y` | array-like | `AudioLoadNode` | mono audio samples |
| `sr` | `int` | `AudioLoadNode` | sample rate |
| `target_analysis_path` | `str` | `AudioLoadNode` / `DemucsStemNode` | beat 分析目標音檔 |
| `stems` | `dict` | `DemucsStemNode` | experimental 分軌輸出 |

## Timing Analysis Keys

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `beats` | array-like Nx2 | `BeatNetNode` / `LibrosaBeatNode` | beat timestamp 與 beat number |
| `beat_validation` | `dict` | `BeatValidationNode` | beat 品質檢查結果 |
| `beat_confidence_level` | `str` | `BeatValidationNode` | `PASS` / `WARN` / `FAIL` |
| `beat_warnings` | `list[str]` | `BeatValidationNode` | 可繼續但需人工確認的警告 |
| `beat_errors` | `list[str]` | `BeatValidationNode` | 需停止流程的錯誤 |
| `refined_beats` | array-like Nx2 | `DownbeatRefineNode` | 補強 downbeat 後的 beat，timestamp 不變 |
| `downbeat_refinement` | `dict` | `DownbeatRefineNode` | downbeat 補強摘要 |
| `downbeat_refine_status` | `str` | `DownbeatRefineNode` | `PASS` / `WARN` / `FAIL` |
| `downbeat_refine_warnings` | `list[str]` | `DownbeatRefineNode` | downbeat 補強警告 |
| `downbeat_candidates` | `list[dict]` | `DownbeatRefineNode` | downbeat 候選 |
| `measure_map` | `list[dict]` | `MeasureMapNode` | 小節地圖 |
| `measure_map_status` | `str` | `MeasureMapNode` | `PASS` / `WARN` / `FAIL` |
| `measure_map_warnings` | `list[str]` | `MeasureMapNode` | 小節地圖警告 |

## Music Reference Keys

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `estimated_key` | `str` | `KeyChordAnalysisNode` | 調性參考 |
| `chord_progression` | `list[dict]` | `KeyChordAnalysisNode` | 小節和弦參考 |

## Export Keys

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `click_track` | `str` | `ClickSynthesisNode` | click WAV 路徑 |
| `mix_with_click` | `str` | `ClickSynthesisNode` | 原曲加 click 預聽檔 |
| `tempo_map_midi` | `str` | `MIDIExportNode` | DAW tempo map MIDI |
| `click_guide_midi` | `str` | `MIDIExportNode` | MIDI click guide |
| `vocal_pitch_midi` | `str` | `CREPEPitchNode` | CREPE 音高輪廓 MIDI |
| `pitch_contour_json` | `str` | `CREPEPitchNode` | CREPE 音高輪廓 JSON |
| `melody_lead_midi` | `str` | `BasicPitchNode` | Basic Pitch 主旋律 MIDI |
| `vocal_lead_quantized_midi` | `str` | `HybridPitchNode` | 雙音高融合量化主唱 MIDI |
| `subtitles_srt` | `str` | `PodcastSpeechNode` | 字幕 SRT 檔路徑 |
| `transcript_json` | `str` | `PodcastSpeechNode` | 逐字稿 JSON 路徑 |
| `instrument_presence_json` | `str` | `InstrumentPresenceNode` | 配器存在性矩陣 JSON |
| `instrument_matrix` | `list[dict]` | `InstrumentPresenceNode` | 逐小節配器動態矩陣 |
| `sections` | `list[dict]` | `SectionStructureNode` | 樂曲段落分析 |
| `sections_json` | `str` | `SectionStructureNode` | 樂曲段落結構 JSON 檔路徑 |
| `measure_map_json` | `str` | `MeasureMapNode` | 獨立小節地圖 JSON 檔路徑 |
| `quantized_beats` | array-like Nx2 | `AudioQuantizerNode` | 自動量化對齊網格後的節拍列表 |
| `quantization_offset_ms` | `float` | `AudioQuantizerNode` | 節拍網格微秒級平均對齊偏置 |
| `quantized_vocal_notes` | `list[dict]` | `MIDIQuantizerGuardNode` | 1/16 網格修復與微小碎音過濾後的音符列表 |
| `voice_split_midis` | `dict[str, str]` | `VoiceSplitMIDIExportNode` | 鋼琴左右手與吉低音/刷弦拆分後的 MIDI 路徑 |
| `ai_model_status` | `dict[str, str]` | AI Nodes | 記錄各 AI 模組實作狀態 (REAL_MODEL vs FALLBACK_DSP) |
| `daw_profile` | `str` | caller / CLI `--daw-profile` | 目標 DAW 導出格式 (reaper/ableton/logic/cubase/all) |

## Workflow Observability Keys

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `workflow_status` | `str` | `BTWorkflowEngine` | 整體 BT 執行狀態 |
| `workflow_trace` | `list[dict]` | `BaseNode.run()` | 節點執行順序、狀態、父節點與耗時 |
| `contract_validation` | `list[dict]` | `BaseNode.run()` | 非阻斷式節點契約檢查結果 |

Validation entry 格式：

```json
{
  "index": 0,
  "node": "AudioLoadNode",
  "node_type": "AudioLoadNode",
  "parent": "PGMCraftWorkflowRoot",
  "status": "PASS",
  "missing_required_keys": [],
  "required_keys": ["audio_path"],
  "optional_keys": [],
  "output_keys": ["y", "sr", "target_analysis_path"]
}
```

## 主要節點契約 (v1.2.0，16 個節點)

| Node | required_keys | optional_keys | output_keys |
|------|---------------|---------------|-------------|
| `VideoURLDownloadNode` | `audio_path` | `output_dir` | `audio_path`, `downloaded_video_path` |
| `AudioLoadNode` | `audio_path` |  | `y`, `sr`, `target_analysis_path` |
| `DemucsStemNode` | `audio_path`, `enable_stem` | `output_dir`, `demix_steps` | `stems`, `target_analysis_path` |
| `BeatNetNode` | `target_analysis_path` |  | `beats` |
| `LibrosaBeatNode` | `target_analysis_path` |  | `beats` |
| `BeatValidationNode` | `beats` |  | `beat_validation`, `beat_confidence_level`, `beat_warnings`, `beat_errors` |
| `DownbeatRefineNode` | `beats`, `beat_validation` |  | `refined_beats`, `downbeat_refinement`, `downbeat_refine_status`, `downbeat_refine_warnings`, `downbeat_candidates` |
| `MeasureMapNode` | `beats`, `beat_validation` | `refined_beats`, `downbeat_refinement` | `measure_map`, `measure_map_status`, `measure_map_warnings` |
| `SectionStructureNode` | `measure_map` | `y`, `sr`, `chord_progression` | `sections` |
| `KeyChordAnalysisNode` | `audio_path`, `beats` | `refined_beats` | `estimated_key`, `chord_progression` |
| `ClickSynthesisNode` | `audio_path`, `beats`, `output_dir` | `refined_beats` | `click_track`, `mix_with_click` |
| `MIDIExportNode` | `beats`, `output_dir` | `refined_beats`, `chord_progression` | `tempo_map_midi`, `click_guide_midi`, `chord_guide_midi` |
| `BasicPitchNode` | `audio_path`, `beats` | `output_dir`, `target_analysis_path` | `melody_lead_midi` |
| `CREPEPitchNode` | `audio_path` | `output_dir`, `y`, `sr` | `vocal_pitch_midi`, `pitch_contour_json` |
| `PodcastSpeechNode` | `audio_path` | `output_dir`, `y`, `sr` | `subtitles_srt`, `transcript_json` |
| `InstrumentPresenceNode` | `audio_path` | `output_dir`, `measure_map`, `y`, `sr` | `instrument_presence_json`, `instrument_matrix` |
| `HybridPitchNode` | `audio_path` | `output_dir`, `beats`, `y`, `sr` | `vocal_lead_quantized_midi` |


## BT 裝飾器節點

| 裝飾器節點 | 說明 |
|-----------|------|
| `RetryFallbackNode(child, max_retries, fallback)` | 對子節點重試 `max_retries` 次；全部失敗後切換 fallback 節點降級執行。適用 URL 下載與 AI 推論節點。 |
| `ParallelNode(children, success_threshold, max_workers)` | 使用 ThreadPoolExecutor 並行執行所有子節點。`success_threshold` 控制需幾個子節點成功才回傳 SUCCESS（預設全部）。AI 密集型節點 (BasicPitch/CREPE/InstrumentPresence/PodcastSpeech) 已移入 `AIAnalysisGroup` 並行組。 |


## DAWProfileRegistry

| Profile | 導出格式 |
|---------|----------|
| `reaper` | Reaper 專案 `.rpp` |
| `ableton` | Ableton Live `.als` |
| `logic` | Logic Pro Final Cut XML `.fcpxml` |
| `cubase` | Cubase Tempo Track `.csv` |
| `all` *(預設)* | 以上全部格式 |

## 後續方向

- 將契約轉成型別化 schema。
- 將目前非阻斷式 validation 接到 GUI/debug 面板。
- 讓 GUI 顯示節點缺少的 required key 與最近 trace entry。
- 為 URL 下載與 AI 節點套用 `RetryFallbackNode` 包裝器。
