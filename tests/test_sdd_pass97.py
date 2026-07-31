"""
SDD Pass 97 — app.py 一鍵全自動模式整合測試（原本涵蓋 FullAutoDemixingBTEngine 智慧分流
預跑步驟，該步驟已於後續稽核中確認結果從未被使用、且用寫死假樂器機率取代真實偵測，因此
被移除；本測試改為驗證 process_full_auto_pgm 本身仍能正常執行）。
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
        """驗證 process_full_auto_pgm 能正常執行並回傳 process_pgm 的完整輸出 tuple。"""
        res = process_full_auto_pgm(
            url_input=None,
            audio_file=self.test_wav,
            custom_output_dir=self.temp_dir,
        )
        self.assertIsInstance(res, tuple)


if __name__ == "__main__":
    unittest.main()
