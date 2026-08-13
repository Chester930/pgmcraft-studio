"""PASS-212: instrument the 33-56s Verse 1 window where
BarGridContinuityRepairNode had to interpolate 7 bars at almost exactly
2x the expected bar length (~2.90s), meaning the loop only committed every
other real bar directly there. Captures full candidate lists + arbitration
for every tick overlapping this window to find why the "skipped" bar in
each pair never clears commit on its own.

Audit-only: monkeypatches only node execute() methods, restores in finally.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.pipeline import PGMCraftEngine

AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_PATH = os.path.join(
    ROOT, "outputs", "pass198_default_pipeline_reverify", AUDIO_NAME, "source", AUDIO_NAME + ".wav"
)
OUTPUT_ROOT = os.path.join(ROOT, "outputs", "pass212_verse1_skip_diagnosis")
STEMS_SOURCE = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")
TRACE_PATH = os.path.join(ROOT, "scratch", "pass212_verse1_skip_trace.jsonl")

WATCH_START = 30.0
WATCH_END = 56.0


def reuse_stems_cache():
    dst = os.path.join(OUTPUT_ROOT, AUDIO_NAME, "stems")
    if os.path.exists(dst) or not os.path.exists(STEMS_SOURCE):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.symlink(STEMS_SOURCE, dst, target_is_directory=True)
    except OSError:
        import subprocess
        subprocess.run(["cmd", "/c", "mklink", "/J", dst, STEMS_SOURCE], capture_output=True, text=True, check=False)


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        return value.tolist()
    except AttributeError:
        return repr(value)


def _window_in_range(window):
    start = window.get("start_time")
    end = window.get("end_time")
    if start is None or end is None:
        return False
    return float(end) >= WATCH_START and float(start) <= WATCH_END


def _install_probes(trace):
    from pgm_craft.workflow.module3_barstart_v2_bt import (
        BarStartCandidateCommitNode,
        DrumEvidenceBarSearchNode,
    )

    original_commit = BarStartCandidateCommitNode.execute
    original_drum = DrumEvidenceBarSearchNode.execute

    last_drum_report = {}
    last_kick_count = {}

    def wrapped_drum(self, blackboard):
        status = original_drum(self, blackboard)
        nonlocal last_drum_report
        last_drum_report = dict(blackboard.get_val("drum_bar_evidence_report", {}) or {})
        return status

    def wrapped_commit(self, blackboard):
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        watch = _window_in_range(window)
        committed_before = list(blackboard.get_val("committed_bar_starts", []) or [])
        before_candidates = list(blackboard.get_val("bar_start_candidates", []) or [])
        kick_anchors = list(blackboard.get_val("kick_anchors", []) or [])
        kick_in_window = [
            t for t in kick_anchors
            if window.get("start_time") is not None
            and float(window["start_time"]) <= float(t) <= float(window.get("end_time", window["start_time"]))
        ]
        status = original_commit(self, blackboard)
        if watch:
            decision = dict(blackboard.get_val("bar_start_decision_report", {}) or {})
            committed_after = list(blackboard.get_val("committed_bar_starts", []) or [])
            trace.append(_json_safe({
                "window": window,
                "committed_before_last2": committed_before[-2:],
                "kick_anchors_in_window": kick_in_window,
                "drum_evidence_report": last_drum_report,
                "candidates_before_commit": before_candidates,
                "decision": decision,
                "committed_after_last": committed_after[-1] if committed_after else None,
            }))
        return status

    BarStartCandidateCommitNode.execute = wrapped_commit
    DrumEvidenceBarSearchNode.execute = wrapped_drum
    return (BarStartCandidateCommitNode, original_commit), (DrumEvidenceBarSearchNode, original_drum)


def _restore_probes(patches):
    for target, original in patches:
        target.execute = original


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-212-v1skip] blocked: missing {AUDIO_PATH}")
        return 1
    reuse_stems_cache()
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    trace = []
    patches = _install_probes(trace)
    started = time.time()
    try:
        PGMCraftEngine(enable_stem_separation=True).run(
            AUDIO_PATH,
            output_dir=OUTPUT_ROOT,
            enable_stem=True,
            target_stage="module3",
            user_meter_selection="4/4",
            allow_temporary_bar_delta=0,
        )
    finally:
        _restore_probes(patches)
    elapsed = time.time() - started

    with open(TRACE_PATH, "w", encoding="utf-8") as handle:
        for item in trace:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[PASS-212-v1skip] elapsed={elapsed:.1f}s watched_ticks={len(trace)} trace={TRACE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
