"""PASS-211: confirm the user's explicit promotion approval actually
replaces the legacy output end-to-end.

Identical to scratch/run_pass207_clean_production_verify.py (no
monkeypatching, real stall_limit=3 default), except it passes
barstart_v2_promotion_approved=True through PGMCraftEngine.run() ->
BTWorkflowEngine.run() -> blackboard, so BarStartV2AutoMergeNode's
promotion_decision can actually flip promoted=True and swap
beats/refined_beats to BarStart V2's grid. Every other caller of the
pipeline leaves this parameter unset, so this is an explicit per-run
opt-in, not a global default change.
"""

from __future__ import annotations

import json
import os
import re
import time
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.golden_benchmark import (
    GOLDEN_WORLD_IS_MINE_STATS,
    compare_to_golden,
    compute_measure_map_stats,
)
from pgm_craft.pipeline import PGMCraftEngine

AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_PATH = os.path.join(
    ROOT, "outputs", "pass198_default_pipeline_reverify", AUDIO_NAME, "source", AUDIO_NAME + ".wav"
)
OUTPUT_ROOT = os.path.join(ROOT, "outputs", "pass211_promoted_production_verify")
STEMS_SOURCE = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")


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


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-211-promoted] blocked: missing {AUDIO_PATH}")
        return 1
    reuse_stems_cache()
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    print("[PASS-211-promoted] running target_stage=module3 with barstart_v2_promotion_approved=True")
    started = time.time()
    report = PGMCraftEngine(enable_stem_separation=True).run(
        AUDIO_PATH,
        output_dir=OUTPUT_ROOT,
        enable_stem=True,
        target_stage="module3",
        user_meter_selection="4/4",
        allow_temporary_bar_delta=0,
        barstart_v2_promotion_approved=True,
    )
    elapsed = time.time() - started

    project_dir = os.path.join(OUTPUT_ROOT, safe_name(AUDIO_NAME))
    click_report_path = os.path.join(project_dir, "reports", "module3_beat_click_report.json")
    v2_report = {}
    if os.path.exists(click_report_path):
        with open(click_report_path, encoding="utf-8") as handle:
            full = json.load(handle)
        v2_report = full.get("barstart_v2_report", {})

    measure_map = report.get("measure_map", [])
    stats = compute_measure_map_stats(measure_map) if measure_map else {}

    output = {
        "pass": "Pass 211 (promoted production verify)",
        "elapsed_sec": elapsed,
        "legacy_stats_after_promotion": stats,
        "legacy_diff_to_golden": compare_to_golden(stats) if stats else None,
        "golden_benchmark": GOLDEN_WORLD_IS_MINE_STATS,
        "barstart_v2_status": v2_report.get("status"),
        "barstart_v2_promoted_flag": v2_report.get("promoted"),
        "barstart_v2_replaces_module3_click": v2_report.get("replaces_module3_click"),
        "promotion_gate": v2_report.get("promotion_gate"),
        "promotion_decision": v2_report.get("promotion_decision"),
        "quality_comparison": v2_report.get("quality_comparison"),
        "click_report_path": click_report_path,
    }
    report_path = os.path.join(OUTPUT_ROOT, "reverify_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"[PASS-211-promoted] report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
