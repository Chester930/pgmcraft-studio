"""
SDD Pass 76 — Live PGM 工作流 5-4：Ableton Live / Logic Pro / Cubase 原生專案檔對齊狀態機單元測試
"""

import os
import tempfile
import unittest
import gzip
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.live_pgm_bt import build_live_daw_native_align_workflow


class TestSDDPass76LiveDAWNativeAlignWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "live_master.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.4).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_live_daw_native_align_execution(self):
        """驗證 LiveDAWNativeAlignRoot 狀態機成功導出 Ableton_Live_Project.als」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_live_daw_native_align_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        als_p = blackboard.get_val("als_project_path")

        self.assertTrue(os.path.exists(als_p))
        with gzip.open(als_p, 'rb') as f:
            xml_content = f.read().decode('utf-8')
            self.assertIn("Ableton", xml_content)


if __name__ == "__main__":
    unittest.main()
