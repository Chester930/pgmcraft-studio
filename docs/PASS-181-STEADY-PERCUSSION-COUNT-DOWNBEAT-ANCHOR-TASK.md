# Pass 181 任務書：連續穩定擊點（Kick/Snare/Hi-hat）當第一拍續接錨點

**狀態**：已實作，單元測試（含真實資料回歸）與既有回歸測試皆已通過，見第 4
節。真實音訊完整管線回歸（確認對《World is Mine》18 秒附近實際有幫助）尚未
執行，需要使用者同意才進行。
**目標**：修正使用者在《World is Mine》前奏/間奏區段聽到的「第一拍沒對上」問題
——當任一打擊樂器（kick、snare、或 hi-hat/鈸）連續打出 ≥4 下真正等間隔、
間隔又貼近全曲已知拍距的擊點時，這代表樂器正在「明確數拍子」，可以拿來當作
這段時間最可信的拍號續接依據，強制往後（可能也往前）重算 1-2-3-4 循環。
**這個訊號不是每首歌都有**——找不到就完全不動，不勉強套用。

---

## 0. 背景：這個訊號是怎麼被驗證出來的

### 0.1 起點

Pass 180 修好 `ViterbiTempoSmoothingNode` 後，使用者重新試聽《World is Mine》
確認結果：「副歌都滿不錯的。前奏和間奏勉強接受。但是有出現第一拍沒對上的
問題。」並提出一個具體構想：「連續出現四個 Kicks 就是鼓在給 1234 拍，所以
那個就是指小節的 1234 拍可以接續。」

### 0.2 第一次查證：偵測邏輯設計對了，但這首歌的 kick 沒有這個型態

用 `_extract_peak_anchors` 對 kick 音軌整首歌重新提取擊點，寫了一版偵測邏輯
（連續 ≥4 個、變異係數 <12%、且間隔要接近全曲已知拍距 ±25%），在全曲找到 4
段候選，只有兩段（93.7s、111.4s，都落在副歌）真正乾淨地符合「間隔幾乎等於
全曲拍距」，但副歌已經不需要這個機制介入；前奏那段（12.3s-15.0s）間隔是拍距
的 2.4 倍且逐漸拉長，正確地被排除掉——**偵測邏輯設計本身是對的，但這首歌的
kick 軌在使用者說的問題區段（前奏/間奏）沒有這個型態**。

### 0.3 使用者指出具體位置，才發現真正的訊號在別的樂器上

使用者接著明確指出：「這首歌有喔!! 大約在 18 秒的位置。」查證 kick 音軌
15.1s-19.9s 完全靜音（振幅趨近雜訊底噪），一開始誤判成「這裡沒有訊號」。
使用者追問「還是那個音色不是鼓的 kick，是鼓的哪一軌」，才去查完整鼓組軌
（`drums.wav`）跟細分軌（`snare.wav`、`hihat_cymbals.wav`），發現
`hihat_cymbals.wav` 在 16s-19.5s 有明顯能量，但用**振幅包絡**（每 0.05 秒抓
一次最大值）看起來是連續攀升的滾奏型態，回報使用者「像是鈸的滾奏漸強，不是
四下分開的敲擊」。使用者確認「鈸的聲音」，但接著反問「真的沒有四下鼓敲擊
HI HAT 嗎? 我確認有」。

### 0.4 分析方法本身的錯誤：振幅包絡看不出真正的離散擊點

改用**正確的 onset 偵測**（`librosa.onset.onset_strength` +
`onset_detect`，抓真正的獨立擊點時間，而不是粗略的音量高低）重新分析
`hihat_cymbals.wav` 的 13-21 秒區間，這次在 **18.561s、18.933s、19.293s、
19.641s、20.012s** 清楚抓到連續四個間隔：`0.372s, 0.360s, 0.348s, 0.372s`
——平均 0.363 秒，幾乎完全等於這首歌的拍距（黃金基準量出來是 0.364 秒），
**變異係數只有 2.6%，是目前查過所有候選裡最乾淨的一組**。

**教訓**：先前用 `_extract_peak_anchors`（簡單的窗口最大值包絡）分析 kick/
snare 沒問題，是因為鼓聲本身夠「尖峰」；但 hi-hat/鈸這種質地比較連續、比較
不「尖峰」的樂器，窗口最大值法會被附近較大聲的滾奏蓋掉細節，必須用真正的
onset 偵測才能正確抓到離散擊點。**這次任務實作時，偵測邏輯必須對 kick、
snare、hi-hat/鈸統一用 onset 偵測，不能沿用 `_extract_peak_anchors` 的窗口
最大值法**（那個方法目前給 `KickSnarePulseNode` 用是可以接受的，但這個新
節點的偵測目標本質上更依賴分辨「連續但緊密的獨立擊點」，需要更精確的方法）。

---

## 1. 設計

### 1.1 新節點：`SteadyPercussionCountAnchorNode`

放在 `ReEntryReAnchoringNode` 附近（同屬於「找到強力證據點、強制標記、往後
續接 1-2-3-4 循環」這一類節點）。

**輸入來源**（依序嘗試解析路徑，仿照 `KickSnarePulseNode` 的既有寫法）：
- `stems["kick"]` / `stems_dir/drums/kick.wav`
- `stems["snare"]` / `stems_dir/drums/snare.wav`
- `stems["hihat_cymbals"]` / `stems_dir/drums/hihat_cymbals.wav`（新增路徑
  解析，目前專案裡沒有節點在讀這個檔案）

**偵測步驟**（每個樂器分開跑，找到的候選再合併）：
1. 對該樂器音軌用 `librosa.onset.onset_strength` + `onset_detect` 抓真正的
   離散擊點時間（**不用 `_extract_peak_anchors`**，見 0.4 節教訓）。
2. 掃描擊點序列，找連續 ≥4 個（可設定，預設 4）擊點，滿足：
   - 相鄰間隔的變異係數（std/mean）低於門檻（預設 12%）——確保是真正等間隔，
     不是巧合規律。
   - 這段的平均間隔要落在**全曲已知拍距**（從當下 `beats` 陣列算出的中位數
     拍距，不是這個新節點自己重新猜）的 ±25% 範圍內——排除「間隔規律但根本
     不是逐拍」的情況（例如 0.4 節之前查到的 12.3s、150.3s 那兩段）。
   - 排除掉落在 `snap_exclusion_zones`/`drum_fill_regions`（`DrumFillDetectionNode`
     已經標記的過門密集擊點區）裡的候選，雙重保險。
3. 找到符合的連續段時：把第一個擊點強制標記成 Beat 1、依序 2、3、4，然後從
   這個錨點往後重新推算 1-2-3-4 循環（重用 `ReEntryReAnchoringNode` 已經有
   的「錨點+續接」寫法，直到下一個更強證據點或曲末）。
4. 找不到任何樂器有這種連續段時：完全不動 `beats`，安全空操作（`smoothing_
   report`/自己的 report 裡標記 `NO_STEADY_RUN_FOUND`）。

### 1.2 待實作時決定的細節

1. **多個樂器都找到候選時的優先順序**：例如同一段時間 kick 跟 hi-hat 都有
   候選、但標記的相位不一致，要以誰為準？傾向：變異係數更低（更「乾淨」）
   的優先；同樣乾淨則 kick > snare > hi-hat（低頻樂器通常更少被和聲/旋律的
   殘留干擾污染）。
2. **跟 `ReEntryReAnchoringNode` 的先後順序跟衝突處理**：這個新節點放在
   `ReEntryReAnchoringNode` 之前還是之後？傾向放在**之後**，讓這個訊號有
   機會覆蓋掉能量邊緣重錨的結果（因為「連續四個等間隔擊點」是比「無鼓→
   有鼓的能量邊緣」更直接、更明確的相位證據），但需要在合成測試裡驗證兩者
   疊加不會互相打架。
3. **續接的邊界**：從錨點往後重算 1-2-3-4，要算到哪裡停？沿用
   `ReEntryReAnchoringNode` 的做法（算到下一個更強錨點或曲末），但要考慮
   「往前」（錨點之前的拍點）要不要也回頭修正——先只做「往後」，因為這是
   `ReEntryReAnchoringNode` 已經驗證過的安全做法，往前修正風險較高、先不做。

---

## 2. 驗證計畫

1. **合成測試（保留正確行為）**：合成一段規律的 4 拍等間隔擊點（例如
   kick），驗證節點正確找到、正確從第一下開始標記 1-2-3-4 並往後續接。
2. **合成測試（正確排除誤判）**：
   - 合成一段「間隔規律但跟全曲拍距差很多」的擊點（模擬 0.2 節查到的 12.3s/
     150.3s 案例），驗證不會被誤判成有效錨點。
   - 合成一段「密集過門」（間隔遠短於拍距）擊點，驗證不會被誤判。
3. **真實資料回歸測試**：直接節錄這次真實驗證到的
   `hihat_cymbals.wav` 18.561s-20.012s 這組真實時間資料當固定測試資料，
   驗證節點能正確辨識出來（這是目前找到最乾淨的真實案例，變異係數 2.6%）。
4. **既有回歸測試全跑一次**：確認新節點插入 `build_beat_refinement_nodes()`
   沒有破壞既有行為（`test_commercial_beat_quality`、
   `test_sdd_pass23/28/42/87/102/103/104/141/144/178/179/180`、
   `test_module3_bt`）。
5. **真實音訊回歸（可選，成本較高，需使用者同意）**：《World is Mine》完整
   跑一次，確認 18-20 秒附近的第一拍位置是否真的被修正、且沒有在其他段落
   造成退步。

---

## 3. 範圍界定

- 這次只處理「連續穩定擊點當錨點」這一個訊號來源，不處理其他可能的降拍
  訊號（貝斯根音、和弦轉換點等）——使用者在前一輪有提過這個備案方向，
  但這次先驗證擊點訊號本身，不同時做兩件事。
- 不修改 `_extract_peak_anchors`（`KickSnarePulseNode` 沿用既有窗口最大值法
  不變）——這次的教訓只套用在新節點自己的偵測邏輯上。
- 不修改 `ReEntryReAnchoringNode` 本身邏輯，只決定新節點跟它的相對順序。

---

## 4. 實作結果

### 4.1 新增內容

`pgm_craft/workflow/beat_tracking_bt.py`：

- 新增 `SteadyPercussionCountAnchorNode`（放在 `DrumFillDetectionNode` 之後、
  `OnsetPhaseRealignmentNode` 之前——比原本規劃的「`ReEntryReAnchoringNode`
  之後」更晚一點，理由是要讓 `snap_exclusion_zones`/`drum_fill_regions`
  在這個節點執行時已經真的存在，排除區檢查才有實際作用，不是空清單）。
- `STEM_CANDIDATES = [("kick", ...), ("snare", ...), ("hihat_cymbals", ...)]`：
  依序解析 `stems` dict 或 `stems_dir/drums/*.wav` 路徑，跟
  `KickSnarePulseNode` 既有的路徑解析寫法一致，新增了 `hihat_cymbals.wav`
  這個目前專案裡沒有節點讀取過的路徑。
- `_detect_onsets()`：用 `librosa.onset.onset_strength` + `onset_detect` 做
  真正的 onset 偵測，不是 `_extract_peak_anchors` 的窗口最大值包絡（見第
  0.4 節教訓）。
- `_find_steady_runs()`：逐步延伸連續段，每加入一個新間隔就檢查（a）間隔要
  落在 `known_beat_length ± 25%` 範圍內、（b）目前為止所有間隔的變異係數要
  低於 12%，兩者都通過才繼續延伸；並排除跟 `snap_exclusion_zones`/
  `drum_fill_regions` 重疊的候選。
- `_dedupe_overlaps()`：多個樂器的候選時間重疊時，取變異係數最低者，同樣
  乾淨則依 `STEM_CANDIDATES` 順序（kick > snare > hihat_cymbals）決定。
- `_apply_anchor()`：把連續擊點依序快照對應到最近的 `beats` 陣列拍點（容差
  0.12 秒，超過就放棄這段），標記成 1-2-3-4，再從最後一個快照點往後續接
  循環，直到下一個已接受的錨點或曲末——重用 `ReEntryReAnchoringNode` 的
  「錨點+續接」寫法精神，但錨點本身是一整段擊點（直接給定 1234 的對應），
  不是單一時間點再往後猜循環相位。
- `build_beat_refinement_nodes()` 插入這個新節點，並加註解說明位置理由。

### 4.2 測試結果

新增 `tests/test_sdd_pass181.py`（5 項全過）：

1. `test_clean_steady_run_anchors_and_continues_cycle`——合成規律 4 拍
   kick，驗證正確標記 1234 並往後續接。
2. `test_regular_but_wrong_scale_interval_not_anchored`——間隔規律但是全曲
   拍距的 2.5 倍，驗證正確排除（對應 0.2 節查到的 12.3s/150.3s 案例）。
3. `test_dense_fill_not_anchored`——16 分音符等級的密集過門，驗證正確排除。
4. `test_no_stems_is_safe_noop`——沒有任何鼓組音軌時安全空操作。
5. `test_real_captured_hihat_scenario_anchors_correctly`——節錄真實抓到的
   hi-hat 18.561s-20.012s 案例當回歸固定資料，驗證五個 onset 對應到的拍點
   被正確標記成 1,2,3,4,1，且快照點彼此是連續格點索引（間隔真的貼合全曲
   拍距），錨點之後也正確續接 2,3,4,1。

既有回歸測試（`C:/Python313/python.exe`，含 madmom 的正確環境）：
`test_commercial_beat_quality`、`test_sdd_pass23/28/42/87/102/103/104/
141/144/178/179/180`、`test_module3_bt`，加上新增的 `test_sdd_pass181`，
共 74 項全數通過，確認新節點插入沒有破壞既有行為。

### 4.3 尚未執行

- 第 2 節第 5 項「真實音訊回歸」尚未重新跑《World is Mine》完整管線——需要
  使用者同意才執行（Demucs 分離+完整精修鏈，約 10-30 分鐘），確認 18-20
  秒附近的第一拍位置在真實管線裡真的被修正、且沒有在其他段落造成退步。
