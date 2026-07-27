"""
SDD Pass 68 — Vocal 工作流 3-3：主唱與和聲雙軌獨立分離狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.vocal_bt import build_vocal_lead_backing_split_workflow


class TestSDDPass68LeadBackingSplitWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "sample_vocal_song.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.3).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_vocal_lead_backing_split_execution(self):
        """驗證 VocalLeadBackingSplitRoot 狀態機成功拆解主唱與和聲軌」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_vocal_lead_backing_split_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        lead_p = blackboard.get_val("lead_vocal_path")
        back_v_p = blackboard.get_val("backing_vocal_path")

        self.assertTrue(os.path.exists(lead_p))
        self.assertTrue(os.path.exists(back_v_p))


if __name__ == "__main__":
    unittest.main()
