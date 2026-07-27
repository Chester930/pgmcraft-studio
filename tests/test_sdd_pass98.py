"""
SDD Pass 98 — ExportBT BackingWithClickSynthesizerNode 防禦性波形 Lazy Load 單元測試
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.export_bt import BackingWithClickSynthesizerNode


class TestSDDPass98BackingWithClickLazyLoad(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_wav = os.path.join(self.temp_dir, "backing_test.wav")
        sr = 22050
        t = np.linspace(0, 0.5, sr // 2, endpoint=False)
        y = 0.4 * np.sin(2 * np.pi * 440 * t)
        sf.write(self.test_wav, y, sr)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_backing_with_click_lazy_loads_y(self):
        """驗證 BackingWithClickSynthesizerNode 在 y 為 None 時能自動從 audio_path 讀取波形並成功匯出」"""
        bb = Blackboard()
        bb.set_val("audio_path", self.test_wav)
        bb.set_val("output_dir", self.temp_dir)
        self.assertIsNone(bb.get_val("y"))

        node = BackingWithClickSynthesizerNode()
        status = node.run(bb)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertIsNotNone(bb.get_val("backing_with_click_path"))
        self.assertTrue(os.path.exists(bb.get_val("backing_with_click_path")))


if __name__ == "__main__":
    unittest.main()
