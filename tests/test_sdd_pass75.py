"""
SDD Pass 75 — Live PGM 工作流 5-3：樂手即時 HTML5 視聽同步 HUD 控制台面板狀態機單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.live_pgm_bt import build_live_stage_hud_workflow


class TestSDDPass75LiveStageHUDWorkflow(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "live_show.wav")
        sr = 22050
        t = np.linspace(0, 1.0, sr, False)
        sig = (np.sin(2 * np.pi * 440 * t) * 0.4).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_live_stage_hud_execution(self):
        """驗證 LiveStageHUDRoot 狀態機成功導出 live_stage_hud.html」"""
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.audio_path)
        blackboard.set_val("output_dir", self.test_dir)

        tree = build_live_stage_hud_workflow()
        status = tree.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        hud_p = blackboard.get_val("hud_html_path")

        self.assertTrue(os.path.exists(hud_p))
        with open(hud_p, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("Live PGM Stage HUD", content)


if __name__ == "__main__":
    unittest.main()
