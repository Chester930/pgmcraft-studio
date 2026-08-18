# Pass 236 任務書：madmom 當主要輸出，弱區段整段替換成 V2（不逐拍融合）

**狀態**：設計已定案，根因鏈已完整（Pass229→235），可直接轉交 Codex
CLI 執行。**這是全新的後製階段（post-processing splice），不是修改
`_best_candidate()`仲裁邏輯本身——刻意避開 Pass232/235 已經證明會
連鎖污染的逐拍融合設計。**

---

## 0. 背景：為什麼要換方向

- Pass229-231：madmom（`RNNDownBeatProcessor`+`DBNDownBeatTrackingProcessor`，
  `transition_lambda=500`）不接分軌、不用任何自製證據融合，直接對
  原始音檔跑，Verse1/Chorus1/Intro 幾乎完美（Pass233實測：Intro
  17/17、Verse1 42/42、Chorus1 42/42 都在50毫秒內），只有Outro較弱
  （9/20，45%）。
- Pass232、Pass235：兩次嘗試把madmom候選逐拍融合進BarStart V2的
  仲裁機制，**都造成真實retrogression**（Pass232：barstart_v2_score
  80.66→65.77；Pass235：離線驗證顯示Verse1/Chorus1/Outro全面退步，
  未進真實驗證）。**根因已經精確定位**（Pass234逐案例驗證）：
  BarStart V2的`phase_consistency_score`純粹跟已委任歷史比對，
  覆蓋一次會改變後面**每一個**tick的比對基準，造成連鎖漂移——這是
  逐拍融合這個設計本身的結構性問題，不是信心值或排序權重能調好的。
- **使用者實際聽過兩個版本後確認**：目前正式基準（BarStart V2，
  `barstart_v2_score=80.66`，無madmom）Chorus1明顯不穩、一直搶拍，
  Intro有hihat對齊問題（Pass212已診斷過、修復嘗試造成退步、目前
  仍未修復，見`docs/BT-BUILD-PROGRESS.md`Pass212條目）；純madmom版本
  「整體而言比較穩，差滿多的」，但**確認還是有「沒有鼓與自由拍漸快
  漸慢」處理不好的段落**——跟Pass230量測到Outro真實速度變化（前半段
  1.5022秒/小節、後半段1.4196秒，中間有拉長到1.6-1.625秒的段落）
  完全吻合。

**決策（使用者已確認）**：不再嘗試逐拍融合，改成**madmom當全曲主要
輸出，只在madmom自己表現弱的區段，整段替換成V2的輸出**——替換是
一次性的、尊重小節邊界的後製拼接，不是逐tick即時覆蓋，不會有
Pass232/235那種連鎖污染問題。

---

## 1. 弱區段判斷依據：不要用鼓組密度，要用 madmom 自己輸出的局部速度變異度

**重要更正（寫任務書時發現，避免Codex重蹈覆轍）**：原本直覺會想用
「鼓組onset密度」當弱區段判斷依據（Pass230量測過Intro密度1.511/秒、
Outro 2.476/秒，都明顯低於Verse1/Chorus1的3.5+/秒）——**但這個訊號
會誤判**：Intro密度低，但madmom在Intro實測是100%完美命中（Pass233
`direct_madmom_report.json`），代表密度低不等於madmom追蹤得差。
真正的區別在於**Outro有真實劇烈的速度變化，Intro只是證據稀疏但
速度穩定**——madmom對「證據稀疏但速度穩定」處理得很好（正是DBN
tempo-lock的強項），對「證據稀疏+速度真的在變」才會出問題。

**改用madmom自己輸出的小節間距局部變異度**當判斷依據——這個訊號
直接從madmom自己的結果算出來，不需要額外的鼓組資料，而且直接對應
真正的失敗模式：

```python
def _detect_weak_spans(madmom_downbeats, window_bars=5, cv_threshold=0.06, min_span_bars=2):
    """對madmom輸出的每個小節，計算前後window_bars個小節間距的
    變異係數（std/mean）。變異係數過高代表這個區域madmom自己的
    tempo-lock正在被迫劇烈調整（要嘛是真的在變速，要嘛是被迫追一個
    不穩定的訊號），標記成弱區段。cv_threshold需要離線用真實資料
    校準（見第3節），這裡給一個起點，不是定案數值。"""
    ...
```

`window_bars`/`cv_threshold`/`min_span_bars`**都需要離線驗證校準**
（第3節），不能憑感覺硬編碼——目標是校準到「準確標記Outro那個已知
有問題的區段，同時不誤傷Intro/Verse1/Chorus1」，用Pass233已有的
逐段殘差數字（Intro 17/17、Verse1 42/42、Chorus1 42/42、Outro 9/20）
當校準的ground truth。

---

## 2. 整段替換機制（後製拼接，不是逐拍融合）

```python
def _splice_weak_spans_with_fallback(madmom_downbeats, fallback_downbeats, weak_spans):
    """weak_spans: [(start_time, end_time), ...] 已經合併過的連續弱
    區段。對每個weak span：
    1. 移除madmom_downbeats裡落在[start_time, end_time]的小節。
    2. 插入fallback_downbeats（V2既有輸出，見第4節）裡落在
       [start_time - tolerance, end_time + tolerance]的小節。
    3. 邊界不強制對齊——容許替換邊界處出現稍微不規則的小節長度
       （這個專案既有的BarGridContinuityRepairNode等機制本來就
       容許這種過渡），但要把每次替換的邊界間距記錄進報告，方便
       事後檢查有沒有不合理的大跳。
    4. 合併排序、去除重複（沿用BarStartCandidateCommitNode既有的
       duplicate_tolerance_sec=0.03慣例）。
    回傳最終網格 + 一份透明的替換報告（第5節）。
    """
    ...
```

---

## 3. 驗證流程

### 3.1 離線校準+驗證（先做，便宜快速）

用`scratch/pass233...`（或重新產生）madmom全曲降拍清單 +
`scratch/pass222_full_song_candidate_trace.jsonl`或最新的V2全曲輸出
（不需要重跑pipeline，這兩份資料應該都已經有現成的可以重用，Codex
可以確認哪一份最新），離線測試`_detect_weak_spans`的參數校準：

1. 掃`window_bars`/`cv_threshold`的合理範圍組合，確認有一組參數
   讓弱區段判定**精準對應Outro**（而且只有Outro，不要誤傷
   Intro/Verse1/Chorus1——這是最重要的驗收標準，因為Intro看似證據
   稀疏但madmom在那裡其實是滿分，錯誤地把Intro也判成弱區段、替換
   成V2的輸出，反而會把已經修好的Intro再弄壞）。
2. 用選定的參數跑一次完整拼接，離線比對拼接後的網格 vs
   （a）純madmom（b）純V2 的逐段golden殘差，確認拼接後的結果**至少
   不比純madmom差**（Intro/Verse1/Chorus1維持madmom的近乎完美表現，
   Outro因為換成V2的輸出應該要跟純V2的Outro表現相近）。

### 3.2 真實資料驗證（離線驗證通過後才做）

用`scratch/run_pass228_grounded_score_production_verify.py`（或
Codex熟悉的等效腳本，這次madmom走的是全新的後製拼接節點，不動
`_best_candidate()`，理論上不會影響V2自己的內部行為，但仍然要用
真實pipeline跑一次確認）：

- 重新計算`barstart_v2_score`（用Pass228的`_score_beat_grid_grounded`，
  在拼接後的最終網格上算）——**這次的比較對象除了現行基準80.66，
  也要跟純madmom（沒有拼接）的分數比**，確認拼接後至少不比純madmom
  差、且Outro有實質改善。
- 逐段跟golden比殘差，確認Intro/Verse1/Chorus1維持接近madmom的
  近乎完美表現（**這是最重要的安全底線**：如果拼接機制不小心把
  Intro/Verse1/Chorus1也判成弱區段、替換掉了，就是設計失敗，要
  revert，不能將就）。
- **明確要求**：這個新機制先用一個明確的opt-in旗標控制（例如
  `madmom_hybrid_approved`，比照`barstart_v2_promotion_approved`
  既有的manual-approval慣例），不要變成任何呼叫端的預設行為——
  這個決定不在本任務書範圍內，需要使用者另外核准才能變成正式
  預設輸出。

---

## 4. 資料來源：V2的哪個網格當替換用的fallback？

**用V2目前實際的最終輸出**（`Module3BarStartV2MergeNode`寫入的
`beats`/`refined_beats`，也就是現在使用者聽到的那個80.66分基準版本
——即使它整體比madmom差，在madmom自己也弱的Outro這種區段，V2至少
還有貝斯/和絃/旋律等額外證據來源，不是只靠鼓組，可能還是比讓madmom
硬撐一個它自己也不確定的區段更好）。**不要另外接legacy v1的輸出
當fallback**——範圍收斂，只用現成已經算好、使用者已經聽過評估過的
V2輸出。

---

## 5. 透明度要求（不能悄悄替換，要看得出哪裡被替換過）

比照這個專案一貫的慣例（`bar_grid_repair_report`/
`tail_extrapolation`等既有欄位的設計精神）：

1. 新增`madmom_hybrid_report`欄位，記錄：
   - 偵測到幾個弱區段、各自的起訖時間。
   - 每個弱區段替換了幾個小節、來源是V2的哪幾個小節。
   - 替換邊界的間距數字（用來事後檢查有沒有不合理的大跳）。
2. 這些替換出來的小節，`evidence_sources`要標成類似
   `["v2_fallback_splice"]`，不要跟madmom自己的小節混在一起看不
   出來——之後如果要繼續改善，需要能清楚知道哪些小節是madmom原生
   輸出、哪些是替換進來的。

---

## 6. 測試要求

新增`tests/test_sdd_pass236.py`：

1. 合成案例：構造一個madmom降拍序列，其中一段小節間距劇烈變異
   （模擬Outro那種真實速度變化），驗證`_detect_weak_spans`正確
   標記出那一段，且**不誤標速度穩定但密度低的段落**（用合成的
   稀疏但等間距序列驗證，直接對應「不能誤傷Intro」這個安全要求）。
2. 合成案例：驗證`_splice_weak_spans_with_fallback`正確移除弱區段
   內的madmom小節、插入對應的V2小節，邊界外的小節完全不受影響。
3. 邊界案例：弱區段完全沒有對應的V2小節可用（fallback也是空的）
   ——驗證優雅降級（保留madmom原本的輸出，不要因為fallback缺失就
   整個崩潰或產生空洞）。
4. 執行既有回歸測試確認沒有破壞其他機制：
   ```
   C:/Python313/python.exe -m pytest tests/test_sdd_pass236.py tests/test_sdd_pass202.py tests/test_module3_bt.py -q
   ```

---

## 7. 完成後

1. 更新`docs/BT-BUILD-PROGRESS.md`，新增Pass236條目：完整記錄
   離線校準參數（`window_bars`/`cv_threshold`/`min_span_bars`最終
   選了什麼值、為什麼）、真實資料驗證的完整數字（跟純madmom、跟
   現行V2基準80.66三方比較）、Intro/Verse1/Chorus1有沒有維持
   完美（安全底線）、Outro有沒有實質改善。
2. 更新使用者記憶檔案（如果是Claude執行）。
3. Commit + push到`origin/worktree-pass171-multi-variant-harness`，
   commit message用`feat(pass236): ...`前綴。
4. **不要在這個任務書範圍內順便做**：(a) 修改
   `BarStartCandidateCommitNode._best_candidate()`或任何V2內部仲裁
   邏輯（Pass232/235已經證明這條路是死路）；(b) 把這個機制設成
   任何呼叫端的預設行為（需要使用者另外核准）；(c) 嘗試修Pass212
   那個V2 Intro syncopation誤判的舊bug（這個新設計繞開它就好，
   不需要回頭修）；(d) 在其他曲目做量化驗證（沒有其他曲目的golden
   基準，範圍留給之後）。
