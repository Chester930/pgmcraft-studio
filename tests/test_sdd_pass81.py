"""
SDD Pass 81 — 節點級聲學快取與中間態重用機制單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard


class TestSDDPass81BlackboardCacheLayer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "test_audio.wav")
        sr = 22050
        t = np.linspace(0, 0.5, sr // 2, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        if os.path.exists("cache"):
            shutil.rmtree("cache", ignore_errors=True)

    def test_audio_hash_calculation(self):
        """驗證 Blackboard 正確計算同音檔 SHA256 Hash 值」"""
        bb1 = Blackboard()
        bb1.set_val("audio_path", self.audio_path)
        h1 = bb1.get_audio_hash()

        bb2 = Blackboard()
        bb2.set_val("audio_path", self.audio_path)
        h2 = bb2.get_audio_hash()

        self.assertEqual(len(h1), 16)
        self.assertEqual(h1, h2)

    def test_cache_miss_and_hit(self):
        """驗證 Blackboard set_cached_artifact 與 get_cached_artifact 快取讀寫」"""
        bb = Blackboard()
        bb.set_val("audio_path", self.audio_path)

        # 1. 尚未寫入快取，Cache Miss
        cached_data = bb.get_cached_artifact("beat_analysis")
        self.assertIsNone(cached_data)

        # 2. 寫入快取
        sample_beats = {"bpm": 120.0, "beats": [0.0, 0.5, 1.0]}
        bb.set_cached_artifact("beat_analysis", sample_beats)

        # 3. 再次讀取快取，Cache Hit
        cached_data = bb.get_cached_artifact("beat_analysis")
        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data["bpm"], 120.0)


if __name__ == "__main__":
    unittest.main()
