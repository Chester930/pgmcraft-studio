"""PASS-222: one-time full-song capture of every tick's complete candidate
list + arbitration report for World is Mine, so future arbitration-design
attempts (periodic/local re-anchoring, etc.) can be simulated OFFLINE
against real data instead of requiring a full pipeline re-run (~13-18 min)
for every design iteration.

This is the same instrumentation pattern as
scratch/run_pass216_verse1_tail_diagnosis.py /
scratch/run_pass217_chorus1_drift_diagnosis.py, just with the watch window
covering the entire song instead of one region.

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
OUTPUT_ROOT = os.path.join(ROOT, "outputs", "pass222_full_song_candidate_trace")
STEMS_SOURCE = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")
TRACE_PATH = os.path.join(ROOT, "scratch", "pass222_full_song_candidate_trace.jsonl")


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


def _install_probes(trace):
    from pgm_craft.workflow.module3_barstart_v2_bt import BarStartCandidateCommitNode

    original_commit = BarStartCandidateCommitNode.execute

    def wrapped_commit(self, blackboard):
        window = dict(blackboard.get_val("active_bar_probe_window", {}) or {})
        committed_before = list(blackboard.get_val("committed_bar_starts", []) or [])
        before_candidates = list(blackboard.get_val("bar_start_candidates", []) or [])
        status = original_commit(self, blackboard)
        decision = dict(blackboard.get_val("bar_start_decision_report", {}) or {})
        committed_after = list(blackboard.get_val("committed_bar_starts", []) or [])
        trace.append(_json_safe({
            "window": window,
            "committed_before": committed_before,
            "candidates_before_commit": before_candidates,
            "decision": decision,
            "committed_after_last": committed_after[-1] if committed_after else None,
        }))
        return status

    BarStartCandidateCommitNode.execute = wrapped_commit
    return (BarStartCandidateCommitNode, original_commit)


def _restore_probes(patch):
    target, original = patch
    target.execute = original


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-222] blocked: missing {AUDIO_PATH}")
        return 1
    reuse_stems_cache()
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    trace = []
    patch = _install_probes(trace)
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
        _restore_probes(patch)
    elapsed = time.time() - started

    with open(TRACE_PATH, "w", encoding="utf-8") as handle:
        for item in trace:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[PASS-222] elapsed={elapsed:.1f}s total_ticks={len(trace)} trace={TRACE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
