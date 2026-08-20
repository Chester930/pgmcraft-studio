# Pass 246 任務書：madmom hybrid 輸出套用既有的聲學瞬態微調（重用
`MicroTimingTransientSnapNode`，不是新機制）

**狀態**：設計已定案（跟使用者討論確認過方向），根因鏈已完整
（Pass236→245），可直接轉交 Codex CLI 執行。**這是重用既有、已經在
legacy pipeline 跑很久的節點，套用到 madmom hybrid 的最終輸出上，
不是發明新的追蹤演算法。**

---

## 0. 背景：為什麼要做這件事

Pass245（只查證，未修改任何程式碼）發現：使用者用DAW等級耳朵聽過
Pass244版本後回報「前奏快結束時的漸慢、bass或吉他solo的間奏，拍子
不太一樣，沒有微調；不過鼓進來後可以快速對上」。查證後定位到兩段
低鼓聲密度區（用`SteadyPercussionCountAnchorNode._detect_onsets`
獨立驗證）：

- **5.5-20.0秒**（前奏中後段，14.5秒內鼓組onset密度接近0）
- **100.5-106.0秒**（落在系統標記的Chorus1範圍內，5.5秒內鼓聲密度
  掉到0，可能是被自動分段誤併入Chorus1的間奏/solo段落）

**逐點核對這兩段的降拍（小節第一拍）準確度：完全正常**（13-41
毫秒，跟其他段落一樣準）——**問題不在選錯小節，在小節內部的第
2、3、4拍**：golden在這兩段的beat-to-beat間距明顯不均勻（例如某
小節四拍間距0.33/0.37/0.50秒，起伏近50%，真實表情性彈性節奏），
但madmom自己追蹤出來的beat間距幾乎等分（同一批小節只有0.36/0.37/
0.36秒左右的微小變化）——**madmom的DBN模型本身帶有很強的「拍子要
規律」先驗假設，會把真實存在的彈性節奏拉平磨平**，即使該段仍有
稀疏的真實鼓點提示（使用者原話：「雖然漸慢，但還是有鼓的提示
拍點」）。

**使用者確認的修法方向**：不需要發明新機制，直接重用專案裡已經
存在、已經驗證過、目前只套用在**legacy v1**網格上的
`MicroTimingTransientSnapNode`（`pgm_craft/workflow/beat_tracking_bt.py:2763`），
套用到**madmom hybrid的最終輸出**上。

---

## 1. `MicroTimingTransientSnapNode` 做什麼（已存在的機制，不用重寫）

```python
class MicroTimingTransientSnapNode(BaseNode):
    """對每一拍，在AI推算位置 ±35ms 視窗內搜尋鼓組波形的真實聲學
    瞬態peak，把拍點磁吸過去；視窗內沒有明顯訊號就維持原樣。避開
    已知的鼓過門/切分音排除區（snap_exclusion_zones/drum_fill_regions，
    這兩份資料在pipeline更早階段就已經算好，讀得到不用重算）。"""
```

`required_keys = ["beats"]`；讀取 `stems["drums"]`（或
`extracted_stems["drums"]`，找不到才退回 `y`/`audio_path`）算波形
包絡（`np.abs(audio)`），逐拍在 ±35ms 視窗內找 `np.argmax` 當真實
peak，寫回 `refined_beats`/`beats`，並記錄 `snap_offsets_ms`/
`snap_skip_report`（跳過幾個過門/切分區）。目前只在 legacy Stage 3
pipeline 裡跑一次（跑在 BarStart V2/madmom hybrid 之前的原始 v1
網格上），madmom hybrid 從沒用過它。

---

## 2. 設計核心：在 `MadmomPrimarySegmentSpliceNode` 收尾時多呼叫一次

**明確要求：不要修改 `MicroTimingTransientSnapNode` 本體**（它已經
在 legacy pipeline 穩定跑很久，任何改動都可能影響現有行為，不在
本任務書範圍內）。只需要在
`pgm_craft/workflow/madmom_hybrid.py::MadmomPrimarySegmentSpliceNode.execute()`
裡，**在 `final_grid`（弱區段拼接 + Pass244尾聲外推都處理完之後）
寫入 `blackboard.set_val("beats", final_grid)` 之後**，額外呼叫一次
`MicroTimingTransientSnapNode().execute(blackboard)`，讓它讀
madmom hybrid 剛寫入的 `beats`，用同一套±35ms磁吸邏輯精修，再把
它產出的 `refined_beats` 寫回 `blackboard.set_val("beats", ...)`／
`blackboard.set_val("refined_beats", ...)`（覆蓋掉沒精修過的版本）。

**明確要求：這一步只能在 `madmom_hybrid_approved=True` 這個既有
opt-in旗標成立時才執行**（`MadmomPrimarySegmentSpliceNode.execute()`
一開始就有 `if not approved: return` 的判斷，這次的呼叫要放在那個
判斷之後，天然只在hybrid啟用時生效）——**不能把
`MicroTimingTransientSnapNode` 加成`build_module3_pipeline_tree()`
裡一個獨立、無條件執行的新節點**，那樣會在`madmom_hybrid_approved`
沒開的預設情況下，對現有v1/V2網格重複套用第二次微調，改變現有
預設行為，超出範圍。

新增一個獨立的opt-in旗標（沿用Pass236-244一路建立的細粒度旗標
慣例）：`madmom_hybrid_micro_timing_snap_enabled`，預設值跟隨
`madmom_hybrid_approved`（也就是hybrid本身啟用時，這個微調預設
一起啟用），但允許使用者/Codex在驗證時獨立關掉，方便A/B比較有沒有
這一步的差異。

`madmom_hybrid_report` 要透明記錄這一步的結果（沿用這個模組一貫的
透明度要求）：新增欄位 `micro_timing_snap_report`，內容至少包含
`MicroTimingTransientSnapNode` 自己產出的 `snap_offsets_ms`（統計
摘要即可，例如平均絕對偏移、觸發次數）跟 `snap_skip_report`。

---

## 3. 驗證流程

### 3.1 離線驗證（先做，便宜快速）

用已有的 `_run_madmom_dbn` + 這首歌快取的 `outputs/pass237_madmom_hybrid_production_verify/.../stems/drums/drums.wav`，
針對 Pass245 標出的兩段（5.5-20.0秒、100.5-106.0秒），手動構造幾個
「AI推算拍點在附近有真實鼓點提示、但沒對齊」的案例，直接呼叫
`MicroTimingTransientSnapNode().execute()`，確認：

1. 附近±35ms內確實有真實鼓聲的拍點，會被正確磁吸過去（offset不為0）。
2. 附近完全沒有訊號的拍點（真的無鼓的段落，Pass243找到的
   168.5-176.5s那種），維持原位不動或只有可忽略的微小偏移（這個
   節點沒有振幅門檻，理論上會磁吸到雜訊底噪的局部最大值，如果
   離線測試發現這造成不合理的亂跳，回報給使用者/Claude決定要不要
   額外加振幅門檻——但不要自己決定要不要改動`MicroTimingTransientSnapNode`
   本體，先回報）。

### 3.2 真實資料驗證（離線驗證通過後才做）

用 `scratch/run_pass237_madmom_hybrid_production_verify.py`（可能
需要小幅修改以印出/儲存 micro_timing_snap 相關的統計數字，比照
既有其他欄位的印法）跑一次完整pipeline（`madmom_hybrid_approved=True`）：

1. **逐拍（不只降拍）跟golden比對**：golden的 `measure_map.json`
   每個小節都有完整4拍的時間（`m["beats"]`），這次驗證的重點是
   beat-to-beat間距，不能只看降拍——延伸 Pass245 用過的方法，針對
   5.5-20.0秒跟100.5-106.0秒這兩段，逐一比較golden的beat 2/3/4
   時間 vs 套用micro-timing snap前後的候選時間，確認套用之後這兩段
   的beat-level平均誤差有實質改善（不是只看降拍分數，降拍分數
   預期不會有明顯變化）。
2. **安全底線（最重要）**：確認Intro/Verse1/Chorus1/Outro的降拍
   準確度沒有退步（維持Pass239/242/244已驗證的數字量級：Intro
   18/18、Verse1 43/43、Chorus1 43/43、Outro 10/20附近），套用
   micro-timing snap不能讓已經準的降拍被磁吸偏移到錯誤的鄰近瞬態
   上——如果發現這種退步，要回報，不能為了呈現「這次成功了」而
   忽略。
3. 確認 `snap_skip_report` 有正確避開已知的過門/切分區（跟legacy
   pipeline原本的行為一致），沒有意外把這些區域也磁吸掉。

---

## 4. 測試要求

新增 `tests/test_sdd_pass246.py`：

1. 合成案例：構造一組 madmom-style beats（4拍等分）+ 一份合成的
   drums波形，波形裡在某一拍附近±20ms處放一個明顯的peak（模擬真實
   鼓點提示），確認套用後那一拍被正確磁吸過去；波形裡完全沒有peak
   的另一拍，確認維持原位（或至少不大幅偏移）。
2. 驗證 `madmom_hybrid_micro_timing_snap_enabled=False` 時完全不
   套用這一步，`beats`維持`MadmomPrimarySegmentSpliceNode`原本的
   輸出不變（跟開啟時的結果不同）。
3. 驗證 `madmom_hybrid_approved=False`（整個hybrid沒啟用）時，
   micro-timing snap同樣不會被觸發（沿用既有opt-in測試模式，比照
   `test_node_is_strictly_opt_in_and_preserves_default_grid`）。
4. 執行既有回歸測試確認沒有破壞其他機制：
   ```
   C:/Python313/python.exe -m pytest tests/test_sdd_pass246.py tests/test_sdd_pass236.py tests/test_sdd_pass202.py tests/test_module3_bt.py -q
   ```

---

## 5. 明確排除（範圍收斂，避免任務蔓延）

- **不要修改 `MicroTimingTransientSnapNode` 本體**——只是多呼叫
  一次，不是重新設計它。如果離線驗證發現它在真空段落有亂跳問題，
  先回報給使用者/Claude決定要不要另開任務處理，不要自己順手改。
- **不要把貝斯分軌加進搜尋來源**——這次範圍明確只用既有節點原本
  就在用的鼓組分軌（跟使用者討論時已經確認：先做鼓組版本，如果
  貝斯主導的段落還是沒改善，再考慮是否要另開任務加貝斯搜尋）。
- **不要把這個機制設成任何呼叫端的預設行為**——`madmom_hybrid_approved`
  跟新增的 `madmom_hybrid_micro_timing_snap_enabled` 都要維持opt-in，
  需要使用者另外核准才能變成正式預設輸出。
- **不要嘗試修 Pass241/243 已經定案的深層問題**（V2仲裁自我參照
  缺陷、真的沒有節奏證據的段落）——那些是不同範圍、不同性質的
  問題，這次任務書只處理「有稀疏鼓點提示但被madmom拉太規律」這個
  特定的新維度。
- **不要在其他曲目做量化驗證**（沒有其他曲目的golden基準，範圍
  留給之後）。

---

## 6. 完成後

1. 更新 `docs/BT-BUILD-PROGRESS.md`，新增Pass246條目：完整記錄
   離線驗證結果、真實pipeline驗證的逐拍（不只降拍）比對數字、
   Intro/Verse1/Chorus1/Outro降拍準確度有沒有維持（安全底線）、
   兩段目標區段的beat-level誤差有沒有實質改善。
2. 更新使用者記憶檔案（如果是Claude執行）。
3. Commit + push 到 `origin/worktree-pass171-multi-variant-harness`，
   commit message 用 `feat(pass246): ...` 前綴。
