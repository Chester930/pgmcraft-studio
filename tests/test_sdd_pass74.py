"""
SDD Pass 74 — Live PGM 工作流 5-2：舞台導聽 Click & Cue Voice 指示音軌自動生成狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.live_pgm_bt import build_live_click_cue_gen_workflow


class TestSDDPass74LiveClickCueGenWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "live_track.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.4).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_live_click_cue_gen_execution(self):
        """驗證 LiveClickCueGenRoot 狀態機成功導出 click_track.wav 與 cue_track.wav」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_live_click_cue_gen_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        clk_p = blackboard.get_val("click_track_path")
        cue_p = blackboard.get_val("cue_track_path")

        self.assertTrue(os.path.exists(clk_p))
        self.assertTrue(os.path.exists(cue_p))


if __name__ == "__main__":
    unittest.main()
