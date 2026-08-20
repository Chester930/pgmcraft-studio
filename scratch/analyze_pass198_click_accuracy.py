r"""
Pass 198 Click 準確度量化分析——核對階段 A（小節內隱藏 downbeat 升格）
實際運作後，5-45s 這段（使用者回報 9 秒/11 秒之後有問題）的 click 是否
真的落在真實鼓點上。改自 analyze_pass197_click_accuracy.py，只掃描
使用者回報有問題的區段並列出逐拍細節（而非分散的目標窗口）。
"""

import os
import sys
import json

import numpy as np
import librosa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_DIR = (
    r"D:\Users\666\Desktop\UVR5 音檔\自動節拍器\.claude\worktrees\pass171-multi-variant-harness"
    r"\outputs\pass198_default_pipeline_reverify"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
)
STEMS_DIR = os.path.join(PROJECT_DIR, "stems", "drums")
MEASURE_MAP_PATH = os.path.join(PROJECT_DIR, "reports", "measure_map.json")

TOLERANCE_SEC = 0.05
SCAN_START, SCAN_END = 5.0, 45.0


def detect_onsets(path, sr_target=22050):
    y, sr = librosa.load(path, sr=sr_target, mono=True)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    return librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, backtrack=True, units="time")


def nearest_onset_dist(t, onsets):
    if len(onsets) == 0:
        return None
    return float(np.min(np.abs(onsets - t)))


def main():
    with open(MEASURE_MAP_PATH, encoding="utf-8") as f:
        data = json.load(f)
    measure_map = data["measure_map"]

    click_times = sorted(
        b["time"] for m in measure_map for b in m["beats"] if SCAN_START <= b["time"] <= SCAN_END
    )

    print("載入鼓組音軌，偵測真實 onset...")
    kick = detect_onsets(os.path.join(STEMS_DIR, "kick.wav"))
    snare = detect_onsets(os.path.join(STEMS_DIR, "snare.wav"))
    drums = detect_onsets(os.path.join(STEMS_DIR, "drums.wav"))

    hit, total = 0, 0
    for t in click_times:
        dk, ds, dd = nearest_onset_dist(t, kick), nearest_onset_dist(t, snare), nearest_onset_dist(t, drums)
        best_label, best_dist = min(
            [("kick", dk), ("snare", ds), ("drums", dd)],
            key=lambda x: x[1] if x[1] is not None else 999,
        )
        ok = best_dist is not None and best_dist <= TOLERANCE_SEC
        total += 1
        hit += int(ok)
        print(f"{t:8.3f}s  best={best_label:5s} err={best_dist*1000:7.1f}ms  {'OK ' if ok else 'BAD'}")

    print(f"\n總計：{hit}/{total} 個 click 落在 50ms 容差內（{SCAN_START}s-{SCAN_END}s）")


if __name__ == "__main__":
    main()
