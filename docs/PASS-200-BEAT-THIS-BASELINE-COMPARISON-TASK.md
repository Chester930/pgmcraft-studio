# Pass 200 任務書：用 `beat_this` 預訓練模型建立獨立基準比較

**狀態**：已執行完成，結果比預期複雜——不是單純「更好」或「更差」，
發現一個具體、可重現的新問題（tempo octave 切換）。完整結論見第 4 節。

---

**（原始狀態，供對照）**：設計完成，可直接轉交 Codex CLI 執行。**這是
純研究/評估任務，不修改 production 管線程式碼**——只新增一個獨立的
比較腳本跟報告，目的是取得一個跟現有 madmom/BeatNet pipeline 完全
無關的獨立基準，用來判斷 Pass 194-199 系列反覆碰到的問題，是不是
現有拍點偵測引擎（Stage 3）本身的限制。

---

## 0. 背景

`docs/STAGE3-BEAT-TRACKING-LITERATURE-REFERENCES.md` 整理過的文獻
確認：「downbeat 在訊號層級不一定比較大聲、也不一定有明顯打擊樂
特徵」是學界共識，代表用 onset 能量/信心公式手刻規則的做法有先天
天花板。`CPJKU/beat_this`（ISMIR 2024，https://github.com/CPJKU/beat_this）
是目前公開、有預訓練模型、免 DBN 後處理的 transformer 拍點/downbeat
追蹤器，用「shift-tolerant 二元交叉熵」損失函數專門處理標註時間
誤差，跟我們這幾季反覆處理的「相位容差」問題方向一致。

這個任務是這整個研究方向裡**成本最低、資訊量最高**的第一步：不改
任何 production 程式碼，只是拿它的預訓練模型對我們的測試曲目跑一次，
看它在已知問題點的表現，藉此判斷值不值得投入更深（例如換掉 Stage 3
引擎、或把它的輸出當成一個新的證據來源接進 BarStart V2）。

---

## 1. 具體工作

### 1.1 環境準備

1. 確認 `beat_this` 套件安裝方式（`pip install` 或 clone repo，看
   `https://github.com/CPJKU/beat_this` 的 README，用
   `C:/Python313/python.exe` 對應的環境安裝，或視相容性建立獨立的
   virtualenv——**不要動到現有 pipeline 依賴的 madmom/BeatNet 環境**，
   這個任務只是旁支評估，不能影響現有管線能不能跑）。
2. 用 `beat_this.inference.load_model('final0', device='cpu')`（沒有
   GPU 就用 CPU，這首歌只有 176 秒，跑一次應該不會太久）載入預訓練
   模型。

### 1.2 建立比較腳本

新增 `scratch/run_pass200_beat_this_baseline.py`：

1. 對測試曲目
   `outputs/pass175_current_pipeline_check/【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】/source/【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】.wav`
   跑 `beat_this` 推論，取得它自己的 beat/downbeat 時間戳列表。
2. 讀取我們現有 pipeline 最新一次真實回驗的 `measure_map.json`
   （`outputs/pass198_default_pipeline_reverify/.../reports/measure_map.json`，
   Pass 198 階段 A 的結果：114 小節、10 不規則）當對照基準。
3. **逐一核對以下已知問題點**，`beat_this` 在這些位置給出的
   downbeat 標記是否跟現有 pipeline 一致、或有清楚的改善/退步：
   - 8.041s（證據薄弱，人聲清唱段落）
   - 22.883s、35.300s（真實偵測到額外拍點，relabel 無法消除）
   - 77.803s、80.020s（同上，Pass 197 仲裁的目標案例）
   - 93.802s、97.197s（97.197s 是過門段落，證據薄弱）
   - 108.652s
   - 153.467s
   - 18-20 秒目標區段（`SteadyPercussionCountAnchorNode` 已確認乾淨
     的對照組，`beat_this` 在這裡「至少不能比現有結果差」是最低
     要求）
4. 對每個問題點，印出：`beat_this` 在該時間點附近 ±3 秒內的
   beat/downbeat 標記，跟現有 pipeline 的對應標記並排比較，並計算
   時間差（毫秒）。

### 1.3 全曲整體比較

1. 用 `pgm_craft.golden_benchmark.compute_measure_map_stats`（沿用
   這系列一直在用的黃金基準比較方式）算出 `beat_this` 輸出對應的
   `total_measures`/`irregular_measure_count`（需要先把 `beat_this`
   的 beat/downbeat 輸出轉成跟 `measure_map` 相容的格式——只要有
   時間戳 + 是否為 downbeat 的標記就能轉換，不需要完整走一遍
   `MeasureMapNode` 的後處理，直接用連續 downbeat 間距切小節即可）。
2. 跟黃金基準（121 小節、0 不規則）、Pass 198 階段 A 的結果
   （114 小節、10 不規則）三方比較。

---

## 2. 安全機制

1. **這個任務不能修改任何 production 程式碼**（`pgm_craft/workflow/`
   底下的檔案），只能新增 `scratch/` 底下的獨立腳本——這是純評估，
   不是要現在就整合 `beat_this` 進管線。
2. **不能只看聚合數字（`total_measures`/`irregular_measure_count`）
   就下結論**——這系列已經連續四次證明聚合數字會騙人（Pass 197
   threshold bug、Pass 198B 級聯、Pass 199 的 85% 抄襲網格都是這樣）。
   一定要逐一核對第 1.2 節列出的已知問題點，看 `beat_this` 是不是
   「真的」在這些困難位置表現更好，不是只看總數字剛好比較接近黃金
   基準。
3. 如果 `beat_this` 安裝或推論過程遇到環境相容性問題（例如需要的
   PyTorch 版本跟現有環境衝突），**不要為了跑起來去動現有環境的
   套件版本**——記錄下這個障礙，回報給使用者，不要自己決定要不要
   降級/升級現有依賴。

---

## 3. 驗證與交付物

1. `scratch/run_pass200_beat_this_baseline.py`（可重現的比較腳本）。
2. `scratch/pass200_beat_this_comparison_report.json`（結構化比較
   結果：每個問題點的 `beat_this` vs 現有 pipeline 標記、時間差、
   全曲整體統計三方比較）。
3. 一份簡短的文字結論（可以寫在 `docs/BT-BUILD-PROGRESS.md` 新增
   一則 Pass 200 條目），誠實回答：`beat_this` 在這首歌的已知問題點
   上，是明顯更好、差不多、還是更差？如果明顯更好，具體是在哪些
   問題點、改善幅度多少（用毫秒/拍數量化，不要用「感覺比較好」這種
   主觀說法）。
4. **不需要請使用者實際試聽**（這個階段還沒有產出新的 click 音檔，
   只是數據比較）——但如果結論是「明顯更好，值得往下做」，下一步
   會需要产出對照的 click 音檔供使用者確認，那是後續 Pass 的工作，
   不是這個任務書的範圍。

---

## 4. 執行結果（Claude 直接執行，不是 Codex）

Codex 原本因為「找不到指定的 WAV」卡住——查證後確認
`outputs/pass175_current_pipeline_check`（任務書原本寫的路徑）這個
目錄整個消失了（本機 `outputs/` 快取被清過，內容從未進 git），但
**同一份音檔在其他 `pass19x_default_pipeline_reverify` 資料夾裡都還
完整存在**（每次重跑管線都會複製一份到專案資料夾），改成指向
`outputs/pass198_default_pipeline_reverify/.../source/*.wav` 就直接
解決了，不是真的遺失資料。順手也修了 Codex 腳本裡一個小 bug
（`_normalise_events` 用 `raw or []` 在 numpy 陣列輸入時會拋
`ValueError: truth value of an array is ambiguous`，改成
`if raw is None: raw = []`）。裝 `beat_this`（PyPI 直接 `pip install`
成功，只新增 `beat_this`/`rotary-embedding-torch` 兩個套件，沒有動到
既有的 torch/madmom/BeatNet 依賴）。

### 4.1 聚合統計：不能直接看，會誤導

```
golden:            121 小節, 0 不規則
existing_pipeline:  118 小節, 10 不規則, BPM跳動 2
beat_this (raw):    103 小節, 26 不規則, BPM跳動 8
```

單看這個表格會得出「`beat_this` 更差」的結論——**但這是不公平的
比較**：`existing_pipeline` 是經過 Pass 193-199 一整季後處理修正過的
結果，`beat_this` 這裡是完全原始、沒有任何後處理的輸出。這正是任務書
第 2 節特別提醒過的「不能只看聚合數字」，逐點核對後發現真正的故事
複雜得多。

### 4.2 逐點核對：`beat_this` 在部分已知難點表現「不一樣」，不是單純更好或更差

- **8.041s（人聲清唱、鼓聲近乎靜默）**：`beat_this` 給出乾淨的 4 拍
  間距（6.62s → 9.52s，間隔 2.9 秒 ≈ 4 拍 @ 0.73 秒/拍）——這正是
  我們自己的 pipeline 在這裡卡住、只能靠複製舊網格或誠實回報不規則
  的位置。`beat_this` 沒有做任何鼓組/貝斯融合，純粹從頻譜學到的
  節奏感，在這個弱證據段落反而給出乾淨答案。
- **22.883s（真實多偵測到一拍的問題點）**：同樣乾淨的 4 拍間距
  （20.0s → 22.9s → 25.8s，都是 2.9 秒間隔）。
- **35.300s（同類問題點）**：這裡 `beat_this` 的拍距只有 1.44-1.46
  秒（正常拍距的一半），downbeat 抓得比預期密——這個點沒有比我們
  自己的結果更乾淨。

### 4.3 重大發現：`beat_this` 原始輸出有明顯的 tempo octave（八度）切換問題

用滑動視窗算 `beat_this` 全曲的拍距中位數，發現一個清楚、可重現的
規律（用 `dbn=True`/`dbn=False` 兩種設定重跑過，結果幾乎一樣，**不是
參數選錯，是這個模型對這首歌真實的行為**）：

```
0-27s:    拍距 ~0.72-0.73s（~83 BPM）  ← 這是全曲真實拍速 164.8 BPM 的一半
28-87s:   拍距 ~0.36s   （~166.7 BPM） ← 對上真實拍速
89-117s:  拍距 ~0.72s   （~83 BPM）    ← 又切回一半
118-148s: 拍距 ~0.36s   （~166.7 BPM） ← 又切回真實拍速
148s 之後: 混亂，多次切換
```

`beat_this` 在全曲反覆在「正確拍速」跟「正確拍速的一半」之間切換
（這是節奏學文獻裡常見的「tempo octave error」——模型有時候把
一個真實拍子的兩倍長度誤判成一個拍子）。這個現象**至少解釋了聚合
統計裡的 BPM 跳動次數（8 次）跟偏低的平均 BPM（136.5，剛好落在
83 跟 166.7 的中間）**——不是隨機雜訊，是規律性的整段誤判。

### 4.4 誠實結論

**`beat_this` 不能直接拿來取代現有 Stage 3，也不是「明顯更好」**——
它在幾個我們的弱證據段落給出了乾淨答案（8.041s、22.883s 這兩個算是
正面訊號，值得注意），但引入了一個我們現有 pipeline 沒有的新問題
（全曲規律性的 tempo octave 切換，範圍遠比我們原本的 9 個問題點更
廣）。**不是「換一個模型就解決」，換一個模型會解決一部分舊問題、
引入新問題，兩者都需要額外的後處理才能用**。

對應第 0 節的三個決策分支：**這是分支 B（差不多或更差），暫不整合
`beat_this`**，但 8.041s/22.883s 的正面訊號值得記錄——如果之後真的
要往這個方向走，`beat_this` 更適合當「補充證據來源」（例如專門用來
處理鼓聲稀疏的段落），而不是整個取代現有引擎；引入前一定要先解決
tempo octave 切換問題（可能需要另外接一層跟現有拍速估計做一致性
檢查的機制，不能直接信任它的原始輸出）。

**產出物**：
- `scratch/run_pass200_beat_this_baseline.py`（已修正音檔路徑跟
  numpy bug，可重現）
- `scratch/pass200_beat_this_comparison_report.json`（完整逐點比較）
