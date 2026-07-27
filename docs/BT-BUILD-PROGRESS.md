# BT 建構進度同步紀錄

**最後更新：** 2026-07-27

本文件是 PGMCraft Studio 全自動音訊工作流 BT 的**實作進度活文件**。
每次討論與實作完成後同步更新，避免重複討論或重建相同決策。

---

## 一、整體 BT 架構（決策已定與實作現況）

全自動流程拆成**階段式 BT**，每個 Stage 是獨立的 `SequenceNode`，可單獨測試、單獨串接。

```
[Stage 0] InputAcquisitionRoot       ← 輸入取得 + 專案資料夾建立    ✅ 已實作 (builder.py 已串接)
[Stage 1] AudioQualityRoot           ← 11項評估 + 人群/環境降噪淨化  ✅ 已實作 (builder.py 已串接)
[Stage 2] StemSeparationRoot         ← 需求驅動樂器自動分軌          ✅ 已實作 (builder.py 已串接)
[Stage 3] BeatTrackingRoot           ← 節拍追蹤 + 驗證               ✅ 現有 (audio_nodes.py)
[Stage 4] MusicAnalysisRoot          ← 調性 + 段落結構              ✅ 現有 (audio_nodes.py)
[Stage 5] ExportRoot                 ← Click / MIDI / DAW           ✅ 現有 (audio_nodes.py)
[Stage 6] PackageRoot                ← 打包 ZIP + 報告              ✅ 現有 (packager.py)
```

---

## 二、Stage 0 — 輸入取得 BT

**狀態：✅ 完整實作並 SDD 測試通過（2026-07-25）**

### 實作位置

- 節點：[`pgm_craft/workflow/input_acquisition_bt.py`](../pgm_craft/workflow/input_acquisition_bt.py)
- 測試：[`tests/test_sdd_pass16.py`](../tests/test_sdd_pass16.py)（43 tests passed）

### BT 樹結構

```
Sequence [InputAcquisitionRoot]
├── ValidateInputNode              ← Guard: url 優先，audio_path 次之，兩者都空→FAILURE
├── ValidateProjectRootNode        ← Guard: project_root 存在且可寫
├── Fallback [InputSourceSelector]
│   ├── Sequence [URLInputBranch]
│   │   ├── IsURLConditionNode    ← http/https 判斷
│   │   ├── URLDownloadToTempNode ← yt-dlp 下載→暫存 WAV
│   │   └── NormalizeToProjectWAVNode
│   └── Sequence [LocalFileInputBranch]
│       ├── IsLocalFileConditionNode
│       ├── ValidateAudioFileNode ← 格式白名單: wav/mp3/flac/m4a/aac/ogg/opus
│       └── NormalizeToProjectWAVNode
└── Sequence [ProjectSetupChain]
    ├── ResolveProjectNameNode     ← 檔名/影片標題→合法資料夾名
    ├── CreateProjectFolderNode    ← 建立 source/stems/click/midi/reports/
    └── CopySourceToProjectNode    ← WAV 複製進 source/，更新 audio_path
```

### Blackboard 輸出契約

| Key | 值 |
|---|---|
| `audio_path` | `{project_dir}/source/{name}.wav` |
| `project_dir` | `{project_root}/{project_name}/` |
| `project_name` | 字串（合法資料夾名） |
| `media_title` | 同 project_name |
| `source_type` | `"url"` 或 `"local_file"` |
| `original_url` | URL 路徑才有 |

### 專案資料夾結構（兩條路統一）

```
{project_root}/
  └── {project_name}/
        ├── source/     ← audio_path 指向此
        ├── stems/
        ├── click/
        ├── midi/
        └── reports/
```

---

## 三、Stage 1 — 音質偵測與調整 BT

**狀態：✅ 完整實作並 SDD 測試通過（2026-07-25）**

### 實作位置

- 節點：[`pgm_craft/workflow/audio_quality_bt.py`](../pgm_craft/workflow/audio_quality_bt.py)
- 測試：[`tests/test_sdd_pass17.py`](../tests/test_sdd_pass17.py)（68 tests passed）

### BT 樹結構

### BT 樹結構

```
Sequence [AudioQualityRoot]
├── [1-A] AudioLoadNode                    ← librosa soxr_hq 載入
├── [1-B] AudioQualityInspectorNode        ← 11 項偵測，純讀不改
├── [1-C] QualityGateNode                  ← FAIL 阻擋整條鏈
└── [1-D] Fallback [QualityOptimizationSelector]
    ├── Sequence [EnhancementChain]        ← 多階層修復與 ABC 三版產出
    │   ├── NeedsEnhancementConditionNode
    │   ├── DCOffsetRemovalNode            ← 10Hz HPF filtfilt
    │   ├── SilenceTrimNode                ← -60dB trim + trim_offset_sec
    │   ├── PhaseAlignmentNode             ← 全曲均值 corr < 0 → flip R
    │   ├── SpectralDenoiseNode            ← Martin Minimum Statistics 頻譜降噪 (產出 y_denoised)
    │   ├── CrowdNoiseRemovalNode          ← 人群/現場喧躁音帶通壓制與清洗
    │   ├── LoudnessNormalizeNode          ← -18 LUFS + Soft Knee -1.0 dBTP
    │   └── WriteNormalizedWAVNode         ← 分層匯出 A(raw), B(normalized), C(denoised) 三版音訊
    └── PassthroughNode                    ← 落盤與複製三版音訊
```

### 業界標準數值與 ABC 三版設計

| 版本標示 | 檔名命名 | 處理內容 | 最佳適用情境 |
|---|---|---|---|
| **A 版 (Raw)** | `{name}_raw.wav` | **零處理** 原始備份 | 原始素材保存 |
| **B 版 (Normalized)** | `{name}_normalized.wav` | 祛直流 + 極性校正 + 靜音修剪 + -18 LUFS | 人耳監聽、主唱採譜、聽感試聽 (`audio_path`) |
| **C 版 (Denoised)** | `{name}_denoised.wav` | B 版 + Minimum Statistics 頻譜降噪 + 人群雜訊過濾 | 後續 Beat Tracking 與 Demucs 分軌最佳化 (`target_analysis_path`) |

### Blackboard 輸出契約

| Key | 值 |
|---|---|
| `y` | 處理後 (B 版) numpy array |
| `y_denoised` | 深度降噪 (C 版) numpy array |
| `sr` | 取樣率 (int) |
| `quality_report` | 所有偵測數值 dict |
| `quality_flags` | 所有 bool flags dict |
| `quality_grade` | "A"/"B"/"C"/"WARN"/"FAIL" |
| `quality_optimized` | bool |
| `trim_offset_sec` | 截掉的開場靜音秒數 (預設 0.0) |
| `raw_wav_path` | A 版原聲檔路徑 (`{project_dir}/source/{name}_raw.wav`) |
| `normalized_wav_path` | B 版輕度修復檔路徑 (`{project_dir}/source/{name}_normalized.wav`) |
| `denoised_wav_path` | C 版深度降噪檔路徑 (`{project_dir}/source/{name}_denoised.wav`) |
| `target_analysis_path` | 自動對齊 C 版 (`denoised_wav_path`)，提供 AI 最強辨識度 |

---

## 四、Stage 2 — 自動分軌 BT

**狀態：✅ 完整實作並 SDD 測試通過（2026-07-25）**

### 實作位置

- 節點：[`pgm_craft/workflow/stem_separation_bt.py`](../pgm_craft/workflow/stem_separation_bt.py)
- 測試：[`tests/test_sdd_pass18.py`](../tests/test_sdd_pass18.py)（13 tests passed）

### BT 樹結構

```
## 四、Stage 2 — 需求驅動樂器分軌 BT

**狀態：✅ 完整實作並 SDD 測試通過（2026-07-26）**

### 實作位置

- 節點：[`pgm_craft/workflow/stem_separation_bt.py`](../pgm_craft/workflow/stem_separation_bt.py)
- 分離引擎：[`pgm_craft/separator.py`](../pgm_craft/separator.py)
- 測試：[`tests/test_sdd_pass18.py`](../tests/test_sdd_pass18.py)（13 tests passed）及 [`tests/test_peel_core_trio.py`](../tests/test_peel_core_trio.py)

### BT 樹結構（按需懶加載 Lazy Guard + 遞減層疊 + 同層動態減算）

```
Sequence [StemSeparationRoot]
├── EnsureStemsFolderNode                       ← 1. 建立 project_dir/stems/ 目錄
│
├── Fallback [VocalsBranchFallback]             ← 2. 【第 1 階：人聲與和聲家族】(以 Stage 1 C 版檔輸入)
│   ├── Sequence [VocalsBranch]                 │    - DetectVocalPresenceNode 按需短路探測 (prob >= 0.25)
│   │   ├── DetectVocalPresenceNode             │    ➔ SeparateVocalsNode 分離 vocals/vocals.wav 與 根目錄 instrumental.wav
│   │   ├── SeparateVocalsNode                  │    - DetectHarmonyPresenceNode (只對純 vocals.wav 局部探測)
│   │   └── Fallback [HarmonyBranchFallback]    │    ➔ SeparateLeadAndBackingNode 拆分 lead_vocal.wav 與 backing_vocals.wav
│   │       ├── Sequence [HarmonyBranch]        │    ➔ VocalDeBreatheNode 過濾口水音氣音 (vocals_debreathed.wav)
│   │       │   ├── DetectHarmonyPresenceNode   │
│   │       │   ├── SeparateLeadAndBackingNode  │
│   │       │   └── VocalDeBreatheNode          │
│   │       └── SkipHarmonyPassthrough          │
│   └── SkipVocalsPassthrough                   │
│
├── Fallback [DrumsBranchFallback]              ← 3. 【第 2 階：鼓組家族】(以 instrumental.wav 輸入)
│   ├── Sequence [DrumsBranch]                  │    - DetectDrumsPresenceNode 探測鼓組
│   │   ├── DetectDrumsPresenceNode             │    ➔ SeparateDrumsNode 產出 drums/drums.wav (中間殘音 no_drums 內存傳遞不落盤)
│   │   ├── SeparateDrumsNode                   │    ➔ SubSplitDrumsNode 二階細分 kick.wav / snare.wav / hihat_cymbals.wav
│   │   └── SubSplitDrumsNode                   │
│   └── SkipDrumsPassthrough                    │
│
├── Fallback [BassBranchFallback]               ← 4. 【第 3 階：貝斯家族】(以 no_drums 記憶體音軌輸入)
│   ├── Sequence [BassBranch]                   │    - DetectBassPresenceNode 探測低音
│   │   ├── DetectBassPresenceNode              │    ➔ SeparateBassNode 產出 bass/bass.wav (帶 40-60Hz Sub-Harmonics 補全，other 不落盤)
│   │   ├── SeparateBassNode                    │    ➔ SubSplitBassNode 二階細分 electric_bass.wav 與 synth_bass_808.wav
│   │   └── SubSplitBassNode                    │
│   └── SkipBassPassthrough                     │
│
├── Fallback [PeelCoreTrioBranchFallback]       ← 5. 【第 4 階：吉他/鋼琴/弦樂 同層動態減算】(以去鼓去貝斯殘音輸入)
│   ├── Sequence [PeelCoreTrioBranch]           │    - DetectGuitarPresenceNode 探測動態和聲樂器
│   │   ├── DetectGuitarPresenceNode            │    ➔ PeelCoreTrioNode 即時動態比對 Guitar/Piano/Strings 顯著度
│   │   └── PeelCoreTrioNode                    │    ➔ 洋蔥式 (Peel-and-Subtract) 剝離最高分音軌
│   │                                           │    ➔ 吉他細分: acoustic_guitar.wav / electric_guitar.wav / guitar_left / guitar_right
│   │                                           │    ➔ 鋼琴細分: piano_treble_hand.wav / piano_bass_hand.wav / electric_rhodes_piano
│   │                                           │    ➔ 弦樂細分: violins_viola.wav / cello_doublebass.wav / pizzicato / legato
│   └── SkipPeelCoreTrioPassthrough             │
│
├── StrictStemDirectoryGuardNode                 ← 6. 【Stems 音色資料夾隔離衛兵】(移除非白名單副產品與異物檔，按需歸類)
│
└── RegisterStemsToBlackboardNode               ← 7. 遞迴註冊純音軌檔至 Blackboard (過濾 no_*, residual_* 殘餘檔)
```

### 嚴格音色資料夾隔離契約 (Strict Stem Directory Isolation)

- **`stems/` 根目錄**：僅保留 `no_vocals.wav`（純去人聲伴奏）與 `instrumental.wav`（全樂器剝離殘音）。
- **`stems/{instrument}/` 子目錄**：只允許放置屬於該音色白名單之音檔（例如 `vocals/` 內絕不出現 `bass.wav` 或 `drums.wav`），其餘在分軌過程由 Demucs 多軌落盤產生之異物音檔自動移出或刪除清理。

### Blackboard 輸出契約

| Key | 值 |
|---|---|
| `stems_dir` | `{project_dir}/stems/` 路徑 |
| `stems` | `dict`: `{"vocals": path, "lead_vocal": path, "drums": path, "kick": path, "bass": path, "guitar": path, ...}` |
| `target_analysis_path` | 自動對齊最適合進行節拍分析的音軌 (stems/drums/drums.wav > stems/instrumental.wav > C版降噪檔) |
| `stem_separation_status` | `"SUCCESS"` \| `"SKIPPED"` \| `"FAILURE"` |

### 錄音室級 Session 交付目錄規範

```
{project_dir}/stems/
  ├── instrumental.wav            ← 留存全曲純伴奏 (無人聲)
  ├── vocals/                     ← 🎤 人聲家族 (vocals.wav, lead_vocal, backing_vocals, vocals_debreathed, breath_noises)
  ├── drums/                      ← 🥁 鼓組家族 (drums.wav, kick.wav, snare.wav, hihat_cymbals.wav)
  ├── bass/                       ← 🎸 貝斯家族 (bass.wav, electric_bass.wav, synth_bass_808.wav)
  ├── guitars/                    ← 🎸 吉他家族 (guitar.wav, acoustic_guitar, electric_guitar, guitar_left, guitar_right)
  ├── pianos/                     ← 🎹 鋼琴家族 (piano.wav, piano_treble_hand, piano_bass_hand, electric_rhodes_piano)
  ├── strings/                    ← 🎻 弦樂家族 (strings.wav, violins_viola, cello_doublebass, pizzicato_strings, legato_bowing_strings)
  └── events/                     ← 🗣️ 非音色/語音事件/環境組 (speech_口白, crowd_現場歡呼, count_in_倒數, hum_電流聲)
```

---

## 五、SDD 測試進度匯總

| SDD Pass | 涵蓋範圍 | 測試數量 | 結果 |
|---|---|---|---|
| Pass 3–13 | 各獨立節點與降級邏輯單元測試 | 65+ | ✅ |
| Pass 14 | HPSS / DownbeatRefine / MIDI Tempo | - | ✅ |
| Pass 15 | AI 模型狀態標記 / MasterBT 同步 | - | ✅ |
| **Pass 16** | **Stage 0 Input Acquisition BT** | 43 | ✅ 2026-07-25 |
| **Pass 17** | **Stage 1 Audio Quality & Multi-tier Denoise BT** | 68 | ✅ 2026-07-26 |
| **Pass 18** | **Stage 2 Stem Separation BT** | 13 | ✅ 2026-07-25 |
| **Pass 19** | **非音色/語音事件/環境組跨 Stage BT** | 5 | ✅ 2026-07-26 |
| **Pass 20** | **三梯隊同層樂器動態減算 (3-Tier Peel-and-Subtract Loop)** | 2 | ✅ 2026-07-26 |
| **Pass 21** | **CLAP 語意探測門閥與 Formant 物理破壞 Rollback Guard** | 3 | ✅ 2026-07-26 |
| **Pass 22** | **Stems 音色資料夾嚴格隔離衛兵 (Strict Stem Isolation)** | 1 | ✅ 2026-07-27 |
| **Pass 23** | **Stage 3 雙軌併行節拍分析與動態融合 (Dual-Track Beat Fusion)** | 4 | ✅ 2026-07-27 |
| **Pass 25** | **Stage 4 樂段結構專屬 Sub-mix 與段落切分 (Structure Sub-mix & Section BT)** | 2 | ✅ 2026-07-27 |
| **Pass 26** | **Stage 4 拍點格點和弦對齊與平滑化衛兵 (Grid-Constrained Chord BT)** | 2 | ✅ 2026-07-27 |
| **Pass 27** | **Stage 4 BT 順序修正、和聲 Sub-mix 多樂器擴充與小節和弦 Smoothing** | 3 | ✅ 2026-07-27 |
| **Pass 28** | **Stage 3 Count-In/Clap 事件 1 號拍錨定、 Validation 維度防護與音波緩存** | 3 | ✅ 2026-07-27 |
| **Pass 29** | **Stage 5 Export BT 重構、DAW Section Markers 導出與工程交付** | 2 | ✅ 2026-07-27 |
| **Pass 30** | **Stage 0~5 全管道整合修復、Pipeline 順序調整與專案 Session 落盤對齊** | 1 | ✅ 2026-07-27 |
| **Pass 31** | **前端 Stage 1~5 選擇器 UI 補全與後端 BT 樹動態階段截斷** | 2 | ✅ 2026-07-27 |
| **Pass 32** | **Stage 6 PackageRoot Behavior Tree 重構與 DAW 全套素材包自動歸檔** | 2 | ✅ 2026-07-27 |
| **Pass 33** | **舞台語音提示音軌合成 (Voice Cue Guide Synthesis)** | 1 | ✅ 2026-07-27 |
| **Pass 34** | **AI 貝斯與主旋律 MIDI 獨立導出 (`bass_line.mid`, `lead_melody.mid`)** | 1 | ✅ 2026-07-27 |
| **Pass 35** | **Groove Micro-timing 雙軌 MIDI 律動導出** | 1 | ✅ 2026-07-27 |
| **Pass 36** | **Web-based Live 舞台動態滾動提詞器 HTML 自動化** | 1 | ✅ 2026-07-27 |
| **Pass 37** | **Lyrics-to-Marker MIDI Text Event 歌詞標註** | 1 | ✅ 2026-07-27 |
| **Pass 38** | **Pro Tools / AAF 全 DAW 泛用工程包 (`project_protools.aaf`)** | 1 | ✅ 2026-07-27 |
| **Pass 39** | **Kick & Snare 獨立聲學脈衝提取衛兵 (`KickSnarePulseNode`)** | 1 | ✅ 2026-07-27 |
| **Pass 40** | **Tempo Inertia 速度慣性等速內插引擎 (無鼓區間 Click 防摔)** | 1 | ✅ 2026-07-27 |
| **Pass 41** | **Re-Entry Re-Anchoring 鼓聲切入第一拍自動校正重錨衛兵** | 1 | ✅ 2026-07-27 |
| **Pass 42** | **Stage 3 Behavior Tree 全管道連動與無鼓/切入重音防禦測試** | 2 | ✅ 2026-07-27 |
| **Pass 43** | **HarmonicSilenceGateNode (和聲靜音閘門，消滅前奏/尾奏 Ghost Chords)** | 1 | ✅ 2026-07-27 |
| **Pass 44** | **DownbeatAlignedSectionNode (樂段 100% 強制吸附對齊小節第 1 拍)** | 1 | ✅ 2026-07-27 |
| **Pass 45** | **MultiBandChromaKeyNode (Bass 根音 + 鋼琴和聲多頻段色譜調性校正)** | 1 | ✅ 2026-07-27 |
| **Pass 46** | **Stage 4 Behavior Tree 全管道連動與和聲/樂段小節對齊測試** | 2 | ✅ 2026-07-27 |
| **Pass 47** | **ReEntryReAnchoringNode v2 鼓聲切入精確重錨與 DownbeatRefine Median Filter** | 18 | ✅ 2026-07-27 |
| **Pass 48** | **專項音訊分離模型 (Specialized Stem Models) 與前處理適配器 (Input Guard Adapter)** | 4 | ✅ 2026-07-27 |
| **Pass 49** | **CREPE / BasicPitch 採譜專項護航與 Ghost Note 碎音濾波** | 2 | ✅ 2026-07-27 |
| **Pass 50** | **二階音色細分的動態顯著度早停 (Presence Early Exit Guard)** | 2 | ✅ 2026-07-27 |
| **Pass 51** | **變拍子動態感應器 (3/4 & 4/4) 與 REAPER `.RPP` 原生工程導出器** | 2 | ✅ 2026-07-27 |
| **Pass 52** | **PeelCoreTrio 同層顯著度門檻調優 (0.20) 與殘軌污染消除** | 1 | ✅ 2026-07-27 |
| **Pass 53** | **BasicPitch / CREPE 可選 AI 採譜模組安裝與避坑指南補全** | DOC | ✅ 2026-07-27 |
| **Pass 54** | **P0 雙核：1 小節開頭預備拍 Count-In 導引與 7/sus4/add9 擴展和弦識別** | 2 | ✅ 2026-07-27 |
| **Pass 55** | **P1 雙核：Sub-Bass 40-100Hz 低頻聲學對位與 Live Web Audio 視聽同步面板** | 1 | ✅ 2026-07-27 |
| **Pass 56** | **P1 雙核：立體聲 180 度相位反相翻轉修復衛兵與 UTF-8 Unicode Zip 跨平台解壓護航** | 2 | ✅ 2026-07-27 |
| **Pass 57** | **Ableton Live `.als` 原生專案檔導出器 (Gzip XML, Tempo Map & Locators 鏈路對齊)** | 1 | ✅ 2026-07-27 |
| **Pass 58** | **獨立影音下載區塊 (STAGE 1) 升級：線上 Audio Previewer 預聽與 ID3 Tag 標籤寫入** | 1 | ✅ 2026-07-27 |
| **Pass 59** | **兩階層應用場景與狀態機工作流註冊表 (6 大領域, 21 細分狀態機與 UI 雙選單動態聯動)** | 2 | ✅ 2026-07-27 |
| **Pass 60** | **Podcast 工作流 1-1：雙人/多人訪談聲音淨化狀態機 (DeHum ➔ Denoise ➔ DeReverb ➔ R128)** | 1 | ✅ 2026-07-27 |
| **Pass 61** | **Podcast 工作流 1-2：播客音量 EBU R128 自動標準化與防剪峰狀態機 (LoudnessNormalize ➔ SaveMaster)** | 1 | ✅ 2026-07-27 |
| **聯合測試** | **全套系統核心與 Stage 0~6 BT 整合驗證** | **212** | ✅ **100% 通過** |

---

## 六、Blackboard 全域契約（跨 Stage 運作流）

```
[Stage 0]
audio_path ➔ {project_dir}/source/{name}.wav
project_dir ➔ {project_root}/{project_name}/

[Stage 1]
raw_wav_path ➔ {project_dir}/source/{name}_raw.wav (A 版)
normalized_wav_path ➔ {project_dir}/source/{name}_normalized.wav (B 版)
denoised_wav_path ➔ {project_dir}/source/{name}_denoised.wav (C 版)
crowd_path ➔ {project_dir}/source/crowd_cheering.wav (Pre-Vocal 剝離現場歡呼聲)
dereverb_dry_path ➔ {project_dir}/source/dereverb_dry.wav (Pre-Vocal 還原極乾聲)
target_analysis_path ➔ {project_dir}/source/{name}_denoised.wav (AI 分析導向)
quality_grade ➔ "A" | "B" | "C" | "WARN" | "FAIL"
quality_report ➔ 完整音訊數據報告

[Stage 2]
stems ➔ {"vocals": path, "lead_vocal": path, "drums": path, "kick": path, "organ": path, "sub_bass_808": path, "synth_pads": path, ...}
no_vocals_path ➔ {project_dir}/stems/no_vocals.wav (純去人聲伴奏檔，完整保留鼓/貝斯/吉他/鋼琴/弦樂/Synth)
instrumental_path ➔ {project_dir}/stems/instrumental.wav (全套動態減算後之保真殘音檔)
clap_similarity_score ➔ CLAP 語意相似度分數 (>= 0.35 始進行 Tier-3 剝離)
formant_guard_status ➔ "PASSED" | "PASSED_NO_CHANGE" | "ROLLBACK_EXECUTED" (失真超標自動還原)
target_analysis_path ➔ 指向最精準節拍音軌 (stems/drums/drums.wav > stems/instrumental.wav > denoised_wav_path)

[Stage 3 雙軌併行與融合]
rhythm_track_path ➔ {project_dir}/stems/submix/track_a_rhythm.wav (A軌 Drums+Bass 骨幹)
inst_track_path ➔ {project_dir}/stems/no_vocals.wav (B軌 純伴奏全音軌)
beats_rhythm / beats_inst ➔ A/B 軌各自特徵節拍陣列
conf_rhythm / conf_inst ➔ A/B 軌信心度分數
beats ➔ 經 BeatFusionArbitratorNode 仲裁能量段落與無鼓補全後之最終微秒級節拍陣列
count_in_events / clap_events ➔ 用於 DownbeatRefineNode 第一拍 (Downbeat) 第一小節對對齊與弱起對位
beat_fusion_report ➔ 雙軌融合採納統計報告

[Stage 4 和聲與樂理分析]
harmonic_track_path ➔ {project_dir}/stems/submix/track_stage4_harmonic.wav (Piano+Guitar+Bass+Organ+Strings+Pads 無鼓無人聲 Sub-mix)
structure_track_path ➔ {project_dir}/stems/submix/track_stage4_structure.wav (Vocals+Drums+Other 樂段結構 Sub-mix)
estimated_key ➔ 樂曲主調性 (如 "C Major", "A Minor")
grid_constrained_chords ➔ 按小節多數決對齊與平滑化後之純淨和弦進行
chord_progression ➔ 逐小節和弦進程陣列 (包含 start_time, end_time, chord, measure)
section_structure ➔ 樂曲 Intro/Verse/Chorus/Bridge 段落結構
measure_map ➔ 小節與時間對齊地圖 (含完整變動小節長度)

[Stage 5 成果導出與 DAW 素材交付]
click_track ➔ {project_dir}/click/click_track.wav (高低音打點音軌)
mix_with_click ➔ {project_dir}/click/mix_with_click.wav (原曲+Click預聽檔)
tempo_map_midi ➔ {project_dir}/midi/tempo_map.mid (BPM與小節變速度曲線軌)
click_guide_midi ➔ {project_dir}/midi/click_guide.mid (對齊節拍點 MIDI 軌)
chord_guide_midi ➔ {project_dir}/midi/chord_guide.mid (和弦 MIDI 導引軌)
section_markers_midi ➔ {project_dir}/midi/section_markers.mid (DAW 樂段 Marker 標籤軌)

[Stage 6 工程專案歸檔與素材包交付]
project_package_dir ➔ {project_dir}/pgm_project_package/ (完整 DAW 素材包目錄)
zip_archive ➔ {project_dir}/pgm_project_package.zip (純淨壓縮高密度 zip 檔)
live_dashboard ➔ {project_dir}/pgm_project_package/reports/live_dashboard.html (Live 舞台指示面板)
markers_csv ➔ {project_dir}/pgm_project_package/tempo_track_cubase.csv (Cubase / 泛用 Marker CSV)
import_guide ➔ {project_dir}/pgm_project_package/IMPORT_GUIDE.md (DAW 匯入說明文件)
```

---

## 七、變更日誌

| 日期 | 變更說明 |
|---|---|
| 2026-07-27 | 完成 **Pass 61: Podcast 工作流 1-2：播客音量 EBU R128 自動標準化與防剪峰狀態機**：<br>1. **`build_podcast_r128_normalize_workflow`**：建立由 AudioLoad ➔ LoudnessNormalize (-16 LUFS, True Peak <= -1.0 dBFS) 構成之狀態機<br>2. **UI & 管道整合**：選取 `podcast_r128_normalize` 時一鍵觸發狀態機，輸出 Mastered 音檔 `podcast_mastered_-16lufs.wav`<br>3. 通過 SDD Pass 61 單元測試 (`tests/test_sdd_pass61.py`, 1 passed) |
| 2026-07-27 | 完成 **Pass 60: Podcast 工作流 1-1：雙人/多人訪談聲音淨化狀態機**：<br>1. **`build_interview_clean_workflow`**：建立由 DeHum ➔ Denoise ➔ DeReverb ➔ LoudnessNormalize (-16 LUFS) 構成之 Behavior Tree 狀態機<br>2. **UI & 管道整合**：選取 `podcast_interview_clean` 時一鍵觸發狀態機，輸出廣播級淨化檔 `interview_clean_speech.wav`<br>3. 通過 SDD Pass 60 單元測試 (`tests/test_sdd_pass60.py`, 1 passed) |
| 2026-07-27 | 完成 **Pass 59: 兩階層應用場景與狀態機工作流註冊表 (6 大領域, 21 細分狀態機與 UI 雙選單動態聯動)**：<br>1. **`ScenarioManager`**：建立 6 大領域 (Podcast, Vlog, Vocal, Transcribe, Live PGM, ASMR) 與 21 項細分狀態機工作流註冊表<br>2. **Gradio UI 二級動態聯動**：第一階選擇 Domain ➔ 第二階 `.change()` 即時更新對應之 Workflow 下拉選單<br>3. 通過 SDD Pass 59 單元測試 (`tests/test_sdd_pass59.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 58: 獨立影音無損下載區塊 (STAGE 1) 極致體驗優化**：<br>1. **Audio Previewer 預聽**：下載完成後自動於 UI 渲染 `<audio>` 播放器，提供線上即時聽感確認<br>2. **ID3 Tag 元資料護航**：`inject_id3_metadata` 自動將影片標題與歌手寫入下載音檔<br>3. 通過 SDD Pass 58 單元測試 (`tests/test_sdd_pass58.py`, 1 passed) |
| 2026-07-27 | 完成 **Pass 57: Ableton Live `.als` 原生工程檔導出器**：<br>1. **`generate_ableton_als`**：產出相容 Ableton Live 11/12 之 Gzip XML 工程檔 (`ableton_project.als`)，對齊 Tempo Envelope, Stems 音軌卡槽與 Locators (Markers)<br>2. **`DAWSessionGenerateNode`**：連動將 `.als` 原生專案檔自動歸檔入 DAW 專案素材包<br>3. 通過 SDD Pass 57 單元測試 (`tests/test_sdd_pass57.py`, 1 passed) |
| 2026-07-27 | 完成 **Pass 56 (P1 雙核): 立體聲 180 度相位反相修復衛兵與 UTF-8 Unicode Zip 跨平台解壓護航**：<br>1. **`StereoPhaseCorrectionNode`**：自動檢測左右聲道互相關係數 (corr < -0.5)，自動觸發 180 度相位翻轉修復，消除混縮 Mono 時聲音發空問題<br>2. **`build_zip_archive`**：使用 `zipfile.ZipInfo` + UTF-8 `0x800` 旗標保護日文/中文檔名，跨平台 Windows/macOS 解壓 100% 絕不亂碼<br>3. 通過 SDD Pass 56 單元測試 (`tests/test_sdd_pass56.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 55 (P1 雙核): Sub-Bass 低頻脈衝對位與 Live HTML 提詞器視聽同步**：<br>1. **`KickSnarePulseNode`**：無鼓/前奏區間自動提取 Sub-Bass 40-100Hz 脈衝補充為正拍對位錨點<br>2. **`export_live_dashboard`**：HTML 舞台提詞面板注入 Web Audio API 音訊播放器與 JavaScript 動態小節/和弦高亮滾動引擎<br>3. 通過 SDD Pass 55 單元測試 (`tests/test_sdd_pass55.py`, 1 passed) |
| 2026-07-27 | 完成 **Pass 54 (P0 雙核): 1 小節開頭預備拍 Count-In 導引與 7/sus4/add9 擴展和弦識別**：<br>1. **`synthesize_click`**：產出 Live PGM 1 小節預備拍 Count-In Click 倒數預聽軌<br>2. **`CHORD_TEMPLATES`**：擴充 Chroma 樣板矩陣解碼，精確識別 7, maj7, m7, sus4, add9 擴展和弦<br>3. 通過 SDD Pass 54 單元測試 (`tests/test_sdd_pass54.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 52 & 53: PeelCoreTrio 門檻調優 (0.20) 與 BasicPitch / CREPE 可選 AI 安裝指南** |
| 2026-07-27 | 完成 **Pass 51: 變拍子動態感應與 REAPER `.RPP` 原生工程導出器**：<br>1. **變拍子識別**：`DownbeatRefineNode` 動態感知 3/4 華爾滋與 4/4 標準拍號<br>2. **REAPER `.RPP` 導出**：`DAWExporter` 匯出包含音軌分色、Stems 載入、Marker 時間軸與 Tempo Map 之專案檔<br>3. 通過 SDD Pass 51 單元測試 (`tests/test_sdd_pass51.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 50: 二階音色細分的動態顯著度早停 (Presence Early Exit Guard)**：<br>1. **RMS -40dB 門閥**：鼓組/貝斯二階細分前自動檢測能量，低於門檻時早停 Skip，防止無效空檔落盤<br>2. 通過 SDD Pass 50 單元測試 (`tests/test_sdd_pass50.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 49: CREPE / BasicPitch 採譜專項護航與 Ghost Note 碎音濾波**：<br>1. **`CREPEPitchNode`**：強制選用去氣音純人聲軌 + 3.5kHz 巴特沃斯低通濾波預處理，消滅顫音震盪<br>2. **`BasicPitchNode`**：適配 `-1.0 dBFS` Peak Guard 並對導出 MIDI 進行 `> 80ms` 碎音過濾<br>3. 通過 SDD Pass 49 單元測試 (`tests/test_sdd_pass49.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 48: 專項音訊分離模型 (Specialized Stem Models) 與前處理適配器 (Input Guard Adapter)**：<br>1. **`StemInputGuardAdapter`**：實作 44100Hz 高品質重採樣、Stereo 雙聲道補齊展平 `[2, T]` 與 Peak Safeguard (-1.0 dBFS) 動態防爆音<br>2. **Prerequisite 防呆級聯**：吉他/鋼琴專項分離前自動強制轉為 `Instrumental` 伴奏軌<br>3. **`DemucsCacheGuard`**：MD5 + 檔案大小雙重 Hash 快取，0 秒即時複用<br>4. 通過 SDD Pass 48 單元測試 (`tests/test_sdd_pass48.py`, 4 passed) |
| 2026-07-27 | 完成 **Pass 47: ReEntryReAnchoringNode v2 鼓聲切入精確重錨與 DownbeatRefine Median Filter**：<br>1. **`ReEntryReAnchoringNode` v2**：只對「無鼓→有鼓」邊緣事件重錨（從 280 個 kick 縮減到 5-15 個），重錨後向後重算整段 1-2-3-4 循環並加上 2s 冷卻保護<br>2. **`DownbeatRefineNode`**：加入 measure_length 眾數 Median Filter 容錯保底<br>3. 通過 SDD Pass 47 單元測試 (`tests/test_sdd_pass47.py`, 18 passed) |
| 2026-07-27 | 完成 **Pass 32: Stage 6 PackageRoot Behavior Tree 重構與 DAW 全套素材包自動歸檔**：<br>1. **`package_bt.py`**：實作獨立 `PackageRoot` BT 樹包含 `DAWSessionGenerateNode` (Reaper/Ableton/Logic/Cubase CSV)、`LiveDashboardExportNode` (Live 舞台面板 HTML) 與 `ZIPArchivePackagerNode` (壓縮素材包打包)<br>2. **`packager.py` 素材補全**：補齊 Pass 29 產出之 `section_markers_midi` 入 ZIP 打包白名單<br>3. 通過 SDD Pass 32 單元測試 (`tests/test_sdd_pass32.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 31: 前端 Stage 1~5 選擇器 UI 補全與後端 BT 樹動態階段截斷**：<br>1. **`app.py` UI 升級**：在「🎛️ PGM 節目軌與採譜分析」主頁籤加入「🎯 選擇 BT 執行目標階段 (Stage 1 ~ 5)」下拉選單<br>2. **`builder.py` 截斷**：`build_master_pipeline_tree(target_stage)` 支援動態截斷在指定的 Stage<br>3. 通過 SDD Pass 31 單元測試 (`tests/test_sdd_pass31.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 30: Stage 0~5 全管道整合修復、Pipeline 順序調整與專案 Session 落盤對齊**：<br>1. **順序重排**：將 `ai_parallel_group` 與 `VoiceSplitMIDIExportNode` 前移至 `build_export_tree()` 前，確保 AI 旋律 MIDI 完全進入導出包<br>2. **Session 落盤對齊**：`ClickSynthesisNode` / `MIDIExportNode` / `MIDIMarkerSectionExportNode` 設為 `project_dir` 優先<br>3. 通過 SDD Pass 30 全管道測試 (`tests/test_sdd_pass30.py`, 1 passed) |
| 2026-07-27 | 完成 **Pass 29: Stage 5 Export BT 重構與 DAW Section Markers 素材導出**：<br>1. **`export_bt.py`**：模組化 Stage 5 獨立 Behavior Tree (`ExportRoot`)<br>2. **`MIDIMarkerSectionExportNode`**：將 Stage 4 產出之樂段 (`Intro`/`Verse`/`Chorus`/`Outro`) 寫入 MIDI Text Marker，支援 Cubase/Logic/Ableton 時間軸自動標籤<br>3. **`builder.py` 串接**：將 `build_export_tree()` 正式整合進 Master Pipeline 主樹<br>4. 通過 SDD Pass 29 單元測試 (`tests/test_sdd_pass29.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 28: Stage 3 Count-In/Clap 事件 1 號拍錨定、Validation 維度防護與音波緩存**：<br>1. **喊拍與響指第一拍錨定**：`DownbeatRefineNode` 自動讀取 `count_in_events` / `clap_events` 作為 Downbeat 參考<br>2. **極限維度防禦**：`TrackValidationNode` 增加 `beats.ndim != 2` 防衛<br>3. 通過 SDD Pass 28 單元測試 (`tests/test_sdd_pass28.py`, 3 passed) |
| 2026-07-27 | 完成 **Pass 27: Stage 4 BT 順序修正、和聲 Sub-mix 多樂器擴充與小節和弦 Smoothing**：<br>1. **順序重排**：將 `MeasureMapNode` 調整至 `SectionStructureNode` 前，徹底解決 `measure_map` 空陣列 Bug<br>2. **多樂器 Sub-mix**：`SynthesizeHarmonicTrackNode` 白名單擴充 `organ`, `strings`, `synth_pads` 等 Tier-2 樂器<br>3. **小節和弦多數決**：`GridConstrainedChordNode` 結合 `measure_map` 消除 0.1 秒碎裂和弦抖動<br>4. 通過 SDD Pass 27 單元測試 (`tests/test_sdd_pass27.py`, 3 passed) |
| 2026-07-27 | 完成 **Pass 26: Stage 4 拍點格點和弦對齊與平滑化衛兵 (Grid-Constrained Chord BT) 重構**：<br>1. **`GridConstrainedChordNode`**：利用 Stage 3 的 `beats` 時間格點強制將 Chroma 解碼鎖定在拍點與小節邊界<br>2. **小節 Smoothing**：中值濾波消除單拍 0.1 秒碎裂和弦抖動，確保 100% 符合 MIDI / DAW 工程對齊<br>3. 通過 SDD Pass 26 單元測試 (`tests/test_sdd_pass26.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 25: Stage 4 樂段結構專屬 Sub-mix 與段落切分 (Structure Sub-mix & Section BT) 重構**：<br>1. **`SynthesizeStructureTrackNode`**：合成 Vocals + Drums + Other/No_Vocals 樂段結構 Sub-mix（涵蓋巨觀音色、動態能量與人聲疊軌變化）<br>2. **`SectionStructureNode`**：結合自相似矩陣 (SSM) 與雙重音色能量維度切分 Intro / Verse / Chorus / Bridge / Outro 段落<br>3. 通過 SDD Pass 25 單元測試 (`tests/test_sdd_pass25.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 24: Stage 4 和聲專屬 Sub-mix 與調性/和弦/段落樂理分析 (Harmonic Analysis BT) 重構**：<br>1. **`SynthesizeHarmonicTrackNode`**：合成 Piano + Guitar + Bass 專屬和聲 Sub-mix（零鼓噪聲、零人聲花腔干擾）<br>2. **`build_music_analysis_tree`**：拍點對齊之 Key/Chord 分析、樂曲 Intro/Verse/Chorus 段落切分與小節地圖建置<br>3. 通過 SDD Pass 24 單元測試 (`tests/test_sdd_pass24.py`, 2 passed) |
| 2026-07-27 | 完成 **Pass 23: Stage 3 雙軌併行節拍分析與動態融合 (Dual-Track Beat Fusion) BT 重構**：<br>1. **A 軌 (鼓+Bass 骨幹)**：`SynthesizeRhythmTrackNode` 提供微秒級硬核擊點<br>2. **B 軌 (去人聲伴奏)**：`PrepareInstrumentalTrackNode` 提供連續柱狀和弦與動態特徵<br>3. **動態融合衛兵**：`BeatFusionArbitratorNode` 自動偵測無鼓/前奏 (Intro) 能量空隙並動態切換接管，解決斷拍問題<br>4. 通過 SDD Pass 23 單元測試 (`tests/test_sdd_pass23.py`, 4 passed) |
| 2026-07-27 | 完成 **Pass 22: Stems 音色資料夾嚴格隔離衛兵 (Strict Stem Isolation)**：實作 `StrictStemDirectoryGuardNode`，對 `stems/` 根目錄與各音色子資料夾進行白名單嚴格掃描與雜音過濾。 |
| 2026-07-26 | 完成 **Pass 21: CLAP 語意探測門閥與 Formant 物理破壞 Rollback Guard 整合**：<br>1. **語意門閥**：實作 `CLAPSemanticProbeConditionNode`，相似度 $< 0.35$ 時短路 Skip 避免無效剝離<br>2. **物理防禦與 Rollback**：實作 `FormantSafetyGuardNode`，變形破壞率 $> 0.40$ 時自動觸發 Rollback 還原伴奏殘音<br>3. 通過 Pass 21 測試 (`tests/test_sdd_pass21.py`, 3 passed) 及主 BT 樹契約測試 (19 passed) |
| 2026-07-26 | 完成 **Pass 20: 三梯隊同層樂器動態減算 (3-Tier Peel-and-Subtract Loop) 整合**：<br>1. **Tier-1 Core Trio** (Guitar, Piano, Strings, 門檻 0.10)<br>2. **Tier-2 High-Confidence** (Organ, Sub-Bass 808, Glockenspiel, 門檻 0.15)<br>3. **Tier-3 Medium-Confidence** (Synth Pads, Brass, Saxophone, Accordion, 嚴格 Guard 門檻 0.25)<br>4. 修復所有 BT 節點 `output_keys` 契約宣告，`test_bt_workflow.py` (19 passed) 與 `test_sdd_pass20.py` (2 passed) 100% 綠燈 |
| 2026-07-26 | 完成 **Pass 19: 非音色 / 語音事件 / 環境場景組跨 Stage 整合**：<br>1. **Pre-Vocal 淨化 (Stage 1)**：整合 `DeHumFilterNode` (50/60Hz 電流聲)、`SeparateCrowdNode` (現場歡呼聲) 與 `DeReverbFilterNode` (還原 Studio 極乾聲)<br>2. **Post-Vocal 精細事件 (Stage 2)**：整合 `ExtractCountInVoiceNode` (1-2-3-4 喊拍倒數) 與 `ExtractClapSnapEventsNode` (拍手響指脈衝，供 Downbeat 對齊)<br>3. 建立 `stems/events/` 專屬 Session 交付目錄規範，通過 Pass 19 測試 (127 項測試 100% 通過) |
| 2026-07-26 | 完成 **Stage 2 樂器家族二階細分與錄音室級 Session 結構**：<br>1. **人聲**：新增 De-Breathe 換氣與口水音過濾 (`vocals_debreathed.wav`)<br>2. **鼓組**：新增 Kick (大鼓) / Snare (小鼓) / HiHat (踩鈸) 三分拆<br>3. **貝斯**：新增 Sub-Harmonics 倍頻補全與 Electric / Synth 808 拆分<br>4. **吉他/鋼琴/弦樂**：新增木電吉他/L-R Pan、鋼琴高低手 C4 切分、弦樂撥拉聲部二階細分 |
| 2026-07-26 | 重構 Stage 2 為 **按需短路懶加載 (Lazy Guard) + 遞減層疊順序 + 吉他鋼琴弦樂動態同層減算 (Peel-and-Subtract Loop)** 架構，中間殘音自動過濾不落盤 |
| 2026-07-26 | 升級 Stage 1 為 **ABC 三版 (Raw/Normalized/Denoised) 分層降噪與落盤機制**，自動更新 Blackboard 契約並優先指定 C 版供 AI 節拍追蹤分析 |
| 2026-07-25 | 完成 Stage 0, Stage 1, Stage 2 全部實作與 SDD 測試（122 項測試 100% 通過） |
| 2026-07-25 | 將 Stage 0~2 正式整合至 `builder.py` 主 BT 樹、`pipeline.py` 及 `app.py` Web 前端 |
| 2026-07-25 | Stage 1 加入 `CrowdNoiseRemovalNode` 人群現場噪聲清洗壓制節點 |
| 2026-07-25 | Stage 1 加入 `WriteNormalizedWAVNode` 寫入優化音檔至專案 `source/` 目錄 |
| 2026-07-25 | 建立本文件，同步全自動工作流 BT 狀態 |

