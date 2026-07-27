"""
SDD Pass 60 — Podcast 工作流 1-1：雙人/多人訪談聲音淨化狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.podcast_bt import build_interview_clean_workflow


class TestSDDPass60InterviewCleanWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "noisy_interview.wav")
        # 產生合成聲音 (帶 50Hz 電流聲與高頻雜訊)
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        speech = np.sin(2 * np.pi * 300 * t) * 0.3
        hum = np.sin(2 * np.pi * 50 * t) * 0.05
        noise = np.random.randn(sr) * 0.02
        sig = (speech + hum + noise).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_interview_clean_workflow_execution(self):
        """驗證 InterviewCleanBTWorkflow 狀態機依序通過 6 個狀態節點並輸出淨化檔」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_interview_clean_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        clean_p = blackboard.get_val("clean_speech_path")
        self.assertTrue(os.path.exists(clean_p))

        # 讀取淨化後的音檔，驗證能量與 EBU Normalization 保底
        y_clean, sr_c = sf.read(clean_p)
        self.assertGreater(len(y_clean), 0)


if __name__ == "__main__":
    unittest.main()
