# Pass 177 任務書：Lane 1（純鼓軌偵測）+ 多軌審查工具

**狀態**：進行中
**目標**：把 Pass 176 的 V3 設計（缺口逐輪疊加證據）落地成使用者可以實際操作的
多軌審查流程，第一步先做 Lane 1（純鼓軌，全曲）的偵測 + 音檔渲染，並把
Pass 176 做的單軌審查工具（`scratch/gap_review_server.py`）擴充成多軌版本。

---

## 0. 背景：確認過的設計原則

延續 Pass 176 的討論，使用者確認了完整的多軌審查流程：

```
Lane 1（純鼓軌偵測，全曲）
  → 對全曲每個區塊做偵測 + 既有評分標準初篩
  → 人工逐區塊聽、標記通過/不通過

Lane 2（鼓 + Bass 疊加偵測）
  → 只針對 Lane 1 評分標準判定「需要複核」的區塊，重新用鼓+貝斯分析
  → 人工再對這些區塊聽、標記通過/不通過

Lane 3（+ 和弦）→ 只處理 Lane 2 還不通過的區塊
Lane 4（+ 旋律）→ 只處理 Lane 3 還不通過的區塊
```

**否決往後傳遞規則**：某個區塊在較前面的 Lane 被系統評分標準判定「通過」，但人工
在後面某個 Lane 重新聽覺得不通過——這個「不通過」要往後所有 Lane 都同步套用在
同一個時間區段上，不能因為前面一次自動通過就被排除在後續複核之外。

另外兩個 Pass 176 討論中確認的原則，繼續適用：
- 「不通過」＝這個區塊裡面存在錯誤，不是整個區塊都不能用。
- 區塊是對訊號連續取樣、依信心門檻自動合併出來的，不是照最終小節邊界切
  （分析當下小節本來就還沒確認）。

## 1. Lane 1：純鼓軌偵測設計

### 1.1 為什麼不能直接拿現有的 V1 網格當 Lane 1

現有 pipeline 的 beat grid（不管是黃金版還是目前的 B 版）都是 BeatNet 雙軌融合 +
一長串精修守衛鏈算出來的，早就摻雜了非鼓的資訊（全曲混音、樂器分析）。
「純鼓軌」必須是一個獨立、只吃 `stems/drums/kick.wav` + `stems/drums/snare.wav`
的全新分析，才能真正代表「如果只聽鼓，會得到什麼」，作為後面逐輪疊加證據的
乾淨基準線。

### 1.2 演算法

`scratch/lane1_pure_drum_detection.py`：

1. 讀取 `stems/drums/kick.wav` + `stems/drums/snare.wav`，合併能量包絡
   （onset strength），只用這兩軌，不碰其他任何音色。
2. 用 `librosa.beat.beat_track`（古典的 onset envelope + 動態規劃拍點追蹤，
   跟現有 pipeline 用的 BeatNet CRNN+DBN 是完全不同的方法）在這個純鼓包絡上
   算出全曲拍點時間陣列。
3. 拍號循環標記 1-2-3-4（Lane 1 階段還沒有能力判斷真正的 downbeat 相位，
   這正是後面疊加貝斯/和弦要解決的問題，Lane 1 不用假裝做得到）。
4. 信心度：對每一拍，檢查 ±60ms 內是否有真實 kick 或 snare 音頭
   （不是外推猜的），算出一個滾動窗口（例如每 4 秒）內「有真實音頭佐證的拍點
   比例」，比例低的窗口標記 `needs_review`。這是比純粹看 RMS 能量更直接的
   信心度指標——直接反映「這段是真的偵測到，還是純粹用等速外推填的」。
5. 渲染音檔：重用既有的 `PGMSynthesizer.synthesize_click(audio_path, beats,
   output_dir)`（`ClickSynthesisNode` 內部用的同一個函式），輸出
   `<project_dir>/lanes/lane1_drum_only/click/mix_with_click.wav`。
6. 區塊清單：套用跟 Pass 176 審查工具一樣的「連續取樣 + 信心門檻 + 相鄰合併」
   邏輯，輸出到 `<project_dir>/lanes/lane1_drum_only/blocks.json`。

## 2. 多軌審查工具擴充

`scratch/gap_review_server.py` 從單軌改成多軌：

- 每個 Lane 是一個獨立資料夾：`<project_dir>/lanes/<lane_id>/`，裡面有
  `click/mix_with_click.wav`（該 Lane 的音檔）、`blocks.json`（該 Lane 偵測出的
  區塊）、`marks.json`（該 Lane 的人工標記）。
- 前端加一個 Lane 選單（tabs 或下拉選單），切換 Lane 會換播放器音源、換時間軸
  區塊，但共用同一條時間軸比例尺（方便來回比對同一個時間點在不同 Lane 的狀態）。
- **否決傳遞**：使用者在 Lane N 把某個區塊標記為 `fail` 時，伺服器端要找出
  Lane N+1 ~ 最後一個 Lane 裡，跟這個區塊時間範圍有重疊的所有區塊，強制把它們
  的標記也設成 `fail`（即使該區塊在那些 Lane 原本是 `auto_pass`）。反向（在
  後面 Lane 標 pass）不會覆蓋前面 Lane 的標記——只往後傳遞不通過，不往前也不
  往後傳遞通過。

## 3. 驗證方式

1. 對 `outputs/pass175_current_pipeline_check` 這個既有專案跑
   `lane1_pure_drum_detection.py`，確認能產出音檔跟區塊清單，且區塊數量/位置
   合理（人工聽幾個片段確認純鼓拍點大致對得上真實 kick）。
2. 啟動多軌審查工具，確認：
   - Lane 選單能正確切換音源與時間軸區塊。
   - 在 Lane 1 標記某區塊 fail，之後產生 Lane 2（哪怕還沒有真的資料，用假資料
     測試）時，該時間範圍會自動繼承 fail 狀態。
3. 這一版只做到 Lane 1；Lane 2（鼓+貝斯）、Lane 3（+和弦）、Lane 4（+旋律）
   留給後續 Pass，等 Lane 1 的偵測品質跟工具流程都確認可用之後再擴充。
