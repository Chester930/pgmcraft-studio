# Pass 173 任務書：Demucs 分軌決定性驗證 (Demucs Separation Determinism)

**狀態**：已完成
**目標**：驗證 Pass 172 的假設——「477 vs 黃金版 485 拍」的落差，根源是 Demucs
（`htdemucs_ft`）重新分離同一份音訊時輸出的 drums/bass 波形不是逐 sample 相同，
而不是 BeatNet 或任何節拍追蹤/BarStart v2 節點的邏輯問題。

---

## 0. 背景

Pass 172 已經證實：`BeatNetNode_TrackA` 對同一份節奏骨幹軌（`track_a_rhythm.wav`）
兩次推論，結果 100% 一致（485 拍、時間戳誤差 0.0 秒）。既然 BeatNet 本身是決定性的，
Pass 171 那次重新分離、重新產生的 `track_a_rhythm.wav` 卻讓 BeatNet 只抓到 477 拍，
唯一合理的解釋就是：**那份重新分離出來的音訊內容，跟黃金專案現存的那份不是同一份。**

## 0.1 找到具體機制（靜態比對，未跑模型）

檢查 `pgm_craft/separator.py::CascadedStemSeparator._demucs_separate()`：

```python
sources = apply_model(model, wav, progress=True)[0]  # [n_stems, 2, T]
```

呼叫 `demucs.apply.apply_model()` **沒有指定 `shifts` 參數**。查詢本機安裝的
`demucs.apply.apply_model` 簽名：

```python
def apply_model(model, mix, shifts: int = 1, split: bool = True, ...):
    """
    shifts (int): if > 0, will shift in time `mix` by a random amount between
        0 and 0.5 sec and apply the opposite shift to the output. This is
        repeated `shifts` time and all predictions are averaged. This
        effectively makes the model time equivariant and improves SDR by up
        to 0.2 points.
    """
```

**`shifts` 預設值是 1**——代表每次呼叫 `apply_model()` 都會用亂數決定一個 0~0.5 秒
的時間平移量，對輸入做一次隨機平移再推論。`pgm_craft/determinism.py` 的
`enable_deterministic_mode()` 只在 pipeline **啟動時**呼叫一次
`torch.manual_seed(42)`／`numpy.random.seed(42)`，之後每呼叫一次 `apply_model()`
都會從當前的 RNG 狀態繼續往下取亂數——**同一個 process 內連續兩次分離，或是
不同 process/不同呼叫順序，都會拿到不同的隨機平移量**，因此輸出波形不會逐 sample
相同，也就難怪下游 BeatNet 抓到的拍數不一樣。這跟 Pass 172 的實測完全吻合。

還有一個附帶發現：`_demucs_separate()` 內建 `self._demucs_cache`（依
`(abs_path, file_size, model_name, output_dir)` 為 key 的記憶體快取），**同一個
`CascadedStemSeparator` 實例、同一個 `output_dir` 連續呼叫兩次會直接命中快取、
回傳完全相同的結果**——這只是省算力的捷徑，不代表 Demucs 本身決定性；驗證時必須
換一個 `output_dir`（或換一個全新的 `CascadedStemSeparator` 實例）才能繞過快取、
真正逼出兩次獨立推論。

## 1. 驗證方法

`scratch/pass173_demucs_determinism_check.py`：

1. 啟用 `enable_deterministic_mode()`（跟正式 pipeline 一致）。
2. 對黃金專案的 denoised 來源音訊（`source/..._denoised.wav`），用同一個
   `CascadedStemSeparator` 實例、但**兩個不同的 output_dir**（繞過快取），各呼叫一次
   `_demucs_separate(..., "htdemucs_ft", {"drums", "bass"})`。
3. 逐 sample 比較兩次的 `drums.wav` / `bass.wav`：是否完全相等、最大絕對誤差多少。
4. 對照組：把 `apply_model` 的 `shifts` 強制設為 `0`（不做隨機平移），同樣跑兩次，
   驗證是否因此變成逐 sample 相同——藉此確認「隨機平移」就是決定性缺口的真正來源，
   而不是其他原因（例如 cudnn 非決定性 kernel）。

## 2. 執行結果（實測，非預測）

對黃金專案的 denoised 來源音訊，用 `htdemucs_ft` 模型跑 `apply_model()`：

```
determinism report: {'seed': 42, 'torch_available': True, 'cuda_available': True,
  'applied': ['CUBLAS_WORKSPACE_CONFIG', 'random.seed', 'numpy.random.seed',
              'torch.manual_seed', 'torch.cuda.manual_seed_all',
              'cudnn.deterministic+benchmark', 'torch.use_deterministic_algorithms'],
  'status': 'ENABLED'}

[shifts=1] bit_exact=False  max_abs_diff=0.23415576
[shifts=0] bit_exact=True   max_abs_diff=0.00000000
```

`shifts=1`（目前 pipeline 的實際預設，因為 `_demucs_separate()` 呼叫
`apply_model()` 時沒有傳 `shifts` 參數）連續兩次分離**不是 bit-exact**，最大絕對
誤差達 `0.234`（音訊振幅正規化在 -1~1 之間，這是相當顯著的差異，足以讓下游 BeatNet
偵測出不同的拍子數）。`shifts=0`（強制關閉隨機時間平移）連續兩次分離**完全
bit-exact**，誤差 `0.0`。

## 3. 結論：假設完全成立

**Demucs 的 random-shift test-time augmentation（`shifts=1`，demucs 套件本身的預設值）
就是 Pass 171「477 vs 黃金版 485 拍」落差的根本原因**，而且是一個結構性、每次重跑都會
發生的問題，不是任何 Pass 141-172 節拍追蹤或 BarStart v2 節點的邏輯 bug：

- **Pass 172**：`BeatNetNode_TrackA` 對同一份音訊 100% 決定性（0.0 秒誤差）。
- **Pass 173**：`BeatNetNode_TrackA` 的輸入（Demucs 分離出的 drums/bass）在目前的
  `shifts=1` 設定下，每次重新分離都不是同一份音訊（最大誤差 0.234），這個輸入層級的
  差異才是真正讓 BeatNet 抓到不同拍數的原因。
- `pgm_craft/determinism.py` 的 `enable_deterministic_mode()` 只在 pipeline 啟動時
  seed 一次全域 RNG，沒有覆蓋到 `apply_model()` 內部每次呼叫都會消耗的隨機平移量，
  所以「決定性模式已啟用」跟「Demucs 分軌具備決定性」是兩件事，後者目前並不成立。

至此，從「黃金版 121 小節 vs 現在 119 小節」一路往回追，找到的根因鏈是：

```
measure_map 小節數差異
  → MeasureMapNode 依賴 beats（Pass 171 確認：不是 BarStart v2 造成）
  → beats 來自 BeatFusionArbitratorNode，固定等於 len(beats_rhythm)（Pass 171 確認邏輯未變）
  → beats_rhythm 來自 BeatNetNode_TrackA（Pass 172 確認：同輸入下 100% 決定性）
  → BeatNetNode_TrackA 的輸入 track_a_rhythm.wav 來自 Demucs 分離的 drums+bass
  → Demucs 用 shifts=1（隨機時間平移）推論，每次分離結果不是同一份音訊（Pass 173 確認）
```

比對邏輯（是否 bit-exact、最大絕對誤差、shape 不符時的安全處理）已抽成
`pgm_craft.determinism.compare_audio_arrays()`，並補上 `tests/test_sdd_pass173.py`
（3 項合成資料單元測試）。

## 4. 後續建議
1. 在 `_demucs_separate()` 呼叫 `apply_model()` 前，針對這次呼叫本身重新
   `torch.manual_seed(固定值)`（而非只靠 pipeline 啟動時呼叫一次），確保
   每次呼叫都從同一個 RNG 狀態開始取亂數平移量，讓「同一份輸入音訊」永遠得到
   「同一個隨機平移」，藉此達成 run-to-run 決定性，同時保留 shifts=1 帶來的
   SDR 品質增益（無需犧牲成 shifts=0）。
2. 或者顯式傳入 `shifts=0`，完全放棄隨機平移增益，換取百分之百決定性與較快的
   推論速度（`shifts=1` 等於多跑一次推論做平均）。這是犧牲一點分離品質換穩定性
   的權衡，需要使用者決定是否可接受。
