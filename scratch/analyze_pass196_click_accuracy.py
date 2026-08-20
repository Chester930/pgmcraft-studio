r"""
Pass 196 Click 準確度量化分析——用真實鼓組音軌的 onset 偵測，核對每個
click 打點位置是否真的落在鼓組的真實擊點上（不是主觀聽感，是可驗證的
訊號分析）。
"""

import os
import sys
import json

import numpy as np
import librosa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_DIR = (
    r"D:\Users\666\Desktop\UVR5 音檔\自動節拍器\.claude\worktrees\pass171-multi-variant-harness"
    r"\outputs\pass196_default_pipeline_reverify"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
)
STEMS_DIR = os.path.join(PROJECT_DIR, "stems", "drums")
MEASURE_MAP_PATH = os.path.join(PROJECT_DIR, "reports", "measure_map.json")

TOLERANCE_SEC = 0.05  # 50ms 容差——落在這個範圍內視為「有對應真實擊點」

TARGET_WINDOWS = [
    ("問題點 8.041s", 6.0, 12.0),
    ("問題點 21.458s", 19.0, 25.0),
    ("問題點 32.382s", 30.0, 36.0),
    ("問題點 77.803s", 75.0, 82.0),
    ("問題點 81.446s", 79.0, 86.0),
    ("問題點 93.802s", 91.0, 97.0),
    ("問題點 97.197s", 95.0, 101.0),
    ("問題點 108.652s", 106.0, 112.0),
    ("問題點 152.023s", 149.0, 156.0),
    ("18-20秒目標區段", 16.0, 22.0),
]


def detect_onsets(path, sr_target=22050):
    y, sr = librosa.load(path, sr=sr_target, mono=True)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, backtrack=True, units="time")
    return onsets, y, sr


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

    print("載入鼓組音軌，偵測真實 onset...")
    kick_onsets, _, _ = detect_onsets(os.path.join(STEMS_DIR, "kick.wav"))
    snare_onsets, _, _ = detect_onsets(os.path.join(STEMS_DIR, "snare.wav"))
    hihat_onsets, _, _ = detect_onsets(os.path.join(STEMS_DIR, "hihat_cymbals.wav"))
    drums_onsets, _, _ = detect_onsets(os.path.join(STEMS_DIR, "drums.wav"))
    print(f"kick: {len(kick_onsets)} onsets, snare: {len(snare_onsets)}, hihat: {len(hihat_onsets)}, drums: {len(drums_onsets)}")

    for label, lo, hi in TARGET_WINDOWS:
        print(f"\n{'='*90}\n{label}（{lo}s - {hi}s）\n{'='*90}")
        window_clicks = [t for t in click_times if lo <= t <= hi]
        for t in window_clicks:
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


if __name__ == "__main__":
    main()
