# 開發脈絡

**最後更新：** 2026-07-22

本文件記錄第一次正式文件整理時的專案脈絡。

## 目前版控狀態

- 本地 Git repository 已建立。
- 目前 branch 是 `main`。
- 已有初始 local commit：`029d072 chore: initial project snapshot`。
- 已有專案目標與架構文件 commit：`2460e17 docs: define project goals and architecture`。
- 尚未設定 GitHub remote。
- GitHub CLI 已登入 `Chester930`。
- 查詢到的 GitHub repo 清單中，未看到明顯對應此專案的 repository。

## 目前測試狀態

最近觀察到的測試命令：

```bash
python -m pytest -q
```

最近觀察到的結果：

```text
35 passed, 1 skipped
```

觀察到的警告：

- Python 3.13 上 `audioread` 觸發 audio 相關 deprecation warning
- `requests` 顯示 urllib3 或 charset package 版本相容性 warning

## 重要實作現況

目前 repository 同時包含可運作的 MVP 部分，以及面向未來的 placeholder。

已可運作或大致可運作的區域：

- 本地音訊分析
- BeatNet 與 Librosa fallback
- BeatValidationNode v1
- 調性與和弦參考分析
- Click Track WAV 合成
- 原曲加 Click 的 WAV 輸出
- `tempo_map.mid` MIDI tempo map 輸出
- `click_guide.mid` MIDI click guide 輸出
- 速度曲線圖
- JSON report
- Gradio GUI 外殼
- CLI 外殼

目前仍屬 placeholder 或 experimental 的區域：

- 多數 stem separation function 目前是複製檔案，不是真正執行分軌模型
- Podcast diarization 與 enhancement 目前寫出 placeholder output
- 部分 music AI function 回傳固定範例資料或最小 fallback 檔
- advanced model registry 是 roadmap 結構，不代表模型已安裝或已可用

公開文件必須保留這個區分。

## 目前形成的架構方向

目前討論後形成的方向：

- 專案主要目標是從音訊產生 DAW 與 PGM 工程素材。
- 可匯入 DAW 的 MIDI 輸出是核心產品功能。
- 系統應設計為節點式音訊工作流。
- Behavior Tree 負責串接節點、guard condition 與 fallback。
- beat tracking 後應先經過 validation，只有 `FAIL` 會停止後續輸出，`WARN` 會繼續但寫入報告。
- AI 分軌與 Podcast 工作流在完成真實整合前，應維持為 extension module。
- 開發階段預設使用繁體中文撰寫討論與文件，除非另有英文版需求。

## 公開發布前需要整理

公開前應處理：

- 依照實際 MVP 重寫 README
- 移除 `your-username` clone placeholder
- 移除 GUI 預設值中的本機絕對路徑
- 公開 GUI code 中避免預設 broad filesystem `allowed_paths`
- 清楚標示已實作功能與 roadmap 功能
- 拆分 core dependencies 與 optional AI/downloader dependencies
- 決定 `main.py`、`web_app.py`、`beat_tracker.py` 是 legacy example 還是正式入口
- 加入 CI
- 加入 DAW 工程素材包匯入說明

## 既有未提交變更注意

本次文件整理開始時，`app.py` 已經顯示 local modifications。這些變更不應被自動視為本次文檔整理的一部分。

提交文件時應檢查 `git diff`，避免把無關的 `app.py` 變更混入。

## 建議正式記錄的 ADR

若專案採用 ADR 流程，以下決策值得記錄：

- 使用節點式工作流加 Behavior Tree 編排。
- 將 DAW-ready 工程素材輸出定為專案核心，而不是 AI 分軌。
- AI 模型整合在完整實作前視為 optional extension nodes。
- BeatNet 作為優先 beat tracker，Librosa 作為 deterministic fallback。

若採用 ADR，建立 `docs/adr/`，並以一個決策一份 ADR 的方式記錄。
