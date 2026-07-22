import unittest
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
from pgm_craft.enhancer import AudioEnhancerEngine

class TestAudioEnhancerEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = os.path.join(self.temp_dir, "test_input.wav")
        # 產生 1 秒 Sine 波微弱音訊
        sr = 22050
        t = np.linspace(0, 1, sr, endpoint=False)
        y = 0.1 * np.sin(2 * np.pi * 440 * t)
        sf.write(self.test_wav, y, sr)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_audio_enhancement_and_normalization(self):
        """測試去噪、EBU R128 聲音響度放大與峰值限幅功能"""
        enhancer = AudioEnhancerEngine()
        out_wav = os.path.join(self.temp_dir, "test_output.wav")
        enhancer.enhance_audio_file(self.test_wav, out_wav, target_lufs=-14.0)

        self.assertTrue(os.path.exists(out_wav))
        y_out, sr_out = sf.read(out_wav)
        self.assertEqual(sr_out, 22050)
        # 驗證聲音振幅已被放大但未破音 (Peak Limit < 1.0)
        self.assertGreater(np.max(np.abs(y_out)), 0.2)
        self.assertLessEqual(np.max(np.abs(y_out)), 0.99)

if __name__ == '__main__':
    unittest.main()
