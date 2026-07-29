# 模塊三任務規劃書：和弦簡譜與節拍器生成

**最後更新：** 2026-07-29

## 模塊定位

模塊三的主要目標不是完整 DAW 工程包，也不是旋律採譜，而是從音訊產出兩個核心成品：

1. **和弦簡譜**
2. **節拍器打點音檔**

其中「和弦簡譜」不是只列出根音或簡單大三和弦，而是要能表達常見 lead sheet / chord chart 所需的和弦品質。最低目標應包含：

```text
大三和弦：C, F, G
小三和弦：Am, Dm, Em
屬七和弦：G7, A7
大七和弦：Cmaj7, Fmaj7
小七和弦：Am7, Dm7
九和弦 / add9：Cadd9, G9, Am9
掛留和弦：Csus2, Csus4, G7sus4
增和弦：Caug, C+
減和弦：Cdim, Cdim7, Cm7b5
變化音和弦：G7b9, G7#9, Cmaj7#11, Dm9/G
轉位 / slash chord：G/B, C/E, Dm7/G
```

第一版不需要旋律或數字簡譜音符，但和弦符號必須足夠給樂手練團使用。

建議前端命名：

```text
模塊三：和弦簡譜與節拍器生成
```

副標：

```text
節拍、小節、調性、和弦與 Click 打點
```

## BT 階段定位

目前現有 `target_stage="stage4"` 只會跑到小節、調性、和弦與段落分析，不會產生 click 音檔。

目前現有 `target_stage="stage5"` 會產生 click，但也會跑完整 Export BT，包含 MIDI、section markers、lyrics markers、voice cue、human groove、IEM、count-in 等模塊三不一定需要的內容。

因此模塊三已新增專用目標：

```text
target_stage = "module3"
```

`module3` 不走完整 Stage 5/6，而是使用模塊三專用 BT。節拍部分與完整全自動 Stage 3 共用同一系列節點；差異是模塊三會在 Stage 3 dual-track fusion 後插入四個節拍候選來源，按小節或段落標註哪一軌最可信，再合成唯一 `refined_beats` 給 click 輸出。

## 建議 BT 結構

```text
Module3BeatClickRoot [Sequence]
├── Input Acquisition                       # 共用 Stage 0
├── Audio Quality                           # 共用 Stage 1
├── OptionalStemSeparationNode              # enable_stem=true 才跑 Stage 2
├── CandidateTrackBuildNode                 # 建立 full/rhythm/band/vocal 四軌候選來源
├── SynthesizeRhythmTrackNode               # 共用 Stage 3 preparation
├── PrepareInstrumentalTrackNode            # 共用 Stage 3 preparation
├── KickSnarePulseNode                      # 共用 Stage 3 preparation
├── TrackA_RhythmBranch                     # 共用 Stage 3 dual-track analysis
├── TrackB_InstrumentalBranch               # 共用 Stage 3 dual-track analysis
├── MultiModelBeatEnsembleNode              # 共用 Stage 3 fusion
├── BeatFusionArbitratorNode                # 共用 Stage 3 fusion
├── PerTrackBeatAnalysisNode                # 每軌各自產生 beat candidates
├── SegmentGridNode                         # 以小節或 4 拍建立分析段落
├── PerSegmentConfidenceNode                # 每段、每軌計算可信度
├── SegmentSourceAttributionNode            # 標註每段 primary/supporting 來源
├── BeatGridSynthesisNode                   # 依分段來源合成唯一 beat grid
├── ReEntryReAnchoringNode                  # 共用 Stage 3 refinement guard
├── BeatValidationNode                      # 共用 Stage 3 refinement guard
├── DownbeatRefineNode                      # 共用 Stage 3 refinement guard
├── OnsetPhaseRealignmentNode               # 共用 Stage 3 refinement guard
├── MicroTimingTransientSnapNode            # 共用 Stage 3 refinement guard
├── KickBassDownbeatVerifierNode            # 共用 Stage 3 refinement guard
├── ViterbiTempoSmoothingNode               # 共用 Stage 3 refinement guard
├── BeatAlignmentVerificationAndFallback    # 共用 Stage 3 fallback guard
├── MusicAnalysisRoot                       # 共用 Stage 4，產出 measure/key/chord/section
├── SubdivisionGridNode                     # 建立 8 分音符分析 grid，click 仍維持 4 分音符
├── SyncopationClassificationNode           # 標記切分/提前音，不讓 click 被拉走
└── Module3ExportRoot                       # 新增模塊三專用導出
    ├── ClickSynthesisNode                  # 共用：click_track.wav / mix_with_click.wav
    ├── Module3BackingWithClickNode         # 只有 no_vocals/instrumental 存在時才產生 backing_with_click.wav
    └── Module3OutputSummaryNode            # module3_beat_click_report.json
```

不建議再用：

```text
target_stage = "stage5"
```

因為 Stage 5 會混入 DAW marker、lyrics marker、voice cue、IEM、count-in 等非模塊三必要輸出。

## 分段可信來源標註

模塊三不是把四軌候選「全曲選一軌」當答案，而是建立 `segment_source_map`：

```text
measure 1-4     full_mix + vocal     清唱或弱伴奏段
measure 5-16    rhythm primary       drums+bass groove 明確
measure 17-24   band primary         無鼓但伴奏和聲脈絡穩定
measure 25-32   rhythm primary       鼓 re-entry 後重新錨定
```

候選來源：

| 來源 | 內容 | 用途 |
|------|------|------|
| `full_mix` | 原曲 / C 版降噪音檔 | 清唱、分軌失敗、全曲保底 |
| `rhythm` | drums + bass | groove、kick/snare、downbeat 主要依據 |
| `band` | drums + bass + guitar + piano；無法合成時用 no_vocals / instrumental | 無主唱伴奏、無鼓但和聲清楚的段落 |
| `vocal` | vocals / lead vocal | 清唱段、弱起、phrase onset 輔助；不可直接讓 click 跟音節跑 |

每段會計算：

```text
onset clarity / coverage
tempo stability
segment energy
source role weight
disagreement penalty
```

最後由 `BeatGridSynthesisNode` 依段落選用 primary source，並用 supporting sources 驗證，合成唯一 `beats` / `refined_beats`。

## 8 分音符分析 Grid 與 4 分音符 Click

模塊三會把每小節展開成：

```text
| 1   &   2   &   3   &   4   & |
```

但 `click_grid` 只保留：

```text
1, 2, 3, 4
```

`SubdivisionGridNode` 輸出：

```text
subdivision_grid  # 8 分音符分析用
click_grid        # 4 分音符輸出用
```

`SyncopationClassificationNode` 會將實際 onset 標記成：

```text
true_beat
syncopation
anticipation
pickup
phrase_onset
```

若 transient 是下一拍前的提前音或上一小節最後的 `&`，會寫入 `snap_exclusion_zones`，後續 click 不應被吸附過去。

## 模塊三主要輸出

### 目前已實作成品

| 輸出 | 來源節點 | 用途 |
|------|----------|------|
| `click_track.wav` | `ClickSynthesisNode` | 節拍器打點音檔 |
| `mix_with_click.wav` | `ClickSynthesisNode` | 原曲 + click 預聽，方便人工確認拍點 |
| `backing_with_click.wav` | `Module3BackingWithClickNode` | 只有 no_vocals / instrumental 存在時才產出 |
| `module3_beat_click_report.json` | `Module3OutputSummaryNode` | 模塊三 BT 專用報告，包含分段可信來源、8 分 grid、切分音標註 |
| `module3_pipeline_report.json` | `PGMCraftEngine` | pipeline 層摘要與前端下載用 manifest |
| `tempo_curve.png` | `PGMCraftEngine` | BPM 變化視覺化，位於測試專案 `reports/` |

### 後續 Lead Sheet 成品

| 輸出 | 來源 | 用途 |
|------|------|------|
| `chord_leadsheet.md` | `ChordLeadSheetNode` | 給樂手/練團快速閱讀 |
| `chord_leadsheet.html` | `ChordLeadSheetNode` | 前端預覽與列印 |
| `chord_leadsheet.json` | `ChordLeadSheetNode` | 前端結構化資料與後續自動化 |
| `beat_evaluation.json` | CLI reference evaluation | 有 reference annotation 時做客觀精度驗收 |

模塊三目前是測試專案輸出，不是 PGM/DAW package 輸出：

```text
{output_root}/{project_name}/
├── source/
├── stems/
├── click/
└── reports/
```

`target_stage="module3"` 會標記：

```text
project_package_status = SKIPPED_MODULE3_TEST_PROJECT
```

前端與自動化測試應優先讀取 `module3_outputs` 作為 output manifest。

## 模塊三內部必要資料

| Blackboard Key | 來源 | 是否必要 | 用途 |
|----------------|------|----------|------|
| `audio_path` | Input Acquisition | 必要 | click mix 與分析來源 |
| `output_dir` / `project_dir` | Input Acquisition | 必要 | 導出位置 |
| `beats` | Stage 3 | 必要 | click、BPM、小節與和弦對齊 |
| `refined_beats` | Stage 3 post-process | 建議必要 | 最終採用的 click grid |
| `beat_validation` | `BeatValidationNode` | 必要 | 前端顯示 PASS/WARN/FAIL |
| `downbeat_refinement` | `DownbeatRefineNode` | 必要 | 小節第一拍可信度 |
| `beat_precision_diagnostics` | pipeline report | 建議 | 對拍除錯 |
| `beat_candidate_tracks` | `CandidateTrackBuildNode` | 必要 | full/rhythm/band/vocal 四軌候選來源 |
| `beat_candidates` | `PerTrackBeatAnalysisNode` | 必要 | 每軌 beat candidates |
| `analysis_segments` | `SegmentGridNode` | 必要 | 小節或 4 拍分析段落 |
| `per_segment_confidence` | `PerSegmentConfidenceNode` | 必要 | 每段每軌可信度 |
| `segment_source_map` | `SegmentSourceAttributionNode` | 必要 | 每段 primary/supporting 來源與原因 |
| `beat_synthesis_report` | `BeatGridSynthesisNode` | 必要 | 最終 beat grid 合成來源摘要 |
| `subdivision_grid` | `SubdivisionGridNode` | 必要 | 8 分音符分析 grid |
| `click_grid` | `SubdivisionGridNode` | 必要 | 4 分音符 click grid |
| `syncopation_events` | `SyncopationClassificationNode` | 建議 | 切分、提前音、phrase onset 標註 |
| `snap_exclusion_zones` | `SyncopationClassificationNode` | 建議 | 不允許 click snap 的 transient 區間 |
| `measure_map` | `MeasureMapNode` | 必要 | 和弦簡譜按小節排版 |
| `measure_map_status` | `MeasureMapNode` | 必要 | 小節 fallback 警告 |
| `estimated_key` | `KeyChordAnalysisNode` / `MultiBandChromaKeyNode` | 必要 | 簡譜抬頭 |
| `bass_progression` | `BassRootAnalysisNode` | 建議必要 | 每小節底音 / bass note，作為 slash chord 分母 |
| `chord_tone_progression` | `ChordToneAnalysisNode` | 建議必要 | 不含底音約束的和弦音色 / chord quality |
| `chord_progression` | `SlashChordSynthesisNode` / `GridConstrainedChordNode` | 必要 | 合成後的完整和弦簡譜主體 |
| `sections` | `SectionStructureNode` | 建議 | Intro/Verse/Chorus 分段 |
| `meter_changes` | `DynamicMeterChangeGuardNode` | 建議 | 3/4、4/4、6/8 或變拍號提示 |

## 新增節點規格

### ChordLeadSheetNode

責任：

- 將 `measure_map`、`sections`、`chord_progression`、`estimated_key` 整理成可閱讀的和弦簡譜。
- 保留和弦品質與 extension，不可把 `Cmaj7`、`C7`、`Cm7`、`Cdim` 全部簡化成 `C`。
- 支援 slash chord 與 altered chord 的顯示；若分析器無法可靠判定，應保留警告而不是硬猜。
- 不做旋律採譜。
- 不產生 `melody_lead_midi`、`vocal_pitch_midi` 或 MusicXML melody。

建議契約：

| 欄位 | Key |
|------|-----|
| required_keys | `measure_map`, `chord_progression`, `estimated_key` |
| optional_keys | `beats`, `refined_beats`, `sections`, `meter_changes`, `beat_validation`, `downbeat_refinement`, `output_dir`, `project_dir` |
| output_keys | `chord_leadsheet`, `chord_leadsheet_md_path`, `chord_leadsheet_html_path`, `chord_leadsheet_json_path` |

輸出格式：

```text
Key: C Major    BPM: 92.5    Time: 4/4

[Intro]
| Cmaj7   | Am7     | Fadd9   | G7sus4  |

[Verse 1]
| C/E     | G/B     | Am9     | Fmaj7   |
| Dm7     | G7b9    | Cmaj7   | Cdim7   |
```

JSON 格式建議：

```json
{
  "title": "song.wav",
  "key": "C Major",
  "average_bpm": 92.5,
  "time_signature": "4/4",
  "sections": [
    {
      "name": "Intro",
      "start_measure": 1,
      "end_measure": 4,
      "measures": [
        {
          "measure": 1,
          "chord": "Cmaj7",
          "root": "C",
          "quality": "maj7",
          "bass": null,
          "extensions": ["7"],
          "alterations": [],
          "start_time": 0.0,
          "end_time": 2.0
        }
      ]
    }
  ],
  "warnings": []
}
```

### Chord Vocabulary Target

`ChordLeadSheetNode` 本身只負責排版；真正的辨識仍由 `KeyChordAnalysisNode`、`GridConstrainedChordNode` 與後續 chord model 決定。但模塊三的資料格式與 UI 必須先能承載下列和弦類型：

| 類型 | 範例 | 第一版處理 |
|------|------|------------|
| major / minor | `C`, `Am` | 必須支援 |
| dominant seventh | `G7` | 必須支援 |
| major seventh | `Cmaj7` | 必須支援 |
| minor seventh | `Dm7` | 必須支援 |
| add9 / ninth | `Cadd9`, `G9`, `Am9` | 必須支援顯示；辨識可逐步強化 |
| suspended | `Csus2`, `Csus4`, `G7sus4` | 必須支援顯示 |
| augmented | `Caug`, `C+` | 必須支援顯示 |
| diminished | `Cdim`, `Cdim7`, `Cm7b5` | 必須支援顯示 |
| altered dominant | `G7b9`, `G7#9`, `G7b13` | 必須支援顯示；辨識列為進階 |
| slash chord | `G/B`, `C/E`, `Dm7/G` | 必須支援顯示與 JSON `bass` 欄位 |

現有 `MusicAnalyzer` 已有 major、minor、dominant 7、maj7、m7、sus4、add9 template；後續應補齊 dim、dim7、m7b5、aug、sus2、9、m9、maj9 與 slash chord formatter。

### Chord Recognition Layering

建議將和弦辨識拆成三層，而不是一次直接猜完整符號：

```text
BassRootAnalysisNode
-> ChordToneAnalysisNode
-> SlashChordSynthesisNode
-> GridConstrainedChordNode / ChordLeadSheetNode
```

這樣可以處理「上方和弦」與「底音」不同的狀況，例如：

```text
上方和弦音色：C
底音：G
完整和弦：C/G

上方和弦音色：Dm7
底音：G
完整和弦：Dm7/G
```

#### BassRootAnalysisNode

責任：

- 優先分析 `stems["bass"]`、`electric_bass`、`synth_bass_808` 或低頻 submix。
- 以 `measure_map` 為單位輸出每小節底音。
- 若無 bass stem，fallback 到 full mix / harmonic track 的低頻 chroma。
- 產出「只有底音的譜」，供 debug 與前端顯示。

建議契約：

| 欄位 | Key |
|------|-----|
| required_keys | `measure_map` |
| optional_keys | `stems`, `harmonic_track_path`, `audio_path`, `y`, `sr` |
| output_keys | `bass_progression`, `bass_root_chart`, `bass_root_report` |

`bass_progression` 範例：

```json
[
  {"measure": 1, "bass": "G", "confidence": 0.82, "source": "bass_stem"},
  {"measure": 2, "bass": "B", "confidence": 0.76, "source": "bass_stem"}
]
```

底音譜範例：

```text
[Bass Roots]
| G       | B       | A       | F       |
```

#### ChordToneAnalysisNode

責任：

- 優先分析 `harmonic_track_path`，也就是 piano/guitar/organ/strings/bass 等和聲音色 submix。
- 可選擇降低 bass 權重，避免低音直接把上方和弦誤判成 slash chord 根音。
- 輸出「和弦音色的譜」，例如 `C`, `Am7`, `Fmaj7`, `G7`。
- 不在此階段處理 slash chord 分母。

建議契約：

| 欄位 | Key |
|------|-----|
| required_keys | `measure_map` |
| optional_keys | `harmonic_track_path`, `stems`, `audio_path`, `estimated_key` |
| output_keys | `chord_tone_progression`, `chord_tone_chart`, `chord_tone_report` |

和弦音色譜範例：

```text
[Chord Tones]
| C       | G       | Am7     | Fmaj7   |
```

#### SlashChordSynthesisNode

責任：

- 合併 `chord_tone_progression` 與 `bass_progression`。
- 若 bass note 與 chord root 不同，輸出 slash chord。
- 若 bass note 是 chord tone 的三音、五音或七音，優先視為轉位，例如 `C/E`, `C/G`, `Am/G`。
- 若 bass note 不是明確 chord tone，但低音可信度高，仍可輸出 `Dm7/G` 這類 pedal / slash chord，並加上 warning 或 confidence。
- 若 bass confidence 低，保留原 chord symbol，不硬寫 slash chord。

建議契約：

| 欄位 | Key |
|------|-----|
| required_keys | `chord_tone_progression`, `bass_progression`, `measure_map` |
| optional_keys | `estimated_key`, `sections` |
| output_keys | `chord_progression`, `slash_chord_report` |

合成規則：

```text
chord = C, bass = C  -> C
chord = C, bass = E  -> C/E
chord = C, bass = G  -> C/G
chord = Dm7, bass = G -> Dm7/G
chord = G7, bass = B -> G7/B
```

這個流程比直接從 full mix 猜 `C/G` 更可控，因為每一層都有獨立 debug 輸出：

```text
bass_root_chart
chord_tone_chart
final chord_leadsheet
```

### Module3OutputSummaryNode

責任：

- 收集測試專案資料夾、source、stems、click、reports、候選軌、預聽檔與 report path。
- 寫入 `module3_outputs` output manifest，供前端只讀一個 key。

建議契約：

| 欄位 | Key |
|------|-----|
| required_keys | 無 |
| optional_keys | `project_dir`, `audio_path`, `raw_wav_path`, `normalized_wav_path`, `denoised_wav_path`, `beat_candidate_tracks`, `click_track`, `mix_with_click`, `backing_with_click_path` |
| output_keys | `module3_outputs`, `module3_report_json` |

## 共用節點與工作流

### 可以共用

| 共用項目 | 來源 | 理由 |
|----------|------|------|
| `build_input_acquisition_tree()` | Stage 0 | URL / 本地音檔 / 專案資料夾建立邏輯一致 |
| `build_audio_quality_tree()` | Stage 1 | 音訊載入、品質檢查、去噪/正規化可共用 |
| `build_stem_separation_tree()` | Stage 2 | 可選；用來提供 drums/bass/instrumental 給節拍與和聲分析 |
| `build_beat_tracking_tree()` | Stage 3 | 模塊三 click 與小節分析的核心 |
| `build_music_analysis_tree()` | Stage 4 | 調性、和弦、小節、段落與拍號分析的核心 |
| `ClickSynthesisNode` | Stage 5 Export | 模塊三需要 click_track.wav 與 mix_with_click.wav |
| `PGMCraftEngine` report serialization | Pipeline | 已能輸出 `beats`、`refined_beats`、tempo curve 與 diagnostics |
| `beat_evaluation.py` | Evaluation | 有人工/DAW reference 時可共用客觀驗收 |

### 不應直接共用為模塊三必要流程

| 節點 / 流程 | 原因 |
|-------------|------|
| `MIDIExportNode` | MIDI 是後續 DAW 導出，不是模塊三核心成品 |
| `MIDIMarkerSectionExportNode` | 給 DAW marker，用不到可讀和弦簡譜 |
| `MIDILyricsMarkerExportNode` | 模塊三不處理歌詞 |
| `VoiceCueSynthesisNode` | 舞台 cue 屬 Live PGM 模塊 |
| `HumanGrooveMIDIExportNode` | MIDI groove 屬 DAW/演出擴充 |
| `IEMSplitMonoLRNode` | IEM 雙聲道屬 Live PGM 輸出 |
| `CountInSynthesizerNode` | 可作為未來選項，但不應是和弦簡譜與基本 click 的必要輸出 |
| `BasicPitchNode` / `CREPEPitchNode` | 模塊三不需要旋律或 vocal pitch |
| `PodcastSpeechNode` | 模塊三不需要逐字稿 |
| `HybridPitchNode` / `VoiceSplitMIDIExportNode` | 屬旋律/聲部分軌 MIDI，不屬模塊三 |
| `build_package_tree()` | ZIP/DAW 素材包屬 Stage 6 |

## 前端輸出區塊建議

模塊三前端結果區可分成三塊：

```text
1. 和弦簡譜
   - HTML 預覽
   - Markdown / HTML / JSON 下載

2. 節拍器
   - click_track.wav 播放與下載
   - mix_with_click.wav 播放與下載

3. 分析品質
   - BPM 平均/最低/最高
   - 總拍數/總小節數
   - Beat Validation
   - Downbeat Refinement
   - Measure Map Status
   - 警告列表
```

不要在模塊三主畫面放旋律 MIDI、逐字稿、完整 DAW ZIP，以免使用者誤解模塊目標。

## 接下來任務

### Pass M3-1：和弦簡譜節點

- 新增 `ChordLeadSheetNode`
- 產出 `.md`、`.html`、`.json`
- 設計 chord symbol parser / formatter，至少保留：
  - major / minor
  - 7 / maj7 / m7
  - add9 / 9 / m9 / maj9
  - sus2 / sus4
  - aug / dim / dim7 / m7b5
  - altered dominant
  - slash chord
- 單元測試：
  - 4/4 基本和弦表
  - extension 和弦不被簡化，例如 `Cmaj7`、`G7b9`、`Am9`
  - 增減和弦可輸出，例如 `Caug`、`Bdim7`、`Bm7b5`
  - slash chord 可輸出，例如 `G/B`、`Dm7/G`
  - 有 sections 時依段落分組
  - `N/A` / 靜音小節顯示
  - 缺 sections 時仍可輸出

### Pass M3-1b：和弦辨識模板擴充

- 擴充 `MusicAnalyzer` chord templates：
  - `dim`, `dim7`, `m7b5`
  - `aug`
  - `sus2`, `sus4`, `7sus4`
  - `add9`, `9`, `m9`, `maj9`
- 新增分層辨識節點規劃或實作：
  - `BassRootAnalysisNode`
  - `ChordToneAnalysisNode`
  - `SlashChordSynthesisNode`
- `GridConstrainedChordNode` 保留完整 chord symbol，不做根音化簡。
- 若辨識信心不足，輸出 `N/A` 或附加 warning，不應過度標註複雜和弦。
- 單元測試：
  - template vocabulary 包含上述和弦類型
  - bass-only chart 可輸出每小節底音
  - chord-tone chart 可不帶 slash bass 獨立輸出
  - `SlashChordSynthesisNode` 能合成 `C/G`、`C/E`、`Dm7/G`
  - bass confidence 低時不強制 slash chord
  - chord progression JSON 保留 `extension` / `quality` 欄位
  - lead sheet renderer 能正確顯示所有符號

### Pass M3-2：Module3 BT target

- 在 `build_master_pipeline_tree()` 支援 `target_stage="module3"`（已完成）
- 新增 `build_module3_export_tree()`（已完成）
- module3 tree 只接窄版輸出：
  - `ClickSynthesisNode`
  - `Module3BackingWithClickNode`
  - `Module3OutputSummaryNode`
- 測試：
  - `target_stage="module3"` 不執行 `MIDIExportNode`（已完成）
  - 不執行 `PodcastSpeechNode` / `VoiceSplitMIDIExportNode` / package（已完成）
  - 會產出 `click_track`
  - 會產出 `module3_report_json`
  - 後續補 `ChordLeadSheetNode` 後再驗證 `chord_leadsheet_md_path`

### Pass M3-3：Pipeline report 與 outputs mapping

- `module3_pipeline_report.json` 加入：
  - `chord_leadsheet`
  - `outputs.chord_leadsheet_md`
  - `outputs.chord_leadsheet_html`
  - `outputs.chord_leadsheet_json`
  - `outputs.click_track`
  - `outputs.mix_with_click`
- 測試 module3 report 與 `module3_outputs` 同步。

### Pass M3-4：前端模塊三頁面

- 新增或重命名前端區塊為「和弦簡譜與節拍器生成」
- `target_stage` 使用 `module3`
- 顯示：
  - 和弦簡譜 HTML
  - click player
  - mix with click player
  - tempo curve
  - 品質警告

### Pass M3-5：客觀檢查入口

- 保留 CLI `--reference-beats` / `--reference-downbeats`
- 前端可先不接 reference upload
- 後續若要接 GUI，再新增 reference annotation 上傳與 `beat_evaluation.json` 表格。

## 完成標準

模塊三完成時，使用者只需要提供音檔或 URL，即可得到：

```text
click_track.wav
mix_with_click.wav
module3_beat_click_report.json
module3_pipeline_report.json
tempo_curve.png
```

且前端能清楚顯示：

```text
調性
BPM
拍號 / 變拍號提示
段落
小節和弦
節拍與 downbeat 品質狀態
下載和弦簡譜與 click 音檔
```

## 風險與注意事項

- 和弦簡譜品質高度依賴 Stage 3 downbeat 與 Stage 4 measure map；若 downbeat 錯，和弦小節排版會一起錯。
- `ChordLeadSheetNode` 不應自行重算拍點或調性，只負責格式化與輸出。
- 和弦辨識可逐步強化，但 lead sheet 格式第一版就必須能承載複雜和弦；否則後續模型升級會被輸出格式卡住。
- `ClickSynthesisNode` 應使用 `refined_beats` 優先，避免和 report 顯示的最終 beat grid 不一致。
- 模塊三不應默默跑完整 Stage 5/6，否則速度、輸出數量與前端心智模型都會變差。
