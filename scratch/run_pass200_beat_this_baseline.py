"""PASS-200: independent Beat This! baseline for World is Mine.

This script intentionally lives outside the production workflow. It uses the
official ``File2Beats`` API when the optional package and the requested audio
fixture are available, then compares the result with the existing measure map
at the known investigation points.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
AUDIO_PATH = (
    ROOT
    / "outputs"
    / "pass198_default_pipeline_reverify"
    / AUDIO_NAME
    / "source"
    / f"{AUDIO_NAME}.wav"
)
MEASURE_MAP_PATH = (
    ROOT
    / "outputs"
    / "pass198_default_pipeline_reverify"
    / AUDIO_NAME
    / "reports"
    / "measure_map.json"
)
REPORT_PATH = ROOT / "scratch" / "pass200_beat_this_comparison_report.json"

KNOWN_POINTS = [
    {"label": "weak_intro", "time": 8.041},
    {"label": "extra_beat_1", "time": 22.883},
    {"label": "extra_beat_2", "time": 35.300},
    {"label": "pass197_conflict_1", "time": 77.803},
    {"label": "pass197_conflict_2", "time": 80.020},
    {"label": "transition_1", "time": 93.802},
    {"label": "weak_transition", "time": 97.197},
    {"label": "known_point_108", "time": 108.652},
    {"label": "known_point_153", "time": 153.467},
    {"label": "clean_control_18_20", "start": 18.0, "end": 20.0},
]


def _load_measure_map() -> tuple[list[dict], dict]:
    if not MEASURE_MAP_PATH.exists():
        return [], {"status": "MISSING_MEASURE_MAP", "path": str(MEASURE_MAP_PATH)}
    with MEASURE_MAP_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    measure_map = payload.get("measure_map", payload if isinstance(payload, list) else [])
    from pgm_craft.golden_benchmark import compute_measure_map_stats

    return measure_map, {
        "status": "READY",
        "path": str(MEASURE_MAP_PATH),
        "stats": compute_measure_map_stats(measure_map),
    }


def _normalise_events(raw) -> tuple[list[float], list[float]]:
    """Return ``(beats, downbeats)`` for the package's supported output forms."""
    beats = []
    downbeats = []
    if raw is None:
        raw = []
    for item in raw:
        if isinstance(item, dict):
            time = item.get("time", item.get("timestamp"))
            label = item.get("beat", item.get("label", item.get("beat_num")))
        elif isinstance(item, (list, tuple, np.ndarray)):
            if len(item) == 0:
                continue
            time = item[0]
            label = item[1] if len(item) > 1 else None
        else:
            time, label = item, None
        try:
            time = float(time)
        except (TypeError, ValueError):
            continue
        beats.append(time)
        if str(label) in {"1", "1.0", "downbeat", "Downbeat"}:
            downbeats.append(time)
    return sorted(set(beats)), sorted(set(downbeats))


def _events_from_measure_map(measure_map: list[dict]) -> tuple[list[float], list[float]]:
    beats = []
    downbeats = []
    for measure in measure_map:
        start = measure.get("start_time")
        if start is not None:
            downbeats.append(float(start))
        for beat in measure.get("beats", []) or []:
            if beat.get("time") is not None:
                beats.append(float(beat["time"]))
    return sorted(set(beats)), sorted(set(downbeats))


def _near(events: list[float], target: float, tolerance: float = 3.0) -> list[dict]:
    return [
        {"time": round(float(event), 6), "delta_ms": round((float(event) - target) * 1000.0, 3)}
        for event in events
        if abs(float(event) - target) <= tolerance
    ]


def _build_measure_map(beats: list[float], downbeats: list[float]) -> list[dict]:
    """Convert Beat This! timestamps to the benchmark's minimal measure shape."""
    result = []
    for index, start in enumerate(downbeats):
        end = downbeats[index + 1] if index + 1 < len(downbeats) else start
        in_measure = [beat for beat in beats if start <= beat < end]
        result.append({
            "measure": index + 1,
            "start_time": start,
            "end_time": end,
            "beat_count": len(in_measure) or 4,
            "beats": [{"beat": (i % 4) + 1, "time": beat} for i, beat in enumerate(in_measure)],
            "is_variable_length": bool(in_measure and len(in_measure) != 4),
        })
    return result


def _run_beat_this() -> dict:
    if not AUDIO_PATH.exists():
        return {
            "status": "BLOCKED_MISSING_INPUT",
            "audio_path": str(AUDIO_PATH),
            "error": "PASS-200 source WAV is not present in this worktree.",
        }
    try:
        from beat_this.inference import File2Beats
    except Exception as exc:  # pragma: no cover - depends on optional environment
        return {
            "status": "BLOCKED_MISSING_DEPENDENCY",
            "audio_path": str(AUDIO_PATH),
            "error": f"Cannot import beat_this: {type(exc).__name__}: {exc}",
        }

    try:
        tracker = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
        beats_raw, downbeats_raw = tracker(str(AUDIO_PATH))
        beats, downbeats = _normalise_events(beats_raw)
        # The current official API returns a separate downbeat list, while
        # older/local builds may encode labels in the beat rows.
        downbeat_values, labelled_downbeats = _normalise_events(downbeats_raw)
        downbeats = downbeat_values or labelled_downbeats or _normalise_events(beats_raw)[1] or downbeats
        return {
            "status": "COMPLETED",
            "audio_path": str(AUDIO_PATH),
            "model": "final0",
            "device": "cpu",
            "beats": beats,
            "downbeats": downbeats,
        }
    except Exception as exc:  # pragma: no cover - depends on optional model/runtime
        return {
            "status": "INFERENCE_FAILED",
            "audio_path": str(AUDIO_PATH),
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    sys.path.insert(0, str(ROOT))
    measure_map, existing = _load_measure_map()
    existing_beats, existing_downbeats = _events_from_measure_map(measure_map)
    baseline = _run_beat_this()
    beat_this_beats = baseline.get("beats", [])
    beat_this_downbeats = baseline.get("downbeats", [])

    point_comparisons = []
    for point in KNOWN_POINTS:
        target = point.get("time")
        if target is None:
            target = (point["start"] + point["end"]) / 2.0
        point_comparisons.append({
            **point,
            "existing_pipeline": {
                "beats": _near(existing_beats, target),
                "downbeats": _near(existing_downbeats, target),
            },
            "beat_this": {
                "beats": _near(beat_this_beats, target),
                "downbeats": _near(beat_this_downbeats, target),
            },
        })

    from pgm_craft.golden_benchmark import GOLDEN_WORLD_IS_MINE_STATS, compute_measure_map_stats

    beat_this_stats = compute_measure_map_stats(
        _build_measure_map(beat_this_beats, beat_this_downbeats)
    ) if baseline.get("status") == "COMPLETED" else None
    report = {
        "pass": "PASS-200",
        "status": baseline["status"],
        "baseline": baseline,
        "known_point_comparisons": point_comparisons,
        "overall_comparison": {
            "golden": GOLDEN_WORLD_IS_MINE_STATS,
            "existing_pipeline": existing.get("stats"),
            "beat_this": beat_this_stats,
        },
        "interpretation": (
            "No conclusion: required source audio or optional runtime is unavailable."
            if baseline["status"] != "COMPLETED"
            else "Inspect each known point before drawing an aggregate conclusion."
        ),
        "reproducibility": {
            "script": str(Path(__file__)),
            "official_api": "beat_this.inference.File2Beats(checkpoint_path='final0', device='cpu', dbn=False)",
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[PASS-200] report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
