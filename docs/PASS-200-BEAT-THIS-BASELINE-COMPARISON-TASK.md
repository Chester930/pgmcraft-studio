# Pass 200 任務書：用 `beat_this` 預訓練模型建立獨立基準比較

**狀態**：設計完成，可直接轉交 Codex CLI 執行。**這是純研究/評估
任務，不修改 production 管線程式碼**——只新增一個獨立的比較腳本跟
報告，目的是取得一個跟現有 madmom/BeatNet pipeline 完全無關的獨立
基準，用來判斷 Pass 194-199 系列反覆碰到的問題，是不是現有拍點偵測
引擎（Stage 3）本身的限制。

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
