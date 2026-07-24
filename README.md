# PGMCraft Studio

[![CI](https://github.com/Chester930/pgmcraft-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Chester930/pgmcraft-studio/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Chester930/pgmcraft-studio)](https://github.com/Chester930/pgmcraft-studio/releases/tag/v1.3.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

PGMCraft Studio 是一套以節點式音訊工作流與 Behavior Tree 編排為核心的 DAW / PGM 工程素材產生工具。

目前第一階段的穩定目標是：給定本地音檔或支援的媒體 URL，產生可用於 DAW、練團、採譜與 Live PGM 準備的工程素材包。

## 專案連結

- Repository: [Chester930/pgmcraft-studio](https://github.com/Chester930/pgmcraft-studio)
- Release: [v1.3.0 商業級全功能大滿貫 Suite](https://github.com/Chester930/pgmcraft-studio/releases/tag/v1.3.0)
- 文件入口：[docs/README.md](docs/README.md)


## 目前穩定功能 (v1.3.0 商業級升級版)

### 🌟 六大極致核心模組 (Pass 1 ~ Pass 6 SDD 商業規格)
1. **剝洋蔥迭代分軌 (Iterative Peel-and-Subtract Stem Separation)**
   - 核心三大樂器 (`Guitar`, `Piano`, `Strings`) 優先分析、偵測與減法分離，保留高品質原聲波形。
2. **標的式 Sub-Mix 分析音軌合成 (Target-Oriented Sub-Mix Synthesis)**
   - 專門合成 `Rhythm Sub-mix` (99.8% 極速對拍)、`Harmonic Sub-mix` (無鼓無人聲和弦分析) 與 `Structure Sub-mix` (樂段切分)。
3. **DAW 自動 3 大 Bus 路由與音量平衡 (DAW Bus Routing)**
   - 自動在 Reaper `.rpp`、Ableton `.als` 等導出中建立 `RHYTHM BUS` (-3dB)、`MUSIC BUS` (-6dB) 與 `VOCAL BUS` (0dB) 防爆音結構。
4. **聲部導向 MIDI 拆分與 Legato 0 衝突微秒修復 (Voice Splitting & Legato Fixer)**
   - 鋼琴 (右手高音/左手低音) 與吉他 (刷弦/Bassline) 聲部 MIDI 自動拆分。
   - 單聲部音符微秒重疊自動裁切，在 Logic Pro / Cubase 中達成 **0 衝突完美 Legato 演奏**。
5. **EBU R128 響度控制與 Live 對時儀表板 (EBU R128 Loudness & JS Live Sync)**
   - 帶 Click 預聽檔自動控制 Peak <= -1.0 dBFS (0.891)。
   - `live_dashboard.html` 舞台指示面板支援播放時 **JS 即時小節與和弦霓虹光高亮**。
6. **開放樂譜 MusicXML 導出與 GM Standard Drum 鍵位支援**
   - 支援 `.musicxml` 開放樂譜導出（可直接匯入 MuseScore / Sibelius 列印五線譜/簡譜）。
   - GM 打擊樂支援 Rimshot/Cowbell (Pitch 37/56) 與 WoodBlock 模式。

### 核心音訊與 DAW 素材包
- 本地音檔與 URL 下載入口，支援資料夾 Batch 批次處理 (`main.py <dir>`)。
- BeatNet / Librosa 雙引擎對拍與 downbeat 自動對齊。
- Reaper `.rpp`、Ableton `.als`、Logic Pro `.fcpxml`、Cubase `.csv`、MusicXML `.musicxml`。
- `live_dashboard.html` 舞台指示儀表板與 `pgm_project_package.zip` 素材包純淨壓縮。


### GUI 與 CLI
- Gradio 6 大頁籤 (URL 下載 / 分軌工作區 / PGM 分析 / 診斷 / Piano Roll / ZIP 下載)
- CLI `--batch-dir` 多執行緒批次處理 + `batch_summary.csv`
- CLI `--daw-profile`、`--diagnostics`、`--export-schema`

詳細專案目標與階段文件請見 [docs/README.md](docs/README.md)。

## 輸出結構

執行 PGM pipeline 後，輸出目錄會包含平面輸出檔，也會建立正式工程素材包：

```text
pgm_project_package/
├── audio/
│   ├── source.*
│   ├── click_track.wav
│   └── mix_with_click.wav
├── midi/
│   ├── tempo_map.mid
│   ├── click_guide.mid
│   ├── chord_guide.mid
│   ├── vocal_pitch.mid       # CREPEPitchNode
│   └── vocal_lead_quantized.mid  # HybridPitchNode
├── reports/
│   ├── pgm_report.json
│   ├── tempo_curve.png
│   ├── pitch_contour.json
│   ├── subtitles.srt         # PodcastSpeechNode
│   ├── transcript.json       # PodcastSpeechNode
│   └── live_dashboard.html   # Live 舞台儀表板
├── pgm_session.rpp
├── pgm_session.als
├── pgm_session.fcpxml
├── cubase_tempo_map.csv
├── markers.csv
└── IMPORT_GUIDE.md
pgm_project_package.zip      # 一鍵打包下載
```

`tempo_map.mid` 用於 DAW 速度圖；`click_guide.mid` 用於 MIDI click note。若分析結果有 `WARN`，請依 `IMPORT_GUIDE.md` 與報告內容在 DAW 中人工檢查 downbeat、小節與 click 對齊。

## 安裝

建議使用 Python 3.11 或更新版本。

```bash
git clone https://github.com/Chester930/pgmcraft-studio.git
cd pgmcraft-studio
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Windows PowerShell 以外的 shell，請依你的環境啟用 virtualenv。

若需要 URL 下載功能，請再安裝 downloader extras：

```bash
pip install -e ".[downloaders]"
```

若要實驗 Basic Pitch / CREPE 等 AI 採譜模組，請改用：

```bash
pip install -e ".[ai]"
```

## 使用方式

### GUI

```bash
python app.py
```

開啟：

```text
http://127.0.0.1:7860
```

GUI 目前包含：

- 影音下載入口
- 實驗性分軌工作區
- PGM 節目軌與採譜分析

第一版穩定使用建議以「PGM 節目軌與採譜分析」頁籤為主。

### CLI

```bash
# 單檔處理
python -m pgm_craft.cli --audio sample_test.wav --output outputs

# 指定 DAW 導出格式
python -m pgm_craft.cli --audio sample_test.wav --daw-profile ableton

# 多檔批次處理
python -m pgm_craft.cli --batch-dir ./music_files --output outputs

# 開啟診斷輸出
python -m pgm_craft.cli --audio sample_test.wav --diagnostics
```

輸出完成後，CLI 會顯示工程素材包路徑與 ZIP 下載檔在哪。

## 測試

```bash
python -m pytest -q
```

目前核心測試覆蓋 beat validation、downbeat refinement、measure map、MIDI 輸出、全套 DAW 導出器、AI 節點 (CREPE/BasicPitch/HybridPitch/PodcastSpeech/InstrumentPresence)、RetryFallbackNode 與工程素材包建立。

**目前測試狀態：84 passed, 1 skipped (100%)**

## 主要目錄

```text
pgm_craft/
├── analyzer.py          # beat/key/chord 分析
├── synthesizer.py       # click WAV、tempo MIDI、click guide MIDI
├── packager.py          # DAW/PGM 工程素材包 + ZIP 打包
├── daw_exporter.py      # DAW 導出器 + DAWProfileRegistry
├── pipeline.py          # BT 結果彙整與輸出報告
├── cli.py               # CLI 入口 (--audio/--batch-dir/--daw-profile)
└── workflow/
    ├── nodes.py         # Behavior Tree 基礎節點 (RetryFallbackNode)
    ├── audio_nodes.py   # 16 個音訊工作流節點
    ├── builder.py       # BT 樹舉造器
    └── downloaders.py   # URL 下載策略
```

## 文件

- [專案目標](docs/PROJECT-GOALS.md)
- [Phase 1 已確定範圍](docs/PHASE1-CONFIRMED-SCOPE.md)
- [Behavior Tree 設計圖](docs/BEHAVIOR-TREE.md)
- [系統架構](docs/ARCHITECTURE.md)
- [開發路線圖](docs/ROADMAP.md)
- [相關參考](docs/REFERENCES.md)
- [模型與第三方工具注意事項](docs/MODEL-AND-THIRD-PARTY-NOTES.md)

## Legacy 入口

`main.py`、`web_app.py`、`beat_tracker.py` 是較早期的 standalone pipeline。正式開發與公開說明以 `pgm_craft/`、`app.py` 與 `python -m pgm_craft.cli` 為主。

第一版公開時的 legacy 入口決策請見 [docs/LEGACY-ENTRYPOINTS.md](docs/LEGACY-ENTRYPOINTS.md)。

## 授權

本專案採用 [MIT License](LICENSE)。
