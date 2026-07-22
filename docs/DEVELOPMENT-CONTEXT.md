# 開發脈絡

**最後更新：** 2026-07-23

本文件記錄第一次正式文件整理時的專案脈絡。

## 目前版控狀態

- 本地 Git repository 已建立。
- 目前 branch 是 `main`。
- 已有初始 local commit：`029d072 chore: initial project snapshot`。
- 已有專案目標與架構文件 commit：`2460e17 docs: define project goals and architecture`。
- 根目錄 README 已改為 Phase 1 實作現況導向。
- GitHub remote 已設定為 `https://github.com/Chester930/-----.git`。
- GitHub repository 已建立，目前為 private。
- GitHub CLI 已登入 `Chester930`。
- GitHub Actions CI 已由 push 觸發，遠端執行結果為通過。

## 目前測試狀態

最近觀察到的測試命令：

```bash
python -m pytest -q
```

最近觀察到的結果：

```text
42 passed, 1 skipped
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
- MeasureMapNode v1
- DownbeatRefineNode v1
- 調性與和弦參考分析
- Click Track WAV 合成
- 原曲加 Click 的 WAV 輸出
- `tempo_map.mid` MIDI tempo map 輸出
- `click_guide.mid` MIDI click guide 輸出
- `pgm_project_package/` 工程素材包
- `IMPORT_GUIDE.md` 匯入說明
- 速度曲線圖
- JSON report
- Gradio GUI 外殼，PGM 頁籤為穩定主線，分軌工作區標示為 experimental
- CLI 外殼
- GitHub Actions CI workflow

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
- 小節推定不能硬套整首 4/4；同一首歌內可能有不同拍數的小節，後續 `MeasureMapNode` 必須支援可變小節長度。
- AI 分軌與 Podcast 工作流在完成真實整合前，應維持為 extension module。
- 開發階段預設使用繁體中文撰寫討論與文件，除非另有英文版需求。

## 公開發布前需要整理

公開前應處理：

- README 已依照實際 MVP 重寫
- README 中的範例 clone placeholder 已移除
- legacy `web_app.py` 的本機絕對輸出路徑已移除
- Gradio `allowed_paths` 已限制在預設 `outputs/`
- 清楚標示已實作功能與 roadmap 功能
- core dependencies 與 optional AI/downloader dependencies 已初步拆分
- 已決定 `main.py`、`web_app.py`、`beat_tracker.py` 暫時保留為 legacy example
- CI workflow 已新增，且 GitHub Actions 遠端執行已通過
- `CONTRIBUTING.md` 已加入
- 加入 DAW 工程素材包匯入說明
- 加入模型與第三方工具注意事項
- 第一版 release tag 已建立：`v1.0.0`

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
