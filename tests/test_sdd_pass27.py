import unittest
import os
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.music_analysis_bt import (
    SynthesizeHarmonicTrackNode,
    GridConstrainedChordNode,
    build_music_analysis_tree,
    MusicAnalysisBTEngine
)
from pgm_craft.workflow.audio_nodes import SectionStructureNode, MeasureMapNode

class TestSDDPass27(unittest.TestCase):
    def setUp(self):
        self.chords = [
            {"measure": 1, "start_time": 0.0, "end_time": 1.0, "chord": "C"},
            {"measure": 1, "start_time": 1.0, "end_time": 2.0, "chord": "C"},
            # 小節 2：前半段只有 G、後半段只有 Am，測試 Pass 164 半小節（2 拍）
            # 動態雙和弦拆分——前後半和弦明確不同時應拆成 2 個 sub_bar 事件。
            {"measure": 2, "start_time": 2.0, "end_time": 3.0, "chord": "G"},
            {"measure": 2, "start_time": 3.0, "end_time": 4.0, "chord": "Am"},
        ]
        self.measure_map = [
            {"measure": 1, "start_time": 0.0, "end_time": 2.0, "time_signature": "4/4"},
            {"measure": 2, "start_time": 2.0, "end_time": 4.0, "time_signature": "4/4"},
            {"measure": 3, "start_time": 4.0, "end_time": 6.0, "time_signature": "4/4"},
            {"measure": 4, "start_time": 6.0, "end_time": 8.0, "time_signature": "4/4"}
        ]

    def test_bt_node_execution_order_and_measure_map_dependency(self):
        """驗證 Stage 4 BT 執行順序已修正，SectionStructureNode 能正確拿到 measure_map"""
        bb = Blackboard()
        bb.set_val("audio_path", "sample_test.wav")
        beats = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4],
            [2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4],
            [4.0, 1], [4.5, 2], [5.0, 3], [5.5, 4],
            [6.0, 1], [6.5, 2], [7.0, 3], [7.5, 4],
        ])
        bb.set_val("beats", beats)
        bb.set_val("beat_validation", {"status": "PASS"})

        tree = build_music_analysis_tree()
        status = tree.run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        # 核心驗證：measure_map 不得為空，且 sections 成功衍生
        m_map = bb.get_val("measure_map")
        sections = bb.get_val("sections")
        self.assertIsNotNone(m_map)
        self.assertGreater(len(m_map), 0)
        self.assertIsNotNone(sections)
        self.assertGreater(len(sections), 0)

    def test_grid_constrained_chord_smoothing_with_measure_map(self):
        """驗證 GridConstrainedChordNode 結合 measure_map 執行小節平滑化，
        以及 Pass 164 加入的半小節（2 拍）動態雙和弦拆分。"""
        bb = Blackboard()
        bb.set_val("chord_progression", self.chords)
        bb.set_val("measure_map", self.measure_map)

        node = GridConstrainedChordNode()
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        grid_chords = bb.get_val("grid_constrained_chords")
        self.assertIsNotNone(grid_chords)

        # 小節 1：前後半都是 C，應合併為 1 個全小節和弦事件 (sub_bar=0)。
        measure_1 = [c for c in grid_chords if c["measure"] == 1]
        self.assertEqual(len(measure_1), 1)
        self.assertEqual(measure_1[0]["sub_bar"], 0)
        self.assertEqual(measure_1[0]["chord"], "C")

        # 小節 2：前半 G、後半 Am，明確不同，應拆成 2 個半小節和弦事件。
        measure_2 = sorted(
            (c for c in grid_chords if c["measure"] == 2),
            key=lambda c: c["sub_bar"],
        )
        self.assertEqual(len(measure_2), 2)
        self.assertEqual(measure_2[0]["sub_bar"], 1)
        self.assertEqual(measure_2[0]["chord"], "G")
        self.assertEqual(measure_2[1]["sub_bar"], 2)
        self.assertEqual(measure_2[1]["chord"], "Am")

    def test_harmonic_track_node_tier2_support(self):
        """驗證 SynthesizeHarmonicTrackNode 支援 strings/organ 等 Tier-2 和聲樂器"""
        node = SynthesizeHarmonicTrackNode()
        self.assertIn("organ", node.harmonic_stems_whitelist)
        self.assertIn("strings", node.harmonic_stems_whitelist)

if __name__ == "__main__":
    unittest.main()
