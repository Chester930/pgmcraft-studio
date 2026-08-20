"""PASS-235 offline replay of the madmom arbitration bypass.

Replays a captured candidate/arbitration trace twice: with the production
phase-only key and with independent madmom support inserted between the
threshold gate and phase score.  The trace is intentionally treated as the
candidate set from the real run; this isolates the arbitration change before
spending time on a new production pipeline run.
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TRACE = os.path.join(ROOT, "scratch", "pass235_full_song_madmom_trace.jsonl")
FALLBACK_TRACE = os.path.join(ROOT, "scratch", "pass234_chorus1_trace.jsonl")
GOLDEN_CANDIDATES = [
    os.path.join(ROOT, "outputs", "pass228_grounded_score_production_verify", "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】", "reports", "measure_map.json"),
    r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json",
]

SEGMENTS = [
    ("Intro", 0.0, 25.813243),
    ("Verse1", 25.813243, 86.907256),
    ("Chorus1", 86.907256, 147.977778),
    ("Outro", 147.977778, float("inf")),
]


def _load_trace(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _phase_consistency_score(candidate_time, committed, expected):
    residuals = []
    for previous in committed:
        delta = float(candidate_time) - float(previous)
        if delta <= 0:
            continue
        bars = max(1, int(round(delta / expected)))
        residuals.append(abs(delta - bars * expected))
    if not residuals:
        return 0.0
    mean_residual = sum(residuals) / len(residuals)
    return round(max(0.0, min(1.0, 1.0 - mean_residual / max(expected * 0.5, 1e-6))), 6)


def _has_independent_model_support(item):
    evidence = set(item.get("candidate", {}).get("evidence_sources", []) or [])
    return bool(evidence & {"madmom_dbn", "madmom_dbn_support"})


def replay(trace, support_mode="none"):
    committed = [float(t) for t in (trace[0].get("committed_before") or [])]
    decisions = []
    for tick in trace:
        decision = tick.get("decision", {}) or {}
        arbitration = decision.get("candidate_arbitration", {}) or {}
        real_committed = tick.get("committed_after_last")
        expected = arbitration.get("expected_bar_duration_sec")
        if not arbitration.get("triggered") or not expected or not committed:
            if real_committed is not None:
                committed.append(float(real_committed))
            continue

        threshold = arbitration.get("commit_threshold")
        scored = []
        for item in arbitration.get("candidates", []) or []:
            candidate = item.get("candidate", {}) or {}
            time_sec = candidate.get("time")
            if time_sec is None:
                continue
            phase = _phase_consistency_score(time_sec, committed, expected)
            clears = (
                float(candidate.get("confidence", 0.0)) >= float(threshold)
                if threshold is not None else True
            )
            supported = _has_independent_model_support(item)
            scored.append({
                "candidate": candidate,
                "clears": clears,
                "supported": supported,
                "phase": phase,
            })
        if not scored:
            if real_committed is not None:
                committed.append(float(real_committed))
            continue

        non_madmom_phases = [item["phase"] for item in scored if not item["supported"]]
        for item in scored:
            if support_mode == "none":
                item["supported"] = False
            elif support_mode == "direct":
                evidence = set(item["candidate"].get("evidence_sources", []) or [])
                item["supported"] = "madmom_dbn" in evidence
            elif support_mode.startswith("phase_gap:"):
                gap = float(support_mode.split(":", 1)[1])
                max_non_madmom = max(non_madmom_phases, default=item["phase"])
                item["supported"] = item["supported"] and (
                    max_non_madmom - item["phase"] >= gap
                )

        best = max(
            scored,
            key=lambda item: (
                item["clears"],
                item["supported"],
                item["phase"],
                float(item["candidate"].get("confidence", 0.0)),
                -float(item["candidate"]["time"]),
            ),
        )
        if best["clears"]:
            committed.append(float(best["candidate"]["time"]))
        decisions.append({
            "window_start": (tick.get("window") or {}).get("start_time"),
            "winner_time": best["candidate"].get("time"),
            "winner_supported": best["supported"],
        })
    return sorted(set(round(t, 6) for t in committed)), decisions


def _load_golden():
    for path in GOLDEN_CANDIDATES:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                return [float(item["start_time"]) for item in json.load(handle)["measure_map"]]
    return []


def _metrics(sequence, golden):
    metrics = {}
    for name, start, end in SEGMENTS:
        values = [t for t in sequence if start <= t < end]
        nearest = [min((abs(t - g) for g in golden), default=float("inf")) for t in values]
        metrics[name] = {
            "count": len(values),
            "within_50ms": sum(delta <= 0.05 for delta in nearest),
            "mean_nearest_abs_sec": round(sum(nearest) / len(nearest), 6) if nearest else None,
        }
    return metrics


def _real_raw_sequence(trace):
    committed = [float(t) for t in (trace[0].get("committed_before") or [])]
    for tick in trace:
        committed_time = tick.get("committed_after_last")
        if committed_time is not None:
            committed.append(float(committed_time))
    return sorted(set(round(t, 6) for t in committed))


def main():
    trace_path = sys.argv[1] if len(sys.argv) > 1 else (
        DEFAULT_TRACE if os.path.exists(DEFAULT_TRACE) else FALLBACK_TRACE
    )
    trace = _load_trace(trace_path)
    baseline, _ = replay(trace, support_mode="none")
    bypass, decisions = replay(trace, support_mode="all")
    real_raw = _real_raw_sequence(trace)
    baseline_mismatches = [
        (index, baseline[index] if index < len(baseline) else None,
         real_raw[index] if index < len(real_raw) else None)
        for index in range(max(len(baseline), len(real_raw)))
        if (baseline[index] if index < len(baseline) else None)
        != (real_raw[index] if index < len(real_raw) else None)
    ]
    golden = _load_golden()
    changed = [
        {"index": i, "baseline": baseline[i] if i < len(baseline) else None,
         "bypass": bypass[i] if i < len(bypass) else None}
        for i in range(max(len(baseline), len(bypass)))
        if (baseline[i] if i < len(baseline) else None) != (bypass[i] if i < len(bypass) else None)
    ]
    if len(sys.argv) > 2 and sys.argv[2] == "--sweep":
        variants = ["direct"] + [f"phase_gap:{gap}" for gap in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40)]
        sweep = []
        for mode in variants:
            result, _ = replay(trace, support_mode=mode)
            metrics = _metrics(result, golden)
            sweep.append({
                "mode": mode,
                "count": len(result),
                "changed_from_baseline": sum(
                    (baseline[i] if i < len(baseline) else None)
                    != (result[i] if i < len(result) else None)
                    for i in range(max(len(baseline), len(result)))
                ),
                "metrics": metrics,
            })
        print(json.dumps({"trace": trace_path, "baseline_metrics": _metrics(baseline, golden), "sweep": sweep}, ensure_ascii=False, indent=2))
        return

    print(json.dumps({
        "trace": trace_path,
        "tick_count": len(trace),
        "baseline_count": len(baseline),
        "real_raw_count": len(real_raw),
        "baseline_matches_real_raw": not baseline_mismatches,
        "baseline_mismatch_count": len(baseline_mismatches),
        "baseline_mismatch_first": baseline_mismatches[:3],
        "bypass_count": len(bypass),
        "changed_commit_count": len(changed),
        "changed_commits": changed,
        "baseline_metrics": _metrics(baseline, golden),
        "bypass_metrics": _metrics(bypass, golden),
        "madmom_supported_winners": sum(item["winner_supported"] for item in decisions),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
