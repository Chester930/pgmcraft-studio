"""Pass 236: madmom-primary beat grid with opt-in V2 weak-span splicing.

This module deliberately sits after the existing V2 merge node.  It does not
feed madmom candidates back into V2 arbitration, so a replacement cannot alter
the history used by the V2 phase-consistency logic.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np

from .beat_tracking_bt import MicroTimingTransientSnapNode
from .nodes import BaseNode, Blackboard, NodeStatus


DEFAULT_WINDOW_BARS = 3
DEFAULT_CV_THRESHOLD = 0.04
DEFAULT_MIN_SPAN_BARS = 2
DEFAULT_TOLERANCE_SEC = 0.5
DEFAULT_DUPLICATE_TOLERANCE_SEC = 0.03
DEFAULT_TRANSITION_LAMBDA = 500

# Pass 241 found that BarStartCandidateCommitNode's committed_bar_starts
# (the fallback source here) is itself sometimes a mechanically rigid
# n*expected_bar_duration sequence rather than real acoustic tracking --
# reproduced identically (to <1ms) across independent pipeline runs, and
# affecting ~23% of this song's V2 grid overall. Real onset-derived bar
# intervals, even in a genuinely steady passage, always carry some natural
# jitter; a 5-interval sliding window over this song's actual V2 output
# shows a clean bimodal split -- essentially machine-epsilon range (<1e-5s)
# for the synthetic-looking stretches vs >=0.17s for everything else -- so
# this threshold sits with wide margin on both sides, not tuned to one case.
DEFAULT_FALLBACK_MIN_INTERVAL_RANGE_SEC = 0.01

# Pass 243 found (via independent kick/bass onset detection, not madmom's own
# output) that real percussive/bass evidence for this song thins out well
# before the point BarStartCandidateCommitNode's own unresolved-span tracking
# notices -- madmom's DBN keeps producing smoothly-drifting output even once
# real acoustic grounding is gone, so the existing CV-based weak-span
# detector (tuned to catch erratic wobble, not a smooth ungrounded drift)
# never flags it. Rather than inventing a new drift heuristic on madmom's own
# output (fragile, hard to calibrate without misfiring on real ritardandos
# elsewhere), this reuses kick_anchors/snare_anchors -- the same real onset
# arrays BarStartTempoSmoothingNode already trusts as ground truth for its
# own drum-protection check -- as a direct evidence test, and falls back to
# the same even-interpolation math as TailBarExtrapolationNode (Pass 211),
# just scoped to whatever's actually exported here (madmom-primary), not
# V2's own committed grid.
DEFAULT_TAIL_EVIDENCE_TOLERANCE_SEC = 0.1
DEFAULT_TAIL_MIN_GAP_BARS = 2
DEFAULT_TAIL_RECENT_INTERVAL_COUNT = 4


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


def _interval_range(values: Sequence[float]) -> float | None:
    """Max-min spread of consecutive intervals; None if fewer than 2 intervals."""
    ordered = sorted(float(value) for value in values)
    if len(ordered) < 3:
        return None
    intervals = [ordered[i + 1] - ordered[i] for i in range(len(ordered) - 1)]
    return max(intervals) - min(intervals)


def _splice_weak_spans_with_fallback(
    madmom_downbeats: Sequence[Any],
    fallback_downbeats: Sequence[Any],
    weak_spans: Sequence[tuple[float, float]],
    tolerance_sec: float = DEFAULT_TOLERANCE_SEC,
    duplicate_tolerance_sec: float = DEFAULT_DUPLICATE_TOLERANCE_SEC,
    min_fallback_interval_range_sec: float = DEFAULT_FALLBACK_MIN_INTERVAL_RANGE_SEC,
) -> tuple[list[float], dict[str, Any]]:
    """Replace only weak-span downbeats and return a transparent splice report.

    Pass241: before trusting the fallback source for a span, check whether its
    own bar intervals there are suspiciously rigid (near-zero spread) rather
    than real acoustic tracking. A fallback that's itself just a mechanical
    n*expected_bar_duration sequence is not a real second opinion -- splicing
    it in swaps one wrong answer for a different, differently-wrong one. When
    that happens, the span is left on the (still imperfect, but at least
    acoustically-derived) primary source instead.
    """
    madmom = _as_time_list(madmom_downbeats)
    fallback = _as_time_list(fallback_downbeats)
    spans_report: list[dict[str, Any]] = []
    removed: set[float] = set()
    inserted: list[float] = []
    any_rejected_rigid = False

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
            "fallback_interval_range_sec": None,
            "fallback_rejected_reason": None,
        }
        interval_range = _interval_range(in_fallback)
        entry["fallback_interval_range_sec"] = (
            round(interval_range, 6) if interval_range is not None else None
        )
        if (
            in_fallback
            and interval_range is not None
            and interval_range < min_fallback_interval_range_sec
        ):
            entry["fallback_rejected_reason"] = "rigid_interval_pattern"
            any_rejected_rigid = True
            in_fallback = []
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
    elif any_rejected_rigid:
        status = "FALLBACK_REJECTED_RIGID"
    else:
        status = "FALLBACK_UNAVAILABLE"
    report = {
        "status": status,
        "weak_span_count": len(weak_spans),
        "replaced_spans": spans_report,
        "tolerance_sec": float(tolerance_sec),
        "duplicate_tolerance_sec": float(duplicate_tolerance_sec),
        "min_fallback_interval_range_sec": float(min_fallback_interval_range_sec),
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
    min_fallback_interval_range_sec: float = DEFAULT_FALLBACK_MIN_INTERVAL_RANGE_SEC,
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
        min_fallback_interval_range_sec=min_fallback_interval_range_sec,
    )

    if report["status"] != "APPLIED":
        return madmom.copy(), report

    # Only spans that actually got a fallback insertion should have their
    # madmom rows dropped/replaced -- a span rejected for a rigid fallback
    # pattern (fallback_rejected_reason set) must keep its original madmom
    # rows untouched, even though other spans in the same call succeeded.
    applied_spans = [
        (entry["start_time"], entry["end_time"])
        for entry in report["replaced_spans"]
        if entry["fallback_inserted_count"]
    ]

    rows: list[tuple[float, float]] = []
    for row in madmom:
        time = float(row[0])
        if any(start <= time <= end for start, end in applied_spans):
            continue
        rows.append((time, float(row[1])))
    for row in fallback:
        time = float(row[0])
        if any(start - tolerance_sec <= time <= end + tolerance_sec for start, end in applied_spans):
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


def _tail_evidence_gap_anchor(
    downbeats: Sequence[float],
    kick_anchors: Sequence[float],
    snare_anchors: Sequence[float],
    tolerance_sec: float = DEFAULT_TAIL_EVIDENCE_TOLERANCE_SEC,
    min_gap_bars: int = DEFAULT_TAIL_MIN_GAP_BARS,
) -> tuple[int, float] | None:
    """Find the last downbeat with real kick/snare evidence nearby, if a
    trailing run of at least ``min_gap_bars`` downbeats after it has none.

    Returns (index_into_downbeats, anchor_time) for that last-evidenced
    downbeat, or None if there's no such trailing gap (including when the
    whole grid has no anchors to check against at all -- silence about a
    signal we don't have is not evidence of a gap).
    """
    ordered = sorted(float(v) for v in downbeats)
    if len(ordered) < min_gap_bars + 1:
        return None
    anchors = sorted(
        {round(float(v), 6) for v in list(kick_anchors or []) + list(snare_anchors or [])}
    )
    if not anchors:
        return None

    def _has_evidence(t: float) -> bool:
        return any(abs(t - a) <= tolerance_sec for a in anchors)

    index = len(ordered) - 1
    while index >= 0 and not _has_evidence(ordered[index]):
        index -= 1
    trailing_gap_count = len(ordered) - 1 - index
    if index < 0 or trailing_gap_count < min_gap_bars:
        return None
    return index, ordered[index]


def _extrapolate_tail_downbeats(
    anchor_time: float,
    duration_cap: float,
    recent_intervals: Sequence[float],
) -> list[float]:
    """Evenly divide [anchor_time, duration_cap] using the recent local bar
    duration -- the exact same math as TailBarExtrapolationNode (Pass 211),
    kept in sync deliberately: both exist to fill a genuine evidence void
    without inventing a fake precise position, just a plausible bar count."""
    valid = [v for v in recent_intervals if math.isfinite(v) and v > 0.05]
    if not valid:
        return []
    expected = float(np.median(valid))
    remaining = float(duration_cap) - float(anchor_time)
    if remaining <= expected * 0.5:
        return []
    count = max(1, int(round(remaining / expected)))
    step = remaining / count
    return [round(float(anchor_time + step * i), 6) for i in range(1, count + 1)]


def _apply_tail_evidence_gap(
    grid: np.ndarray,
    kick_anchors: Sequence[float],
    snare_anchors: Sequence[float],
    duration_cap: float | None,
    tolerance_sec: float = DEFAULT_TAIL_EVIDENCE_TOLERANCE_SEC,
    min_gap_bars: int = DEFAULT_TAIL_MIN_GAP_BARS,
    recent_interval_count: int = DEFAULT_TAIL_RECENT_INTERVAL_COUNT,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Replace a trailing run of evidence-free downbeats (and their beats)
    with an even interpolation anchored to the last real kick/snare hit."""
    report: dict[str, Any] = {
        "triggered": False,
        "reason": "NOOP",
        "anchor_time": None,
        "duration_cap_sec": duration_cap,
        "expected_bar_duration_sec": None,
        "extrapolated_bar_count": 0,
        "bars": [],
    }
    array = _as_grid(grid)
    if duration_cap is None or len(array) == 0:
        report["reason"] = "MISSING_DURATION_CAP_OR_GRID"
        return array, report

    downbeats = _downbeat_times(array)
    gap = _tail_evidence_gap_anchor(
        downbeats, kick_anchors, snare_anchors,
        tolerance_sec=tolerance_sec, min_gap_bars=min_gap_bars,
    )
    if gap is None:
        report["reason"] = "NO_TRAILING_EVIDENCE_GAP"
        return array, report

    anchor_index, anchor_time = gap
    report["anchor_time"] = round(anchor_time, 6)
    recent = downbeats[max(0, anchor_index - recent_interval_count):anchor_index + 1]
    recent_intervals = list(np.diff(np.asarray(recent, dtype=float))) if len(recent) > 1 else []
    extrapolated = _extrapolate_tail_downbeats(anchor_time, duration_cap, recent_intervals)
    if not extrapolated:
        report["reason"] = "TAIL_REMAINDER_WITHIN_HALF_BAR"
        return array, report

    expected = float(np.median(recent_intervals)) if recent_intervals else None
    step = (
        (float(duration_cap) - anchor_time) / len(extrapolated)
        if extrapolated else None
    )
    kept = [(float(row[0]), float(row[1])) for row in array if float(row[0]) <= anchor_time + 1e-6]
    new_rows: list[tuple[float, float]] = []
    for index, bar_start in enumerate(extrapolated):
        bar_end = extrapolated[index + 1] if index + 1 < len(extrapolated) else duration_cap
        quarter = (bar_end - bar_start) / 4.0
        for beat_position in range(4):
            new_rows.append((round(bar_start + quarter * beat_position, 6), float(beat_position + 1)))
    combined = sorted(kept + new_rows, key=lambda item: item[0])
    report.update({
        "triggered": True,
        "reason": "EXTRAPOLATED_FROM_TRAILING_EVIDENCE_GAP",
        "expected_bar_duration_sec": round(expected, 6) if expected else None,
        "extrapolated_bar_count": len(extrapolated),
        "step_sec": round(step, 6) if step else None,
        "bars": [
            {"time": t, "confidence": 0.0, "evidence_sources": ["tail_evidence_gap_extrapolation"]}
            for t in extrapolated
        ],
    })
    return np.asarray(combined, dtype=float).reshape((-1, 2)), report


def _audio_duration_cap(blackboard: Blackboard) -> float | None:
    """Same lookup as NoDrumPhaseCarryNode._audio_duration_cap -- duplicated
    locally rather than imported to keep this opt-in module decoupled from
    module3_barstart_v2_bt's internals."""
    try:
        explicit = float(blackboard.get_val("audio_duration_sec"))
        if explicit > 0:
            return explicit
    except (TypeError, ValueError):
        pass
    y = blackboard.get_val("y")
    sr = blackboard.get_val("sr")
    try:
        if y is not None and sr:
            length = y.shape[-1] if hasattr(y, "shape") else len(y)
            return float(length) / float(sr)
    except (TypeError, ValueError, AttributeError):
        pass
    return None


class MadmomPrimarySegmentSpliceNode(BaseNode):
    """Opt-in Pass236 post-processing node, placed after V2 merge."""

    optional_keys = [
        "audio_path",
        "denoised_wav_path",
        "madmom_hybrid_audio_path",
        "trim_offset_sec",
        "raw_wav_path",
        "barstart_v2_grid_beats",
        "refined_beats",
        "beats",
        "madmom_hybrid_approved",
        "madmom_hybrid_micro_timing_snap_enabled",
        "madmom_hybrid_window_bars",
        "madmom_hybrid_cv_threshold",
        "madmom_hybrid_min_span_bars",
        "madmom_hybrid_tolerance_sec",
        "madmom_hybrid_transition_lambda",
        "madmom_hybrid_min_fallback_interval_range_sec",
        "kick_anchors",
        "snare_anchors",
        "audio_duration_sec",
        "y",
        "sr",
        "madmom_hybrid_tail_evidence_tolerance_sec",
        "madmom_hybrid_tail_min_gap_bars",
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

        # Manual override remains highest priority. target_analysis_path is
        # deliberately NOT used here: by the time this node runs (after stem
        # separation), stem-specific nodes have repointed it at an isolated
        # stem (e.g. the drums stem) for their own onset/timing work. madmom's
        # RNNDownBeatProcessor was calibrated (Pass229-233) against the full
        # mix, so this node needs denoised_wav_path -- set once by
        # WriteNormalizedWAVNode and never reassigned afterward -- with
        # audio_path only as a last-resort fallback for older callers that
        # never ran the 3-tier quality pipeline.
        audio_path = (
            blackboard.get_val("madmom_hybrid_audio_path")
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
        min_fallback_interval_range_sec = float(
            blackboard.get_val(
                "madmom_hybrid_min_fallback_interval_range_sec",
                DEFAULT_FALLBACK_MIN_INTERVAL_RANGE_SEC,
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
            min_fallback_interval_range_sec=min_fallback_interval_range_sec,
        )

        # Pass 243: the CV-based weak-span detector above catches erratic
        # wobble, not a smooth ungrounded drift -- madmom's DBN keeps
        # producing plausible-looking output even once real percussive
        # evidence has actually run out near a song's end. Check directly
        # against real kick/snare onsets (already computed pipeline-wide,
        # not re-detected here) for a trailing run with no support at all,
        # and fill only that with an honest even interpolation instead of
        # trusting madmom's ungrounded guess.
        tail_report = _apply_tail_evidence_gap(
            final_grid,
            blackboard.get_val("kick_anchors", []),
            blackboard.get_val("snare_anchors", []),
            _audio_duration_cap(blackboard),
            tolerance_sec=float(
                blackboard.get_val(
                    "madmom_hybrid_tail_evidence_tolerance_sec",
                    DEFAULT_TAIL_EVIDENCE_TOLERANCE_SEC,
                )
            ),
            min_gap_bars=int(
                blackboard.get_val("madmom_hybrid_tail_min_gap_bars", DEFAULT_TAIL_MIN_GAP_BARS)
            ),
        )
        final_grid, tail_gap_report = tail_report
        blackboard.set_val("beats", final_grid)
        blackboard.set_val("refined_beats", final_grid)

        # Pass 246: reuse the already-proven legacy transient snap on the
        # completed madmom-hybrid grid.  This remains downstream of all
        # splice/tail decisions, so it cannot feed evidence back into V2
        # arbitration.  The explicit flag is independently disable-able for
        # A/B verification, while its omitted value follows hybrid approval.
        #
        # Pass 247: real-pipeline verification found the snap can pull an
        # already-correct downbeat toward a louder-but-wrong nearby
        # transient (1-2 downbeats per section moved from <50ms to 54-72ms
        # off golden), while showing no measurable benefit on intra-bar
        # (beat 2/3/4) accuracy in the exact zones Pass245 flagged.
        # Downbeats are already accurate -- Pass245's own finding was
        # specifically about intra-bar timing -- so only beat positions
        # 2/3/4 are allowed to accept the snap; downbeat rows always keep
        # their pre-snap (already-verified) position.
        micro_snap_enabled = bool(
            blackboard.get_val("madmom_hybrid_micro_timing_snap_enabled", approved)
        )
        micro_snap_report: dict[str, Any]
        if micro_snap_enabled:
            try:
                pre_snap_grid = _as_grid(final_grid).copy()
                MicroTimingTransientSnapNode(search_window_ms=35.0).execute(blackboard)
                snapped_grid = _as_grid(blackboard.get_val("refined_beats"))
                if len(snapped_grid) == len(pre_snap_grid) and len(pre_snap_grid):
                    merged_rows = [
                        pre_row if abs(float(pre_row[1]) - 1.0) < 1e-6 else post_row
                        for pre_row, post_row in zip(pre_snap_grid, snapped_grid)
                    ]
                    final_grid = np.asarray(merged_rows, dtype=float).reshape((-1, 2))
                else:
                    final_grid = pre_snap_grid
                blackboard.set_val("beats", final_grid)
                blackboard.set_val("refined_beats", final_grid)
                offsets = [
                    (float(post_row[0]) - float(pre_row[0])) * 1000.0
                    for pre_row, post_row in zip(pre_snap_grid, final_grid)
                    if abs(float(pre_row[1]) - 1.0) >= 1e-6
                    and abs(float(post_row[0]) - float(pre_row[0])) > 1e-9
                ]
                abs_offsets = [abs(value) for value in offsets]
                micro_snap_report = {
                    "status": "APPLIED",
                    "enabled": True,
                    "node": "MicroTimingTransientSnapNode",
                    "downbeats_excluded": True,
                    "snap_offsets_ms": offsets,
                    "snap_offset_count": len(offsets),
                    "nonzero_snap_count": sum(value > 1e-9 for value in abs_offsets),
                    "mean_abs_offset_ms": round(float(np.mean(abs_offsets)), 6)
                    if abs_offsets
                    else 0.0,
                    "max_abs_offset_ms": round(float(max(abs_offsets)), 6)
                    if abs_offsets
                    else 0.0,
                    "snap_skip_report": dict(
                        blackboard.get_val("snap_skip_report", {}) or {}
                    ),
                }
            except Exception as exc:
                # The hybrid output is still valid without this optional
                # refinement; retain it and make the failure visible.
                blackboard.set_val("beats", final_grid)
                blackboard.set_val("refined_beats", final_grid)
                micro_snap_report = {
                    "status": "ERROR",
                    "enabled": True,
                    "node": "MicroTimingTransientSnapNode",
                    "error": str(exc),
                    "snap_offsets_ms": [],
                    "snap_offset_count": 0,
                    "nonzero_snap_count": 0,
                    "mean_abs_offset_ms": 0.0,
                    "max_abs_offset_ms": 0.0,
                    "snap_skip_report": {},
                }
        else:
            micro_snap_report = {
                "status": "DISABLED_FLAG",
                "enabled": False,
                "node": "MicroTimingTransientSnapNode",
                "snap_offsets_ms": [],
                "snap_offset_count": 0,
                "nonzero_snap_count": 0,
                "mean_abs_offset_ms": 0.0,
                "max_abs_offset_ms": 0.0,
                "snap_skip_report": {},
            }

        blackboard.set_val("madmom_hybrid_downbeats", _downbeat_times(final_grid))
        evidence_sources = [
            {
                "source": "v2_fallback_splice",
                "spans": [entry for entry in splice_report["replaced_spans"] if entry["fallback_inserted_count"]],
            }
        ]
        if tail_gap_report["triggered"]:
            evidence_sources.append({"source": "tail_evidence_gap_extrapolation", "spans": tail_gap_report["bars"]})
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
                "micro_timing_snap_report": micro_snap_report,
                "tail_evidence_gap_report": tail_gap_report,
                "evidence_sources": evidence_sources,
            }
        )
        blackboard.set_val("madmom_hybrid_report", splice_report)
        return NodeStatus.SUCCESS
