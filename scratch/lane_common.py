r"""
Pass 177 — 多軌偵測共用工具

Lane 2（鼓+貝斯）、Lane 3（+和弦）、未來的 Lane 4（+旋律）都需要同一套：
- 讀上一條 Lane 的 blocks.json/marks.json，算出「需要重新分析」的時間範圍
  （非 pass/auto_pass 的區塊）
- 把新分析出的拍點，只拼接進這些範圍內，範圍外沿用上一條 Lane 的原始拍點
- 用「這一拍附近有沒有真實音頭佐證」滾動窗口比例，算信心度區塊
這裡集中寫一次，避免每條 Lane 的腳本各自重複、容易改一邊漏一邊。
"""

import os

CONFIRM_TOLERANCE_SEC = 0.06
WINDOW_SEC = 4.0
CONFIRM_RATIO_THRESHOLD = 0.5
SAMPLE_STEP_SEC = 0.5
MIN_SEGMENT_SEC = 1.5


def load_mono(path, target_sr=None):
    import soundfile as sf
    import librosa
    y, sr = sf.read(path)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if target_sr is not None and sr != target_sr:
        y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return y, sr


def resolve_base_audio_path(project_dir: str) -> str:
    """回傳這首歌『純音檔、完全沒有混過任何 click』的路徑，用來當
    synth.synthesize_click() 的底——絕對不能用 click/mix_with_click.wav，
    那個檔案本身已經混了 V1 正式管線自己的 click，疊上去等於兩層 click
    同時響、互相打架，讓人聽不出這條 Lane 自己準不準（Pass 177 實測發現
    的真實 bug：在只有 V1 有拍、這條 Lane 沒有拍的時間點，仍能量到 V1
    click 的殘留脈衝）。這裡跟正式管線 ClickSynthesisNode 用的 audio_path
    blackboard 值（音質正規化階段的輸出）保持一致，維持全部 Lane 用同一個
    底本公平比較。"""
    import glob

    source_dir = os.path.join(project_dir, "source")
    if os.path.isdir(source_dir):
        for suffix in ("_normalized.wav", "_denoised.wav", "_raw.wav"):
            matches = sorted(glob.glob(os.path.join(source_dir, f"*{suffix}")))
            if matches:
                return matches[0]
    raise FileNotFoundError(
        f"找不到 {project_dir} 底下乾淨的原始音檔（source/*_normalized.wav 等），"
        f"不能拿 click/mix_with_click.wav 頂替，那樣會把 V1 自己的 click 混進去。"
    )


def escalation_ranges(source_lane_dir: str):
    """回傳 [(start, end), ...]：上一條 Lane 自己的信心評分判定 needs_review
    的區塊時間範圍，合併相鄰/重疊的範圍。

    這條逐輪疊加證據的鏈路完全由每一層自己的信心評分（build_confidence_
    blocks 算出來、寫死在 blocks.json 裡的 needs_review 欄位）自動驅動，跟
    人工標記（marks.json）無關——人工在審查介面上標的 pass/fail 只是回饋
    紀錄，用來在下一次調整信心評分的門檻參數（CONFIRM_RATIO_THRESHOLD 等）
    後，把整條鏈路重新跑一次，不會即時介入、改變這一輪要不要重新分析哪些
    區塊。故意不讀 marks.json。"""
    import json

    blocks_path = os.path.join(source_lane_dir, "blocks.json")
    with open(blocks_path, "r", encoding="utf-8") as f:
        blocks = json.load(f)

    ranges = [(b["start"], b["end"]) for b in blocks if b["needs_review"]]
    ranges.sort()
    merged = []
    for s, e in ranges:
        if merged and s <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def splice_beats(source_beats, candidate_beat_times, ranges):
    """保留 source_beats 落在 ranges 之外的部分，範圍內的一律換成
    candidate_beat_times 裡落在同一範圍的拍點，合併排序後重新循環標記拍號。"""
    def in_any_range(t):
        return any(s <= t < e for s, e in ranges)

    kept = [row for row in source_beats if not in_any_range(row[0])]
    inserted = [float(t) for t in candidate_beat_times if in_any_range(float(t))]

    merged_times = sorted([row[0] for row in kept] + inserted)
    return [[round(t, 6), (i % 4) + 1] for i, t in enumerate(merged_times)]


def build_confidence_blocks(beats, real_onsets, duration):
    import numpy as np

    times = np.arange(0.0, duration, SAMPLE_STEP_SEC)
    beat_times = np.array([b[0] for b in beats]) if beats else np.array([])

    confirmed_per_beat = []
    for t in beat_times:
        nearest = float(np.min(np.abs(real_onsets - t))) if len(real_onsets) else float("inf")
        confirmed_per_beat.append(nearest <= CONFIRM_TOLERANCE_SEC)
    confirmed_per_beat = np.array(confirmed_per_beat, dtype=bool)

    flags = []
    for t in times:
        lo, hi = t - WINDOW_SEC / 2, t + WINDOW_SEC / 2
        mask = (beat_times >= lo) & (beat_times < hi)
        window_beats = confirmed_per_beat[mask]
        if len(window_beats) == 0:
            flags.append(True)
            continue
        flags.append(float(np.mean(window_beats)) < CONFIRM_RATIO_THRESHOLD)

    raw_segments = []
    seg_start_idx = 0
    for i in range(1, len(times) + 1):
        if i == len(times) or flags[i] != flags[seg_start_idx]:
            seg_end = duration if i == len(times) else times[i]
            raw_segments.append({"start": float(times[seg_start_idx]), "end": float(seg_end), "needs_review": flags[seg_start_idx]})
            seg_start_idx = i

    merged = []
    for seg in raw_segments:
        if merged and (seg["end"] - seg["start"]) < MIN_SEGMENT_SEC:
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(seg)
    final_segments = []
    for seg in merged:
        if final_segments and final_segments[-1]["needs_review"] == seg["needs_review"]:
            final_segments[-1]["end"] = seg["end"]
        else:
            final_segments.append(seg)

    return [
        {"id": f"seg-{i}", "start": s["start"], "end": s["end"], "needs_review": bool(s["needs_review"])}
        for i, s in enumerate(final_segments)
    ]
