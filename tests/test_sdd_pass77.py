"""
SDD Pass 77 — ASMR 工作流 6-1：ASMR 高頻底噪與電流聲淨化狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.asmr_bt import build_asmr_hiss_clean_workflow


class TestSDDPass77ASMRHissCleanWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "asmr_whisper.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        # 440Hz 訊號 + 13000Hz 刺耳 Hiss 白雜訊
        sig = (np.sin(2 * np.pi * 440 * t) * 0.3 + np.sin(2 * np.pi * 13000 * t) * 0.2).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_asmr_hiss_clean_execution(self):
        """驗證 ASMRHissCleanRoot 狀態機成功淨化並落盤 ASMR_Hiss_Cleaned.wav」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_asmr_hiss_clean_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        clean_p = blackboard.get_val("asmr_clean_path")

        self.assertTrue(os.path.exists(clean_p))


if __name__ == "__main__":
    unittest.main()
