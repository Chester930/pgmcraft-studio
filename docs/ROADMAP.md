# 開發路線圖

**最後更新：** 2026-07-22

本路線圖定義 PGMCraft Studio 的階段。每個階段都應產生一個可理解、可測試、可繼續擴充的專案狀態。

## Phase 0：版控與專案基線

狀態：大致完成。

目標：

- 初始化 Git 版控
- 忽略產出檔與快取
- 保留測試 fixture 音檔
- 建立專案目標與架構文件
- 將公開宣稱與實作現況分開

目前狀態：

- 本地已建立 Git repository
- 已有初始專案 snapshot commit
- 尚未設定 GitHub remote
- 本地測試通過，但有警告

## Phase 1：PGM 與 DAW 匯出 MVP

狀態：目前主目標。

目標：

建立一條可靠流程，把音訊轉成 PGM 與 DAW-ready 輔助素材。

範圍：

- 本地音檔輸入
- URL 輸入與下載工作流
- 音訊載入與驗證
- BeatNet beat tracking 與 Librosa fallback
- Beat validation
- Measure map 與可變小節長度整理
- Downbeat refine
- BPM 統計
- 速度曲線圖
- Click Track WAV
- 原曲加 Click 的預聽 WAV
- `tempo_map.mid`
- `click_guide.mid`
- JSON 與文字報告
- `pgm_project_package/`
- `IMPORT_GUIDE.md`
- CLI 與 Gradio GUI 執行

完成標準：

- 測試覆蓋核心 pipeline
- 產出檔能匯入 DAW
- README 將此描述為穩定功能集
- 移除使用者介面中的本機絕對路徑預設值

## Phase 2：節點工作流強化

狀態：規劃中。

目標：

讓節點執行更明確、可測試、可重用。

範圍：

- 標準節點輸入與輸出契約
- blackboard key 文件化或型別化
- node status 處理規則
- workflow trace log
- guard node 慣例
- fallback node 慣例
- 適合 GUI 與 CLI 顯示的錯誤訊息
- 每個主要節點的單元測試

完成標準：

- 開發者新增節點時不需要改動無關 pipeline
- 執行後可以檢查 workflow 過程
- 失敗時能看出哪個節點失敗與原因

## Phase 3：DAW 工程素材包

狀態：v1 已在 Phase 1 中建立，進階 DAW profile 規劃中。

目標：

從單一輸出檔，升級成完整 DAW-ready project package。

範圍：

- 穩定輸出資料夾結構
- 每次產生工程素材包時附匯入說明
- Tempo MIDI
- Click guide MIDI
- Click WAV
- 預聽 WAV
- 分析 JSON
- 選用 chord guide MIDI
- 選用 marker files
- 未來 DAW profile 抽象

Phase 1 已完成：

- `pgm_project_package/`
- `audio/`
- `midi/`
- `reports/`
- `IMPORT_GUIDE.md`

範例結構：

```text
project-name/
├── audio/
│   ├── source.wav
│   ├── click_track.wav
│   └── mix_with_click.wav
├── midi/
│   ├── tempo_map.mid
│   └── click_guide.mid
├── reports/
│   ├── analysis_report.json
│   └── analysis_report.txt
└── IMPORT_GUIDE.md
```

完成標準：

- package layout 穩定
- 檔案命名可預期
- DAW 匯入流程有文件

## Phase 4：公開發布整理

狀態：規劃中。

目標：

整理成適合 GitHub public release 的狀態。

範圍：

- 依照實際 MVP 重寫 README
- 將實驗模型宣稱移到 roadmap
- 移除本機路徑
- 釐清 Python 版本支援
- 拆分核心依賴與選用依賴
- 加入 CI
- 加入貢獻指南
- 加入模型與授權注意事項
- 決定 `main.py`、`web_app.py`、`beat_tracker.py` 是否移到 `legacy/`

完成標準：

- fresh clone 後能安裝、測試、執行核心工作流
- 公開宣稱符合實作
- 選用 AI 功能明確標示為 experimental

## Phase 5：AI 輔助音樂模組

狀態：未來階段。

目標：

將真正的 AI 模型整合成選用節點。

候選模組：

- stem separation
- Basic Pitch MIDI transcription
- CREPE pitch tracking
- instrument presence detection
- section detection
- podcast transcription and diarization

完成標準：

- 模型依賴是 optional
- 模型輸出有 fixture 或 golden file 測試
- fallback 行為明確
- 模型授權已記錄
