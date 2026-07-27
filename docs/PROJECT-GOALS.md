# 專案目標

**最後更新：** 2026-07-24 (v1.3.0 商業級 Suite 正式完工版)

## 專案定義

PGMCraft Studio 是一套以節點式音訊工作流為基礎，並透過 Behavior Tree 進行流程編排與 Quality Guard 品質估測防禦的音訊工程素材產生系統。

專案核心目標是將音訊或影片來源轉換成可直接用於 DAW、練團、採譜與 Live PGM 製作的商業級工程素材包。

## 第一階段承諾 (已 100% 正式交付完工)

給定本地音檔或支援的媒體 URL，PGMCraft Studio 可可靠提供：

- **剝洋蔥迭代減法分軌 (Trio Peel & Subtract)**
- **標的式 Sub-Mix 分析音軌合成 (Rhythm, Harmonic, Structure)**
- **DAW 自動 3 大 Bus 路由與音量平衡 (Rhythm -3dB / Music -6dB / Vocal 0dB)**
- **聲部導向 MIDI 拆分 (Piano/Guitar) & Legato 0 衝突微秒修復衛兵**
- **EBU R128 (-14 LUFS / -16 LUFS, Peak <= -1.0 dBFS) 聽感極致控制**
- **兩階層目標驅動應用場景矩陣 (6 大一級領域 + 21 項細分二級狀態機工作流)**
- **Podcast / Vlog / 卡拉OK / 樂手採譜 / Live PGM / ASMR 狀態機全管道連動**
- **Live 舞台對時指示儀表板 (JS 即時小節與和弦燈號高亮同步)**
- **MusicXML `.musicxml` 開放樂譜導出與 Global MIDI Chord Track 和弦軌標記**
- **Behavior Tree 自我修復衛兵 (BT Exception Self-Healing Guard)**
- **CLI 資料夾 Batch 批次 Processing 模式**


## DAW 匯出目標

DAW 匯出是核心功能，不是附屬輸出。

專案應從單一 MIDI 檔逐步發展成 DAW-ready 工程素材包：

- `tempo_map.mid`：提供速度與時間參考
- `click_guide.mid`：提供逐拍 MIDI click note
- `pgm_project_package/`：整理音訊、MIDI、報告與匯入說明
- `IMPORT_GUIDE.md`：提供 DAW 匯入順序與人工檢查提示
- 未來加入小節、段落與和弦導引軌
- 未來支援 Ableton Live、Logic Pro、Cubase、Reaper 等 DAW profile
- 產出清楚的專案資料夾與匯入說明

## 架構目標

專案設計應圍繞以下概念：

- 小型、單責任的音訊處理節點
- 透過 blackboard 共享工作流狀態
- 使用 Behavior Tree 編排流程
- 對不穩定或選用模型提供 fallback
- 對前置條件與安全檢查使用 guard node

這樣可以讓專案保持可擴充。未來 AI 模型應以節點形式加入，而不是改寫整條流程。

## 第一版公開時的非目標

第一個公開版本不應宣稱已完成目前仍屬 stub 或實驗狀態的功能。

除非真的完成整合與測試，否則以下功能不應被描述為正式完成：

- 真正具備品質驗證的 BS-Roformer、UVR 或 Demucs 分軌
- 主唱與和聲分離
- 鼓組細分
- 完整 Whisper 或 pyannote Podcast pipeline
- Basic Pitch 或 CREPE 的正式採譜與音高分析流程
- 自動樂段辨識
- DAW 專用工程檔產生

這些功能在完成前應放在 roadmap。

## 成功標準

專案方向正確時，應該滿足：

- 使用者能把產生的 MIDI 與 WAV 素材匯入 DAW
- Beat 與 Click 輸出足以支援練團或 PGM 準備
- 每個工作流能力都有清楚節點
- Behavior Tree 能解釋每一步為何執行、跳過或 fallback
- 文件清楚區分已完成功能與規劃功能
- 測試能保護核心音訊到工程素材包流程
