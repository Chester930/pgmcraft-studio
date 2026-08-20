# Pass 203 任務書：診斷「為什麼證據融合幾乎每小節都達不到 0.7 commit 門檻」

**狀態**：問題已量化確認（85% 小節無法靠真正證據 commit），但確切
原因尚未診斷——這是一個診斷型任務，**產出是一份根因報告，不是一次
修復**。可轉交 Codex CLI 執行，執行方式必須比照這個系列已經驗證過
有效的做法：即時 instrumentation 抓真實資料，不要憑程式碼邏輯猜測。

---

## 0. 背景

Pass 199 真實資料回驗（`docs/PASS-199-BARSTART-V2-FULL-SONG-LOOP-STALL-TASK.md`
第 5 節）確認：124 個 commit 的小節裡，只有 18 個（15%）是
`BarStartCandidateCommitNode` 真正靠鼓組/貝斯/和絃證據達到 0.7
信心門檻獨立判斷出來的，其餘 85% 都要靠 fallback carry（複製 v1
舊網格）撐過去。

**這是比 Pass 199 原本規格（修好全曲卡死）更根本的問題**：就算
Pass 201/202 都修好了，只要真正的證據判斷成功率還是只有 15%，
BarStart V2 整體上就還是「大部分時間在抄舊資料」，不會是真正獨立、
可信的新方法。

目前完全不知道 15% 這個數字的具體原因是什麼——可能是：
（a）信心公式本身校準得太保守（例如 `DrumEvidenceBarSearchNode` 的
base_confidence 0.55 太低，就算間距完全吻合也很難疊加到 0.7）；
（b）各證據來源彼此很少同時觸發（例如鼓組候選存在時，貝斯/和絃剛好
都沒有對應證據可以疊加信心）；（c）這首歌的音色特性本來就不利於
這套證據邏輯（例如人聲/合成器編曲比重高，傳統鼓點型態不明顯）；
（d）某個地方有還沒發現的實作 bug，類似這系列已經連續發生四次的
「看起來合理但真實資料上會暴露」的門檻/邏輯問題。

**在不知道是哪一種之前，不應該貿然調整任何信心公式的參數**——這
系列已經用血淋淋的教訓證明，憑感覺調參數不看真實資料驗證會出事
（Pass 197 threshold bug、Pass 198B 級聯）。

---

## 1. 診斷方法：即時 instrumentation（比照 Pass 198B / Pass 199 的做法）

### 1.1 埋點位置

在 `BarStartCandidateCommitNode.execute`（`pgm_craft/workflow/module3_barstart_v2_bt.py:975`）
加上暫時的 debug 埋點（用完要還原，不要留在最終 commit 裡，比照
Pass 198/199 診斷時的做法），記錄**每一個 tick**：

1. `active_bar_probe_window`（這次搜尋的時間範圍）。
2. **所有候選的完整清單**（不只是 `best`），每個候選的
   `evidence_sources`、`confidence`、`time`——不能只記錄最後選中的
   那一個，要能看到「這個 tick 到底有幾個候選、分別多少分、是哪個
   證據來源給的」。
3. 各個上游證據節點（`DrumEvidenceBarSearchNode`、
   `DrumBassEvidenceBarSearchNode`、`ChordTrackPKNode`、
   `MelodyTrackPKNode`、`V1GridEvidenceBarSearchNode`）**各自**在
   這個 tick 有沒有產生候選、產生了幾個——用來分辨「完全沒有任何
   證據來源觸發」還是「有觸發但信心不夠疊加到 0.7」。
4. 最終 `threshold`（0.7）、`best candidate` 的信心分數、是否
   commit 成功。

### 1.2 執行

對測試曲目跑一次完整的 `target_stage="module3"` 管線（比照
`scratch/run_pass198_default_pipeline_reverify.py` 的模式，衍生成
`scratch/run_pass203_evidence_fusion_diagnosis.py`），把埋點資料
寫成結構化的 `scratch/debug_pass203_evidence_trace.jsonl`（一行一個
tick）。

### 1.3 分析

1. 統計：318 次 tick（Pass 199 真實案例的迭代次數）裡，各證據來源
   分別觸發了幾次、平均信心多少。
2. 對「有觸發但沒達到 0.7」的 tick，看差距多少——是普遍差一點點
   （例如 0.5-0.65，代表門檻或信心公式可能真的偏保守），還是差很多
   （例如 0.1-0.3，代表證據來源本身根本沒抓到東西，門檻調整不會有
   幫助）。
3. 對「完全沒有任何候選」的 tick，對照這些時間點落在歌曲的哪個
   段落（人聲清唱？過門？副歌高潮？），看是不是集中在已知的證據
   薄弱段落（8.041s、97.197s 那種），還是全曲普遍都很少觸發（如果
   是後者，代表問題比我們原本以為的更廣泛，不只是那幾個已知弱證據
   段落）。

---

## 2. 安全機制

1. **這是診斷任務，不是修復任務**——即使診斷過程中發現「調某個
   參數看起來就會變好」，也不要在這個任務書範圍內直接改，先把診斷
   報告寫完整、回報使用者，讓使用者決定要不要另開任務書調整。
2. **診斷用的 instrumentation 用完要還原**（比照 Pass 198B/199 的
   做法），不要留在正式程式碼裡。
3. **不要只看統計平均值**——這系列已經證明「聚合數字看起來合理」
   不代表沒問題，診斷報告要包含具體的個案範例（挑幾個代表性的
   tick，完整列出當時的候選跟信心），不能只給統計摘要。

---

## 3. 交付物

一份診斷報告（可以是獨立的 markdown 文件，或寫進
`docs/BT-BUILD-PROGRESS.md` 新增的 Pass 203 條目），至少要回答：

1. 15% 的真正 commit 成功率，具體卡在信心公式的哪一段（普遍差一點
   點 vs 完全沒證據）？
2. 哪個證據來源觸發率最低？是不是有某個來源幾乎從來沒有成功產生
   候選（代表它可能有 bug，或這首歌的編曲類型完全不適合這個證據
   來源）？
3. 「完全沒有任何候選」的 tick，是集中在已知的少數弱證據段落，還是
   全曲普遍分布？
4. 根據以上發現，給出下一步建議的具體方向（例如：「應該調高某個
   證據來源的 base_confidence，因為它常態性只差 0.05-0.1 就達標」
   或「應該放棄某個證據來源，因為它整首歌只觸發過 2 次」或「問題不
   在信心公式，是這首歌的編曲特性本來就不利於這套方法，應該考慮
   Pass 200 的 `beat_this` 路線」）——**不要在這個任務書裡直接動手
   實作這個建議，留給使用者確認方向後再開下一個任務書**。

---

## 4. 執行結果

Codex 原本的執行也卡在 Pass 200 同一個「找不到指定 WAV」的問題，已
比照 Pass 200 修正路徑（改指向 `pass198_default_pipeline_reverify`
的複製版本）解決。**第一次跑完後發現用的還是 Pass 198B 那個有 bug、
92% 假插值的舊網格**（見 Pass 198 任務書第 9 節追記——那個規格要求
刪除的程式碼其實從來沒被刪掉，已經在這次順手修正並確認 51 個測試
通過），所以**用修正後的乾淨基準又重跑一次**，兩次的證據觸發統計
結果完全一致，代表這個發現跟 v1 網格乾不乾淨無關，是真的。

### 4.1 只跑到 9 個 tick（覆蓋 0-52 秒）就停了，不是全曲

`FullSongBarStartLoopNode` 的卡住/停止機制在這裡也提前觸發（跟
Pass 199 診斷過的機制一樣：連續 3 次沒 commit 就檢查
`provisional_bar_starts`），這次的診斷腳本沒有像 Pass 199 那樣繼續
往後追蹤完整迴圈，**只捕捉到全曲前 52 秒、9 個 tick 的資料，不是
完整 176 秒**。以下結論的適用範圍僅限於這段，不能直接推論到全曲。

### 4.2 逐 tick 明細

```
tick=1 window=2.0-7.0     UNRESOLVED best_conf=0.45 sources=[drums, drum_onset, outside_fill_exclusion]
tick=2-6                  COMMITTED（正常推進）
tick=7 window=31.1-37.1   UNRESOLVED best_conf=0.60 sources=[drums, kick, snare_backbeat_support,
                                                                exclusion_penalty, bass_coincidence_support,
                                                                phrase_anchor_support]
tick=8 window=37.1-44.1   UNRESOLVED best_conf=0.60（同上，候選卡住，視窗一直往後擴大找不到更好的）
tick=9 window=44.1-52.1   UNRESOLVED best_conf=0.60（同上，第三次卡住，觸發 stall 機制）
```

### 4.3 「證據來源觸發次數為 0」不是 bug，是分類方式的誤解

`drum_bass`/`chord`/`melody`/`beat_this` 四個來源在統計表裡都是 0
次獨立候選——**但看 tick 7-9 的候選細節，`evidence_sources` 裡明明
包含 `bass_coincidence_support`、`phrase_anchor_support`**！矛盾的
原因：這些證據**設計上就是拿來當「加成」，附著在鼓組候選上提高
信心，不是自己產生獨立候選**（跟第一輪 fork 調查 `DrumBassEvidenceBarSearchNode`
的文獻對照結果一致：貝斯/和絃/旋律的信心上限本來就被設計成低於 0.7、
要靠疊加才能過關）。診斷腳本用「找候選來源名稱裡有沒有
`drum_bass`/`chord`/`melody` 字樣」這種方式統計，**沒有偵測到「作為
加成 tag 附著在別的候選上」這種情況，統計方法本身有誤判**，不代表
這些證據來源真的完全沒運作。

### 4.4 真正的發現：卡住的候選是「有疊加但還是差一點」，不是「完全沒證據」

tick 7-9 的最佳候選已經疊加了 kick + snare 反拍 + 貝斯重合 + 旋律
樂句支持**四種證據**，信心還是只有 0.60，離 0.7 差 0.1——**這比較
接近任務書第 0 節列的「分支 C」（普遍差一點點，可能是信心公式本身
偏保守），不是「分支 D」（某個來源完全不觸發）**。但因為只覆蓋了
52 秒（一個候選卡住 3 個 tick 都沒變化，樣本量很小），**這個結論
還需要一次涵蓋全曲的完整診斷才能確認是不是全曲通則**，不能只憑
這 9 個 tick 下定論。

### 4.5 建議（不是最終決定，留給 Pass 204）

1. 這次的觀察比較接近分支 C（信心公式可能偏保守），但樣本太小
   （52 秒/9 tick），建議 Pass 204 決定往這個方向前，先跑一次不會
   提前終止的完整診斷（例如暫時放寬 `stall_limit`，讓迴圈continue
   往後探索，即使最終還是不會 commit，至少能收集到全曲的信心分布，
   不是只有卡住那一段）。
2. 第 4.3 節的統計方法缺陷應該先修（改成同時偵測「獨立候選」跟
   「附著在別的候選上的支持 tag」兩種情況），不然之後任何一次重跑
   都會得到一樣誤導人的「0 次觸發」數字。

---

## 5. 全曲版重跑：真正的根因，比原本猜測精確很多

修好第 4.3/4.5 節的兩個問題後（統計方法改用精確標籤比對；暫時把
`FullSongBarStartLoopNode` 的 `stall_limit` 拉高到 10000，只在這次
診斷的實例生效，不影響正式管線預設行為），重新跑了一次涵蓋全曲的
版本。**結果推翻了先前「偏向分支 C」的初步判斷——真正的問題是一個
具體、局部、範圍遠大於已知弱證據段落的斷層，不是全曲信心公式普遍
偏低**。

### 5.1 逐 tick 精確定位

```
tick 1-6：正常推進，成功 commit 到 31.103129s（第 6 個小節起點）
tick 7-13（31.1s → 94.1s，約 63 秒）：confidence_below_threshold
  ——這段完全沒有任何候選能達到 0.7 信心，不是「差一點點」，是真的
  不夠。這個斷層長度（63 秒）遠遠超過先前已知的任何一個弱證據段落
  （8.041s 附近的近乎清唱段落也才 4-5 秒）。
tick 14-20（94.1s → 166.1s）：quality_regression
  ——這段反而出現多個信心 1.0（滿分）的候選，但因為上一個確認的
  小節還卡在 31.1s，任何跳到 94s+ 的候選都代表「小節長度」暴增
  60 幾秒，系統正確地判斷這是嚴重的品質倒退而拒絕 commit，不是
  bug，是安全機制正常運作。
tick 21-500（178.1s 之後，遠遠超過全曲 176 秒的實際長度）：
  no_candidates——因為第 7-20 tick 都沒有真的往前推進小節序列，
  搜尋視窗本身卻持續往後滑動，滑到超出全曲長度之後理所當然找不到
  任何東西，一路耗到 500 次迭代上限。**這是這次診斷改動（拉高
  stall_limit）額外暴露出的一個既有邏輯缺口**：`FullSongBarStartLoopNode`
  判斷「是否已經到達全曲結尾」的依據是「最後一次成功 commit 的
  小節時間」，不是「目前搜尋視窗的位置」——正常情況下 `stall_limit=3`
  會在卡住幾次之後就觸發卡住/回退機制而提前結束，不會真的探索到
  超出全曲長度的地方，所以正式管線不會被這個缺口影響；但如果之後
  要調整 stall 相關邏輯，這個「用最後 commit 位置判斷是否結束」而
  非「用目前搜尋位置判斷」的設計要留意。
```

（統計數字加總：480 個 `no_candidates` + 8 個 `confidence_below_threshold`
+ 7 個 `quality_regression` + 5 個成功 commit = 500 個 tick。）

### 5.2 結論：31.1s 之後有一個約 63 秒的真空斷層，不是全曲證據普遍偏弱

跟第 4.4 節「傾向分支 C」的初步判斷不同，全曲版數據顯示：**問題
高度集中在 31.1s 到 94s 這一段，不是全曲性的信心公式偏保守**。
在斷層之前（0-31s）跟斷層之後證據恢復（94s+，甚至到滿分信心）都
正常，只有這中間 63 秒完全沒有任何來源能單獨或疊加後達到 0.7。

這也解釋了 Pass 199 診斷 `NoDrumPhaseCarryNode` 卡住時看到的現象
（`next_anchor` 卡在 `12.376236` 不動、跟這裡 `anchor_time` 卡在
`31.103129` 不動是同一種病灶在不同的具體位置發作）——BarStart V2
的「一次一小節、需要獨立高信心證據」的設計，對這首歌某些段落
（不只是先前已知的 8.041s/97.197s 那種明顯的人聲清唱/過門段落）
會出現比想像中更大範圍的真空。**這比較接近任務書原本分支選項裡的
「分支 E」精神（範圍比已知弱證據段落大得多），但不是「全曲普遍」，
是一個具體、有明確起訖時間的區間性斷層**，兩者的下一步處理方式
不同（分支 E 建議暫停整個 BarStart V2 路線；這裡更像是需要
`InterveningBarCountEstimatorNode`／`BidirectionalBarAlignmentNode`
這類「跨多小節搭橋」機制真正發揮作用，卻在這個具體案例失靈了，
值得先查清楚為什麼「跨橋」沒有在 94s 那批滿分候選出現時被觸發，
而不是直接放棄整條路線）。

### 5.3 給 Pass 204 的具體建議

1. **不要直接套用分支 C 的「調校信心公式」方向**——這次全曲資料
   顯示信心公式本身在有證據的地方運作正常（甚至能給到滿分），
   問題不在校準，在「31-94s 這一段的證據來源本身找不到東西」，跟
   「跨小節搭橋機制沒有在 94s 找到解法時被正確觸發」。
2. 下一步建議：針對 31.1s-94s 這個具體區間做更細的個案調查——這裡
   究竟是真的鼓組/貝斯/和絃都安靜（矛盾點：我們自己的 legacy 管線
   在這段有正常偵測到拍點，代表音訊本身不是完全沒特徵，只是
   BarStart V2 這套以鼓組為主的證據邏輯抓不到）；同時追查
   `InterveningBarCountEstimatorNode`/`BidirectionalBarAlignmentNode`
   為什麼沒有在 94s 出現滿分候選時，正確估算「31.1s 到 94s 之間
   該有幾個小節」並嘗試搭橋，而是直接判定為品質倒退放棄。
3. 這兩點都需要新的、範圍更小更精確的任務書，不是延續 Pass 203
   原本設計的「找信心公式哪裡偏低」方向。

---

## 6. 修正（同一系列後續調查）：31-94s 斷層不是證據真空，是 Pass 202 仲裁邏輯自己的 bug

**第 5 節「31-94s 證據真空斷層」的結論已被推翻。** 針對使用者
「針對 31-94s 這個斷層繼續深入調查」的指示，重新檢視 tick 7-13 的
完整候選清單（不是只看最終 `best_candidate`），發現：

- 這幾個 tick 的搜尋視窗裡**每一個都存在信心 1.0 的候選**（例如
  tick 7 視窗裡的 `bar_start_candidate_20`，time=33.750204，
  confidence=1.0）——跟第 5 節「這段完全沒有任何候選能達到 0.7
  信心」的描述**直接矛盾**。
- 真正發生的事：`BarStartCandidateCommitNode._best_candidate`
  （`pgm_craft/workflow/module3_barstart_v2_bt.py:1091`）的仲裁排序
  把 `phase_consistency_score` 放在**主排序鍵**，`confidence` 只是
  次要排序鍵——這代表只要某個候選跟已 commit 的小節序列「相位」對得
  上，就算它的原始信心遠低於 0.7 門檻，也會贏過同一視窗裡信心
  1.0、只是相位分數略低的候選。tick 7 實際勝出的是
  `bar_start_candidate_21`（time=34.017234, confidence=0.6,
  phase_consistency_score=0.728582），不是任何一個信心 1.0 的候選。
- 根本原因是 `_conflicting_candidates`（同檔 1217 行）把「一個 bar
  duration（約 1.45 秒）之內的任意兩個候選」都判定為互斥衝突——但
  探測視窗寬達 6-12+ 秒，天生會同時包含好幾個**合法、依序排列的
  真實小節候選**，這些候選彼此之間本來就不是「同一小節的重複」，
  而是「下一個小節、下下個小節……」，被過度寬鬆的衝突判定誤判成
  必須互相淘汰的競爭者，讓仲裁機制反過來壓制了原本能直接達標的
  高信心候選。

換句話說：**根本不存在證據真空**，31-94s 這段音訊的鼓組/貝斯/和絃
證據運作正常（甚至能給到滿分），問題出在 Pass 202 自己新增的仲裁
邏輯，用相位一致性覆蓋了信心門檻本身的判斷。

### 6.1 已完成的修復（Claude 直接實作並驗證，未經 Codex）

`_best_candidate` 簽名新增 `commit_threshold` 參數，勝出排序鍵改為
`(是否達到 commit_threshold, phase_consistency_score, confidence,
-time)`——`clears_threshold` 現在是**第一優先**排序鍵，只有在同一
衝突組裡**沒有任何候選達到門檻**時，才會退回原本「用相位分數決定
勝負」的行為（這保留了 Pass 202 原始測試
`test_close_conflict_uses_committed_phase_consistency` 的既有語意：
兩個候選都達標時，相位分數合理地決定要選哪一個）。呼叫端
（`BarStartCandidateCommitNode.execute`，同檔 969 行）已改為把
`threshold` 傳入 `_best_candidate`。

新增兩個回歸測試（`tests/test_sdd_pass202.py`）：
- `test_threshold_clearing_candidate_beats_phase_only_preference`：
  重現這次確認的真實 bug 場景（一個相位完美但信心不足的候選，輸給
  另一個相位稍差但信心達標的候選）。
- `test_no_threshold_clearing_candidate_falls_back_to_phase_score`：
  確認「同組都沒人達標」時，舊行為（相位分數決勝）不受影響。

`tests/test_sdd_pass202.py`、`tests/test_module3_bt.py`、既有全部
21 個相關測試，以及涵蓋 barstart/module3/pass19x/pass20x 的 91 個
測試全數通過。

### 6.2 修復後全曲重跑：暴露出第二個、先前被這個 bug 掩蓋的問題

用修好的仲裁邏輯重新跑一次 `scratch/run_pass203_evidence_fusion_diagnosis.py`
全曲診斷，31-94s 這段的仲裁確實改選到高信心候選了（`winner_cleared_threshold=True`，
勝出信心從 0.52-0.6 提升到 0.72-1.0），**但這並沒有讓 loop 恢復正常
推進**——新的全曲結果是 500 tick 裡只成功 commit **1 次**（比修
之前的 5 次還少）。

原因：`BarStartCandidateCommitNode.execute` 裡的 `quality_regression`
安全機制（`_score_bar_start_list_quality`，同檔 881 行；比較
`quality_before`/`quality_after` 的小節間距標準差）現在變成新的主要
瓶頸。具體數據（tick 2/3/6/10，`committed` 從 tick 1 之後就再也沒有
成長過，`quality_before` 因此固定在 0.9197）：

| tick | 候選時間 | 信心 | quality_before | quality_after | 結果 |
|---|---:|---:|---:|---:|---|
| 2 | 6.616259 | 0.94 | 0.9197 | 0.7663 | quality_regression 拒絕 |
| 3 | 12.376236 | 1.00 | 0.9197 | 0.2199 | quality_regression 拒絕 |
| 6 | 32.382177 | 0.72 | 0.9197 | 0.0000 | quality_regression 拒絕 |
| 10 | 70.535193 | 0.72 | 0.9197 | 0.0000 | quality_regression 拒絕 |

這是一個自我鎖死的迴圈：只要有一次 commit 因故失敗（例如中間某個
小節本身證據被 fill/exclusion 排除），下一個「真正正確」的候選跟
`committed` 最後一筆之間的間距，就會是預期小節長度（約 1.45s）的
好幾倍——`_score_bar_start_list_quality` 只看**原始**相鄰間距的
標準差，不知道中間有「已知的、被跳過的小節」，把這種合理的多小節
跳躍當成嚴重的節奏不穩定，於是永遠拒絕，`committed` 從此凍結，
`quality_before` 也永遠不會再改善——形成惡性循環。**這個問題先前
被 Pass 202 的仲裁 bug 掩蓋了**：修之前，仲裁本身就常態性選到跟
上一個 commit 只差一個 bar 的低信心候選（因為 `_conflicting_candidates`
限定在一個 bar duration 之內），所以很少真的觸發需要跨越多個小節
的 quality_regression 情境；修好仲裁之後，`_best_candidate` 老實
選出真正正確、但離上次 commit 有好幾個 bar 遠的候選，quality
regression 機制才第一次被大量觸發。

**下一步任務書見 `docs/PASS-205-BARSTART-V2-QUALITY-REGRESSION-GATE-TASK.md`。**
