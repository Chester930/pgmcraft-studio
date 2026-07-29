# Blackboard Contract v1.3.0

**最後更新：** 2026-07-29 (v1.3.0)

本文件記錄 PGMCraft Studio 主要 Behavior Tree 工作流的 blackboard key 契約。v1.3.0 更新 Stage 3 雙軌 beat tracking、ensemble/fusion、相位校準與 fallback 重算的 Key 契約。

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
| `rhythm_track_path` | `str` | `SynthesizeRhythmTrackNode` | A 軌節奏骨幹分析目標 |
| `inst_track_path` | `str` | `PrepareInstrumentalTrackNode` | B 軌伴奏分析目標 |
| `beats_rhythm` | array-like Nx2 | `BeatNetSingleTrackNode` / `LibrosaSingleTrackNode` | A 軌候選 beat timestamp 與 beat number |
| `beats_inst` | array-like Nx2 | `BeatNetSingleTrackNode` / `LibrosaSingleTrackNode` | B 軌候選 beat timestamp 與 beat number |
| `conf_rhythm` | `float` | `TrackValidationNode` | A 軌節拍 confidence |
| `conf_inst` | `float` | `TrackValidationNode` | B 軌節拍 confidence |
| `kick_anchors` | array-like | `KickSnarePulseNode` | kick / sub-bass 脈衝錨點 |
| `snare_anchors` | array-like | `KickSnarePulseNode` | snare 脈衝錨點 |
| `ensemble_beats` | array-like Nx2 | `MultiModelBeatEnsembleNode` | A/B 軌共識候選 |
| `ensemble_confidence` | `float` | `MultiModelBeatEnsembleNode` | A/B 軌共識比例 |
| `beat_fusion_report` | `dict` | `BeatFusionArbitratorNode` | A/B 軌融合統計 |
| `beats` | array-like Nx2 | Stage 3 canonical beat chain | 目前最新版 beat timestamp 與 beat number |
| `beat_validation` | `dict` | `BeatValidationNode` | beat 品質檢查結果 |
| `beat_confidence_level` | `str` | `BeatValidationNode` | `PASS` / `WARN` / `FAIL` |
| `beat_warnings` | `list[str]` | `BeatValidationNode` | 可繼續但需人工確認的警告 |
| `beat_errors` | `list[str]` | `BeatValidationNode` | 需停止流程的錯誤 |
| `refined_beats` | array-like Nx2 | `DownbeatRefineNode` / snap / smoothing / fallback | 與 canonical `beats` 同步的最終 beat 陣列 |
| `downbeat_refinement` | `dict` | `DownbeatRefineNode` | downbeat 補強摘要 |
| `downbeat_refine_status` | `str` | `DownbeatRefineNode` | `PASS` / `WARN` / `FAIL` |
| `downbeat_refine_warnings` | `list[str]` | `DownbeatRefineNode` | downbeat 補強警告 |
| `downbeat_candidates` | `list[dict]` | `DownbeatRefineNode` | downbeat 候選 |
| `phase_realignment_report` | `dict` | `OnsetPhaseRealignmentNode` | onset 相位微調統計 |
| `snap_offsets_ms` | `list[float]` | `MicroTimingTransientSnapNode` | transient snap 偏移量 |
| `downbeat_fix_report` | `dict` | `KickBassDownbeatVerifierNode` | 低頻 downbeat 修正摘要 |
| `smoothing_report` | `dict` | `ViterbiTempoSmoothingNode` | interval outlier 平滑摘要 |
| `beat_alignment_score` | `float` | `BeatAlignmentVerifierGuardNode` | section/kick anchor 閉環對齊分數 |
| `fallback_beat_recalculated` | `bool` | `DrumsKickBeatFallbackNode` | 是否啟動鼓軌 fallback 重算 |
| `measure_map` | `list[dict]` | `MeasureMapNode` | 小節地圖 |
| `measure_map_status` | `str` | `MeasureMapNode` | `PASS` / `WARN` / `FAIL` |
| `measure_map_warnings` | `list[str]` | `MeasureMapNode` | 小節地圖警告 |

## Module 3 Beat/Click Keys

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `beat_candidate_tracks` | `dict` | `CandidateTrackBuildNode` | full_mix / rhythm / band / vocal 四軌候選來源、路徑與權重 |
| `full_mix_track_path` | `str` | `CandidateTrackBuildNode` | 原曲或降噪後音檔 |
| `rhythm_track_path` | `str` | `CandidateTrackBuildNode` | drums+bass 節奏骨幹；無 stems 時 fallback 原曲 |
| `band_track_path` | `str` | `CandidateTrackBuildNode` | drums+bass+guitar+piano；無法合成時 fallback no_vocals / instrumental |
| `vocal_track_path` | `str or None` | `CandidateTrackBuildNode` | vocals / lead_vocal，僅作 phrase 輔助來源 |
| `beat_candidates` | `dict` | `PerTrackBeatAnalysisNode` | 每一候選來源的 beat array 與 metadata |
| `beats_full_mix` | array-like Nx2 | `PerTrackBeatAnalysisNode` | full mix 候選拍點 |
| `beats_band` | array-like Nx2 | `PerTrackBeatAnalysisNode` | band 候選拍點 |
| `beats_vocal` | array-like Nx2 | `PerTrackBeatAnalysisNode` | vocal 候選拍點 |
| `analysis_segments` | `list[dict]` | `SegmentGridNode` | 小節或 4 拍分析區間 |
| `per_segment_confidence` | `list[dict]` | `PerSegmentConfidenceNode` | 每段每軌可信度、coverage、stability、energy |
| `segment_source_map` | `list[dict]` | `SegmentSourceAttributionNode` | 每段 primary source、supporting sources 與選用原因 |
| `beat_synthesis_report` | `dict` | `BeatGridSynthesisNode` | 最終 beat grid 的分段合成來源摘要 |
| `subdivision_grid` | `list[dict]` | `SubdivisionGridNode` | 8 分音符分析 grid |
| `click_grid` | `list[dict]` | `SubdivisionGridNode` | 4 分音符 click grid |
| `syncopation_events` | `list[dict]` | `SyncopationClassificationNode` | 切分、提前音、phrase onset 標註 |
| `snap_exclusion_zones` | `list[dict]` | `SyncopationClassificationNode` | 不允許 click snap 的 transient 區間 |
| `backing_with_click_status` | `str` | `Module3BackingWithClickNode` | `EXPORTED` 或 `SKIPPED_NO_NO_VOCAL_SOURCE` |
| `module3_outputs` | `dict` | `Module3OutputSummaryNode` / `PGMCraftEngine` | 模塊三 output manifest，包含 `test_project_dir`、`source_dir`、`stems_dir`、`click_dir`、`reports_dir`、`candidate_tracks`、click/mix/backing/report 路徑 |
| `module3_report_json` | `str` | `Module3OutputSummaryNode` | `module3_beat_click_report.json` 路徑 |
| `project_package_status` | `str` | `PGMCraftEngine` | `module3` 時固定為 `SKIPPED_MODULE3_TEST_PROJECT`，表示未進入完整 PGM/DAW package |

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

## Report / Evaluation Outputs

這些欄位不一定是 blackboard key；它們由 `PGMCraftEngine` 或 CLI 將 blackboard 結果序列化後寫入 report。

| Key | 型態 | 來源 | 說明 |
|-----|------|------|------|
| `beats` | `list[list[time_seconds, beat_number]]` | `PGMCraftEngine` | Stage 3 canonical beat grid 的 JSON-safe 版本 |
| `refined_beats` | `list[list[time_seconds, beat_number]]` | `PGMCraftEngine` | 最終採用的 beat grid；click/MIDI/reference evaluation 以此為優先 |
| `beat_precision_diagnostics` | `dict` | `PGMCraftEngine` | phase realignment、transient snap、downbeat verifier、smoothing 與 fallback 摘要 |
| `beat_evaluation` | `dict` | CLI `--reference-beats` / `--reference-downbeats` | reference annotation 比對結果 |
| `outputs.beat_evaluation_json` | `str` | CLI reference evaluation | `beat_evaluation.json` 路徑 |

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

## 主要節點契約 (v1.3.0)

| Node | required_keys | optional_keys | output_keys |
|------|---------------|---------------|-------------|
| `VideoURLDownloadNode` | `audio_path` | `output_dir` | `audio_path`, `downloaded_video_path` |
| `AudioLoadNode` | `audio_path` |  | `y`, `sr`, `target_analysis_path` |
| `DemucsStemNode` | `audio_path`, `enable_stem` | `output_dir`, `demix_steps` | `stems`, `target_analysis_path` |
| `SynthesizeRhythmTrackNode` |  | `stems`, `stems_dir`, `audio_path`, `rhythm_submix` | `rhythm_track_path` |
| `PrepareInstrumentalTrackNode` |  | `stems`, `stems_dir`, `audio_path` | `inst_track_path` |
| `KickSnarePulseNode` |  | `stems`, `stems_dir` | `kick_anchors`, `snare_anchors` |
| `BeatNetSingleTrackNode` | configured input key |  | configured beats key |
| `LibrosaSingleTrackNode` | configured input key |  | configured beats key |
| `TrackValidationNode` | configured beats key |  | configured confidence key |
| `MultiModelBeatEnsembleNode` | `beats_rhythm`, `beats_inst` | `rhythm_track_path`, `inst_track_path`, `audio_path`, `stems` | `ensemble_beats`, `ensemble_confidence` |
| `BeatFusionArbitratorNode` | `beats_rhythm`, `beats_inst` | `y_rhythm`, `sr_rhythm`, `rhythm_track_path` | `beats`, `beat_fusion_report` |
| `ReEntryReAnchoringNode` |  | `beats`, `kick_anchors`, `y_rhythm`, `sr_rhythm` | `beats` |
| `BeatValidationNode` | `beats` |  | `beat_validation`, `beat_confidence_level`, `beat_warnings`, `beat_errors` |
| `DownbeatRefineNode` | `beats`, `beat_validation` |  | `refined_beats`, `downbeat_refinement`, `downbeat_refine_status`, `downbeat_refine_warnings`, `downbeat_candidates` |
| `OnsetPhaseRealignmentNode` | `beats`, `y`, `sr` |  | `beats`, `phase_realignment_report` |
| `MicroTimingTransientSnapNode` | `beats` | `stems`, `extracted_stems`, `audio_path`, `sr`, `y` | `refined_beats`, `snap_offsets_ms` |
| `KickBassDownbeatVerifierNode` | `beats`, `y`, `sr` |  | `beats`, `downbeat_fix_report` |
| `ViterbiTempoSmoothingNode` | `beats` |  | `beats`, `smoothing_report` |
| `BeatAlignmentVerifierGuardNode` | `beats` | `sections`, `kick_anchors` | `beat_alignment_score` |
| `DrumsKickBeatFallbackNode` |  | `stems`, `rhythm_track_path`, `audio_path`, `kick_anchors` | `beats`, `fallback_beat_recalculated` |
| `MeasureMapNode` | `beats`, `beat_validation` | `refined_beats`, `downbeat_refinement` | `measure_map`, `measure_map_status`, `measure_map_warnings` |
| `SectionStructureNode` | `measure_map` | `y`, `sr`, `chord_progression` | `sections` |
| `KeyChordAnalysisNode` | `audio_path`, `beats` | `refined_beats` | `estimated_key`, `chord_progression` |
| `ClickSynthesisNode` | `audio_path`, `beats`, `output_dir` | `refined_beats` | `click_track`, `mix_with_click` |
| `CandidateTrackBuildNode` |  | `audio_path`, `target_analysis_path`, `project_dir`, `output_dir`, `stems`, `stems_dir` | `beat_candidate_tracks`, `full_mix_track_path`, `rhythm_track_path`, `band_track_path`, `vocal_track_path` |
| `PerTrackBeatAnalysisNode` |  | `beat_candidate_tracks` | `beat_candidates`, `beats_full_mix`, `beats_rhythm`, `beats_band`, `beats_vocal` |
| `SegmentGridNode` |  | `measure_map`, `beats`, `refined_beats`, `beat_candidates` | `analysis_segments` |
| `PerSegmentConfidenceNode` | `analysis_segments`, `beat_candidates` | `beat_candidate_tracks` | `per_segment_confidence` |
| `SegmentSourceAttributionNode` | `per_segment_confidence` |  | `segment_source_map` |
| `BeatGridSynthesisNode` | `segment_source_map`, `beat_candidates` |  | `beats`, `refined_beats`, `beat_synthesis_report` |
| `SubdivisionGridNode` | `beats` | `measure_map` | `subdivision_grid`, `click_grid` |
| `SyncopationClassificationNode` | `subdivision_grid`, `click_grid` | `onset_events` | `syncopation_events`, `snap_exclusion_zones` |
| `Module3BackingWithClickNode` |  | `stems`, `stems_dir`, `no_vocals_path`, `instrumental_path` | `backing_with_click_path`, `backing_with_click_status` |
| `Module3OutputSummaryNode` |  | `click_track`, `mix_with_click`, `backing_with_click_path`, `segment_source_map`, `beat_synthesis_report`, `subdivision_grid`, `syncopation_events` | `module3_outputs`, `module3_report_json` |
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
