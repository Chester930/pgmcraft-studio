# PGMCraft Studio

[![CI](https://github.com/Chester930/pgmcraft-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Chester930/pgmcraft-studio/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Chester930/pgmcraft-studio)](https://github.com/Chester930/pgmcraft-studio/releases/tag/v2.0.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

PGMCraft Studio 是一套以節點式音訊工作流與 **Behavior Tree (行為樹)** 編排為核心的 DAW / Live PGM 工程素材自動產生系統。

給定本地音檔或網路影音 URL，系統能自動進行 **AI 樂器分軌、雙軌動態節拍對齊、Tempo Inertia 速度慣性脈衝防跳拍、和聲與 Downbeat 樂段對齊**，並一鍵產出適用於 **Pro Tools, Cubase, REAPER, Ableton Live, Logic Pro** 的全套 DAW 工程素材包與 **Live 舞台 HTML 動態滾動提詞器**。

---

## 📚 說明文件導覽

- 🚀 **[初學者 3 分鐘快速上手指南](docs/QUICK-START.md)**（樂手/PGM/DAW 製作人使用情境）
- 🛠️ **[詳細環境安裝與避坑指南](docs/INSTALLATION-GUIDE.md)**（Python, PyTorch GPU, FFmpeg）
- 🎛️ **[全 DAW 素材包匯入教學](docs/DAW-IMPORT-GUIDE.md)**（Pro Tools AAF, REAPER RPP, Cubase CSV）
- 📐 **[系統架構與 Behavior Tree 設計](docs/ARCHITECTURE.md)**

---

## 🚀 3 分鐘快速開始

```bash
# 1. 複製儲存庫
git clone https://github.com/Chester930/pgmcraft-studio.git
cd pgmcraft-studio

# 2. 建立與啟用虛擬環境
python -m venv .venv
.venv\Scripts\activate      # Windows (PowerShell: .venv\Scripts\Activate.ps1)
# source .venv/bin/activate  # macOS / Linux

# 3. 安裝依賴
pip install -r requirements.txt

# 4. 啟動 Web UI 服務
python app.py
```

在瀏覽器訪問 `http://127.0.0.1:7860` 即可開啟 PGMCraft Studio 旗艦級控制介面！

---

## 🌟 八大核心音訊與 PGM 引擎亮點 (v2.0.0)

1. 🥁 **Tempo Inertia 速度慣性脈衝引擎 (Pass 40)**
   - 當曲目進入無鼓區間 (Breakdown / 鋼琴獨奏) 時，系統自動切換為硬體級電子節拍器等速內插，屏蔽 AI 混亂預測，**Click 100% 穩定不亂跳拍**。
2. 🎯 **Re-Entry Re-Anchoring 鼓聲切入重音第一拍自動鎖定 (Pass 41)**
   - 鼓聲重新爆發瞬間 (Re-entry)，自動抓取大鼓 (Kick) 衝擊脈衝，**強制將重音校正重錨為 Beat 1 Downbeat**，消滅錯拍。
3. 🛡️ **HarmonicSilenceGate 和聲靜音門閥 (Pass 43)**
   - 前奏/尾奏留白區間 (RMS < 0.01) 強制屏蔽並消毒，**徹底消滅虛構 Ghost Chords**。
4. 📐 **Downbeat-Aligned Section 樂段 100% 第一拍吸附 (Pass 44)**
   - Intro, Verse, Chorus, Outro 時間點，**100% 強制吸附對齊至最近小節 Measure 1 號拍**，告別切在小節中間拍的痛苦排版。
5. 🎼 **Multi-Band Chroma Key 關係大小調校正 (Pass 45)**
   - 分離 Bass 低頻與中高頻和聲，對 Bass 音高進行 Root Note 重點加權，**消滅 C Major / Am 關係大小調混淆**。
6. 🎤 **Web-based Live 舞台動態滾動提詞器 (Pass 36)**
   - 自動生成 `live_dashboard.html`，可在 iPad/筆電播放器隨音樂平滑自動滾動顯示小節、和弦與歌詞。
7. 🎧 **Voice Cue Guide 舞台語音倒數導引 (Pass 33)**
   - 自動生成 `voice_cue_guide.wav` 舞台導唱/數拍語音倒數音軌。
8. 📦 **Pro Tools / AAF 全 DAW 泛用工程包 (Pass 38)**
   - 自動打包匯出包含 `project_protools.aaf`、`pgm_session.rpp`、`pgm_session.als` 與 `cubase_tempo_map.csv` 之純淨 ZIP 包。

---

## 💻 CLI 命令行批次處理

```bash
# 單一檔案分析
python main.py input.wav --output-dir outputs --enable-stem

# 資料夾多執行緒批次自動化處理
python main.py ./my_songs_folder --batch-dir
```

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
