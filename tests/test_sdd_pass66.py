"""
SDD Pass 66 — Vocal 工作流 3-1：經典純伴奏製作狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.vocal_bt import build_vocal_pure_inst_workflow


class TestSDDPass66VocalPureInstWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "sample_song.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.3).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_vocal_pure_inst_workflow_execution(self):
        """驗證 VocalPureInstRoot 狀態機成功提取純伴奏與落盤」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_vocal_pure_inst_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        inst_p = blackboard.get_val("pure_inst_path")

        self.assertTrue(os.path.exists(inst_p))
        y_inst, sr_i = sf.read(inst_p)
        self.assertGreater(len(y_inst), 0)


if __name__ == "__main__":
    unittest.main()
