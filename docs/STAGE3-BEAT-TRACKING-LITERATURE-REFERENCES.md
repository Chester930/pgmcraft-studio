# Stage 3 拍點偵測問題的相關文獻與專案參考

**用途**：Pass 194-199 系列（`MeasureMapNode` Stage 4 後處理、BarStart V2）
反覆確認：有些問題不是後處理邏輯能安全解決的，根本原因在 Stage 3
（拍點/downbeat 偵測本身）。這份文件整理外部文獻與開源專案，對應
到我們已經量化確認的三個具體難題，供之後評估要不要引入/參考。

**這不是任務書**，是研究參考資料；如果要真的動工，應該針對其中某個
方向另開任務書，先小範圍驗證（例如先在這首歌上跑一次現成的預訓練
模型比較結果），再決定要不要整合進管線。

---

## 0. 對應關係：文獻怎麼對到我們的問題

| 我們確認的問題 | 具體案例 | 對應的研究方向 |
|---|---|---|
| 小節內偵測到 5-6 個真實拍點，relabel 無法消除 | 77.803s/80.020s/22.883s/35.300s/93.802s/153.467s（Pass 198 第 9.3 節） | §1 downbeat vs 過門/裝飾音辨識 |
| 證據薄弱段落（人聲清唱、鼓聲近乎靜默） | 8.041s、97.197s（Pass 196/198 已知） | §2 稀疏證據下的穩健拍點延續 |
| 多來源候選很接近時無法交叉驗證誰對 | `BarStartCandidateCommitNode._best_candidate` 只選信心最高（無驗證） | §3 多軌融合與共識機制 |

---

## 1. 為什麼「哪一拍是真正的重音」本質上很難：關鍵文獻結論

搜尋確認一個重要的學術共識，直接解釋了我們這幾季用 onset 能量/信心
分數手刻規則會撞牆的原因：

> **Downbeats are not necessarily associated with stronger signal
> energy, nor do they necessarily feature a distinct percussive
> profile.**（downbeat 在訊號層級不一定比較大聲，也不一定有明顯的
> 打擊樂特徵）

這代表我們這整季（包括 BarStart V2 的信心公式）用「onset 強度/是否
落在預期位置附近」當證據，**天花板本來就有限**——現代作法幾乎都改用
端到端訓練的神經網路模型，直接從資料學會「這是不是重音」，而不是
手刻信心公式。

### 相關的三個現代開源模型（依成熟度排序）

1. **`CPJKU/beat_this`**（Beat This!，ISMIR 2024）
   https://github.com/CPJKU/beat_this
   - 用旋轉 transformer 直接處理頻譜圖，**不需要 DBN 後處理**
     （我們現有的 madmom pipeline 依賴 DBN），用「shift-tolerant
     二元交叉熵」損失函數專門處理「標註跟真實拍點有些微時間誤差」
     的情況——這正好對應我們反覆處理過的「相位/時間誤差容差」問題。
   - 有現成預訓練模型跟 `beat_this.inference.load_model('final0')`
     可以直接呼叫，**可以先直接拿這首歌跑一次比較看看跟現有 madmom/
     BeatNet 結果差多少，成本很低**。
2. **BeatNet+**（2024/2025，NSF 技術報告）
   - 論文提到明確在「獨立人聲、非打擊樂音訊」上表現優於前代——**直接
     對應我們的 8.041s/97.197s 弱證據段落問題**。目前程式碼庫用的是
     BeatNet（舊版），值得查證 BeatNet+ 是否已經開源可用。
3. **Beat Transformer**（ISMIR 2022）
   https://arxiv.org/abs/2209.07140
   - **這篇論文的架構，幾乎就是使用者這幾輪一直在描述的「多軌各自
     分析、再融合」概念，只是用學習到的權重取代我們手刻的信心公式**：
     用 Spleeter 把歌曲分離成多個樂器聲道，對每個聲道分別做 beat/
     downbeat 追蹤，再用一個「同時做時間維度注意力跟樂器維度注意力」
     的 transformer 做融合，而不是像 BarStart V2 那樣用寫死的加權
     公式（kick+bass 90ms 內重合 +0.12 這種）。在有無鼓聲的測試集上
     都比傳統架構穩定，論文本身就是設計來處理「鼓聲不穩定/不存在」
     這種情況。**這篇論文的架構本身可以直接拿來對照檢討 BarStart V2
     的融合邏輯哪裡不夠**，就算不整個引入，也值得讀完整篇當設計參考。

---

## 2. 稀疏證據段落的穩健處理：相關專案

除了 BeatNet+ 之外，找到一個概念上很有參考價值的專案：

- **`headbang.py`**（consensus beat tracking）
  https://sevagh.github.io/headbang.py/
  - 核心設計哲學：**寧可少報，不要報錯**——這個工具會刻意只輸出
    「多個獨立 beat tracker 都同意」的強拍，其餘寧可空著不標，也不要
    在證據薄弱的地方硬猜。這正好呼應這整季反覆得到的教訓（Pass 193
    的核心教訓：沒有證據就不要硬做決定），只是 headbang.py 把這個
    原則做成了正式的演算法設計，而不是我們這邊用臨時的
    `protected_ranges`/證據門檻手動兜出來的。
  - 對應到我們的問題：8.041s/97.197s 這種段落，也許正確答案就是
    「誠實回報這裡沒有足夠證據」，而不是想辦法找出一個 4 拍答案——
    這跟 Pass 198 第 9.3 節「Stage 4 沒辦法安全解決」的結論方向一致，
    只是 headbang.py 提供了一個更系統化、有文獻背書的做法可以參考。

---

## 3. 多軌證據融合與衝突仲裁：相關文獻

對應我們確認的具體缺口（`_best_candidate` 只選信心最高、無交叉驗證）：

- **Drum-Aware Ensemble Architecture**（2021）
  https://arxiv.org/pdf/2106.08685
  - 對不同聲音來源（分軌）分別跑平行的 beat/downbeat tracker，再用
    一個 BLSTM 融合機制決定最終結果——跟 Beat Transformer 是同一個
    研究脈絡（現在的 SOTA 傾向用學習到的融合，不是手刻規則）。
- **ConsensusBeatTracker**（headbang.py 專案內）
  - 明確設計了「多個 tracker 意見不一致時的容差窗口跟共識門檻」機制
    ——用一個時間容差窗口判斷兩個 tracker 的候選算不算「同一個事件」，
    再用「至少幾個 tracker 同意」當共識門檻，這正是我們目前
    `BarStartCandidateCommitNode` 完全沒有的那一塊。
- **一般性原則**（多篇文獻共通）：和絃改變、貝斯根音、鼓組型態
  （kick 通常在 1、3 拍，snare 在 2、4 拍）都是文獻上驗證過的有效
  downbeat 證據來源，**證實 BarStart V2 現有的證據分層設計方向本身
  是對的（不是憑空亂做），只是融合/驗證機制的實作方式（手刻加權公式
  vs 學習到的融合、有沒有共識驗證）落後於現在的研究水準**。

---

## 4. 建議的下一步（不是任務書，是選項）

1. **成本最低、值得先做**：直接用 `CPJKU/beat_this` 的預訓練模型
   對這首歌跑一次，比較它產生的 beat/downbeat 標籤跟我們現有
   madmom/BeatNet pipeline 的差異，特別看它在 77.803s、8.041s、
   97.197s 這幾個已知問題點的表現——如果它天生就不會犯這些錯，
   可能比繼續修 Stage 4 後處理或 BarStart V2 更划算。
2. **中期參考**：讀完 Beat Transformer 全文，用來檢討 BarStart V2
   的融合邏輯設計哪裡該改（例如：要不要放棄手刻加權公式，改成某種
   學習到的融合；要不要引入時間維度+樂器維度的注意力機制概念）。
3. **設計哲學參考**：headbang.py 的「寧可少報、不要報錯」跟共識
   門檻設計，可以直接影響 Pass 199 第 5 節提到「promotion_gate 該
   考慮品質分數」跟「弱證據段落該誠實回報，不要硬插值」這兩個
   已經在討論的方向，不需要整個引入這個專案，取設計原則就有價值。

這三個方向都需要先跟使用者確認要投入到什麼程度（從「單純跑一次比較
結果」到「換掉整個 Stage 3 拍點偵測引擎」，成本跟風險差非常多），
不建議直接讓 Codex 憑這份文件自己決定範圍動工。

---

## 來源

- [Beat this! Accurate beat tracking without DBN postprocessing (arXiv 2407.21658)](https://arxiv.org/html/2407.21658v1)
- [GitHub - CPJKU/beat_this](https://github.com/CPJKU/beat_this)
- [Beat Transformer: Demixed Beat and Downbeat Tracking with Dilated Self-Attention (arXiv 2209.07140)](https://arxiv.org/pdf/2209.07140)
- [BEAT TRANSFORMER: DEMIXED BEAT AND DOWNBEAT TRACKING (ISMIR 2022)](https://archives.ismir.net/ismir2022/paper/000019.pdf)
- [Drum-Aware Ensemble Architecture for Improved Joint Musical Beat and Downbeat Tracking (arXiv 2106.08685)](https://arxiv.org/pdf/2106.08685)
- [BeatNet+: Real-Time Rhythm (NSF PAR)](https://par.nsf.gov/servlets/purl/10534060)
- [GitHub - mjhydri/BeatNet](https://github.com/mjhydri/BeatNet)
- [headbang.py — consensus beat tracking](https://sevagh.github.io/headbang.py/)
- [(PDF) Enhancing downbeat detection when facing different music styles](https://www.researchgate.net/publication/269294894_Enhancing_downbeat_detection_when_facing_different_music_styles)
