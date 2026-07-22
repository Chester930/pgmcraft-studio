# 相關說明文獻與參考專案

**最後更新：** 2026-07-22

本文件整理 PGMCraft Studio 第一階段會參考的工具、文件與專案。用途是建立技術脈絡，不代表每個工具都會直接成為依賴。

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
| BeatNet | CRNN + particle filtering 的 beat/downbeat/tempo/meter tracking；支援 offline mode | 適合作為高精度優先節點 |
| librosa `beat_track` | dynamic programming beat tracker；可回傳 tempo 與 beat event locations | 適合作為穩定 fallback |
| aubio | tempo tracking、beat detection、onset/pitch 工具 | 可作為未來替代 fallback 或 CLI 參考 |
| Essentia RhythmExtractor2013 | 可輸出 BPM、beat positions、confidence、BPM estimates | 可作為未來高階分析與 confidence 設計參考 |

連結：

- https://github.com/mjhydri/BeatNet
- https://librosa.org/doc/latest/generated/librosa.beat.beat_track.html
- https://aubio.readthedocs.io/en/latest/
- https://aubio.org/manpages/latest/aubiotrack.1.html
- https://essentia.upf.edu/tutorial_rhythm_beatdetection.html

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
BeatNet 優先
-> BeatNet 不可用或失敗時 Librosa fallback
-> 輸出前加入 validation / measure map
-> MIDI 使用標準 tempo meta event
```

此策略可讓核心流程先穩定，同時保留未來替換節點的空間。
