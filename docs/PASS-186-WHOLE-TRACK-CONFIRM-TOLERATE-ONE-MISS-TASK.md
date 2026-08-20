# Pass 186 任務書：Pass 182 整軌確認「全有全無」太嚴格，允許少量擊點不匹配

**狀態**：已實作，單元測試與真實資料候選層級驗證皆已通過（見第 4 節）。
真實音訊完整管線回歸（評估對 `irregular_measure_count` 的實際影響）進行中。

---

## 0. 背景：Pass 185 驗證時發現的精確根因

Pass 185（`beat_phase_protected_ranges` 保護機制）實作、測試、真實資料
完整管線回歸後，發現 18-20 秒的重音位置**仍然沒有修正**——追查後確認
**不是 Pass 185 保護機制失效**，而是候選在更早的階段就被 Pass 182 的
「整軌能量確認」機制拒絕掉了，保護機制根本沒有機會生效。

### 0.1 精確重現

用這次真實管線回歸留下的資料（`outputs/pass185_default_pipeline_reverify/
【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】/`，若目錄還在）：

```python
from pgm_craft.workflow.beat_tracking_bt import SteadyPercussionCountAnchorNode
import numpy as np

node = SteadyPercussionCountAnchorNode()
base = r'<專案目錄>\stems\drums'

whole_onsets = node._detect_onsets(f'{base}/drums.wav')
hihat_onsets = [18.563, 18.934, 19.294, 19.642, 20.014]  # SteadyPercussionCountAnchorNode
                                                            # 對 hihat_cymbals.wav 找到的候選
whole_arr = np.array(whole_onsets)
for t in hihat_onsets:
    diff = np.min(np.abs(whole_arr - t))
    print(f'{t:.3f}  整軌最近距離={diff:.3f}s')
```

實測結果：

```
18.563  整軌最近距離=0.000s
18.934  整軌最近距離=0.360s   <-- 唯一沒對上的一個
19.294  整軌最近距離=0.000s
19.642  整軌最近距離=0.000s
20.014  整軌最近距離=0.000s
```

五個裡面四個跟整個鼓軌（`drums.wav`）的偵測結果完全對上（誤差 0.000 秒），
只有 **18.934 秒這一個**整軌完全沒有偵測到對應的擊點（最近距離 0.36 秒，
幾乎是一整拍）。

### 0.2 根因

`SteadyPercussionCountAnchorNode._confirmed_by_whole_track()`（Pass 182）
目前的邏輯是「這段候選裡**每一個**擊點都要在整軌裡找到對應能量（容差
`whole_track_confirm_tolerance_sec`，預設 0.04 秒），只要有一個沒對上，
整段候選就整批判定 `REJECTED_NO_WHOLE_TRACK_ENERGY`」：

```python
def _confirmed_by_whole_track(self, run: dict, whole_drum_onsets: list) -> bool:
    whole_arr = np.asarray(whole_drum_onsets, dtype=float)
    if len(whole_arr) == 0:
        return False
    for t in run["onsets"]:
        if np.min(np.abs(whole_arr - t)) > self.whole_track_confirm_tolerance_sec:
            return False
    return True
```

這個「全有全無」的判斷太嚴格——整個鼓軌是多樂器疊加的訊號，onset 偵測
（即使用了 Pass 184 修好的滑動視窗分段分析）本來就有可能在某個時間點被
其他同時發生的聲音蓋掉、沒抓到獨立的峰值，不代表這個時間點真的沒有對應
的鼓聲能量。這正是 Pass 182 當初設計這個確認機制時，比原本規劃更寬鬆的
「檢查有沒有 onset 能量」而不是「整軌也要一樣乾淨」的同一個精神——現在的
「全有全無」實作沒有貫徹這個精神。

---

## 1. 修法

`_confirmed_by_whole_track()` 改成允許少量擊點沒對上，不是全有全無：

```python
def __init__(
    self,
    ...
    whole_track_confirm_tolerance_sec: float = 0.04,
    max_unconfirmed_onsets: int = 1,
    ...
):
    ...
    self.max_unconfirmed_onsets = max_unconfirmed_onsets

def _confirmed_by_whole_track(self, run: dict, whole_drum_onsets: list) -> bool:
    """細分軌候選的擊點，大多數都要在整軌裡找到對應能量（容差
    whole_track_confirm_tolerance_sec）——允許最多 max_unconfirmed_onsets
    個沒對上（Pass 186：整軌是多樂器疊加訊號，onset 偵測本來就可能在少數
    時間點被同時發生的其他聲音蓋掉，「全有全無」的判斷太嚴格，會把大多數
    擊點都乾淨對應、只有一兩個沒抓到獨立峰值的真實案例也一起拒絕掉）。"""
    whole_arr = np.asarray(whole_drum_onsets, dtype=float)
    if len(whole_arr) == 0:
        return False
    unconfirmed = sum(
        1 for t in run["onsets"]
        if np.min(np.abs(whole_arr - t)) > self.whole_track_confirm_tolerance_sec
    )
    return unconfirmed <= self.max_unconfirmed_onsets
```

`max_unconfirmed_onsets` 預設 1（不是比例，是絕對數量）——`min_run_length`
預設也是 4，用絕對數量在候選段長度不同時行為比較可預期、容易理解，不用
另外決定比例門檻要抓多少。

---

## 2. 驗證計畫

1. **合成測試（保留既有行為）**：Pass 182 既有測試場景（全部擊點都對上、
   或全部/大多數都沒對上）維持既有的通過/拒絕結果不變。
2. **合成測試（新行為：允許 1 個沒對上）**：合成一個 5 擊點候選，其中 1 個
   故意讓整軌沒有對應能量、其餘 4 個都有，驗證這次會被接受（不再整批拒絕）。
3. **合成測試（超過門檻還是要拒絕）**：合成一個候選，2 個以上擊點整軌都
   沒有對應能量，驗證依然被拒絕——不能因為放寬就完全不設限。
4. **真實資料回歸**：用 0.1 節的真實資料（真實 hi-hat 18.563-20.014 候選、
   整軌偵測結果），驗證這次 `_confirmed_by_whole_track` 回傳 `True`，這個
   候選能進到 `applied` 清單。
5. **既有回歸測試全跑一次**：確認沒有破壞既有行為（`test_commercial_beat_
   quality`、`test_sdd_pass23/28/42/87/102/103/104/120/121/124/141/144/
   178/179/180/181/182/183/184/185`、`test_module3_bt`）。
6. **實際影響評估（重要，不能省略）**：這次任務書的動機是解決 18-20 秒
   沒對到的問題，修好後要重新核對：
   - 用 `SteadyPercussionCountAnchorNode` 直接對真實 stems 重跑一次（不用
     整條管線），確認 18.563-20.014 這段候選這次真的進到 `applied`，且
     `beat_phase_protected_ranges` 有正確涵蓋這段。
   - Pass 185 真實跑法發現 `irregular_measure_count` 從 1 跳到 12（34 個
     保護區段造成的接縫副作用）——這次放寬確認門檻後，候選數量可能增加，
     要一併觀察這個數字是變好、變壞、還是不變，誠實記錄，不要只看
     18-20 秒這一個指標。
   - 如果情況允許（使用者同意），跑一次真實音訊完整管線回歸
     （`scratch/run_pass184_default_pipeline_reverify.py` 或
     `scratch/run_pass185_default_pipeline_reverify.py` 的同款腳本，複製
     一份改路徑），確認 18-20 秒這次真的對齊，且 `irregular_measure_count`
     沒有惡化。

---

## 3. 範圍界定

- 只調整 `_confirmed_by_whole_track` 的判斷邏輯（全有全無 → 允許少量不
  匹配），不動 Pass 182 其餘設計（`_dedupe_overlaps`、`drum_only_runs` 邏輯
  不變）。
- 不處理 Pass 185 發現的「12 個不規則小節」副作用——第 2 節第 6 點要求
  觀察並誠實記錄這次修改對這個數字的影響，但**不在這次任務內主動修正**
  接縫平滑化問題（那是 Pass 185 任務書裡已經明確記錄、故意延後的設計
  取捨，需要另外評估要不要處理）。
- 不修改 `KickSnarePulseNode`（Pass 183，同樣有整軌確認機制，但那邊沒有
  觀察到這次的「全有全無太嚴格」問題，先不動）。

---

## 4. 實作結果

### 4.1 修改內容

`SteadyPercussionCountAnchorNode.__init__` 新增 `max_unconfirmed_onsets: int
= 1`；`_confirmed_by_whole_track()` 改成計算候選段裡有幾個擊點整軌對不上
（`unconfirmed`），只要 `unconfirmed <= self.max_unconfirmed_onsets` 就算
通過，不再要求全部擊點都要對上。

### 4.2 測試結果

新增 `tests/test_sdd_pass186.py`（4 項全過）：全部擊點都對上維持既有行為、
只有 1 個沒對上這次改成通過、2 個以上沒對上依然拒絕、真實案例回歸（節錄
《World is Mine》18.563s-20.014s 五連拍，四個對上一個沒對上）。

既有回歸測試（`C:/Python313/python.exe`）：`test_commercial_beat_quality`、
`test_sdd_pass23/28/42/87/102/103/104/120/121/124/141/144/178/179/180/
181/182/183/184/185`、`test_module3_bt`，加上新增的 `test_sdd_pass186`，
共 117 項全數通過。

### 4.3 真實資料候選層級驗證

直接對真實 `beats`（從 Pass 185 真實跑法留下的 `measure_map.json` 還原）
重跑 `SteadyPercussionCountAnchorNode`：

- 18.563s-20.014s 這段 hi-hat 候選這次**正確進到 `applied` 清單**（修復
  前是 `REJECTED_NO_WHOLE_TRACK_ENERGY`）。
- 對應到的拍點標號正確變成 `1, 2, 3, 4, 1`（原本被拒絕、由其他更早的錨點
  續接過來的結果是 `2, 3, 4, 1, 2`）。
- 這次總共找到 37 段候選（Pass 185 真實跑法是 34 段，Pass 182/183 累積
  修復後最初是 31 段）、只剩 2 段仍被拒絕——確認放寬門檻後大多數之前被
  誤拒的候選現在能正確通過。

### 4.4 尚未完成

第 2 節第 6 點要求的「實際影響評估」——這次放寬確認門檻後，候選數量從
34 增加到 37（+3），保護區段變多，理論上交界處接縫也可能變多，需要重跑
一次真實音訊完整管線，確認 `irregular_measure_count`（Pass 185 真實跑法
是 12）這次是變好、變壞、還是不變，誠實記錄。正在執行中。
