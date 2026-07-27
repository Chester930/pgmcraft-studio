"""
SDD Pass 97 — app.py 一鍵全自動模式整合需求驅動智慧分流 (FullAutoDemixingBTEngine) 測試
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import soundfile as sf
from app import process_full_auto_pgm


class TestSDDPass97AppFullAutoIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = os.path.join(self.temp_dir, "app_auto_test.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * 440 * t)
        sf.write(self.test_wav, y, sr)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_process_full_auto_pgm_signature_and_execution(self):
        """驗證 process_full_auto_pgm 能接受 enable_smart_demix 參數並正常執行」"""
        res = process_full_auto_pgm(
            url_input=None,
            audio_file=self.test_wav,
            custom_output_dir=self.temp_dir,
            enable_smart_demix=True
        )
        self.assertIsInstance(res, tuple)


if __name__ == "__main__":
    unittest.main()
