"""PASS-207: clean (non-instrumented, non-monkeypatched) production-settings
reverify of BarStart V2 after the Pass 205 quality-gate fix + Pass 206
observability additions.

Why this script exists: `scratch/run_pass203_evidence_fusion_diagnosis.py`
monkeypatches `FullSongBarStartLoopNode.__init__` to force `stall_limit=10000`
for the *entire python process*, including the real `_run_barstart_v2_comparison`
call inside the normal `target_stage="module3"` pipeline run. That means the
"115 measures / 404 unresolved bar spans / V2 score 37.15" numbers produced by
that script do NOT reflect real production behavior (`stall_limit=3`,
default) -- they are inflated by ~400 wasted ticks where the probe window
slides past the song's actual ~176.65s duration (a pre-existing, known,
production-harmless logic gap documented in
docs/PASS-203-EVIDENCE-FUSION-THRESHOLD-DIAGNOSIS-TASK.md section 5.3 that
only manifests when stall_limit is disabled).

This script runs the plain pipeline with no monkeypatching at all, so
`FullSongBarStartLoopNode` uses its real default `stall_limit=3`, to get an
honest picture of what BarStart V2 actually produces under real settings.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time

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
OUTPUT_ROOT = os.path.join(ROOT, "outputs", "pass207_clean_production_verify")
STEMS_SOURCE = os.path.join(ROOT, "outputs", "pass203_evidence_fusion_diagnosis", AUDIO_NAME, "stems")


def safe_name(title):
    return re.sub(r"\s+", "_", re.sub(r'[\*?:"<>|]', "", title).strip())[:120]


def reuse_stems_cache():
    dst = os.path.join(OUTPUT_ROOT, AUDIO_NAME, "stems")
    if os.path.exists(dst):
        return
    if not os.path.exists(STEMS_SOURCE):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.symlink(STEMS_SOURCE, dst, target_is_directory=True)
    except OSError:
        subprocess_run_mklink(dst, STEMS_SOURCE)


def subprocess_run_mklink(dst, src):
    import subprocess
    subprocess.run(["cmd", "/c", "mklink", "/J", dst, src], capture_output=True, text=True, check=False)


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[PASS-207] blocked: missing {AUDIO_PATH}")
        return 1
    reuse_stems_cache()
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    print("[PASS-207] running target_stage=module3 with NO monkeypatching (real stall_limit=3)")
    started = time.time()
    report = PGMCraftEngine(enable_stem_separation=True).run(
        AUDIO_PATH,
        output_dir=OUTPUT_ROOT,
        enable_stem=True,
        target_stage="module3",
        user_meter_selection="4/4",
        allow_temporary_bar_delta=0,
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
        "pass": "Pass 207 (clean production verify)",
        "elapsed_sec": elapsed,
        "legacy_stats": stats,
        "legacy_diff_to_golden": compare_to_golden(stats) if stats else None,
        "golden_benchmark": GOLDEN_WORLD_IS_MINE_STATS,
        "barstart_v2_report_status": v2_report.get("status"),
        "barstart_v2_promoted": v2_report.get("promotion_gate", {}).get("adoptable"),
        "barstart_v2_beat_count": v2_report.get("beat_count"),
        "barstart_v2_unresolved_bar_span_count": v2_report.get("unresolved_bar_span_count"),
        "barstart_v2_quality_comparison": v2_report.get("quality_comparison"),
        "barstart_v2_promotion_gate": v2_report.get("promotion_gate"),
        "barstart_v2_full_song_loop_report_summary": {
            k: v for k, v in (v2_report.get("full_song_loop_report", {}) or {}).items()
            if k not in ("diagnostic_trace", "final_committed_bar_starts", "loop_committed_bar_starts", "initial_committed_bar_starts")
        },
        "barstart_v2_state_consistency": v2_report.get("state_consistency"),
        "click_report_path": click_report_path,
    }
    report_path = os.path.join(OUTPUT_ROOT, "reverify_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"[PASS-207] report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
