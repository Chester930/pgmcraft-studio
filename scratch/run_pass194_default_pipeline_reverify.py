r"""
Pass 194 — MeasureMapNode 相位補全尊重 beat_phase_protected_ranges 真實資料回驗
"""

import os
import re
import sys
import json
import shutil
import subprocess
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.pipeline import PGMCraftEngine
from pgm_craft.golden_benchmark import compute_measure_map_stats, compare_to_golden, GOLDEN_WORLD_IS_MINE_STATS

SOURCE_PROJECT_DIR = (
    r"D:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\pass175_current_pipeline_check"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
)
AUDIO_PATH = os.path.join(
    SOURCE_PROJECT_DIR, "source", "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】.wav"
)
REGRESSION_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "pass194_default_pipeline_reverify"
)
SHARED_STEMS_CACHE = os.path.join(REGRESSION_ROOT, "_shared_stems_cache", "stems")


def resolve_project_name(title: str) -> str:
    safe = re.sub(r'[\*?:"<>|]', "", title).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:120] or "untitled_project"


PROJECT_NAME = resolve_project_name(os.path.splitext(os.path.basename(AUDIO_PATH))[0])


def link_or_copy_dir(src: str, dst: str) -> str:
    if os.path.exists(dst):
        return "already_exists"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.symlink(src, dst, target_is_directory=True)
        return "symlink"
    except OSError:
        pass
    try:
        result = subprocess.run(["cmd", "/c", "mklink", "/J", dst, src], capture_output=True, text=True, check=False)
        if result.returncode == 0 and os.path.exists(dst):
            return "junction"
    except Exception:
        pass
    shutil.copytree(src, dst)
    return "copy"


def ensure_shared_stems_cache() -> None:
    if os.path.exists(SHARED_STEMS_CACHE):
        return
    print(f"[Pass194回驗] 建立共用 stems 快取：{SHARED_STEMS_CACHE}")
    os.makedirs(os.path.dirname(SHARED_STEMS_CACHE), exist_ok=True)
    p193_cache = r"D:\Users\666\Desktop\UVR5 音檔\自動節拍器\.claude\worktrees\pass171-multi-variant-harness\outputs\pass193_default_pipeline_reverify\_shared_stems_cache\stems"
    src = p193_cache if os.path.exists(p193_cache) else os.path.join(SOURCE_PROJECT_DIR, "stems")
    shutil.copytree(src, SHARED_STEMS_CACHE)


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[FATAL] 找不到來源音檔：{AUDIO_PATH}")
        sys.exit(1)

    os.makedirs(REGRESSION_ROOT, exist_ok=True)
    ensure_shared_stems_cache()

    project_dir = os.path.join(REGRESSION_ROOT, PROJECT_NAME)
    os.makedirs(project_dir, exist_ok=True)
    stems_mode = link_or_copy_dir(SHARED_STEMS_CACHE, os.path.join(project_dir, "stems"))
    print(f"[Pass194回驗] stems 重用方式：{stems_mode}")

    print(f"\n=== [Pass194回驗] 執行 target_stage=module3（MeasureMapNode 尊重 beat_phase_protected_ranges）===")
    t0 = time.time()

    engine = PGMCraftEngine(enable_stem_separation=True)
    report = engine.run(
        AUDIO_PATH,
        output_dir=REGRESSION_ROOT,
        enable_stem=True,
        target_stage="module3",
        user_meter_selection="4/4",
        allow_temporary_bar_delta=0,
    )

    elapsed = time.time() - t0
    measure_map = report.get("measure_map", [])
    stats = compute_measure_map_stats(measure_map)
    diff = compare_to_golden(stats)

    irregulars = [m for m in measure_map if m.get("is_variable_length")]

    print("\n不規則小節詳情：")
    for m in irregulars:
        print(f"  measure={m['measure']}, beat_count={m['beat_count']}, start={m['start_time']:.3f}s")

    # 直接核對 18-20 秒目標區段（Pass 184/186 驗證過 beat-1 應在
    # 18.563s/20.014s 附近）在這次真實輸出裡有沒有被正確標成 beat 1。
    print("\n18-20 秒目標區段核對：")
    for m in measure_map:
        if 17.0 <= m["start_time"] <= 21.0:
            beats_str = ", ".join(f"({b['beat']},{b['time']:.3f})" for b in m["beats"])
            print(f"  measure={m['measure']} start={m['start_time']:.3f} beats=[{beats_str}]")

    print("\n" + "=" * 100)
    print(f"耗時: {elapsed:.1f}s")
    print(
        f"Pass194 這次結果: {stats['total_measures']} 小節（差黃金基準 {diff['total_measures']:+}） / "
        f"{stats['total_duration_sec']:.2f}s（差 {diff['total_duration_sec']:+.2f}s） / "
        f"BPM跳動 {stats['bpm_jump_count']}（差 {diff['bpm_jump_count']:+}） / "
        f"不規則小節 {stats['irregular_measure_count']}（差 {diff['irregular_measure_count']:+}）"
    )
    click_path = os.path.join(project_dir, "click", "mix_with_click.wav")
    print(f"mix_with_click.wav 存在: {os.path.exists(click_path)} -> {click_path}")
    print("=" * 100 + "\n")

    out_file = os.path.join(REGRESSION_ROOT, "reverify_report.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "pass": "Pass 194",
                "elapsed_sec": elapsed,
                "stats": stats,
                "diff_to_golden": diff,
                "golden_benchmark": GOLDEN_WORLD_IS_MINE_STATS,
                "irregular_details": [
                    {"measure": m["measure"], "beat_count": m["beat_count"], "start_time": m["start_time"]}
                    for m in irregulars
                ],
                "mix_with_click": click_path,
                "click_exists": os.path.exists(click_path),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"完整報告：{out_file}")
    print(f"請實際試聽（特別注意 18-20 秒重音位置）：{click_path}")


if __name__ == "__main__":
    main()
