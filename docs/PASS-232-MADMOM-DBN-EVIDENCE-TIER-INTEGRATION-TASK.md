# Pass 232 任務書：madmom DBN 降拍追蹤器接進 BarStart V2，當作新證據來源（不取代、不改動既有機制）

**狀態**：設計已定案，根因/驗證數據/技術細節都已確認，可直接轉交
Codex CLI 執行。**這是新增功能（`feat`），不是修 bug。**

---

## 0. 背景：為什麼要做這件事

Pass 229-231 用真實資料驗證了 madmom（Böck/Krebs/Widmer 的 DBN 降拍
追蹤器，`RNNDownBeatProcessor`+`DBNDownBeatTrackingProcessor`）：

- 對 World is Mine（不接分軌、不用任何自製證據融合，直接對原始
  音檔跑）：`transition_lambda=500` 時，Verse1/Chorus1/Intro 三段
  幾乎完美（18-25毫秒平均誤差，100%在50毫秒內），Outro 誤差減半
  （512ms→225ms，且Outro的golden基準本身可信度已知偏低，見Pass227）。
  **Chorus1 正是Pass212-226共13種自製仲裁邏輯調整嘗試都修不好的
  段落**，madmom 直接命中。
- 泛化性檢查（Pass231）：在另外兩首風格不同的歌（當代敬拜流行、
  管弦樂系電影配樂）上，使用者親耳確認 λ=100/500 兩版都達到「可
  接受、勉強商用」的品質，且穩定——不是只對World is Mine調出來的
  過擬合結果。

**使用者明確決定**：不完全取代 BarStart V2（World is Mine 這種有
真實變速的高難度曲子，madmom 在證據稀疏+速度變化的Intro/Outro
仍有殘餘誤差，不該貿然全面接手），改成**當作 BarStart V2 現有
「多證據來源逐小節仲裁」架構裡的一個新證據層**——這正好符合使用者
自己描述的「多個小場景模型協作、過濾後融合」的架構願景。

---

## 1. 整合點：只需要動 `pgm_craft/workflow/module3_barstart_v2_bt.py` 一個檔案

BarStart V2 的仲裁核心 `BarStartCandidateCommitNode._best_candidate()`
已經是一套成熟的多證據來源逐小節仲裁機制（現有證據層：
`DrumEvidenceBarSearchNode`/`DrumBassEvidenceBarSearchNode`/
`ChordTrackPKNode`/`MelodyTrackPKNode`/`V1GridEvidenceBarSearchNode`）。
**不需要新設計仲裁邏輯**，只需要讓 madmom 的降拍輸出，用跟其他證據
來源一樣的格式（`{"time":..., "confidence":..., "evidence_sources":[...], "source_node":...}`）
餵進 `bar_start_candidates`。

**現成可以直接參考的模板**：`BeatThisCandidateAdapterNode`
（`module3_barstart_v2_bt.py:2577-2770`附近，Pass200/220 beat_this
嘗試留下的、設計完整但目前沒有上游節點餵資料的轉接器）——它已經
示範了正確的模式：
1. 對每個探測視窗，把外部模型的降拍清單過濾到視窗範圍內。
2. 如果外部模型的降拍跟**既有候選**很接近（`coincidence_tolerance_sec`
   內），**提升既有候選的信心分數**（`_boost_existing_candidates`，
   +0.16，並在 `evidence_sources` 加註記），而不是重複新增一個候選
   ——這樣madmom證據強的地方會自然增強既有共識，不會製造衝突。
3. 只有當外部模型的降拍**附近完全沒有既有候選**時，才新增一個
   全新的獨立候選（且每個視窗最多新增一個，避免灌爆候選清單）。

**這次的做法：不修 `BeatThisCandidateAdapterNode` 本體，新增一個
結構相同、資料來源換成madmom的新節點**（`BeatThisCandidateAdapterNode`
保留給未來如果真的要接 beat_this 用；兩者邏輯可能會有共用之處，
Codex 可以自行判斷要不要抽共用函式，但不強制）。

---

## 2. 新增兩個節點

### 2.1 `MadmomDBNEvidenceExtractNode`——全曲跑一次，不是逐視窗跑

**關鍵設計原則**：madmom 的 DBN 需要整首歌的音訊脈絡才能做全域最佳化
（這正是它比逐窗口分析更準的原因），**絕對不能在每個探測視窗裡重跑
一次**——那樣不只浪費算力（RNN forward pass對一首3-4分鐘的歌要跑
數十秒到一兩分鐘），還會讓每個視窗看到不同的、局部脈絡不完整的
DBN結果，失去DBN全域最佳化的意義。

```python
class MadmomDBNEvidenceExtractNode(BaseNode):
    """全曲跑一次 madmom RNNDownBeatProcessor + DBNDownBeatTrackingProcessor，
    把結果快取到 blackboard，供 MadmomDBNCandidateAdapterNode 每個探測
    視窗查詢用。madmom 需要整首歌脈絡才能做全域最佳化的tempo-lock
    解碼——這正是它比逐窗口證據來源更準的原因，不能拆成逐視窗重跑。

    見 docs/PASS-229/230/231 的驗證數據：對 World is Mine，
    transition_lambda=500（不是預設的100）在Verse1/Chorus1/Intro
    幾乎完美，Outro也顯著改善；另外兩首風格不同的歌上使用者親耳確認
    穩定、可接受，不是對這首歌過擬合的結果。
    """

    optional_keys = ["audio_path"]
    output_keys = ["madmom_downbeats", "madmom_beats", "madmom_evidence_report"]

    TRANSITION_LAMBDA = 500  # Pass230 掃描出的甜蜜點，見任務書第0節

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
            # madmom 是既有依賴（專案裡已經在用），但預訓練模型檔案
            # (madmom.models git submodule) 有可能在某些環境沒裝進來
            # ——Pass229 就踩過這個坑，見下方「環境注意事項」。這裡
            # 不能讓整條 pipeline 因為這個可選證據來源失敗而掛掉。
            blackboard.set_val("madmom_evidence_report", {
                "status": "SKIPPED_IMPORT_ERROR", "error": str(exc),
            })
            return NodeStatus.SUCCESS

        try:
            act = RNNDownBeatProcessor()(audio_path)
            dbn = DBNDownBeatTrackingProcessor(
                beats_per_bar=[4], fps=100, transition_lambda=self.TRANSITION_LAMBDA
            )
            result = dbn(act)
        except Exception as exc:
            blackboard.set_val("madmom_evidence_report", {
                "status": "SKIPPED_RUNTIME_ERROR", "error": str(exc),
            })
            return NodeStatus.SUCCESS

        beats = sorted(set(round(float(t), 6) for t, _ in result))
        downbeats = sorted(set(round(float(t), 6) for t, pos in result if int(round(pos)) == 1))

        blackboard.set_val("madmom_downbeats", downbeats)
        blackboard.set_val("madmom_beats", beats)
        blackboard.set_val("madmom_evidence_report", {
            "status": "EXTRACTED",
            "transition_lambda": self.TRANSITION_LAMBDA,
            "downbeat_count": len(downbeats),
            "beat_count": len(beats),
        })
        return NodeStatus.SUCCESS
```

**環境注意事項（寫進節點 docstring 跟任務書，Codex 執行前務必確認）**：
這個worktree的madmom已經在Pass229修好過（原本`pip install`漏了
`madmom/models` git submodule，導致`RNNDownBeatProcessor()`初始化時
丟`ModuleNotFoundError: No module named 'madmom.models'`；修法是
`git clone --recursive https://github.com/CPJKU/madmom.git`後
`pip install --user --force-reinstall --no-deps <clone路徑>`）。
**如果Codex在全新環境執行、遇到同樣的import錯誤，上面`SKIPPED_IMPORT_ERROR`
分支會讓madmom證據來源優雅跳過、不影響其他證據層跟既有安全機制**
——但這樣等於這個Pass的功能完全沒生效，Codex應該先確認
`python -c "from madmom.features.downbeats import RNNDownBeatProcessor; RNNDownBeatProcessor()"`
在目標環境能跑成功，跑不成功要照上面的方法修好環境，不能就這樣
交差了事。

### 2.2 `MadmomDBNCandidateAdapterNode`——每個探測視窗查詢一次，轉成候選

```python
class MadmomDBNCandidateAdapterNode(BaseNode):
    """把 MadmomDBNEvidenceExtractNode 全曲跑好、快取在blackboard的
    降拍清單，轉成當前探測視窗的 bar_start_candidates，格式跟寫法
    直接參考 BeatThisCandidateAdapterNode（module3_barstart_v2_bt.py，
    Pass200/220遺留的完整轉接器範本，只是資料來源、信心值、日誌欄位
    換成madmom自己的）：madmom降拍靠近既有候選就提升既有候選信心
    （+boost，evidence_sources加註記"madmom_dbn_support"），完全沒
    候選覆蓋的位置才新增一個獨立候選（每個視窗最多一個）。
    """

    optional_keys = [
        "active_bar_probe_window",
        "bar_start_candidates",
        "madmom_downbeats",
        "committed_bar_starts",
    ]
    output_keys = ["bar_start_candidates", "madmom_candidate_report"]

    BASE_CONFIDENCE = 0.78  # 見任務書第3節信心值設計理由
    BOOST_AMOUNT = 0.16     # 跟 BeatThisCandidateAdapterNode 的既有慣例一致
    COINCIDENCE_TOLERANCE_SEC = 0.08

    def __init__(self):
        super().__init__("MadmomDBNCandidateAdapterNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        # ...實作邏輯直接仿照 BeatThisCandidateAdapterNode.execute()，
        # 只是資料來源改成 blackboard.get_val("madmom_downbeats")
        # （已經是全曲降拍時間清單，不需要再區分beats/downbeats/
        # candidates三種輸入格式，比beat_this的轉接邏輯更簡單）。
        ...
```

**這裡刻意省略完整實作**（跟前一個節點不同），因為邏輯應該直接
仿照`BeatThisCandidateAdapterNode`既有程式碼改寫，Codex 執行時
直接讀那段程式碼照著改就好，不需要我重新在任務書裡寫一次容易
出現轉寫錯誤的完整實作。

---

## 3. 信心值設計理由

`BASE_CONFIDENCE = 0.78`，比`V1GridEvidenceBarSearchNode`的`0.72`
高、比`BeatThisCandidateAdapterNode`降拍的`0.82`低一點——理由：

- madmom在這次驗證（Verse1/Chorus1 18-19ms、100%命中）表現明顯優於
  beat_this當初的驗證結果（Pass220：tempo octave亂跳問題），值得
  給比v1_grid更高的基礎信心。
- 但madmom仍然是**全曲單一信心值**（不像既有證據來源可以依據局部
  訊號強弱動態調整）——Pass229/230已經證實它在Intro/Outro這種
  證據稀疏段落明顯較弱，**不建議給到beat_this當初預期的0.82那麼高**，
  留一點餘裕讓既有的信心門檻（0.7）+仲裁邏輯在證據弱的地方自然
  地不讓它單獨勝出，而是靠既有機制（`_best_candidate`的
  `phase_consistency_score`、`quality_regression`否決層等）稀釋掉。

**明確決定：不額外設計「偵測困難區段（證據稀疏/速度不穩）就調低
madmom信心值」這種動態機制**——這是刻意的範圍收斂：這類自訂啟發式
規則正是Pass219-226整整13次嘗試失敗的同一種模式（在仲裁邏輯裡加
規則、規則本身可能又是新的偏差來源）。**先用固定信心值+既有仲裁
機制跑一次真實驗證，看效果如何，如果效果好但Intro/Outro還是拖累
整體，再另開新Pass評估要不要做動態信心**，不要在這個任務書裡
一次做兩件事。

---

## 4. 接線位置

`module3_bt.py:_run_barstart_v2_comparison()`函式裡的
`v2_core = SequenceNode("BarStartV2CoreChain", [...])`
（約第1026-1046行）——這是唯一需要接線的地方（`build_module3_barstart_v2_pipeline_tree()`
委派呼叫的是同一條主樹，不是獨立的第二份節點清單，已確認）。

新增順序（兩個精確插入點都已確認）：

1. **`MadmomDBNEvidenceExtractNode()`**：放在`module3_bt.py`的
   `v2_core = SequenceNode("BarStartV2CoreChain", [...])`裡，
   `ManualCommittedBarStartsSeedNode()`之後、`FullSongBarStartLoopNode()`
   之前（全曲一次性節點要在迴圈開始前跑完）。
2. **`MadmomDBNCandidateAdapterNode()`**：放進
   `build_module3_barstart_v2_probe_tick_tree()`
   （`module3_barstart_v2_bt.py:3903-3934`，`FullSongBarStartLoopNode`
   每一輪都會重跑這個tick序列）——**`BeatThisCandidateAdapterNode()`
   已經接在這裡**（第3923行，緊接在`V1GridEvidenceBarSearchNode()`
   之後、`ReliableBarAnchorNode()`之前）：

   ```python
   return SequenceNode("BarStartV2ProbeTick", [
       RollingProbeWindowNode(),
       LocalModelRegistryNode(),
       DrumEvidenceBarSearchNode(),
       DrumBassEvidenceBarSearchNode(),
       ChordTrackPKNode(),
       MelodyTrackPKNode(),
       V1GridEvidenceBarSearchNode(),
       BeatThisCandidateAdapterNode(),
       MadmomDBNCandidateAdapterNode(),  # <-- 新增在這裡
       ReliableBarAnchorNode(),
       ...
   ])
   ```

   放在`BeatThisCandidateAdapterNode()`之後即可（`BeatThisCandidateAdapterNode`
   目前沒有上游節點餵`beat_this_downbeats`，永遠是no-op跳過，順序
   不影響madmom）。

---

## 5. 測試要求

新增`tests/test_sdd_pass232.py`：

1. `MadmomDBNEvidenceExtractNode`：mock掉`madmom.features.downbeats`
   （測試環境不應該依賴真的跑madmom，太慢）驗證 (a) 正常回傳時
   正確寫入`madmom_downbeats`/`madmom_beats`；(b) `ImportError`時
   優雅跳過（`SKIPPED_IMPORT_ERROR`，不拋例外）；(c) `audio_path`
   不存在時優雅跳過。
2. `MadmomDBNCandidateAdapterNode`：合成`madmom_downbeats`清單+
   合成既有`bar_start_candidates`，驗證 (a) 靠近既有候選時正確
   boost且不重複新增；(b) 完全沒候選覆蓋的位置正確新增一個獨立
   候選；(c) 一個視窗最多新增一個獨立候選（即使madmom清單裡有
   多個沒被覆蓋的降拍落在同一視窗）。
3. 執行既有回歸測試確認沒有破壞任何東西：
   ```
   C:/Python313/python.exe -m pytest tests/test_sdd_pass232.py tests/test_sdd_pass202.py tests/test_module3_bt.py -q
   ```

---

## 6. 真實資料驗證（必須做，不能只憑單元測試）

1. **先確認madmom環境正常**（第2.1節的環境注意事項）。
2. 用`scratch/run_pass211_promoted_production_verify.py`（或最新
   等效腳本，例如`scratch/run_pass228_grounded_score_production_verify.py`）
   重跑World is Mine的完整管線，記錄：
   - 新的`original_score`/`barstart_v2_score`（Pass228接地後的
     新基準：`original_score=66.5`、`barstart_v2_score=80.66`——
     **這次驗證要看madmom加進來後barstart_v2_score有沒有進一步
     提升**，不能拿舊的88.14/88.47當基準）。
   - 逐段（Intro/Verse1/Chorus1/Outro）跟golden比對的殘差，尤其
     **Chorus1這段的殘差是否真的隨madmom證據加入而改善**（golden
     在Chorus1可信，見Pass227，這段的改善才是真正有意義的訊號）。
   - `full_song_loop_report`裡`madmom_dbn_support`這個
     evidence_sources註記出現的次數/位置，確認madmom證據真的有
     被仲裁機制用到，不是形同虛設。
3. **明確要求**：如果真實資料驗證顯示整體變差（不只是沒進步），
   要如實記錄、revert，不能為了呈現「這個Pass有效果」而勉強接受
   退步的結果——這是整個Pass197-231系列一貫的鐵律。
4. 不需要、也不應該在這個任務書範圍內改動
   `barstart_v2_promotion_approved`的核准邏輯或既有的manual-approval
   安全機制。

---

## 7. 完成後

1. 更新`docs/BT-BUILD-PROGRESS.md`，新增Pass232條目：完整記錄
   設計、測試結果、真實資料驗證的完整數字（新基準vs加madmom後的
   新新基準）、Chorus1是否真的改善、如實記錄任何退步或需要revert
   的部分。
2. 更新使用者記憶檔案（如果是Claude執行的話）：madmom證據層是否
   成功整合、新的分數基準是多少。
3. Commit + push到`origin/worktree-pass171-multi-variant-harness`，
   commit message用`feat(pass232): ...`前綴。
4. **不要在這個任務書範圍內順便做**：(a) 動態信心值機制（第3節已
   明確排除）；(b) 讓madmom也接進Stage3舊版legacy pipeline（這份
   任務書只處理BarStart V2）；(c) 嘗試修Outro的殘餘誤差（golden
   基準本身在那裡就不夠可信，見Pass227，不是這個任務書能解決的
   問題）；(d) 在其他曲目上做量化驗證（沒有golden基準，Pass231
   已經用聽感驗證過泛化性，量化驗證留給有真正需求時再做）。
