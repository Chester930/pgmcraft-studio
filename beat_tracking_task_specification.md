# 📋 專案任務書：MP3 音樂自動動態節拍追蹤與打點生成工具

## 1. 專案目標 (Project Objective)
建立一套自動化處理流程，輸入任意 MP3 音檔（包含 **固定 BPM** 或 **動態變速 / 手感游移 / 漸快漸慢 / Rubato 自由拍** 音樂），經由 AI 深度學習模型進行節拍追蹤（Beat Tracking）與強弱拍辨識（Downbeat Tracking），並自動匯出可於音樂製作（DAW）或影片剪輯使用的打點音檔與 Tempo Map（MIDI）。

---

## 2. 核心功能與輸出規格 (Outputs & Specs)

- **輸入**：單一 `.mp3` 或 `.wav` 音檔。
- **輸出檔案規格**：
  1. `click_track.wav`：純節拍器打點音檔（區分 **強拍「叮」** 與 **弱拍「嗒」**）。
  2. `mix_with_click.wav`：原曲 + 打點音軌的混合音檔（用於快速試聽與人工驗證對齊度）。
  3. `tempo_map.mid`：MIDI 節拍時間戳檔（可直接拉入 Logic Pro, Ableton, Cubase, Premiere 自動對齊速度軌）。

---

## 3. 技術選型與推薦模型 (Technical Stack)

| 模組類別 | 推薦工具 / 模型 | 選擇原因與功能描述 |
| :--- | :--- | :--- |
| **音軌分離 (選配)** | **Meta Demucs** (`htdemucs`) | 針對樂器混雜或無鼓組的音樂，先抽出鼓組（Drums）或節奏軌，可大幅提升節拍追蹤準確度。 |
| **節拍辨識 (主引擎)** | **BeatNet** | **首選**。基於 CRNN + Particle Filter，專門處理動態變速，機能同時辨識 Beat 與 Downbeat（小節第一拍）。 |
| **備用辨識引擎** | **Madmom** | 學術級經典 RNN 模型，對真鼓彈唱、爵士樂等非標準數位節拍表現極佳。 |
| **音訊與 MIDI 處理** | **Librosa** / **Pretty_MIDI** | 用於音訊讀取、合成 Click 聲效與產生 MIDI 時間戳事件。 |

---

## 4. 標準處理流程 (Workflow Pipeline)

```
[ Step 1: 音訊預處理與鼓組分離 ]
  ├── 檢查輸入音檔
  └── （可選）使用 Demucs 提取 drums.wav 強化節拍特徵
        │
        ▼
[ Step 2: BeatNet 動態節拍追蹤 ]
  ├── 餵入目標音軌
  └── 輸出每拍時間點（秒）與拍數標籤（1為重音，2~4為弱音）
        │
        ▼
[ Step 3: 打點音訊與 MIDI 檔合成 ]
  ├── 依時間戳合成高低音 Click (click_track.wav)
  └── 寫入 MIDI 事件 (tempo_map.mid)
        │
        ▼
[ Step 4: 混合驗證檔匯出 ]
  └── 原曲 + 打點音軌按比例混合 (mix_with_click.wav) 供聽聽確認
```

---

## 5. 給 AI 開發者的提示詞範本 (Prompt for Coding)

> **💡 開發提示詞 (Copypaste to AI Assistant)：**
>
> 「請使用 Python 幫我寫一個自動化腳本。需求如下：
> 1. 使用 `BeatNet` 模型讀取指定的 MP3 音檔，進行動態節拍與 Downbeat（小節第一拍）追蹤。
> 2. 依據辨識出的時間戳，合成一個高低音區分的打點音檔 `click_track.wav`（第一拍高音，其餘拍低音）。
> 3. 使用 `pretty_midi` 將這些節拍時間點寫入並匯出為 `tempo_map.mid` 檔案。
> 4. 最後將原曲與打點合成匯出 `mix_with_click.wav` 供試聽。請確保程式能正確處理變速音樂，不要假設固定的 BPM 值。」

---

## 6. 開發與執行注意事項 (Important Notes)

1. **動態速度處理**：變速音樂**切勿**將 BPM 設定為單一常數，必須完全依據模型輸出的「時間戳陣列（Timestamp Array）」進行逐點音效合成與 MIDI 事件寫入！
2. **環境依賴**：
   - Python 3.8+
   - `beatnet` (`pip install BeatNet`)
   - `librosa`, `soundfile`, `pretty_midi`, `numpy`
   - （選配）`demucs`
