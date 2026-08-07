"""
SDD Pass 171 — 黃金基準回歸比對與多版本 BarStart v2 後處理節點旗標開關驗證

背景：
使用者認定 2026-07-30 16:30 產出的《World is Mine》click 是本週音質最佳的一版。
分析發現該版其實是舊版 BeatNet ensemble + downbeat 精修鏈產生的（121 小節、全 4/4、
涵蓋完整 175.69 秒、零次 BPM 跳動），BarStart v2 當時只是旁路診斷，並未影響輸出。

Pass 142 之後 BarStart v2 被扶正為唯一決策來源，同曲重跑（comparison_test_pass167/168）
只剩 119 小節、171.39 秒，且尾奏最後一小節被截斷成 3 拍、前奏約有 1 拍相位偏移。

本測試驗證兩件事：
1. `pgm_craft/golden_benchmark.py` 的統計函式能正確算出跟黃金基準同一組指標。
2. `FullSongBarStartLoopNode` 新增的 `barstart_v2_postprocess_flags` 旗標，能讓
   Pass 168/169/170 三個後處理節點被獨立開關，且未指定旗標時預設全部執行
   （向下相容，行為與 Pass 170 完全相同）——這是多版本比較 harness
   （scratch/run_pass171_variant_matrix.py）能在同一份程式碼上跑出多個變體的基礎。
"""

import pytest

from pgm_craft.golden_benchmark import (
    GOLDEN_WORLD_IS_MINE_STATS,
    compute_measure_map_stats,
    compare_to_golden,
)
from pgm_craft.workflow.module3_barstart_v2_bt import FullSongBarStartLoopNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _clean_measure_map(count=121, step=1.454, start=0.761542):
    """`count` 個等長 4/4 小節，模擬黃金版 measure_map 的形狀（不含真實逐拍資料）。
    最後一小節的 end_time = start + count * step，即整段涵蓋時長。"""
    starts = [start + i * step for i in range(count)]
    measures = [
        {"measure": i + 1, "start_time": round(t, 6), "beat_count": 4}
        for i, t in enumerate(starts)
    ]
    for i in range(len(measures) - 1):
        measures[i]["end_time"] = measures[i + 1]["start_time"]
    measures[-1]["end_time"] = round(start + count * step, 6)
    return measures


class TestSDDPass171GoldenBenchmark:

    def test_compute_measure_map_stats_matches_uniform_4_4_grid(self):
        step = (175.693469 - 0.761542) / 121
        measure_map = _clean_measure_map(count=121, step=step, start=0.761542)
        stats = compute_measure_map_stats(measure_map)

        assert stats["total_measures"] == 121
        assert stats["irregular_measure_count"] == 0
        assert stats["bpm_jump_count"] == 0
        assert stats["total_duration_sec"] == pytest.approx(GOLDEN_WORLD_IS_MINE_STATS["total_duration_sec"], abs=0.01)

    def test_compute_measure_map_stats_flags_bpm_jump_and_irregular_measure(self):
        measure_map = _clean_measure_map(count=8, step=1.454, start=0.0)
        # 在中間插入一個突然變短、只有 3 拍的小節，製造 BPM 跳動與不規則小節。
        measure_map[4]["beat_count"] = 3
        measure_map[4]["start_time"] = measure_map[3]["start_time"] + 0.36
        for i in range(5, len(measure_map)):
            measure_map[i]["start_time"] = measure_map[4]["start_time"] + (i - 4) * 1.454

        stats = compute_measure_map_stats(measure_map)
        assert stats["irregular_measure_count"] == 1
        assert stats["bpm_jump_count"] >= 1

    def test_compare_to_golden_reports_measure_and_duration_shortfall(self):
        # 模擬目前 BarStart v2（Pass 167/168 同曲重跑）的實測形狀：119 小節、171.39 秒。
        measure_map = _clean_measure_map(count=119, step=(171.386871 - 0.404524) / 119, start=0.404524)
        stats = compute_measure_map_stats(measure_map)
        diff = compare_to_golden(stats)

        assert diff["total_measures"] == -2
        assert diff["total_duration_sec"] < 0


class TestSDDPass171PostprocessFlags:

    def _four_bar_blackboard(self, flags=None):
        bb = Blackboard()
        bars = [1.0, 2.45, 3.9, 5.35]
        bb.set_val("committed_bar_starts", bars)
        # 讓 duration_cap 在第一次檢查就命中，probe tick 迴圈完全不會執行，
        # 只測試迴圈結束後的後處理旗標開關邏輯。
        bb.set_val("audio_duration_sec", 5.35)
        if flags is not None:
            bb.set_val("barstart_v2_postprocess_flags", flags)
        return bb

    def test_default_no_flags_runs_all_three_postprocess_nodes(self):
        bb = self._four_bar_blackboard(flags=None)
        node = FullSongBarStartLoopNode()

        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        assert bb.get_val("twoway_backtrace_report") is not None
        assert bb.get_val("groove_phase_report") is not None
        assert bb.get_val("bar_grid_sanity_report") is not None

    @pytest.mark.parametrize(
        "disabled_flag,report_key",
        [
            ("twoway_backtrace", "twoway_backtrace_report"),
            ("groove_phase_decode", "groove_phase_report"),
            ("sanity_pruner", "bar_grid_sanity_report"),
        ],
    )
    def test_disabling_one_flag_skips_only_that_postprocess_node(self, disabled_flag, report_key):
        other_report_keys = {
            "twoway_backtrace_report",
            "groove_phase_report",
            "bar_grid_sanity_report",
        } - {report_key}

        flags = {"twoway_backtrace": True, "groove_phase_decode": True, "sanity_pruner": True}
        flags[disabled_flag] = False
        bb = self._four_bar_blackboard(flags=flags)
        node = FullSongBarStartLoopNode()

        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        assert bb.get_val(report_key) is None, f"{disabled_flag}=False 時 {report_key} 不應被寫入"
        for other_key in other_report_keys:
            assert bb.get_val(other_key) is not None, f"{other_key} 不該受 {disabled_flag} 影響"
