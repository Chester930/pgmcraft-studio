"""
SDD Pass 88 — Live 舞台雙聲道立體聲 IEM 分立路由 (iem_split_mono_lr.wav) 單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.export_bt import IEMSplitMonoLRNode


class TestSDDPass88IEMSplitMonoLR(unittest.TestCase):

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

    def test_iem_split_mono_lr_export(self):
        """驗證 IEMSplitMonoLRNode 成功導出雙聲道立體聲音檔 (L=Click, R=Backing)"""
        blackboard = Blackboard()
        y, sr = sf.read(self.audio_path)
        blackboard.set_val("y", y)
        blackboard.set_val("sr", sr)
        blackboard.set_val("output_dir", self.test_dir)
        blackboard.set_val("click_audio", y * 0.9)
        blackboard.set_val("stems", {"drums": y * 0.3, "bass": y * 0.3, "other": y * 0.3})

        node = IEMSplitMonoLRNode()
        status = node.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        out_p = blackboard.get_val("iem_split_mono_lr_path")
        self.assertIsNotNone(out_p)
        self.assertTrue(os.path.exists(out_p))

        data, out_sr = sf.read(out_p)
        self.assertEqual(data.ndim, 2)
        self.assertEqual(data.shape[1], 2)
        # L 聲道非空 (Click)
        self.assertGreater(np.max(np.abs(data[:, 0])), 0.01)
        # R 聲道非空 (Backing)
        self.assertGreater(np.max(np.abs(data[:, 1])), 0.01)


if __name__ == "__main__":
    unittest.main()
