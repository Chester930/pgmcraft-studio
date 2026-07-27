"""
SDD Pass 61 — Podcast 工作流 1-2：播客音量 EBU R128 自動標準化與防剪峰狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.podcast_bt import build_podcast_r128_normalize_workflow


class TestSDDPass61PodcastR128Workflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "quiet_podcast.wav")
        # 產生極小音量的正弦聲波 (LUFS 遠低於 -16)
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.01).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_podcast_r128_normalize_execution(self):
        """驗證 PodcastR128NormalizeRoot 狀態機成功標準化音量」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_podcast_r128_normalize_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        master_p = blackboard.get_val("mastered_speech_path")
        self.assertTrue(os.path.exists(master_p))

        # 讀取並驗證 Peak 不超過 1.0 且音量增益正常
        y_master, sr_m = sf.read(master_p)
        max_peak = np.max(np.abs(y_master))
        self.assertLessEqual(max_peak, 1.0)
        self.assertGreater(max_peak, 0.05)


if __name__ == "__main__":
    unittest.main()
