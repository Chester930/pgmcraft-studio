"""
SDD Pass 79 — ASMR 工作流 6-3：ASMR 雙耳 3D 空間環繞聲場增強狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.asmr_bt import build_asmr_spatial_binaural_enhance_workflow


class TestSDDPass79ASMRSpatialBinauralEnhanceWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "asmr_mono.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.4).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_asmr_spatial_binaural_enhance_execution(self):
        """驗證 ASMRSpatialBinauralEnhanceRoot 狀態機成功導出 ASMR_3D_Binaural_Spatial.wav」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_asmr_spatial_binaural_enhance_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        sp_p = blackboard.get_val("asmr_spatial_path")

        self.assertTrue(os.path.exists(sp_p))
        y, sr = sf.read(sp_p)
        self.assertGreaterEqual(y.ndim, 1)


if __name__ == "__main__":
    unittest.main()
