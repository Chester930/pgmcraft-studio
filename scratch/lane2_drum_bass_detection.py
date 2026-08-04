r"""
Pass 177（延伸）— Lane 2：鼓 + 貝斯疊加偵測

只針對 Lane 1（純鼓軌）被標記「不通過」（或還沒標記，保守也視為需要複核）的
區塊重新分析——不是重跑整首歌；Lane 1 已經通過（人工或既有標準判定通過）的
區段直接沿用 Lane 1 的拍點，不重新計算，維持「使用者確認過的部分不動」原則。

證據疊加：讀 stems/drums/kick.wav + snare.wav（跟 Lane 1 一樣）再疊加
stems/bass/（依 synth_bass_808 > electric_bass > bass 優先序，跟
BassEvidenceExtractNode 的慣例一致），用 librosa.beat.beat_track 在
「鼓+貝斯」合併的 onset envelope 上重新算一次全曲拍點，只取落在「需要複核」
時間範圍內的部分，拼接回 Lane 1 的其餘拍點上。

信心度一樣用「這一拍附近有沒有真實音頭佐證」滾動窗口比例，這次佐證來源除了
kick/snare 也加入 bass 的 onset。

用法：
    python scratch/lane2_drum_bass_detection.py --project-dir "<專案資料夾路徑>"
        [--source-lane lane1_drum_only] [--lane-id lane2_drum_bass]

輸出：
    <專案資料夾>/lanes/lane2_drum_bass/click/mix_with_click.wav
    <專案資料夾>/lanes/lane2_drum_bass/blocks.json
    <專案資料夾>/lanes/lane2_drum_bass/beats.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lane_common import load_mono, escalation_ranges, splice_beats, build_confidence_blocks, resolve_base_audio_path

BASS_STEM_PRIORITY = ("synth_bass_808.wav", "electric_bass.wav", "bass.wav")


def _load_mono(path, target_sr=None):
    return load_mono(path, target_sr=target_sr)


def _find_bass_stem(project_dir: str):
    bass_dir = os.path.join(project_dir, "stems", "bass")
    for name in BASS_STEM_PRIORITY:
        p = os.path.join(bass_dir, name)
        if os.path.exists(p):
            return p
    return None


def detect_lane2_beats(kick_path, snare_path, bass_path):
    import librosa
    import numpy as np

    kick_y, sr = _load_mono(kick_path)
    snare_y, _ = _load_mono(snare_path, target_sr=sr)
    bass_y, _ = _load_mono(bass_path, target_sr=sr)

    n = max(len(kick_y), len(snare_y), len(bass_y))
    kick_y = np.pad(kick_y, (0, n - len(kick_y)))
    snare_y = np.pad(snare_y, (0, n - len(snare_y)))
    bass_y = np.pad(bass_y, (0, n - len(bass_y)))
    combined = kick_y + snare_y + bass_y

    onset_env = librosa.onset.onset_strength(y=combined, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    kick_onsets = librosa.onset.onset_detect(y=kick_y, sr=sr, units="time")
    snare_onsets = librosa.onset.onset_detect(y=snare_y, sr=sr, units="time")
    bass_onsets = librosa.onset.onset_detect(y=bass_y, sr=sr, units="time")
    real_onsets = np.sort(np.concatenate([kick_onsets, snare_onsets, bass_onsets]))

    duration = n / float(sr)
    return {
        "tempo": float(tempo) if np.isscalar(tempo) else float(tempo[0]),
        "beat_times": beat_times,
        "real_onsets": real_onsets,
        "duration": duration,
    }


def main():
    parser = argparse.ArgumentParser(description="Pass 177 Lane 2 鼓+貝斯疊加偵測")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--source-lane", default="lane1_drum_only")
    parser.add_argument("--lane-id", default="lane2_drum_bass")
    args = parser.parse_args()

    project_dir = args.project_dir
    kick_path = os.path.join(project_dir, "stems", "drums", "kick.wav")
    snare_path = os.path.join(project_dir, "stems", "drums", "snare.wav")
    audio_path = resolve_base_audio_path(project_dir)
    bass_path = _find_bass_stem(project_dir)
    source_lane_dir = os.path.join(project_dir, "lanes", args.source_lane)
    source_beats_path = os.path.join(source_lane_dir, "beats.json")

    for p in (kick_path, snare_path, audio_path, source_beats_path):
        if not os.path.exists(p):
            print(f"[FATAL] 找不到必要檔案：{p}")
            sys.exit(1)
    if bass_path is None:
        print(f"[FATAL] 找不到任何貝斯 stem（{BASS_STEM_PRIORITY}），無法建立 Lane 2。")
        sys.exit(1)

    lane_dir = os.path.join(project_dir, "lanes", args.lane_id)
    click_dir = os.path.join(lane_dir, "click")
    os.makedirs(click_dir, exist_ok=True)

    with open(source_beats_path, "r", encoding="utf-8") as f:
        source_beats = json.load(f)["beats"]

    ranges = escalation_ranges(source_lane_dir)
    total_escalated_sec = sum(e - s for s, e in ranges)
    print(f"[Lane2] 來源 Lane：{args.source_lane}，需要重新分析的區間共 {len(ranges)} 段、"
          f"合計 {total_escalated_sec:.1f} 秒。")

    print(f"[Lane2] 用 {os.path.basename(bass_path)} 疊加鼓軌，重新分析全曲拍點...")
    result = detect_lane2_beats(kick_path, snare_path, bass_path)
    print(f"[Lane2] 鼓+貝斯估計節奏 {result['tempo']:.1f} BPM。")

    def in_any_range(t):
        return any(s <= t < e for s, e in ranges)

    kept_count = sum(1 for row in source_beats if not in_any_range(row[0]))
    inserted_count = sum(1 for t in result["beat_times"] if in_any_range(float(t)))
    final_beats = splice_beats(source_beats, result["beat_times"], ranges)
    print(f"[Lane2] 拼接後共 {len(final_beats)} 拍（沿用 Lane 1：{kept_count} 拍，新分析：{inserted_count} 拍）。")

    blocks = build_confidence_blocks(final_beats, result["real_onsets"], result["duration"])
    needs_review_count = sum(1 for b in blocks if b["needs_review"])
    print(f"[Lane2] 全曲合併成 {len(blocks)} 個區塊，其中 {needs_review_count} 個仍需複核。")

    with open(os.path.join(lane_dir, "blocks.json"), "w", encoding="utf-8") as f:
        json.dump(blocks, f, ensure_ascii=False, indent=2)
    with open(os.path.join(lane_dir, "beats.json"), "w", encoding="utf-8") as f:
        json.dump({"tempo": result["tempo"], "beats": final_beats}, f, ensure_ascii=False, indent=2)

    print(f"[Lane2] 渲染 click 音檔...")
    from pgm_craft.synthesizer import PGMSynthesizer
    synth = PGMSynthesizer()
    click_path, mix_path = synth.synthesize_click(audio_path, final_beats, output_dir=click_dir)
    print(f"[Lane2] 完成：{mix_path}")


if __name__ == "__main__":
    main()
