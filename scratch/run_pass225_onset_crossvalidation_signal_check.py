r"""PASS-225: does an independent real-onset-distance signal correlate with
which committed bars are actually WRONG?

Motivation: after ruling out 3 different tuning knobs inside
_best_candidate/_phase_consistency_score/_expected_bar_duration (Pass
219-224, all either uniformly regressed real data or showed unseparable
mixed effects), the user's own stated architecture philosophy -- many
small validated models, filter, fuse, post-process -- points at a
STRUCTURALLY different mechanism: cross-validate committed bar starts
against an INDEPENDENT signal that isn't derived from the same
evidence-fusion pipeline, then veto/replace ones that don't hold up.
This is exactly what headbang.py's ConsensusBeatTracker does (validate
against real percussion onsets) and what Pass 198 already used once
(scratch/verify_pass198_promotions_against_steady_runs.py) for a
different, narrower purpose.

Before designing any concrete veto/correction mechanism, first check
whether the signal is even informative: does "far from the nearest
independent onset" predict "large residual vs golden"? If yes, this is
worth building into production. If the correlation is weak/absent, this
whole direction is a dead end too, and it's cheaper to find that out now
with a pure offline diagnostic than after implementing something.

Uses SteadyPercussionCountAnchorNode._detect_onsets (existing, reused
verbatim -- Pass 198's onset-detection precedent) on the cached kick/
snare/hihat_cymbals/drums stems, and the Pass 223 simulator's baseline
(now validated to match real production exactly, 98/98 ticks) as the
committed bar-start sequence to test.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.workflow.beat_tracking_bt import SteadyPercussionCountAnchorNode

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from simulate_pass223_periodic_reanchor import _load_trace, simulate  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
STEMS_DIR = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")
GOLDEN_PATH = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json"

SEGMENTS = [
    ("Intro", 0.0, 25.813243),
    ("Verse 1", 25.813243, 86.907256),
    ("Chorus 1", 86.907256, 147.977778),
    ("Outro", 147.977778, float("inf")),
]


def _nearest_golden_residual(committed, golden_downbeats):
    """Index-aligned per-segment residual (same methodology as every prior
    pass), returned as a dict {committed_time: signed_residual_sec}."""
    out = {}
    for _, start, end in SEGMENTS:
        seg = [b for b in committed if start <= b < end]
        g_seg = [g for g in golden_downbeats if start <= g < end]
        n = min(len(seg), len(g_seg))
        for i in range(n):
            out[seg[i]] = seg[i] - g_seg[i]
    return out


def main():
    trace = _load_trace()
    committed = simulate(trace, reanchor_interval=None)
    print(f"committed bars (validated raw loop output): {len(committed)}")

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)["measure_map"]
    golden_downbeats = [float(m["start_time"]) for m in golden]

    residuals = _nearest_golden_residual(committed, golden_downbeats)
    print(f"bars with a golden residual (index-aligned overlap): {len(residuals)}")

    node = SteadyPercussionCountAnchorNode()
    onset_sets = {}
    for stem_key, rel in node.STEM_CANDIDATES + [node.WHOLE_DRUM_STEM]:
        path = os.path.join(STEMS_DIR, *rel)
        if not os.path.exists(path):
            print(f"  [skip] missing stem: {path}")
            continue
        onsets = node._detect_onsets(path)
        onset_sets[stem_key] = onsets
        print(f"  detected {len(onsets)} independent onsets in '{stem_key}'")

    all_onsets = sorted({t for onsets in onset_sets.values() for t in onsets})
    print(f"union of all independent onsets: {len(all_onsets)}")
    print()

    rows = []
    for bar_time in committed:
        if bar_time not in residuals:
            continue
        # nearest independent onset across ALL stems combined
        dist = min((abs(bar_time - t) for t in all_onsets), default=float("inf"))
        rows.append((bar_time, residuals[bar_time], dist))

    print(f"{'bar_time':>10} {'golden_residual':>16} {'nearest_onset_dist_ms':>22}")
    for bar_time, res, dist in rows:
        print(f"{bar_time:10.3f} {res:16.3f} {dist*1000:22.1f}")
    print()

    # Correlation check: bucket by |golden residual| and report mean onset
    # distance per bucket. If the signal is informative, larger residual
    # buckets should show larger mean onset distance.
    buckets = [("<=0.1s (good)", lambda r: abs(r) <= 0.1),
               ("0.1-0.5s", lambda r: 0.1 < abs(r) <= 0.5),
               ("0.5-1.5s", lambda r: 0.5 < abs(r) <= 1.5),
               (">1.5s (bad)", lambda r: abs(r) > 1.5)]
    print(f"{'bucket':>16} {'n':>4} {'mean_onset_dist_ms':>20} {'median_onset_dist_ms':>22}")
    for label, pred in buckets:
        vals = [dist for _, res, dist in rows if pred(res)]
        if not vals:
            print(f"{label:>16} {0:>4} {'--':>20} {'--':>22}")
            continue
        vals_sorted = sorted(vals)
        mean_ms = sum(vals) / len(vals) * 1000
        median_ms = vals_sorted[len(vals_sorted) // 2] * 1000
        print(f"{label:>16} {len(vals):>4} {mean_ms:20.1f} {median_ms:22.1f}")


if __name__ == "__main__":
    raise SystemExit(main())
