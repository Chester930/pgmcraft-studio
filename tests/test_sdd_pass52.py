"""
SDD Pass 52 — PeelCoreTrio 門檻升級 (0.20) 與早停防護測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.separator import PeelCoreTrioStemSeparator


class TestSDDPass52PeelCoreTrioThreshold(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.weak_wav_path = os.path.join(self.test_dir, "weak_signal.wav")
        # 產生極微弱聲音 (Probe 分數將低於 0.20)
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.005).astype(np.float32)
        sf.write(self.weak_wav_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_peel_trio_loop_early_exit_on_low_score(self):
        """驗證當顯著度得分 < 0.20 時，PeelCoreTrio 立即早停不產出空殘軌」"""
        separator = PeelCoreTrioStemSeparator()
        stems_dir = os.path.join(self.test_dir, "stems")
        res = separator.run_peel_trio_loop(self.weak_wav_path, stems_dir, min_threshold=0.20)

        # 顯著度低於 0.20 應早停，不產生任何核心樂器音軌檔
        self.assertNotIn("guitar", res)
        self.assertNotIn("piano", res)
        self.assertNotIn("strings", res)


if __name__ == "__main__":
    unittest.main()
