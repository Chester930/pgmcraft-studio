"""
SDD Pass 73 — Live PGM 工作流 5-1：Live 舞台 Multi-Track 全分軌 DAW 素材包導出狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.live_pgm_bt import build_live_multitrack_package_workflow


class TestSDDPass73LiveMultiTrackPackageWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "live_performance.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 100 * t) * 0.4 + np.sin(2 * np.pi * 1000 * t) * 0.2).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_live_multitrack_package_execution(self):
        """驗證 LiveMultiTrackPackageRoot 狀態機成功封裝 pgm_project_package.zip」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_live_multitrack_package_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        zip_p = blackboard.get_val("zip_package_path")

        self.assertTrue(os.path.exists(zip_p))


if __name__ == "__main__":
    unittest.main()
