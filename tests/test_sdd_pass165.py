"""
SDD Pass 165 — 升級 DownbeatAlignedSectionNode 樂段小節號雙向對齊與 Safe Fallback 驗證

背景：
在 Pass 165 中升級 DownbeatAlignedSectionNode：
1. 將樂段對齊至 measure_map 的 Downbeat 時間點時，同步更新 sec["measure"] 為對應的小節號，確保 DAW 導出（MIDI Markers / CSV）拿到 100% 雙向一致的對齊資料。
2. 當 sections 為空時，自動建立全曲 Main 樂段 Safe Fallback。

本測試驗證：
1. DownbeatAlignedSectionNode 能正確將樂段 start_time 與 measure 小節號同步。
2. sections 為空時，Safe Fallback 能正確產生全曲 Main 樂段並完成對齊。
"""

import pytest

from pgm_craft.workflow.music_analysis_bt import DownbeatAlignedSectionNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass165:

    def test_section_alignment_syncs_measure_number(self):
        bb = Blackboard()
        measure_map = [
            {"measure": 1, "start_time": 0.0, "end_time": 2.0},
            {"measure": 2, "start_time": 2.0, "end_time": 4.0},
            {"measure": 3, "start_time": 4.0, "end_time": 6.0},
        ]
        # 模擬未對齊的 sections（start_time 落在 2.1 秒，接近 measure 2）
        sections = [
            {"name": "Intro", "start_time": 0.0, "end_time": 2.1, "measure": 1},
            {"name": "Verse", "start_time": 2.1, "end_time": 6.0, "measure": 1},
        ]
        bb.set_val("measure_map", measure_map)
        bb.set_val("sections", sections)

        node = DownbeatAlignedSectionNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        aligned = bb.get_val("sections")
        assert len(aligned) == 2
        assert aligned[1]["start_time"] == 2.0
        assert aligned[1]["measure"] == 2  # 應自動同步為小節 2

    def test_empty_sections_safe_fallback(self):
        bb = Blackboard()
        measure_map = [
            {"measure": 1, "start_time": 0.0, "end_time": 2.0},
            {"measure": 2, "start_time": 2.0, "end_time": 4.0},
        ]
        bb.set_val("measure_map", measure_map)
        bb.set_val("sections", [])  # 空 sections

        node = DownbeatAlignedSectionNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        aligned = bb.get_val("sections")
        assert len(aligned) == 1
        assert aligned[0]["name"] == "Main"
        assert aligned[0]["measure"] == 1
