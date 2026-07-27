"""
SDD Pass 67 — Vocal 工作流 3-2：帶和聲伴奏製作狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.vocal_bt import build_vocal_backing_inst_workflow


class TestSDDPass67VocalBackingInstWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "sample_song_harmony.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 523 * t) * 0.3).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_vocal_backing_inst_workflow_execution(self):
        """驗證 VocalBackingInstRoot 狀態機成功提取帶和聲伴奏與落盤」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_vocal_backing_inst_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        back_p = blackboard.get_val("backing_inst_path")

        self.assertTrue(os.path.exists(back_p))
        y_b, sr_b = sf.read(back_p)
        self.assertGreater(len(y_b), 0)


if __name__ == "__main__":
    unittest.main()
