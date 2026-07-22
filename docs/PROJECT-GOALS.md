# 專案目標

**最後更新：** 2026-07-22

## 專案定義

PGMCraft Studio 是一套以節點式音訊工作流為基礎，並透過 Behavior Tree 進行流程編排的音訊工程素材產生系統。

專案核心目標是將音訊或影片來源轉換成可直接用於 DAW、練團、採譜與 Live PGM 製作的工程素材包。輸出內容包含節拍時間、速度資訊、Click 音軌、MIDI 導引檔、分析報告，以及未來可擴充的 AI 採譜、分軌或語音處理結果。

## 主要使用者

- 需要準備練團素材的樂手
- 需要建立 DAW session 的編曲者與製作人
- 需要準備 Live PGM 與 Click 的演出工作者
- 需要節拍、速度、調性、和弦參考的採譜使用者
- 未來需要 AI 分軌或 Podcast 音訊前處理的使用者

## 核心產品承諾

給定本地音檔或支援的媒體 URL，PGMCraft Studio 應該能產生一個可進入音樂工作流的專案資料夾。

第一個穩定版本應該可靠提供：

- 來源音訊準備
- Beat 與 downbeat 偵測
- BPM 統計與速度曲線
- Click Track WAV
- 原曲加 Click 的預聽 WAV
- 可匯入 DAW 的 MIDI 導引輸出
- 基礎調性與和弦參考
- JSON 與文字報告
- CLI 與 GUI 入口

## DAW 匯出目標

DAW 匯出是核心功能，不是附屬輸出。

專案應從單一 MIDI 檔逐步發展成 DAW-ready 工程素材包：

- `tempo_map.mid`：提供速度與時間參考
- `click_guide.mid`：提供逐拍 MIDI click note
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
