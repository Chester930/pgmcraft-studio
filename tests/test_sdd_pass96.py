"""
SDD Pass 96 — Blackboard get_audio_hash mtime 快取效能優化單元測試
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, _AUDIO_HASH_CACHE


class TestSDDPass96AudioHashCache(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = os.path.join(self.temp_dir, "hash_test.wav")
        sr = 22050
        t = np.linspace(0, 0.5, sr // 2, endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * 440 * t)
        sf.write(self.test_wav, y, sr)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_audio_hash_mtime_caching(self):
        """驗證不同 Blackboard 實例對同一個未修改檔能重用全域 mtime 快取，無須重複全檔讀取"""
        bb1 = Blackboard()
        bb1.set_val("audio_path", self.test_wav)
        h1 = bb1.get_audio_hash()

        self.assertIsNotNone(h1)
        self.assertNotEqual(h1, "default_hash")

        # 驗證快取中存在此項
        stat = os.stat(self.test_wav)
        cache_key = (os.path.abspath(self.test_wav), stat.st_mtime, stat.st_size)
        self.assertIn(cache_key, _AUDIO_HASH_CACHE)

        # 建立第二個全新的 Blackboard
        bb2 = Blackboard()
        bb2.set_val("audio_path", self.test_wav)
        h2 = bb2.get_audio_hash()

        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
