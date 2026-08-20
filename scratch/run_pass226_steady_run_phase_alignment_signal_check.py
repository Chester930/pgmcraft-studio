r"""PASS-226: refinement of Pass 225's negative onset-proximity signal.

Pass 225 found that "distance to nearest independent onset" doesn't
discriminate correct-phase from wrong-phase committed bars, because this
song's dense 16th-note hi-hat/kick pattern means onsets are everywhere,
and because every candidate is already onset-derived by construction.

This script tests a more structured signal: instead of "near ANY onset",
check whether a committed bar lands on the periodic GRID defined by a
locally-detected steady onset run, at BAR-length spacing (not beat-length
1x/2x like SteadyPercussionCountAnchorNode._find_steady_runs normally
uses -- that finds beat-level pulse trains, which are just as dense as
raw onsets in this song and would be equally uninformative). Also
restricts to the KICK stem specifically (not the dense hihat/combined
onset set) since kick is the most likely instrument to mark actual
downbeats rather than every subdivision in this genre.

Approach: find steady runs in the kick stem's onsets using
known_beat_length = expected_bar_duration (i.e. multiple=1 IS bar-length
here, by passing bar duration as the "beat" length into the existing
_find_steady_runs machinery -- no new detection code, just a different
periodicity to test against). For each committed bar, compute the
residual to the nearest point on the nearest overlapping run's own
bar-length grid (not to the nearest raw onset). Bucket against golden
residual same as Pass 225 to check whether this discriminates better.
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

EXPECTED_BAR_DURATION_SEC = 1.4528571428571446  # same global constant the real arbitration uses


def _nearest_golden_residual(committed, golden_downbeats):
    out = {}
    for _, start, end in SEGMENTS:
        seg = [b for b in committed if start <= b < end]
        g_seg = [g for g in golden_downbeats if start <= g < end]
        n = min(len(seg), len(g_seg))
        for i in range(n):
            out[seg[i]] = seg[i] - g_seg[i]
    return out


def _bar_grid_residual(bar_time, runs):
    """Distance from bar_time to the nearest point on the nearest
    overlapping run's own bar-length grid (run start + k * mean_interval),
    not to any raw onset."""
    best = float("inf")
    for run in runs:
        if not (run["start_time"] - 5.0 <= bar_time <= run["end_time"] + 5.0):
            continue
        interval = run["mean_interval_sec"]
        k = round((bar_time - run["start_time"]) / interval)
        grid_point = run["start_time"] + k * interval
        best = min(best, abs(bar_time - grid_point))
    return best


def main():
    trace = _load_trace()
    committed = simulate(trace, reanchor_interval=None)
    print(f"committed bars: {len(committed)}")

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)["measure_map"]
    golden_downbeats = [float(m["start_time"]) for m in golden]
    residuals = _nearest_golden_residual(committed, golden_downbeats)

    node = SteadyPercussionCountAnchorNode(
        min_run_length=3,
        max_interval_cv=0.15,
        beat_length_tolerance_pct=0.15,
    )
    node.ALLOWED_BEAT_MULTIPLES = (1,)  # bar-length grid only, we pass bar duration as "beat"

    all_runs = []
    for stem_key, rel in node.STEM_CANDIDATES + [node.WHOLE_DRUM_STEM]:
        path = os.path.join(STEMS_DIR, *rel)
        if not os.path.exists(path):
            continue
        onsets = node._detect_onsets(path)
        runs = node._find_steady_runs(onsets, EXPECTED_BAR_DURATION_SEC, [])
        print(f"  '{stem_key}': {len(onsets)} onsets -> {len(runs)} bar-length steady runs")
        for r in runs:
            all_runs.append({**r, "stem": stem_key})

    print(f"total bar-length steady runs across all stems: {len(all_runs)}")
    if all_runs:
        for r in sorted(all_runs, key=lambda r: r["start_time"])[:10]:
            print(f"    [{r['stem']}] {r['start_time']:.3f}-{r['end_time']:.3f}s "
                  f"count={r['count']} mean_interval={r['mean_interval_sec']:.4f} cv={r['cv']:.3f}")
    print()

    rows = []
    for bar_time in committed:
        if bar_time not in residuals:
            continue
        grid_dist = _bar_grid_residual(bar_time, all_runs)
        rows.append((bar_time, residuals[bar_time], grid_dist))

    covered = [r for r in rows if r[2] != float("inf")]
    print(f"bars with golden overlap: {len(rows)}, bars covered by >=1 bar-length steady run: {len(covered)}")
    print()

    print(f"{'bar_time':>10} {'golden_residual':>16} {'bar_grid_dist_ms':>18}")
    for bar_time, res, dist in rows:
        dist_str = f"{dist*1000:.1f}" if dist != float("inf") else "no_run"
        print(f"{bar_time:10.3f} {res:16.3f} {dist_str:>18}")
    print()

    buckets = [("<=0.1s (good)", lambda r: abs(r) <= 0.1),
               ("0.1-0.5s", lambda r: 0.1 < abs(r) <= 0.5),
               ("0.5-1.5s", lambda r: 0.5 < abs(r) <= 1.5),
               (">1.5s (bad)", lambda r: abs(r) > 1.5)]
    print(f"{'bucket':>16} {'n':>4} {'n_covered':>10} {'mean_grid_dist_ms':>20} {'median_grid_dist_ms':>22}")
    for label, pred in buckets:
        vals = [dist for _, res, dist in rows if pred(res) and dist != float("inf")]
        n_total = len([1 for _, res, _ in rows if pred(res)])
        if not vals:
            print(f"{label:>16} {n_total:>4} {0:>10} {'--':>20} {'--':>22}")
            continue
        vals_sorted = sorted(vals)
        mean_ms = sum(vals) / len(vals) * 1000
        median_ms = vals_sorted[len(vals_sorted) // 2] * 1000
        print(f"{label:>16} {n_total:>4} {len(vals):>10} {mean_ms:20.1f} {median_ms:22.1f}")


if __name__ == "__main__":
    raise SystemExit(main())
