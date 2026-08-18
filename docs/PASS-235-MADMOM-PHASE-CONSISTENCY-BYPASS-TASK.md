# Pass 235 任務書：讓 madmom 候選繞過自我參照的 phase_consistency_score 仲裁

**狀態**：根因已精確定位（Pass234逐案例驗證，golden交叉比對），設計
方向明確，可直接轉交 Codex CLI 執行。**這是修復 Pass232 失敗根因的
新設計，不是重新整合 Pass232 沒動過的部分。**

---

## 0. 背景：Pass232/233 為什麼失敗，Pass234 已經找到確切機制

Pass232 依 `docs/PASS-232-MADMOM-DBN-EVIDENCE-TIER-INTEGRATION-TASK.md`
把 madmom 包裝成 BarStart V2 的新證據來源（`MadmomDBNEvidenceExtractNode`
全曲跑一次 + `MadmomDBNCandidateAdapterNode` 每視窗轉候選），Codex
完整實作+真實驗證後發現 `barstart_v2_score` 從基準80.66掉到65.77，
更保守的第二版（只boost不新增）更差（63.19），兩次都誠實撤回。

**Pass234 用同樣設計重新診斷（診斷用，跑完已還原，未留下程式碼），
埋點追蹤Chorus1全部34個tick，找到確切機制**：madmom提出獨立候選的
11次裡，**9次（82%）輸掉仲裁——而且每次輸，madmom自己的候選跟golden
真值誤差都在4-40毫秒（近乎完美），贏家的誤差卻是221-481毫秒（通常
代表跳過一個真實小節）**。逐案例展開（`scratch/pass234_chorus1_trace.jsonl`
tick16）：madmom候選117.45秒（golden 117.409796，差40ms）輸給
v1_grid候選118.46秒（golden最近118.907755，差448ms，還跳過golden
在116.0秒的真實降拍）。兩者信心都過門檻，決勝的是
`phase_consistency_score`：v1_grid的0.843明顯高於madmom的0.506。

**根因**：`BarStartCandidateCommitNode._best_candidate()`
（`module3_barstart_v2_bt.py:1286-1350`）的仲裁排序鍵是：

```python
winner = max(
    scored,
    key=lambda item: (
        clears_threshold(item),
        item["phase_consistency_score"],   # ← 純自我參照：跟已委任歷史比對
        item["candidate"]["confidence"],
        -item["candidate"]["time"],
    ),
)
```

`phase_consistency_score`（`_phase_consistency_score`，同檔案
`:1438-1458`）純粹計算候選跟`committed_bar_starts`（已經委任的歷史）
的殘差——**如果歷史本身已經有漂移，這個分數會系統性獎勵「延續漂移」
的候選、懲罰「修正漂移」的候選**。這正是整個Pass212-226系列13次
仲裁調參嘗試都在打轉的同一個核心機制（詳見
`docs/BT-BUILD-PROGRESS.md` Pass219-226各條目）。madmom準確，正是
因為它靠全曲DBN全域最佳化、不依賴已委任歷史，天生就會修正漂移——
但這正好是它在這個自我參照分數裡系統性吃虧的原因。**把madmom包裝成
「多一個候選」丟進同一套仲裁規則，結構上就是死路，不是信心值該給
多少的問題（Pass232/234已經排除這個假設）。**

---

## 1. 設計：新增一個排序維度，讓 madmom 候選繞過 phase_consistency_score 比較

**核心改動只有一處**：`_best_candidate()`裡的排序鍵，在
`clears_threshold`跟`phase_consistency_score`之間，插入一個新維度
——「這個候選是否有madmom獨立模型的佐證」。有madmom佐證的候選，
優先權高於`phase_consistency_score`的比較，不再被自我參照分數
否決；沒有madmom佐證時（全曲大部分tick，madmom沒有提出候選的地方），
排序行為完全不變，退回原本的`phase_consistency_score`比較。

```python
def _has_independent_model_support(item) -> bool:
    evidence = set(item["candidate"].get("evidence_sources", []) or [])
    return bool(evidence & {"madmom_dbn", "madmom_dbn_support"})

winner = max(
    scored,
    key=lambda item: (
        clears_threshold(item),
        _has_independent_model_support(item),   # <-- 新增這一維
        item["phase_consistency_score"],
        item["candidate"]["confidence"],
        -item["candidate"]["time"],
    ),
)
```

**為什麼這樣設計是安全、範圍收斂的**：
1. `clears_threshold`維持最高優先權不變——低信心候選（包含假設性的
   低信心madmom候選，雖然目前madmom是固定0.78恆過門檻）依然不能
   靠這個新維度硬闖過門檻檢查。
2. 只有**衝突候選集合裡真的有madmom佐證的候選時**，這個新維度才會
   產生差異；沒有madmom候選的tick（例如Pass229/230已知madmom證據
   較弱的Intro/Outro部分區段），排序邏輯完全退回原本行為，不會
   意外把madmom不熟悉區段的行為搞得更糟（但要用真實驗證確認這個
   推論，見第3節）。
3. `arbitration`報告要新增`"winner_independent_model_supported"`欄位
   （比照既有`"winner_cleared_threshold"`的寫法），保留可追溯性——
   Pass232當初留下的一個缺口就是報告沒有序列化這個資訊，這次要
   補上。

**明確排除的替代設計（不在這個任務書做）**：
- 不做「madmom信心動態依局部證據強弱調整」——這是Pass232任務書
  第3節就明確排除過的方向，同一個理由：先驗證最簡單版本的效果，
  不要一次疊加兩個新機制。
- 不修改`phase_consistency_score`/`_expected_bar_duration`本身
  ——那是Pass219-226已經徹底測過、確認是死路的方向（13次變體）。
  這次的修法刻意不動這個函式，只是讓madmom候選在排序時繞過它。

---

## 2. 重新加回 Pass232 的兩個節點

**更正（重要）**：Pass232/233 當初的節點實作**從未被 commit 過**
——Codex 依這個專案一貫的「實作→驗證→退步就`git checkout --`還原、
只留文件記錄」慣例正確處理，代表 `git log`/reflog 裡完全沒有那份
程式碼可以復原，**不要花時間去找，找不到是正常的，不是操作失誤**。
下面直接提供已經在 Pass234 診斷時重新實作過、而且已經在真實pipeline
上跑成功、產出過正確trace資料的完整程式碼（`scratch/run_pass234_madmom_chorus1_diagnosis.py`
那次的版本），可以直接照抄，不需要重新設計。

**設計本身沒有問題**（Pass234已經證實madmom提出的候選幾乎每次都
準），問題出在仲裁排序邏輯（第1節），不在下面這兩個證據生成節點。

### 2.1 `MadmomDBNEvidenceExtractNode`

加在 `pgm_craft/workflow/module3_barstart_v2_bt.py`（例如緊接在
`BeatThisCandidateAdapterNode`類別定義之後）：

```python
class MadmomDBNEvidenceExtractNode(BaseNode):
    """全曲跑一次 madmom RNNDownBeatProcessor + DBNDownBeatTrackingProcessor，
    把結果快取到 blackboard，供 MadmomDBNCandidateAdapterNode 每個探測
    視窗查詢用。madmom 需要整首歌脈絡才能做全域最佳化的tempo-lock
    解碼——這正是它比逐窗口證據來源更準的原因，不能拆成逐視窗重跑。
    """

    optional_keys = ["audio_path"]
    output_keys = ["madmom_downbeats", "madmom_beats", "madmom_evidence_report"]

    TRANSITION_LAMBDA = 500  # Pass230 掃描出的甜蜜點

    def __init__(self):
        super().__init__("MadmomDBNEvidenceExtractNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            blackboard.set_val("madmom_evidence_report", {"status": "SKIPPED_NO_AUDIO_PATH"})
            return NodeStatus.SUCCESS
        try:
            from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor
        except ImportError as exc:
            blackboard.set_val("madmom_evidence_report", {"status": "SKIPPED_IMPORT_ERROR", "error": str(exc)})
            return NodeStatus.SUCCESS
        try:
            act = RNNDownBeatProcessor()(audio_path)
            dbn = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=100, transition_lambda=self.TRANSITION_LAMBDA)
            result = dbn(act)
        except Exception as exc:
            blackboard.set_val("madmom_evidence_report", {"status": "SKIPPED_RUNTIME_ERROR", "error": str(exc)})
            return NodeStatus.SUCCESS
        beats = sorted(set(round(float(t), 6) for t, _ in result))
        downbeats = sorted(set(round(float(t), 6) for t, pos in result if int(round(pos)) == 1))
        blackboard.set_val("madmom_downbeats", downbeats)
        blackboard.set_val("madmom_beats", beats)
        blackboard.set_val("madmom_evidence_report", {
            "status": "EXTRACTED", "transition_lambda": self.TRANSITION_LAMBDA,
            "downbeat_count": len(downbeats), "beat_count": len(beats),
        })
        return NodeStatus.SUCCESS
```

### 2.2 `MadmomDBNCandidateAdapterNode`

緊接在上面那個類別之後：

```python
class MadmomDBNCandidateAdapterNode(BaseNode):
    """把 MadmomDBNEvidenceExtractNode 全曲跑好、快取在blackboard的
    降拍清單，轉成當前探測視窗的 bar_start_candidates；跟既有候選
    很接近就提升既有候選信心並標記佐證，完全沒被覆蓋的位置才新增
    一個獨立候選（每個視窗最多一個）。跟 BeatThisCandidateAdapterNode
    同一種模式。
    """

    optional_keys = ["active_bar_probe_window", "bar_start_candidates", "madmom_downbeats", "committed_bar_starts"]
    output_keys = ["bar_start_candidates", "madmom_candidate_report"]

    BASE_CONFIDENCE = 0.78
    BOOST_AMOUNT = 0.16
    COINCIDENCE_TOLERANCE_SEC = 0.08

    def __init__(self):
        super().__init__("MadmomDBNCandidateAdapterNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        candidates = list(blackboard.get_val("bar_start_candidates", []) or [])
        madmom_downbeats = blackboard.get_val("madmom_downbeats") or []

        in_window = [t for t in madmom_downbeats if self._inside_window(t, window)]
        if not in_window:
            blackboard.set_val("madmom_candidate_report", {"status": "SKIPPED_NO_CANDIDATES_IN_WINDOW"})
            return NodeStatus.SUCCESS

        boosted = 0
        for t in in_window:
            nearest = self._nearest_existing(candidates, t)
            if nearest is None:
                continue
            conf = float(nearest.get("confidence", 0.0))
            nearest["confidence"] = round(float(np.clip(conf + self.BOOST_AMOUNT, 0.0, 1.0)), 6)
            evidence = list(nearest.get("evidence_sources", []) or [])
            if "madmom_dbn_support" not in evidence:
                evidence.append("madmom_dbn_support")
            nearest["evidence_sources"] = evidence
            boosted += 1

        added = []
        for t in in_window:
            if self._has_candidate_near(candidates, t):
                continue
            added.append({
                "time": round(t, 6),
                "confidence": round(float(np.clip(self.BASE_CONFIDENCE, 0.0, 1.0)), 6),
                "evidence_sources": ["madmom_dbn"],
                "source_node": self.name,
            })
            break

        candidates.extend(added)
        blackboard.set_val("bar_start_candidates", candidates)
        blackboard.set_val("madmom_candidate_report", {
            "status": "CANDIDATES_BUILT" if added or boosted else "NO_OP",
            "boosted_count": boosted, "added_count": len(added),
            "in_window_count": len(in_window),
        })
        return NodeStatus.SUCCESS

    def _nearest_existing(self, candidates, time_sec: float):
        best, best_dist = None, None
        for c in candidates:
            if not isinstance(c, dict):
                continue
            try:
                t = float(c.get("time"))
            except (TypeError, ValueError):
                continue
            dist = abs(t - time_sec)
            if dist <= self.COINCIDENCE_TOLERANCE_SEC and (best_dist is None or dist < best_dist):
                best, best_dist = c, dist
        return best

    def _has_candidate_near(self, candidates, time_sec: float) -> bool:
        return self._nearest_existing(candidates, time_sec) is not None

    def _inside_window(self, time_sec: float, window: dict) -> bool:
        if not window:
            return False
        start = float(window.get("start_time", 0.0))
        end = float(window.get("end_time", start))
        return start <= float(time_sec) <= end
```

### 2.3 接線位置（已確認精確，Pass234 用同樣接法真的跑成功過）

1. `MadmomDBNEvidenceExtractNode()`：加進`module3_bt.py`的
   `v2_core = SequenceNode("BarStartV2CoreChain", [...])`，放在
   `VocalMelodyEvidenceExtractNode()`之後、`FullSongBarStartLoopNode()`
   之前，並且從`module3_barstart_v2_bt.py`的import清單裡加上
   `MadmomDBNEvidenceExtractNode`。
2. `MadmomDBNCandidateAdapterNode()`：加進
   `build_module3_barstart_v2_probe_tick_tree()`
   （`module3_barstart_v2_bt.py:3903-3934`），緊接在
   `BeatThisCandidateAdapterNode()`之後、`ReliableBarAnchorNode()`
   之前。

---

## 3. 驗證流程：先離線驗證，再花真實pipeline時間

**這個改動比Pass232的風險更高**——Pass232只是新增證據來源，這次是
**直接改動`_best_candidate()`的排序邏輯**，理論上任何有madmom候選
參與的tick都可能改變結果，不是只有Chorus1。**必須先離線驗證，不能
直接跳到真實production verify**。

### 3.1 離線驗證（便宜、快，先做）

Pass234已經留下`scratch/pass234_chorus1_trace.jsonl`（Chorus1
34個tick的完整候選+決策快照，包含madmom候選）。**先擴充Pass234的
埋點腳本（`scratch/run_pass234_madmom_chorus1_diagnosis.py`），移除
`CHORUS1_START-5/CHORUS1_END+5`這個範圍限制，改成擷取全曲所有
tick**（跟Pass222`scratch/run_pass222_full_song_candidate_trace.py`
的做法一樣，這個腳本本來就是全曲埋點的模板，只是Pass234為了聚焦
Chorus1加了範圍過濾），重新跑一次（帶madmom節點，診斷用，跑完一樣
用`git checkout --`還原程式碼，只留trace檔案）。

拿到全曲trace後，寫一個離線模擬器（比照`scratch/simulate_pass223_periodic_reanchor.py`
——**這個模擬器已經驗證到跟真實production 100%逐筆吻合**，見
`docs/BT-BUILD-PROGRESS.md` Pass224追記；直接複製它的
`_phase_consistency_score`實作跟`simulate()`裡的贏家選擇邏輯，
只在排序key插入這次新增的`_has_independent_model_support`維度），
重跑全曲trace，比較：

1. Chorus1的golden殘差是否真的大幅改善（Pass234已知9/11勝率會
   翻轉，離線驗證這個翻轉在完整仲裁流程下是否真的成立，不是只看
   單一候選的分數）。
2. **Verse1/Intro/Outro有沒有意外變差**——這是這次驗證最重要的
   把關項目，因為新排序維度理論上任何有madmom候選的tick都會受
   影響，不是只有Chorus1。
3. 如果離線驗證顯示Verse1或其他段落變差，先在離線層級調整設計
   （例如把新維度限縮成只在`phase_consistency_score`差距超過某個
   門檻時才生效，或只在特定段落生效），不要直接跳到真實pipeline
   驗證去賭。

**只有離線驗證顯示全曲整體正面（Chorus1明顯改善、其他段落沒有
明顯變差）之後，才進入下一步真實pipeline驗證**——這是效率考量，
真實pipeline一次要13-18分鐘，離線模擬只要幾秒到幾分鐘。

### 3.2 真實資料驗證（離線驗證通過後才做）

用`scratch/run_pass228_grounded_score_production_verify.py`（或
Codex熟悉的等效腳本）重跑完整管線，比對：

- `original_score=66.5`/`barstart_v2_score=80.66`（Pass228基準，
  目前正式基準，因為Pass232/233都已撤回）——**這次驗證要看新設計
  能不能讓`barstart_v2_score`真正超過80.66**，不能只是「沒有退步」
  就算過關，畢竟madmom證據品質已知很好，應該要看到實質提升。
- 逐段（Intro/Verse1/Chorus1/Outro）跟golden的殘差，尤其Chorus1
  是否真的改善（golden在這段可信，見Pass227）。
- Verse1（原本已知完美的段落）**絕對不能變差**——這是最基本的
  安全底線，如果Verse1變差，不管Chorus1改善多少都要視為失敗、
  revert。
- **明確要求**：如果真實資料驗證顯示整體變差（不只是Chorus1），
  要如實記錄、revert，不能為了呈現「這次終於成功了」而勉強接受
  混雜結果——這是整個Pass197-234系列一貫的鐵律，Pass232/233已經
  示範過兩次正確的撤回，這次也要一樣嚴格。

---

## 4. 測試要求

新增`tests/test_sdd_pass235.py`（`tests/test_sdd_pass232.py`同樣
從未被commit過，不存在，不用花時間找，直接寫新的）：

1. 合成案例：構造一組衝突候選，其中一個有`madmom_dbn`（或
   `madmom_dbn_support`）在`evidence_sources`裡但`phase_consistency_score`
   較低，另一個沒有madmom佐證但`phase_consistency_score`較高——
   驗證新排序邏輯讓有madmom佐證的候選勝出。
2. 合成案例：完全沒有madmom佐證的衝突候選集合——驗證排序結果
   跟修改前完全一致（回歸測試，確認沒有madmom候選時行為不變）。
3. 合成案例：madmom候選信心低於門檻（雖然目前固定0.78恆過門檻，
   但測試要涵蓋這個邊界情況，不能假設未來不會變成動態信心）——
   驗證`clears_threshold`仍然優先於新增的madmom維度，不會讓低信心
   候選靠這個新機制硬闖過關。
4. 執行既有回歸測試確認沒有破壞其他仲裁行為：
   ```
   C:/Python313/python.exe -m pytest tests/test_sdd_pass235.py tests/test_sdd_pass202.py tests/test_module3_bt.py -q
   ```

---

## 5. 完成後

1. 更新`docs/BT-BUILD-PROGRESS.md`，新增Pass235條目：完整記錄
   離線驗證結果（新舊排序邏輯在全曲trace上的差異）、真實資料驗證
   的完整數字（跟Pass228基準80.66/66.5比較，Chorus1有沒有真的
   改善、Verse1有沒有維持完美）、如實記錄任何退步或需要revert
   的部分——**不管結果是成功還是又一次撤回，都要跟Pass232/233
   一樣誠實記錄，不要為了呈現「這次成功了」而挑選對自己有利的
   數字**。
2. 更新使用者記憶檔案（如果是Claude執行）：這個bypass機制是否
   成功、新的分數基準是多少。
3. Commit + push到`origin/worktree-pass171-multi-variant-harness`，
   commit message用`feat(pass235): ...`前綴。
4. **不要在這個任務書範圍內順便做**：(a) madmom動態信心機制；
   (b) 修改`phase_consistency_score`/`_expected_bar_duration`本體；
   (c) 接進Stage3舊版legacy pipeline；(d) 嘗試修Outro殘餘誤差
   （golden基準本身在那裡就不夠可信，見Pass227）；(e) 在其他曲目
   做量化驗證（Pass231已用聽感驗證泛化性，這次的改動範圍限定在
   仲裁邏輯，不影響madmom本身的追蹤品質，沒有新增跨曲目風險）。
