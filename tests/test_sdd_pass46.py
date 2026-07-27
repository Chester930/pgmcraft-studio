import unittest
import os
import shutil
import tempfile
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.music_analysis_bt import build_music_analysis_tree, MusicAnalysisBTEngine

class TestSDDPass46(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = "sample_test.wav"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_music_analysis_tree_contains_new_nodes(self):
        """驗證 build_music_analysis_tree 成功掛載 Pass 43~45 新衛兵」"""
        tree = build_music_analysis_tree()
        node_names = [n.name for n in tree.children]
        
        self.assertIn("HarmonicSilenceGateNode", node_names)
        self.assertIn("DownbeatAlignedSectionNode", node_names)
        self.assertIn("MultiBandChromaKeyNode", node_names)

    def test_stage4_music_analysis_bt_engine_run_success(self):
        """驗證 MusicAnalysisBTEngine 完整執行 SUCCESS」"""
        import numpy as np
        engine = MusicAnalysisBTEngine()
        bb = Blackboard()
        bb.set_val("audio_path", self.audio_path)
        bb.set_val("output_dir", self.test_dir)
        bb.set_val("harmonic_track_path", self.audio_path)
        bb.set_val("structure_track_path", self.audio_path)
        bb.set_val("beats", np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.0, 1]]))
        
        result_bb = engine.run(bb)
        self.assertEqual(result_bb.get_val("workflow_status"), "SUCCESS")
        self.assertIsNotNone(result_bb.get_val("estimated_key"))

if __name__ == "__main__":
    unittest.main()
