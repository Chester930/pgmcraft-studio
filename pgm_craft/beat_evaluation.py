"""
Reference-based beat/downbeat evaluation helpers.

The fallback metrics follow the common MIREX-style event matching window
used for beat and downbeat evaluation. If mir_eval is installed, its full
beat metric set is added as an optional section.
"""

from __future__ import annotations

import csv
import json
import math
import os
from typing import Any, Iterable, List, Sequence, Tuple

import numpy as np


DEFAULT_TOLERANCE_SECONDS = 0.07


def coerce_beat_array(beats: Any) -> np.ndarray:
    """Convert common beat representations to an Nx2 float array."""
    if beats is None:
        return np.empty((0, 2), dtype=float)

    arr = np.asarray(beats, dtype=float)
    if arr.size == 0:
        return np.empty((0, 2), dtype=float)

    if arr.ndim == 1:
        times = arr.astype(float)
        labels = (np.arange(len(times)) % 4) + 1
        return np.column_stack([times, labels.astype(float)])

    if arr.ndim == 2 and arr.shape[1] >= 2:
        return arr[:, :2].astype(float)

    if arr.ndim == 2 and arr.shape[1] == 1:
        times = arr[:, 0].astype(float)
        labels = (np.arange(len(times)) % 4) + 1
        return np.column_stack([times, labels.astype(float)])

    raise ValueError("beats must be a 1D time list or an Nx2 beat array")


def serialize_beats(beats: Any) -> List[List[float]]:
    """Return JSON-safe [[time_seconds, beat_number], ...] rows."""
    arr = coerce_beat_array(beats)
    rows: List[List[float]] = []
    for time_s, beat_no in arr:
        rows.append([round(float(time_s), 6), int(round(float(beat_no)))])
    return rows


def beat_times(beats: Any) -> np.ndarray:
    arr = coerce_beat_array(beats)
    return np.sort(arr[:, 0].astype(float)) if len(arr) else np.array([], dtype=float)


def downbeat_times(beats: Any) -> np.ndarray:
    arr = coerce_beat_array(beats)
    if len(arr) == 0:
        return np.array([], dtype=float)
    labels = np.rint(arr[:, 1]).astype(int)
    return np.sort(arr[labels == 1, 0].astype(float))


def load_beat_annotations(path: str, downbeats_only: bool = False) -> np.ndarray:
    """
    Load beat annotations from JSON, CSV, TSV, or whitespace text.

    Accepted rows:
    - time
    - time, beat_number
    - time<TAB>beat_number

    JSON may be a list of times, a list of [time, beat_number], or a dict
    containing one of: beats, refined_beats, downbeats, reference_beats.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            key_order = (
                ("downbeats", "reference_downbeats") if downbeats_only else ()
            ) + ("refined_beats", "beats", "reference_beats")
            for key in key_order:
                if key in data:
                    return _filter_loaded_rows(coerce_beat_array(data[key]), downbeats_only)
            raise ValueError(f"No beat annotation key found in JSON: {path}")
        return _filter_loaded_rows(coerce_beat_array(data), downbeats_only)

    rows: List[Tuple[float, float]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t; ") if sample.strip() else csv.excel
        reader = csv.reader(f, dialect)
        for raw_row in reader:
            parsed = _parse_annotation_row(raw_row)
            if parsed is not None:
                rows.append(parsed)

    return _filter_loaded_rows(np.asarray(rows, dtype=float), downbeats_only)


def evaluate_beats(
    reference_beats: Any,
    estimated_beats: Any,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
    include_mir_eval: bool = True,
) -> dict:
    """Evaluate estimated beat times against reference beat times."""
    return _evaluate_events(
        reference_times=beat_times(reference_beats),
        estimated_times=beat_times(estimated_beats),
        tolerance_seconds=tolerance_seconds,
        include_mir_eval=include_mir_eval,
        mir_eval_task="beat",
    )


def evaluate_downbeats(
    reference_beats: Any,
    estimated_beats: Any,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
) -> dict:
    """Evaluate downbeat positions. Uses labels == 1 when labels exist."""
    return _evaluate_events(
        reference_times=downbeat_times(reference_beats),
        estimated_times=downbeat_times(estimated_beats),
        tolerance_seconds=tolerance_seconds,
        include_mir_eval=False,
        mir_eval_task="downbeat",
    )


def evaluate_report_with_references(
    report: dict,
    reference_beats_path: str | None = None,
    reference_downbeats_path: str | None = None,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
) -> dict:
    """Evaluate a pipeline report against optional beat/downbeat annotation files."""
    estimated = report.get("refined_beats") or report.get("beats") or []
    results = {
        "tolerance_seconds": float(tolerance_seconds),
        "estimated_total_beats": len(coerce_beat_array(estimated)),
    }

    if reference_beats_path:
        reference = load_beat_annotations(reference_beats_path)
        results["beats"] = evaluate_beats(reference, estimated, tolerance_seconds)
        results["reference_beats_path"] = reference_beats_path

    if reference_downbeats_path:
        reference = load_beat_annotations(reference_downbeats_path, downbeats_only=True)
        results["downbeats"] = evaluate_downbeats(reference, estimated, tolerance_seconds)
        results["reference_downbeats_path"] = reference_downbeats_path

    return results


def write_evaluation_report(evaluation: dict, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "beat_evaluation.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=2)
    return path


def _parse_annotation_row(row: Sequence[str]) -> Tuple[float, float] | None:
    cells = []
    for item in row:
        cells.extend(str(item).replace(",", " ").replace(";", " ").split())

    numeric: List[float] = []
    for cell in cells:
        try:
            numeric.append(float(cell))
        except ValueError:
            continue

    if not numeric:
        return None

    time_s = numeric[0]
    beat_no = numeric[1] if len(numeric) > 1 and math.isfinite(numeric[1]) else 1.0
    if not math.isfinite(time_s):
        return None
    return float(time_s), float(beat_no)


def _filter_loaded_rows(rows: np.ndarray, downbeats_only: bool) -> np.ndarray:
    arr = coerce_beat_array(rows)
    if downbeats_only and len(arr):
        labels = np.rint(arr[:, 1]).astype(int)
        arr = arr[labels == 1]
    return arr


def _evaluate_events(
    reference_times: Iterable[float],
    estimated_times: Iterable[float],
    tolerance_seconds: float,
    include_mir_eval: bool,
    mir_eval_task: str,
) -> dict:
    ref = _clean_times(reference_times)
    est = _clean_times(estimated_times)
    matches = _match_events(ref, est, tolerance_seconds)
    matched_errors = np.asarray([est[j] - ref[i] for i, j in matches], dtype=float)
    abs_errors_ms = np.abs(matched_errors) * 1000.0

    precision = len(matches) / len(est) if len(est) else 0.0
    recall = len(matches) / len(ref) if len(ref) else 0.0
    f_measure = (2.0 * precision * recall / (precision + recall)) if precision + recall else 0.0

    result = {
        "reference_count": int(len(ref)),
        "estimated_count": int(len(est)),
        "matched_count": int(len(matches)),
        "tolerance_seconds": float(tolerance_seconds),
        "precision": round(float(precision), 6),
        "recall": round(float(recall), 6),
        "f_measure": round(float(f_measure), 6),
        "mean_abs_error_ms": _rounded_stat(abs_errors_ms, np.mean),
        "median_abs_error_ms": _rounded_stat(abs_errors_ms, np.median),
        "p95_abs_error_ms": _rounded_stat(abs_errors_ms, lambda x: np.percentile(x, 95)),
        "mean_signed_error_ms": _rounded_stat(matched_errors * 1000.0, np.mean),
    }

    if include_mir_eval and mir_eval_task == "beat":
        mir_scores = _try_mir_eval(ref, est)
        if mir_scores is not None:
            result["mir_eval"] = mir_scores

    return result


def _clean_times(times: Iterable[float]) -> np.ndarray:
    arr = np.asarray(list(times), dtype=float)
    arr = arr[np.isfinite(arr)]
    arr = arr[arr >= 0.0]
    return np.sort(arr)


def _match_events(reference: np.ndarray, estimated: np.ndarray, tolerance_seconds: float) -> List[Tuple[int, int]]:
    candidates: List[Tuple[float, int, int]] = []
    for ref_idx, ref_time in enumerate(reference):
        start = np.searchsorted(estimated, ref_time - tolerance_seconds, side="left")
        end = np.searchsorted(estimated, ref_time + tolerance_seconds, side="right")
        for est_idx in range(start, end):
            candidates.append((abs(float(estimated[est_idx] - ref_time)), ref_idx, est_idx))

    matched_ref = set()
    matched_est = set()
    matches: List[Tuple[int, int]] = []
    for _, ref_idx, est_idx in sorted(candidates):
        if ref_idx in matched_ref or est_idx in matched_est:
            continue
        matched_ref.add(ref_idx)
        matched_est.add(est_idx)
        matches.append((ref_idx, est_idx))
    return matches


def _rounded_stat(values: np.ndarray, fn) -> float | None:
    if len(values) == 0:
        return None
    return round(float(fn(values)), 3)


def _try_mir_eval(reference: np.ndarray, estimated: np.ndarray) -> dict | None:
    try:
        import mir_eval.beat  # type: ignore
    except Exception:
        return None

    try:
        scores = mir_eval.beat.evaluate(reference, estimated)
    except Exception:
        return None

    return {key: round(float(value), 6) for key, value in scores.items()}
