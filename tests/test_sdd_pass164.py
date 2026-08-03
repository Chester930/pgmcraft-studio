"""
SDD Pass 164 — 升級 GridConstrainedChordNode 支援半小節（2拍）動態雙和弦對齊平滑

背景：
流行樂曲目中經常存在每半個小節（2 拍）切換一次和弦的樂理進行（例如前半小節 C、後半小節 G）。原有的 GridConstrainedChordNode 採取全小節單一多數決，會將後半小節和弦強制抹平。

本測試驗證：
1. 單一和弦的小節能正確平滑為全小節和弦事件（sub_bar: 0）。
2. 包含半小節和弦切換的小節（例如前半小節 C、後半小節 G），機能正確拆分為 2 個半小節和弦事件（sub_bar: 1, sub_bar: 2）。
"""

import pytest

from pgm_craft.workflow.music_analysis_bt import GridConstrainedChordNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass164:

    def test_single_chord_measure_merges_to_full_bar(self):
        bb = Blackboard()
        measure_map = [
            {"measure": 1, "start_time": 0.0, "end_time": 2.0}
        ]
        chords = [
            {"start_time": 0.0, "end_time": 1.0, "chord": "C Major"},
            {"start_time": 1.0, "end_time": 2.0, "chord": "C Major"}
        ]
        bb.set_val("measure_map", measure_map)
        bb.set_val("chord_progression", chords)

        node = GridConstrainedChordNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        res = bb.get_val("grid_constrained_chords")
        assert len(res) == 1
        assert res[0]["chord"] == "C Major"
        assert res[0]["sub_bar"] == 0

    def test_dual_chord_measure_splits_into_half_bars(self):
        bb = Blackboard()
        measure_map = [
            {"measure": 1, "start_time": 0.0, "end_time": 2.0}
        ]
        chords = [
            {"start_time": 0.0, "end_time": 0.9, "chord": "C Major"},
            {"start_time": 1.1, "end_time": 2.0, "chord": "G Major"}
        ]
        bb.set_val("measure_map", measure_map)
        bb.set_val("chord_progression", chords)

        node = GridConstrainedChordNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        res = bb.get_val("grid_constrained_chords")
        assert len(res) == 2
        assert res[0]["chord"] == "C Major"
        assert res[0]["sub_bar"] == 1
        assert res[1]["chord"] == "G Major"
        assert res[1]["sub_bar"] == 2
