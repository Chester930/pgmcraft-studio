# Phase 1 已確定範圍與本輪檢查

**最後更新：** 2026-07-22

本文件只記錄目前已確定、可作為正式開發基準的內容。後續 AI 分軌、Podcast、自動旋律轉 MIDI 等功能不列入本階段完成條件。

## 已確定的專案核心

PGMCraft Studio 第一階段要先成為一套「音訊轉 DAW / PGM 工程素材」工具。

核心流程：

```text
音訊或影片來源
-> 音訊載入與必要下載
-> beat / downbeat 偵測
-> BPM 與 tempo curve
-> click WAV
-> mix preview WAV
-> DAW tempo map MIDI
-> MIDI click guide
-> JSON / TXT 報告
```

## 已確定的 Phase 1 輸出

| 輸出 | 檔名 | 目的 | 本輪狀態 |
|------|------|------|----------|
| Click WAV | `click_track.wav` | 練團、耳監、Live click | 已實作 |
| Mix Preview | `mix_with_click.wav` | 檢查 click 是否貼合原曲 | 已實作 |
| Tempo Curve | `tempo_curve.png` | 檢視 BPM 浮動 | 已實作 |
| Tempo Map MIDI | `tempo_map.mid` | 匯入 DAW 建立速度圖 | 已優化 |
| MIDI Click Guide | `click_guide.mid` | 匯入 DAW 取得逐拍 click note | 已新增 |
| JSON Report | `pgm_report.json` | 機器可讀分析結果 | 已實作並補輸出欄位 |
| TXT Report | `*_pgm_report.txt` | 使用者閱讀摘要 | 已實作 |

## 本輪檢查結論

目前架構方向是可用的，不需要整個重構。

理由：

- `pgm_craft/workflow/` 已有 Behavior Tree builder 與節點結構。
- 節點透過 `Blackboard` 傳遞狀態，符合後續節點化設計。
- BeatNet 與 Librosa fallback 已經是合理的 selector/fallback 形式。
- 主要問題不在架構，而在部分輸出語意不夠精準。

本輪優先處理的問題：

- 原本 `tempo_map.mid` 實際上主要是 MIDI click notes，沒有真正的 `set_tempo` meta event。
- DAW tempo map 與 MIDI click guide 應拆成兩個不同輸出，避免用途混淆。
- 測試不應只檢查 MIDI 檔案存在，應檢查是否含有 tempo meta event 與 click note。

## 本輪已完成優化

- `PGMSynthesizer.export_midi_tempo_map()` 改為輸出 Standard MIDI File，包含 `set_tempo` 與 `time_signature` meta event。
- 新增 `PGMSynthesizer.export_midi_click_guide()`，輸出逐拍 MIDI click notes。
- `MIDIExportNode` 同時寫入 `tempo_map_midi` 與 `click_guide_midi`。
- `PGMCraftEngine` 的 JSON report 補上 `click_guide_midi`。
- Gradio PGM 介面新增 `click_guide.mid` 下載欄位。
- 測試加入 MIDI tempo event 與 click note 驗證。
- `mido` 補為正式依賴，避免隱性依賴。

## 目前已知限制

- 目前假設拍號為 4/4。
- tempo map 由相鄰 beat 間距推算，尚未加入異常 beat validation。
- downbeat refine 與 measure map 仍是下一階段需要明確化的節點。
- 舊版 `beat_tracker.py` / `web_app.py` 尚未整理，公開前應決定移入 `legacy/` 或與正式 BT 管線合併。
- DAW 匯入行為可能因軟體不同而有差異，下一階段應建立 `IMPORT_GUIDE.md` 範本。

## 第一階段下一個技術焦點

下一個應討論與設計的區塊是：

```text
BeatValidationNode
-> DownbeatRefineNode
-> MeasureMapNode
```

這三個節點會決定 tempo map、click guide、報告、和弦小節對齊是否可靠。
