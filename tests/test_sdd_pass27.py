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
            {"measure": 2, "start_time": 2.0, "end_time": 3.0, "chord": "G"},
            {"measure": 2, "start_time": 3.0, "end_time": 4.0, "chord": "Am"}, # 碎裂和弦測試
            {"measure": 2, "start_time": 3.5, "end_time": 4.0, "chord": "G"}
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
        """驗證 GridConstrainedChordNode 結合 measure_map 執行小節平滑化"""
        bb = Blackboard()
        bb.set_val("chord_progression", self.chords)
        bb.set_val("measure_map", self.measure_map)

        node = GridConstrainedChordNode()
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        grid_chords = bb.get_val("grid_constrained_chords")
        self.assertIsNotNone(grid_chords)
        self.assertEqual(len(grid_chords), 4)
        # 小節 2 的碎裂和弦應被平滑化為 G 和弦 (多數決)
        self.assertEqual(grid_chords[1]["chord"], "G")

    def test_harmonic_track_node_tier2_support(self):
        """驗證 SynthesizeHarmonicTrackNode 支援 strings/organ 等 Tier-2 和聲樂器"""
        node = SynthesizeHarmonicTrackNode()
        self.assertIn("organ", node.harmonic_stems_whitelist)
        self.assertIn("strings", node.harmonic_stems_whitelist)

if __name__ == "__main__":
    unittest.main()
