"""PASS-220: re-test CPJKU's Beat This! (ISMIR 2024, pretrained, MIT licensed)
against World is Mine using the same golden-aligned, per-segment,
index-aligned comparison methodology established in Pass 217-219 -- not
just spot-checking a handful of known points like the original Pass 200
baseline did two weeks ago.

Runs the official File2Beats API directly on the source WAV (no stem
separation, no custom evidence fusion at all -- this is a from-scratch
pretrained model, evaluated exactly as a drop-in replacement candidate for
the entire custom beat-tracking core would be used).
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_PATH = os.path.join(
    ROOT, "outputs", "pass198_default_pipeline_reverify", AUDIO_NAME, "source", AUDIO_NAME + ".wav"
)
GOLDEN_PATH = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json"
REPORT_PATH = os.path.join(ROOT, "scratch", "pass220_beat_this_golden_comparison.json")

SEGMENTS = [
    ("Intro", 0.0, 25.813243),
    ("Verse 1", 25.813243, 86.907256),
    ("Chorus 1", 86.907256, 147.977778),
    ("Outro", 147.977778, float("inf")),
]


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-220] blocked: missing {AUDIO_PATH}")
        return 1

    from beat_this.inference import File2Beats

    tracker = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
    beats_raw, downbeats_raw = tracker(AUDIO_PATH)
    beats = sorted(set(round(float(t), 6) for t in beats_raw))
    downbeats = sorted(set(round(float(t), 6) for t in downbeats_raw))

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)["measure_map"]
    golden_downbeats = [float(m["start_time"]) for m in golden]

    overall = {
        "beat_this_total_beats": len(beats),
        "beat_this_total_downbeats": len(downbeats),
        "golden_total_downbeats": len(golden_downbeats),
    }

    segment_reports = []
    for name, start, end in SEGMENTS:
        bt_seg = [d for d in downbeats if start <= d < end]
        g_seg = [g for g in golden_downbeats if start <= g < end]
        n = min(len(bt_seg), len(g_seg))
        residuals = [bt_seg[i] - g_seg[i] for i in range(n)]
        segment_reports.append({
            "segment": name,
            "beat_this_count": len(bt_seg),
            "golden_count": len(g_seg),
            "index_aligned_residuals_sample": [
                {"idx": i, "beat_this": round(bt_seg[i], 3), "golden": round(g_seg[i], 3), "residual": round(residuals[i], 3)}
                for i in range(0, n, max(1, n // 10))
            ] + ([{"idx": n - 1, "beat_this": round(bt_seg[n-1], 3), "golden": round(g_seg[n-1], 3), "residual": round(residuals[n-1], 3)}] if n else []),
            "max_abs_residual": round(max((abs(r) for r in residuals), default=0.0), 3),
            "mean_abs_residual": round(sum(abs(r) for r in residuals) / n, 3) if n else None,
        })

    report = {
        "pass": "PASS-220",
        "model": "CPJKU beat_this (final0, dbn=False)",
        "overall": overall,
        "segments": segment_reports,
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[PASS-220] report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
