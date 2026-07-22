# PGMCraft Studio

PGMCraft Studio 是一套以節點式音訊工作流與 Behavior Tree 編排為核心的 DAW / PGM 工程素材產生工具。

目前第一階段的穩定目標是：給定本地音檔或支援的媒體 URL，產生可用於 DAW、練團、採譜與 Live PGM 準備的工程素材包。

## 目前穩定功能

- 本地音檔輸入
- URL 下載入口與音訊準備工作流
- BeatNet beat / downbeat 偵測，Librosa fallback
- Beat validation：檢查 beat 數量、timestamp、BPM 範圍與跳動
- Downbeat refinement：保守補強 downbeat 標籤，不移動 beat 時間點
- Measure map：允許同一首歌內不同小節長度
- BPM 統計與 tempo curve 圖
- `click_track.wav`
- `mix_with_click.wav`
- `tempo_map.mid`，包含 DAW 可讀的 MIDI tempo meta event
- `click_guide.mid`
- `pgm_report.json`
- 文字分析報告
- `pgm_project_package/` 工程素材包
- `IMPORT_GUIDE.md` DAW 匯入說明
- CLI 與 Gradio GUI 入口

## 目前不是穩定功能

以下模組目前應視為 experimental、placeholder 或 roadmap，不應作為第一版穩定承諾：

- 真正具備品質驗證的 Demucs / UVR / BS-Roformer 分軌
- 主唱與和聲分離
- 鼓組細分
- Whisper / pyannote Podcast pipeline
- Basic Pitch / CREPE 正式採譜與音高分析
- 自動樂段辨識
- DAW 專用工程檔案產生

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
│   └── click_guide.mid
├── reports/
│   ├── pgm_report.json
│   ├── tempo_curve.png
│   └── *_pgm_report.txt
└── IMPORT_GUIDE.md
```

`tempo_map.mid` 用於 DAW 速度圖；`click_guide.mid` 用於 MIDI click note。若分析結果有 `WARN`，請依 `IMPORT_GUIDE.md` 與報告內容在 DAW 中人工檢查 downbeat、小節與 click 對齊。

## 安裝

建議使用 Python 3.11 或更新版本。

```bash
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
python -m pgm_craft.cli --audio sample_test.wav --output outputs
```

輸出完成後，CLI 會顯示工程素材包路徑。

## 測試

```bash
python -m pytest -q
```

目前核心測試覆蓋 beat validation、downbeat refinement、measure map、MIDI 輸出與工程素材包建立。

## 主要目錄

```text
pgm_craft/
├── analyzer.py          # beat/key/chord 分析
├── synthesizer.py       # click WAV、tempo MIDI、click guide MIDI
├── packager.py          # DAW/PGM 工程素材包
├── pipeline.py          # BT 結果彙整與輸出報告
├── cli.py               # CLI 入口
└── workflow/
    ├── nodes.py         # Behavior Tree 基礎節點
    ├── audio_nodes.py   # 音訊工作流節點
    └── downloaders.py   # URL 下載策略
```

## 文件

- [專案目標](docs/PROJECT-GOALS.md)
- [Phase 1 已確定範圍](docs/PHASE1-CONFIRMED-SCOPE.md)
- [Behavior Tree 設計圖](docs/BEHAVIOR-TREE.md)
- [系統架構](docs/ARCHITECTURE.md)
- [開發路線圖](docs/ROADMAP.md)
- [相關參考](docs/REFERENCES.md)

## Legacy 入口

`main.py`、`web_app.py`、`beat_tracker.py` 是較早期的 standalone pipeline。正式開發與公開說明以 `pgm_craft/`、`app.py` 與 `python -m pgm_craft.cli` 為主。

## 授權

本專案採用 [MIT License](LICENSE)。
