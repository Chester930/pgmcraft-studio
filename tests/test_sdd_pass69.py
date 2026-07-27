"""
SDD Pass 69 — Vocal 工作流 3-4：人聲乾聲去殘響與聲音純化狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.vocal_bt import build_vocal_dereverb_clean_workflow


class TestSDDPass69VocalDeReverbCleanWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "vocal_with_reverb.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.3 + np.random.randn(sr) * 0.01).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_vocal_dereverb_clean_execution(self):
        """驗證 VocalDeReverbCleanRoot 狀態機成功去殘響並落盤錄音室乾聲」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_vocal_dereverb_clean_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        dry_p = blackboard.get_val("studio_vocal_path")

        self.assertTrue(os.path.exists(dry_p))
        y_dry, sr_d = sf.read(dry_p)
        self.assertGreater(len(y_dry), 0)


if __name__ == "__main__":
    unittest.main()
