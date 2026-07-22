# PGMCraft Studio 專案文檔

**最後更新：** 2026-07-23

本資料夾用來記錄 PGMCraft Studio 的正式專案方向、架構、階段路線與開發脈絡。

## 閱讀順序

1. [專案目標](PROJECT-GOALS.md)：專案要解決什麼問題、服務誰、第一版要做到什麼。
2. [Phase 1 已確定範圍](PHASE1-CONFIRMED-SCOPE.md)：目前已確認的核心功能、輸出契約與本輪優化結果。
3. [開發路線圖](ROADMAP.md)：從 MVP 到公開發布，再到未來 AI 模組的階段規劃。
4. [系統架構](ARCHITECTURE.md)：節點式工作流與 Behavior Tree 編排模型。
5. [Behavior Tree 設計圖](BEHAVIOR-TREE.md)：目前已實作 BT 與 Phase 1 目標 BT。
6. [開發脈絡](DEVELOPMENT-CONTEXT.md)：目前程式狀態、實作現實、已形成的設計方向。
7. [相關說明文獻與參考專案](REFERENCES.md)：DAW MIDI、beat tracking 與驗證工具參考。
8. [公開發布檢查清單](RELEASE-CHECKLIST.md)：GitHub public 發布狀態與檢查結果。
9. [Legacy 入口決策](LEGACY-ENTRYPOINTS.md)：第一版公開時對早期 standalone 入口的定位。
10. [模型與第三方工具注意事項](MODEL-AND-THIRD-PARTY-NOTES.md)：模型權重、optional 依賴與外部工具授權邊界。

## 文件語言

開發階段預設使用繁體中文撰寫討論、規劃與專案文件。除非明確需要英文版，否則不主動切換成英文。

## 文檔用途

PGMCraft Studio 會被視為正式專案經營。這些文件是以下事項的基準：

- 產品方向
- 開發階段
- 架構邊界
- 目前實作狀態
- 公開發布前的整理項目

根目錄 `README.md` 可以面向使用者；`docs/` 內文件則用來維持工程脈絡與開發連續性。
