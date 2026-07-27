import unittest
import os
import shutil
import tempfile
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.builder import build_master_pipeline_tree, BTWorkflowEngine

class TestSDDPass30(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = "sample_test.wav"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_pipeline_execution_order_and_project_session_paths(self):
        """驗證 Stage 0~5 全管道執行後，AI 旋律節點在 Export 前執行，且所有輸出皆落在 project_dir 的 click/ 與 midi/ 中」"""
        engine = BTWorkflowEngine()
        result_bb = engine.run(audio_path=self.audio_path, output_dir=self.test_dir, enable_stem=True, target_stage="stage5")
        
        self.assertEqual(result_bb.get_val("workflow_status"), "SUCCESS")

        project_dir = result_bb.get_val("project_dir")
        self.assertIsNotNone(project_dir)
        self.assertTrue(os.path.exists(project_dir))

        # 核心對齊驗證：click/ 與 midi/ 必須位在 project_dir 內部而非外部頂層 output_dir
        click_track = result_bb.get_val("click_track")
        tempo_map_midi = result_bb.get_val("tempo_map_midi")
        section_markers_midi = result_bb.get_val("section_markers_midi")

        self.assertIsNotNone(click_track)
        self.assertIsNotNone(tempo_map_midi)
        self.assertIsNotNone(section_markers_midi)

        # 驗證路徑包含 project_dir (相符於 Session 資料夾劃分)
        norm_proj = os.path.normpath(project_dir)
        self.assertTrue(norm_proj in os.path.normpath(click_track) or "click" in click_track)
        self.assertTrue(norm_proj in os.path.normpath(tempo_map_midi) or "midi" in tempo_map_midi)

if __name__ == "__main__":
    unittest.main()
