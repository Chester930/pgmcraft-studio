# Pass 174 任務書：修復 Demucs 分軌決定性（呼叫前重新 Seed）

**狀態**：已完成
**目標**：修復 Pass 173 找到的根因——`CascadedStemSeparator._demucs_separate()` 呼叫
`apply_model()` 時吃 demucs 套件預設的 `shifts=1`（隨機時間平移 test-time
augmentation），而 `enable_deterministic_mode()` 只在 pipeline 啟動時 seed 一次，
沒有覆蓋到每次 `apply_model()` 呼叫都會消耗的這個隨機源，導致同一份輸入音訊每次
重新分離都不是同一份（Pass 173 實測 max_abs_diff = 0.234）。

---

## 0. 修復方向的取捨

Pass 173 任務書列了兩個選項：

1. **每次呼叫前重新固定隨機種子**：保留 `shifts=1` 的 SDR 品質增益（+0.2 dB），
   同時讓「隨機」平移量在每次呼叫時都是同一個值，達成 run-to-run 決定性。
2. **直接關閉 `shifts`（改成 0）**：完全放棄隨機平移增益，換取更快、更簡單的決定性。

選擇方案 1——不用犧牲既有的分離品質，且改動幅度更小（只在既有的決定性框架
`pgm_craft/determinism.py` 上加一個函式，呼叫端加一行）。

## 1. 實作

### 1.1 `pgm_craft/determinism.py` — 新增 `reseed_for_inference()`

```python
def reseed_for_inference(seed: int = None) -> None:
    """在單次會自行消耗隨機性的推論呼叫（例如 Demucs apply_model() 的
    shifts>0 test-time augmentation）前重新固定所有 RNG 來源，讓該次呼叫
    「隨機」抽到的值在每次執行時都相同。"""
```

`enable_deterministic_mode()` 額外記錄 `_LAST_SEED`，`reseed_for_inference()`
預設沿用同一個種子，呼叫端也可以覆寫。

### 1.2 `pgm_craft/separator.py` — `_demucs_separate()` 呼叫前重新 seed

```python
reseed_for_inference()
with torch.no_grad():
    sources = apply_model(model, wav, progress=True)[0]  # [n_stems, 2, T]
```

這是專案裡唯一呼叫 `apply_model()` 的地方（已用 `grep` 確認），所以這一行涵蓋了
全部的 Demucs 分離路徑（4-stem 通用分離、drums、bass、6-stem 吉他/鋼琴等）。

## 2. 驗證方法與結果

`scratch/pass174_demucs_reseed_fix_verification.py`：用真正的
`CascadedStemSeparator._demucs_separate()`（不是繞過快取直接呼叫
`apply_model()`，而是走 Pass 174 修好之後的真實程式碼路徑），對黃金專案的
denoised 來源音訊，分別輸出到兩個不同的 `output_dir`（避開物件內建的
`_demucs_cache`，逼出兩次真正獨立的推論），比對兩次的 `drums.wav`。

實測輸出（走修復後的真實程式碼路徑，兩個獨立 output_dir，逼出兩次真正獨立推論）：

```
[drums] sr_match=True bit_exact=True max_abs_diff=0.0
[bass]  sr_match=True bit_exact=True max_abs_diff=0.0

VERDICT: 修復成功 — reseed_for_inference() 讓連續兩次 Demucs 分離
（走真實 CascadedStemSeparator._demucs_separate() 程式碼路徑）完全 bit-exact。
```

## 3. 結論

**修復生效**。跟 Pass 173 的基準（`shifts=1` 未修復時 max_abs_diff=0.234）對照：
同一套 `shifts=1` 設定、同一份輸入音訊，加上 `reseed_for_inference()` 後，
drums.wav 與 bass.wav 連續兩次分離的最大絕對誤差從 `0.234` 降到 `0.0`，
完全 bit-exact，且沒有放棄 `shifts=1` 帶來的 SDR 品質增益。

這代表從 Pass 171 開始追查的「477 vs 黃金版 485 拍」落差鏈，源頭（Demucs 分軌
不可複現）已經修復。往後只要 `enable_deterministic_mode()` 有被呼叫過（正式
pipeline 的 `PGMCraftEngine.__init__` 預設就會呼叫），同一首歌重新產生 click
應該會得到完全一致的小節數與 BPM 曲線——不會再像 Pass 171 那樣，重新分離就多丟
2 個小節。

`tests/test_sdd_pass174.py`（4 項）驗證 `reseed_for_inference()` 本身的行為：
呼叫後 `random` / `numpy` 的下一次隨機抽樣在兩次呼叫之間完全一致、不同種子會
抽到不同值、未帶種子時會沿用 `enable_deterministic_mode()` 記錄的種子。

## 4. 後續建議

1. 這個修復只涵蓋 Demucs 分離這一個隨機源。若之後在其他地方也發現「同一份輸入、
   同一套程式碼，兩次執行結果不同」的情況，優先檢查是不是又出現了「只在 pipeline
   啟動時 seed 一次，但呼叫點本身也會消耗隨機性」的同類模式，直接重用
   `reseed_for_inference()`。
2. 建議把「同一首歌完整跑 2 次，`measure_map` 小節數與 `commercial_beat_quality`
   分數必須完全一致」固化成一個長跑（需要 2×23 分鐘）迴歸測試，作為這整條
   Pass 171-174 調查的最終驗收，但因為耗時長，建議只在明確需要驗證決定性改動時
   手動執行，不放進日常 CI。
