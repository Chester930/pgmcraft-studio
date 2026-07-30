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

## 新版流程討論稿：分軌優先的小節開頭決策

狀態：**已開始 experimental SDD 落地；目前不替換既有 `module3`**。

本段記錄新的大幅重構方向。現階段先以 `target_stage="module3_barstart_v2"` 獨立 experimental workflow 驗證，等 reference/manual 驗收達標後再評估是否替換現有 Module 3 BT。

### 暫定分軌策略

第一階段分軌：

```text
input audio
-> drums
-> bass
-> guitar
-> piano
-> vocal
```

第二階段細分：

```text
drums
-> kick
-> snare
-> hihat / cymbals
-> tom / percussion

guitar
-> strumming / chord body
-> melodic lead / riff

piano
-> chord comping
-> melodic line
```

此方向的目的不是選出「哪一軌作為最終答案」，而是明確知道每段、每一軌、每一種音樂角色對 beat / downbeat / first bar anchor 的可信度。

### 第一小節開頭定義

新版流程要優先找出：

```text
第一個正式小節的開頭 = song grid 的 bar 1 beat 1
```

不能直接等同於：

- 第一個鼓聲
- 第一個最大 transient
- 第一個人聲音節
- 第一個和弦聲響
- 第一個 BeatNet / Librosa 偵測到的 beat

必須排除或降低權重：

- 自由拍前奏
- pickup / anacrusis 弱起
- count-in / clap / spoken cue
- 只有旋律或人聲的 phrase onset
- 尾奏後殘留拍點
- 鼓過門快速連打造成的裝飾性 transient

暫定判斷式：

```text
first_bar_anchor =
  高可信 downbeat candidate
  + 後續 N 小節 metrical pattern 穩定
  + kick / bass / chord body / section boundary 多來源支持
  - pickup / free-time / fill / phrase-only penalty
```

### 相關文獻基礎

| 文獻 / 方法 | 對新版流程的意義 |
|-------------|------------------|
| Böck, Krebs, Widmer 2016：Joint Beat and Downbeat Tracking with RNNs | 支持 beat 與 downbeat 應共同估計，再用全局時序模型整理小節相位，而不是只抓單點 transient |
| Bar Pointer Model / DBN downbeat tracking | 將「目前位於小節中的哪個位置」建成 hidden state，適合處理 bar phase 與第一拍判斷 |
| Davies & Plumbley 2006：Spectral Difference Downbeat Extraction | 支持在已知 beat sequence 上，用低頻與 beat-synchronous spectral change 判斷 downbeat |
| Fuentes et al. 2019：Music Structure Informed Downbeat Tracking | 支持把段落結構納入 downbeat tracking，避免只用局部鼓點決定第一小節 |
| London, Himberg, Cross 2009：Anacrusis perception | 支持 pickup / 弱起與真正小節第 1 拍可能不同，不能把旋律起點直接當 bar 1 |

參考連結：

- https://research.jku.at/de/publications/joint-beat-and-downbeat-tracking-with-recurrent-neural-networks/
- https://tempobeatdownbeat.github.io/tutorial/ch3_going_deep/postprocessing.html
- https://www.researchgate.net/publication/228898122_A_Spectral_Difference_Approach_to_Downbeat_Extraction_in_Musical_Audio
- https://www.researchgate.net/publication/331589799_A_Music_Structure_Informed_Downbeat_Tracking_System_Using_Skip-Chain_Conditional_Random_Fields_and_Deep_Learning
- https://online.ucpress.edu/mp/article-abstract/27/2/103/62413/The-Effect-of-Structural-and-Performance-Factors

### 待討論問題

- 第一階段與第二階段分軌要使用同一個模型系列，還是允許不同模型分工？
- drums 細分是否需要 tom / percussion，或第一版只做 kick / snare / hihat-cymbal？
- guitar / piano 的「和弦 vs 旋律」是否先用能量頻段與 onset density 估計，還是直接導入 polyphonic transcription？
- first bar anchor 要先做單一候選，還是保留 top-k candidates 讓後續全曲 bar phase 驗證？
- 清唱開頭是否只作 phrase boundary，不直接提供 downbeat anchor？
- 評估資料要用人工 DAW grid、reference downbeat annotation，或兩者都保留？

### Rolling 下一小節開頭搜尋流程

已確認的新方向：

```text
bar_start 優先
數拍作為輔助判斷與驗證
beat grid 由相鄰 bar_start + meter profile 生成
```

流程不是先追逐每一拍 transient，而是從已確認的小節開頭往後滾動搜尋下一個小節開頭。

```text
current_bar_start = A_n
probe_window = [A_n, A_n + adaptive_window_sec]
目標 = 在 probe_window 內找出 A_{n+1}
```

初始窗口：

```text
adaptive_window_sec = 5.0
window_step_sec = 1.0
```

5 秒只是前置粗切塊與搜尋範圍，不代表 `A_n + 5s` 就是下一小節開頭。

窗口調整規則：

```text
若找不到下一小節開頭：
  adaptive_window_sec += 1.0
  下一輪往後推動搜尋窗，重跑相同分析迴圈

若很快找到下一小節開頭：
  adaptive_window_sec -= 1.0

若在合理區間找到：
  adaptive_window_sec 保持不變
```

此設計目標是讓每次搜尋範圍盡量只包含一個下一小節開頭候選，並讓 window 調整過程可解釋、可除錯。

若某一窗找不到，但往後推 5 秒或更長後找到可信小節開頭，前段應標為 unresolved span，後續可再依 tempo / meter continuity 回推補小節；不應直接亂補或強制 commit。

### 證據階梯

在每個 rolling probe window 中，依序擴充證據來源：

```text
1. drums
2. drums substems
3. drums + bass
4. drums + bass + primary chord track
5. drums + bass + both chord tracks
6. + primary melody track
7. + secondary melody track
8. + remaining melody track
```

drums substems 暫定包含：

```text
kick
snare
hihat / cymbals
tom / percussion
```

和弦軌 PK：

```text
guitar_chord_track
vs
piano_chord_track
```

先加入主要和弦軌；若仍不確定，再加入另一個和弦軌。

旋律軌 PK：

```text
vocal_melody_track
vs
piano_melody_track
vs
guitar_melody_track
```

先加入主要旋律軌；若仍不確定，依 PK 排名逐步加入次要與剩餘旋律軌。

每一層搜尋都應輸出：

```text
bar_start_candidate_time
confidence
evidence_sources
failure_reason / uncertainty_reason
```

### 數拍與最終 Click Grid 的角色分工

數拍方法仍保留，但角色是輔助判斷：

```text
BeatCountingEvidenceNode
-> beat_phase_trace
-> counted_beat_candidates
-> expected_next_bar_start
-> count_confidence
```

數拍結果可用來判斷是否已到下一個小節，但不直接把每一拍 transient 寫成最終 click。

最終 click grid 應由相鄰小節開頭與拍號 profile 產生：

```text
bar_start[n]
bar_start[n+1]
meter_profile
-> beats / click_grid / measure_map
```

### 拍號與臨時增減拍

不固定四等分。應依使用者選擇或自動推定的拍號，把相鄰小節開頭區間切成對應拍數。

前端初版建議提供：

```text
拍號模式：
- 自動判斷
- 4/4
- 3/4
- 6/8
- 5/4
- 7/8
```

進階選項：

```text
允許臨時增減拍：
- 關閉
- 允許 +1 拍
- 允許 +2 拍
- 允許 -1 拍
- 自動偵測
```

建議節點：

```text
MeterProfileNode
-> meter_profile
-> allowed_bar_lengths
-> temporary_bar_policy

MeterAwareBeatGridNode
-> beats
-> click_grid
-> measure_map
-> meter_changes
-> bar_length_report
```

若使用者選 4/4 且不允許臨時增減拍：

```json
{
  "base_meter": "4/4",
  "beats_per_bar": 4,
  "allowed_bar_lengths": [4],
  "temporary_bar_policy": "fixed"
}
```

若使用者選 4/4 且允許 +1 / +2：

```json
{
  "base_meter": "4/4",
  "beats_per_bar": 4,
  "allowed_bar_lengths": [4, 5, 6],
  "temporary_bar_policy": "allow_extensions"
}
```

### Tempo Ramp Guard

音色節奏不穩、提前、拖拍、切分、過門，原則上屬於 performance timing，不應拉動 click grid。

但如果相鄰小節開頭本身呈現持續漸快或漸慢，應標記為 tempo ramp / rubato 風險：

```text
BarDurationStabilityGuard
-> tempo_ramp_warning
-> click_not_recommended_reason
```

嚴重漸快、漸慢或 rubato 素材，本來就不適合產生固定節拍器；流程應給出警告，而不是強行輸出看似精準的 click。

### Stage 3 v2 BT 調整方向

新版不應推倒原本 BT，而是把原本 Stage 3 的 beat-first 架構改造成 evidence / guard / fallback，主骨架改為 bar-start-first。

原本思路：

```text
stem separation
-> beat tracking
-> downbeat refinement
-> measure map
-> click
```

新版思路：

```text
high-quality local stem separation
-> role split + model candidates
-> first bar anchor
-> rolling next-bar-start search
-> meter-aware beat grid
-> click
```

建議新增一條獨立測試流程，先不要直接取代現有 `module3`：

```text
target_stage = "module3_barstart_v2"  # 暫定名稱，討論完成後再定
```

暫定 BT：

```text
Module3BarStartClickRoot [Sequence]
├── InputAcquisitionRoot
├── AudioQualityRoot
├── LocalModelRegistryNode
├── BestLocalStemSeparationRoot
│   ├── BS-RoFormerSixStemNode
│   ├── DemucsSixStemFallbackNode
│   └── StemQualityScoringNode
├── RoleSplitRoot
│   ├── DrumSubstemSplitNode
│   ├── GuitarChordMelodySplitNode
│   └── PianoChordMelodySplitNode
├── MeterProfileNode
├── FirstBarAnchorRoot
├── RollingBarStartTrackingRoot
│   ├── RollingProbeWindowNode
│   ├── DrumEvidenceBarSearchNode
│   ├── DrumsOnlyBarSearchNode
│   ├── DrumSubstemBarSearchNode
│   ├── DrumBassBarSearchNode
│   ├── ChordTrackPKNode
│   ├── DrumBassChordBarSearchNode
│   ├── MelodyTrackPKNode
│   ├── MelodyAssistedBarSearchNode
│   ├── BarStartCandidateCommitNode
│   ├── BarStartDecisionNode
│   └── AdaptiveWindowUpdateNode
├── BarDurationStabilityGuard
├── MeterAwareBeatGridNode
├── ExistingStage3RefinementGuards
├── MusicAnalysisRoot
└── Module3ExportRoot
```

### 原本 BT 優點的整合方式

| 原本節點 / 能力 | 新版角色 |
|-----------------|----------|
| `InputAcquisitionRoot` | 保留，仍負責輸入、專案資料夾與 source 落盤 |
| `AudioQualityRoot` | 保留，仍提供 raw / normalized / denoised 版本與分析目標 |
| `StemSeparationRoot` | 保留架構，但模型選擇升級為 best-local-model first |
| `KickSnarePulseNode` | 改成 drum/substem evidence，輔助 bar start 與 beat counting |
| `BeatNetSingleTrackNode` | 保留為 beat/downbeat candidate，不直接主導 final click |
| `LibrosaSingleTrackNode` | 保留為 deterministic fallback 與 sanity check |
| `BeatFusionArbitratorNode` | 改造為 N-source evidence scorer，不再只是 A/B 二選一 |
| `SegmentSourceAttributionNode` | 保留概念，改為每個 probe window 的 evidence source report |
| `DrumFillDetectionNode` | 保留，避免過門密集擊點影響 bar-start / snap |
| `OnsetPhaseRealignmentNode` | 降級為小範圍校正 guard，只能校正已確認 grid，不可重寫結構 |
| `MicroTimingTransientSnapNode` | 降級為小範圍 snap guard，必須尊重 `snap_exclusion_zones` |
| `ViterbiTempoSmoothingNode` | 保留為異常檢查，不無條件拉直 rubato 或漸快/漸慢 |
| `BeatAlignmentVerifierGuardNode` | 改造成 bar-start alignment verifier |
| `MeasureMapNode` | 新版應改由 `committed_bar_starts + meter_profile` 產生 |
| `MusicAnalysisRoot` | 保留，但和弦/段落分析應讀取新版 measure map |
| `Module3ExportRoot` | 保留 click / mix / report 輸出，但 report 要加入 bar-start v2 診斷 |

### 高品質本地模型整合方向

模型不直接決定答案，只產生 candidates / evidence / confidence。

建議優先順序：

| 任務 | 優先本地模型 | Fallback |
|------|--------------|----------|
| 第一階段 6-stem 分軌 | BS-RoFormer-SW | `htdemucs_6s` |
| 4-stem 穩定分軌 | `htdemucs_ft` | `htdemucs` / `mdx_extra` |
| 鼓細分 | `drumsep` / MDX23C drums substem | 現有 DSP bandpass + onset peak |
| beat / downbeat candidate | Beat This! | BeatNet -> Librosa |
| 吉他 / 鋼琴 note events | Basic Pitch on isolated track | chroma / onset fallback |
| 和弦辨識 | BTC 類 Transformer chord model，需檢查權重授權 | madmom DeepChroma+CRF / Chordino / librosa chroma template |

建議新增：

```text
LocalModelRegistryNode
-> local_model_registry
-> model_availability_report
-> model_license_report
```

每個模型輸出應統一格式：

```json
{
  "source": "guitar_chord",
  "model": "basic_pitch",
  "candidate_type": "note_events",
  "confidence": 0.82,
  "path": "...",
  "fallback_reason": null
}
```

### 新版 Blackboard 核心 Key

新版主資料不再只有 `beats`，而是先建立小節開頭序列。

建議新增：

```text
local_model_registry
model_availability_report
model_license_report

stem_quality_report
role_split_tracks

first_bar_anchor
bar_probe_windows
bar_start_candidates
committed_bar_starts
unresolved_bar_spans

meter_profile
allowed_bar_lengths
temporary_bar_policy
bar_duration_report
tempo_ramp_warning
click_not_recommended_reason

beat_phase_trace
counted_beat_candidates
chord_track_pk
melody_track_pk
bar_start_decision_report

beats
click_grid
measure_map
meter_changes
bar_length_report
```

最終資料流：

```text
committed_bar_starts
+ meter_profile
-> MeterAwareBeatGridNode
-> beats / click_grid / measure_map
```

### 實作落地順序

此段只是後續 SDD 拆分參考，尚未開始執行。

建議順序：

1. 新增 `module3_barstart_v2` 任務入口與空 BT skeleton，不影響現有 `module3`。
2. 實作 `MeterProfileNode` 與 `MeterAwareBeatGridNode`，先用人工提供的 `committed_bar_starts` 測試 grid 產生。
3. 實作 `RollingProbeWindowNode` 與 `bar_probe_windows` 記錄。
4. 實作 `bar_start_candidates` / `committed_bar_starts` 的資料格式與 report。
5. 將現有 drums / kick / snare / bass evidence 接入 rolling search。
6. 加入 `ChordTrackPKNode` 與 guitar/piano chord evidence。
7. 加入 `MelodyTrackPKNode` 與 vocal/piano/guitar melody evidence。
8. 接入 Beat This! 作為正式本地 beat/downbeat candidate。
9. 接入 BS-RoFormer / Demucs 模型 registry 與 best-local-model 分軌策略。
10. 最後才評估是否讓 v2 取代現有 `module3`。

### SDD 拆分任務

| SDD Pass | 目標 | 完成條件 |
|----------|------|----------|
| Pass 105 | `module3_barstart_v2` skeleton、`MeterProfileNode`、`MeterAwareBeatGridNode` | ✅ 已完成；可用人工 `committed_bar_starts` 依拍號產生 `beats`、`click_grid`、`measure_map`；不影響現有 `module3` |
| Pass 106 | rolling probe window 基礎資料流 | ✅ 已完成；產出 `active_bar_probe_window` / `bar_probe_windows`，支援初始 5 秒、找不到後 +1 秒、很快找到後 -1 秒 |
| Pass 107 | bar start candidate / commit 資料格式 | ✅ 已完成；建立 `bar_start_candidates`、`committed_bar_starts`、`unresolved_bar_spans`、`bar_start_decision_report`、`last_bar_probe_result` |
| Pass 108 | drums / drum substem evidence | ✅ 已完成；接入 kick/snare/drum onset evidence，輸出候選與可信度，不直接寫 final click，且對 `drum_fill_regions` / `snap_exclusion_zones` 降權 |
| Pass 109 | drums + bass bar search | ✅ 已完成；`DrumBassEvidenceBarSearchNode` 以 `bass_anchors` / `bass_onset_candidates` 提升鼓候選可信度，無鼓候選時只產生低信心 bass-only 候選，並輸出 `drum_bass_evidence_report` |
| Pass 110 | chord track PK | ✅ 已完成；`ChordTrackPKNode` 建立 guitar/piano harmonic anchors 與 `chord_track_pk`，可補強既有 bar-start candidates；harmonic-only candidate 保持低信心 |
| Pass 111 | melody track PK | ✅ 已完成；`MelodyTrackPKNode` 建立 vocal/piano/guitar melody PK 與 phrase/count evidence；melody-only candidate 保持低信心，不直接主導 click commit |
| Pass 112 | Beat This! 本地候選 adapter | ✅ 已完成；`BeatThisCandidateAdapterNode` 將 optional `beat_this_beats` / `beat_this_downbeats` / `beat_this_candidates` 轉入 bar-start evidence ladder；沒有候選時 graceful skip，保留 BeatNet/Librosa fallback |
| Pass 113 | 本地分軌模型 registry | ✅ 已完成；`LocalModelRegistryNode` 建立 Beat This! / BeatNet / Librosa / Demucs / Basic Pitch / chord model availability 與 license metadata report，不載入模型權重 |
| Pass 114 | v2 前端測試入口 | ✅ 已完成；Gradio 新增隔離的 BarStart v2 入口，人工只選拍號與臨時小節拍數調整，小節起點交給模型/evidence ladder；不改動舊版 module3 |
| Pass 115 | v2 替換門檻 | ✅ 閘門已完成；只有 reference/manual 都為 `pass` 且沒有 unresolved bar spans 才回傳 `PROMOTE_READY`；實際 reference/manual 驗收資料仍待執行 |
| Pass 116 | Click 合成輸出增益 | ✅ 已完成；`ClickSynthesisNode` 預設將 click-only、mix 與 backing+click 使用的 Click 增益提高 `+10 dB`，原始音檔不增益 |
| Pass 117 | 雙向小節錨定 lookahead | ✅ 已完成第一版；新增 lookahead candidate、跨無鼓段小節數估計、前後錨點驗證與 transition confidence，無 lookahead 輸入時 graceful no-op |

### 暫停點紀錄（2026-07-29）

目前已完成並驗證：

- Pass 105：`module3_barstart_v2` skeleton、`MeterProfileNode`、`ManualCommittedBarStartsSeedNode`、`MeterAwareBeatGridNode`。
- Pass 106：`RollingProbeWindowNode`，支援初始 5 秒搜尋窗與 ±1 秒調整。
- Pass 107：`BarStartCandidateCommitNode`，統一候選 commit / unresolved span 資料格式。
- Pass 108：`DrumEvidenceBarSearchNode`，以 kick/snare/drum onset 產生候選，並對過門排除區降權。
- Pass 109：`DrumBassEvidenceBarSearchNode`，以 bass coincidence 支援 drum candidate；無鼓候選時產生低信心 bass-only 候選供後續 evidence ladder 或人工檢查。
- Pass 110：`ChordTrackPKNode`，建立 guitar/piano chord anchor PK，並以 harmonic anchor support 保守補強 bar-start candidates。
- Pass 111：`MelodyTrackPKNode`，建立 vocal/piano/guitar melody anchor PK，phrase/count evidence 只保守補強 candidates。
- Pass 112：`BeatThisCandidateAdapterNode`，接入 optional Beat This! beat/downbeat candidates，無候選或未安裝時不阻斷既有 BeatNet/Librosa fallback。
- Pass 113：`LocalModelRegistryNode`，記錄本地模型 availability、fallback 與 license metadata。
- Pass 114：新增 `process_module3_barstart_v2_test` 與 Gradio BarStart v2 入口；前端只傳入拍號與臨時小節拍數調整，bar starts 由模型/evidence ladder 處理，並顯示 `barstart_v2_report`。
- Pass 115：新增 `evaluate_barstart_v2_promotion_gate`；未取得雙重驗收與乾淨小節結果前，v2 維持 `EXPERIMENTAL_ONLY`，不自動替換現有 `module3`。
- Pass 115 smoke：以 `sample_test.wav` 執行成功；結果為 `EXPERIMENTAL_ONLY`，含 provisional seed、1 個 unresolved bar span，未宣告升格。
- Pass 116：`PGMSynthesizer.CLICK_GAIN_DB=10.0`，Click 以 float WAV 輸出避免 PCM 先削波；通過實際 RMS 增益測試與 pipeline 回歸測試。

### Pass 117 SDD 任務：雙向小節錨定 lookahead

#### 目標

處理「有鼓 → 無鼓 → 接鼓」段落：無鼓期間沿用既有 tempo、拍號與小節相位，等下一個可靠鼓點出現後，反向估計中間小節數，再以雙向誤差驗證是否能提交新的 `committed_bar_starts`。

#### 範圍

- 新增 `ReliableBarAnchorNode`：整理高信心 drum / bass / Beat This! /既有 grid anchor。
- 新增 `NoDrumPhaseCarryNode`：在無鼓段維持上一個可靠 anchor 的 tempo、meter 與 phase，產生 provisional bar starts。
- 新增 `LookaheadDrumAnchorSearchNode`：對下一個鼓點建立前後半拍、一拍與 fill 結束候選，不直接 reset。
- 新增 `InterveningBarCountEstimatorNode`：以 anchor 時間差與 bar duration 估計 `N-1/N/N+1` 小節候選。
- 新增 `BidirectionalBarAlignmentNode`：比較 forward projection 與 backward projection 的 phase error。
- 擴充 `TransitionConfidenceNode`：進鼓至少觀測 1 至 2 小節後，才提高 transition confidence。

#### Blackboard 契約草案

| Key | Producer | Consumer | 規則 |
|-----|----------|----------|------|
| `reliable_bar_anchors` | `ReliableBarAnchorNode` | lookahead / alignment | 只收錄高信心 anchor，包含 `time`、`source`、`confidence`、`meter`、`tempo` |
| `provisional_bar_starts` | `NoDrumPhaseCarryNode` | bar-count / alignment | 無鼓段暫時推算，不得直接視為 committed |
| `lookahead_bar_candidates` | `LookaheadDrumAnchorSearchNode` | bar-count / transition | 鼓點候選與 offset、source、confidence |
| `intervening_bar_count_candidates` | `InterveningBarCountEstimatorNode` | alignment | 只允許 `N-1/N/N+1`，記錄 bar duration error |
| `bidirectional_alignment_report` | `BidirectionalBarAlignmentNode` | commit / summary | 包含 forward/backward error、選定小節數與 status |
| `transition_confidence_report` | `TransitionConfidenceNode` | commit / promotion gate | 進鼓穩定觀測前不得回報 high confidence |

#### 降級規則

- 下一個鼓點不足以形成可靠 anchor：維持前一段 phase，標記 `LOOKAHEAD_PENDING`。
- `N-1/N/N+1` 都無法通過誤差門檻：不重設節拍，標記 `AMBIGUOUS_TRANSITION`。
- 鼓點疑似 fill 或 pickup：只保留 candidate，不提交 `committed_bar_starts`。
- 無鼓段沒有前一個可靠 anchor：沿用現有 provisional seed，但 promotion gate 必須阻擋升格。

#### 驗收案例

1. 有鼓 → 無鼓 → 有鼓，間隔正好 4 小節：中間 4 小節被正確補齊。
2. 無鼓 → 進鼓前 pickup：pickup 不得直接成為新小節第一拍。
3. 下一段鼓點落弱拍：維持原 phase，不能因第一個鼓聲跳拍。
4. tempo 有小幅漂移：允許誤差內校正，但不得改變小節數。
5. lookahead 不足：輸出 `LOOKAHEAD_PENDING`，流程仍成功且不產生錯誤 commit。

#### Pass 117 完成條件與目前結果

- 新增節點與既有 evidence ladder 皆可獨立測試。✅
- 5 個驗收案例與 pipeline placement 均有自動化測試，並保留一個實際音檔 smoke case。✅（單元驗收完成；實際音檔 smoke 仍需人工聽測）
- report 可區分 `provisional`、`candidate`、`committed` 三種狀態。
- 現有 `module3` 與 v2 既有測試全部不回歸。✅

最後已通過驗證：

```text
python -m pytest -q tests\test_sdd_pass114.py tests\test_sdd_pass113.py tests\test_sdd_pass112.py tests\test_sdd_pass111.py tests\test_sdd_pass110.py tests\test_sdd_pass109.py tests\test_sdd_pass108.py tests\test_sdd_pass107.py tests\test_sdd_pass106.py tests\test_sdd_pass105.py tests\test_sdd_pass104.py tests\test_module3_bt.py
61 passed
python -m py_compile app.py pgm_craft\workflow\module3_barstart_v2_bt.py pgm_craft\workflow\module3_bt.py pgm_craft\workflow\builder.py pgm_craft\pipeline.py
git diff --check
```

下一步未完成項目：

- Pass 115 實際 reference/manual 驗收：尚未執行；目前僅完成升格閘門與自動化契約測試。

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
