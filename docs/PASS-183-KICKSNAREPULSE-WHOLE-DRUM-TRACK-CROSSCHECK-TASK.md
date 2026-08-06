# Pass 183 任務書：`KickSnarePulseNode` 補上整個鼓軌交叉確認

**狀態**：已實作，單元測試與既有回歸測試皆已通過，見第 4 節。
**目標**：Pass 182 只修了 `SteadyPercussionCountAnchorNode` 一個節點，使用者
同意順便處理其他有同樣架構缺口的節點。`KickSnarePulseNode` 是影響範圍最大
的一個——它產出的 `kick_anchors`/`snare_anchors` 被
`ReEntryReAnchoringNode`、`DownbeatPhaseConsistencyNode`、
`KickAnchorConsensusSnapNode`、`DrumFillDetectionNode` 等一整串下游節點
共用，卻完全只看細分軌（`kick.wav`/`snare.wav`），從未回頭比對整個鼓軌。

---

## 0. 範圍決定：這次只做 `KickSnarePulseNode`，不動 `DrumFillDetectionNode`

- `KickSnarePulseNode`：影響範圍最大（一整串下游節點的共同輸入），錯誤代價
  最高（直接決定「哪裡有鼓聲」），優先處理。
- `DrumFillDetectionNode`：用途是排除過門區段，錯誤代價較小（頂多某段該修
  的拍點被保守跳過，不是「弄錯第一拍位置」這種直接錯誤）；而且已經有部分
  整軌備援機制（kick/snare 都全空才退回整軌），現在改動優先順序風險較高、
  效益較低，這次不動。

---

## 1. 設計

### 1.1 核心改動

在 `KickSnarePulseNode.execute()` 裡，kick/snare 細分軌抽取完成、**在
「無鼓區間 Sub-Bass 補充」邏輯之前**，插入一段整個鼓軌交叉確認：

1. 解析整個 `drums.wav`（`stems["drums"]` 或 `stems_dir/drums/drums.wav`）。
2. 沒有這個檔案時完全跳過確認（向後相容既有行為與既有測試——多數既有測試
   只提供 kick.wav，沒有整軌）。
3. 有的話，用**同一套** `_extract_peak_anchors`（跟 kick/snare 用的方法一致，
   不引入新的偵測方法——這個節點本身的擷取方式對 kick/snare 這種夠「尖峰」
   的樂器已經夠用，不是 Pass 181 那種 hi-hat 才會踩到的坑）對整個鼓軌抽取
   一次候選峰值時間。
4. 對 `kick_anchors`/`snare_anchors` 逐一檢查：整軌候選裡有沒有落在容差
   （放寬到 0.15 秒，因為 `_extract_peak_anchors` 窗口法本身時間精度較粗，
   跟 Pass 182 hi-hat 用的 onset 偵測精度不同）內的對應點，沒有對應的視為
   分離殘留假訊號，濾掉。

### 1.2 為什麼要放在「Sub-Bass 補充」之前

Sub-Bass 補充邏輯的用途是「無鼓區間用貝斯低頻脈衝補位」——這些補進來的
`kick_anchors` 本來就預期整個鼓軌在那個時間點沒有能量（那正是為什麼要用
貝斯來補）。如果整軌交叉確認放在 Sub-Bass 補充**之後**，這些補位錨點會被
自己的存在理由反向淘汰（無鼓區間 = 整軌沒能量 = 被判定成「假訊號」濾掉），
完全弄反。所以交叉確認只套用在**鼓聲細分軌自己抽取出來**的錨點，Sub-Bass
補充的邏輯跟結果不受影響。

### 1.3 不變動的部分

- `_extract_peak_anchors` 本身邏輯不變。
- Sub-Bass 補充邏輯（貝斯低頻脈衝補位）完全不動，只是接在交叉確認之後。
- `output_keys`（`kick_anchors`/`snare_anchors`）不變，下游節點的介面不需要
  跟著改。

---

## 2. 驗證計畫

1. **既有測試全跑一次**：`tests/test_sdd_pass39/42/129/147/148/150/153.py`、
   `tests/test_module3_bt.py` 裡涉及 `KickSnarePulseNode` 的部分——這些測試
   多數只提供 kick.wav（沒有整軌），交叉確認應該完全跳過，行為必須完全
   不變。
2. **新測試（確認通過）**：kick.wav 有乾淨脈衝，整軌在對應時間也有能量，
   驗證錨點正常保留。
3. **新測試（確認拒絕）**：kick.wav 有乾淨脈衝，但整軌在對應時間完全沒有
   能量（模擬分離殘留假訊號），驗證這個錨點被濾掉。
4. **新測試（Sub-Bass 補位不受影響）**：無鼓區間、kick_anchors 少於 5 個、
   有整軌檔案但整軌在無鼓區間本來就沒能量，驗證 Sub-Bass 補位邏輯依然正常
   把貝斯脈衝加進 `kick_anchors`，不會被交叉確認誤刪。
5. **既有 Stage 3 回歸測試全跑一次**：確認沒有破壞既有行為（
   `test_commercial_beat_quality`、
   `test_sdd_pass23/28/42/87/102/103/104/141/144/178/179/180/181/182`、
   `test_module3_bt`）。

---

## 3. 範圍界定

- `DrumFillDetectionNode` 的架構缺口這次不處理（理由見第 0 節），繼續留在
  分開、還沒排入的後續工作清單。
- 不修改任何消費 `kick_anchors`/`snare_anchors` 的下游節點。

---

## 4. 實作結果

### 4.1 修改內容

`pgm_craft/workflow/beat_tracking_bt.py` 的 `KickSnarePulseNode`：

- 新增 `WHOLE_TRACK_CONFIRM_TOLERANCE_SEC = 0.15`（比 Pass 182 用的 0.04
  秒寬鬆，因為 `_extract_peak_anchors` 窗口最大值法本身時間精度較粗，跟
  Pass 181/182 用的 onset 偵測精度不同）。
- kick/snare 細分軌抽取完成後、Sub-Bass 補充邏輯**之前**，插入：解析整個
  `drums.wav`（`stems["drums"]` 或 `stems_dir/drums/drums.wav`），有的話用
  同一套 `_extract_peak_anchors` 對整軌抽取一次峰值，再用新增的
  `_confirmed_by_whole_track()` 過濾 `kick_anchors`/`snare_anchors`——容差
  內在整軌找不到對應峰值的錨點視為分離殘留假訊號，濾掉。
- 沒有整軌檔案時完全跳過確認（`_confirmed_by_whole_track` 直接回傳原始
  anchors）——向後相容，多數既有測試只提供 kick.wav，行為不受影響。
- **設計上的小差異（相對 Pass 182 明確記錄）**：`_confirmed_by_whole_track`
  在整軌檔案存在但抽取出來的峰值列表是空的（`whole_track_peaks` 為空）時，
  選擇「視為無法確認、原樣保留」而不是比照 Pass 182 那樣直接判定不通過。
  理由：這個節點影響範圍是一整串下游節點的共同輸入，既有測試涵蓋 7 個
  檔案，選擇對這個邊界情況更保守（不做更嚴格判定），降低意外行為改變的
  風險；`_extract_peak_anchors` 的閾值是相對自己音軌最大值算的，真的完全
  抽不到任何峰值代表整軌音檔本身有問題（例如讀取失敗、真的是全靜音），
  這種情況下讓交叉確認整批失效、保留細分軌原始結果，比讓所有錨點都被
  誤判掉更安全。

### 4.2 測試結果

新增 `tests/test_sdd_pass183.py`（4 項全過）：

1. `test_confirmed_kick_anchors_kept_with_matching_whole_track`——整軌有
   對應能量，錨點正常保留。
2. `test_unconfirmed_kick_anchors_dropped_without_whole_track_energy`——
   整軌在對應時間沒有能量（但整軌本身在別處有活動，不是空白音軌），驗證
   錨點被濾掉。
3. `test_no_whole_track_file_skips_confirmation`——沒有 `drums.wav` 時完全
   跳過確認，行為跟修改前一致。
4. `test_sub_bass_guard_not_affected_by_crosscheck`——無鼓區間 Sub-Bass
   補位邏輯正常運作，補進來的貝斯錨點不受交叉確認影響。

既有測試驗證（`C:/Python313/python.exe`）：
- 直接使用 `KickSnarePulseNode` 的既有測試檔案（`test_sdd_pass39/129/147/
  148/150/153.py`，共 29 項）全數通過，確認既有行為（多數場景沒有提供
  `drums.wav`）完全不受影響。
- 既有 Stage 3 回歸測試（`test_commercial_beat_quality`、
  `test_sdd_pass23/28/42/87/102/103/104/141/144/178/179/180/181/182`、
  `test_module3_bt`，加上新增的 `test_sdd_pass183`，共 82 項）全數通過。
