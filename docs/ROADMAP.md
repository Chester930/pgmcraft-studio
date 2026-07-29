# 開發路線圖

**最後更新：** 2026-07-24 (v1.4.1)

本路線圖定義 PGMCraft Studio 的階段。每個階段都應產生一個可理解、可測試、可繼續擴充的專案狀態。

模塊三「和弦簡譜與節拍器生成」的專用任務規劃見：[`docs/MODULE3-CHORD-CLICK-PLAN.md`](MODULE3-CHORD-CLICK-PLAN.md)。和弦簡譜目標需能承載大小和弦、七和弦、九和弦、增減和弦、altered dominant 與 slash chord，不應只輸出根音或簡單三和弦。

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
- GitHub remote 已設定
- 本地測試通過，但有警告

## Phase 1：PGM 與 DAW 匯出極致商業級 Suite (v1.3.0)

狀態：已完成 100% 正式交付。

目標：
建立一條極度可靠的音訊工作流，將音訊轉成商業級 DAW-ready 輔助素材包。

範圍 (已完成交付):
- **剝洋蔥迭代分軌 (Iterative Trio Peel-and-Subtract Stem Separation)**
- **標的式 Sub-Mix 分析音軌合成 (Rhythm, Harmonic, Structure Sub-mix)**
- **DAW 自動 3 大 Bus 路由 (Rhythm -3dB / Music -6dB / Vocal 0dB)**
- **聲部導向 MIDI 拆分 (Piano/Guitar) & Legato 音符微秒重疊修復衛兵**
- **EBU R128 (-14 LUFS, Peak <= -1.0 dBFS) 聽感極致控制**
- **Live 舞台對時指示儀表板 (JS 即時小節與和弦燈號高亮同步)**
- **MusicXML `.musicxml` 開放樂譜導出 (MuseScore/Sibelius 開譜)**
- **Global MIDI Chord Track 標記軌事件 (Cubase/Studio One 和弦軌對對位)**
- **Behavior Tree 自我修復衛兵 (BT Exception Self-Healing Guard)**
- **CLI 資料夾 Batch 批次 Processing 模式**
- 本地音檔與 URL 下載入口
- BeatNet / Librosa 雙引擎對拍與 downbeat 自動對齊
- Reaper `.rpp`、Ableton `.als`、Logic Pro `.fcpxml`、Cubase `.csv`、MusicXML `.musicxml`
- `pgm_project_package.zip` 全套素材包純淨壓縮打包

完成標準：
- 140+ 單元與整合測試 100% 綠燈通過
- 產出檔能無縫匯入 Reaper, Ableton, Logic, Cubase, Studio One, MuseScore
- README 與 ARCHITECTURE 文檔描述為 100% 穩定商業功能集

- 移除使用者介面中的本機絕對路徑預設值

## Phase 2：節點工作流強化

狀態：已完成 (v1.1.0)。

目標：

讓節點執行更明確、可測試、可重用。

已完成項目：

- Blackboard 型別化契約 (context.py)
- 非阻斷式與 Strict Contract Validation (validate_strict)
- Workflow Trace Log 與 Gradio 診斷面板 (`app.py`)
- CLI `--diagnostics` 與 `--export-schema` 規格自動匯出
- 每個核心與擴充節點獨立單元測試 (65+ passed tests)

## Phase 3：DAW 工程素材包

狀態：已完成 (v1.1.0)。

目標：

從單一輸出檔，升級成完整 DAW-ready project package。

已完成項目：

- `pgm_project_package/`
- `audio/` (source, click_track, mix_with_click)
- `midi/` (tempo_map.mid, click_guide.mid, chord_guide.mid, melody_lead.mid, vocal_pitch.mid)
- `reports/` (analysis report JSON/TXT, pitch_contour.json, tempo_curve.png)
- `pgm_session.rpp` (Reaper 專案檔)
- `markers.csv` (通用 DAW Marker 檔)
- `IMPORT_GUIDE.md` (DAW 匯入指引)

範例結構：

```text
project-name/
├── audio/
│   ├── source.wav
│   ├── click_track.wav
│   └── mix_with_click.wav
├── midi/
│   ├── tempo_map.mid
│   ├── click_guide.mid
│   ├── chord_guide.mid
│   ├── melody_lead.mid
│   └── vocal_pitch.mid
├── reports/
│   ├── analysis_report.json
│   ├── analysis_report.txt
│   └── pitch_contour.json
├── pgm_session.rpp
├── markers.csv
└── IMPORT_GUIDE.md
```

## Phase 4：公開發布整理

狀態：已完成 public v1.1.0。


目標：

整理成適合 GitHub public release 的狀態。

範圍：

- 依照實際 MVP 重寫 README
- 清楚標示 GUI 分軌工作區為 experimental
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

目前已完成：

- README 已對齊 Phase 1 實作現況
- GitHub Actions CI workflow 已新增
- legacy GUI 的本機絕對輸出路徑已移除
- GUI experimental 功能已標示
- GitHub remote 已設定，repository 目前為 public
- GitHub repository 已改名為 `Chester930/pgmcraft-studio`
- GitHub Actions CI 已在遠端執行通過
- core / optional dependencies 已初步拆分
- legacy 入口已文件化，第一版暫時保留根目錄相容入口
- 模型與第三方工具授權邊界已新增文件
- release tag 已建立：`v1.0.0`
- workflow trace log 已新增 v1，並寫入 `pgm_report.json`
- Blackboard key 契約已新增 v1 文件與節點 metadata
- 非阻斷式 contract validation 已新增 v1

目前剩餘：

- 第一版公開發布後觀察使用者回饋與 CI 狀態

下一個主線：

- Phase 2 節點工作流強化

## Phase 5：AI 輔助音樂模組

狀態：已完成 (v1.2.0)。

目標：

將真正的 AI 模型整合成選用節點。

已完成項目：

- `SectionStructureNode`：自動段落分析 (Intro/Verse/Chorus/Bridge/Outro)
- `CREPEPitchNode`：連續音高輪廓追蹤 (Librosa pyin fallback)
- `PodcastSpeechNode`：语音對齊，產出 `.srt` 字幕與 `transcript.json`
- `InstrumentPresenceNode`：逐小節配器動態檢測矩陣
- `HybridPitchNode`：雙音高融合算法，產出量化主唱 `vocal_lead_quantized.mid`
- Ableton Live `.als`、Logic Pro `.fcpxml`、Cubase Tempo Track `.csv` 導出器
- `DAWProfileRegistry`：抽象工廠動態切換目標 DAW 導出格式
- `RetryFallbackNode`：Behavior Tree 裝飾器節點，支援重試與降級保護
- Live 舞台指示儀表板 `live_dashboard.html` (黑夜模式，支援小節和弦導引)
- Gradio 第 5 頁籤：交互式 MIDI 鋼琴卷軸預覽 (SVG/HTML Piano Roll)
- Gradio 第 6 頁籤：全套 DAW 工程素材包一鍵 ZIP 下載
- CLI `--batch-dir` 多執行緒批次處理與 `batch_summary.csv` / `.json`
- CLI `--daw-profile` 選定 DAW 導出 Profile
- `build_zip_archive()`：全套素材包自動壓縮為 `.zip`

完成標準：

- 模型依賴均為 optional 並帶有 Graceful Fallback Guards
- **83 項單元測試與整合測試全數通過** (80+ passed, 1 skipped)
- 模型授權與契約文件已記錄

## Phase 10：Gradio GUI 多檔案批次處理面板

狀態：已完成 (v1.4.1 Release)。

- [x] Gradio `render_batch_summary_html()` 批次處理佇列與任務摘要對比面板 (`app.py`)
- [x] 單元測試 `tests/test_app_batch_processing.py` 100% 通過
- [x] 全套 123 項測試集合完全相容與通過
