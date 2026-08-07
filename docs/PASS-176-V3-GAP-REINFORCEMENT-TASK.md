# Pass 176 任務書：V3 = V1 骨架 + V2 證據疊加的缺口強化 (GapReinforcementNode)

**狀態**：待處理（設計已與使用者確認，尚未實作）
**目標**：不整套替換 V1、也不單獨修 V2，而是把 V2「多層音色累積證據」的觀念，
接到 V1 現有骨架自己已經標記出來的弱點（`track_b_spans`）上，只在這些缺口做
局部強化重建，V1 原本表現良好的段落完全不動。目標是同時解決使用者實測回報的
兩個症狀：

1. 前奏對不上真實 kick（症狀 1）
2. 無鼓段落拍子亂跳（症狀 2）

---

## 0. 背景：為什麼是「V3」而不是「修好 V2」或「修 V1 的內插」

### 0.1 已知事實（Pass 171-175 累積調查結果）

- 這首歌的黃金版（使用者認定最好的一版）跟目前的 `mix_with_click.wav`
  都是 **V1**（`BeatNetNode_TrackA/B → MultiModelBeatEnsembleNode →
  BeatFusionArbitratorNode → ... 精修鏈`）產生的，V2
  （`Module3BarStartV2MergeNode`）從未真正取代過輸出（`COMPARED_NOT_PROMOTED`）。
- Pass 175 修好 `Module3BarStartV2SummaryNode` 那個「組好報告卻忘記寫回黑板」的
  bug 之後，**第一次能看到 V2 在真實歌曲上的診斷資料**：V2 的
  `FullSongBarStartLoopNode` 在這首歌只撐到第 8 小節（10.4 秒）就
  `stalled_no_recovery`，直接放棄剩下 96% 的歌曲，商用品質分數只有 60.18
  （V1 是 78.86）。
- 症狀 1（實測）：真實 kick 打點時間 vs A/B 兩版 beat grid，前 5 小節都有
  40-65ms「grid 比 kick 晚」的現象，**A、B 兩版都有**，第 4-5 小節後收斂到
  <10ms——不是哪個版本特有的退步，是這套追蹤方式在「證據還沒累積夠」時的通性。
- 症狀 2（實測）：B 版第 10-18 小節出現約 0.37 秒（≈1 拍）的累積相位漂移，
  對照發現這段的節奏骨幹軌 RMS 能量偏低（無鼓/鼓聲稀疏），且黃金版在同樣
  「上游拍點計數不乾淨」的情況下，下游修復節點成功修乾淨、B 版沒修乾淨——
  兩邊用的是同一套修復程式碼，差別在於這次的原始候選剛好比較難修。

### 0.2 為什麼不直接修 V2 的控制流程就好

即使把 `FullSongBarStartLoopNode` 的「一次 stall 就放棄全曲」改成更堅韌的重試，
V2 整條路徑（探測窗口、逐小節依序推進、6 層證據 ladder 全部要在同一個 5 秒窗口
內湊齊）仍然是一個**從未在真實資料上驗證過完整跑完全曲**的新系統，修復成本高、
風險未知。而 V1 已經是被使用者認可（黃金版）的成熟骨架，唯一的弱點就是遇到
`track_b_spans`（低節奏能量段落）時只會用「等速內插」頂著，這是一個範圍明確、
局部的弱點，不需要動到 V1 其餘 95% 已經運作良好的部分。

### 0.3 V3 的核心觀念（使用者確認）

> 「V1 骨架 + V2 的證據疊加，只用在 V1 自己已經標記出的弱點」

`BeatFusionArbitratorNode`（`pgm_craft/workflow/beat_tracking_bt.py`）在雙軌融合
時，A 軌（鼓+貝斯節奏骨幹軌）能量低於門檻的連續區段，已經被記錄成
`beat_fusion_report["track_b_spans"]`：

```python
track_b_spans.append({
    "start_time": round(current_span_start, 3),
    "end_time": round(t, 3),
    "beat_count": current_span_count,
    "reason": "low_rhythm_energy",
})
```

**這就是「信心分段」跟「缺口清單」——現成的，不用重新發明 Stage 0/Stage 1。**
V3 只需要新增一個節點，針對這份缺口清單逐段強化。

---

## 1. 設計：GapReinforcementNode

### 1.1 疊加式證據重建（非互斥切換）

對 `track_b_spans` 裡的每一段缺口，**逐輪擴大證據池**（不是換軌，是疊加）：

| 輪次 | 證據池 | 複用節點 |
|---|---|---|
| 第 0 輪（已有） | 鼓（原本 A 軌本身，能量已知不足） | — |
| 第 1 輪 | 鼓 + 貝斯 | `BassEvidenceExtractNode`（Pass 148） |
| 第 2 輪 | 鼓 + 貝斯 + 和弦 | `ChordMelodyOnsetSplitNode` + `ChordTrackPKNode`（Pass 110/147） |
| 第 3 輪 | 鼓 + 貝斯 + 和弦 + 旋律 | `VocalMelodyEvidenceExtractNode` + `MelodyTrackPKNode`（Pass 111/149） |
| 都不夠 | 沿用 V1 現有的等速內插（現狀，不變差） | — |

每一輪都用 V2 現成的 `bar_start_candidates` 累積評分機制（同一個候選、多個
`evidence_sources` 疊加會提升 `confidence`，這是 Pass 108-111 已經測試過的邏輯，
直接重用），只要某一輪的信心度超過門檻就停止疊加、採用該輪結果；都不夠才落回
現狀的內插。

### 1.2 缺口重建的雙向錨定（解決接縫相位問題）

缺口重建出來的候選拍點，**不能自己憑空決定小節起點**，必須用缺口前後
「V1 已經確信」的那兩個拍點做雙向錨定：

- 起點錨點：`track_b_spans[i]["start_time"]` 之前，V1 grid 最後一個確信拍點。
- 終點錨點：`track_b_spans[i]["end_time"]` 之後，V1 grid 第一個確信拍點。
- 缺口內部重建出的拍點數量，必須跟兩個錨點之間的預期小節數（用局部 BPM 推算）
  吻合；不吻合時，優先信任「跟前後錨點的拍距最接近全曲局部中位數」的候選組合。

這個雙向錨定邏輯直接複用 V2 的 `BidirectionalBarAlignmentNode` /
`TwoWayAnchorBacktraceNode`（Pass 116-117 / 168）已經寫好、測試過的演算法，
只是套用範圍從「v2 全曲逐小節推進」縮小成「只套在 V1 標記的缺口內」。

### 1.3 節點規格（草案）

```python
class GapReinforcementNode(BaseNode):
    """Pass 176: 對 BeatFusionArbitratorNode 標記的 track_b_spans（低節奏能量
    缺口）逐輪疊加貝斯/和弦/旋律證據重新分析，取代現有的等速內插填補，
    並用缺口前後 V1 已確信的拍點做雙向錨定，避免接縫相位跳動。"""

    required_keys = ["beats", "beat_fusion_report"]
    optional_keys = ["stems", "stems_dir"]
    output_keys = ["beats", "gap_reinforcement_report"]
```

放置位置：`BeatFusionArbitratorNode` 之後、`ReEntryReAnchoringNode`/
`BeatValidationNode` 之前（`build_beat_refinement_nodes()`，
`pgm_craft/workflow/beat_tracking_bt.py`）——在 V1 既有的精修守衛鏈**最前面**
插入，讓後面的 `BeatGridContinuityRepairNode`/`ViterbiTempoSmoothingNode` 等
節點是在「已經強化過的缺口」上做最後平滑，而不是在原始的內插結果上做。

---

## 2. 驗證方式

1. **單元測試**（合成資料，快）：
   - 合成一段「鼓能量正常 → 低能量缺口 → 鼓能量恢復」的三段式音訊，缺口內
     埋入已知的貝斯/和弦節奏，驗證 `GapReinforcementNode` 能用貝斯+和弦證據
     正確重建缺口拍點，且跟前後錨點的相位誤差在容許範圍內。
   - 驗證「都沒證據」時安全退回現有內插行為（不得比現狀更差）。
2. **黃金基準回歸**（真實資料，貴，~23-28 分鐘/次）：
   - 用 `pgm_craft.golden_benchmark` 已有的黃金基準統計，跑一次完整
     `target_stage="module3"`，比對修好前後在第 10-18 小節（症狀 2 實測發生
     處）跟前 5 小節（症狀 1）的小節時間差是否縮小。
   - 這一步因為成本高，建議先確認單元測試全過、程式碼審查過一輪，再排這次
     實測，避免反覆燒 23 分鐘除錯。

## 3. 待確認的實作細節（實作前需要再對齊）

1. `track_b_spans` 目前的 `beat_count` 只記錄「A 軌被跳過的拍數」，沒有記錄
   缺口的置信度分數本身——`GapReinforcementNode` 需要自己算「這輪疊加後夠不夠
   信心」的門檻，建議直接重用 Pass 108 `DrumEvidenceBarSearchNode` 系列已有的
   confidence 計算方式，不要另外發明一套。
2. 前奏（症狀 1）目前不一定會被 `BeatFusionArbitratorNode` 標記進
   `track_b_spans`——因為前奏可能是「鼓能量不到 0（有微弱鼓聲），只是還沒準」
   ，不是能量門檻判定的「無鼓」。需要先確認前奏是否真的落在某個
   `track_b_span` 裡；如果沒有，症狀 1 可能需要另外一條規則（例如「全曲第一個
   `track_b_span` 結束前的區間，一律視為需要強化的前奏」）。
