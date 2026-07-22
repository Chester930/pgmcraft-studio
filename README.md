# 🎛️ PGMCraft Studio

> **AI Audio Stem Separation, Music Transcription & Live PGM Backing Track Suite**  
> **AI 音訊分軌 · 音樂人採譜助手 · 播客 Podcast AI · 現場 PGM 節目軌與 Click 音軌生成系統**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/tests-passing-brightgreen.svg)]()

---

## 📖 專案簡介 (Overview)

**PGMCraft Studio** 是一款專為**音樂創作者**、**樂手聽抄採譜**、**播客 Podcast 節目製作**與**演唱會 Live 現場 PGM 播控**設計的專業級音訊處理工具箱。

本專案整合現代 SOTA 深度學習模型（BS-Roformer, Mel-Band Roformer, HTDemucs v4, BeatNet, Spotify Basic Pitch, CREPE, pyannote.audio, OpenAI Whisper large-v3, DeepFilterNet3），支援**動態行為樹 (Smart Behavior Tree)** 條件防呆控制、**全模型前置保護機制 (Prerequisite Protection)**、**EBU R128 響度放大與聲學降噪**。

---

## ✨ 核心功能 (Key Features)

### 1. 📥 獨立影音無損下載 (Standalone Media Downloader)
- 支援 YouTube, Bilibili, IG Reels, TikTok/抖音, Twitter/X, FB Watch 等平台。
- 自動建立「媒體標題資料夾」，一鍵無損導出 **`MP4` 影片檔**、**`WAV` 無損 PCM 音檔** 與 **`MP3` 壓縮音檔** 3 個檔案。

### 2. 🎛️ 獨立音色與特化分軌 (14 Standalone Stem Extraction Modes)
依據**輸入前置要求 (Input Prerequisites)** 分級隔離：
- 🟢 **類別 A (通用模式)**: 通用 4-Stem (Vocals/Drums/Bass/Other)、人聲分離 (BS-Roformer SDR 12.98dB)、鼓組分離 (HTDemucs FT)、貝斯分離、全自動遞迴層疊分軌。
- 🟡 **類別 B (伴奏/音軌細分模式)**: 鼓組三細分 (Kick/Snare/HiHat)、吉他分離 (BSRNN / 6s)、鋼琴分離 (UVR Piano)、弦樂分離、風琴分離 *(系統自動防呆：先去人聲以提升 SDR +2.5dB)*。
- 🔴 **類別 C (高前置條件模式)**: 主唱 vs 和聲細分 (BS-Roformer Lead/Backing)、人聲換氣與口水音消除 (UVR DeBreathe)、電貝斯 vs 808 合成低音細分 (SynthBass Split)、乾聲去殘響 *(系統自動防呆：自動前置剝離純人聲/純貝斯)*。

### 3. 🎙️ 播客與語音特化 AI (Podcast & Speech AI Suite)
- **多人對話/主持人與來賓分離 (Speaker Diarization)**: 採用 **pyannote.audio** / WhisperX，自動將 Host (主持人) 與 Guest (來賓) 聲紋分離成獨立音軌。
- **微秒級逐字稿與 SRT 字幕 (Speech-to-Text)**: 採用 **OpenAI Whisper (large-v3)**，1 秒自動導出繁體中文逐字稿與 SRT 字幕檔。
- **廣播級電流聲與齒音消除 (Broadcast Voice Enhancer)**: 採用 **DeepFilterNet3**，自動消除 50/60Hz 電流聲 (De-Hum) 與刺耳高頻齒音 (De-Esser)。
- **Podcast 口白與 BGM 音樂分離**: 採用 **UVR-MDX-NET Crowd-Speech**，精確抽離主持人說話聲與背景襯樂。

### 4. 🧠 智能行為樹與條件防呆 (Smart Behavior Tree & Guard Nodes)
- **信噪比與響度防護 Guard**: `CheckAudioSNRCondition` 自動偵測微弱訊號，實行**「先頻譜降噪 ➔ 再適應性增益 (-14 LUFS) ➔ 進行 AI 分離」**。
- **樂器存在性檢測 Guard**: `DetectInstrumentPresenceNode` (PANNs / Audio Tagging)，若樂曲無鋼琴/吉他 (Prob < 0.25)，自動 Skip 該分支，避免產生虛假爆音雜訊。

### 5. 🎹 非分軌高價值音樂 AI 採譜 (Non-Demixing Music AI)
- **多音階 MIDI 採譜 (AMT)**: 整合 **Spotify Basic Pitch**，直出可拖入 DAW 編輯的 MIDI 音符檔。
- **微秒級音高追蹤 (Pitch Tracking)**: 整合 **CREPE** 模型，微秒級分析主唱與樂手 Cents 精度音準與顫音曲線。
- **樂段結構識別 (Music Structure Segmentation)**: 自動標記 `Intro`, `Verse`, `Chorus`, `Bridge`, `Outro` 段落。

---

## 📂 專案架構 (Repository Structure)

```text
PGMCraft/
├── pgm_craft/              # 核心 Python 套件目錄
│   ├── __init__.py
│   ├── separator.py        # 14 大 SOTA 單一音色與多階層層疊分軌引擎
│   ├── podcast_ai.py       # Podcast 多人聲紋分離、Whisper 逐字稿與廣播聲音優化
│   ├── enhancer.py         # EBU R128 響度放大、Soft Limiter 與頻譜降噪模組
│   ├── music_ai.py         # Basic Pitch MIDI 採譜、CREPE 音高追蹤與樂段標記
│   ├── analyzer.py         # BeatNet 節拍追蹤與 Key/Chord 和弦分析
│   ├── synthesizer.py      # Click WAV 合成與 DAW Tempo Map MIDI 導出
│   ├── pipeline.py         # 總控 pipeline 引擎
│   ├── cli.py              # CLI 進入點
│   └── workflow/           # 行為樹 (Behavior Tree) 節點庫
│       ├── nodes.py        # BT 核心基底 (Blackboard, SequenceNode, GuardNode)
│       ├── downloaders.py  # 影音網址分發器 (Strategy Pattern)
│       ├── audio_nodes.py  # 音訊處理行為樹動作節點
│       └── smart_demixing_bt.py # 全模型輸入前置Guard與樂器檢測門控BT
├── tests/                  # 24 個單元測試集 (100% PASS)
│   ├── test_pgm_craft.py
│   ├── test_downloaders.py
│   ├── test_separator_prerequisites.py
│   ├── test_enhancer.py
│   ├── test_smart_demixing_bt.py
│   ├── test_music_ai.py
│   └── test_podcast_ai.py
├── app.py                  # Gradio Web GUI 應用程式進入點 (3 大頁籤)
├── MODELS_GUIDE.md         # SOTA 模型、Podcast AI、前置要求與論文權威指南
├── pyproject.toml          # Standard Python Packaging / Config
├── requirements.txt        # 專案依賴項清單
├── README.md               # 專案說明文件
└── LICENSE                 # MIT 開源授權條款
```

---

## 🚀 快速上手 (Quick Start)

### 1. 安裝環境與依賴 (Installation)

```bash
git clone https://github.com/your-username/pgm-craft.git
cd pgm-craft
pip install -r requirements.txt
```

### 2. 啟動 Web 圖形介面 (Launch Web GUI)

```bash
python app.py
```
造訪 `http://127.0.0.1:7860` 即可使用：
- **頁籤 1**: 📥 獨立影音無損下載 (MP4 / MP3 / WAV)
- **頁籤 2**: 🎛️ 獨立音色分軌工作區 (14 大單一音色 / A/B/C 三色塊隔離)
- **頁籤 3**: 🎛️ PGM 節目軌與採譜分析

---

## 🧪 執行單元測試 (Unit Tests)

```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 📜 授權條款 (License)

本專案採用 [MIT License](LICENSE) 條款開源授權。
完整的模型選用說明、Podcast AI 與學術論文引用請參閱 [MODELS_GUIDE.md](MODELS_GUIDE.md)。
