# Pass 228 任務書：評分模型接上真實訊號——修「headline 分數」不動搖 Stage3 內部決策閘門

**狀態**：設計已定案（含明確的風險評估與範圍界線），根因跟修復方向
都已確認，可轉交 Codex CLI 直接執行。**規劃階段，尚未實作**——依
使用者指示「完整規劃後再實作」，本文件先完整寫完，等使用者/下一輪
session 核准後才動工。

---

## 0. 背景：為什麼要做這件事

使用者在 Pass219-227 結束、決定暫停繼續修 BarStart V2 仲裁邏輯之後，
主動要求驗證整個 Pass197-227 系列一直拿來當「這個網格好不好」依據的
**評分模型**（`barstart_v2_score`/`original_score`，過去引用過的數字
例如 88.14 vs 88.47、37.15、65.53、73.14、83.14 等）本身可不可信。

**查證發現：這個分數目前結構上幾乎完全是自我參照，不是真的在檢查
「這個網格是否對應真實音樂」**：

```python
# pgm_craft/workflow/beat_tracking_bt.py:83-167
def _score_beat_grid_quality(beats, kick_anchors=None, sections=None, alignment_score=None) -> dict:
    ...
    score = 100.0 * (
        0.36 * tempo_stability       # 純內部一致性：拍子間距跟自己的中位數比
        + 0.26 * downbeat_consistency  # 純內部一致性：降拍間隔跟自己的中位數比
        + 0.28 * combined_alignment    # 理論上該接真實音訊，實際上被關掉見下
        + 0.10 * min(1.0, len(arr) / 16.0)  # 覆蓋率獎勵
    )
```

`combined_alignment` 的呼叫方式：

```python
# pgm_craft/workflow/module3_bt.py:1063-1069（原始 vs V2 headline 比較）
# Same scoring function, same (empty) optional args on both sides
original_quality = _score_beat_grid_quality(original_beat_grid)
v2_quality = v2_blackboard.get_val("barstart_v2_quality_score") or {
    "score": _score_beat_grid_quality(v2_beat_grid)["score"]
}

# pgm_craft/workflow/module3_barstart_v2_bt.py:3353-3355（V2 自己的分數節點）
class BarStartV2QualityScoreNode(BaseNode):
    def execute(self, blackboard):
        beats = blackboard.get_val("refined_beats", blackboard.get_val("beats"))
        base = _score_beat_grid_quality(beats)   # ← 沒傳 kick_anchors/sections
```

兩處都用**空參數**呼叫，導致：
- `kick_anchors=None` → `anchor_alignment` 直接寫死等於 **0.75**（常數，
  完全不看真實鼓點）。
- `sections=None` → 退回成單一假段落 `{"start_time": 0.0}`，
  `section_alignment` 只檢查「網格開頭附近有沒有降拍」，對任何完整的
  網格幾乎永遠貼近 1.0，跟中後段對不對無關。
- 算下來 `combined_alignment ≈ 0.55×0.75 + 0.45×1.0 ≈ 0.86`，**對任何
  一份還算完整的網格幾乎是同一個常數**，加上覆蓋率那 10% 對這種長度
  的歌也幾乎永遠滿分——**真正會隨網格好壞變動的部分只剩
  `tempo_stability`(36%)+`downbeat_consistency`(26%)= 62% 權重，而
  這兩者都只檢查「間隔規不規律」，不檢查「這個位置是不是真的對」**。
  一個很規律但整體相位錯了的網格可以在這兩項拿到接近滿分。

**好消息**：程式碼註解明確寫著「V1/V2 用完全一樣的空參數呼叫，故意讓
比較公平」——所以 **V1 vs V2 的相對排名（誰分數高）本身沒有被這個
弱點汙染**，兩邊受到同樣的懲罰。但**分數的絕對數值不能解讀成
「這個網格有幾%正確」**。

**額外查證：`sections` 在算 headline 分數的當下，結構上就是空的**。
`sections` 由 `music_analysis_bt.py`（Stage4 MusicAnalysisRoot）產生，
但 `_score_beat_grid_quality` 的所有呼叫（包含已經正確傳入
`kick_anchors=anchors, sections=sections` 的內部節點，例如
`KickAnchorConsensusSnapNode`（`beat_tracking_bt.py:2279-2281`）、
`CommercialBeatQualityNode`（`beat_tracking_bt.py:2517-2522`，Stage3
`build_beat_tracking_nodes()` 序列的最後一個節點，`beat_tracking_bt.py:3358`）
——**全部發生在 Stage3（BeatTrackingRoot）執行期間，Stage4 根本還沒
跑過**，`blackboard.get_val("sections", [])` 在正常全自動流程裡此時
一定是空列表。**這不是漏傳參數的 bug，是 pipeline 階段順序造成的
結構性資料不可用**，本任務書不打算修這個（見第3節範圍界線）。

---

## 1. 風險評估：`_score_beat_grid_quality` 是內部決策閘門，不只是報告數字

**這是本任務書最重要的設計約束，決定了要選哪個修復方案**：

```
scratch 統計 _score_beat_grid_quality 全部呼叫點：
  beat_tracking_bt.py:2036-2037  GapReinforcementNode 內部 accept/reject
  beat_tracking_bt.py:2280-2281  KickAnchorConsensusSnapNode accept/reject
  beat_tracking_bt.py:2315-2316  （同一節點的 fallback 分支）
  beat_tracking_bt.py:2445-2453  DrumsKickBeatFallbackNode accept/reject
  beat_tracking_bt.py:2517       CommercialBeatQualityNode 最終報告
  module3_bt.py:1067-1069        headline V1 vs V2 比較（本任務書要修的目標）
  module3_barstart_v2_bt.py:3355 BarStartV2QualityScoreNode（本任務書要修的目標）
```

前 4 個（`GapReinforcementNode`/`KickAnchorConsensusSnapNode`/
`DrumsKickBeatFallbackNode` 的內部呼叫）**不是報告數字，是 Stage3
舊版管線拿來決定「要不要接受某個候選網格」的實際決策依據**——
如果直接修改 `_score_beat_grid_quality()` 本體的公式（加新項、改
權重），這些節點的 accept/reject 判斷都會跟著變，等於改變整條 Stage3
舊版管線的實際行為，不只是改一個報告數字。

Stage3 舊版管線是這整個專案歷史上landmine最多的地方（Pass189至今
仍未修的無界迴圈bug、Pass219確認「Pass190-198是圍繞Pass189的bug行為
調出來的」——修復一個環節在孤立情況下正確，接到整條鏈可能引發連鎖
退步）。**直接改 `_score_beat_grid_quality()` 本體屬於高風險、大
炸裂半徑的改動**，需要完整重跑 Stage3 全部既有測試+真實全曲驗證才能
確認沒有動到不該動的地方。

---

## 2. 修復方案：新增獨立的 headline 評分函式，不動 `_score_beat_grid_quality` 本體

**決策：選低風險方案**——新增一個**只給 headline 報告使用**的新
評分函式，`_score_beat_grid_quality()` 本體維持原樣不動，Stage3
內部那 4 個決策閘門完全不受影響。

### 2.1 新函式：`_score_beat_grid_grounded(beats, kick_stem_path)`

放在 `beat_tracking_bt.py`，緊接在 `_score_beat_grid_quality` 之後：

```python
def _kick_downbeat_accent_score(beats, kick_stem_path) -> dict:
    """獨立於 golden、獨立於 V1/V2 任何仲裁邏輯的真實音訊接地檢查：
    每個標記為 beat==1 的位置，是否真的是它自己所在小節（同一輪
    beat1-beat4，用該小節內其他拍子的時間界定範圍）裡 kick 分軌能量
    最大的一拍。方法沿用 Pass227 驗證過有效的做法
    （scratch/run_pass227_golden_downbeat_accent_verification.py）：
    Verse1 76.2%、Chorus1 59.5% 明顯高於 25% 隨機基準，Outro 只有
    30.0%——這個訊號本身在這首歌上有區辨力，且完全不依賴 golden，
    可以在正式 pipeline runtime 使用（golden 只有這首測試曲才有）。
    """
    # 用 librosa.feature.rms 對 kick_stem_path 算能量包絡，對每個
    # beat==1 的時間點取窗口內峰值，跟同一小節（同一輪 4 拍）裡
    # beat2/3/4 的峰值比較，回傳
    # {"win_ratio": float 0-1, "measures_checked": int, "warnings": [...]}
    ...


def _score_beat_grid_grounded(beats, kick_anchors=None, sections=None,
                                alignment_score=None, kick_stem_path=None) -> dict:
    """Headline 報告專用——`_score_beat_grid_quality` 的超集，額外接上
    真實 kick_anchors（如果有傳）跟新的 kick 重音判斷項。不修改
    `_score_beat_grid_quality()` 本體，Stage3 內部決策閘門完全不受
    影響，只有 module3_bt.py 的 headline 比較跟
    BarStartV2QualityScoreNode 改呼叫這個新函式。
    """
    base = _score_beat_grid_quality(beats, kick_anchors=kick_anchors,
                                     sections=sections, alignment_score=alignment_score)
    accent = (
        _kick_downbeat_accent_score(beats, kick_stem_path)
        if kick_stem_path else None
    )
    # 權重方案見 2.2
    ...
```

### 2.2 權重方案（待實作時用離線驗證微調，這裡給一個起點）

現有 `_score_beat_grid_quality` 分數維持原樣當 base（讓既有的
`tempo_stability`/`downbeat_consistency` 邏輯繼續發揮作用），新的
`kick_downbeat_accent`（`win_ratio`）以固定權重疊加：

```
grounded_score = 0.75 * base_score + 25.0 * accent["win_ratio"]
```

（`win_ratio` 是 0-1，乘 25 剛好對應 25 分——這個具體數字**不是
定案**，實作時要用 `scratch/run_pass227_golden_downbeat_accent_verification.py`
的方法論，離線跑一次「這個新公式是否真的讓 Verse1/Chorus1 分數高於
Outro（我們已知 golden 在這三段的可信度依序是76%/60%/30%）」的
sanity check，確認公式方向正確再定案；如果 25 分權重讓總分波動太
劇烈或太不敏感，可以調整，只要離線驗證能證明新公式的區辨力方向正確
即可。）

`kick_anchors=None` 時（例如沒有 kick 分軌可用的邊界情況），
`accent=None`，`grounded_score` 直接退回等於 `base_score`——**不能
讓新機制在資料不足時報錯或產生誤導性的低分，沒有資料就退回舊行為**。

### 2.3 呼叫端修改（只改這兩處，其餘全部不動）

```python
# module3_bt.py:1067-1069
original_quality = _score_beat_grid_grounded(
    original_beat_grid,
    kick_anchors=original_blackboard.get_val("kick_anchors"),
    kick_stem_path=original_blackboard.get_val("stems", {}).get("kick"),
)
v2_quality = v2_blackboard.get_val("barstart_v2_quality_score") or {
    "score": _score_beat_grid_grounded(
        v2_beat_grid,
        kick_anchors=v2_blackboard.get_val("kick_anchors"),
        kick_stem_path=v2_blackboard.get_val("stems", {}).get("kick"),
    )["score"]
}
```

```python
# module3_barstart_v2_bt.py: BarStartV2QualityScoreNode.execute()
base = _score_beat_grid_grounded(
    beats,
    kick_anchors=blackboard.get_val("kick_anchors"),
    kick_stem_path=blackboard.get_val("stems", {}).get("kick"),
)
```

`sections` 這次**不接**（見第3節範圍界線）——`_score_beat_grid_grounded`
簽名保留 `sections` 參數只是為了跟 `_score_beat_grid_quality` 介面
一致，呼叫端傳 `None`，維持現有的弱 fallback，不假裝已經解決。

---

## 3. 範圍界線：明確不做的事

1. **不修 `_score_beat_grid_quality()` 本體**——Stage3 內部 4 個決策
   閘門（`GapReinforcementNode`/`KickAnchorConsensusSnapNode`/
   `DrumsKickBeatFallbackNode`）維持用舊公式判斷 accept/reject，本
   任務書不改變它們的行為。如果之後要讓這些內部閘門也用上真實
   kick重音訊號，是規模大很多的獨立任務（需要對整條Stage3管線做
   完整回歸驗證），不在本任務書範圍。
2. **不接真實 `sections`**——Stage4 在 Stage3 之後才跑，算 headline
   分數當下 sections 結構上一定是空的。要修這個需要調整pipeline
   階段順序，或另外新增一個在 Stage4 之後才跑的「最終審計」節點
   （`CommercialBeatQualityNode` 目前的命名/設計意圖看起來就是為了
   這個，但目前掛在 Stage3 序列尾端、跑得太早）——這是架構級改動，
   不在本任務書範圍，留待使用者決定是否要開新Pass處理。
3. **不重新評估過去任何一個Pass的歷史分數**——Pass197-227引用過的
   88.14/88.47等數字維持不變，不回頭改寫歷史記錄；本任務書完成後
   會產生一組**新的、不可跟舊數字直接比較的分數**，需要建立新基準。

---

## 4. 測試要求

新增 `tests/test_sdd_pass228.py`，至少涵蓋：

1. **合成案例**：構造一個「規律但相位錯誤」的網格（間隔完全一致，
   但 beat==1 標在錯誤位置，例如故意錯開一拍），驗證舊
   `_score_beat_grid_quality` 給出高分（證明現有弱點確實存在），新
   `_score_beat_grid_grounded`（配合合成的假 kick 訊號，beat1真正
   對應位置能量明顯較低）給出**明顯更低**的分數——這是本次修復
   最核心的驗收標準。
2. **`kick_stem_path=None` / 檔案不存在的邊界情況**：確認
   `grounded_score` 正確退回等於 `base_score`，不報錯、不產生
   NaN/None 汙染。
3. `_kick_downbeat_accent_score` 對真實 World is Mine 的 kick 分軌
   （沿用已快取的 `outputs/pass203_evidence_fusion_diagnosis/.../stems/drums/kick.wav`）
   跑一次，確認 Verse1/Chorus1/Outro 三段的 `win_ratio` 排序跟
   Pass227 的獨立驗證結果方向一致（Verse1 > Chorus1 > Outro）——
   拿 Pass227 已經產生的分段驗證程式碼改寫成正式測試，不用重新設計
   方法論。
4. 執行既有回歸測試確認 `_score_beat_grid_quality()` 本體行為完全
   沒變（因為本任務書刻意不碰它）：
   ```
   C:/Python313/python.exe -m pytest tests/test_sdd_pass228.py tests/test_module3_bt.py tests/test_sdd_pass202.py -q
   ```

---

## 5. 真實資料驗證

1. 用 `scratch/run_pass211_promoted_production_verify.py`（或最新等效
   腳本）重跑一次完整管線，記錄新的 `original_score`/`barstart_v2_score`
   數字——**明確標註這是全新基準，不能跟過去任何一個Pass引用的舊
   數字直接比較**。
2. 檢查新分數的 `v2_scores_higher`（V2 是否仍然贏過舊方法）有沒有
   翻轉——如果翻轉，如實記錄，不要為了維持「V2已升格」的既有結論
   而回頭調整權重湊數字（這正是這整個系列反覆告誡過的「不能為了
   數字好看而調參數」陷阱）。
3. 確認 Stage3 內部 4 個決策閘門（`GapReinforcementNode` 等）的
   accept/reject 結果**完全沒有變化**（因為 `_score_beat_grid_quality`
   本體沒被動到）——可以用既有的 `full_song_loop_report`/相關診斷
   欄位跟修改前的版本逐項比對確認。

---

## 6. 完成後

1. 更新 `docs/BT-BUILD-PROGRESS.md`，新增 Pass 228 條目：完整記錄
   新公式設計、離線驗證結果（新公式在合成案例+真實三段落上是否真的
   有區辨力）、真實資料驗證後的新基準分數、`v2_scores_higher`
   有沒有變化。
2. 更新使用者記憶檔案（如果是Claude執行）：把「headline分數已接上
   真實kick重音訊號，新基準是多少」這個事實記下來，避免下一輪
   session誤用舊的88.14/88.47當比較基準。
3. Commit + push 到 `origin/worktree-pass171-multi-variant-harness`，
   commit message 用 `feat(pass228): ...` 前綴（新增評分機制，不是
   單純修bug）。
4. **不要在本任務書範圍內順便嘗試修 `sections`資料不可用或Stage3
   內部決策閘門**——這兩件事已經在第3節明確排除，如果實作中發現
   「其實很好修」，先回報給使用者/下一輪session決定要不要開新
   Pass，不要在這個任務書裡順手做掉（範圍蔓延正是這系列過去反覆
   出問題的模式之一）。
