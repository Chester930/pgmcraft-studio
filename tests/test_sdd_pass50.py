"""
SDD Pass 50 — 二階音色細分的動態顯著度早停 (Presence Early Exit Guard) 單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.separator import CascadedStemSeparator


class TestSDDPass50PresenceEarlyExit(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.silent_wav_path = os.path.join(self.test_dir, "silent_track.wav")
        # 產生近全靜音 1 秒音訊 (RMS < 0.001)
        sr = 22050
        y_silent = np.zeros(sr, dtype=np.float32)
        sf.write(self.silent_wav_path, y_silent, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_drums_substem_presence_early_exit(self):
        """驗證無鼓靜音軌觸發 Presence Early Exit 早停」"""
        separator = CascadedStemSeparator()
        sub_dir = os.path.join(self.test_dir, "drums_sub")
        k_path, s_path, h_path = separator.separate_drums_substem(
            self.silent_wav_path, sub_dir, is_already_drums=True
        )
        self.assertTrue(os.path.exists(k_path))
        self.assertTrue(os.path.exists(s_path))
        self.assertTrue(os.path.exists(h_path))

    def test_bass_substem_presence_early_exit(self):
        """驗證無貝斯靜音軌觸發 Presence Early Exit 早停」"""
        separator = CascadedStemSeparator()
        sub_dir = os.path.join(self.test_dir, "bass_sub")
        eb_path, sb_path = separator.separate_synth_and_electric_bass(
            self.silent_wav_path, sub_dir, is_already_bass=True
        )
        self.assertTrue(os.path.exists(eb_path))
        self.assertTrue(os.path.exists(sb_path))


if __name__ == "__main__":
    unittest.main()
