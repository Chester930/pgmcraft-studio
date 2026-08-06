# Pass 178 任務書：V3 生產化 — GapReinforcementNode 正式整合 + 人工微調校準迴圈

**狀態**：`GapReinforcementNode` 已實作並整合進 `build_beat_refinement_nodes()`，
校準腳本已完成。黃金基準真實資料回歸比對（《World is Mine》，見第 4 節）已完成，
**結果是負面的**：節點目前的實作讓整體管線輸出比黃金基準、也比停用時的對照組
都更差，已改為**預設關閉**（`enabled=False`），詳見第 4 節。單元測試
（`tests/test_sdd_pass178.py` 4 項，含新增的「預設關閉即空操作」測試）與既有
Stage 3 相關測試（38 項）在改動後全數通過。
**目標**：把 Pass 176 設計、Pass 177 在審查工具裡用 Lane1-5 實測驗證過的「逐輪疊加
證據」機制，正式寫進 V1 正式管線變成 V3——同時保留人工標記微調的能力，但職責
跟正式生產流程完全分離：**正式生產一次跑完，不需要人工在場；人工複核是隨選的
校準動作，讀已經存好的紀錄，標記結果回饋給下一次的門檻校準，不即時介入這一次
的生產結果**。

---

## 0. 背景：Pass 176 設計 + Pass 177 實測學到的東西

### 0.1 Pass 176 已經定案的部分（見 `PASS-176-V3-GAP-REINFORCEMENT-TASK.md`）

- V3 = V1 骨架（`BeatFusionArbitratorNode` 雙軌融合）+ V2 的「多層音色疊加證據」
  觀念，只用在 V1 自己已經標記出的弱點（`beat_fusion_report["track_b_spans"]`），
  不整套替換、不重新發明 Stage 0/Stage 1。
- 新節點 `GapReinforcementNode`，放在 `BeatFusionArbitratorNode` 之後、精修守衛鏈
  最前面。
- 逐輪疊加：鼓 → +貝斯 → +和弦 → +旋律，複用 `BassEvidenceExtractNode` /
  `ChordMelodyOnsetSplitNode` / `ChordTrackPKNode` / `VocalMelodyEvidenceExtractNode` /
  `MelodyTrackPKNode` 等既有節點，不重新發明證據抽取邏輯。
- 缺口重建拍點要用缺口前後「V1 已確信」的拍點做雙向錨定，複用
  `BidirectionalBarAlignmentNode` / `TwoWayAnchorBacktraceNode`。

### 0.2 Pass 177 在審查工具裡實測學到、Pass 176 設計時還不知道的三件事

Pass 177 用 scratch 腳本（`lane1_pure_drum_detection.py` ~
`lane5_full_instrumental_detection.py`）搭配多軌審查工具（`gap_review_server.py`），
在真實歌曲上模擬了「逐輪疊加證據、只補救上一層可疑段落」的概念，得到三個必須
在正式整合時處理的發現：

1. **概念本身有效，且是跨演算法驗證過的**：拿完全獨立的兩種方法（簡化 librosa
   vs V1 正式 BeatNet，鼓+貝斯 vs 純鼓）互相比對需複核區段，重疊率 90-95%——
   代表信心評分抓到的是音檔本身真實的性質，不是演算法雜訊。
2. **「分軌疊加音頭」跟「真正的完整混音」不等價**：Lane1-4 疊加證據的方式是把
   分開抽出來的音頭訊號（kick/snare/bass onset、和弦/旋律 onset）加總成合成
   envelope，不是真正的聲學混音。Lane5 改用 `stems/no_vocals.wav` 本身直接分析，
   在 Lane4 判定已經沒問題的區段裡，多抓出了 3 個分軌疊加方式漏掉的問題——
   代表 V3 的證據階梯除了現有的疊加式證據，**還需要一輪「真正完整混音」的
   複核**，不能只疊加分軌 onset。
3. **「拍點時間錯」跟「拍點時間對、但第一拍標錯」是兩個不同問題，需要不同修法**：
   審查工具後來加了 `fail`（不在拍點上）／`fail_phase`（有在拍點上但相位標錯）
   的區分。Lane1-5 的拍號目前是循環硬編號（`(i % 4) + 1`），沒有真正的 downbeat
   判斷，`fail_phase` 目前是死資料。V1 正式管線已經有處理這件事的機制
   （`DownbeatRefinementNode`、`beat_precision_diagnostics` 裡的
   `downbeat_fix_report` / `phase_realignment_report` / `kick_anchor_snap_report`），
   `GapReinforcementNode` 補完拍點時間之後，必須接上這些既有機制做相位修正，
   不能沿用 scratch 版本的簡陋編號。

### 0.3 使用者確認的核心原則（貫穿 Pass 176-178）

> 「整個流程跟人工沒有任何關係。人工是為了給反饋作為修正，下一次才會調整。」

人工標記**不能**即時介入當次生產結果——這條原則同樣適用於正式整合後的 V3：
`GapReinforcementNode` 用已經校準好的門檻參數自動判斷、自動產出結果，任何一首
歌都能自動跑完，不會卡在等人工審核。人工複核是**額外、隨選**的品質檢查，用來
累積校準資料，不是生產流程的必經步驟。

---

## 1. 設計：兩條迴圈，職責分離但互相餵養

### 1.1 正式生產迴圈（自動，`GapReinforcementNode` 本體）

**放置位置**：沿用 Pass 176 設計，`BeatFusionArbitratorNode` 之後、
`build_beat_refinement_nodes()` 精修守衛鏈最前面。

**缺口偵測**（比 Pass 176 原案更完整）：

| 訊號來源 | 用途 |
|---|---|
| `beat_fusion_report["track_b_spans"]`（既有） | 粗篩：A 軌能量不足的區段，免費、已經算好 |
| 音頭確認比例信心評分（Pass 177 驗證過的方法，套用在融合後的最終網格上） | 細篩：抓出 `track_b_spans` 漏掉的、能量正常但拍點其實對不上真實音頭的區段 |

兩者聯集作為 `GapReinforcementNode` 要處理的缺口清單，不只依賴單一能量門檻。

**證據疊加階梯**（比 Pass 176 原案多一輪）：

| 輪次 | 證據池 | 備註 |
|---|---|---|
| 第 1 輪 | 鼓 + 貝斯 | 複用 `BassEvidenceExtractNode` |
| 第 2 輪 | + 和弦 | 複用 `ChordMelodyOnsetSplitNode` / `ChordTrackPKNode` |
| 第 3 輪 | + 旋律 | 複用 `VocalMelodyEvidenceExtractNode` / `MelodyTrackPKNode` |
| 第 4 輪（新增，Pass 177 Lane5 驗證過） | 完整無人聲混音（`stems/no_vocals.wav`）直接重新分析，不是分軌疊加 | 抓分軌疊加方式漏掉的聲學交互作用 |
| 都不夠 | 沿用現狀等速內插 | 不得比現狀更差 |

每輪跟 Pass 176 一樣，用 V2 現成的 `bar_start_candidates` 累積評分機制，信心度
超過門檻就停止疊加、採用該輪結果。

**新增：相位修正輪**（Pass 177 發現的缺口，Pass 176 沒有）——證據階梯補完拍點
「時間」之後，缺口區段要另外跑一次 V1 既有的 downbeat 相位判斷邏輯（重用
`DownbeatRefinementNode` 或對應的 `phase_realignment` 邏輯，不重新發明），修正
「哪一拍是第 1 拍」，不能假設疊加證據補完時間後相位自動就對。

**雙向錨定**：沿用 Pass 176 設計，複用 `BidirectionalBarAlignmentNode` /
`TwoWayAnchorBacktraceNode`。

**門檻參數外部化**：`CONFIRM_RATIO_THRESHOLD`、`WINDOW_SEC`、
`CONFIRM_TOLERANCE_SEC`、`energy_threshold` 等，不寫死在
`GapReinforcementNode` 程式碼裡，改讀一個設定檔（例如
`pgm_craft/config/gap_reinforcement_thresholds.json`），供 1.3 節的校準腳本
更新。

**診斷輸出相容審查工具格式**：`GapReinforcementNode` 執行時，把自己判斷「哪些
區段信心不足、疊加到第幾輪、疊加後信心多少」的過程，寫成跟現有
`blocks.json`（`{id, start, end, needs_review}`）/ `beats.json`
（`{tempo, beats}`）一樣的格式，存進**這首歌自己的專案資料夾**（例如
`reports/gap_reinforcement/blocks.json`）——這樣任何一次正式生產的輸出，都能
直接餵給審查工具，不需要额外轉換或依賴 scratch 腳本重跑。

**品質守門**：複用 `pgm_craft/golden_benchmark.py` 既有比較工具，補強結果沒有
比原始 `BeatFusionArbitratorNode` 輸出更好，就退回原本結果，不冒然採用。

### 1.2 校準迴圈（人工在場，隨選，不影響生產）

`scratch/gap_review_server.py`（或正式化後搬到 `pgm_craft/` 底下的對應位置）
擴充 `discover_lanes()`，除了現有的 scratch `lanes/` 資料夾掃描，**新增一種
Lane 來源**：直接指向任一首歌專案資料夾下 `reports/gap_reinforcement/` 的正式
生產診斷輸出——不需要跑任何 scratch 腳本，格式已經相容（見 1.1）。

**標記結果存回同一個專案**：`marks.json` 存在該專案自己的
`reports/gap_reinforcement/marks.json`（比照現有 `reports/gap_review_marks.json`
的路徑慣例），變成這首歌審查歷史的一部分。

**否決傳遞規則沿用**：Pass 177 驗證過的往前/往後雙向傳遞、`fail`/`fail_phase`
子分類，原封不動沿用——這套邏輯是跟資料格式綁定，不是跟 scratch 腳本綁定，
換成正式生產輸出一樣適用。

### 1.3 校準腳本（獨立、離線、需人工確認才生效）

新增 `scripts/calibrate_gap_reinforcement_thresholds.py`：

1. 掃描所有已經複核過的專案（每個專案自己 `reports/gap_reinforcement/` 底下的
   `blocks.json` + `marks.json` 配對）。
2. 對每個門檻參數，計算：
   - **假陽性率**：`needs_review=False`（信心機制判定沒問題）但被人工標記
     `fail`/`fail_phase` 的比例——代表門檻太寬鬆。
   - **假陰性率**：`needs_review=True`（信心機制判定可疑）但被人工標記
     `pass` 的比例——代表門檻太保守，浪費人工聽的時間。
3. 輸出調整建議（不自動套用），人工確認後才手動（或用腳本的 `--apply` 旗標
   明確觸發）寫回 1.1 節的門檻設定檔。
4. 套用新門檻後，跑一次 `golden_benchmark` 回歸比對，確認整體沒有退步，才視為
   正式生效，供下一批生產使用。

---

## 2. 驗證方式

1. **單元測試（合成資料）**：沿用 Pass 176 規劃——合成三段式音訊（鼓能量正常
   → 低能量缺口 → 鼓能量恢復），缺口內埋入已知貝斯/和弦節奏，驗證
   `GapReinforcementNode` 逐輪疊加能正確重建，相位修正輪能正確標出第 1 拍，
   「都沒證據」時安全退回現狀。
2. **格式相容性測試**：`GapReinforcementNode` 的診斷輸出，直接餵給
   `gap_review_server.py` 的 `discover_lanes()`，驗證不需要任何轉換就能載入
   顯示、標記、送出報告。
3. **校準腳本單元測試**：用一組已知答案的合成 `blocks.json` + `marks.json`
   （例如手動構造 3 個假陽性、2 個假陰性），驗證腳本算出的假陽性/假陰性率
   跟手算答案一致。
4. **黃金基準回歸（真實資料，貴）**：`target_stage="module3"` 完整跑一次，比對
   修好前後的品質分數與症狀 1/2（前奏對齊、無鼓段相位漂移）是否改善，且沒有
   在其他段落造成退步。這一步排在單元測試、格式相容性測試都過了之後才做。

---

## 3. 待確認的實作細節（實作前需要再對齊）

1. **相位修正輪重用哪個既有節點**：需要確認 `DownbeatRefinementNode` 能不能
   直接對「一小段缺口區間」單獨呼叫，還是設計上假設吃全曲——如果只能吃全曲，
   要嘛包一層只餵缺口區間的資料，要嘛評估改用
   `beat_precision_diagnostics` 裡更底層的 `kick_anchor_snap_report`/
   `phase_realignment_report` 邏輯直接重用。
2. **完整混音重分析輪的效能成本**：這一輪拿 `stems/no_vocals.wav` 整段（不是
   分軌）重新分析，如果缺口很多、很分散，逐一對每個缺口切片重複載入分析可能
   有效能成本，需要評估是否要一次載入整份無人聲混音、缺口間共用。
3. **校準腳本「多少首歌才算夠」**：避免用 1-2 首歌的標記結果就調整門檻、過度
   擬合單一首歌的特性，需要定一個最低樣本數門檻（例如至少 5 首歌、至少 N 個
   標記過的區塊）才產生調整建議。
4. **V1 legacy 跟 V3 的關係**：V3 上線後，V1 原本的行為是否保留成備援（比照
   BarStart v2 現在「比較但不升格」的做法），還是直接變成新的預設路徑——需要
   跟 `evaluate_barstart_v2_completeness()` 現有的升格閘門模式對齊，不要有兩套
   不一致的升格邏輯並存。**（本節第 4 點在真實回歸測試後有了明確答案：見第 4
   節，V3 目前保留成預設關閉的備援，跟 BarStart v2 用同一套保守原則。）**

---

## 4. 真實資料 A/B 回歸測試結果（《World is Mine》）與後續處理

### 4.1 測試方法

在同一份真實來源音訊（ryo「World is Mine」，`target_stage="module3"`，
`user_meter_selection="4/4"`）上跑兩次完整管線：

- **處理組**（`scratch/run_pass178_gap_reinforcement_regression.py`）：
  `GapReinforcementNode` 啟用。
- **對照組**（`scratch/run_pass178_control_no_reinforcement.py`）：
  `GapReinforcementNode` 停用，其餘管線完全相同。

兩次都是各自獨立重新跑 Demucs 分離（htdemucs_ft ×3 + htdemucs_6s ×1）——原本
以為可以用既有分離結果的目錄 junction 跳過重新分離，實測發現分離節點的快取是
用音訊內容雜湊（`cache/`）鍵值，不是看 `stems/` 資料夾是否已有檔案，所以 junction
沒有跳過 Demucs。這對 A/B 比較反而更嚴謹（兩組都是從頭跑），可重現性則依賴
Pass 174 `reseed_for_inference()` 的 Demucs 決定性修正。

### 4.2 結果

| 指標 | 黃金基準 | 處理組（啟用） | 對照組（停用） |
|---|---|---|---|
| 小節數 | 121 | 109（差 -12） | 117（差 -4） |
| 總長度 | 175.69s | 169.69s（差 -6.01s） | 172.40s（差 -3.30s） |
| BPM 跳動次數 | 0 | 6（差 +6） | 0（差 +0） |
| 不規則小節數 | 0 | 1（差 +1） | 0（差 +0） |
| 執行耗時 | - | 1650.6s | 1097.3s |

處理組的節點自身日誌顯示：`[GapReinforcementNode] 缺口強化：7 段，已採用。`——
也就是說，節點內部的品質守門（比對缺口區段內補強前後的音頭確認比例）認為這 7
段都值得採用，但套用到完整管線後，整體結果在每一項指標上都比黃金基準、也比
完全不跑這個節點的對照組更差。

### 4.3 根因分析

節點目前的品質守門（`_is_improvement`）只檢查**缺口區段自己局部**的音頭確認
比例有沒有提升，沒有檢查補強出來的拍點跟缺口前後「已經確信」的網格節奏是否
連貫。局部看起來合理的補強，接回整體網格時可能引入節奏不連貫——這正是 BPM
跳動從 0 次變成 6 次的原因。這一塊本來就是 Pass 176 原始設計（見第 0.1 節）
規劃要做的「用 `BidirectionalBarAlignmentNode` / `TwoWayAnchorBacktraceNode`
做雙向錨定」，但 Pass 178 實作時只做了局部標籤延續（`_relabel()`），沒有真正
做跨邊界的節奏連貫性驗證——設計文件跟實作之間的落差，直到真實資料測試才暴露
出來。

### 4.4 處理方式

`GapReinforcementNode.__init__` 新增 `enabled: bool = False` 參數，預設關閉。
關閉時 `execute()` 直接回傳 `NodeStatus.SUCCESS`，並在黑板寫入
`{"status": "DISABLED_PENDING_VALIDATION"}`，不修改 `beats`。
`build_beat_refinement_nodes()` 呼叫端保持節點掛在管線裡（診斷輸出、校準迴圈
基礎設施持續可用），但預設不執行實際的缺口強化，直到補上跟周邊網格的連貫性
檢查、重新驗證過為止。這跟這個專案對 BarStart v2 既有的「比較但不升格」原則
一致——不因為節點裝進去了就假設它有幫助。

校準/複核流程要繼續測試這個節點時，明確傳入 `enabled=True`。

### 4.5 尚未完成的後續工作

- 設計並實作缺口補強跟周邊「已確信」網格的節奏連貫性檢查（重用
  `BidirectionalBarAlignmentNode` / `TwoWayAnchorBacktraceNode`），這是重新
  啟用這個節點前的前提。
- 累積更多首歌的真人複核校準資料（目前只有這一首歌有真實複核紀錄）。
- 長期的「V1 legacy vs V3 預設」升格機制設計（類比
  `evaluate_barstart_v2_completeness()`），目前只是暫時用 `enabled=False`
  擋住，還沒有正式的升格閘門。
