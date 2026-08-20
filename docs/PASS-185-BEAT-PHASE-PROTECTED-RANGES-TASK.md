# Pass 185 任務書：讓下游 5 個節點尊重 `SteadyPercussionCountAnchorNode` 建立的區段相位

**狀態**：已完成實作與測試驗證。
**交接對象**：這份任務書寫給接手實作的 agent（可能是全新 session，沒有這次
調查過程的對話記憶），內容盡量自包含，關鍵發現都附上可重現的驗證指令。

---

## 0. 背景：這個 bug 是怎麼被找到的（完整脈絡）

這是 Pass 178 開始的一連串真實資料回歸測試的延續（詳見
`docs/BT-BUILD-PROGRESS.md` Pass 178-184 條目，以及對應的
`docs/PASS-178-...-TASK.md` 到 `docs/PASS-184-...-TASK.md`）。快速摘要：

1. **Pass 180**：修好 `ViterbiTempoSmoothingNode` 誤刪連續拍點的 bug（全曲
   單一中位數 → 局部滾動中位數）。
2. **Pass 181/182**：新增 `SteadyPercussionCountAnchorNode`——當 kick/snare/
   hi-hat 任一樂器連續打出 ≥4 下貼合全曲拍距的等間隔擊點，代表這段時間
   打擊樂器在明確「數拍子」，用這個當第一拍續接錨點，強制標記這段（含往後
   續接）的 1-2-3-4 循環。放在 `build_beat_refinement_nodes()` 裡
   `DrumFillDetectionNode` 之後、`OnsetPhaseRealignmentNode` 之前。
3. **Pass 183**：`KickSnarePulseNode` 補上整個鼓軌交叉確認，跟這次任務關係
   不大（不同節點）。
4. **Pass 184**：真實資料完整管線回歸（使用者實際聽《World is Mine》)後
   回報兩個問題：0-3 秒 hi-hat 沒對到（後來確認是隔拍/half-time 型態，修好
   後改成同時接受拍距 1x/2x 倍數）、18-20 秒重音位置不對（追查發現是
   `_detect_onsets` 對整首歌一次分析導致安靜段落被稀釋，改成滑動視窗分段
   分析修好）。兩個修法都已經用真實 stem 檔案直接驗證過偵測邏輯本身正確。
5. **這次（Pass 185 起點）**：把 Pass 184 修好的 `SteadyPercussionCountAnchorNode`
   放進**完整管線**（`target_stage="module3"`，`GapReinforcementNode`
   維持預設 `enabled=False`，其餘全預設）重跑一次《World is Mine》，
   使用者實際聽感回報：0-3 秒這次對了，但 **18-20 秒的重音位置還是跟修復前
   一樣、沒有改善**。

## 0.1 追查過程：確認真正原因

比對這次真實跑法輸出的 `reports/measure_map.json`（路徑：
`outputs/pass184_default_pipeline_reverify/【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】/reports/measure_map.json`，
如果這個目錄還在的話；不在也沒關係，下面的重現步驟不依賴它），發現
18-20 秒附近的拍號標記，跟 Pass 183（`SteadyPercussionCountAnchorNode`
修復前）的結果完全一樣——代表 `SteadyPercussionCountAnchorNode` 這次雖然
正確找到了 18.561s-20.012s 這五個乾淨的 hi-hat 擊點（可以用下面 0.2 節的
指令重現驗證），但它建立的相位**沒有存活到最終輸出**。

日誌裡看到 `KickBassDownbeatVerifierNode` 觸發了「成功修正強拍反相」，一開始
以為是唯一元兇。但進一步追查（見 0.3 節的重現實驗）發現：**問題不只一個
節點**。`build_beat_refinement_nodes()`（`pgm_craft/workflow/beat_tracking_bt.py`）
這條鏈路裡，`SteadyPercussionCountAnchorNode` 之後還有好幾個節點，只要
**任何一個**觸發，就會把它辛苦建立的區段相位整條蓋掉。

### 0.2 重現 Pass 184 修復本身確實有效（用真實資料）

```python
from pgm_craft.workflow.beat_tracking_bt import SteadyPercussionCountAnchorNode
node = SteadyPercussionCountAnchorNode()
onsets = node._detect_onsets(r'<某個保留下來的 World is Mine 專案 stems 目錄>\drums\hihat_cymbals.wav')
window = [o for o in onsets if 18 <= o <= 21]
print(window)  # 應該印出接近 [18.563, 18.934, 19.294, 19.642, 20.014] 五個值
```

若找不到留存的真實 stems 目錄，可以參考
`scratch/run_pass184_default_pipeline_reverify.py` 重新跑一次（會重用
`outputs/pass175_current_pipeline_check/.../stems/`，前提是那份專案的
stems 還在）。

### 0.3 重現「下游節點會蓋掉區段相位」（不需要真實音檔，純陣列模擬）

```python
import numpy as np
from pgm_craft.workflow.beat_tracking_bt import BeatGridContinuityRepairNode
from pgm_craft.workflow.nodes import Blackboard

times = list(np.arange(0, 20, 0.36))
del times[45]  # 製造一個缺口，讓節點會補一拍（inserted_count > 0，觸發寫回）
times = np.array(times)
labels = [(i % 4) + 1 for i in range(len(times))]
beats = np.array([[t, l] for t, l in zip(times, labels)], dtype=float)

# 模擬 SteadyPercussionCountAnchorNode 在 idx=10-30 建立跟「從陣列開頭數」
# 不同的區段相位（往後移 1）
beats[10:30, 1] = [((i - 10 + 1) % 4) + 1 for i in range(10, 30)]

bb = Blackboard()
bb.set_val('beats', beats.copy())
node = BeatGridContinuityRepairNode()
node.execute(bb)
after = bb.get_val('beats')

# 比對 idx 8-14 附近，標籤應該維持區段相位，但實測會被蓋回「從頭數」的版本
for t in beats[8:14, 0]:
    idx = int(np.argmin(np.abs(after[:, 0] - t)))
    orig_idx = int(np.argmin(np.abs(beats[:, 0] - t)))
    print(f't={t:.3f}  原本(區段相位)={beats[orig_idx,1]:.0f}  執行後={after[idx,1]:.0f}')
# 實測結果：執行後的標籤變成 1,2,3,4,1,2（從頭數的版本），
# 不是原本的區段相位 1,2,2,3,4,1——確認被蓋掉。
```

---

## 1. 根因：5 個節點共用同一個「全曲統一從陣列開頭編號」的核心函式

`pgm_craft/workflow/beat_tracking_bt.py` 裡的共用函式：

```python
def _relabel_beat_numbers(beats, first_label: int = 1, beats_per_bar: int = 4):
    arr = _coerce_beat_matrix(beats)
    if len(arr) == 0:
        return arr
    first_label = int(np.clip(int(first_label), 1, beats_per_bar))
    relabeled = arr.copy()
    relabeled[:, 1] = ((np.arange(len(relabeled)) + first_label - 1) % beats_per_bar) + 1
    return relabeled
```

這個函式純粹用**陣列索引**（不是拍點本身的相位）跟一個全域 `first_label`
重新編號整條 `beats` 陣列——完全不知道、也不尊重中間某一段可能已經被
`SteadyPercussionCountAnchorNode` 用直接證據（真的打出來的擊點）建立過
的、跟「從頭數」不一樣的相位。

`grep -n "_relabel_beat_numbers(" pgm_craft/workflow/beat_tracking_bt.py`
目前有 5 個呼叫端，都在 `build_beat_refinement_nodes()`
（`SteadyPercussionCountAnchorNode` 之後執行）：

| 呼叫端節點 | 觸發條件（會不會覆蓋掉區段相位） |
|---|---|
| `BeatGridContinuityRepairNode` | 全曲任何地方補拍/移除近重複拍就觸發（`inserted_count` 或 `removed_count` > 0 才寫回，但這在真實歌曲很常見——這次真實跑法就有「補 2 拍」） |
| `TempoOscillationDampingNode` | 全曲任何地方修正一次快慢震盪、且修正後品質分數變好或震盪配對數減少 |
| `DownbeatPhaseConsistencyNode` | 設計上**本來就是**全曲挑一個最佳相位（`_phase_score` 對 4 種 `first_label` 都算一次分數），跟 `sections`/`kick_anchors` 比對，選最高分的套用全曲——這是這個節點的核心職責，不是意外 |
| `KickAnchorConsensusSnapNode` | 吸附 `kick_anchors` 後，若品質分數變好就套用（套用時一樣整條重編號） |
| `KickBassDownbeatVerifierNode` | 不直接呼叫 `_relabel_beat_numbers`，但用類似邏輯：全曲比較 1 號拍跟 3 號拍的低頻能量平均值，反相超過門檻就整條旋轉 2 拍（`fixed_beats[:, 1] = 0` 後只把原本第 3 拍位置設回 1，其餘留給後面的節點——包括上面那幾個會呼叫 `_relabel_beat_numbers` 的——重新規範化） |

`KickBassDownbeatVerifierNode` 在鏈路裡的位置**在** `SteadyPercussionCountAnchorNode`
之後、`BeatGridContinuityRepairNode` 之前（見
`build_beat_refinement_nodes()` 的節點順序），所以它的「反相修正」也會被
後面的 `_relabel_beat_numbers` 呼叫端二次規範化，但問題本質相同：全曲
統一決策，不知道有區段需要保護。

---

## 2. 設計（方案 1：全部 5 個節點都加保護機制）

### 2.1 新增介面：`SteadyPercussionCountAnchorNode` 輸出保護區段清單

在 `SteadyPercussionCountAnchorNode` 的 `output_keys` 新增
`"beat_phase_protected_ranges"`。這個節點 `execute()` 裡，每次
`_apply_anchor()` 成功套用一個錨點時，記錄下這次實際套用的**時間範圍**
（不是只有這段擊點本身的時間範圍，是含往後續接的整段——也就是從
`timestamps[base_idx]` 到這次套用的 `next_start` 或曲末，取實際發生
的那個邊界）。

`_apply_anchor()` 目前簽章：

```python
def _apply_anchor(self, beats: np.ndarray, timestamps: np.ndarray, run: dict, next_start: float):
    ...
    base_idx = snapped_indexes[0]
    for idx in range(base_idx, len(beats)):
        if timestamps[idx] >= next_start:
            break
        step = idx - base_idx
        beats[idx, 1] = (step % 4) + 1
    return beats
```

改成回傳 `(beats, protected_start, protected_end)`（或找不到對應拍點時
回傳 `(None, None, None)`），`protected_end` 用實際跑到的最後一個 idx 的
時間（不是 `next_start` 本身，`next_start` 可能是 `inf`）：

```python
def _apply_anchor(self, beats, timestamps, run, next_start):
    onsets = run["onsets"]
    snapped_indexes = []
    for t in onsets:
        diffs = np.abs(timestamps - t)
        idx = int(np.argmin(diffs))
        if diffs[idx] > self.snap_tolerance_sec:
            return None, None, None
        snapped_indexes.append(idx)

    base_idx = snapped_indexes[0]
    last_touched_idx = base_idx
    for idx in range(base_idx, len(beats)):
        if timestamps[idx] >= next_start:
            break
        step = idx - base_idx
        beats[idx, 1] = (step % 4) + 1
        last_touched_idx = idx
    return beats, timestamps[base_idx], timestamps[last_touched_idx]
```

`execute()` 裡呼叫端要跟著改（目前是
`result = self._apply_anchor(new_beats, timestamps, run, next_start)`），
收集每次成功套用的 `(protected_start, protected_end)`，最後統一寫入
`blackboard.set_val("beat_phase_protected_ranges", protected_ranges)`
（`protected_ranges` 是 `[(start, end), ...]` 的 list；沒有任何候選套用
成功時寫入空 list，不是不寫——讓下游節點的 `optional_keys` 拿到的永遠是
一個明確的值，不用額外判斷 key 存不存在）。

### 2.2 共用 helper：判斷一個時間點是否落在保護區段內

新增模組層級函式（放在 `_window_intersects_exclusion` 附近，風格一致）：

```python
def _time_in_protected_ranges(t: float, protected_ranges) -> bool:
    for start, end in protected_ranges or []:
        if start <= t <= end:
            return True
    return False
```

### 2.3 修改 `_relabel_beat_numbers`：支援保護區段

```python
def _relabel_beat_numbers(beats, first_label: int = 1, beats_per_bar: int = 4, protected_ranges=None):
    arr = _coerce_beat_matrix(beats)
    if len(arr) == 0:
        return arr
    first_label = int(np.clip(int(first_label), 1, beats_per_bar))
    relabeled = arr.copy()
    relabeled[:, 1] = ((np.arange(len(relabeled)) + first_label - 1) % beats_per_bar) + 1
    if protected_ranges:
        for i in range(len(arr)):
            if _time_in_protected_ranges(float(arr[i, 0]), protected_ranges):
                relabeled[i, 1] = arr[i, 1]  # 保護區段內的拍點，標號維持原樣不被覆蓋
    return relabeled
```

**設計取捨（已確認，不用再討論）**：保護區段內外的交界處可能會有相位
不連貫的「接縫」（例如交界前是標號 3，交界後從頭數的序列剛好也接了一個
不是 4 的數字）——這是可接受的，跟這個管線既有的「小節邊界偶爾會有不規則
拍數」現象（例如 Pass 180/183 提到的收尾截斷）同一類，不需要額外做接縫
平滑處理。優先保住區段本身的正確相位，勝過強求全曲每個小節邊界都完美
無縫。

### 2.4 修改 5 個呼叫端

全部呼叫端都要：
1. `optional_keys` 加入 `"beat_phase_protected_ranges"`。
2. `execute()` 開頭讀取 `protected_ranges = blackboard.get_val("beat_phase_protected_ranges", []) or []`。
3. 呼叫 `_relabel_beat_numbers(..., protected_ranges=protected_ranges)`。

逐一節點：

- **`BeatGridContinuityRepairNode`**（約在 `class BeatGridContinuityRepairNode`
  的 `execute()` 裡，`repaired_arr = _relabel_beat_numbers(repaired_arr, first_label=first_label)` 那行）：加上 `protected_ranges=protected_ranges`。
- **`TempoOscillationDampingNode`**（`candidate = _relabel_beat_numbers(candidate, first_label=...)` 那行）：同樣加上。
- **`DownbeatPhaseConsistencyNode`**：這個節點比較特殊，`_phase_score()`
  內部**也**呼叫 `_relabel_beat_numbers`（用來算每個候選 `first_label` 的
  分數）。`_phase_score` 需要多一個 `protected_ranges` 參數並往下傳；
  `execute()` 主流程裡 `relabeled = _relabel_beat_numbers(beats, first_label=best_first, ...)` 那行也要加。這樣做的目的：讓分數評估反映
  「保護區段套用後」的實際結果，不是假設全曲會被完全覆寫的理論分數。
- **`KickAnchorConsensusSnapNode`**：`candidate = _relabel_beat_numbers(candidate, first_label=...)` 那行加上。
- **`KickBassDownbeatVerifierNode`**：這個不呼叫 `_relabel_beat_numbers`，
  要單獨處理：
  1. `optional_keys` 加入 `"beat_phase_protected_ranges"`。
  2. 算 `db_energy`/`beat3_energy`（全曲平均）時，**排除**落在保護區段內
     的 beat index（只用未保護的 index 計算平均值）。
  3. 決定要旋轉時（`beat3_energy > db_energy * 1.35`），套用旋轉的迴圈
     （`for idx in beat3_indices: fixed_beats[idx, 1] = 1`）要跳過保護
     區段內的 index，並且 `fixed_beats[:, 1] = 0` 這一步也要先把保護區段
     內的原始標號存起來，最後蓋回去（不能讓它們被歸零）。

---

## 3. 驗證計畫

1. **合成測試（核心：保護機制生效）**：比照 0.3 節的重現腳本，針對每一個
   修改過的節點各寫一個測試——建立一個帶有 `beat_phase_protected_ranges`
   的 blackboard，觸發該節點原本會整條重編號的條件，驗證保護區段內的
   標號沒有被改變，區段外的正常重編號邏輯不受影響。
2. **合成測試（沒有保護區段時完全不變）**：`beat_phase_protected_ranges`
   為空/不存在時，行為要跟修改前完全一致——這是最重要的向後相容檢查，
   確保沒有破壞任何既有測試。
3. **既有測試全跑一次，一個都不能少**：
   - `tests/test_sdd_pass120.py`、`tests/test_sdd_pass87.py`（`KickBassDownbeatVerifierNode`）
   - `tests/test_sdd_pass121.py`（`BeatGridContinuityRepairNode` + `TempoOscillationDampingNode`）
   - `tests/test_sdd_pass124.py`（`KickAnchorConsensusSnapNode`）
   - `tests/test_commercial_beat_quality.py`（涵蓋這幾個節點的整合行為）
   - `tests/test_module3_bt.py`
   - `tests/test_sdd_pass181/182/183/184.py`（`SteadyPercussionCountAnchorNode`
     系列，因為 `_apply_anchor` 簽章改了，回傳值從單一 `beats` 變成
     `(beats, start, end)`，呼叫端 `execute()` 也要跟著改，這幾個既有測試
     驗證的是最終 `beats`/`report` 內容，簽章改變不應該影響它們的斷言，
     但務必實際跑過確認）
   - 完整 Stage 3 回歸：`test_sdd_pass23/28/42/87/102/103/104/141/144/178/
     179/180/181/182/183/184`，共應該有 85+ 項全過（實作前的既有基準是
     85 項全過，見 `docs/PASS-184-...-TASK.md` 第 5.3 節）。
4. **真實資料驗證（強烈建議，不是必須）**：拿真實 `beats`/`stems` 資料
   跑一次完整 `SteadyPercussionCountAnchorNode` → `KickBassDownbeatVerifierNode`
   → `ViterbiTempoSmoothingNode` → `BeatGridContinuityRepairNode` →
   `TempoOscillationDampingNode` → `DownbeatPhaseConsistencyNode` →
   `KickAnchorConsensusSnapNode` 這條子鏈，確認 18-20 秒的區段相位這次真的
   存活到最後（可以參考 0.1-0.2 節重建驗證環境，或直接跑
   `scratch/run_pass184_default_pipeline_reverify.py` 的同款腳本，複製一份
   改成 Pass 185 版本，全預設設定重跑一次《World is Mine》完整管線）。
5. **真實音訊完整管線回歸（可選，成本較高，需使用者同意才執行）**：
   確認使用者實際試聽後，18-20 秒的重音位置這次真的對了。

---

## 4. 範圍界定

- 只處理 `SteadyPercussionCountAnchorNode` 建立的保護區段。
  `ReEntryReAnchoringNode`（另一個「錨點+續接」機制，在
  `SteadyPercussionCountAnchorNode` 之前執行）目前也會被同一批下游節點
  蓋掉，這是已知的、性質相同的缺口，但不在這次任務範圍內——先把
  `SteadyPercussionCountAnchorNode` 這條路徑走通、驗證方案可行，之後再
  考慮要不要讓 `ReEntryReAnchoringNode` 也貢獻進同一個
  `beat_phase_protected_ranges`（介面設計上已經預留空間：`SteadyPercussionCountAnchorNode`
  寫入前應該先讀取 blackboard 上既有的 `beat_phase_protected_ranges`
  並累加，不要直接覆寫成只有自己的結果——這樣未來要讓
  `ReEntryReAnchoringNode` 也貢獻時，介面不用再改）。
- 不修改 `GapReinforcementNode`（目前 `enabled=False`，不在這條鏈路的
  相位保護範圍內考慮）。
- 交界處的相位不連貫（接縫）不特別處理，見 2.3 節設計取捨。
- 不修改 `module3_barstart_v2_bt.py`（V2 比較鏈）裡任何節點——這次只處理
  V1/Stage 3 正式生產鏈路（`build_beat_refinement_nodes()`）。

---

## 5. 相關檔案

- 主要修改：`pgm_craft/workflow/beat_tracking_bt.py`
  （`_relabel_beat_numbers`、`SteadyPercussionCountAnchorNode`、
  `BeatGridContinuityRepairNode`、`TempoOscillationDampingNode`、
  `DownbeatPhaseConsistencyNode`、`KickAnchorConsensusSnapNode`、
  `KickBassDownbeatVerifierNode`）。
- 新增測試：建議 `tests/test_sdd_pass185.py`。
- 完成後更新：`docs/BT-BUILD-PROGRESS.md`（新增 Pass 185 條目，格式比照
  Pass 180-184 既有條目）、這份任務書本身的狀態欄位。
