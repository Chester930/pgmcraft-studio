r"""
用跟 Pass 184 一樣的局部視窗 onset 偵測（window=10s, hop=7s），重新核對
8.041s（7-11s）和 97.197s（95-101s）這兩處，排除掉「整首歌一次分析導致
安靜段落被稀釋、誤判成沒有真實擊點」的可能性。
"""

import os
import sys
import json

import numpy as np
import librosa

PROJECT_DIR = (
    r"D:\Users\666\Desktop\UVR5 音檔\自動節拍器\.claude\worktrees\pass171-multi-variant-harness"
    r"\outputs\pass196_default_pipeline_reverify"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
)
STEMS_DIR = os.path.join(PROJECT_DIR, "stems", "drums")
MEASURE_MAP_PATH = os.path.join(PROJECT_DIR, "reports", "measure_map.json")

WINDOW_SEC = 10.0
HOP_SEC = 7.0
TOLERANCE_SEC = 0.05


def windowed_onset_detect(path, sr_target=22050, window_sec=WINDOW_SEC, hop_sec=HOP_SEC):
    y, sr = librosa.load(path, sr=sr_target, mono=True)
    duration = len(y) / sr
    all_onsets = []
    t = 0.0
    while t < duration:
        start_sample = int(t * sr)
        end_sample = min(len(y), int((t + window_sec) * sr))
        if end_sample - start_sample < sr * 0.5:
            break
        segment = y[start_sample:end_sample]
        onset_env = librosa.onset.onset_strength(y=segment, sr=sr)
        onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, backtrack=True, units="time")
        all_onsets.extend([t + o for o in onsets])
        t += hop_sec
    all_onsets = sorted(set(round(o, 3) for o in all_onsets))
    # 合併 30ms 內的重複偵測
    merged = []
    for o in all_onsets:
        if not merged or o - merged[-1] > 0.03:
            merged.append(o)
    return np.array(merged)


def nearest_onset_dist(t, onsets):
    if len(onsets) == 0:
        return None
    return float(np.min(np.abs(onsets - t)))


def main():
    with open(MEASURE_MAP_PATH, encoding="utf-8") as f:
        data = json.load(f)
    measure_map = data["measure_map"]

    click_times = []
    for m in measure_map:
        for b in m["beats"]:
            click_times.append(b["time"])
    click_times = sorted(click_times)

    print(f"局部視窗 onset 偵測（window={WINDOW_SEC}s, hop={HOP_SEC}s，跟 Pass 184 相同）...")
    kick_onsets = windowed_onset_detect(os.path.join(STEMS_DIR, "kick.wav"))
    snare_onsets = windowed_onset_detect(os.path.join(STEMS_DIR, "snare.wav"))
    hihat_onsets = windowed_onset_detect(os.path.join(STEMS_DIR, "hihat_cymbals.wav"))
    drums_onsets = windowed_onset_detect(os.path.join(STEMS_DIR, "drums.wav"))
    print(f"kick: {len(kick_onsets)}, snare: {len(snare_onsets)}, hihat: {len(hihat_onsets)}, drums: {len(drums_onsets)}")

    for label, lo, hi in [("8.041s 問題點", 6.0, 12.0), ("97.197s 問題點", 95.0, 101.0)]:
        print(f"\n{'='*90}\n{label}（{lo}s - {hi}s，局部視窗偵測）\n{'='*90}")
        for t in [c for c in click_times if lo <= c <= hi]:
            d_kick = nearest_onset_dist(t, kick_onsets)
            d_snare = nearest_onset_dist(t, snare_onsets)
            d_hihat = nearest_onset_dist(t, hihat_onsets)
            d_drums = nearest_onset_dist(t, drums_onsets)
            best_label, best_dist = min(
                [("kick", d_kick), ("snare", d_snare), ("hihat", d_hihat), ("drums整軌", d_drums)],
                key=lambda x: (x[1] if x[1] is not None else 999),
            )
            verdict = "✅ 有對應真實擊點" if best_dist is not None and best_dist <= TOLERANCE_SEC else "❌ 附近沒有明顯鼓組擊點"
            print(
                f"  click@{t:.3f}s  最近={best_label}(差{best_dist*1000:.1f}ms)  "
                f"[kick={d_kick*1000:.1f}ms snare={d_snare*1000:.1f}ms hihat={d_hihat*1000:.1f}ms drums={d_drums*1000:.1f}ms]  {verdict}"
            )

        # 額外印出這個視窗內鼓組整軌實際偵測到的所有 onset，方便肉眼比對
        window_drum_onsets = [o for o in drums_onsets if lo <= o <= hi]
        print(f"\n  [這個視窗內 drums.wav 整軌實際偵測到的 onset]：{[round(o,3) for o in window_drum_onsets]}")


if __name__ == "__main__":
    main()
