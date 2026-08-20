"""PASS-234: diagnose why madmom's standalone-near-perfect Chorus1 result
(Pass 229: 42/42 within 50ms) degraded to only 3/42 within 50ms once
merged into BarStart V2's arbitration (Pass 232, reverted by Codex after
real production verify showed a 14.89-point score regression).

Instruments BarStartCandidateCommitNode.execute to capture the FULL
candidate list + arbitration decision at every tick in the Chorus1
window (86.907256s-147.977778s), so we can see exactly which candidate
won, whether a madmom-sourced/boosted candidate was even offered, and
why it lost if so.

This is a one-time diagnostic run reusing cached stems -- the two new
nodes (MadmomDBNEvidenceExtractNode, MadmomDBNCandidateAdapterNode) are
temporarily wired into module3_barstart_v2_bt.py / module3_bt.py for
this run only (matching Pass 232's task doc design) and will be
reverted via `git checkout --` after this diagnosis, per this project's
established practice of not leaving failed integration code in place.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_PATH = os.path.join(
    ROOT, "outputs", "pass198_default_pipeline_reverify", AUDIO_NAME, "source", AUDIO_NAME + ".wav"
)
OUTPUT_ROOT = os.path.join(ROOT, "outputs", "pass234_madmom_chorus1_diagnosis")
STEMS_SOURCE = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")
TRACE_PATH = os.path.join(ROOT, "scratch", "pass235_full_song_madmom_trace.jsonl")

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
        w_start = window.get("start_time")
        committed_before = list(blackboard.get_val("committed_bar_starts", []) or [])
        candidates_before = list(blackboard.get_val("bar_start_candidates", []) or [])
        madmom_report = dict(blackboard.get_val("madmom_candidate_report", {}) or {})
        status = original_commit(self, blackboard)
        decision = dict(blackboard.get_val("bar_start_decision_report", {}) or {})
        committed_after = list(blackboard.get_val("committed_bar_starts", []) or [])
        trace.append(_json_safe({
            "window": window,
            "committed_before": committed_before,
            "candidates_before_commit": candidates_before,
            "madmom_candidate_report": madmom_report,
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
        print(f"[PASS-234] blocked: missing {AUDIO_PATH}")
        return 1
    reuse_stems_cache()
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    from pgm_craft.pipeline import PGMCraftEngine

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

    print(f"[PASS-235] elapsed={elapsed:.1f}s full_song_ticks={len(trace)} trace={TRACE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
