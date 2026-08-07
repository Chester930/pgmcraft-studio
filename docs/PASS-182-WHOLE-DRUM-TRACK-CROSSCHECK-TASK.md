# Pass 182 任務書：`SteadyPercussionCountAnchorNode` 補上整個鼓軌比對

**狀態**：已實作，單元測試與既有回歸測試皆已通過，見第 4 節。
**目標**：修正 Pass 181 剛做完就暴露出的架構缺口——`SteadyPercussionCountAnchorNode`
目前只看 kick/snare/hihat_cymbals 三個細分軌，完全不回頭比對整個鼓軌
（`drums.wav`），沒有使用者原本設計的「先從整個鼓軌辨識，細分軌處理不確定
的部分、進行比對與調整」這一層保險。

---

## 0. 背景

Pass 181 完成後，使用者提出疑慮：「先從整個鼓軌來辨識。如果有不確定的部分，
就透過鼓的細分軌來分析。進行比對與調整。這是我原先的想法，請檢查這部分。」

盤點現有管線後確認：
- 核心拍點/速度偵測（`BeatNetNode_TrackA`）跟 `MicroTimingTransientSnapNode`
  已經是「整個鼓軌（或鼓+貝斯）優先」，符合原則。
- 但負責「這一拍是誰在打、第一拍在哪」的關鍵節點——`KickSnarePulseNode`
  衍生出的一整串（`ReEntryReAnchoringNode`、`DownbeatPhaseConsistencyNode`、
  `KickAnchorConsensusSnapNode`）跟剛新增的 `SteadyPercussionCountAnchorNode`
  **完全只看細分軌，從來不回頭比對整個鼓軌**。
- `DrumFillDetectionNode` 有部分類似機制，但順序相反（細分軌優先，兩者都
  完全空了才退回整個鼓軌），不是「先廣後窄、不確定再比對」。

這次任務**只修 `SteadyPercussionCountAnchorNode`**（剛做完、最直接踩到這個
問題的節點）。`KickSnarePulseNode`、`DrumFillDetectionNode` 有同樣的架構
缺口，但範圍界定在第 3 節說明，不在這次任務內。

---

## 1. 設計

### 1.1 核心改動：整個鼓軌變成候選來源之一 + 細分軌候選要跟整個鼓軌比對

**現況**（Pass 181）：只對 kick/snare/hihat_cymbals 三個細分軌各自找「連續
穩定擊點」候選，互相比較變異係數決定優先權。

**改成**：

1. **新增整個鼓軌（`drums.wav`）當第四個候選來源**，用同一套「連續 ≥4 個、
   變異係數 <12%、間隔貼近全曲拍距 ±25%」邏輯找候選段——即使整個鼓軌因為
   多樂器疊加，規律性天生會比純細分軌雜訊多一點，還是可能找到候選（例如
   全曲很多樂器都同時在打拍子的段落）。
2. **細分軌候選要拿整個鼓軌的 onset 能量做確認**：對每一個從 kick/snare/
   hihat_cymbals 找到的候選段，檢查整個 `drums.wav` 在這段候選的每一個
   擊點時間附近（容差 ±40ms）**是否真的有 onset 能量**——這是比「整軌也要
   有一樣乾淨的連續段」更寬鬆的檢查（多樂器疊加本來就會讓整軌規律性變差，
   不能要求整軌一樣乾淨），但至少確保細分軌抓到的「乾淨規律」不是分離殘留
   的假訊號（真實混音裡完全沒有對應能量，卻在細分軌裡出現規律擊點，這種
   情況要當作可疑，不能盲目採用）。
   - 通過確認：正常列入候選，變異係數排序不變。
   - 沒通過確認：**不採用**，但要記錄進 report（例如
     `REJECTED_NO_WHOLE_TRACK_ENERGY`），讓這種情況可以被看見，不是靜默
     丟掉。
3. **整個鼓軌自己找到、但沒有對應到任何細分軌候選的候選段，一樣可以採用**
   （標記 `source="drums"`）——用在「多個樂器輪流疊加打拍子，沒有單一細分軌
   自己乾淨到符合門檻，但整體聽起來明顯在數拍」的情況。優先權排在「整軌
   確認過的細分軌候選」之後（因為無法歸因到具體哪個樂器，信心稍低，但仍然
   是這首歌實際聽得到的訊號，比完全找不到候選好）。

### 1.2 優先權順序（`_dedupe_overlaps` 更新）

1. 細分軌候選 + 整個鼓軌確認通過（依變異係數排序，同樣乾淨依
   kick > snare > hihat_cymbals）
2. 整個鼓軌自己找到、沒有細分軌候選對應的段落
3.（細分軌候選但整軌沒通過確認的——不列入候選池，只記錄在 report）

### 1.3 不變動的部分

- `_detect_onsets`（onset 偵測方法）、`_find_steady_runs`（找連續段的核心
  邏輯）、`_apply_anchor`（錨定+續接）都不變，只是多一個來源、多一層確認。
- 排除區（`snap_exclusion_zones`/`drum_fill_regions`）檢查邏輯不變，一樣
  套用在所有候選來源（含整個鼓軌）上。

---

## 2. 驗證計畫

1. **合成測試（整軌候選單獨成立）**：合成一段整個鼓軌訊號本身就有連續穩定
   擊點、但拆開的 kick/snare/hihat 都各自抓不到完整的段（例如兩個樂器
   輪流補位），驗證整軌自己的候選被正確找到並採用（`source="drums"`）。
2. **合成測試（細分軌候選被整軌確認）**：現有 Pass 181 的 5 項測試場景都要
   補上整個鼓軌音檔（內容涵蓋細分軌的擊點能量），驗證確認通過、候選正常
   採用，行為跟 Pass 181 完全一致（不能因為加了確認機制就讓原本會通過的
   案例變成不通過）。
3. **合成測試（細分軌候選被整軌拒絕，新增情境）**：合成一個細分軌裡有乾淨
   規律擊點、但整個鼓軌音檔在對應時間完全沒有能量（模擬分離殘留假訊號）的
   極端案例，驗證這種候選被正確拒絕、且 report 裡記錄
   `REJECTED_NO_WHOLE_TRACK_ENERGY`，不是靜默通過。
4. **真實資料回歸**：《World is Mine》hi-hat 18.561s-20.012s 這組真實案例，
   驗證補上整個鼓軌比對後依然正確辨識、正確採用（因為這段真實資料整個鼓軌
   在那幾個時間點本來就有對應能量，見 Pass 181 驗證過程紀錄）。
5. **既有回歸測試全跑一次**：確認沒有破壞既有行為（`test_commercial_beat_
   quality`、`test_sdd_pass23/28/42/87/102/103/104/141/144/178/179/180/181`、
   `test_module3_bt`）。

---

## 3. 範圍界定

- 這次**只修 `SteadyPercussionCountAnchorNode`**。`KickSnarePulseNode`（
  kick_anchors/snare_anchors 抽取，完全只看細分軌）跟 `DrumFillDetectionNode`
  （細分軌優先、整軌只在兩者都全空時當備援，跟這次要的「先廣後窄」順序
  相反）有同樣的架構缺口，是分開、還沒排入的後續工作，不在這次任務範圍內。
- 不修改 `_extract_peak_anchors`、`ReEntryReAnchoringNode`、
  `DownbeatPhaseConsistencyNode`、`KickAnchorConsensusSnapNode` 本身邏輯。
- 不改變 `SteadyPercussionCountAnchorNode` 在 `build_beat_refinement_nodes()`
  裡的位置。

---

## 4. 實作結果

### 4.1 修改內容

`pgm_craft/workflow/beat_tracking_bt.py` 的 `SteadyPercussionCountAnchorNode`：

- 新增 `WHOLE_DRUM_STEM = ("drums", ("drums", "drums.wav"))`，跟
  `STEM_CANDIDATES` 用同一套路徑解析方式（新增 `_resolve_stem_path()`
  helper，把原本內嵌在迴圈裡的解析邏輯抽出來，`WHOLE_DRUM_STEM` 也能共用）。
- `execute()` 流程改成：
  1. 先解析並對整個 `drums.wav` 做 onset 偵測（`whole_drum_onsets`）。
  2. 對 kick/snare/hihat_cymbals 找候選段（跟 Pass 181 一樣）。
  3. 每個細分軌候選都要通過 `_confirmed_by_whole_track()`——只要整個鼓軌
     檔案存在（`whole_drum_path` 不是 `None`），就要求候選段裡**每一個**
     擊點時間在整個鼓軌裡都有對應 onset（容差
     `whole_track_confirm_tolerance_sec`，預設 0.04 秒），沒通過的進
     `rejected` 清單（`reason: "REJECTED_NO_WHOLE_TRACK_ENERGY"`），不再
     進候選池。**沒有整個鼓軌檔案時完全跳過這層檢查**（保留 Pass 181 的
     行為，向後相容）。
  4. 對整個鼓軌自己也跑一次 `_find_steady_runs()`，只保留沒有被任何已確認
     細分軌候選涵蓋到的段落（`_overlaps()` 判斷），標記 `source="drums"`。
  5. 細分軌確認候選 + 整軌獨立候選合併後才進 `_dedupe_overlaps()`——優先權
     順序更新為變異係數優先，同樣乾淨依 `STEM_CANDIDATES` 順序，`drums`
     敬陪末座。
- report 新增 `rejected` 欄位（`NO_STEADY_RUN_FOUND`、
  `CANDIDATES_FOUND_BUT_NOT_APPLIED`、`ANCHORED` 三種狀態都會帶），讓
  「找到但因為整軌沒對應能量而不採用」這件事可以被看見，不是靜默丟掉。

### 4.2 測試結果

新增 `tests/test_sdd_pass182.py`（4 項全過）：

1. `test_confirmed_sub_run_still_anchors`——Pass 181 的清晰案例補上對應的
   整個鼓軌音檔，驗證正常通過、`rejected` 為空。
2. `test_sub_run_rejected_without_whole_track_energy`——細分軌乾淨規律，但
   整個鼓軌在對應時間沒有能量（整軌本身在別處有活動，不是完全空白，排除
   「沒有整軌檔案」這種會被跳過檢查的情境），驗證正確拒絕、
   `reason == "REJECTED_NO_WHOLE_TRACK_ENERGY"`，`beats` 沒被動到。
3. `test_whole_track_only_candidate_anchors`——kick 只打第 1、3 拍、snare
   只打第 2、4 拍（各自都不足 4 個連續），但整個鼓軌（兩者疊加）合起來有
   完整連續四拍，驗證正確找到並採用 `source="drums"` 的候選。
4. `test_real_captured_hihat_scenario_still_anchors_with_whole_track`——
   Pass 181 的真實 hi-hat 回歸案例補上對應的整個鼓軌音檔，驗證依然正確
   辨識、正確採用。

`tests/test_sdd_pass181.py` 原本 5 項測試（沒有提供 `drums.wav`）全部維持
不變地通過，確認「沒有整軌檔案時跳過確認檢查」的向後相容設計正確。

既有回歸測試（`C:/Python313/python.exe`，含 madmom 的正確環境）：
`test_commercial_beat_quality`、`test_sdd_pass23/28/42/87/102/103/104/
141/144/178/179/180/181`、`test_module3_bt`，加上新增的
`test_sdd_pass182`，共 78 項全數通過。
