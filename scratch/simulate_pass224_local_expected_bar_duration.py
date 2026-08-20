"""PASS-224: offline test of a locally-adaptive expected_bar_duration.

Finding that motivates this: `BarStartCandidateCommitNode._expected_bar_duration`
(module3_barstart_v2_bt.py:1481) computes `np.median(np.diff(v1_reference_downbeats))`
over v1's WHOLE-SONG downbeat grid, every single tick -- confirmed via the
Pass 222 trace, where `expected_bar_duration_sec` is the literal same value
(1.452857) across all 101 ticks. Every arbitration decision in
`_best_candidate`/`_phase_consistency_score`/`_candidate_phase_alignment`
converts a raw time delta into "how many bars apart" via
`bars = round(delta / expected)` using this single frozen global constant.

This is a DIFFERENT knob from anything tried in Pass 219/221/223 (all 8
prior variants changed the ANCHOR -- which committed time to measure
residual FROM -- but kept this same frozen global `expected` divisor).
It is also different from Pass 212's two `_expected_interval` attempts,
which touched `DrumEvidenceBarSearchNode`'s candidate-generation step, not
this arbitration-scoring helper.

Pass 218 already measured real local tempo variation for this song:
Verse1=1.457s, Chorus1-early=1.455s, Chorus1-drift-zone=1.451s,
Outro=1.466s -- a real, if small (~1%), spread around the global
1.452857s constant this formula actually uses everywhere.

This script tests: does substituting a LOCALLY-WINDOWED median (computed
directly from v1_reference_beat_grid, an independent external signal, not
V2's own self-referencing committed history -- avoiding the contamination
mechanism that sank Pass 212's rolling-median-of-committed-intervals
attempt) for this one frozen constant change the baseline (no anchor
blending) or periodic-reanchor comparisons?

Reuses scratch/pass222_full_song_candidate_trace.jsonl (already validated
against real production for 60 consecutive ticks in Pass 223) and
scratch/pass218_v1_reference_downbeats.json (v1's raw downbeat list,
captured in Pass 218) -- no pipeline re-run needed.
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE_PATH = os.path.join(ROOT, "scratch", "pass222_full_song_candidate_trace.jsonl")
V1_DOWNBEATS_PATH = os.path.join(ROOT, "scratch", "pass218_v1_reference_downbeats.json")
GOLDEN_PATH = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json"

SEGMENTS = [
    ("Intro", 0.0, 25.813243),
    ("Verse 1", 25.813243, 86.907256),
    ("Chorus 1", 86.907256, 147.977778),
    ("Outro", 147.977778, float("inf")),
]


def _load_trace():
    with open(TRACE_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_v1_downbeats():
    with open(V1_DOWNBEATS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return sorted(float(t) for t in data["v1_downbeats"])


def _global_expected(v1_downbeats):
    intervals = [b - a for a, b in zip(v1_downbeats, v1_downbeats[1:])]
    valid = sorted(d for d in intervals if d > 0.05)
    n = len(valid)
    if n == 0:
        return None
    mid = n // 2
    return valid[mid] if n % 2 else (valid[mid - 1] + valid[mid]) / 2.0


def _local_expected(v1_downbeats, anchor_time, half_window_sec, fallback):
    lo, hi = anchor_time - half_window_sec, anchor_time + half_window_sec
    intervals = [
        b - a
        for a, b in zip(v1_downbeats, v1_downbeats[1:])
        if lo <= (a + b) / 2.0 <= hi and (b - a) > 0.05
    ]
    if len(intervals) < 3:
        return fallback
    intervals.sort()
    n = len(intervals)
    mid = n // 2
    return intervals[mid] if n % 2 else (intervals[mid - 1] + intervals[mid]) / 2.0


def _phase_consistency_score(candidate_time, committed, expected):
    residuals = []
    for previous in committed:
        delta = float(candidate_time) - float(previous)
        if delta <= 0:
            continue
        bars = max(1, round(delta / expected))
        residuals.append(abs(delta - bars * expected))
    if not residuals:
        return 0.0
    mean_residual = sum(residuals) / len(residuals)
    score = max(0.0, min(1.0, 1.0 - mean_residual / max(expected * 0.5, 1e-6)))
    return round(score, 6)


def simulate(trace, v1_downbeats, half_window_sec=None, reanchor_interval=None, weight_absolute=0.5):
    """half_window_sec=None reproduces the ORIGINAL frozen global `expected`
    (same as Pass 223's baseline). A positive half_window_sec substitutes a
    locally-windowed v1-grid median around the current probe window's
    anchor_time for that one tick's arbitration, falling back to the global
    value when the local window has too few v1 downbeats (e.g. right at
    song start/end)."""
    global_expected = _global_expected(v1_downbeats)
    committed = [float(t) for t in (trace[0].get("committed_before") or [])]
    for tick in trace:
        decision = tick.get("decision", {})
        arb = decision.get("candidate_arbitration", {}) or {}
        real_committed_time = tick.get("committed_after_last")

        if half_window_sec is None:
            expected = arb.get("expected_bar_duration_sec")
        else:
            anchor_time = (tick.get("window") or {}).get("anchor_time")
            expected = (
                _local_expected(v1_downbeats, float(anchor_time), half_window_sec, global_expected)
                if anchor_time is not None
                else global_expected
            )

        if not arb.get("triggered") or not expected or not committed:
            if real_committed_time is not None:
                committed.append(float(real_committed_time))
            continue

        cand_list = arb.get("candidates", [])
        if not cand_list:
            if real_committed_time is not None:
                committed.append(float(real_committed_time))
            continue

        commit_threshold = arb.get("commit_threshold")

        scored = []
        for entry in cand_list:
            cand = entry.get("candidate", {})
            t = cand.get("time")
            conf = cand.get("confidence", 0.0)
            if t is None:
                continue
            phase_score = _phase_consistency_score(t, committed, expected)
            if reanchor_interval:
                anchor_idx = max(0, (len(committed) - 1) // reanchor_interval * reanchor_interval)
                local_anchor = [committed[anchor_idx]]
                absolute_score = _phase_consistency_score(t, local_anchor, expected)
                combined = (1 - weight_absolute) * phase_score + weight_absolute * absolute_score
            else:
                combined = phase_score
            clears = conf >= commit_threshold if commit_threshold is not None else True
            scored.append((clears, combined, conf, -t, t))

        best = max(scored, key=lambda item: (item[0], item[1], item[2], item[3]))
        # Matches the Pass 223 fix: production only commits when
        # best["confidence"] >= threshold (module3_barstart_v2_bt.py:1088);
        # otherwise it leaves committed_bar_starts untouched this tick.
        if best[0]:
            committed.append(best[4])

    return sorted(set(round(t, 6) for t in committed))


def compare_to_golden(committed, golden_downbeats, label):
    print(f"=== {label}: total bars = {len(committed)} (golden = {len(golden_downbeats)}) ===")
    for name, start, end in SEGMENTS:
        seg = [b for b in committed if start <= b < end]
        g_seg = [g for g in golden_downbeats if start <= g < end]
        n = min(len(seg), len(g_seg))
        if n == 0:
            print(f"  {name:>10}: no overlap")
            continue
        residuals = [seg[i] - g_seg[i] for i in range(n)]
        mean_abs = sum(abs(r) for r in residuals) / n
        max_abs = max(abs(r) for r in residuals)
        print(f"  {name:>10}: v2={len(seg):>3} golden={len(g_seg):>3} mean_abs={mean_abs:.3f} max_abs={max_abs:.3f}")
    print()


def main():
    trace = _load_trace()
    v1_downbeats = _load_v1_downbeats()
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)["measure_map"]
    golden_downbeats = [float(m["start_time"]) for m in golden]

    baseline = simulate(trace, v1_downbeats, half_window_sec=None)
    compare_to_golden(baseline, golden_downbeats, "baseline (frozen global expected, = Pass223 baseline)")

    for half_window in (10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 60.0):
        result = simulate(trace, v1_downbeats, half_window_sec=half_window)
        compare_to_golden(result, golden_downbeats, f"local expected, +/-{half_window:.0f}s window, no anchor blend")

    # Retest the best periodic-reanchor interval from Pass 223 (8 bars) now
    # combined with a locally-adaptive expected, to see whether Pass 223's
    # failure was actually caused by the frozen-global `expected` divisor
    # rather than by anchor locality itself.


if __name__ == "__main__":
    raise SystemExit(main())
