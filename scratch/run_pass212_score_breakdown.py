"""PASS-212: capture the exact score breakdown (tempo_stability,
downbeat_consistency, and the V2-specific penalty deductions) for both the
legacy grid and the promoted V2 grid, from a real pipeline run -- to find
what is actually dragging V2's score down before attempting any more fixes.

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
OUTPUT_ROOT = os.path.join(ROOT, "outputs", "pass212_score_breakdown")
STEMS_SOURCE = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")


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


def _install_probes(captured):
    from pgm_craft.workflow import module3_bt
    from pgm_craft.workflow.module3_barstart_v2_bt import BarStartV2QualityScoreNode
    from pgm_craft.workflow import beat_tracking_bt

    original_score_fn = module3_bt._score_beat_grid_quality
    original_v2_node = BarStartV2QualityScoreNode.execute

    def wrapped_score_fn(beats, *args, **kwargs):
        result = original_score_fn(beats, *args, **kwargs)
        captured.setdefault("legacy_score_calls", []).append(result)
        return result

    def wrapped_v2_node(self, blackboard):
        status = original_v2_node(self, blackboard)
        captured["v2_quality_score"] = dict(blackboard.get_val("barstart_v2_quality_score", {}) or {})
        captured["bar_grid_repair_report"] = dict(blackboard.get_val("bar_grid_repair_report", {}) or {})
        captured["downbeat_fix_report"] = dict(blackboard.get_val("downbeat_fix_report", {}) or {})
        captured["unresolved_bar_spans_count"] = len(blackboard.get_val("unresolved_bar_spans", []) or [])
        return status

    module3_bt._score_beat_grid_quality = wrapped_score_fn
    BarStartV2QualityScoreNode.execute = wrapped_v2_node
    return [
        (module3_bt, "_score_beat_grid_quality", original_score_fn),
        (BarStartV2QualityScoreNode, "execute", original_v2_node),
    ]


def _restore_probes(patches):
    for target, attr, original in patches:
        setattr(target, attr, original)


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-212-score] blocked: missing {AUDIO_PATH}")
        return 1
    reuse_stems_cache()
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    captured = {}
    patches = _install_probes(captured)
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

    print(f"[PASS-212-score] elapsed={elapsed:.1f}s")
    print(json.dumps(captured, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
