# 相關說明文獻與參考專案

**最後更新：** 2026-07-29

本文件整理 PGMCraft Studio 第一階段會參考的工具、文件與專案。用途是建立技術脈絡，不代表每個工具都會直接成為依賴。

模型搭配與接入優先序另見：[`docs/MODEL-COMBINATION-EVALUATION.md`](MODEL-COMBINATION-EVALUATION.md)。

## DAW 與 MIDI Tempo Map

| 來源 | 參考重點 | 對 PGMCraft 的意義 |
|------|----------|--------------------|
| Ableton：Importing a tempo map | MIDI 檔需要包含 tempo changes，且需要有跨越 tempo changes 長度的 MIDI note 或 notes | `tempo_map.mid` 應包含 `set_tempo` meta events，並放入 anchor note |
| Ableton Manual：MIDI Files | Live 可匯入 Standard MIDI files，MIDI 資料會被納入 Live Set | Phase 1 應輸出標準 `.mid`，而不是自訂格式 |
| MIDI Association：Standard MIDI Files | SMF 支援多 track、tempo、time signature 等資訊 | `tempo_map.mid` 與 `click_guide.mid` 應遵循 SMF |
| Mido：Meta Message Types | `set_tempo` 使用 microseconds per beat，`time_signature` 是 meta message | Python 端用 `mido` 寫 tempo map 比只用 note event 更明確 |

連結：

- https://help.ableton.com/hc/en-us/articles/360003387979-Importing-a-tempo-map
- https://www.ableton.com/en/manual/managing-files-and-sets/
- https://midi.org/standard-midi-files
- https://mido.readthedocs.io/en/1.1.24/meta_message_types.html

## Beat / Downbeat 偵測

| 來源 | 參考重點 | 對 PGMCraft 的意義 |
|------|----------|--------------------|
| BeatNet (ISMIR 2021) | CRNN + particle filtering 的 joint beat/downbeat/tempo/meter tracking；官方實作亦提供 offline mode 與 DBN inference | 適合作為高精度優先節點；`BeatNetSingleTrackNode` 應優先輸出 beat/downbeat labels，而不是只輸出 BPM |
| BeatNet+ (TISMIR 2025) | 針對 generic music、isolated singing voice、non-percussive audio 強化；重點是不同聲學條件需要 adaptation strategy | 支持目前 A 軌 rhythm、B 軌 instrumental 的多訊號來源策略；但不能把單一鼓軌結果當成所有素材都可靠 |
| madmom RNN/DBN beat tracking | RNN beat activation + DBN/processor 後處理；DBN beat processor 以 activation function 輸出秒級 beat positions | 目前的 BeatNet/Librosa fallback 應被視為最低層；未來可加入 madmom/Aubio/Essentia 作為獨立候選，而不是只做自寫 heuristic |
| librosa `beat_track` / Ellis 2007 | dynamic programming beat tracker：onset strength、tempo autocorrelation、依 tempo consistency 選 peak | 適合作為 deterministic fallback；可用於低依賴環境，但 downbeat/meter 精度不應高估 |
| Beat This! (ISMIR 2024) | 指出 DBN 在變拍號、大幅變速、非 3/4 或 4/4、複雜曲風時可能受固定假設限制；以較少後處理追求泛化 | PGMCraft 的 Viterbi/DBN 類平滑應保持 guard 性質，不能無條件把所有 rubato 或變拍號拉直 |
| MIREX / mir_eval beat evaluation | beat tracking 應以 annotation 對齊誤差與 F-measure、CML/AML、Cemgil 等指標評估；`mir_eval.beat.f_measure` 預設 70 ms 容差 | 最終測試不能只看流程成功，應輸出 beat list 與人工/標註 reference 比對 |
| MIREX Audio Downbeat Estimation | downbeat task 只評估每小節第一拍位置，並以 +/-70 ms F-measure 為主要程序 | downbeat 必須與 beat tracking 分開驗收；只看總 beat 數不足以證明小節相位正確 |
| aubio | tempo tracking、beat detection、onset/pitch 工具 | 可作為未來替代 fallback 或 CLI 參考 |
| Essentia RhythmExtractor2013 | 可輸出 BPM、beat positions、confidence、BPM estimates | 可作為未來高階分析與 confidence 設計參考 |

連結：

- https://archives.ismir.net/ismir2021/paper/000033.pdf
- https://github.com/mjhydri/BeatNet
- https://transactions.ismir.net/articles/10.5334/tismir.198
- https://madmom.readthedocs.io/en/v0.16/modules/features/beats.html
- https://pypi.org/project/madmom/
- https://librosa.org/doc/latest/generated/librosa.beat.beat_track.html
- https://www.tandfonline.com/doi/abs/10.1080/09298210701653344
- https://github.com/CPJKU/beat_this
- https://music-ir.org/mirex/wiki/2026%3AAudio_Beat_Tracking
- https://music-ir.org/mirex/wiki/2026%3AAudio_Downbeat_Estimation
- https://mir-eval.readthedocs.io/latest/api/beat.html
- https://aubio.readthedocs.io/en/latest/
- https://aubio.org/manpages/latest/aubiotrack.1.html
- https://essentia.upf.edu/tutorial_rhythm_beatdetection.html

## 節拍精度驗收原則

目前 Stage 3 的設計是「多候選來源 + 保守融合 + 後處理 guard」：

```text
Rhythm track (drums + bass)
+ Instrumental / no vocals track
-> BeatNet / Librosa fallback
-> ensemble / fusion
-> downbeat refinement
-> onset transient snap
-> low-frequency downbeat verifier
-> tempo smoothing guard
-> alignment verifier / drums fallback
```

這個架構方向與正式文獻相容，因為它同時保留 neural tracker、onset/DP fallback、低頻重音驗證與 tempo continuity 約束。不過「精確取得拍子」必須用 reference beat annotations 驗證；通過單元測試只能證明資料流與防呆邏輯成立，不能證明音樂感知上的 beat/downbeat 正確。

建議最終測試至少記錄：

- beat F-measure，建議使用 `mir_eval.beat.f_measure` 預設 70 ms window。
- continuity 指標：CMLc/CMLt/AMLc/AMLt，用來檢查半速、雙速與 phase shift。
- downbeat hit rate：以人工標註 downbeat 或 DAW 手動 grid 作 reference。
- click residual：預測 click 與 kick/snare/onset peak 的平均與 P95 offset ms。
- 曲型分層：穩定流行/搖滾、無鼓 intro、rubato、3/4、變拍號、現場錄音分開統計。

目前 CLI 已提供 reference-based 評估入口：

```bash
pgm-craft --audio song.wav --output outputs/song_eval --reference-beats annotations/beats.txt --reference-downbeats annotations/downbeats.txt
```

annotation 檔可用純文字、CSV、TSV 或 JSON。每列可只放 `time_seconds`，也可放 `time_seconds beat_number`；downbeat 驗收會使用 `beat_number == 1` 的列。執行後會寫出：

- `pgm_report.json`：包含完整 `beats`、`refined_beats` 與 `beat_precision_diagnostics`。
- `beat_evaluation.json`：包含 70 ms window 的 precision、recall、F-measure、平均/中位/P95 絕對誤差；若安裝 `mir_eval`，beat 評估會額外包含 mir_eval 指標。

## 音訊分析與人工檢查參考

| 來源 | 參考重點 | 對 PGMCraft 的意義 |
|------|----------|--------------------|
| Sonic Visualiser | 可檢視 waveform、spectrogram、annotation layer、MIDI note data，並同步播放音訊與 annotation | 適合作為人工驗證 beat / tempo / MIDI guide 的參考工具 |

連結：

- https://sonicvisualiser.org/
- https://sonicvisualiser.org/features.html

## 目前採用策略

Phase 1 不追求一次整合所有演算法，而是採用穩定優先策略：

```text
BeatNet / Librosa 作為候選來源
-> 雙軌 rhythm / instrumental 分析
-> ensemble / fusion / validation / downbeat refinement
-> onset snap / low-frequency verifier / tempo smoothing guard
-> measure map 與 alignment verifier
-> MIDI 使用標準 tempo meta event
```

此策略可讓核心流程先穩定，同時保留未來替換節點的空間。
