r"""
Pass 177 — Lane 1：純鼓軌偵測

只吃 stems/drums/kick.wav + stems/drums/snare.wav，不碰其他任何音色，用古典的
onset envelope + 動態規劃拍點追蹤（librosa.beat.beat_track）算出全曲拍點——
跟現有 pipeline 用的 BeatNet CRNN+DBN 是完全不同、更簡單的方法，作為 V3 多軌
逐輪疊加證據流程的最底層基準線。

信心度不是用 RMS 能量門檻猜，而是直接檢查「這一拍附近有沒有真實的 kick/snare
音頭」，滾動窗口內音頭佐證比例低的區段標記為 needs_review——這是 Lane 1 這種
「還沒有能力判斷真正 downbeat 相位」階段最誠實的信心度指標。

用法：
    python scratch/lane1_pure_drum_detection.py --project-dir "<專案資料夾路徑>"

輸出：
    <專案資料夾>/lanes/lane1_drum_only/click/mix_with_click.wav
    <專案資料夾>/lanes/lane1_drum_only/blocks.json
    <專案資料夾>/lanes/lane1_drum_only/beats.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIRM_TOLERANCE_SEC = 0.06     # 拍點附近多近才算「有真實音頭佐證」
WINDOW_SEC = 4.0                 # 信心度滾動窗口
CONFIRM_RATIO_THRESHOLD = 0.5    # 窗口內佐證比例低於此值視為需要複核
SAMPLE_STEP_SEC = 0.5
MIN_SEGMENT_SEC = 1.5


def detect_lane1_beats(kick_path: str, snare_path: str):
    import librosa
    import numpy as np
    import soundfile as sf

    def load_mono(path):
        y, sr = sf.read(path)
        if y.ndim > 1:
            y = y.mean(axis=1)
        return y, sr

    kick_y, sr = load_mono(kick_path)
    snare_y, sr2 = load_mono(snare_path)
    if sr2 != sr:
        snare_y = librosa.resample(snare_y, orig_sr=sr2, target_sr=sr)

    n = max(len(kick_y), len(snare_y))
    kick_y = np.pad(kick_y, (0, n - len(kick_y)))
    snare_y = np.pad(snare_y, (0, n - len(snare_y)))
    drum_only = kick_y + snare_y

    onset_env = librosa.onset.onset_strength(y=drum_only, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # 真實 kick/snare 音頭時間（獨立於上面的拍點追蹤，用來驗證每一拍是不是真的
    # 偵測到，還是動態規劃內插猜的）
    kick_onsets = librosa.onset.onset_detect(y=kick_y, sr=sr, units="time")
    snare_onsets = librosa.onset.onset_detect(y=snare_y, sr=sr, units="time")
    real_onsets = np.sort(np.concatenate([kick_onsets, snare_onsets]))

    beats = []
    confirmed = []
    for i, t in enumerate(beat_times):
        beat_num = (i % 4) + 1
        beats.append([round(float(t), 6), beat_num])
        if len(real_onsets):
            nearest = float(np.min(np.abs(real_onsets - t)))
        else:
            nearest = float("inf")
        confirmed.append(nearest <= CONFIRM_TOLERANCE_SEC)

    duration = n / float(sr)
    return {
        "tempo": float(tempo) if np.isscalar(tempo) else float(tempo[0]),
        "beats": beats,
        "confirmed": confirmed,
        "duration": duration,
    }


def build_confidence_blocks(beats, confirmed, duration):
    import numpy as np

    times = np.arange(0.0, duration, SAMPLE_STEP_SEC)
    beat_times = np.array([b[0] for b in beats]) if beats else np.array([])
    confirmed = np.array(confirmed) if len(confirmed) else np.array([], dtype=bool)

    flags = []
    for t in times:
        lo, hi = t - WINDOW_SEC / 2, t + WINDOW_SEC / 2
        mask = (beat_times >= lo) & (beat_times < hi)
        window_beats = confirmed[mask]
        if len(window_beats) == 0:
            flags.append(True)  # 這個窗口內完全沒有拍點資料，視為需要複核
            continue
        ratio = float(np.mean(window_beats))
        flags.append(ratio < CONFIRM_RATIO_THRESHOLD)

    raw_segments = []
    seg_start_idx = 0
    for i in range(1, len(times) + 1):
        if i == len(times) or flags[i] != flags[seg_start_idx]:
            seg_end = duration if i == len(times) else times[i]
            raw_segments.append({
                "start": float(times[seg_start_idx]),
                "end": float(seg_end),
                "needs_review": flags[seg_start_idx],
            })
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

    blocks = []
    for i, seg in enumerate(final_segments):
        blocks.append({
            "id": f"seg-{i}",
            "start": seg["start"],
            "end": seg["end"],
            "needs_review": bool(seg["needs_review"]),
        })
    return blocks


def main():
    parser = argparse.ArgumentParser(description="Pass 177 Lane 1 純鼓軌偵測")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--lane-id", default="lane1_drum_only")
    args = parser.parse_args()

    project_dir = args.project_dir
    kick_path = os.path.join(project_dir, "stems", "drums", "kick.wav")
    snare_path = os.path.join(project_dir, "stems", "drums", "snare.wav")
    audio_path = os.path.join(project_dir, "click", "mix_with_click.wav")

    for p in (kick_path, snare_path, audio_path):
        if not os.path.exists(p):
            print(f"[FATAL] 找不到必要檔案：{p}")
            sys.exit(1)

    lane_dir = os.path.join(project_dir, "lanes", args.lane_id)
    click_dir = os.path.join(lane_dir, "click")
    os.makedirs(click_dir, exist_ok=True)

    print(f"[Lane1] 讀取 kick/snare 分析純鼓拍點...")
    result = detect_lane1_beats(kick_path, snare_path)
    print(f"[Lane1] 估計整體節奏 {result['tempo']:.1f} BPM，共 {len(result['beats'])} 拍。")

    blocks = build_confidence_blocks(result["beats"], result["confirmed"], result["duration"])
    needs_review_count = sum(1 for b in blocks if b["needs_review"])
    print(f"[Lane1] 全曲合併成 {len(blocks)} 個區塊，其中 {needs_review_count} 個需要複核。")

    with open(os.path.join(lane_dir, "blocks.json"), "w", encoding="utf-8") as f:
        json.dump(blocks, f, ensure_ascii=False, indent=2)
    with open(os.path.join(lane_dir, "beats.json"), "w", encoding="utf-8") as f:
        json.dump({"tempo": result["tempo"], "beats": result["beats"]}, f, ensure_ascii=False, indent=2)

    print(f"[Lane1] 渲染 click 音檔（重用 PGMSynthesizer.synthesize_click）...")
    from pgm_craft.synthesizer import PGMSynthesizer
    synth = PGMSynthesizer()
    click_path, mix_path = synth.synthesize_click(audio_path, result["beats"], output_dir=click_dir)
    print(f"[Lane1] 完成：{mix_path}")


if __name__ == "__main__":
    main()
