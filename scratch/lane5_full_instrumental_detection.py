r"""
Pass 177（延伸）— Lane 5：無人聲完整混音重新分析

只針對 Lane 4（+旋律）被標記「不通過」（或還沒標記，保守也算需要複核）的
區塊重新分析，範圍外沿用 Lane 4 的拍點不動。

跟 Lane1-4 的關鍵差異：Lane1-4 疊加證據的方式是把 kick.wav、snare.wav、
bass stem、和弦 onset、旋律 onset 這些「分開抽出來的音頭訊號」各自加總成
一條合成的 onset envelope——不是真正的完整混音，分開再疊加可能會漏掉真正
混音裡才有的聲學交互作用（樂器互相遮蔽、真實的過渡瞬態）。Lane 5 改用
`stems/no_vocals.wav`（無人聲全樂器混音，跟 Track B 同一份檔案）本身直接
分析，捕捉 Lane1-4 那種分軌疊加方式抓不到的東西。

跟 Track B 的差異：Track B 是對這份無人聲混音做全曲獨立分析（不吃任何
前面 Lane 的結果）；Lane 5 只重新分析 Lane 4 判定可疑的殘餘區段，其餘沿用
Lane 4 已確認的拍點——是疊加證據鏈的第 5 層，不是獨立分析。

用法：
    python scratch/lane5_full_instrumental_detection.py --project-dir "<專案資料夾路徑>"
        [--source-lane lane4_melody] [--lane-id lane5_full_instrumental]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lane_common import load_mono, escalation_ranges, splice_beats, build_confidence_blocks, resolve_base_audio_path


def _find_instrumental_stem(project_dir: str):
    for name in ("no_vocals.wav", "instrumental.wav"):
        p = os.path.join(project_dir, "stems", name)
        if os.path.exists(p):
            return p
    return None


def detect_lane5_beats(instrumental_path):
    import librosa
    import numpy as np

    y, sr = load_mono(instrumental_path)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    real_onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time")

    duration = len(y) / float(sr)
    return {
        "tempo": float(tempo) if np.isscalar(tempo) else float(tempo[0]),
        "beat_times": beat_times,
        "real_onsets": real_onsets,
        "duration": duration,
    }


def main():
    parser = argparse.ArgumentParser(description="Pass 177 Lane 5 無人聲完整混音重新分析")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--source-lane", default="lane4_melody")
    parser.add_argument("--lane-id", default="lane5_full_instrumental")
    args = parser.parse_args()

    project_dir = args.project_dir
    audio_path = resolve_base_audio_path(project_dir)
    instrumental_path = _find_instrumental_stem(project_dir)
    source_lane_dir = os.path.join(project_dir, "lanes", args.source_lane)
    source_beats_path = os.path.join(source_lane_dir, "beats.json")

    for p in (audio_path, source_beats_path):
        if not os.path.exists(p):
            print(f"[FATAL] 找不到必要檔案：{p}")
            sys.exit(1)
    if instrumental_path is None:
        print(f"[FATAL] 找不到 stems/no_vocals.wav 或 stems/instrumental.wav，無法建立 Lane 5。")
        sys.exit(1)

    lane_dir = os.path.join(project_dir, "lanes", args.lane_id)
    click_dir = os.path.join(lane_dir, "click")
    os.makedirs(click_dir, exist_ok=True)

    with open(source_beats_path, "r", encoding="utf-8") as f:
        source_beats = json.load(f)["beats"]

    ranges = escalation_ranges(source_lane_dir)
    total_sec = sum(e - s for s, e in ranges)
    print(f"[Lane5] 來源 Lane：{args.source_lane}，需要重新分析的區間共 {len(ranges)} 段、合計 {total_sec:.1f} 秒。")

    print(f"[Lane5] 用 {os.path.basename(instrumental_path)}（完整無人聲混音，非分軌疊加）重新分析全曲拍點...")
    result = detect_lane5_beats(instrumental_path)
    print(f"[Lane5] 完整混音估計節奏 {result['tempo']:.1f} BPM。")

    def in_any_range(t):
        return any(s <= t < e for s, e in ranges)

    kept_count = sum(1 for row in source_beats if not in_any_range(row[0]))
    inserted_count = sum(1 for t in result["beat_times"] if in_any_range(float(t)))
    final_beats = splice_beats(source_beats, result["beat_times"], ranges)
    print(f"[Lane5] 拼接後共 {len(final_beats)} 拍（沿用上一 Lane：{kept_count} 拍，新分析：{inserted_count} 拍）。")

    blocks = build_confidence_blocks(final_beats, result["real_onsets"], result["duration"])
    needs_review_count = sum(1 for b in blocks if b["needs_review"])
    print(f"[Lane5] 全曲合併成 {len(blocks)} 個區塊，其中 {needs_review_count} 個仍需複核。")

    with open(os.path.join(lane_dir, "blocks.json"), "w", encoding="utf-8") as f:
        json.dump(blocks, f, ensure_ascii=False, indent=2)
    with open(os.path.join(lane_dir, "beats.json"), "w", encoding="utf-8") as f:
        json.dump({"tempo": result["tempo"], "beats": final_beats}, f, ensure_ascii=False, indent=2)

    print(f"[Lane5] 渲染 click 音檔...")
    from pgm_craft.synthesizer import PGMSynthesizer
    synth = PGMSynthesizer()
    click_path, mix_path = synth.synthesize_click(audio_path, final_beats, output_dir=click_dir)
    print(f"[Lane5] 完成：{mix_path}")


if __name__ == "__main__":
    main()
