r"""
Pass 198 根因診斷——離線驗證「只保留階段 A（含證據門檻）、完全不跑
階段 B」的最終結果，不需要重跑整條真實管線。

用法前提：`scratch/debug_measure_map_dump.json` 已經存在（由暫時的
debug instrumentation 對 MeasureMapNode.build_measure_map 加的埋點,
在真實管線跑一次後產生，內容是 Pass 197 refined_beats 原始輸入
+ 真實的 beat_phase_protected_ranges，埋點本身已經從 audio_nodes.py
移除，不影響正式程式碼）。

結論：total_measures=114、irregular=10，跟目前已驗證信任的 Pass 197
單獨基準完全一致，只是 3 個問題點因為階段 A 升格而挪動位置——證明
階段 B 的連鎖 bug 移除後，階段 A 本身是安全、正確的。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgm_craft.workflow.audio_nodes import MeasureMapNode

DEBUG_DUMP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_measure_map_dump.json")
STEMS_DIR = (
    r"outputs\pass198_default_pipeline_reverify"
    r"\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\stems"
)


def main():
    with open(DEBUG_DUMP_PATH, encoding="utf-8") as f:
        dump = json.load(f)

    protected_ranges = [tuple(r) for r in dump["protected_ranges"]]

    node = MeasureMapNode()
    beat_rows = node._normalize_beats(dump["input_beats"])
    beat_rows = node._ensure_44_phase_continuity(beat_rows, protected_ranges)
    downbeat_indexes = [i for i, r in enumerate(beat_rows) if r["beat"] == 1]

    downbeat_indexes, reconciliation = node._reconcile_close_downbeats(
        beat_rows, downbeat_indexes, protected_ranges
    )
    beat_rows = node._ensure_44_phase_continuity(beat_rows, protected_ranges)
    downbeat_indexes = [i for i, r in enumerate(beat_rows) if r["beat"] == 1]

    beat_rows, gap_reconciliation = node._interpolate_protected_gaps(
        beat_rows, downbeat_indexes, protected_ranges
    )
    downbeat_indexes = [i for i, r in enumerate(beat_rows) if r["beat"] == 1]

    beat_rows, promotion_reconciliation = node._promote_intra_bar_downbeats(
        beat_rows, downbeat_indexes, protected_ranges, stems={}, stems_dir=STEMS_DIR
    )
    downbeat_indexes = [i for i, r in enumerate(beat_rows) if r["beat"] == 1]

    # 刻意不呼叫 _interpolate_weak_evidence_gaps（階段 B）——這正是本次
    # 診斷的修復規格：直接不跑它，不是修它。

    print(f"Pass 197A 仲裁: {len(reconciliation)} 次")
    print(f"Pass 197B 空隙插值: {len(gap_reconciliation)} 次")
    print(f"Pass 198A 升格（含證據門檻）: {len(promotion_reconciliation)} 次")
    for r in promotion_reconciliation:
        print(f"  {r}")

    measure_map = node._build_from_downbeats(
        beat_rows, downbeat_indexes, source="downbeat", protected_ranges=protected_ranges
    )
    irregular = [m for m in measure_map if m.get("is_variable_length")]
    print(f"\ntotal_measures={len(measure_map)} irregular_measure_count={len(irregular)}")
    for m in irregular:
        print(f"  measure={m['measure']} beat_count={m['beat_count']} start={m['start_time']:.3f}s")


if __name__ == "__main__":
    main()
