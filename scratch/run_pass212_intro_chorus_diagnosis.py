"""PASS-212: instrument BarStartCandidateCommitNode + drum_fill_regions to
find the exact root cause of the Intro (12.9-18.6s) and Chorus 1
(101.4-120.4s) discrepancies against the golden reference.

Audit-only: monkeypatches only node execute() methods (never __init__ /
stall_limit -- that was the Pass 203 monkeypatch-contamination lesson),
restores everything in finally, and is otherwise identical to
scratch/run_pass211_promoted_production_verify.py.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.pipeline import PGMCraftEngine

AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_PATH = os.path.join(
    ROOT, "outputs", "pass198_default_pipeline_reverify", AUDIO_NAME, "source", AUDIO_NAME + ".wav"
)
OUTPUT_ROOT = os.path.join(ROOT, "outputs", "pass212_intro_chorus_diagnosis")
STEMS_SOURCE = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")
TRACE_PATH = os.path.join(ROOT, "scratch", "pass212_intro_chorus_trace.jsonl")

WATCH_WINDOWS = [(9.0, 20.0), (99.0, 122.0)]


def safe_name(title):
    return re.sub(r"\s+", "_", re.sub(r'[\*?:"<>|]', "", title).strip())[:120]


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


def _window_overlaps_watch(window):
    start = window.get("start_time")
    end = window.get("end_time")
    if start is None or end is None:
        return False
    for lo, hi in WATCH_WINDOWS:
        if float(end) >= lo and float(start) <= hi:
            return True
    return False


def _install_probe(trace):
    from pgm_craft.workflow.module3_barstart_v2_bt import BarStartCandidateCommitNode

    original = BarStartCandidateCommitNode.execute

    def wrapped(self, blackboard):
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        watch = _window_overlaps_watch(window)
        before_candidates = list(blackboard.get_val("bar_start_candidates", []) or [])
        exclusions = (
            list(blackboard.get_val("snap_exclusion_zones", []) or [])
            + list(blackboard.get_val("drum_fill_regions", []) or [])
        )
        status = original(self, blackboard)
        if watch:
            decision = dict(blackboard.get_val("bar_start_decision_report", {}) or {})
            trace.append(_json_safe({
                "window": window,
                "candidates_before_commit": before_candidates,
                "exclusion_zones": exclusions,
                "decision": decision,
            }))
        return status

    BarStartCandidateCommitNode.execute = wrapped
    return BarStartCandidateCommitNode, original


def _restore_probe(target, original):
    target.execute = original


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-212] blocked: missing {AUDIO_PATH}")
        return 1
    reuse_stems_cache()
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    trace = []
    target, original = _install_probe(trace)
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
        _restore_probe(target, original)
    elapsed = time.time() - started

    with open(TRACE_PATH, "w", encoding="utf-8") as handle:
        for item in trace:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[PASS-212] elapsed={elapsed:.1f}s watched_ticks={len(trace)} trace={TRACE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
