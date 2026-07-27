"""
SDD Pass 78 — ASMR 工作流 6-2：ASMR 口腔濕潤音與唇齒音極致剝離狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.asmr_bt import build_asmr_mouth_click_removal_workflow


class TestSDDPass78ASMRMouthClickRemovalWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "asmr_click.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 300 * t) * 0.4).astype(np.float32)
        # 加上微秒點擊音 Spike
        sig[sr // 2] = 0.95
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_asmr_mouth_click_removal_execution(self):
        """驗證 ASMRMouthClickRemovalRoot 狀態機成功壓制 Mouth Click 並落盤」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_asmr_mouth_click_removal_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        mc_clean_p = blackboard.get_val("asmr_mouth_click_clean_path")

        self.assertTrue(os.path.exists(mc_clean_p))


if __name__ == "__main__":
    unittest.main()
