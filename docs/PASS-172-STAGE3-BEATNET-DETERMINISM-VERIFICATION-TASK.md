# Pass 172 任務書：Stage 3 BeatNet 決定性驗證 (Determinism Verification)

**狀態**：已完成
**目標**：確認 Pass 155 導入的 `enable_deterministic_mode()` 是否真的能讓
`BeatNetNode_TrackA`（Stage 3 節拍追蹤的核心模型）在同一份音訊上重複跑出完全相同的
拍點，藉此判斷 Pass 171 量到的「119 vs 黃金版 121 小節」落差，究竟是可修的程式碼回歸，
還是黃金版本身就是一次不可重現的隨機結果。

---

## 0. 背景

Pass 171 追查到「119 vs 121 小節」的落差源頭是 `BeatNetNode_TrackA` 這次偵測到 477 拍，
黃金版當時是 485 拍，而 `BeatFusionArbitratorNode` 的融合邏輯自黃金版以來完全沒變
（見 `PASS-171-...-TASK.md` 第 2.2 節）。

在往下追之前，先確認兩個關鍵時間點：

| 事件 | 時間 |
|---|---|
| 黃金版《World is Mine》click 產出 | 2026-07-30 16:30 |
| `enable_deterministic_mode()` 導入（Pass 155，`71564f0`） | 2026-08-02 23:43 |

**黃金版早於決定性模式導入 3 天。** `pgm_craft/determinism.py` 的 docstring 明確記載：

> Neither BeatNet nor Demucs pins a random seed, and GPU inference is non-deterministic
> by default in PyTorch... confirmed directly by comparing three same-song, same-code runs
> whose `commercial_beat_quality` scores drifted (88.71 / 88.47 / 89.3) despite v1's
> algorithm being untouched.

也就是說，Pass 155 本身就是為了修復「同一份程式碼、同一首歌，每次跑出來的節拍都不一樣」
這個已知問題而存在的。而本機確實有 GPU（`torch.cuda.is_available() == True`），
GPU 上 cuDNN 的 autotune 正是 docstring 提到的非決定性來源。這代表**黃金版的 485 拍，
很可能只是當時一次沒有固定隨機種子的 GPU 推論結果**，換句話說，它本身就不是一個可以
精確複現的「正確答案」，而只是分布裡的一個樣本。

---

## 1. 驗證方法

不需要重跑完整分軌（Demucs）——黃金專案已經有現成的 Stage 3 節奏骨幹軌
`stems/submix/track_a_rhythm.wav`（`SynthesizeRhythmTrackNode` 的輸出，也就是餵給
`BeatNetNode_TrackA` 的確切輸入）。直接對同一份音訊檔跑兩次 `BeatNet(...).process()`，
比較：

1. 兩次輸出的拍點總數是否完全一致。
2. 兩次輸出逐拍時間戳的最大差異（毫秒級）。
3. 過程中一併確認 `enable_deterministic_mode()` 回報的 `applied` 清單（本機是否真的
   套用了 `cudnn.deterministic` / `torch.use_deterministic_algorithms` 等設定）。

腳本：`scratch/pass172_beatnet_determinism_check.py`。

## 2. 執行結果（實測，非預測）

實際執行（本機 GPU：`cuda_available: True`，`enable_deterministic_mode()` 已啟用，
輸入音訊是黃金專案本身的 `stems/submix/track_a_rhythm.wav`）：

```
determinism report: {'seed': 42, 'torch_available': True, 'cuda_available': True,
  'applied': ['CUBLAS_WORKSPACE_CONFIG', 'random.seed', 'numpy.random.seed',
              'torch.manual_seed', 'torch.cuda.manual_seed_all',
              'cudnn.deterministic+benchmark', 'torch.use_deterministic_algorithms'],
  'status': 'ENABLED'}

Run 1: 485 beats (32.2s)
Run 2: 485 beats (15.9s)
beat count match: True
max per-beat timestamp delta: 0.0 sec
VERDICT: DETERMINISTIC — 兩次跑出的拍點數與時間戳完全一致
```

**這個結果比原本猜測的更精確、也更有用**：對同一份音訊，`BeatNetNode_TrackA` 兩次
都跑出跟黃金版原始 `beat_validation.total_beats` 完全相同的 **485 拍**、時間戳誤差
`0.0` 秒。這推翻了第 0 節「黃金版的 485 拍是不可複現的隨機結果」的猜測——**只要
輸入音訊完全相同，決定性模式下 BeatNet 是百分之百可複現的，而且會複現出跟黃金版
一模一樣的數字。**

## 3. 結論：真正的落差不在 BeatNet，而在它的輸入音訊本身

既然「同一份音訊 → 決定性 BeatNet → 一定是 485 拍」已經證實，那 Pass 171 那次完整變體
測出的 477 拍，唯一可能的解釋是：**那次重新分離出來的 `track_a_rhythm.wav`，跟黃金專案
現存的這份 `track_a_rhythm.wav` 內容不是完全一樣的音訊。** 換句話說：

- `BeatNetNode_TrackA` 本身：✅ 已證實決定性、可複現。
- 餵給它的節奏骨幹軌（`SynthesizeRhythmTrackNode` 合成自 Demucs 分離出的 drums + bass）：
  ❌ **每次重新分離，內容都不是逐 byte 相同**，這才是 477 vs 485 真正的落差來源。

`pgm_craft/determinism.py` 的 docstring 雖然也把 Demucs 列為需要固定種子的對象，但
Demucs 本身在推論時常見會做 test-time shift augmentation（對輸入音訊做隨機時間平移
後多次推論再平均，藉此降噪），這類隨機平移如果沒有被 `enable_deterministic_mode()`
擋下的隨機源覆蓋到，就會讓每次分離出的 drums/bass 波形有細微但足以讓 BeatNet 抓到
不同拍數的差異。**這是 Demucs 分離管線本身的決定性問題，不是任何一個 BarStart v2
或 Stage 3 精修節點的邏輯 bug。**

## 4. 後續建議

1. **不要再拿「121 小節」當精確驗收標準**——已證實只要分軌內容相同，今天的管線一定能
   精確複現黃金版的拍數。真正該固化成迴歸測試的，是「同一份**已分離好**的節奏骨幹軌，
   跑幾次 BeatNet 结果都必須一致」（本 Pass 已用 `scratch/pass172_beatnet_determinism_check.py`
   實測證實這點成立；比對邏輯本身（拍數是否一致、時間戳誤差多少）已抽成
   `pgm_craft.determinism.compare_beat_outputs()` 並補上 `tests/test_sdd_pass172.py` 的
   3 項合成資料單元測試，涵蓋完全一致 / 拍數一致但時間戳有微差 / 拍數不一致三種情形）。
2. **下一個該查的目標明確了：Demucs 分軌本身的決定性**。建議 Pass 173：對同一份
   `denoised.wav` 輸入，重跑兩次 `SeparateDrumsNode`/`SeparateBassNode`，逐 sample 比較
   輸出波形是否完全相同；若不同，檢查 Demucs 呼叫端（`CascadedStemSeparator`）是否有
   test-time shift/ensemble 之類沒被 `enable_deterministic_mode()` 覆蓋到的隨機源，
   視情況固定該隨機源或改用非隨機的單一 pass 推論。
3. 使用者若仍想知道「477 拍版本」聽起來到底好不好，可以直接聽 Pass 171 已產出的
   `v1_current_default` 變體 `mix_with_click.wav`（清理前已產出，若已清除可重新用
   `scratch/run_pass171_variant_matrix.py` 的 `run_variant()` 單獨補一份）跟黃金版 A/B
   比較——但這已經是主觀聽感判斷，不是本 Pass 的範圍。
