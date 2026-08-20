r"""
Pass 177（延伸）— Lane 4：鼓 + 貝斯 + 和弦 + 旋律疊加偵測

只針對 Lane 3（+和弦）被標記「不通過」（或還沒標記，保守也算需要複核）的
區塊重新分析，範圍外沿用 Lane 3 的拍點不動。

旋律證據來源兩個，都重用既有節點的邏輯，不是另外發明：
1. 吉他/鋼琴的旋律 onset：重用 ChordMelodyOnsetSplitNode._split_onsets()
   分類出來的 melody_anchors（跟 Lane 3 取同一批 onset，只是這次取旋律
   那一半，不是和弦那一半）。
2. 主唱人聲 onset：重用 VocalMelodyEvidenceExtractNode._extract_onsets()
   （lead_vocal.wav 優先，找不到才退回 vocals_debreathed.wav / vocals.wav）。

用法：
    python scratch/lane4_melody_detection.py --project-dir "<專案資料夾路徑>"
        [--source-lane lane3_drum_bass_chord] [--lane-id lane4_melody]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lane_common import load_mono, escalation_ranges, splice_beats, build_confidence_blocks, resolve_base_audio_path

BASS_STEM_PRIORITY = ("synth_bass_808.wav", "electric_bass.wav", "bass.wav")
VOCAL_STEM_PRIORITY = ("lead_vocal.wav", "vocals_debreathed.wav", "vocals.wav")
MELODY_ONSET_IMPULSE_GAIN = 3.0  # 跟 Lane3 的 CHORD_ONSET_IMPULSE_GAIN 對稱


def _find_bass_stem(project_dir: str):
    bass_dir = os.path.join(project_dir, "stems", "bass")
    for name in BASS_STEM_PRIORITY:
        p = os.path.join(bass_dir, name)
        if os.path.exists(p):
            return p
    return None


def _find_vocal_stem(project_dir: str):
    vocal_dir = os.path.join(project_dir, "stems", "vocals")
    for name in VOCAL_STEM_PRIORITY:
        p = os.path.join(vocal_dir, name)
        if os.path.exists(p):
            return p
    return None


def _melody_onset_times(project_dir: str, vocal_path):
    """重用 ChordMelodyOnsetSplitNode（吉他/鋼琴旋律那一半）+
    VocalMelodyEvidenceExtractNode（主唱人聲）的既有邏輯，不重新發明。"""
    from pgm_craft.workflow.module3_barstart_v2_bt import (
        ChordMelodyOnsetSplitNode,
        VocalMelodyEvidenceExtractNode,
    )

    melody_times = []

    chord_node = ChordMelodyOnsetSplitNode()
    for instrument, folder in (("guitar", "guitars"), ("piano", "pianos")):
        path = os.path.join(project_dir, "stems", folder, f"{instrument}.wav")
        if not os.path.exists(path):
            continue
        try:
            _chord_anchors, melody_anchors = chord_node._split_onsets(path)
            melody_times.extend(a["time"] for a in melody_anchors)
        except Exception as e:
            print(f"[Lane4] {instrument} 旋律分析失敗，略過：{e}")

    if vocal_path:
        vocal_node = VocalMelodyEvidenceExtractNode()
        try:
            vocal_anchors = vocal_node._extract_onsets(vocal_path)
            melody_times.extend(a["time"] for a in vocal_anchors)
        except Exception as e:
            print(f"[Lane4] 人聲旋律分析失敗，略過：{e}")

    return sorted(melody_times)


def detect_lane4_beats(kick_path, snare_path, bass_path, melody_times):
    import librosa
    import numpy as np

    kick_y, sr = load_mono(kick_path)
    snare_y, _ = load_mono(snare_path, target_sr=sr)
    bass_y, _ = load_mono(bass_path, target_sr=sr)

    n = max(len(kick_y), len(snare_y), len(bass_y))
    kick_y = np.pad(kick_y, (0, n - len(kick_y)))
    snare_y = np.pad(snare_y, (0, n - len(snare_y)))
    bass_y = np.pad(bass_y, (0, n - len(bass_y)))
    combined = kick_y + snare_y + bass_y

    hop_length = 512
    onset_env = librosa.onset.onset_strength(y=combined, sr=sr, hop_length=hop_length)

    melody_impulse = np.zeros_like(onset_env)
    for t in melody_times:
        frame = int(round(t * sr / hop_length))
        if 0 <= frame < len(melody_impulse):
            melody_impulse[frame] += MELODY_ONSET_IMPULSE_GAIN
    onset_env = onset_env + melody_impulse

    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=hop_length, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)

    kick_onsets = librosa.onset.onset_detect(y=kick_y, sr=sr, units="time")
    snare_onsets = librosa.onset.onset_detect(y=snare_y, sr=sr, units="time")
    bass_onsets = librosa.onset.onset_detect(y=bass_y, sr=sr, units="time")
    real_onsets = np.sort(np.concatenate([kick_onsets, snare_onsets, bass_onsets, np.array(melody_times)]))

    duration = n / float(sr)
    return {
        "tempo": float(tempo) if np.isscalar(tempo) else float(tempo[0]),
        "beat_times": beat_times,
        "real_onsets": real_onsets,
        "duration": duration,
    }


def main():
    parser = argparse.ArgumentParser(description="Pass 177 Lane 4 鼓+貝斯+和弦+旋律疊加偵測")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--source-lane", default="lane3_drum_bass_chord")
    parser.add_argument("--lane-id", default="lane4_melody")
    args = parser.parse_args()

    project_dir = args.project_dir
    kick_path = os.path.join(project_dir, "stems", "drums", "kick.wav")
    snare_path = os.path.join(project_dir, "stems", "drums", "snare.wav")
    audio_path = resolve_base_audio_path(project_dir)
    bass_path = _find_bass_stem(project_dir)
    vocal_path = _find_vocal_stem(project_dir)
    source_lane_dir = os.path.join(project_dir, "lanes", args.source_lane)
    source_beats_path = os.path.join(source_lane_dir, "beats.json")

    for p in (kick_path, snare_path, audio_path, source_beats_path):
        if not os.path.exists(p):
            print(f"[FATAL] 找不到必要檔案：{p}")
            sys.exit(1)
    if bass_path is None:
        print(f"[FATAL] 找不到任何貝斯 stem，無法建立 Lane 4。")
        sys.exit(1)
    if vocal_path is None:
        print(f"[WARN] 找不到任何人聲 stem，Lane 4 只會用吉他/鋼琴旋律 onset。")

    lane_dir = os.path.join(project_dir, "lanes", args.lane_id)
    click_dir = os.path.join(lane_dir, "click")
    os.makedirs(click_dir, exist_ok=True)

    with open(source_beats_path, "r", encoding="utf-8") as f:
        source_beats = json.load(f)["beats"]

    ranges = escalation_ranges(source_lane_dir)
    total_sec = sum(e - s for s, e in ranges)
    print(f"[Lane4] 來源 Lane：{args.source_lane}，需要重新分析的區間共 {len(ranges)} 段、合計 {total_sec:.1f} 秒。")

    print(f"[Lane4] 分析吉他/鋼琴旋律 onset + 人聲旋律 onset...")
    melody_times = _melody_onset_times(project_dir, vocal_path)
    print(f"[Lane4] 偵測到 {len(melody_times)} 個旋律 onset。")

    print(f"[Lane4] 用 {os.path.basename(bass_path)} + 旋律 onset 疊加鼓軌，重新分析全曲拍點...")
    result = detect_lane4_beats(kick_path, snare_path, bass_path, melody_times)
    print(f"[Lane4] 鼓+貝斯+旋律估計節奏 {result['tempo']:.1f} BPM。")

    def in_any_range(t):
        return any(s <= t < e for s, e in ranges)

    kept_count = sum(1 for row in source_beats if not in_any_range(row[0]))
    inserted_count = sum(1 for t in result["beat_times"] if in_any_range(float(t)))
    final_beats = splice_beats(source_beats, result["beat_times"], ranges)
    print(f"[Lane4] 拼接後共 {len(final_beats)} 拍（沿用上一 Lane：{kept_count} 拍，新分析：{inserted_count} 拍）。")

    blocks = build_confidence_blocks(final_beats, result["real_onsets"], result["duration"])
    needs_review_count = sum(1 for b in blocks if b["needs_review"])
    print(f"[Lane4] 全曲合併成 {len(blocks)} 個區塊，其中 {needs_review_count} 個仍需複核。")

    with open(os.path.join(lane_dir, "blocks.json"), "w", encoding="utf-8") as f:
        json.dump(blocks, f, ensure_ascii=False, indent=2)
    with open(os.path.join(lane_dir, "beats.json"), "w", encoding="utf-8") as f:
        json.dump({"tempo": result["tempo"], "beats": final_beats}, f, ensure_ascii=False, indent=2)

    print(f"[Lane4] 渲染 click 音檔...")
    from pgm_craft.synthesizer import PGMSynthesizer
    synth = PGMSynthesizer()
    click_path, mix_path = synth.synthesize_click(audio_path, final_beats, output_dir=click_dir)
    print(f"[Lane4] 完成：{mix_path}")


if __name__ == "__main__":
    main()
