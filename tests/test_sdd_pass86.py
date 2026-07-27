"""
SDD Pass 86 — 純音樂伴奏 + Click 導出檔 (backing_with_click.wav) 單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.export_bt import BackingWithClickSynthesizerNode


class TestSDDPass86BackingWithClickSynthesizer(unittest.TestCase):

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

    def test_backing_with_click_synthesis(self):
        """驗證 BackingWithClickSynthesizerNode 成功導出 backing_with_click.wav」"""
        blackboard = Blackboard()
        y, sr = sf.read(self.audio_path)
        blackboard.set_val("y", y)
        blackboard.set_val("sr", sr)
        blackboard.set_val("output_dir", self.test_dir)
        blackboard.set_val("click_audio", y * 0.8)
        blackboard.set_val("stems", {"drums": y * 0.3, "bass": y * 0.3, "other": y * 0.3})

        node = BackingWithClickSynthesizerNode()
        status = node.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        out_p = blackboard.get_val("backing_with_click_path")
        self.assertIsNotNone(out_p)
        self.assertTrue(os.path.exists(out_p))


if __name__ == "__main__":
    unittest.main()
