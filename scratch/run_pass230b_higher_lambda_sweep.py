"""PASS-230 continued: push transition_lambda higher (200 already beat the
default 100 across the board in the first sweep -- counter to the
"lower lambda tracks real tempo changes better" hypothesis; apparently
in sparse-evidence sections a stiffer/steadier DBN outperforms a more
adaptive one because it resists noisy local evidence better than it
loses from resisting genuine tempo drift). Check where this trend
saturates or reverses.
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
REPORT_PATH = os.path.join(ROOT, "scratch", "pass230b_higher_lambda_sweep.json")

SEGMENTS = [
    ("Intro", 0.0, 25.813243),
    ("Verse 1", 25.813243, 86.907256),
    ("Chorus 1", 86.907256, 147.977778),
    ("Outro", 147.977778, float("inf")),
]

LAMBDA_VALUES = [200, 300, 500, 800, 1500, 3000]


def evaluate(downbeats, golden_downbeats):
    segment_reports = []
    for name, start, end in SEGMENTS:
        g_seg = [g for g in golden_downbeats if start <= g < end]
        residuals = []
        for g in g_seg:
            if not downbeats:
                continue
            nearest = min(downbeats, key=lambda d: abs(d - g))
            residuals.append(nearest - g)
        n = len(residuals)
        within_50ms = sum(1 for r in residuals if abs(r) <= 0.05)
        segment_reports.append({
            "segment": name,
            "golden_count": len(g_seg),
            "mean_abs_residual": round(sum(abs(r) for r in residuals) / n, 4) if n else None,
            "max_abs_residual": round(max((abs(r) for r in residuals), default=0.0), 4),
            "within_50ms_ratio": round(within_50ms / n, 4) if n else None,
        })
    return segment_reports


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-230b] blocked: missing {AUDIO_PATH}")
        return 1

    from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor

    print("[PASS-230b] running RNNDownBeatProcessor activation (once, reused across sweep)...")
    act = RNNDownBeatProcessor()(AUDIO_PATH)

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)["measure_map"]
    golden_downbeats = [float(m["start_time"]) for m in golden]

    results = []
    for lam in LAMBDA_VALUES:
        print(f"[PASS-230b] decoding with transition_lambda={lam}...")
        dbn = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=100, transition_lambda=lam)
        result = dbn(act)
        downbeats = sorted(set(round(float(t), 6) for t, pos in result if int(round(pos)) == 1))
        segments = evaluate(downbeats, golden_downbeats)
        results.append({"transition_lambda": lam, "total_downbeats": len(downbeats), "segments": segments})
        for seg in segments:
            print(f"    {seg['segment']:>10}: mean_abs={seg['mean_abs_residual']} within_50ms={seg['within_50ms_ratio']}")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({"pass": "PASS-230b", "sweep": results}, f, ensure_ascii=False, indent=2)
    print(f"[PASS-230b] report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
