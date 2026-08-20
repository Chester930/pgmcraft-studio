r"""
Pass 180 — ViterbiTempoSmoothingNode 修好之後，重新驗證 GapReinforcementNode

目的：
Pass 178 的真實資料 A/B 回歸發現 GapReinforcementNode 啟用後會讓
ViterbiTempoSmoothingNode 把補強出的連續拍點誤判成離群值、壓縮消失
（見 docs/PASS-178-GAP-REINFORCEMENT-PRODUCTION-INTEGRATION-TASK.md 第 4.3.1
節）。Pass 180 修好了 ViterbiTempoSmoothingNode 本身（改用局部滾動中位數，
不再連鎖疊加），已經用真實抓到的資料重播驗證過演算法本身沒問題。這支腳本
重跑一次完整正式管線（GapReinforcementNode 啟用），確認修好後的節點組合在
真實歌曲上：

1. 不再出現 click 完全消失的區段。
2. BPM 跳動次數比 Pass 178 原始問題版本（6 次）下降。
3. 跟黃金基準、跟停用時的對照組比較，整體品質分數是否合理。

用法：
    python scratch/run_pass180_reverify_gap_reinforcement.py
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
from pgm_craft.workflow import beat_tracking_bt

# GapReinforcementNode 生產預設是 enabled=False（Pass 178 發現問題後改的）。
# 這支腳本專門用來驗證 Pass 180 修好 ViterbiTempoSmoothingNode 之後，
# GapReinforcementNode 啟用的效果，所以在這個行程裡把預設值蓋成 True——
# 不動 build_beat_refinement_nodes() 呼叫端本身，生產環境的行為不受影響。
_original_init = beat_tracking_bt.GapReinforcementNode.__init__


def _enabled_by_default_init(self, config_path=None, enabled=True):
    _original_init(self, config_path=config_path, enabled=enabled)


beat_tracking_bt.GapReinforcementNode.__init__ = _enabled_by_default_init

SOURCE_PROJECT_DIR = (
    r"D:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\pass175_current_pipeline_check"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】"
)
AUDIO_PATH = os.path.join(
    SOURCE_PROJECT_DIR, "source", "【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】.wav"
)
REGRESSION_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "pass180_gap_reinforcement_reverify"
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
    """絕不直接 junction 回 Pass 175 的專案本身——先真的複製一份到獨立快取，
    回歸測試才 link 回這份快取，不會有寫壞正在使用中的專案的風險。"""
    if os.path.exists(SHARED_STEMS_CACHE):
        return
    print(f"[Pass180回驗] 建立共用 stems 快取（僅此一次）：{SHARED_STEMS_CACHE}")
    os.makedirs(os.path.dirname(SHARED_STEMS_CACHE), exist_ok=True)
    shutil.copytree(os.path.join(SOURCE_PROJECT_DIR, "stems"), SHARED_STEMS_CACHE)


def main():
    if not os.path.exists(AUDIO_PATH):
        print(f"[FATAL] 找不到來源音檔：{AUDIO_PATH}")
        sys.exit(1)
    if not os.path.exists(os.path.join(SOURCE_PROJECT_DIR, "stems")):
        print(f"[FATAL] 找不到 Pass175 專案已分離的 stems/：{SOURCE_PROJECT_DIR}\\stems")
        sys.exit(1)

    os.makedirs(REGRESSION_ROOT, exist_ok=True)
    ensure_shared_stems_cache()

    project_dir = os.path.join(REGRESSION_ROOT, PROJECT_NAME)
    os.makedirs(project_dir, exist_ok=True)
    stems_mode = link_or_copy_dir(SHARED_STEMS_CACHE, os.path.join(project_dir, "stems"))
    print(f"[Pass180回驗] stems 重用方式：{stems_mode}")

    print(f"\n=== [Pass180回驗] 執行 target_stage=module3"
          f"（GapReinforcementNode 啟用 + 修好後的 ViterbiTempoSmoothingNode）===")
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

    click_path = os.path.join(project_dir, "click", "mix_with_click.wav")
    gap_report_path = os.path.join(project_dir, "reports", "gap_reinforcement", "blocks.json")
    beats_report_path = os.path.join(project_dir, "reports", "gap_reinforcement", "beats.json")

    print("\n" + "=" * 100)
    print(f"耗時: {elapsed:.1f}s")
    print(f"黃金基準:         {GOLDEN_WORLD_IS_MINE_STATS['total_measures']} 小節 / "
          f"{GOLDEN_WORLD_IS_MINE_STATS['total_duration_sec']:.2f}s / "
          f"BPM跳動 {GOLDEN_WORLD_IS_MINE_STATS['bpm_jump_count']}")
    print(f"Pass178 舊版問題:  109 小節 / 169.69s / BPM跳動 6 / 不規則小節 1（含 click 消失 bug）")
    print(f"Pass178 對照組:    117 小節 / 172.40s / BPM跳動 0 / 不規則小節 0（停用時）")
    print(f"Pass180 這次結果: {stats['total_measures']} 小節（差黃金基準 {diff['total_measures']:+d}） / "
          f"{stats['total_duration_sec']:.2f}s（差 {diff['total_duration_sec']:+.2f}s） / "
          f"BPM跳動 {stats['bpm_jump_count']}（差 {diff['bpm_jump_count']:+d}） / "
          f"不規則小節 {stats['irregular_measure_count']}（差 {diff['irregular_measure_count']:+d}）")
    print(f"mix_with_click.wav 存在: {os.path.exists(click_path)} -> {click_path}")
    print(f"gap_reinforcement 診斷輸出存在: blocks.json={os.path.exists(gap_report_path)}, "
          f"beats.json={os.path.exists(beats_report_path)}")
    print("=" * 100)

    result = {
        "elapsed_sec": round(elapsed, 1),
        "stats": stats,
        "diff_vs_golden": diff,
        "mix_with_click": click_path,
        "click_exists": os.path.exists(click_path),
        "gap_reinforcement_blocks_exists": os.path.exists(gap_report_path),
        "gap_reinforcement_beats_exists": os.path.exists(beats_report_path),
    }
    report_path = os.path.join(REGRESSION_ROOT, "reverify_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n完整報告：{report_path}")
    print(f"請實際試聽：{click_path}")


if __name__ == "__main__":
    main()
