import unittest
import os
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.music_analysis_bt import (
    GridConstrainedChordNode,
    build_music_analysis_tree,
    MusicAnalysisBTEngine
)

class TestSDDPass26(unittest.TestCase):
    def setUp(self):
        self.chords = [
            {"measure": 1, "start_time": 0.0, "end_time": 2.0, "chord": "C"},
            {"measure": 2, "start_time": 2.0, "end_time": 4.0, "chord": "G"},
            {"measure": 3, "start_time": 4.0, "end_time": 6.0, "chord": "Am"},
            {"measure": 4, "start_time": 6.0, "end_time": 8.0, "chord": "F"}
        ]

    def test_grid_constrained_chord_node(self):
        """測試拍點格點和弦對齊與平滑化衛兵"""
        bb = Blackboard()
        bb.set_val("chord_progression", self.chords)

        node = GridConstrainedChordNode()
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

        grid_chords = bb.get_val("grid_constrained_chords")
        self.assertIsNotNone(grid_chords)
        self.assertEqual(len(grid_chords), 4)
        self.assertTrue(grid_chords[0]["is_grid_aligned"])

    def test_full_stage4_pass26_bt_engine(self):
        """測試包含 Pass 26 格點衛兵的 Stage 4 BT 完整樹鏈」"""
        bb = Blackboard()
        bb.set_val("audio_path", "sample_test.wav")
        beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.0, 1], [2.5, 2]])
        bb.set_val("beats", beats)
        bb.set_val("beat_validation", {"status": "PASS"})

        engine = MusicAnalysisBTEngine()
        result_bb = engine.run(bb)
        self.assertEqual(result_bb.get_val("music_analysis_status"), "SUCCESS")
        self.assertIsNotNone(result_bb.get_val("grid_constrained_chords"))

if __name__ == "__main__":
    unittest.main()
