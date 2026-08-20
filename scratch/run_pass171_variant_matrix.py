"""
Pass 171 — 多版本 BarStart v2 後處理節點比較 harness

目的：
《World is Mine》黃金基準版（2026-07-30 16:30）是舊版 BeatNet ensemble 產生的，BarStart v2
成為預設決策來源後（Pass 142+），同曲重跑會少 2 小節、尾奏被截斷成 3 拍、前奏有約 1 拍相位
偏移。Pass 171 在 FullSongBarStartLoopNode 加了 barstart_v2_postprocess_flags 旗標，讓
Pass 168 (TwoWayAnchorBacktraceNode) / Pass 169 (GroovePatternPhaseDecoderNode) /
Pass 170 (BarGridSanityPrunerNode) 三個後處理節點可以獨立開關。

本腳本針對同一首歌，一次跑出 5 個變體（見下方 VARIANTS），每個變體重用黃金專案已經分離好的
stems/（symlink 優先，避免重跑 Demucs），只重跑 Stage 3 節拍追蹤 + Module 3 BarStart v2
決策層，輸出到 outputs/pass171_variants/<variant_name>/，並用
pgm_craft.golden_benchmark 算出每個變體跟黃金基準的差異，寫成
outputs/pass171_variants/comparison_report.json + 終端機表格。

使用方式：
    python scratch/run_pass171_variant_matrix.py

跑完後，請實際聽 outputs/pass171_variants/<variant_name>/click/mix_with_click.wav，
選出聽感最接近（或超越）黃金版的變體，回報給下一個 Pass 172 任務書正式落地。
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


GOLDEN_PROJECT_DIR = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
AUDIO_PATH = os.path.join(GOLDEN_PROJECT_DIR, "source", "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】.wav")
VARIANTS_ROOT = r"d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\pass171_variants"
# 絕對不直接 symlink/junction 回黃金專案本身 —— module3 階段會在 stems_dir 底下額外寫入
# submix 等衍生檔案，直接連回黃金專案會有寫壞使用者珍視的黃金參考資料的風險。
# 一律先「真的複製」一份到這個共用快取，變體再 junction/symlink 回這份快取，不動golden分毫。
SHARED_STEMS_CACHE = os.path.join(VARIANTS_ROOT, "_shared_stems_cache", "stems")

# 對應 ResolveProjectNameNode 的清洗規則 (input_acquisition_bt.py)，
# 用來預先算出每個變體資料夾底下的 project_dir 名稱，才能把 stems/ symlink 放對位置。
def resolve_project_name(title: str) -> str:
    safe = re.sub(r'[\*?:"<>|]', "", title).strip()
    safe = re.sub(r'\s+', "_", safe)
    return (safe[:120] or "untitled_project")


PROJECT_NAME = resolve_project_name(os.path.splitext(os.path.basename(AUDIO_PATH))[0])

VARIANTS = [
    {
        "name": "v1_current_default",
        "flags": {"twoway_backtrace": True, "groove_phase_decode": True, "sanity_pruner": True},
        "note": "現況 (Pass 170 行為)，對照組",
    },
    {
        "name": "v2_no_sanity_pruner",
        "flags": {"twoway_backtrace": True, "groove_phase_decode": True, "sanity_pruner": False},
        "note": "懷疑 Pass 170 過度合併/砍掉合法短小節（尤其尾奏）",
    },
    {
        "name": "v3_no_groove_phase",
        "flags": {"twoway_backtrace": True, "groove_phase_decode": False, "sanity_pruner": True},
        "note": "懷疑 Pass 169 反拍解碼在前奏誤判、造成相位偏移",
    },
    {
        "name": "v4_no_twoway_backtrace",
        "flags": {"twoway_backtrace": False, "groove_phase_decode": True, "sanity_pruner": True},
        "note": "懷疑 Pass 168 反推邏輯本身引入相位誤差",
    },
    {
        "name": "v5_all_disabled",
        "flags": {"twoway_backtrace": False, "groove_phase_decode": False, "sanity_pruner": False},
        "note": "最貼近 Pass 167（三個新節點都還沒加上去）的基準線",
    },
]


def link_or_copy_dir(src: str, dst: str) -> str:
    """把 src 目錄重用到 dst：優先 symlink，其次 Windows junction，最後退回複製。
    回傳實際採用的方式，供終端機顯示。"""
    if os.path.exists(dst):
        return "already_exists"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.symlink(src, dst, target_is_directory=True)
        return "symlink"
    except OSError:
        pass
    try:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", dst, src],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0 and os.path.exists(dst):
            return "junction"
    except Exception:
        pass
    shutil.copytree(src, dst)
    return "copy"


def ensure_shared_stems_cache() -> None:
    """把黃金專案的 stems/ 真的複製一份到共用快取（只做一次），後續變體一律 link 回這份
    快取，絕不直接連回黃金專案，避免 module3 階段寫入的 submix 衍生檔汙染黃金參考資料。"""
    if os.path.exists(SHARED_STEMS_CACHE):
        return
    print(f"[Pass171] 建立共用 stems 快取（僅此一次）: {SHARED_STEMS_CACHE}")
    os.makedirs(os.path.dirname(SHARED_STEMS_CACHE), exist_ok=True)
    shutil.copytree(os.path.join(GOLDEN_PROJECT_DIR, "stems"), SHARED_STEMS_CACHE)


def prepare_variant_stems(variant_dir: str) -> str:
    """在 variant_dir/<PROJECT_NAME>/stems/ 底下 link 回共用快取（而非黃金專案本身），
    這樣 target_stage="module3" 就不用重跑 Demucs 分離。source/ 則刻意不預先放置，
    交給 pipeline 自己從 AUDIO_PATH（唯讀來源）複製一份，避免 junction 造成
    「複製檔案到自己身上」的 WinError 32 衝突。"""
    ensure_shared_stems_cache()
    project_dir = os.path.join(variant_dir, PROJECT_NAME)
    os.makedirs(project_dir, exist_ok=True)
    stems_mode = link_or_copy_dir(SHARED_STEMS_CACHE, os.path.join(project_dir, "stems"))
    return stems_mode


def run_variant(variant: dict) -> dict:
    variant_dir = os.path.join(VARIANTS_ROOT, variant["name"])
    os.makedirs(variant_dir, exist_ok=True)
    stems_mode = prepare_variant_stems(variant_dir)

    print(f"\n=== [Pass 171] 執行變體 {variant['name']} ({variant['note']}) — stems 重用方式: {stems_mode} ===")
    t0 = time.time()

    engine = PGMCraftEngine(enable_stem_separation=True)
    report = engine.run(
        AUDIO_PATH,
        output_dir=variant_dir,
        enable_stem=True,
        target_stage="module3",
        user_meter_selection="4/4",
        allow_temporary_bar_delta=0,
        barstart_v2_postprocess_flags=variant["flags"],
    )

    elapsed = time.time() - t0
    measure_map = report.get("measure_map", [])
    stats = compute_measure_map_stats(measure_map)
    diff = compare_to_golden(stats)

    click_path = os.path.join(variant_dir, PROJECT_NAME, "click", "mix_with_click.wav")

    result = {
        "variant": variant["name"],
        "note": variant["note"],
        "flags": variant["flags"],
        "elapsed_sec": round(elapsed, 1),
        "stats": stats,
        "diff_vs_golden": diff,
        "mix_with_click": click_path,
        "click_exists": os.path.exists(click_path),
    }
    print(f"    小節數={stats['total_measures']} (黃金版差 {diff['total_measures']:+d})  "
          f"時長={stats['total_duration_sec']:.2f}s (差 {diff['total_duration_sec']:+.2f}s)  "
          f"BPM跳動={stats['bpm_jump_count']} (差 {diff['bpm_jump_count']:+d})  "
          f"不規則小節={stats['irregular_measure_count']} (差 {diff['irregular_measure_count']:+d})  "
          f"耗時={elapsed:.1f}s")
    return result


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[FATAL] 找不到來源音檔：{AUDIO_PATH}")
        sys.exit(1)
    if not os.path.exists(os.path.join(GOLDEN_PROJECT_DIR, "stems")):
        print(f"[FATAL] 找不到黃金專案的已分離 stems/：{GOLDEN_PROJECT_DIR}\\stems")
        sys.exit(1)

    os.makedirs(VARIANTS_ROOT, exist_ok=True)
    results = []
    for variant in VARIANTS:
        try:
            results.append(run_variant(variant))
        except Exception as exc:
            print(f"[ERROR] 變體 {variant['name']} 執行失敗: {exc}")
            results.append({"variant": variant["name"], "note": variant["note"], "error": str(exc)})

    report_path = os.path.join(VARIANTS_ROOT, "comparison_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"golden": GOLDEN_WORLD_IS_MINE_STATS, "variants": results}, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 100)
    print(f"黃金基準: {GOLDEN_WORLD_IS_MINE_STATS['total_measures']} 小節 / "
          f"{GOLDEN_WORLD_IS_MINE_STATS['total_duration_sec']:.2f}s / "
          f"BPM {GOLDEN_WORLD_IS_MINE_STATS['avg_bpm']:.1f} / 0 次跳動")
    print(f"{'變體':<24}{'小節差':>8}{'時長差(s)':>12}{'BPM跳動差':>10}{'不規則差':>10}  說明")
    for r in results:
        if "error" in r:
            print(f"{r['variant']:<24}{'ERROR':>8}  {r['error']}")
            continue
        d = r["diff_vs_golden"]
        print(f"{r['variant']:<24}{d['total_measures']:>+8}{d['total_duration_sec']:>+12.2f}"
              f"{d['bpm_jump_count']:>+10}{d['irregular_measure_count']:>+10}  {r['note']}")
    print("=" * 100)
    print(f"\n完整報告：{report_path}")
    print("請實際試聽每個變體的 mix_with_click.wav，選出聽感最接近/超越黃金版的方向：")
    for r in results:
        if r.get("click_exists"):
            print(f"  [{r['variant']}] {r['mix_with_click']}")


if __name__ == "__main__":
    main()
