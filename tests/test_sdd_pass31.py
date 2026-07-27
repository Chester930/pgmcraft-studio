import unittest
import os
import shutil
import tempfile
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.builder import BTWorkflowEngine

class TestSDDPass31(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = "sample_test.wav"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_bt_engine_target_stage_truncation_stage3(self):
        """驗證傳入 target_stage='stage3' 時，BT 樹僅執行至 Stage 3」"""
        engine = BTWorkflowEngine()
        result_bb = engine.run(
            audio_path=self.audio_path,
            output_dir=self.test_dir,
            target_stage="stage3"
        )
        self.assertEqual(result_bb.get_val("workflow_status"), "SUCCESS")
        
        # Stage 3 的 beats 必須存在
        self.assertIsNotNone(result_bb.get_val("beats"))
        
        # Stage 4 的 grid_constrained_chords 與 Stage 5 的 click_track 應為 None (因為被短路截斷)
        self.assertIsNone(result_bb.get_val("grid_constrained_chords"))
        self.assertIsNone(result_bb.get_val("click_track"))

    def test_bt_engine_target_stage_truncation_stage4(self):
        """驗證傳入 target_stage='stage4' 時，BT 樹執行至 Stage 4」"""
        engine = BTWorkflowEngine()
        result_bb = engine.run(
            audio_path=self.audio_path,
            output_dir=self.test_dir,
            enable_stem=True,
            target_stage="stage4"
        )
        self.assertEqual(result_bb.get_val("workflow_status"), "SUCCESS")
        
        # Stage 4 的 estimated_key 必須存在
        self.assertIsNotNone(result_bb.get_val("estimated_key"))
        
        # Stage 5 的 click_track 應為 None
        self.assertIsNone(result_bb.get_val("click_track"))

if __name__ == "__main__":
    unittest.main()
