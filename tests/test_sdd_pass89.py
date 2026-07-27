"""
SDD Pass 89 — 曲首 1-2 小節預備拍 (Count-In) 與語音倒數合成單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.export_bt import CountInSynthesizerNode


class TestSDDPass89CountInSynthesizer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sr = 22050
        duration = 2.0
        t = np.linspace(0, duration, int(self.sr * duration), False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        self.audio_path = os.path.join(self.test_dir, "test_audio.wav")
        sf.write(self.audio_path, sig, self.sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_countin_synthesizer_execution(self):
        """驗證 CountInSynthesizerNode 成功導出帶有預備拍之 click_with_countin.wav"""
        blackboard = Blackboard()
        blackboard.set_val("sr", self.sr)
        blackboard.set_val("output_dir", self.test_dir)
        blackboard.set_val("beats", np.array([[0.0, 1], [0.5, 0], [1.0, 0], [1.5, 0]]))
        blackboard.set_val("click_audio", np.sin(2 * np.pi * 800 * np.linspace(0, 1.0, self.sr)))

        node = CountInSynthesizerNode(count_in_bars=1)
        status = node.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        out_p = blackboard.get_val("click_with_countin_path")
        offset = blackboard.get_val("countin_offset_sec")

        self.assertIsNotNone(out_p)
        self.assertTrue(os.path.exists(out_p))
        self.assertGreater(offset, 0.0)


if __name__ == "__main__":
    unittest.main()
