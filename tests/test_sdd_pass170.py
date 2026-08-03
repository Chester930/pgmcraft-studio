"""
SDD Pass 170 — 小節網格合理性過濾與 Ghost 小節合併 (BarGridSanityPrunerNode) 驗證

背景：
Pass 168 TwoWayAnchorBacktraceNode 修復 105 處切分搶拍後，部分修復點留下超短「Ghost 殘片小節」
(duration < 0.6 * global_median，約 0.36s)，這些殘片造成相鄰 BPM 跳動超過 35%，
拉低 CommercialBeatQualityNode 評分至 70.2 (NEEDS_MANUAL_EDIT)。

本測試驗證：
1. 注入 5 個 ghost 殘片小節 (duration = 0.36s) 後，BarGridSanityPrunerNode 能正確識別並移除 5 個 ghost 殘片。
2. 移除後小節總數減少 5，且最終小節列表中不存在 duration < 0.6 * median 的殘片。
"""

import pytest
import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import BarGridSanityPrunerNode
from pgm_craft.workflow.audio_nodes import MeasureMapNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass170:

    def test_bar_grid_sanity_pruner_removes_ghost_measures(self):
        bb = Blackboard()
        normal_step = 1.45
        t0 = 0.405
        ghost_step = 0.36  # 約 0.25 * 1.45，遠低於 0.6 * median threshold

        # 建立正常小節序列，然後在第 4、8、12、16、20 個小節後各插入一個 ghost 殘片
        bars = []
        t = t0
        for i in range(25):
            bars.append(t)
            t += normal_step
            # 在第 4、8、12、16、20 個拍點後插入 ghost 殘片
            if i in (3, 7, 11, 15, 19):
                bars.append(t)  # 正常小節的起始點
                t += ghost_step  # 接著一個超短 ghost 殘片

        original_count = len(bars)
        bb.set_val("committed_bar_starts", bars)

        node = BarGridSanityPrunerNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("bar_grid_sanity_report", {})
        assert report.get("pruned", 0) == 5

        fixed_bars = bb.get_val("committed_bar_starts", [])
        fixed_times = [b.get("time") if isinstance(b, dict) else float(b) for b in fixed_bars]

        # 移除後總數應減少 5
        assert len(fixed_times) == original_count - 5

        # 最終不應存在 duration < 0.6 * median 的殘片
        if len(fixed_times) > 1:
            diffs = np.diff(sorted(fixed_times))
            median = float(np.median(diffs))
            assert all(d >= 0.6 * median for d in diffs), f"仍有 ghost 殘片存在: {[d for d in diffs if d < 0.6 * median]}"

    def test_measure_map_node_prune_ghost_downbeats(self):
        """
        Pass 170 fix: MeasureMapNode._prune_ghost_downbeats 應移除相鄰間距只有 1 個 beat 的 ghost downbeat。
        模擬：正常 4-beat 小節中插入 5 個 ghost downbeat（間距只有 1），
        驗證 build_measure_map 不產生 beat_count == 1 的異常小節。
        """
        node = MeasureMapNode()

        # 建立 beats 序列：每小節 4 拍 (beat 1,2,3,4)，在第 4、8 個小節後各插一個 ghost downbeat (beat=1)
        beat_interval = 0.363  # 約 165 BPM
        beats = []
        t = 0.405
        measure_count = 12
        for m in range(measure_count):
            for b in range(1, 5):
                beats.append([t, b])
                t += beat_interval
            # 在第 3 和第 7 個小節後各插入一個 ghost downbeat
            if m in (3, 7):
                beats.append([t, 1])   # ghost downbeat（間距只有 0 拍）
                t += beat_interval * 0.3  # 超短間距

        beats_arr = np.array(beats)
        beat_validation = {"status": "PASS", "warnings": []}

        measure_map, status, warnings = node.build_measure_map(beats_arr, beat_validation, {})

        # 不應有 beat_count == 1 的 ghost 小節
        ghost_measures = [m for m in measure_map if m.get("beat_count", 4) == 1]
        assert len(ghost_measures) == 0, f"仍有 {len(ghost_measures)} 個 ghost 1-beat 小節存在！"
