"""Offline Pass236 calibration using the already verified Pass233 direct DBN run."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pgm_craft.workflow.madmom_hybrid import (
    _detect_weak_spans,
    _run_madmom_dbn,
)


AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
AUDIO_PATH = ROOT / "outputs" / "pass198_default_pipeline_reverify" / AUDIO_NAME / "source" / f"{AUDIO_NAME}.wav"
GOLDEN_PATH = Path(r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\reports\measure_map.json")
LOCAL_GOLDEN_PATH = ROOT / "outputs" / "pass228_grounded_score_production_verify" / AUDIO_NAME / "reports" / "measure_map.json"
REPORT_PATH = ROOT / "outputs" / "pass233_direct_madmom" / AUDIO_NAME / "direct_madmom_report.json"


def load_golden():
    path = GOLDEN_PATH if GOLDEN_PATH.exists() else LOCAL_GOLDEN_PATH
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [float(item["start_time"]) for item in payload["measure_map"]]


def overlap(span, section):
    return span[0] < section[1] and span[1] > section[0]


def main():
    if not AUDIO_PATH.exists():
        raise SystemExit(f"missing audio: {AUDIO_PATH}")
    golden = load_golden()
    madmom_grid = _run_madmom_dbn(str(AUDIO_PATH), transition_lambda=500)
    madmom_downbeats = [float(row[0]) for row in madmom_grid if abs(float(row[1]) - 1.0) < 1e-6]
    counts = [17, 42, 42, 20]
    sections = {}
    cursor = 0
    for name, count in zip(("Intro", "Verse1", "Chorus1", "Outro"), counts):
        start = golden[cursor]
        end_index = min(cursor + count, len(golden) - 1)
        end = golden[end_index] if end_index > cursor else start
        sections[name] = (start, end)
        cursor += count

    print(f"audio={AUDIO_PATH}")
    print(f"madmom_downbeats={len(madmom_downbeats)} golden_downbeats={len(golden)}")
    print("sections=" + json.dumps(sections, ensure_ascii=False))
    print("candidate_results:")
    candidates = []
    for window in (3, 5, 7, 9):
        for threshold in (0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12):
            for minimum in (2, 3, 4):
                spans = _detect_weak_spans(
                    madmom_downbeats,
                    window_bars=window,
                    cv_threshold=threshold,
                    min_span_bars=minimum,
                )
                non_outro = [name for span in spans for name, section in sections.items() if name != "Outro" and overlap(span, section)]
                outro = any(overlap(span, sections["Outro"]) for span in spans)
                exact = bool(spans) and not non_outro and outro
                result = {
                    "window_bars": window,
                    "cv_threshold": threshold,
                    "min_span_bars": minimum,
                    "spans": [[round(a, 6), round(b, 6)] for a, b in spans],
                    "outro_overlap": outro,
                    "non_outro_overlap": sorted(set(non_outro)),
                    "exact_outro_only": exact,
                }
                candidates.append(result)
                if exact:
                    print(json.dumps(result, ensure_ascii=False))

    exact_candidates = [item for item in candidates if item["exact_outro_only"]]
    if not exact_candidates:
        raise SystemExit("no exact Outro-only calibration found")

    # Prefer the middle of the contiguous passing threshold band.  This keeps
    # the default away from either edge of the calibrated 0.03..0.05 band,
    # while preferring a parameter set whose neighboring threshold values also
    # pass the exact-Outro-only criterion.
    threshold_values = (0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12)
    exact_keys = {
        (item["window_bars"], item["min_span_bars"], item["cv_threshold"])
        for item in exact_candidates
    }

    def selection_score(item):
        window = item["window_bars"]
        minimum = item["min_span_bars"]
        threshold = item["cv_threshold"]
        threshold_index = threshold_values.index(threshold)
        neighboring_passes = sum(
            (window, minimum, threshold_values[index]) in exact_keys
            for index in range(max(0, threshold_index - 1), min(len(threshold_values), threshold_index + 2))
        )
        middle_band_margin = -abs(threshold - 0.04)
        return (neighboring_passes, middle_band_margin, -window, -minimum)

    selected = max(exact_candidates, key=selection_score)
    selected["selection_reason"] = (
        "Selected from exact_Outro_only candidates by preferring the candidate "
        "with the most passing neighboring threshold values, then the middle "
        "of the calibrated 0.03..0.05 band to retain threshold margin."
    )
    output = {
        "pass": "Pass236 offline calibration",
        "transition_lambda": 500,
        "madmom_downbeat_count": len(madmom_downbeats),
        "golden_downbeat_count": len(golden),
        "madmom_downbeats": madmom_downbeats,
        "sections": sections,
        "selected": selected,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "source_report": str(REPORT_PATH),
    }
    output_path = ROOT / "scratch" / "pass236_offline_calibration.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("selected=" + json.dumps(selected, ensure_ascii=False))
    print(f"wrote={output_path}")


if __name__ == "__main__":
    main()
