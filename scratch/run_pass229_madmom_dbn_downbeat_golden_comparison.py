"""PASS-229: evaluate madmom's DBN downbeat tracker (Böck/Krebs/Widmer --
already installed as a dependency in this project, but never used for
downbeat tracking anywhere in the codebase) against World is Mine.

Motivation: the user pointed out a real design flaw in Pass 228's
kick-accent scoring metric -- it assumes beat==1 should have the loudest
kick, which is false for syncopated passages (kick deliberately on an
off-beat). A correct downbeat tracker should stay phase-locked to a
consistent tempo regardless of which instrument accent falls where.
madmom's DBN decoder is designed for exactly this: an RNN activation
layer proposes per-frame beat/downbeat/none probabilities (which CAN be
locally misled by a loud off-beat kick), but the DBN/HMM decoder then
finds the single globally tempo-consistent path through the whole
sequence, so one strong off-beat hit shouldn't flip the phase unless the
whole passage consistently supports it.

Runs the pretrained RNNDownBeatProcessor + DBNDownBeatTrackingProcessor
directly on the source WAV (no stem separation, no custom evidence
fusion) -- evaluated as a drop-in whole-pipeline replacement/consensus
candidate, same framing as the Pass 220 beat_this test.

IMPORTANT methodology note (found during this same pass): comparing by
independently filtering each list to "downbeats within [segment_start,
segment_end)" and then index-aligning creates a spurious ~1-bar
constant residual whenever the two lists' first in-window downbeat
happens to land on a different absolute bar near the boundary (each
list's own upstream count differs slightly before the boundary). This
is a comparison-methodology artifact, not a real tracking disagreement
-- confirmed by inspecting raw per-beat labels, which matched golden's
beat numbers almost exactly (~10-30ms) throughout Verse1. This script
uses NEAREST-NEIGHBOR matching per segment instead (for each golden
downbeat, find the closest madmom downbeat), which has no such boundary
artifact.
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
REPORT_PATH = os.path.join(ROOT, "scratch", "pass229_madmom_dbn_downbeat_golden_comparison.json")

SEGMENTS = [
    ("Intro", 0.0, 25.813243),
    ("Verse 1", 25.813243, 86.907256),
    ("Chorus 1", 86.907256, 147.977778),
    ("Outro", 147.977778, float("inf")),
]


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-229] blocked: missing {AUDIO_PATH}")
        return 1

    from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor

    print("[PASS-229] running RNNDownBeatProcessor activation...")
    act = RNNDownBeatProcessor()(AUDIO_PATH)
    print("[PASS-229] running DBNDownBeatTrackingProcessor (beats_per_bar=[4])...")
    dbn = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=100)
    result = dbn(act)  # Nx2 array: [time, beat_position_in_bar]

    beats = sorted(set(round(float(t), 6) for t, _ in result))
    downbeats = sorted(set(round(float(t), 6) for t, pos in result if int(round(pos)) == 1))

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)["measure_map"]
    golden_downbeats = [float(m["start_time"]) for m in golden]

    overall = {
        "madmom_total_beats": len(beats),
        "madmom_total_downbeats": len(downbeats),
        "golden_total_downbeats": len(golden_downbeats),
    }

    segment_reports = []
    for name, start, end in SEGMENTS:
        g_seg = [g for g in golden_downbeats if start <= g < end]
        residuals = []
        for g in g_seg:
            if not downbeats:
                continue
            nearest = min(downbeats, key=lambda d: abs(d - g))
            residuals.append(round(nearest - g, 4))
        n = len(residuals)
        within_50ms = sum(1 for r in residuals if abs(r) <= 0.05)
        segment_reports.append({
            "segment": name,
            "golden_count": len(g_seg),
            "matched": n,
            "mean_abs_residual": round(sum(abs(r) for r in residuals) / n, 4) if n else None,
            "max_abs_residual": round(max((abs(r) for r in residuals), default=0.0), 4),
            "within_50ms_count": within_50ms,
            "within_50ms_ratio": round(within_50ms / n, 4) if n else None,
        })

    report = {
        "pass": "PASS-229",
        "model": "madmom RNNDownBeatProcessor + DBNDownBeatTrackingProcessor (beats_per_bar=[4])",
        "matching_method": "nearest_neighbor_per_segment (NOT independently-filtered index-alignment -- see module docstring)",
        "overall": overall,
        "segments": segment_reports,
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[PASS-229] report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
