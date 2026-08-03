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
