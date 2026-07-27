"""
SDD Pass 80 — ASMR 工作流 6-4：ASMR 助眠極微音細節增益高亮狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.asmr_bt import build_asmr_subtle_mic_booster_workflow


class TestSDDPass80ASMRSubtleMicBoosterWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "asmr_subtle.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        # 極低音量小訊號 (Amplitude 0.05)
        sig = (np.sin(2 * np.pi * 500 * t) * 0.05).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_asmr_subtle_mic_booster_execution(self):
        """驗證 ASMRSubtleMicBoosterRoot 狀態機成功導出 ASMR_Booster_Enhanced.wav」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_asmr_subtle_mic_booster_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        boost_p = blackboard.get_val("asmr_booster_path")

        self.assertTrue(os.path.exists(boost_p))


if __name__ == "__main__":
    unittest.main()
