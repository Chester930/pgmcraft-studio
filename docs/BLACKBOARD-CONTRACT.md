# Blackboard Contract v1

**最後更新：** 2026-07-23

本文件記錄 PGMCraft Studio 主要 Behavior Tree 工作流的 blackboard key 契約。v1 先做文件化與節點 metadata，不做 runtime 強制驗證。

## 契約欄位

每個主要節點可宣告：

- `required_keys`：節點執行前預期存在的 key
- `optional_keys`：節點可使用但不一定需要存在的 key
- `output_keys`：節點可能寫入的 key

這些欄位用於文件、測試與後續 GUI/debug 顯示。節點實際邏輯仍以目前 `execute()` 行為為準。

## Workflow Entry Keys

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `audio_path` | `str` | CLI / GUI / `BTWorkflowEngine` | 本地音檔路徑或 URL；若 URL 下載成功會被改寫成 WAV 路徑 |
| `output_dir` | `str` | CLI / GUI / `BTWorkflowEngine` | 產出目錄 |
| `enable_stem` | `bool` | CLI / GUI / `BTWorkflowEngine` | 是否啟用 experimental 分軌 |
| `demix_steps` | `list[str]` | optional caller | 分軌步驟，未提供時使用節點預設 |

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

## Workflow Observability Keys

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `workflow_status` | `str` | `BTWorkflowEngine` | 整體 BT 執行狀態 |
| `workflow_trace` | `list[dict]` | `BaseNode.run()` | 節點執行順序、狀態、父節點與耗時 |

## 主要節點契約

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
| `KeyChordAnalysisNode` | `audio_path`, `beats` | `refined_beats` | `estimated_key`, `chord_progression` |
| `ClickSynthesisNode` | `audio_path`, `beats`, `output_dir` | `refined_beats` | `click_track`, `mix_with_click` |
| `MIDIExportNode` | `beats`, `output_dir` | `refined_beats` | `tempo_map_midi`, `click_guide_midi` |

## 後續方向

- 將契約轉成型別化 schema。
- 在 debug/dev 模式加入 optional runtime validation。
- 讓 GUI 顯示節點缺少的 required key 與最近 trace entry。
