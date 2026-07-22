import unittest
import os
import shutil
import tempfile
from pgm_craft.workflow.nodes import SequenceNode, FallbackNode, Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import VideoURLDownloadNode, AudioLoadNode, BeatNetNode, LibrosaBeatNode
from pgm_craft.workflow.builder import BTWorkflowEngine

class TestBTWorkflowEngine(unittest.TestCase):
    def setUp(self):
        self.test_audio = "sample_test.wav"
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_video_url_download_node_local_skip(self):
        """測試 VideoURLDownloadNode：輸入為本地檔案時自動 PASS 並跳過下載」"""
        node = VideoURLDownloadNode()
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.test_audio)
        status = node.execute(blackboard)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("audio_path"), self.test_audio)

    def test_bt_fallback_selector(self):
        """測試 BT Selector/Fallback 控制節點：當第一個失敗時自動降級跑第二個"""
        fallback_node = FallbackNode("BeatTrackingSelector", [
            BeatNetNode(),
            LibrosaBeatNode()
        ])
        
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.test_audio)
        blackboard.set_val("target_analysis_path", self.test_audio)

        status = fallback_node.execute(blackboard)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertIsNotNone(blackboard.get_val("beats"))

    def test_bt_engine_full_run(self):
        """測試 BT 引擎完整行為樹節點執行流水線 (包含 VideoURLDownloadNode 進入點)"""
        bt_engine = BTWorkflowEngine()
        blackboard = bt_engine.run(self.test_audio, output_dir=self.temp_dir, enable_stem=False)

        self.assertIsNotNone(blackboard.get_val("beats"))
        self.assertIsNotNone(blackboard.get_val("estimated_key"))
        self.assertTrue(os.path.exists(blackboard.get_val("click_track")))
        self.assertTrue(os.path.exists(blackboard.get_val("tempo_map_midi")))

if __name__ == '__main__':
    unittest.main()
