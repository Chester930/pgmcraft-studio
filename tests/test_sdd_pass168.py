"""
SDD Pass 168 — 雙向確定錨點跳過與拍位反推節點 (TwoWayAnchorBacktraceNode) 驗證

背景：
在切分音 (Push/Pull Syncopation) 或前奏/間奏段落中，舊邏輯易將切分搶拍 (如 4& 拍) 誤判為第 1 拍 (Downbeat)，造成 185+ BPM 或 140 BPM 的時間步距發散。
Pass 168 透過 TwoWayAnchorBacktraceNode，讀取實體 kick_anchors / snare_anchors，跳過不確定的切分音，從前後確信的 Downbeat 錨點向後/向前反推，導回正確的第 1 拍時間點。

本測試驗證：
1. 當小節序列中出現切分搶拍 (1.28s) 造成間距突變時，TwoWayAnchorBacktraceNode 能正確識別並從下一個確信錨點反推出正確的 Downbeat。
2. 反推後的小節間距恢復平滑中位數步距。
"""

import pytest
import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import TwoWayAnchorBacktraceNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass168:

    def test_twoway_backtrace_fixes_syncopated_anticipation(self):
        bb = Blackboard()
        normal_step = 1.45
        t0 = 0.405
        bars = [t0 + i * normal_step for i in range(10)]
        
        # 模擬在第 7 個小節出現切分搶拍 (變為 1.28s 搶拍)
        syncopated_bar = bars[6] - 0.25
        bars_with_syncopation = bars[:6] + [syncopated_bar] + bars[7:]

        bb.set_val("committed_bar_starts", bars_with_syncopation)
        bb.set_val("kick_anchors", [{"time": bars[0]}, {"time": bars[9]}])

        node = TwoWayAnchorBacktraceNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("twoway_backtrace_report", {})
        assert report.get("corrections", 0) >= 1

        fixed_bars = bb.get_val("committed_bar_starts", [])
        fixed_times = [b.get("time") if isinstance(b, dict) else float(b) for b in fixed_bars]

        # 驗證修正後的第 6 個小節時間點恢復到接近標準步距
        assert abs(fixed_times[6] - bars[6]) < 0.08
