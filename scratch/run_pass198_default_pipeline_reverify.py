"""Pass 198 real-data reverify using the established World is Mine fixture."""

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


SOURCE_PROJECT_DIR = (
    r"D:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\pass175_current_pipeline_check"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
)
AUDIO_NAME = "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
AUDIO_PATH = os.path.join(SOURCE_PROJECT_DIR, "source", AUDIO_NAME + ".wav")
REGRESSION_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "outputs",
    "pass198_default_pipeline_reverify",
)
SHARED_STEMS_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "outputs",
    "pass196_default_pipeline_reverify",
    "_shared_stems_cache",
    "stems",
)


def safe_name(title):
    return re.sub(r"\s+", "_", re.sub(r'[\*?:"<>|]', "", title).strip())[:120]


def ensure_stems_cache():
    if os.path.exists(SHARED_STEMS_CACHE):
        return
    source = os.path.join(SOURCE_PROJECT_DIR, "stems")
    if not os.path.exists(source):
        raise FileNotFoundError(f"stems cache not found: {SHARED_STEMS_CACHE}")
    os.makedirs(os.path.dirname(SHARED_STEMS_CACHE), exist_ok=True)
    shutil.copytree(source, SHARED_STEMS_CACHE)


def main():
    if not os.path.exists(AUDIO_PATH):
        raise FileNotFoundError(AUDIO_PATH)
    ensure_stems_cache()
    os.makedirs(REGRESSION_ROOT, exist_ok=True)
    project_dir = os.path.join(REGRESSION_ROOT, safe_name(AUDIO_NAME))
    stems_dir = os.path.join(project_dir, "stems")
    os.makedirs(project_dir, exist_ok=True)
    if not os.path.exists(stems_dir):
        try:
            os.symlink(SHARED_STEMS_CACHE, stems_dir, target_is_directory=True)
        except OSError:
            shutil.copytree(SHARED_STEMS_CACHE, stems_dir)

    print("[Pass198] running target_stage=module3")
    started = time.time()
    report = PGMCraftEngine(enable_stem_separation=True).run(
        AUDIO_PATH,
        output_dir=REGRESSION_ROOT,
        enable_stem=True,
        target_stage="module3",
        user_meter_selection="4/4",
        allow_temporary_bar_delta=0,
    )
    elapsed = time.time() - started
    measure_map = report.get("measure_map", [])
    stats = compute_measure_map_stats(measure_map)
    output = {
        "pass": "Pass 198",
        "elapsed_sec": elapsed,
        "stats": stats,
        "diff_to_golden": compare_to_golden(stats),
        "golden_benchmark": GOLDEN_WORLD_IS_MINE_STATS,
        "irregular_details": [
            {"measure": m["measure"], "beat_count": m["beat_count"], "start_time": m["start_time"]}
            for m in measure_map if m.get("is_variable_length")
        ],
        "measure_map_json": os.path.join(project_dir, "reports", "measure_map.json"),
        "mix_with_click": os.path.join(project_dir, "click", "mix_with_click.wav"),
        "click_track": os.path.join(project_dir, "click", "click_track.wav"),
    }
    report_path = os.path.join(REGRESSION_ROOT, "reverify_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"[Pass198] report: {report_path}")


if __name__ == "__main__":
    main()
