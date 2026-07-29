# 模型搭配使用評估

**最後更新：** 2026-07-29

本文件評估 PGMCraft Studio 在「精確取得 beat / downbeat」與「分軌輔助節拍」上的模型組合。結論先行：目前最值得接入的不是更多自寫規則，而是把 `Beat This!` 作為第三個正式 beat/downbeat 候選，並把高品質分軌模型限制在「提供 rhythm anchors」的角色。

## 目前狀態

### 已實作核心

| 類別 | 目前模型 / 方法 | 角色 | 評估 |
|------|------------------|------|------|
| Beat tracking | BeatNet | A/B 軌優先候選 | 合理。具 joint beat/downbeat/tempo/meter 能力，適合作為高精度候選。 |
| Beat fallback | Librosa / Ellis dynamic programming | deterministic fallback | 合理但不能單獨宣稱 downbeat 精準。適合低依賴環境與失敗保底。 |
| Stem separation | HTDemucs / htdemucs_ft | 4-stem 基礎分軌 | 實務可用；適合產生 drums/bass/rhythm track。 |
| Sub-stem anchors | DSP bandpass / onset peak | kick/snare/bass anchor | 適合作為校正訊號，不應取代 beat tracker。 |
| Evaluation | reference-based 70 ms matching | 最終精度驗收 | 已補上；應成為模型選型依據。 |

### 目前缺口

| 缺口 | 影響 | 建議 |
|------|------|------|
| 缺少第二個正式 neural beat/downbeat tracker | BeatNet 錯時，Librosa 只提供傳統 fallback，候選多樣性不足 | 加入 `Beat This!` 作為獨立候選 |
| 分軌模型名稱多，但專項模型多數未真實推論 | 前端看起來支援很多音色，但 precision 不能建立在 placeholder 上 | 將專項模型標示為 optional / experimental；節拍只依賴可驗證 stems |
| Downbeat 評估尚未在 GUI 顯示 | 使用者需要 CLI 或 JSON 才能看客觀精度 | 先維持 CLI，等 reference workflow 穩定後再接 GUI |
| madmom Python 相容性風險 | PyPI madmom 對新 Python / numpy 不友善 | 不建議列為預設依賴，只能做 optional adapter |

## 推薦組合

### 組合 A：高精度離線 PGM 預設

```text
Full mix
+ instrumental/no_vocals
+ rhythm track(drums + bass)
-> Beat This! candidate
-> BeatNet candidate
-> Librosa deterministic fallback
-> weighted consensus / fusion
-> onset transient snap
-> kick/bass downbeat verifier
-> conservative tempo smoothing
-> reference evaluation
```

建議用途：正式 DAW/Live PGM 工程包、你會做最終人工測試的素材。

模型角色：

- `Beat This!`：主要泛化候選。適合 rubato、變拍號、古典/solo/non-drum 類型，因為它刻意降低 DBN 固定節奏假設。
- `BeatNet`：主要連續性候選。適合 pop/rock/electronic、鼓與低頻明確的素材。
- `Librosa`：保底與 sanity check。當 neural tracker 掉拍或依賴不可用時仍能輸出。
- `HTDemucs / BS-RoFormer 6-stem`：只作為產生 rhythm/instrumental candidate 的前處理，不直接決定最終 beat。

這是目前最適合 PGMCraft 的目標組合。

### 組合 B：CPU / 低依賴穩定組合

```text
Full mix
-> Librosa beat_track
-> Essentia RhythmExtractor2013(multifeature)
-> onset/kick anchor verification
-> reference evaluation
```

建議用途：沒有 CUDA、不能安裝 PyTorch/BeatNet/Beat This! 的電腦。

取捨：

- 優點：部署穩、可重現、安裝風險低。
- 缺點：downbeat 與複雜曲風精度較弱；適合 demo / fallback，不適合宣稱最終高精度。

### 組合 C：Live / 快速預覽組合

```text
Precomputed stems or full mix
-> BeatNet online/offline
-> Aubio or Essentia fast tracker
-> minimal smoothing
-> click preview
```

建議用途：Live 現場快速產生 click 或預覽，不是最終採譜。

取捨：

- 優點：速度優先。
- 缺點：不應做重型 BS-RoFormer / Demucs 分軌；現場環境也不適合長時間模型推論。

### 組合 D：無鼓 / 古典 / rubato / 變拍號

```text
Full mix + harmonic/instrumental track
-> Beat This! primary
-> BeatNet secondary
-> madmom bar/downbeat optional post-check
-> smoothing guard disabled or loosened
-> reference evaluation with CML/AML
```

建議用途：鋼琴獨奏、弦樂、古典、現場彈性速度、3/4 或變拍號。

關鍵規則：

- 不要讓 drums/kick anchors 覆蓋全曲。
- 不要把 Viterbi smoothing 當成絕對校正。
- 評估時除了 F-measure，必須看 continuity 與 downbeat phase。

### 組合 E：分軌品質優先組合

```text
BS-RoFormer 6-stem or vocals/instrumental
-> HTDemucs fallback
-> drums/bass/instrumental candidates
-> Beat This! + BeatNet over multiple tracks
```

建議用途：人聲很前、混音複雜、鼓與 bass 被遮蔽的流行/動漫/Live 音源。

取捨：

- BS-RoFormer 類模型在 vocals/instrumental 與 6-stem 上較值得評估。
- HTDemucs 仍適合當穩定 fallback，尤其 drums/bass 目標明確時。
- 分軌 artifact 會製造假 transient，所以 stems 只能提供候選與 anchor，不能單獨決定 beat grid。

## 不建議的組合

| 組合 | 問題 |
|------|------|
| 只用 Librosa + 自寫 downbeat heuristic | downbeat、半速/雙速、弱起與變拍號風險太高 |
| 只用鼓軌/kick anchor 取得全曲拍子 | 無鼓 intro、breakdown、acoustic、rubato 會失效 |
| Demucs 6s piano/guitar 結果直接拿來做節拍主軸 | Demucs 官方也提醒 6-source piano/guitar 可能 bleed/artifacts 明顯 |
| madmom 作為預設依賴 | Python / numpy 相容性風險高，適合 optional adapter |
| 53-stem mega model 作為預設 | 太重、VRAM 要求高，單一 stem 品質不一定優於專項模型 |

## 建議接入順序

1. 新增 `BeatThisSingleTrackNode`，輸出 `beats_btthis_rhythm` / `beats_btthis_inst` / `beats_btthis_mix`。
2. 將 `MultiModelBeatEnsembleNode` 從 A/B 兩來源擴充為 N-source candidate fusion。
3. 新增 candidate-level report：每個候選的 beat count、median BPM、tempo stability、downbeat density、alignment score。
4. 在 `beat_evaluation.json` 中記錄每個候選與 final fused result 的分數。
5. 分軌模型先接 `bs-roformer-infer` optional adapter；預設仍保留 HTDemucs fallback。
6. GUI 等 CLI 評估穩定後，再加 reference annotation 上傳與結果表格。

## 最終建議

PGMCraft 下一版最合理的預設組合是：

```text
Beat This! + BeatNet + Librosa
+ HTDemucs/BS-RoFormer 產生 rhythm/instrumental candidates
+ onset/kick/bass anchors 做校正
+ reference-based evaluation 決定採用權重
```

這個組合比「BeatNet + Librosa + 自寫 guard」更適合，因為它增加了一個現代 neural tracker 的獨立觀點，同時不把 DBN、分軌或 kick transient 任一單點當成絕對真相。

## 參考來源

- BeatNet: https://github.com/mjhydri/BeatNet
- BeatNet paper: https://archives.ismir.net/ismir2021/paper/000033.pdf
- BeatNet+: https://transactions.ismir.net/articles/10.5334/tismir.198
- Beat This!: https://github.com/CPJKU/beat_this
- Beat This! publication page: https://research.jku.at/en/publications/beat-this-accurate-beat-tracking-without-dbn-postprocessing/
- madmom downbeat docs: https://madmom.readthedocs.io/en/v0.16.1/modules/features/downbeats.html
- Essentia RhythmExtractor2013: https://essentia.upf.edu/reference/std_RhythmExtractor2013.html
- Demucs: https://github.com/facebookresearch/demucs
- BS-RoFormer inference toolkit: https://github.com/openmirlab/bs-roformer-infer
- BS-RoFormer architecture: https://github.com/lucidrains/BS-RoFormer
