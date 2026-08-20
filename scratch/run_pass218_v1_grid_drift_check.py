"""PASS-218: before designing an absolute-phase-anchor fix for Pass 217's
Chorus1/Outro drift finding, check whether v1's OWN reference grid
(v1_reference_beat_grid, independent of V2's self-referential commit
chain) is itself accurate in the 86.9-176.6s drift zone. If v1 also
drifts there, it cannot serve as an absolute anchor and the fix design
needs to change.

Captures `original_beat_grid` (v1's refined beat grid, the same array
threaded into v2_blackboard as v1_reference_beat_grid) via
Module3BarStartV2MergeNode.execute, dumps downbeat times only.

Audit-only: monkeypatches only Module3BarStartV2MergeNode.execute, restores
in finally.
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
OUTPUT_ROOT = os.path.join(ROOT, "outputs", "pass218_v1_grid_drift_check")
STEMS_SOURCE = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")
OUT_PATH = os.path.join(ROOT, "scratch", "pass218_v1_reference_downbeats.json")


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


def _install_probe(captured):
    from pgm_craft.workflow.module3_bt import Module3BarStartV2MergeNode, _run_barstart_v2_comparison

    original = Module3BarStartV2MergeNode.execute

    def wrapped(self, blackboard):
        comparison = _run_barstart_v2_comparison(blackboard)
        if comparison and comparison.get("success"):
            grid = comparison["original_beat_grid"]
            downbeats = sorted(float(t) for t, b in grid if int(round(b)) == 1)
            captured["v1_downbeats"] = downbeats
        return original(self, blackboard)

    Module3BarStartV2MergeNode.execute = wrapped
    return (Module3BarStartV2MergeNode, original)


def _restore_probe(patch):
    target, original = patch
    target.execute = original


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-218-v1drift] blocked: missing {AUDIO_PATH}")
        return 1
    reuse_stems_cache()
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    captured = {}
    patch = _install_probe(captured)
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
        _restore_probe(patch)
    elapsed = time.time() - started

    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(captured, handle, ensure_ascii=False, indent=2)

    print(f"[PASS-218-v1drift] elapsed={elapsed:.1f}s downbeats={len(captured.get('v1_downbeats', []))} out={OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
