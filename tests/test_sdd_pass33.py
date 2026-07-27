import unittest
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.export_bt import VoiceCueSynthesisNode

class TestSDDPass33(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        self.blackboard.set_val("output_dir", self.test_dir)
        self.blackboard.set_val("sections", [
            {"measure": 1, "name": "Intro", "start_time": 0.0, "end_time": 4.0},
            {"measure": 5, "name": "Chorus", "start_time": 4.0, "end_time": 8.0}
        ])
        self.blackboard.set_val("measure_map", [
            {"measure": 1, "start_time": 0.0, "end_time": 1.0},
            {"measure": 2, "start_time": 1.0, "end_time": 2.0},
            {"measure": 3, "start_time": 2.0, "end_time": 3.0},
            {"measure": 4, "start_time": 3.0, "end_time": 4.0},
            {"measure": 5, "start_time": 4.0, "end_time": 5.0},
        ])

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_voice_cue_synthesis_node_standalone(self):
        """驗證 VoiceCueSynthesisNode 能正確合成 voice_cue_guide.wav 並寫入 outputs 契約」"""
        node = VoiceCueSynthesisNode()
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        outputs = self.blackboard.get_val("outputs", {})
        self.assertIn("voice_cue_guide", outputs)
        
        cue_path = outputs["voice_cue_guide"]
        self.assertTrue(os.path.exists(cue_path))
        
        # 驗證產出的音訊檔能被正常讀取且非空
        data, sr = sf.read(cue_path)
        self.assertGreater(len(data), 0)
        self.assertEqual(sr, 44100)

if __name__ == "__main__":
    unittest.main()
