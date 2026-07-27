"""
SDD Pass 84 — 靜音段 Noise Floor 自適應動態門限調諧單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.audio_quality_bt import NoiseFloorAnalyzerNode


class TestSDDPass84NoiseFloorAnalyzer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "noisy_audio.wav")
        sr = 22050
        t = np.linspace(0, 0.5, sr // 2, False)
        # 背景低底噪訊號
        sig = (np.sin(2 * np.pi * 440 * t) * 0.4 + np.random.normal(0, 0.01, len(t))).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_noise_floor_analyzer_execution(self):
        """驗證 NoiseFloorAnalyzerNode 正確導出 noise_floor_db 與 adaptive_denoise_threshold」"""
        blackboard = Blackboard()
        y, sr = sf.read(self.audio_path)
        blackboard.set_val("y", y)
        blackboard.set_val("sr", sr)

        node = NoiseFloorAnalyzerNode()
        status = node.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        noise_db = blackboard.get_val("noise_floor_db")
        thresh = blackboard.get_val("adaptive_denoise_threshold")

        self.assertIsNotNone(noise_db)
        self.assertIsNotNone(thresh)
        self.assertGreater(thresh, 0.0)


if __name__ == "__main__":
    unittest.main()
