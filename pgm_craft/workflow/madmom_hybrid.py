"""Pass 236: madmom-primary beat grid with opt-in V2 weak-span splicing.

This module deliberately sits after the existing V2 merge node.  It does not
feed madmom candidates back into V2 arbitration, so a replacement cannot alter
the history used by the V2 phase-consistency logic.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np

from .nodes import BaseNode, Blackboard, NodeStatus


DEFAULT_WINDOW_BARS = 3
DEFAULT_CV_THRESHOLD = 0.04
DEFAULT_MIN_SPAN_BARS = 2
DEFAULT_TOLERANCE_SEC = 0.5
DEFAULT_DUPLICATE_TOLERANCE_SEC = 0.03
DEFAULT_TRANSITION_LAMBDA = 500


def _as_time_list(values: Any) -> list[float]:
    """Extract sorted finite event times from scalar, row, or dict data."""
    if values is None:
        return []
    if isinstance(values, dict):
        if "time" in values:
            values = [values]
        else:
            values = values.get("beats", values.get("downbeats", []))

    try:
        array = np.asarray(values, dtype=object)
    except (TypeError, ValueError):
        return []

    if array.size == 0:
        return []
    if array.ndim == 0:
        raw_items: Iterable[Any] = [array.item()]
    elif array.ndim == 1:
        raw_items = array.tolist()
    else:
        raw_items = array.tolist()

    times: list[float] = []
    for item in raw_items:
        try:
            if isinstance(item, dict):
                item = item.get("time")
            elif isinstance(item, (list, tuple, np.ndarray)):
                item = item[0] if len(item) else None
            if item is None:
                continue
            value = float(item)
            if math.isfinite(value):
                times.append(value)
        except (TypeError, ValueError, IndexError):
            continue
    return sorted(times)


def _as_grid(values: Any) -> np.ndarray:
    """Normalize a beat grid to an ``N x 2`` [time, beat-position] array."""
    if values is None:
        return np.empty((0, 2), dtype=float)
    if isinstance(values, dict):
        values = values.get("beats", values.get("grid", []))
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return np.empty((0, 2), dtype=float)
    if array.size == 0:
        return np.empty((0, 2), dtype=float)
    if array.ndim == 1:
        if array.size < 2:
            return np.column_stack((array, np.ones(array.shape[0], dtype=float)))
        array = array.reshape((-1, 2))
    if array.ndim != 2:
        return np.empty((0, 2), dtype=float)
    if array.shape[1] == 1:
        array = np.column_stack((array[:, 0], np.ones(array.shape[0], dtype=float)))
    return array[:, :2]


def _downbeat_times(grid: Any) -> list[float]:
    """Return position-1 rows, with a time-only fallback for synthetic data."""
    array = _as_grid(grid)
    if not len(array):
        return []
    downbeats = array[np.isclose(array[:, 1], 1.0)]
    if len(downbeats):
        return _as_time_list(downbeats[:, 0])
    return _as_time_list(array[:, 0])


def _detect_weak_spans(
    madmom_downbeats: Sequence[Any],
    window_bars: int = DEFAULT_WINDOW_BARS,
    cv_threshold: float = DEFAULT_CV_THRESHOLD,
    min_span_bars: int = DEFAULT_MIN_SPAN_BARS,
) -> list[tuple[float, float]]:
    """Detect contiguous areas whose local inter-bar CV is above the threshold.

    The unit of measurement is the inter-downbeat interval, not onset density.
    ``window_bars`` is the radius around each interval, and a returned span is
    bounded by the downbeats at the beginning and end of the flagged intervals.
    """
    times = _as_time_list(madmom_downbeats)
    if len(times) < 3:
        return []
    intervals = np.diff(np.asarray(times, dtype=float))
    intervals = intervals[np.isfinite(intervals) & (intervals > 0)]
    if len(intervals) != len(times) - 1:
        return []

    radius = max(1, int(window_bars))
    minimum = max(1, int(min_span_bars))
    threshold = float(cv_threshold)
    flagged = np.zeros(len(intervals), dtype=bool)
    for index in range(len(intervals)):
        start = max(0, index - radius)
        stop = min(len(intervals), index + radius + 1)
        local = intervals[start:stop]
        mean = float(np.mean(local)) if len(local) else 0.0
        cv = float(np.std(local) / mean) if mean > 0 else 0.0
        flagged[index] = cv >= threshold

    spans: list[tuple[float, float]] = []
    index = 0
    while index < len(flagged):
        if not flagged[index]:
            index += 1
            continue
        start = index
        while index + 1 < len(flagged) and flagged[index + 1]:
            index += 1
        end = index
        if end - start + 1 >= minimum:
            spans.append((times[start], times[end + 1]))
        index += 1

    # Adjacent flagged runs are merged when their boundaries touch.  This also
    # keeps the report stable if a single interval falls just below threshold.
    merged: list[tuple[float, float]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((float(start), float(end)))
    return merged


def _boundary_intervals(times: Sequence[float], start: float, end: float) -> dict[str, float | None]:
    before = [value for value in times if value < start]
    after = [value for value in times if value > end]
    return {
        "left_boundary_interval_sec": round(start - before[-1], 6) if before else None,
        "right_boundary_interval_sec": round(after[0] - end, 6) if after else None,
    }


def _splice_weak_spans_with_fallback(
    madmom_downbeats: Sequence[Any],
    fallback_downbeats: Sequence[Any],
    weak_spans: Sequence[tuple[float, float]],
    tolerance_sec: float = DEFAULT_TOLERANCE_SEC,
    duplicate_tolerance_sec: float = DEFAULT_DUPLICATE_TOLERANCE_SEC,
) -> tuple[list[float], dict[str, Any]]:
    """Replace only weak-span downbeats and return a transparent splice report."""
    madmom = _as_time_list(madmom_downbeats)
    fallback = _as_time_list(fallback_downbeats)
    spans_report: list[dict[str, Any]] = []
    removed: set[float] = set()
    inserted: list[float] = []

    for raw_start, raw_end in weak_spans:
        start, end = sorted((float(raw_start), float(raw_end)))
        in_fallback = [
            value for value in fallback
            if start - tolerance_sec <= value <= end + tolerance_sec
        ]
        removed_in_span = [value for value in madmom if start <= value <= end]
        entry: dict[str, Any] = {
            "start_time": round(start, 6),
            "end_time": round(end, 6),
            "madmom_removed_count": 0,
            "madmom_removed_downbeats": [],
            "fallback_inserted_count": 0,
            "fallback_inserted_downbeats": [],
            "inserted_downbeats": [],
            "evidence_sources": [],
        }
        if in_fallback:
            removed.update(removed_in_span)
            inserted.extend(in_fallback)
            entry["madmom_removed_count"] = len(removed_in_span)
            entry["madmom_removed_downbeats"] = [round(value, 6) for value in removed_in_span]
            entry["fallback_inserted_count"] = len(in_fallback)
            entry["fallback_inserted_downbeats"] = [round(value, 6) for value in in_fallback]
            entry["inserted_downbeats"] = [
                {"time": round(value, 6), "evidence_sources": ["v2_fallback_splice"]}
                for value in in_fallback
            ]
            entry["evidence_sources"] = ["v2_fallback_splice"]
            entry.update(_boundary_intervals(sorted(set(madmom + in_fallback)), start, end))
        spans_report.append(entry)

    combined = [value for value in madmom if value not in removed] + inserted
    combined.sort()
    deduped: list[float] = []
    for value in combined:
        if deduped and abs(value - deduped[-1]) <= duplicate_tolerance_sec:
            continue
        deduped.append(float(value))

    if not weak_spans:
        status = "NO_WEAK_SPANS"
    elif inserted:
        status = "APPLIED"
    else:
        status = "FALLBACK_UNAVAILABLE"
    report = {
        "status": status,
        "weak_span_count": len(weak_spans),
        "replaced_spans": spans_report,
        "tolerance_sec": float(tolerance_sec),
        "duplicate_tolerance_sec": float(duplicate_tolerance_sec),
    }
    return deduped, report


def _run_madmom_dbn(audio_path: str, transition_lambda: int = DEFAULT_TRANSITION_LAMBDA) -> np.ndarray:
    """Run the Pass233 direct madmom DBN configuration."""
    from madmom.features.downbeats import (
        DBNDownBeatTrackingProcessor,
        RNNDownBeatProcessor,
    )

    activations = RNNDownBeatProcessor()(audio_path)
    tracker = DBNDownBeatTrackingProcessor(
        beats_per_bar=[4],
        fps=100,
        transition_lambda=transition_lambda,
    )
    return _as_grid(tracker(activations))


def _splice_grid(
    madmom_grid: Any,
    fallback_grid: Any,
    weak_spans: Sequence[tuple[float, float]],
    tolerance_sec: float,
    duplicate_tolerance_sec: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply scalar span decisions to complete beat rows, preserving bar grids."""
    madmom = _as_grid(madmom_grid)
    fallback = _as_grid(fallback_grid)
    scalar_madmom = _downbeat_times(madmom)
    scalar_fallback = _downbeat_times(fallback)
    _, report = _splice_weak_spans_with_fallback(
        scalar_madmom,
        scalar_fallback,
        weak_spans,
        tolerance_sec=tolerance_sec,
        duplicate_tolerance_sec=duplicate_tolerance_sec,
    )

    if report["status"] != "APPLIED":
        return madmom.copy(), report

    rows: list[tuple[float, float]] = []
    for row in madmom:
        time = float(row[0])
        if any(start <= time <= end for start, end in weak_spans):
            continue
        rows.append((time, float(row[1])))
    for row in fallback:
        time = float(row[0])
        if any(start - tolerance_sec <= time <= end + tolerance_sec for start, end in weak_spans):
            rows.append((time, float(row[1])))
    rows.sort(key=lambda item: item[0])
    merged: list[tuple[float, float]] = []
    for row in rows:
        if merged and abs(row[0] - merged[-1][0]) <= duplicate_tolerance_sec:
            # Fallback rows are appended after madmom rows, so they win ties.
            if row[0] not in {item[0] for item in merged}:
                merged[-1] = row
            continue
        merged.append(row)
    return np.asarray(merged, dtype=float).reshape((-1, 2)), report


class MadmomPrimarySegmentSpliceNode(BaseNode):
    """Opt-in Pass236 post-processing node, placed after V2 merge."""

    optional_keys = [
        "audio_path",
        "target_analysis_path",
        "denoised_wav_path",
        "madmom_hybrid_audio_path",
        "trim_offset_sec",
        "raw_wav_path",
        "barstart_v2_grid_beats",
        "refined_beats",
        "beats",
        "madmom_hybrid_approved",
        "madmom_hybrid_window_bars",
        "madmom_hybrid_cv_threshold",
        "madmom_hybrid_min_span_bars",
        "madmom_hybrid_tolerance_sec",
        "madmom_hybrid_transition_lambda",
    ]
    output_keys = ["madmom_hybrid_report", "madmom_hybrid_downbeats"]

    def __init__(self):
        super().__init__("MadmomPrimarySegmentSpliceNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        approved = bool(blackboard.get_val("madmom_hybrid_approved", False))
        if not approved:
            blackboard.set_val(
                "madmom_hybrid_report",
                {
                    "status": "DISABLED_OPT_IN_REQUIRED",
                    "approved": False,
                    "primary_source": "existing_pipeline_output",
                    "weak_span_count": 0,
                    "replaced_spans": [],
                },
            )
            return NodeStatus.SUCCESS

        # Manual override remains highest priority; normal analysis follows
        # the project-wide target_analysis_path convention, with denoised and
        # legacy audio_path fallbacks for older callers.
        audio_path = (
            blackboard.get_val("madmom_hybrid_audio_path")
            or blackboard.get_val("target_analysis_path")
            or blackboard.get_val("denoised_wav_path")
            or blackboard.get_val("audio_path")
        )
        if not audio_path:
            blackboard.set_val(
                "madmom_hybrid_report",
                {
                    "status": "SKIPPED_NO_AUDIO",
                    "approved": True,
                    "primary_source": "existing_pipeline_output",
                    "weak_span_count": 0,
                    "replaced_spans": [],
                },
            )
            return NodeStatus.SUCCESS

        try:
            madmom_grid = _run_madmom_dbn(
                audio_path,
                transition_lambda=int(
                    blackboard.get_val("madmom_hybrid_transition_lambda", DEFAULT_TRANSITION_LAMBDA)
                ),
            )
        except Exception as exc:
            blackboard.set_val(
                "madmom_hybrid_report",
                {
                    "status": "SKIPPED_MADMOM_ERROR",
                    "approved": True,
                    "primary_source": "existing_pipeline_output",
                    "error": str(exc),
                    "weak_span_count": 0,
                    "replaced_spans": [],
                },
            )
            return NodeStatus.SUCCESS

        trim_offset_sec = float(blackboard.get_val("trim_offset_sec", 0.0) or 0.0)
        if trim_offset_sec:
            madmom_grid = _as_grid(madmom_grid).copy()
            madmom_grid[:, 0] += trim_offset_sec

        fallback_grid = blackboard.get_val("barstart_v2_grid_beats")
        if len(_as_grid(fallback_grid)) == 0:
            fallback_grid = blackboard.get_val("refined_beats")
        if len(_as_grid(fallback_grid)) == 0:
            fallback_grid = blackboard.get_val("beats")

        downbeats = _downbeat_times(madmom_grid)
        window_bars = int(blackboard.get_val("madmom_hybrid_window_bars", DEFAULT_WINDOW_BARS))
        cv_threshold = float(
            blackboard.get_val("madmom_hybrid_cv_threshold", DEFAULT_CV_THRESHOLD)
        )
        min_span_bars = int(
            blackboard.get_val("madmom_hybrid_min_span_bars", DEFAULT_MIN_SPAN_BARS)
        )
        tolerance_sec = float(
            blackboard.get_val("madmom_hybrid_tolerance_sec", DEFAULT_TOLERANCE_SEC)
        )
        duplicate_tolerance_sec = float(
            blackboard.get_val(
                "madmom_hybrid_duplicate_tolerance_sec",
                DEFAULT_DUPLICATE_TOLERANCE_SEC,
            )
        )
        weak_spans = _detect_weak_spans(
            downbeats,
            window_bars=window_bars,
            cv_threshold=cv_threshold,
            min_span_bars=min_span_bars,
        )
        final_grid, splice_report = _splice_grid(
            madmom_grid,
            fallback_grid,
            weak_spans,
            tolerance_sec=tolerance_sec,
            duplicate_tolerance_sec=duplicate_tolerance_sec,
        )
        blackboard.set_val("beats", final_grid)
        blackboard.set_val("refined_beats", final_grid)
        blackboard.set_val("madmom_hybrid_downbeats", _downbeat_times(final_grid))
        splice_report.update(
            {
                "approved": True,
                "primary_source": "madmom_dbn_direct",
                "fallback_source": "barstart_v2_grid_beats",
                "audio_path": str(audio_path),
                "trim_offset_sec": trim_offset_sec,
                "transition_lambda": int(
                    blackboard.get_val("madmom_hybrid_transition_lambda", DEFAULT_TRANSITION_LAMBDA)
                ),
                "window_bars": window_bars,
                "cv_threshold": cv_threshold,
                "min_span_bars": min_span_bars,
                "madmom_downbeat_count": len(downbeats),
                "final_beat_count": int(len(final_grid)),
                "evidence_sources": [
                    {
                        "source": "v2_fallback_splice",
                        "spans": [entry for entry in splice_report["replaced_spans"] if entry["fallback_inserted_count"]],
                    }
                ],
            }
        )
        blackboard.set_val("madmom_hybrid_report", splice_report)
        return NodeStatus.SUCCESS
