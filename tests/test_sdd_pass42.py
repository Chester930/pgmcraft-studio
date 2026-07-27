import unittest
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.beat_tracking_bt import build_beat_tracking_tree, BeatTrackingBTEngine

class TestSDDPass42(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = "sample_test.wav"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_beat_tracking_tree_contains_new_pass39_pass41_nodes(self):
        """驗證 build_beat_tracking_tree 成功掛載 KickSnarePulseNode 與 ReEntryReAnchoringNode」"""
        tree = build_beat_tracking_tree()
        node_names = [n.name for n in tree.children]
        
        self.assertIn("KickSnarePulseNode", node_names)
        self.assertIn("ReEntryReAnchoringNode", node_names)

    def test_stage3_beat_tracking_bt_engine_run_success(self):
        """驗證 BeatTrackingBTEngine 完整執行 SUCCESS」"""
        engine = BeatTrackingBTEngine()
        bb = Blackboard()
        bb.set_val("audio_path", self.audio_path)
        bb.set_val("output_dir", self.test_dir)
        bb.set_val("rhythm_track_path", self.audio_path)
        bb.set_val("inst_track_path", self.audio_path)
        
        result_bb = engine.run(bb)
        self.assertEqual(result_bb.get_val("workflow_status"), "SUCCESS")
        self.assertIsNotNone(result_bb.get_val("beats"))

if __name__ == "__main__":
    unittest.main()
